# Manager execution brief — Web Scraper

Updated September 29, 2026. **Task specification; no collector, agent or schedule is running.** Begin implementation when the owner delegates this brief. This documentation PR is not permission to start arbitrary scraping or unattended spend.

## Mission

Build reusable job-source collection, normalization and deduplication tools that feed a separate private job-search/application tracker. The goal is useful job records and a functioning import contract, not tests or planning documents alone.

Coordinate with [video-analysis](https://github.com/krnch/video-analysis): start with **two active implementation workers total, at most one per repository**. “Hyperscale” describes this coordination strategy; no special executable hyperscale mode exists in this repository yet. Actions concurrency does not establish AI/session concurrency.

## Manager's first actions

1. Read this brief, [PLAN.md](PLAN.md), [DATA_BOUNDARY.md](DATA_BOUNDARY.md) and [EXECUTION.md](EXECUTION.md). Check existing code and open tasks/PRs to avoid duplicate work.
2. Record a task ID, implementation branch, worker and status. If this documentation PR is unmerged, use its branch as the specification; do not silently merge it or unrelated changes.
3. Start **W1** with new generic code and synthetic fixtures. Do not copy private source, resumes, application records or credentials. Record the code license decision and review any third-party provenance.
4. Return a working implementation PR with exact test/reproduction evidence, then update the next milestone. Do not create more planning-only PRs instead of implementing the core.

## Work packages

### W1 — usable offline job-record pipeline (first implementation PR)

- Create a small installable CLI/library using an appropriate maintained stack; Python is a sensible baseline. Document supported versions and entry points.
- Parse synthetic HTML/JSON listing fixtures into a versioned job-record schema.
- Normalize allowed fields and canonical source identities; deduplicate repeated observations without confusing distinct postings with the same title/company.
- Add generic user-supplied filters, with no embedded personal profile, resume or real target list.
- Emit a bounded JSON/JSONL result bundle and manifest to an explicit output directory. Real runtime records must not be committed.
- Define concrete configuration bounds. Proposed initial defaults: <=1 MB input/response, <=100 records/batch, bounded field lengths and a task deadline below the 15-minute proposed demo cap. Reject unsafe paths and malformed input.

**Acceptance:** a documented offline command produces normalized records; fixtures prove correct extraction, missing-field handling, canonicalization and deduplication; malformed/oversized input and output traversal fail clearly; tests make no external network or model calls.

### W2 — permitted-source adapter with network safeguards

- Implement a pluggable source-adapter contract and test HTTP behavior against mocks/a loopback test server; a real site's permission is not needed to test the interface.
- Add HTTPS host allowlisting, bounded redirects with destination revalidation, private/link-local destination protection, response-size limits, request deadlines, bounded pagination and respectful backoff.
- Proposed initial live cap, only after source approval: one permitted public source, <=20 pages, <=1 request/second or the site's stricter limit. Bound errors/retries and stop on blocking or rate-limit instructions.
- Prefer documented APIs; respect source policies. No login/CAPTCHA/paywall bypass, cookie injection or proxy rotation to evade limits. Do not fetch arbitrary issue-supplied URLs.
- A real connector and source configuration need explicit review of permitted collection, storage and redistribution. Public accessibility alone is not permission.

**Acceptance:** tests cover off-allowlist redirects, restricted addresses, timeout, oversized response, pagination cap and throttle/backoff. The default CLI remains offline or explicitly requires an approved source configuration; tests do not scrape a real board.

### W3 — private-consumer contract and measurement

- Produce the task/result contract below, stable deduplication IDs and offline bundle validation.
- Add a mock/local consumer test: repeated imports update last-seen state rather than creating duplicate jobs/applications; malformed or partial bundles are not imported.
- Keep resume-based fit scoring, application status and human decisions in the private consumer. Optional AI extraction can be designed with mocks, explicit opt-in and budget limits, not activated by default.
- Measure accepted unique records, extraction correctness, duplicates, elapsed time, source requests and output bytes. Record measured AI usage if available; otherwise `unknown`.

**Acceptance:** a consumer can safely import the same bundle repeatedly without losing existing application state. No live private application's endpoint is assumed or claimed verified.

## Private-result contract

Manifest: `schema_version`, `task_id`, core/source-adapter version, observation time, source provenance, result hash/byte length and record count. Records include source ID, source job ID or deterministic fallback identity, title, company, location, canonical public URL and available posting/expiry dates. Include descriptions only where permitted and within field limits.

No resume, personal contact detail, login cookie, private preferences, application answers or signed delivery URL in public-side logs, manifests or agent prompts. Do not automatically commit live feeds to either public or private Git repositories.

Final product flow: permitted collection -> normalized/deduplicated bundle -> authenticated private delivery -> private matching and application tracking. The private consumer owns personal data and submission decisions. No automatic application submission is part of this project.

A future transfer must have task-scoped authentication, content validation, durable receipts and idempotent import. A sleeping destination requires an approved private buffer or paused admission. Private storage is not provided by a public branch, Actions artifacts or ephemeral runner scratch space.

## Coordination and capacity

- The manager enforces the two-worker global limit across repositories; per-repo Actions concurrency groups do not enforce a shared cross-repo limit. Until centralized tracking exists, dispatch manually and verify active sessions.
- One implementation writer per repo. Do not silently spawn additional cloud agents, repeat uncertain dispatches or run recursive review/fix loops without bounds.
- Benchmark one worker before two. Up to five independent standard Actions jobs requires separate approval/evidence; supported model/session concurrency must be checked independently.
- Increase capacity only if accepted output improves within the approved cost/quality target. Respect other workflows sharing account limits.
- On provider throttling, record sanitized scope/status/reset information and honor retry instructions. Stop on exhausted budgets, authorization uncertainty, repeated failure or an empty useful backlog. Do not rotate identities/IPs to evade restrictions or generate requests merely to hit a limit.

## Runtime gates — offline implementation can proceed

W1 and mocked W2/W3 are implementable without private systems or real source access. Keep the following as separate runtime blockers rather than delaying all code:

- Owner-approved real source and its access, rate, storage and redistribution conditions.
- Verified private tracker's import/storage interface before claiming live compatibility.
- Supported AI access and a numeric credit/paid-overage cap before unattended model dispatch or runtime inference.
- Selected private destination and authenticated delivery before real record transfer.
- Workload suitability and owner approval before relying on Actions for sustained collection. Private outputs alone do not establish eligibility for free production compute.
- Review before adding executable workflows: manual and bounded development first, no schedule, secrets, private-repo checkout, live dataset artifact upload or paid larger runners by default.

Do not treat organization membership as proof of remaining model credits. Ordinary offline implementation in the owner's delegated session is different from launching unattended cloud agents or collection jobs.

## Manager completion report

Update [EXECUTION.md](EXECUTION.md) per milestone with task ID, branch/commit/PR, implementation summary, actual test commands/results, fixture/source provenance, accepted unique-record metrics, limitations and next step. Distinguish mocked tests from real-source results and real private imports.

Do not merge PRs, release datasets or apply for jobs automatically.

## Definition of first useful result

**A reproducible CLI produces correct deduplicated job records and a verified private-importable bundle, with tests and no personal-data exposure.** Then add one permitted real source and measure useful collection rather than maximizing requests or duplicate records.