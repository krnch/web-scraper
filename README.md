# Web Scraper

A planned reusable toolkit for permitted-source collection, parsing, deduplication and job-search data normalization.

**Status: documentation-only.** No runnable scraper, scheduled collection, job dataset, AI integration or Actions workflow exists yet.

## Intended first version

- Parse offline synthetic HTML/JSON fixtures into a documented listing schema.
- Deduplicate records and apply generic, configurable job-search filters.
- Add explicitly permitted public APIs/pages later, with host allowlists, rate limits and bounded pagination.
- Keep personal ranking inputs and application activity in a separate private runtime.

This is not a CAPTCHA/login bypass tool, an automatic application service or an unlimited free hosted scraping backend.

## Documentation

- [Plan and compute constraints](PLAN.md)
- [Execution state and acceptance checklist](EXECUTION.md)
- [Data and publication boundary](DATA_BOUNDARY.md)

A code license must be selected before releasing implementation code. Publicly accessible web pages do not automatically grant permission to scrape or republish their contents.