import argparse
import json
import sys
from pathlib import Path

from .pipeline import (
    MAX_INPUT_BYTES,
    ListingError,
    create_bundle,
    process_input,
    write_bundle,
)


def _read_limited(path):
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise ListingError(f"cannot read input file: {exc}") from exc
    if len(data) > MAX_INPUT_BYTES:
        raise ListingError(f"input exceeds the {MAX_INPUT_BYTES}-byte limit")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ListingError("input file must use UTF-8 encoding") from exc


def _format_for(path, text):
    suffix = Path(path).suffix.lower()
    if suffix in {".json", ".jsonld"}:
        return "json"
    if suffix in {".html", ".htm"}:
        return "html"
    return "json" if text.lstrip().startswith(("{", "[")) else "html"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Parse offline HTML/JSON listings into a bounded versioned bundle."
    )
    parser.add_argument("--input", required=True, help="local synthetic HTML or JSON file")
    parser.add_argument("--output-dir", required=True, help="explicit directory outside this Git worktree")
    parser.add_argument("--source", default="unknown", help="fallback source name for records")
    parser.add_argument("--filters", help="optional local JSON filter configuration")
    args = parser.parse_args(argv)

    try:
        text = _read_limited(args.input)
        input_format = _format_for(args.input, text)
        filters = json.loads(_read_limited(args.filters)) if args.filters else None
        records = process_input(text, input_format, source=args.source, filters=filters)
        destination = write_bundle(create_bundle(records), args.output_dir)
    except (ListingError, json.JSONDecodeError, OSError) as exc:
        print(f"web-scraper: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {len(records)} records to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
