# Security, privacy, and disclosure

**Public repository content:** public API examples, source for a fixed demo, curated public benchmarks, and offline tests. There are no user-provided API secrets, private provider response bodies, raw reasoning traces or attempt-lock ledgers in this release package.

**Do not upload:** local `.env` values, `BASETEN_API_KEY`, Meta credentials, personal paths, unpublished lab/industry research, proprietary internal artifacts, raw receipts, provider reasoning or user datasets.

**Do not deploy `studio_app.py` as a public multi-user evidence-upload app.** The Evidence Vault is intended for a trusted, local environment. Provider scripts that require explicit acknowledgements can make real paid requests; do not run them for the offline demo.

**Important:** this application does not sandbox arbitrary Python and is not a general-purpose secret scanner. Run only known fixed fixtures and examine third-party input before processing it.

To report a sensitive disclosure, contact the repository owner through a private channel; do not open a public issue containing a credential or exploit transcript.
