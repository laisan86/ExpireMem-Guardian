"""Offline D2 benchmark helpers. No provider calls or target-library import."""
from __future__ import annotations
from collections import Counter
from benchmark.guardian_d2 import assess, load_cases


def evaluate_cases() -> list[dict]:
    rows=[]
    for case in load_cases():
        result=assess(case)
        rows.append({
            "case_id":case["case_id"], "library":case["library"],
            "target_version":case["target_version"], "scenario":case["scenario"],
            "expected":case["expected_decision"], "actual":result["decision"],
            "match":case["expected_decision"] == result["decision"],
            "reason":result["reason"], "matched_symbols":result["matched"],
            "source_code":case["source_code"], "evidence_urls":case["evidence_urls"],
        })
    return rows


def evaluate_summary(rows: list[dict]) -> dict:
    return {"count":len(rows),"correct":sum(r["match"] for r in rows),
            "mismatches":sum(not r["match"] for r in rows),
            "distribution":dict(Counter(r["actual"] for r in rows)),
            "libraries":sorted({r["library"] for r in rows}),
            "caveat":"Frozen narrow AST baseline: benchmark agreement does not imply broad safety/generalization."}
