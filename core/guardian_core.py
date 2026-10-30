"""ExpireMem Guardian v0.2 — explicit public-API version rules and Muse patch candidates.

Scope: public pandas deprecation only. No unpublished research code,
private documents, secret handling, or automatic paid calls.
"""
from __future__ import annotations

import ast
import difflib
import os
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Callable
from urllib.parse import urlparse

import pandas as pd
from packaging.version import Version, InvalidVersion

OFFICIAL_DOC = "https://pandas.pydata.org/docs/whatsnew/v2.0.0.html"
EVIDENCE_ID = "pandas-2.0.0-removed-dataframe-append-gh35407"
SCHEMA_VERSION = "0.3"

BUGGY_CODE = '''import pandas as pd
print("runtime pandas:", pd.__version__)
df = pd.DataFrame([{"id": 1, "name": "old"}])
df = df.append({"id": 2, "name": "new"}, ignore_index=True)
assert df.to_dict(orient="records") == [
    {"id": 1, "name": "old"}, {"id": 2, "name": "new"}
]
print("GREEN: rows=", df.to_dict(orient="records"))
'''


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_text(s: str):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.suppress = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg"): self.suppress += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg") and self.suppress: self.suppress -= 1

    def handle_data(self, data):
        if not self.suppress: self.parts.append(data)


def inspect_source(src: str) -> dict[str, Any]:
    """Recognize one DataFrame.append(dict, ignore_index=True) under narrow AST scope.

    This is NOT a general security validator; demo source must be a trusted fixture.
    """
    try: tree = ast.parse(src)
    except SyntaxError as exc:
        return {"recognized": False, "reason": f"SyntaxError: {exc.msg}", "append_calls": [], "line": exc.lineno}
    has_pandas = any(isinstance(n, ast.Import) and any(
        a.name == "pandas" and a.asname == "pd" for a in n.names) for n in tree.body)
    df_vars = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                and fn.value.id == "pd" and fn.attr == "DataFrame"):
                df_vars.update(t.id for t in node.targets if isinstance(t, ast.Name))
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append":
            recv = node.func.value
            shape = (len(node.args) == 1 and isinstance(node.args[0], ast.Dict)
                     and len(node.keywords) == 1 and node.keywords[0].arg == "ignore_index"
                     and isinstance(node.keywords[0].value, ast.Constant)
                     and node.keywords[0].value.value is True)
            matches.append({"variable": recv.id if isinstance(recv, ast.Name) else None,
                            "line": node.lineno, "valid_rewrite_shape": shape})
    recognized = (has_pandas and len(matches) == 1 and matches[0]["variable"] in df_vars
                  and matches[0]["valid_rewrite_shape"])
    return {"recognized": recognized, "append_calls": matches,
            "dataframe_vars": sorted(df_vars), "reason": "supported fixture" if recognized else "unsupported/ambiguous source"}


def version_gate(source: str, pandas_version: str) -> dict[str, Any]:
    scan = inspect_source(source)
    try: version = Version(pandas_version)
    except InvalidVersion:
        return {"decision": "ABSTAIN", "reason": "Unparseable runtime version", "scan": scan}
    if not scan["append_calls"]:
        return {"decision": "PASS", "reason": "No .append detected by this narrow rule; NOT a correctness guarantee", "scan": scan}
    if not scan["recognized"]:
        return {"decision": "ABSTAIN", "reason": "Unsupported/ambiguous append pattern", "scan": scan}
    if version >= Version("2.0.0"):
        return {"decision": "ABSTAIN", "reason": "DataFrame.append was REMOVED in pandas 2.0; execution blocked pending refresh/remediation", "scan": scan}
    if version >= Version("1.4.0"):
        return {"decision": "WARN", "reason": "DataFrame.append is DEPRECATED, still available in pandas 1.4–1.x", "scan": scan}
    return {"decision": "PASS", "reason": "Rule does not mark this method removed in the selected older runtime", "scan": scan}


