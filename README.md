# Web Scraper

A reusable toolkit for offline listing parsing, deduplication and normalization.

The first release is an offline-only parser and does not fetch pages, use models, or run scheduled collection.

## Install and run

Requires Python 3.10 or later.

```sh
python -m pip install .
web-scraper --input ./synthetic-jobs.json --output-dir /tmp/listings
```

`--input` accepts local `.json`, `.html`, or `.htm` files (otherwise inferred from content). JSON can be a listing object, an array, or an object containing a `records`, `listings`, `jobs`, or `data` array. HTML extraction supports Schema.org `JobPosting` JSON-LD and JSON in `data-job`/`data-listing` attributes. Input is capped at 1 MB and 100 records per batch.

The normalized listing schema is versioned and includes `source`, `identifier`, `title`, `company`, `location`, `canonical_url`, `observed_at`, `posting_date`, and `expiry_date`. Missing fields are `null`; extra fields are discarded. Descriptions are excluded unless `--include-descriptions` is explicitly used for a permitted source. URLs are canonicalized by lowercasing the host, removing fragments and common tracking parameters, and sorting remaining query parameters. Records deduplicate by canonical URL or by source plus identifier, never by title alone.

Each bundle also contains a manifest with the task ID, source-adapter and core versions, observation time, provenance, source content SHA-256/byte size, and record count. The CLI hashes the local fixture input and writes this metadata alongside the records.

`LocalConsumer` is an optional private SQLite consumer. It keys records by canonical URL or source plus job identifier, updates `last_seen_at` on re-import, and leaves an existing `human_decision` unchanged. It stores listing state only; resumes, personal ranking, and application records are intentionally not part of the public bundle or consumer schema.

Filters are optional JSON in `--filters`; supported keys are `include` (exact match), `contains`, `exclude_contains`, and `require`. The first three map normalized field names to a value or list of values. For example:

```json
{
  "contains": {"title": "engineer"},
  "exclude_contains": {"location": "onsite"},
  "require": ["title", "canonical_url"]
}
```

The CLI requires an explicit `--output-dir`, rejects traversal and symbolic-link paths, and refuses to write inside the Git worktree. It writes a bounded `listings-v1.json` bundle there; generated data is not committed to this repository.

This is not a CAPTCHA/login bypass tool, an automatic application service or an unlimited hosted scraping backend. Live collection requires a separate source-approval and safety review.

## Documentation

- [Plan and compute constraints](PLAN.md)
- [Execution state and acceptance checklist](EXECUTION.md)
- [Data and publication boundary](DATA_BOUNDARY.md)

A code license must be selected before releasing implementation code. Publicly accessible web pages do not automatically grant permission to scrape or republish their contents.