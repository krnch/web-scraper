import json
import tempfile
import unittest
from pathlib import Path

from web_scraper.cli import main
from web_scraper.pipeline import (
    MAX_INPUT_BYTES,
    ListingError,
    apply_filters,
    create_bundle,
    collect_from_source,
    deduplicate,
    parse_html,
    parse_json,
    process_input,
    write_bundle,
)

FIXTURES = Path(__file__).parent / "fixtures"


class PipelineTests(unittest.TestCase):
    def test_json_normalizes_allowlisted_fields_and_deduplicates_canonical_urls(self):
        text = (FIXTURES / "listings.json").read_text(encoding="utf-8")
        records = process_input(text, "json")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["title"], "Senior Engineer")
        self.assertEqual(records[0]["canonical_url"], "https://jobs.example/jobs/eng-1")
        self.assertNotIn("private_note", records[0])
        self.assertNotIn("description", records[0])

    def test_same_title_does_not_deduplicate_distinct_jobs(self):
        records = parse_json(
            json.dumps(
                [
                    {"id": "one", "title": "Developer"},
                    {"id": "two", "title": "Developer"},
                ]
            ),
            source="board",
        )
        self.assertEqual(len(deduplicate(records)), 2)

    def test_missing_fields_are_normalized_to_none(self):
        record = parse_json('[{"id": "minimal"}]')[0]
        self.assertEqual(record["identifier"], "minimal")
        self.assertIsNone(record["title"])
        self.assertIsNone(record["canonical_url"])

    def test_html_extracts_json_ld_job_postings(self):
        text = (FIXTURES / "listings.html").read_text(encoding="utf-8")
        records = parse_html(text, source="synthetic-html")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Data Analyst")
        self.assertEqual(records[0]["company"], "Example Analytics")
        self.assertEqual(records[0]["location"], "Remote")
        self.assertEqual(records[0]["identifier"], "analyst-7")

    def test_generic_configurable_filters(self):
        records = parse_json(
            '[{"title":"Engineer","location":"Remote"},'
            '{"title":"Designer","location":"New York"}]'
        )
        selected = apply_filters(
            records,
            {"contains": {"title": "eng"}, "exclude_contains": {"location": "new"}},
        )
        self.assertEqual([record["title"] for record in selected], ["Engineer"])

    def test_malformed_and_oversized_inputs_fail_clearly(self):
        with self.assertRaisesRegex(ListingError, "malformed JSON"):
            parse_json("{")
        with self.assertRaisesRegex(ListingError, "byte limit"):
            parse_json(" " * (MAX_INPUT_BYTES + 1))

    def test_batch_limit_is_checked_before_deduplication(self):
        with self.assertRaisesRegex(ListingError, "100-record"):
            parse_json(json.dumps([{"url": "https://example.com"}] * 101))

    def test_fields_are_bounded_and_invalid_urls_are_omitted(self):
        record = parse_json(
            json.dumps(
                [
                    {"title": "x" * 700, "url": "javascript:alert(1)"},
                    {"url": "https://example.com/" + "x" * 2100},
                ]
            )
        )[0]
        self.assertEqual(len(record["title"]), 500)
        self.assertIsNone(record["canonical_url"])
        long_url = "https://example.com/" + "x" * 2100
        self.assertIsNone(parse_json(json.dumps([{"url": long_url}]))[0]["canonical_url"])

    def test_malformed_json_ld_fails_clearly(self):
        with self.assertRaisesRegex(ListingError, "malformed JSON-LD"):
            parse_html('<script type="application/ld+json">{</script>')

    def test_url_canonicalization_handles_ipv6_hosts(self):
        record = parse_json('[{"url":"https://[2001:db8::1]:443/job#details"}]')[0]
        self.assertEqual(record["canonical_url"], "https://[2001:db8::1]/job")

    def test_url_canonicalization_preserves_non_tracking_query_parameters(self):
        record = parse_json(
            '[{"url":"https://jobs.example/role?source=remote&ref=engineering"}]'
        )[0]
        self.assertEqual(
            record["canonical_url"],
            "https://jobs.example/role?ref=engineering&source=remote",
        )


    def test_collect_from_source_uses_policy_and_parses_pages(self):
        class StubAdapter:
            def fetch_pages(self, policy):
                self.policy = policy
                yield '[{"url":"https://jobs.example/one","title":"One"}]', "json"
                yield '[{"url":"https://jobs.example/one","title":"One duplicate"}]', "json"

        adapter = StubAdapter()
        records = collect_from_source("synthetic-board", adapter)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source"], "synthetic-board")
        self.assertEqual(records[0]["title"], "One")

    def test_bundle_is_versioned_bounded_json_in_explicit_external_directory(self):
        records = process_input((FIXTURES / "listings.json").read_text(), "json")
        with tempfile.TemporaryDirectory() as directory:
            destination = write_bundle(create_bundle(records), Path(directory) / "bundle")
            bundle = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(bundle["schema_version"], "1.0")
        self.assertEqual(bundle["record_count"], len(bundle["records"]))
        self.assertEqual(destination.name, "listings-v1.json")

    def test_unsafe_output_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ListingError, "path traversal"):
                write_bundle(create_bundle([]), Path(directory) / ".." / "unsafe")
            with self.assertRaisesRegex(ListingError, "outside the Git worktree"):
                write_bundle(create_bundle([]), Path(__file__).resolve().parents[1] / "output")

    def test_cli_writes_bundle_from_local_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "listings.json"
            output_path = root / "bundle"
            input_path.write_text('[{"title":"Offline role","id":"local-1"}]', encoding="utf-8")
            result = main(["--input", str(input_path), "--output-dir", str(output_path)])
            bundle = json.loads((output_path / "listings-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(bundle["records"][0]["title"], "Offline role")


if __name__ == "__main__":
    unittest.main()