def verify_official_document(timeout=12, fetch=None) -> dict[str, Any]:
    """REFRESH stage: re-fetch official primary evidence, or return UNAVAILABLE."""
    injected = fetch is not None
    if fetch is None:
        from urllib.request import Request, urlopen
        def fetch(url, timeout):
            req = Request(url, headers={"User-Agent": "ExpireMemGuardianDemo/0.3"})
            with urlopen(req, timeout=timeout) as res:
                return res.geturl(), res.read(2_000_000).decode("utf-8", "replace")
    try:
        final_url, html = fetch(OFFICIAL_DOC, timeout)
        p = urlparse(final_url)
        if (p.scheme, p.hostname, p.path) != ("https", "pandas.pydata.org", "/docs/whatsnew/v2.0.0.html"):
            raise ValueError("Official documentation redirected to unapproved URL")
        text_parser = _TextOnly(); text_parser.feed(html)
        plain = re.sub(r"\s+", " ", " ".join(text_parser.parts)).lower()
        match = re.search(r"removed deprecated.{0,180}(?:dataframe\.append\(\)).{0,140}(?:concat\(\))", plain)
        if not match:
            raise ValueError("Official page did not contain expected removal + replacement statement")
        return {"status": "VERIFIED_TEST_INJECTION" if injected else "VERIFIED_LIVE",
                "source": final_url, "checked_at": utc_now(),
                "evidence_id": EVIDENCE_ID, "excerpt": match.group(0)[:350], "page_sha256": sha256_text(html)}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "source": OFFICIAL_DOC, "checked_at": utc_now(),
                "reason": f"{type(exc).__name__}: {str(exc)[:240]}"}


def _known_append_call(source: str) -> ast.Call:
    scan = inspect_source(source)
    if not scan["recognized"]: raise ValueError("Not a supported fixture shape")
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "append"]
    if len(calls) != 1: raise ValueError("Ambiguous number of append calls")
    return calls[0]


def deterministic_expression(source: str) -> str:
    call = _known_append_call(source)
    receiver = call.func.value.id
    original_dict = ast.unparse(call.args[0])
    return f"pd.concat([{receiver}, pd.DataFrame([{original_dict}])], ignore_index=True)"


def validate_candidate_expression(source: str, expression: str) -> dict[str, Any]:
    """Accept only an AST-exact replacement shape and original dictionary/receiver.

    This whitelist stops side effects inside the replacement expression. It is
    intentionally fixture-specific, not a sandbox for arbitrary model code.
    """
    if not isinstance(expression, str) or len(expression) > 4000:
        raise ValueError("Candidate expression must be a short string")
    original = _known_append_call(source)
    try: node = ast.parse(expression, mode="eval").body
    except SyntaxError as exc: raise ValueError(f"Invalid candidate syntax: {exc.msg}") from exc
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "pd"
            and node.func.attr == "concat" and len(node.args) == 1
            and isinstance(node.args[0], ast.List) and len(node.args[0].elts) == 2
            and len(node.keywords) == 1 and node.keywords[0].arg == "ignore_index"
            and isinstance(node.keywords[0].value, ast.Constant) and node.keywords[0].value.value is True):
        raise ValueError("Candidate not a whitelisted pd.concat call")
    receiver, frame = node.args[0].elts
    if not (isinstance(receiver, ast.Name) and receiver.id == original.func.value.id):
        raise ValueError("Receiver variable changed")
    if not (isinstance(frame, ast.Call) and isinstance(frame.func, ast.Attribute)
            and isinstance(frame.func.value, ast.Name) and frame.func.value.id == "pd"
            and frame.func.attr == "DataFrame" and len(frame.args) == 1
            and isinstance(frame.args[0], ast.List) and len(frame.args[0].elts) == 1
            and not frame.keywords):
        raise ValueError("Candidate must wrap original record as a DataFrame")
    if ast.dump(frame.args[0].elts[0], include_attributes=False) != ast.dump(original.args[0], include_attributes=False):
        raise ValueError("Original row data changed")
    return {"expression": ast.unparse(node), "candidate_sha256": sha256_text(expression)}


class _SingleCallReplace(ast.NodeTransformer):
    def __init__(self, source_node: ast.Call, replacement: ast.AST):
        self.source_node = source_node; self.replacement = replacement; self.count = 0

    def visit_Call(self, node):
        if node is self.source_node:
            self.count += 1
            return ast.copy_location(self.replacement, node)
        return self.generic_visit(node)


