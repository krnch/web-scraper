# Data and publication boundary

## Allowed public material

Generic original/licensed code, schemas, documentation, synthetic pages/listings, reviewed permitted-source adapters and approved non-sensitive dataset examples with provenance.

## Keep outside public execution

Resumes, application records, contact details, account cookies, passwords/tokens, personal filters, private URLs and production queues. Store them in a separate private directory/repository and access-controlled data store. Public CI must not check out that private state.

## Important limitations

- `.gitignore` is an accidental-staging guard, not access control or history removal.
- All branches of a public repository are public. A branch named `private` does not hide its files.
- GitHub Secrets do not stop a program or AI agent from leaking sensitive results into logs, summaries, artifacts, issues or PRs. Masking does not guarantee redaction of transformed data.
- Public artifacts are broadly accessible to signed-in repository readers, not private application storage.
- Do not give untrusted pull requests/issues access to credentials or arbitrary commands/URLs. Review dependencies and use least-privilege permissions.
- Public accessibility is not permission to bulk scrape, bypass access controls or redistribute a site's content. Respect source policies, privacy and data licenses.

Before dataset publication: verify source permissions and provenance, remove personal/contact details, inspect exact fields and output manifest, cap size/retention, and obtain explicit approval. Personal job applications require a separate private workflow and human confirmation.