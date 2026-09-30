from .source_adapter import SourcePolicy


PERMITTED_SOURCES = {
    "synthetic-board": SourcePolicy(
        source_id="synthetic-board",
        source_name="synthetic-board",
        start_url="https://jobs.example/listings.json",
        allowed_hosts=("jobs.example",),
        input_format="json",
        max_pages=20,
        timeout_seconds=10.0,
        max_response_bytes=1_000_000,
        max_redirects=3,
        max_retries=2,
        backoff_seconds=0.25,
        max_backoff_seconds=2.0,
    )
}


def get_source_policy(source_id: str) -> SourcePolicy:
    try:
        return PERMITTED_SOURCES[source_id]
    except KeyError as exc:
        raise ValueError(f"unknown source id: {source_id}") from exc
