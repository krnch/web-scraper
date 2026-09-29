import json
import os
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_INPUT_BYTES = 1_000_000
MAX_RECORDS = 100
MAX_FIELD_LENGTHS = {
    "source": 100,
    "identifier": 256,
    "title": 500,
    "company": 300,
    "location": 300,
    "canonical_url": 2048,
    "observed_at": 100,
}
SCHEMA_VERSION = "1.0"
FIELDS = frozenset(MAX_FIELD_LENGTHS)
ALIASES = {
    "source": ("source", "provider", "site"),
    "identifier": ("identifier", "id", "job_id", "jobId", "positionId"),
    "title": ("title", "job_title", "jobTitle", "name"),
    "company": ("company", "company_name", "companyName", "hiringOrganization"),
    "location": ("location", "job_location", "jobLocation"),
    "canonical_url": ("canonical_url", "url", "apply_url", "applyUrl"),
    "observed_at": ("observed_at", "observedAt", "date_posted", "datePosted"),
}
TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "ref",
    "source",
}
REPOSITORY_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()),
    None,
)


class ListingError(ValueError):
    pass


def _text(value, max_length):
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    value = " ".join(str(value).split())
    return value[:max_length] or None


def _nested_text(field, value):
    if field == "location" and isinstance(value, list):
        return ", ".join(
            str(normalized)
            for item in value
            if (normalized := _nested_text(field, item))
        )
    if not isinstance(value, dict):
        return value
    if field == "identifier":
        return value.get("value") or value.get("name")
    if field == "company":
        return value.get("name")
    if field == "location":
        address = value.get("address", value)
        if isinstance(address, dict):
            return ", ".join(
                str(address[key])
                for key in ("addressLocality", "addressRegion", "addressCountry")
                if address.get(key)
            )
    return value


def canonicalize_url(value):
    value = _text(value, MAX_INPUT_BYTES)
    if value is None:
        return None
    if len(value) > MAX_FIELD_LENGTHS["canonical_url"]:
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        hostname = parts.hostname.encode("idna").decode("ascii").lower()
        host_for_netloc = f"[{hostname}]" if ":" in hostname else hostname
        port = parts.port
        netloc = host_for_netloc if port is None else f"{host_for_netloc}:{port}"
        if (parts.scheme.lower(), port) in {("http", 80), ("https", 443)}:
            netloc = host_for_netloc
        path = parts.path or "/"
        if path != "/":
            path = path.rstrip("/")
        query = urlencode(
            sorted(
                (key, val)
                for key, val in parse_qsl(
                    parts.query, keep_blank_values=True, max_num_fields=100
                )
                if key.lower() not in TRACKING_PARAMETERS
                and not key.lower().startswith("utm_")
            )
        )
        canonical = urlunsplit((parts.scheme.lower(), netloc, path, query, ""))
        return canonical if len(canonical) <= MAX_FIELD_LENGTHS["canonical_url"] else None
    except (UnicodeError, ValueError):
        return None


def normalize_record(record, source="unknown"):
    if not isinstance(record, dict):
        raise ListingError("each listing must be a JSON object")

    normalized = {}
    for field, aliases in ALIASES.items():
        value = next((record[key] for key in aliases if key in record), None)
        if field == "source" and value is None:
            value = source
        value = _nested_text(field, value)
        if field == "canonical_url":
            value = canonicalize_url(value)
        else:
            value = _text(value, MAX_FIELD_LENGTHS[field])
        normalized[field] = value
    return normalized


def _records_from_json(value):
    if isinstance(value, list):
        records = value
    elif isinstance(value, dict):
        records = next(
            (
                value[key]
                for key in ("records", "listings", "jobs", "data")
                if isinstance(value.get(key), list)
            ),
            None,
        )
        if records is None:
            records = [value]
    else:
        raise ListingError("JSON input must be an object or an array of listings")
    if len(records) > MAX_RECORDS:
        raise ListingError(f"input exceeds the {MAX_RECORDS}-record batch limit")
    return records


def parse_json(text, source="unknown"):
    _check_text_size(text)
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ListingError(f"malformed JSON input: {exc}") from exc
    return [normalize_record(item, source=source) for item in _records_from_json(payload)]


class _OfflineHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.jsonld = []
        self.embedded = []
        self._script_parts = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "script" and "ld+json" in attrs.get("type", "").lower():
            self._script_parts = []
        embedded = attrs.get("data-job") or attrs.get("data-listing")
        if embedded:
            try:
                self.embedded.extend(_records_from_json(json.loads(embedded)))
            except (json.JSONDecodeError, ListingError, RecursionError):
                raise ListingError("malformed JSON in HTML data-job/data-listing attribute")
            if len(self.embedded) > MAX_RECORDS:
                raise ListingError(f"input exceeds the {MAX_RECORDS}-record batch limit")

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._script_parts is not None:
            content = "".join(self._script_parts).strip()
            try:
                self.jsonld.append(json.loads(content))
            except (json.JSONDecodeError, RecursionError) as exc:
                raise ListingError(f"malformed JSON-LD script: {exc}") from exc
            self._script_parts = None

    def handle_data(self, data):
        if self._script_parts is not None:
            self._script_parts.append(data)


