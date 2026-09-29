# Web Scraper — plan

## Purpose

Build reusable collection and parsing tools, including generic job-search connectors and normalized listing schemas. Publish safe examples that help others develop/test the software. Do not equate producing more records with permission to operate a continuous personal service on Actions.

## Public core and examples

1. Offline HTML/JSON parsers and normalized listing schema: source, identifier, title, company, location, canonical URL and observation time.
2. Deduplication, pagination logic, retries and configurable non-personal filters.
3. Explicitly permitted source connectors with attribution and documented access/rate policies.
4. Synthetic fixtures and tests; public dataset examples only after redistribution/privacy review.
5. Optional AI extraction/ranking later with opt-in, caching and per-run cost limits.

No existing private application's source, history or datasets have been copied. Any future extraction needs license and privacy review first.

## Private runtime

Resumes, identities, contact information, location/salary preferences, application records, login cookies, credentials, personalized rankings and production target queues stay in separate private storage/execution. A public job title/URL can be part of an approved example; it is not automatically secret, nor automatically free to republish.

Automatic job application submission is not in scope. Keep any future submission behind explicit human approval, separate from collection.

## Development milestones

1. Select a code license and define schemas/source-adapter contract.
2. Implement fixture-only parsing, deduplication and filters with offline tests. No runtime LLM is required.
3. Add one source only after verifying its permitted API/access, robots instructions, site terms and redistribution conditions. Prefer documented APIs; robots allowance alone is not a license.
4. Enforce HTTPS host allowlists, redirect revalidation, private/link-local address rejection, response-size/page/time limits and respectful retry/backoff. Never fetch arbitrary issue-submitted URLs with private network or credential access.
5. Review a manual development workflow: one job at a time, 15-minute timeout, no schedule, no credentials, no automatic artifact upload or dataset commit. Proposed live-source cap: 20 pages and one request/second OR the site's stricter limits; stop on blocking/rate-limit responses rather than evade them.
6. Review actual outputs, measure time/disk, remove contact/identity data and obtain approval before any public dataset release or recurring refresh.

All caps are proposed, not code already implemented. No CAPTCHA solving, login/paywall circumvention, proxy rotation to evade limits or browser cookie injection is part of the plan.

## Dataset generation versus running a private service

- Strong development fit: parse synthetic job pages, test schema drift against an approved small sample, publish reproducible parser benchmarks.
- Case-specific proposal: a bounded, useful public dataset/example refresh with source permission, provenance, privacy review and a clear connection to the tool. Confirm suitability before relying on scheduled hosted compute.
- Outside the initial scope: continuously search for one person's jobs, operate their private application queue, or use a public repository as a facade for an always-on private backend.

An issue can request a connector or document a bug. It should not contain a resume, private target list, login or untrusted command to execute. Use a separate private queue for real personal work. All branches in a public repository are public.

## Compute and AI constraints

As checked September 29, 2026, the public Linux x64 `ubuntu-latest` standard runner has 4 CPU cores, 16 GB RAM and 14 GB SSD. Its eligible minute usage is free, not unrestricted use: runtime, concurrency, storage, source-site and acceptable-use limits apply. Paid larger runners are a different offering, even in public repos. Scheduled Actions can be delayed and are not a production availability guarantee.

Deterministic parsers need no model calls. Optional AI consumes the selected provider's quota independently of runner pricing. Copilot subscription credits are not a generic external LLM API balance. Keep optional AI disabled in the first development workflow; do not copy personal Copilot tokens into CI.

## References

- [Runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [Actions limits](https://docs.github.com/en/actions/reference/limits)
- [Actions terms](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features#actions)
- [Cloud-agent costs](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent#copilot-cloud-agent-usage-costs)
- [GitHub Support](https://support.github.com/)