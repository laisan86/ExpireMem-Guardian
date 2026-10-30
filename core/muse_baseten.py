"""Fail-closed, explicitly authorized, SINGLE attempt to Baseten Muse Spark Open.

Public pandas fixture only. This module never runs requests on import and never
reads or changes the unrelated Meta Model API D2 ledger. Raw provider artifacts
and attempt locks belong only in the caller's PRIVATE directory.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Callable

MODEL = "meta-models/muse-spark-open-1026"  # Hackathon-specific ID from the Baseten email
BASE_URL = "https://inference.baseten.co/v1"
ACKNOWLEDGEMENT = "I AUTHORIZE ONE BASETEN MUSE PATCH PROPOSAL"
MAX_TOKENS = 8192  # Reasoning model: an overly small budget may return no final content.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _write_exclusive(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        f.flush()


class BasetenOneShotProposer:
    def __init__(self, *, private_dir: Path, api_key: str,
                 allow_paid: bool = False, acknowledgement: str = "",
                 transport: Callable | None = None):
        if not allow_paid or acknowledgement != ACKNOWLEDGEMENT:
            raise PermissionError("Real Baseten call disabled: explicit acknowledgement required")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("BASETEN_API_KEY missing")
        self.private_dir = Path(private_dir)
        self.key = api_key
        self.transport = transport
        self.receipt: dict | None = None

    def __call__(self, prompt: str) -> str:
        if not isinstance(prompt, str) or not (
            "Official URL: https://pandas.pydata.org/docs/whatsnew/v2.0.0.html" in prompt
            and "Original public fixture:" in prompt
            and "Actual stderr" in prompt
        ):
            raise ValueError("Refuse non-public, unverified or unexpected prompt")
        self.private_dir.mkdir(parents=True, exist_ok=True)
        gate = self.private_dir / "baseten_muse_attempt_lock.json"
        _write_exclusive(gate, {
            "status": "UNKNOWN_PENDING", "created_at_utc": _now(),
            "provider": "Baseten", "model": MODEL, "prompt_sha256": _hash(prompt),
            "note": "Exactly one request authorized. Lock never auto-clears, even on success/error."})

        # Exclusive lock is written BEFORE the network request. Deliberately never
        # remove it: a second request requires a separate, explicit review.
        request = {"model": MODEL,
                   "messages": [
                       {"role": "system", "content": "Output exactly one JSON object with the string key replacement_expr. No Markdown."},
                       {"role": "user", "content": prompt}],
                   "max_tokens": MAX_TOKENS}
        started = time.perf_counter()
        try:
            if self.transport is not None:
                # Only for deterministic tests. Always marked TEST_INJECTION.
                answer, usage = self.transport(prompt)
                raw = {"_test_injection": True, "model": MODEL,
                       "choices": [{"message": {"content": answer}, "finish_reason": "stop"}],
                       "usage": usage}
                transport_kind = "test_injection"
            else:
                from openai import OpenAI
                client = OpenAI(api_key=self.key, base_url=BASE_URL,
                                max_retries=0, timeout=120.0)
                response = client.chat.completions.create(**request)
                # Capture the complete SDK-visible server response FIRST.
                raw = response.model_dump(mode="json")
                transport_kind = "baseten_real"

            raw_path = self.private_dir / "baseten_muse_raw_response_private.json"
            _write_exclusive(raw_path, raw)
            raw_hash = _hash(json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str))
            choices = raw.get("choices") or []
            first = choices[0] if choices else {}
            message = first.get("message") or {}
            answer = message.get("content")
            receipt = {
                "provider": "Baseten", "model_requested": MODEL,
                "model_returned": raw.get("model"),
                "transport_kind": transport_kind,
                "response_id": raw.get("id"),
                "response_sha256": raw_hash,
                "raw_response_private_path": str(raw_path),
                "finish_reason": first.get("finish_reason"),
                "usage": raw.get("usage"),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "prompt_sha256": _hash(prompt),
                "response_saved_at_utc": _now(),
                "billing_verified": False,
            }
            self.receipt = receipt
            _write_exclusive(self.private_dir / "baseten_muse_receipt_private.json", receipt)

            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Model produced no final content; raw response is preserved")
            if first.get("finish_reason") not in ("stop", None):
                raise ValueError("Model response was truncated or not finished; raw response is preserved")
            return answer
        except Exception as exc:
            # Avoid including provider response bodies, headers or credentials in errors.
            self.receipt = self.receipt or {
                "transport_kind": "test_injection" if self.transport else "baseten_real",
                "error_type": type(exc).__name__, "response_sha256": None,
                "at_utc": _now(), "billing_verified": False}
            failure_path = self.private_dir / "baseten_attempt_failure_private.json"
            if not failure_path.exists():
                _write_exclusive(failure_path, {
                    "error_type": type(exc).__name__,
                    "http_status": getattr(exc, "status_code", None),
                    "request_id": getattr(exc, "request_id", None),
                    "at_utc": _now(),
                    "raw_response_saved": (self.private_dir / "baseten_muse_raw_response_private.json").exists(),
                    "billing_verified": False,
                    "note": "DO NOT retry; manual inspection first"})
            raise RuntimeError("Baseten attempt or response validation failed. "
                               "One-shot lock retained; inspect private receipt and raw JSON. "
                               "Never retry automatically.") from None
