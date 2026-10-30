"""Read-only validator for PRIVATE v0.3 audit artifacts.

No network, no credential access. Validates internal consistency, not authenticity
of the provider or independence of the execution environment.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

MAX_UPLOAD_BYTES = 2_500_000


def parse_json_bytes(blob: bytes) -> dict[str, Any]:
    if not isinstance(blob, bytes) or len(blob) > MAX_UPLOAD_BYTES:
        raise ValueError("JSON exceeds safe upload size or invalid binary input")
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError("Expected one JSON object")
    return data


def canonical_response_hash(raw: dict) -> str:
    # Exact v0.3 BasetenOneShotProposer canonicalization.
    encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def inspect_guardian_report(report: dict, raw_provider: dict | None = None) -> dict:
    """Whitelisted readback; never echo private paths or provider raw content."""
    if not isinstance(report, dict):
        raise ValueError("Report must be an object")
    declared = report.get("outcome")
    model = report.get("model_evidence")
    model = model if isinstance(model, dict) else {}
    red = report.get("red") if isinstance(report.get("red"), dict) else {}
    green = report.get("green") if isinstance(report.get("green"), dict) else {}
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    initial = report.get("decision") if isinstance(report.get("decision"), dict) else {}
    checks = {
        "red_traceback": report.get("red_confirmed") is True
                         and red.get("returncode") not in (None, 0)
                         and "AttributeError" in str(red.get("stderr", ""))
                         and "has no attribute 'append'" in str(red.get("stderr", "")),
        "removed_api_blocked": initial.get("decision") == "ABSTAIN",
        "official_refreshed": evidence.get("status") == "VERIFIED_LIVE"
            and evidence.get("source") == "https://pandas.pydata.org/docs/whatsnew/v2.0.0.html",
        "real_baseten_receipt": (model.get("transport_kind") == "baseten_real"
            and model.get("model_requested") == "meta-models/muse-spark-open-1026"
            and model.get("model_returned") == "meta-models/muse-spark-open-1026"
            and bool(model.get("response_id")) and bool(model.get("response_sha256"))),
        "green_execution": report.get("patched") is True
            and green.get("returncode") == 0
            and "GREEN: rows=" in str(green.get("stdout", "")),
        "outcome_claim": declared == "GREEN_VERIFIED_MUSE",
    }
    verification = "NOT_SUPPLIED"
    if raw_provider is not None:
        if not isinstance(raw_provider, dict):
            raise ValueError("Raw provider response must be a JSON object")
        expected = model.get("response_sha256")
        computed = canonical_response_hash(raw_provider)
        verification = "MATCH" if expected and expected == computed else "MISMATCH"
        checks["provider_raw_hash_match"] = verification == "MATCH"
        checks["provider_response_id_match"] = model.get("response_id") == raw_provider.get("id")
        checks["provider_model_match"] = model.get("model_returned") == raw_provider.get("model")
    return {
        "claimed_outcome": str(declared)[:80],
        "structural_checks": checks,
        "structurally_consistent": all(checks.values()),
        "provider_raw_hash_check": verification,
        "evidence_status": str(evidence.get("status", "UNKNOWN"))[:80],
        "pandas_runtime": str((report.get("runtime") or {}).get("pandas", "?"))[:36],
        "model": str(model.get("model_returned", "unknown"))[:90],
        "total_tokens": (model.get("usage") or {}).get("total_tokens"),
        "model_seconds": model.get("elapsed_seconds"),
        "model_usage": (model.get("usage") or {}),
        "audit_stages": [str(e.get("stage", ""))[:48]
                         for e in report.get("audit_trace", []) if isinstance(e, dict)][:32],
        "evidence_sha256": str(evidence.get("page_sha256", ""))[:64],
        "code_diff_sha256": str(report.get("candidate_diff_sha256", ""))[:64],
        "note": "Consistency check of user-supplied files; NOT independent provider attestation.",
    }


def public_receipt_summary(report: dict, raw_provider: dict | None = None) -> dict:
    """Export only explicitly selected fields; exclude identifiers, secrets, raw text and paths."""
    checked = inspect_guardian_report(report, raw_provider)
    return {
        "project": "ExpireMem Guardian",
        "demo_scope": "Public pandas DataFrame.append API removal",
        "claimed_outcome": checked["claimed_outcome"],
        "structurally_consistent": checked["structurally_consistent"],
        "provider_raw_hash_check": checked["provider_raw_hash_check"],
        "evidence_status": checked["evidence_status"],
        "pandas_runtime": checked["pandas_runtime"],
        "model": checked["model"],
        "model_seconds": checked["model_seconds"],
        "total_tokens": checked["total_tokens"],
        "audit_stages": checked["audit_stages"],
        "source_url": "https://pandas.pydata.org/docs/whatsnew/v2.0.0.html",
        "limitations": [
            "Provided audit artifacts are not independent provider attestations.",
            "One observed case, not cross-library generalization evidence.",
            "No nonpublic research material included.",
            "Billing amount not independently verified.",
        ],
    }