def fix_fixture_code(source: str, pandas_version: str, evidence: dict, *, replacement_expression: str | None = None) -> str:
    """Convert a blocked (ABSTAIN) removal into a narrowly validated patch."""
    original_gate = version_gate(source, pandas_version)
    if original_gate["decision"] != "ABSTAIN" or not original_gate["scan"]["recognized"] or Version(pandas_version) < Version("2.0.0"):
        raise RuntimeError("Patch denied: removal gate was not activated")
    if evidence.get("status") not in ("VERIFIED_LIVE", "VERIFIED_TEST_INJECTION") or evidence.get("evidence_id") != EVIDENCE_ID:
        raise RuntimeError("Patch denied: REFRESH lacked verified live official evidence")
    expression = deterministic_expression(source) if replacement_expression is None else replacement_expression
    candidate = validate_candidate_expression(source, expression)
    tree = ast.parse(source)
    target = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "append")
    transformer = _SingleCallReplace(target, ast.parse(candidate["expression"], mode="eval").body)
    fixed = ast.fix_missing_locations(transformer.visit(tree))
    if transformer.count != 1: raise RuntimeError("Patch denied: expected exactly one replacement")
    result = ast.unparse(fixed) + "\n"
    compile(result, "guardian_patch", "exec")
    if version_gate(result, pandas_version)["decision"] != "PASS":
        raise RuntimeError("Patched code still blocked by narrow version gate")
    return result


def make_muse_prompt(source: str, red_stderr: str, evidence: dict) -> str:
    """Send only public fixture + official excerpt; no private secrets or ledger."""
    if evidence.get("status") not in ("VERIFIED_LIVE", "VERIFIED_TEST_INJECTION"): raise RuntimeError("No verified source: deny Muse prompt")
    return ("You are proposing one narrowly scoped pandas API migration. "
            "Return ONLY JSON with key replacement_expr, with a Python expression string. "
            "Replace the single DataFrame.append(dict, ignore_index=True) with "
            "pd.concat([original_dataframe, pd.DataFrame([original_dict])], ignore_index=True). "
            "Keep the receiver name and exact original row contents. No other statements/imports. "
            "Your patch is untrusted and will undergo AST validation and execution tests.\n\n"
            f"Official URL: {evidence['source']}\nOfficial excerpt: {evidence['excerpt']}\n"
            f"Original public fixture:\n{source}\n"
            f"Actual stderr (truncated):\n{red_stderr[-1200:]}\n")


def parse_muse_reply(reply: str) -> str:
    """Require strict JSON object to avoid treating prose or fences as code."""
    data = json.loads(reply)
    if not isinstance(data, dict) or set(data.keys()) != {"replacement_expr"} or not isinstance(data["replacement_expr"], str):
        raise ValueError("Muse response must be JSON with one string: replacement_expr")
    return data["replacement_expr"]


def run_in_same_environment(path: Path) -> dict[str, Any]:
    t0 = time.perf_counter()
    # Inherit no API credentials or unrelated environment variables in the child.
    # The input is the trusted, controlled fixture + strictly AST-validated replacement.
    clean_env = {"PATH": str(Path(sys.executable).parent),
                 "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([sys.executable, str(path)], text=True, capture_output=True,
                          timeout=25, cwd=str(path.parent), check=False, env=clean_env)
    return {"command": [sys.executable, path.name], "returncode": proc.returncode,
            "stdout": proc.stdout[-8000:], "stderr": proc.stderr[-8000:],
            "elapsed_seconds": round(time.perf_counter()-t0, 4)}