def _job_postings(value):
    if isinstance(value, list):
        for item in value:
            yield from _job_postings(item)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if any(
            isinstance(item, str) and item.rsplit("/", 1)[-1] == "JobPosting"
            for item in types
        ):
            yield value
        graph = value.get("@graph")
        if graph is not None:
            yield from _job_postings(graph)


def parse_html(text, source="unknown"):
    _check_text_size(text)
    parser = _OfflineHTMLParser()
    try:
        parser.feed(text)
        parser.close()
        if parser._script_parts is not None:
            raise ListingError("unterminated JSON-LD script")
    except ListingError:
        raise
    except Exception as exc:
        raise ListingError(f"malformed HTML input: {exc}") from exc

    records = list(parser.embedded)
    for document in parser.jsonld:
        for record in _job_postings(document):
            records.append(record)
            if len(records) > MAX_RECORDS:
                raise ListingError(f"input exceeds the {MAX_RECORDS}-record batch limit")
    return [normalize_record(item, source=source) for item in records]


def _check_text_size(text):
    if not isinstance(text, str):
        raise ListingError("input must be UTF-8 text")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ListingError("input must be UTF-8 text") from exc
    if size > MAX_INPUT_BYTES:
        raise ListingError(f"input exceeds the {MAX_INPUT_BYTES}-byte limit")


def identity_key(record):
    if record.get("canonical_url"):
        return "url:" + record["canonical_url"]
    if record.get("identifier"):
        return f"source:{record.get('source') or 'unknown'}:{record['identifier']}"
    return None


def deduplicate(records):
    unique = []
    seen = set()
    for record in records:
        key = identity_key(record)
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        unique.append(record)
    return unique


def _values(value):
    return value if isinstance(value, list) else [value]


def apply_filters(records, filters=None):
    if filters is None:
        filters = {}
    allowed = {"include", "contains", "exclude_contains", "require"}
    if not isinstance(filters, dict) or set(filters) - allowed:
        raise ListingError(f"filters must contain only: {', '.join(sorted(allowed))}")

    for mode in ("include", "contains", "exclude_contains"):
        rules = filters.get(mode, {})
        if not isinstance(rules, dict) or set(rules) - FIELDS:
            raise ListingError(f"{mode} filters must use normalized listing fields")
        if sum(len(_values(value)) for value in rules.values()) > MAX_RECORDS:
            raise ListingError(f"{mode} filters exceed the {MAX_RECORDS}-value limit")
        for field, value in rules.items():
            if any(
                not isinstance(item, (str, int, float))
                or len(str(item)) > MAX_FIELD_LENGTHS[field]
                for item in _values(value)
            ):
                raise ListingError(f"{mode} filter values must be bounded scalar values")
    required = filters.get("require", [])
    if (
        not isinstance(required, list)
        or len(required) > len(FIELDS)
        or any(field not in FIELDS for field in required)
    ):
        raise ListingError("require filters must be a list of normalized listing fields")

    selected = []
    for record in records:
        keep = all(record.get(field) is not None for field in required)
        for field, expected in filters.get("include", {}).items():
            actual = record.get(field)
            if actual not in _values(expected):
                keep = False
        for field, fragments in filters.get("contains", {}).items():
            actual = (record.get(field) or "").casefold()
            if not any(str(item).casefold() in actual for item in _values(fragments)):
                keep = False
        for field, fragments in filters.get("exclude_contains", {}).items():
            actual = (record.get(field) or "").casefold()
            if any(str(item).casefold() in actual for item in _values(fragments)):
                keep = False
        if keep:
            selected.append(record)
    return selected


def process_input(text, input_format, source="unknown", filters=None):
    if input_format == "json":
        records = parse_json(text, source=source)
    elif input_format == "html":
        records = parse_html(text, source=source)
    else:
        raise ListingError("input format must be 'html' or 'json'")
    return apply_filters(deduplicate(records), filters)


def create_bundle(records):
    if len(records) > MAX_RECORDS:
        raise ListingError(f"bundle exceeds the {MAX_RECORDS}-record limit")
    records = deduplicate([normalize_record(record) for record in records])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }


def _safe_output_directory(output_dir):
    raw = os.fspath(output_dir)
    if not raw or any(part == ".." for part in raw.replace("\\", "/").split("/")):
        raise ListingError("output directory must not contain path traversal")
    candidate = Path(raw).absolute()
    for path in (candidate, *candidate.parents):
        if path.is_symlink():
            raise ListingError("output directory must not traverse symbolic links")
    resolved = candidate.resolve()
    if REPOSITORY_ROOT is not None:
        try:
            resolved.relative_to(REPOSITORY_ROOT)
        except ValueError:
            pass
        else:
            raise ListingError("output directory must be outside the Git worktree")
    return resolved


def write_bundle(bundle, output_dir):
    if not isinstance(bundle, dict) or bundle.get("schema_version") != SCHEMA_VERSION:
        raise ListingError(f"bundle must use schema version {SCHEMA_VERSION}")
    records = bundle.get("records")
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise ListingError(f"bundle must contain at most {MAX_RECORDS} records")
    directory = _safe_output_directory(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "listings-v1.json"
    safe_bundle = create_bundle(records)
    encoded = (json.dumps(safe_bundle, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".listings-", delete=False) as temporary:
            temporary.write(encoded)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return destination
