# ExpireMem Guardian

**Verify before you execute.** A version-aware safety gate and auditable repair workflow for coding agents, demonstrated with public API-deprecation evidence and a fixed Python test fixture.

This repository is a **public, deliberately scoped source release** of the ExpireMem Guardian Studio v0.8.2 demonstration. It contains no private provider responses, keys, experiment ledgers, unpublished research documents, or recording assets. The original v0.3 Guardian core is preserved byte-for-byte.

## See the demo locally (no API key; no model or network call)

Tested for the fixed replay using Python 3.12.2 and pandas 2.2.3 on macOS. Other environments are not asserted identical to the recorded historical Baseten run.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-demo.txt
python demo_offline.py
python run_tests.py
```

Expected central results:

```text
RED exit code: 1
RED error: AttributeError: 'DataFrame' object has no attribute 'append' ...
Decision: ABSTAIN
Mode: GREEN_OFFLINE_REPLAY
Proposal origin: OFFLINE_REPLAY_RULE
GREEN exit code: 0
GREEN output: ... two expected rows: old, new
```

The code deliberately triggers a genuine `AttributeError` on a **fixed seeded fixture** (not a naturally generated model error), applies a local deterministic reference patch to `pd.concat`, checks it and executes it in the same selected Python interpreter. Offline success must **never** be relabeled `GREEN_VERIFIED_MUSE`. The simple version-rule baseline also catches the removed API.

## Studio (optional; run locally)

```bash
python -m streamlit run studio_app.py
```

The six-tab local Studio provides fixed RED→GREEN replay, a curated 14-case version-rule benchmark, API lifecycle examples, a controlled gapped-index task case, official-document evidence, and a local Evidence Vault. **Do not deploy the private-receipt upload interface on a public server.** The Studio does not automatically send provider requests.

Optional CLI checks are `python d4_offline_review.py`, `python d5_evaluation.py --execute-fixed-cases`, and `python d5_freeze_readiness.py`. These are offline tests and readiness checks, not provider attestations or fitted empirical calibration. A manual `one_shot_judge.py` integration is included for code completeness but **requires explicit user authorization and may incur API charges**; it is not used in this release validation. No provider calls are necessary for assessment.

## How the controlled case works

1. **ASSESS:** inspect actual source using AST and identify `DataFrame.append`.
2. **ABSTAIN:** version rule rejects use on pandas 2.2.3. A rule-only baseline can already do this.
3. **REFRESH:** in the *historical v0.3 run*, the host retrieved allowlisted [official pandas 2.0.0 release notes](https://pandas.pydata.org/docs/whatsnew/v2.0.0.html); the model did not autonomously call a tool.
4. **PROPOSE:** in that separately recorded run, Baseten-hosted `meta-models/muse-spark-open-1026` proposed a constrained JSON replacement after the host supplied the official excerpt and an explicit `pd.concat` migration template.
5. **VALIDATE + EXECUTE:** restrictive AST checks and the fixture subprocess verified the candidate. The historical receipt recorded `GREEN_VERIFIED_MUSE`; this public repository does not contain private raw receipts or independently authenticate that provider event.

The **public replay** executes only steps and observations in a separate offline mode: `GREEN_OFFLINE_REPLAY`. It must not be presented as a new Baseten inference or as reenactment of the complete historical call.

## Code map

| File / area | Purpose |
|---|---|
| `core/guardian_core.py` | Frozen v0.3 narrow Guardian AST, version gate, and fixed fixture |
| `core/muse_baseten.py` | Original constrained Baseten model proposal client; no automatic calls |
| `replay.py` and `demo_offline.py` | Offline fixture replay and easy CLI entrypoint |
| `studio_app.py` | Six-tab local Streamlit Studio |
| `benchmark/` | Curated 14-case rule-only baseline (not a population metric) |
| `d4_*`, `d5_*` | Auxiliary offline adapters, reference-oracle validation, and readiness |
| `tests/` and `run_tests.py` | Bounded regression tests; test success is not a security proof |

## Results and limitations

Read **[LIMITATIONS.md](LIMITATIONS.md)** and **[REPRODUCIBILITY.md](REPRODUCIBILITY.md)** before interpreting claims. Particularly: there is no measured overall agent-success improvement, no demonstrated superiority over a version-rule baseline on the simple pandas example, no independently validated generic Python sandbox, no fitted UNKNOWN-rule calibration, and no generalization from one verified controlled case. Auxiliary oracle witnesses validate a narrow frozen test set, not arbitrary data-correctness proofs.

## Provenance, privacy and rights

* Public release intentionally omits personal/local paths, keys, attempt-lock ledgers, private raw Baseten/Meta model reasoning, raw response IDs, private research notes, backups and archived filming material.
* **No API request or paid inference is triggered by `demo_offline.py` or `run_tests.py`.**
* No exact private model transcript or vendor receipt is included. The local Evidence Vault is not a service for collecting public uploads.
* A software license has **not yet been selected** for this public release. GitHub visibility by itself does not grant reuse permissions. The repository owner must decide licensing and ensure any institutional IP/brand clearance before publication.
* The hackathon video may carry a Taipei Tech department end slate; that identification is not an assertion of institutional sponsorship or endorsement. The artwork and video are not included in the source package.

[Security guidance](SECURITY.md) · [Reproducibility](REPRODUCIBILITY.md) · [Limitations](LIMITATIONS.md)