def run_demo(output_dir: Path | str, *, fetch=None, allow_offline_replay=False,
             muse_proposer: Callable[[str], str] | None = None) -> dict[str, Any]:
    """Run one controlled fixture. Live Muse is injected, never called by default.

    Production safety: never run arbitrary untrusted input using this fixture harness.
    Run only in an isolated disposable runtime with no credentials in subprocess.
    """
    directory = Path(output_dir)
    if directory.exists() and any(directory.iterdir()):
        raise RuntimeError("Nonempty demo output directory: refuse overwrite/stale snapshot")
    directory.mkdir(parents=True, exist_ok=True)
    before = directory / "buggy_pandas_append.py"
    after = directory / "fixed_pandas_concat.py"
    env_version = pd.__version__
    if Version(env_version) < Version("2.0.0"):
        raise RuntimeError("Requires pandas >= 2.0 for real removed-method demonstration")
    audit = []
    def log(stage, **fields):
        audit.append({"at": utc_now(), "stage": stage, **fields})
    initial = version_gate(BUGGY_CODE, env_version)
    log("ASSESS", decision=initial["decision"], reason=initial["reason"])
    before.write_text(BUGGY_CODE, encoding="utf-8")
    red = run_in_same_environment(before)
    red_ok = (red["returncode"] != 0 and "AttributeError" in red["stderr"]
              and "has no attribute 'append'" in red["stderr"])
    log("RED_FIXTURE", outcome="RED_CONFIRMED" if red_ok else "ABSTAIN", returncode=red["returncode"])
    evidence = {"status": "NOT_REQUESTED"}
    authorization = "BLOCKED"
    repaired_gate = None
    green = None
    patch_origin = None
    proposal_rejected = None
    model_evidence = None
    patch_diff = None
    outcome = "ABSTAIN"
    note = None
    if not red_ok or initial["decision"] != "ABSTAIN":
        note = "Red traceback mismatch or removed-API gate not activated"
    else:
        log("ABSTAIN", cause="Removed API not permitted to execute")
        evidence = verify_official_document(fetch=fetch)
        log("REFRESH", outcome=evidence["status"], source=evidence["source"])
        authorization = "AUTHORIZED" if evidence["status"] in ("VERIFIED_LIVE", "VERIFIED_TEST_INJECTION") else "BLOCKED"
        log("REASSESS", original_decision="ABSTAIN", remediation_authorization=authorization,
            detail="Original code remains blocked; only a constrained repair may be proposed")
        if authorization == "BLOCKED" and not allow_offline_replay:
            note = "REFRESH unavailable: no patch or Muse call"
        else:
            try:
                if authorization == "BLOCKED":
                    # Explicit fixture-only replay: NEVER treat as verified, NEVER call Muse,
                    # and do not invoke fix_fixture_code with fake verification.
                    proposal_expr = deterministic_expression(BUGGY_CODE)
                    _ = validate_candidate_expression(BUGGY_CODE, proposal_expr)
                    patch_origin = "OFFLINE_REPLAY_RULE"
                    tree = ast.parse(BUGGY_CODE)
                    target = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                                  and isinstance(n.func, ast.Attribute) and n.func.attr == "append")
                    patcher = _SingleCallReplace(target, ast.parse(proposal_expr, mode="eval").body)
                    fixed_tree = ast.fix_missing_locations(patcher.visit(tree))
                    if patcher.count != 1: raise RuntimeError("Offline fixture transform count mismatch")
                    replacement = ast.unparse(fixed_tree) + "\n"
                    note = "OFFLINE_REPLAY only: not live evidence, no Muse call"
                elif muse_proposer is not None:
                    patch_origin = "MUSE_PROPOSAL"
                    prompt = make_muse_prompt(BUGGY_CODE, red["stderr"], evidence)
                    reply = muse_proposer(prompt)
                    # This receipt is independent of validity of the proposed patch:
                    # a bad JSON/AST reply still leaves a provider audit record.
                    model_evidence = getattr(muse_proposer, "receipt", None)
                    proposal_expr = parse_muse_reply(reply)
                    log("PROPOSE", origin=patch_origin, proposal_sha256=sha256_text(reply),
                        provenance=model_evidence and model_evidence.get("transport_kind"))
                    replacement = fix_fixture_code(BUGGY_CODE, env_version, evidence,
                                                   replacement_expression=proposal_expr)
                else:
                    patch_origin = "VERSION_RULE_BASELINE"
                    log("PROPOSE", origin=patch_origin, proposal_sha256=sha256_text(deterministic_expression(BUGGY_CODE)))
                    replacement = fix_fixture_code(BUGGY_CODE, env_version, evidence)
                log("VALIDATE_PATCH", status="AST_WHITELIST_PASS", patched_sha256=sha256_text(replacement))
                repaired_gate = version_gate(replacement, env_version)
                log("REASSESS_PATCHED", decision=repaired_gate["decision"])
                if repaired_gate["decision"] != "PASS": raise ValueError("Patched source failed version gate")
                patch_diff = "".join(difflib.unified_diff(
                    BUGGY_CODE.splitlines(keepends=True), replacement.splitlines(keepends=True),
                    fromfile="buggy_pandas_append.py", tofile="fixed_pandas_concat.py"))
                (directory / "candidate_patch.diff").write_text(patch_diff, encoding="utf-8")
                candidate_path = directory / "candidate_pandas_concat.py"
                candidate_path.write_text(replacement, encoding="utf-8")
                green = run_in_same_environment(candidate_path)
                ok = green["returncode"] == 0 and "GREEN: rows=" in green["stdout"]
                from muse_baseten import BasetenOneShotProposer
                real_provider = (patch_origin == "MUSE_PROPOSAL"
                                 and isinstance(muse_proposer, BasetenOneShotProposer)
                                 and muse_proposer.transport is None
                                 and isinstance(model_evidence, dict)
                                 and model_evidence.get("transport_kind") == "baseten_real"
                                 and model_evidence.get("response_sha256")
                                 and model_evidence.get("response_id"))
                if ok:
                    # Only an executed and passing patch earns the accepted file name.
                    os.replace(candidate_path, after)
                    outcome = ("GREEN_OFFLINE_REPLAY" if patch_origin == "OFFLINE_REPLAY_RULE"
                               else "GREEN_TEST_INJECTION_MUSE" if patch_origin == "MUSE_PROPOSAL" and (evidence["status"] != "VERIFIED_LIVE" or not real_provider)
                               else "GREEN_TEST_INJECTION_RULE" if evidence["status"] == "VERIFIED_TEST_INJECTION"
                               else "GREEN_VERIFIED_MUSE" if real_provider
                               else "GREEN_VERIFIED_RULE" if patch_origin == "VERSION_RULE_BASELINE"
                               else "GREEN_TEST_INJECTION_MUSE")
                else:
                    outcome = "ABSTAIN"
                    proposal_rejected = "Candidate executed but validation output/exit code failed"
                log("EXECUTE_PATCHED", outcome=outcome, returncode=green["returncode"],
                    accepted=after.is_file())
            except Exception as exc:
                if muse_proposer is not None and model_evidence is None:
                    model_evidence = getattr(muse_proposer, "receipt", None)
                outcome = "ABSTAIN"
                proposal_rejected = f"{type(exc).__name__}: {str(exc)[:250]}"
                note = "Candidate rejected; no unverified patch accepted"
                log("REJECT_PROPOSAL", reason=proposal_rejected)
    report = {
        "schema": SCHEMA_VERSION, "project": "ExpireMem Guardian", "generated_at": utc_now(),
        "runtime": {"python": sys.version.split()[0], "pandas": env_version, "executable": sys.executable},
        "decision": initial, "post_refresh": {"original_decision": initial["decision"], "remediation_authorization": authorization},
        "patched_decision": repaired_gate, "version_rule_baseline": {"decision": initial["decision"],
            "detects_removed": initial["decision"] == "ABSTAIN"},
        "evidence": evidence, "red": red, "red_confirmed": red_ok, "green": green,
        "patched": after.is_file(), "proposal_origin": patch_origin, "proposal_rejected": proposal_rejected,
        "model_evidence": model_evidence, "candidate_diff_sha256": sha256_text(patch_diff) if patch_diff is not None else None,
        "outcome": outcome, "note": note, "audit_trace": audit,
        "limits": ["Public controlled fixture only, not a sandbox for arbitrary code",
                   "Version-rule baseline already detects this simple case",
                   "MUSE_PROPOSAL means model suggested a patch, not it was trusted",
                   "Injected official HTML yields GREEN_TEST_INJECTION, not verified-live evidence",
                   "A mock Muse proposer is not a live model call",
                   "GREEN_VERIFIED_MUSE requires genuine official retrieval AND a real Baseten response receipt",
                   "Executed candidates remain unaccepted until all checks pass",
                   "No unpublished research methods"]}
    (directory / "guardian_demo_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="./guardian_run")
    p.add_argument("--offline-replay", action="store_true")
    args = p.parse_args()
    r = run_demo(args.out, allow_offline_replay=args.offline_replay)
    print(json.dumps({"outcome": r["outcome"], "initial_decision": r["decision"]["decision"],
                      "red": r["red_confirmed"], "green": r["green"] and r["green"]["returncode"] == 0,
                      "evidence": r["evidence"]["status"]}, indent=2))
