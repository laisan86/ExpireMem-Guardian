# Limitations and evidence boundaries

This public code demonstrates a controlled API-deprecation safety workflow. It is not an estimate of coding-agent population accuracy or a production-ready arbitrary-code sandbox.

- **Fixed fixture, not naturally model-generated failure.** `DataFrame.append` was intentionally seeded and fails on pandas 2.2.3.
- **Rule-only baseline also abstains.** The known version gate already detects `DataFrame.append` on pandas ≥ 2.0. There is no measured performance advantage over that baseline.
- **Host-orchestrated evidence.** The host retrieves official documentation from an allowlist; the model did not independently discover or fetch the official page. SHA-256 supports consistency checking, not independent authenticity or a digital signature.
- **Constrained model proposal.** In the separately recorded historical v0.3 run, the host supplied the relevant official excerpt **and a `pd.concat` template**; Muse supplied bounded JSON candidate content. This is not autonomous API repair discovery, and this repository does not independently authenticate the private provider receipt.
- **Historical run vs public replay.** The recorded 2026-10-27 Baseten run labeled `GREEN_VERIFIED_MUSE` and the 2026-10-30 Mac `GREEN_OFFLINE_REPLAY` are distinct executions. The offline public replay cannot support live-provider attribution.
- **Controlled execution only.** A restrictive AST whitelist plus subprocess execution on fixed data is not a sandbox for untrusted arbitrary Python. Exit status 0 is not sufficient for general task correctness.
- **Auxiliary demos are not equivalently attested.** NumPy lifecycle judgments require exact pinned runtime verification; silent data-loss Case C uses an independent controlled offline task oracle. The D4 oracle reference is handwritten; frozen witnesses are finite tests, not a mathematical proof or live Muse-authored oracle. D5 lacks independent UNKNOWN-rule score data for fitted calibration.
- **No population claim.** Test counts, frozen benchmark fixtures, or historical provider results do not establish measured general coding-agent accuracy, broad reliability or a causal Guardian uplift.
- **Security/privacy boundaries.** Never paste API keys, raw provider reasoning, private research, attempt-locks or internal records into a public repository or a hosted Studio.

The project should be evaluated as an **auditable, bounded proof of workflow**, not as a demonstrated universal autonomous repair system.
