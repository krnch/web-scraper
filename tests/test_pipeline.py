import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from web_scraper.cli import main
from web_scraper.consumer import LocalConsumer
from web_scraper.pipeline import (
    MAX_INPUT_BYTES,
    ListingError,
    apply_filters,
    create_bundle,
    deduplicate,
    parse_html,
    parse_json,
    process_input,
    write_bundle,
)
from web_scraper.source import PermittedSource, SourceError, SourcePolicy, SourceResponse

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

    def test_descriptions_require_explicit_permission(self):
        text = '[{"id":"job-1","description":"Permitted fixture description"}]'
        self.assertNotIn("description", parse_json(text)[0])
        self.assertEqual(
            parse_json(text, include_description=True)[0]["description"],
            "Permitted fixture description",
        )

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

    def test_bundle_is_versioned_bounded_json_in_explicit_external_directory(self):
        records = process_input((FIXTURES / "listings.json").read_text(), "json")
        with tempfile.TemporaryDirectory() as directory:
            destination = write_bundle(create_bundle(records), Path(directory) / "bundle")
            bundle = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(bundle["schema_version"], "1.0")
        self.assertEqual(bundle["record_count"], len(bundle["records"]))
        self.assertEqual(destination.name, "listings-v1.json")

    def test_manifest_contains_contract_metadata_and_content_fingerprint(self):
        content = (FIXTURES / "listings.json").read_text(encoding="utf-8")
        records = process_input(content, "json", source="fixture-board")
        bundle = create_bundle(
            records,
            task_id="task-1",
            source_adapter_version="fixture-2",
            observed_at="2026-09-30T00:00:00Z",
            provenance={"source": "fixture-board", "license": "test"},
            content=content,
        )
        manifest = bundle["manifest"]
        self.assertEqual(manifest["task_id"], "task-1")
        self.assertEqual(manifest["source_adapter_version"], "fixture-2")
        self.assertEqual(manifest["core_version"], "0.1.0")
        self.assertEqual(manifest["content_size"], len(content.encode("utf-8")))
        self.assertEqual(manifest["record_count"], bundle["record_count"])
        self.assertEqual(bundle["generated_at"], manifest["observed_at"])

    def test_private_consumer_is_idempotent_and_preserves_human_decisions(self):
        records = parse_json(
            '[{"id":"job-1","title":"Engineer","datePosted":"2026-09-01",'
            '"validThrough":"2026-10-01"}]',
            source="fixture-board",
        )
        with tempfile.TemporaryDirectory() as directory:
            consumer = LocalConsumer(Path(directory) / "private-state.sqlite")
            bundle = create_bundle(records, observed_at="2026-09-30T00:00:00Z")
            self.assertEqual(consumer.import_bundle(bundle), {"imported": 1, "updated": 0})
            consumer.set_human_decision("source:fixture-board:job-1", "review")
            updated = parse_json(
                '[{"id":"job-1","title":"Updated Engineer"}]', source="fixture-board"
            )
            result = consumer.import_bundle(
                create_bundle(updated, observed_at="2026-09-30T01:00:00Z")
            )
            self.assertEqual(result, {"imported": 0, "updated": 1})
            state = consumer.get("source:fixture-board:job-1")
        self.assertEqual(state["human_decision"], "review")
        self.assertEqual(state["record"]["title"], "Updated Engineer")
        self.assertEqual(state["first_seen_at"], "2026-09-30T00:00:00Z")
        self.assertEqual(state["last_seen_at"], "2026-09-30T01:00:00Z")

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
            result = main(
                [
                    "--input",
                    str(input_path),
                    "--output-dir",
                    str(output_path),
                    "--task-id",
                    "fixture-task",
                    "--source-adapter-version",
                    "fixture-1",
                ]
            )
            bundle = json.loads((output_path / "listings-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(bundle["records"][0]["title"], "Offline role")
        self.assertEqual(bundle["manifest"]["task_id"], "fixture-task")


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.policy = SourcePolicy(
            frozenset({"approved.example"}),
            max_response_bytes=8,
            max_pages=2,
            max_retries=1,
        )

    @staticmethod
    def response(status=200, body=b"ok", location=None):
        headers = {} if location is None else {"Location": location}
        return SourceResponse(status, headers, body, "")

    def test_https_allowlist_and_private_address_guard_run_before_transport(self):
        transport = unittest.mock.Mock()
        source = PermittedSource(self.policy, transport=transport)
        with self.assertRaisesRegex(SourceError, "HTTPS"):
            source.fetch("http://approved.example/jobs")
        for blocked in ("127.0.0.1", "10.0.0.1", "169.254.1.1"):
            with self.assertRaisesRegex(SourceError, "not permitted|private"):
                source.fetch(f"https://{blocked}/jobs")
        transport.assert_not_called()

    @patch("web_scraper.source._host_is_public", return_value=True)
    def test_redirect_destination_is_revalidated(self, _public):
        responses = iter(
            [
                self.response(302, location="https://evil.example/jobs"),
            ]
        )
        source = PermittedSource(self.policy, transport=lambda request, timeout: next(responses))
        with self.assertRaisesRegex(SourceError, "not permitted"):
            source.fetch("https://approved.example/jobs")

    @patch("web_scraper.source._host_is_public", return_value=True)
    def test_response_size_is_bounded(self, _public):
        source = PermittedSource(
            self.policy,
            transport=lambda request, timeout: self.response(body=b"012345678"),
        )
        with self.assertRaisesRegex(SourceError, "8-byte"):
            source.fetch("https://approved.example/jobs")

    @patch("web_scraper.source._host_is_public", return_value=True)
    def test_pagination_and_retry_are_bounded(self, _public):
        calls = []
        responses = iter([self.response(503), self.response(body=b"page")])
        source = PermittedSource(
            self.policy,
            transport=lambda request, timeout: (calls.append(request.full_url), next(responses))[1],
            sleep=lambda delay: calls.append(delay),
        )
        pages = source.fetch_pages(
            "https://approved.example/jobs",
            lambda response: "https://approved.example/jobs?page=2" if len(calls) == 2 else None,
        )
        self.assertEqual(len(pages), 1)
        self.assertEqual(calls[1], 0.25)

    @patch("web_scraper.source._host_is_public", return_value=True)
    def test_pagination_limit_is_enforced(self, _public):
        source = PermittedSource(
            self.policy,
            transport=lambda request, timeout: self.response(body=b"page"),
        )
        with self.assertRaisesRegex(SourceError, "2-page"):
            source.fetch_pages(
                "https://approved.example/jobs",
                lambda response: "https://approved.example/jobs?page=next",
            )


if __name__ == "__main__":
    unittest.main()
