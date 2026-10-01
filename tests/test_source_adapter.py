import unittest
from web_scraper.source_adapter import HTTPResult, PermittedSourceAdapter, SourceError, SourcePolicy


class FakeTransport:
    def __init__(self, responses=None, error=None):
        self._responses = list(responses or [])
        self._error = error
        self.calls = []

    def request(self, url, timeout_seconds, max_response_bytes):
        self.calls.append((url, timeout_seconds, max_response_bytes))
        if self._error is not None:
            raise self._error
        if not self._responses:
            raise AssertionError("no fake responses left")
        return self._responses.pop(0)


def public_resolver(hostname, port, type=None):
    return [
        (None, None, None, None, ("93.184.216.34", port)),
    ]


class AdapterTests(unittest.TestCase):
    def test_rejects_non_https_and_credentials(self):
        adapter = PermittedSourceAdapter(transport=FakeTransport(), resolver=public_resolver)

        insecure = SourcePolicy(
            source_id="x",
            source_name="x",
            start_url="http://jobs.example/listings.json",
            allowed_hosts=("jobs.example",),
            input_format="json",
        )
        with self.assertRaisesRegex(SourceError, "only https"):
            list(adapter.fetch_pages(insecure))

        with_credentials = SourcePolicy(
            source_id="x",
            source_name="x",
            start_url="https://user:pass@jobs.example/listings.json",
            allowed_hosts=("jobs.example",),
            input_format="json",
        )
        with self.assertRaisesRegex(SourceError, "embedded credentials"):
            list(adapter.fetch_pages(with_credentials))

    def test_blocks_private_and_link_local_addresses(self):
        for blocked_ip in ("169.254.1.10", "127.0.0.1", "10.1.2.3"):
            def resolver(hostname, port, type=None):
                return [(None, None, None, None, (blocked_ip, port))]

            adapter = PermittedSourceAdapter(transport=FakeTransport(), resolver=resolver)
            policy = SourcePolicy(
                source_id="x",
                source_name="x",
                start_url="https://jobs.example/listings.json",
                allowed_hosts=("jobs.example",),
                input_format="json",
            )
            with self.assertRaisesRegex(SourceError, "private/link-local"):
                list(adapter.fetch_pages(policy))

    def test_rejects_redirect_to_disallowed_host(self):
        transport = FakeTransport(
            responses=[
                HTTPResult(
                    status=302,
                    headers={"location": "https://evil.example/jobs"},
                    body=b"",
                )
            ]
        )
        adapter = PermittedSourceAdapter(transport=transport, resolver=public_resolver)
        policy = SourcePolicy(
            source_id="x",
            source_name="x",
            start_url="https://jobs.example/listings.json",
            allowed_hosts=("jobs.example",),
            input_format="json",
        )

        with self.assertRaisesRegex(SourceError, "allowlist"):
            list(adapter.fetch_pages(policy))

    def test_enforces_response_size_limit(self):
        transport = FakeTransport(
            responses=[HTTPResult(status=200, headers={}, body=b"12345678901")]
        )
        adapter = PermittedSourceAdapter(transport=transport, resolver=public_resolver)
        policy = SourcePolicy(
            source_id="x",
            source_name="x",
            start_url="https://jobs.example/listings.json",
            allowed_hosts=("jobs.example",),
            input_format="json",
            max_response_bytes=10,
        )

        with self.assertRaisesRegex(SourceError, "max size"):
            list(adapter.fetch_pages(policy))

    def test_timeout_retry_uses_bounded_backoff(self):
        sleeps = []
        transport = FakeTransport(error=TimeoutError("timed out"))
        times = iter([0.0, 0.0, 0.1, 0.2, 0.3])
        adapter = PermittedSourceAdapter(
            transport=transport,
            resolver=public_resolver,
            sleeper=sleeps.append,
            monotonic=lambda: next(times),
        )
        policy = SourcePolicy(
            source_id="x",
            source_name="x",
            start_url="https://jobs.example/listings.json",
            allowed_hosts=("jobs.example",),
            input_format="json",
            max_retries=1,
            backoff_seconds=0.8,
            max_backoff_seconds=0.5,
        )

        with self.assertRaisesRegex(SourceError, "request failed"):
            list(adapter.fetch_pages(policy))
        self.assertEqual(sleeps, [0.5])

    def test_pagination_stops_at_page_limit(self):
        transport = FakeTransport(
            responses=[
                HTTPResult(
                    status=200,
                    headers={"link": '<https://jobs.example/page-2.json>; rel="next"'},
                    body=b"[]",
                ),
                HTTPResult(
                    status=200,
                    headers={"link": '<https://jobs.example/page-3.json>; rel="next"'},
                    body=b"[]",
                ),
                HTTPResult(status=200, headers={}, body=b"[]"),
            ]
        )
        adapter = PermittedSourceAdapter(transport=transport, resolver=public_resolver)
        policy = SourcePolicy(
            source_id="x",
            source_name="x",
            start_url="https://jobs.example/page-1.json",
            allowed_hosts=("jobs.example",),
            input_format="json",
            max_pages=2,
        )

        pages = list(adapter.fetch_pages(policy))
        self.assertEqual(len(pages), 2)
        self.assertEqual(
            [call[0] for call in transport.calls],
            [
                "https://jobs.example/page-1.json",
                "https://jobs.example/page-2.json",
            ],
        )

    def test_registry_blocks_arbitrary_source_ids(self):
        from web_scraper.pipeline import collect_from_source

        class StubAdapter:
            def fetch_pages(self, policy):
                yield "[]", "json"

        with self.assertRaisesRegex(Exception, "unknown source id"):
            collect_from_source("does-not-exist", StubAdapter())


if __name__ == "__main__":
    unittest.main()
