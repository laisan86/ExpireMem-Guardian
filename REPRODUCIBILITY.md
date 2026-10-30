# Reproducing the public controlled demo

## Intended environment

The filmed Mac offline replay used **Python 3.12.2 / pandas 2.2.3**. The separately saved historical provider execution used a different interpreter and must not be represented by this replay.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-demo.txt
python demo_offline.py
python run_tests.py
```

No provider key, internet document fetch, or Baseten request is necessary to run these commands. The dependency installation itself uses the package index, unless dependencies are pre-cached. Tests use synthetic mocks or offline fixtures, not paid provider calls.

Confirm that the terminal prints `RED exit code: 1`, a genuine `AttributeError` referring to `append`, `Decision: ABSTAIN`, `Mode: GREEN_OFFLINE_REPLAY`, `GREEN exit code: 0`, and two expected rows (`old`, `new`).

`python replay.py` by itself imports the replay function but does not launch a demo; use `python demo_offline.py` or `from replay import run_offline`.

For the optional local UI:

```bash
python -m streamlit run studio_app.py
```

The Studio's evidence upload is for **local** inspection of documents you already own. Do not host it publicly with private receipts.

## Interpretation

The local deterministic rule supplies the offline patch expression; it does not call the Muse model. The original model's successful constrained patch proposal is a different historical case whose private raw response is intentionally excluded. The AST whitelist verifies a narrow allowed replacement structure; the fixture's expected rows are a controlled correctness check, not proof of general program safety.
