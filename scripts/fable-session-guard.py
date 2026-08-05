#!/usr/bin/env python3
"""fable-session-guard.py — SessionStart guard that closes the INTERACTIVE Fable bypass.

The non-bypassable model shim (`scripts/shims/claude`, the #328 fix) governs only daemon / `claude -p`
spawns. INTERACTIVE Claude Code sessions bypass it entirely and use the account default model — which
was Fable when the weekly allotment blew out on 2026-07-09. This guard is the only control that reaches
an interactive session:

  * If the session model is `claude-fable-5`, it prints the live weekly Fable balance loudly.
  * If the week is OVER CAP, or no live acceptance receipt is present, it emits a HARD WARNING plus the
    exact `/model` switch to drop off Fable.
  * On any non-Fable model, it is a clean no-op.

Wired as a SessionStart hook in settings.json (staged, human-armed — see
`docs/keys/fable-guard-settings-snippet.json`). Fail-open by construction: a SessionStart hook cannot
block a session, and this one is read-only. The model is resolved from the hook stdin payload when the
harness provides it, else from ANTHROPIC_MODEL / an explicit --model, so the guard is testable.

Exit codes (for the verify harness, NOT to block a live session):
  0 — non-Fable model, or Fable under cap with a live receipt (clean).
  2 — Fable model AND (over_cap OR no live acceptance receipt) — the hard-warn case.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
FABLE_SWITCH = "/model opus"  # the exact in-session switch off Fable


def _read_stdin_payload() -> dict:
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_model(payload: dict, explicit: str | None) -> str:
    if explicit:
        return explicit
    # SessionStart payloads may carry the model under a few shapes; be permissive.
    for key in ("model", "model_id"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            return v
    m = payload.get("model")
    if isinstance(m, dict):
        for key in ("id", "name"):
            v = m.get(key)
            if isinstance(v, str) and v:
                return v
    for env_key in ("ANTHROPIC_MODEL", "CLAUDE_MODEL", "LIMEN_SESSION_MODEL"):
        v = os.environ.get(env_key)
        if v:
            return v
    return ""


def _is_fable(model: str) -> bool:
    return "fable" in (model or "").lower()


def _load_balance() -> dict | None:
    path = os.environ.get("LIMEN_FABLE_BALANCE_PATH") or str(ROOT / "logs" / "fable-allotment.json")
    try:
        data = json.loads(Path(path).read_text())
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    now = dt.datetime.now(dt.timezone.utc)
    monday = (now - dt.timedelta(days=now.weekday())).date().isoformat()
    if str(data.get("week")) != monday:
        return None  # stale week
    return data


def _live_acceptance_present() -> bool:
    raw = os.environ.get("LIMEN_FABLE_ACCEPTANCE", "").strip()
    if not raw or raw == "1":
        return False
    try:
        receipt = json.loads(Path(os.path.expanduser(raw)).read_text())
    except Exception:
        return False
    now = dt.datetime.now(dt.timezone.utc)
    monday = (now - dt.timedelta(days=now.weekday())).date().isoformat()
    return receipt.get("schema") == "limen.fable_acceptance.v1" and receipt.get("week") == monday


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", help="override the resolved session model (test/inspection)")
    args = ap.parse_args(argv)

    payload = _read_stdin_payload()
    model = _resolve_model(payload, args.model)

    if not _is_fable(model):
        return 0  # clean no-op on any non-Fable model

    bal = _load_balance()
    accept = _live_acceptance_present()
    if bal is not None:
        pct = bal.get("spent_pct")
        over = bool(bal.get("over_cap"))
        print(
            f"[fable-session-guard] Interactive session model is Fable ({model}). "
            f"Weekly Fable spend: {pct}% (deliberate cap {bal.get('deliberate_cap')}%, "
            f"hard cap {bal.get('hard_cap')}%; over_cap={over}).",
            file=sys.stderr,
        )
    else:
        over = False
        print(
            f"[fable-session-guard] Interactive session model is Fable ({model}). "
            "No live weekly balance meter found (run scripts/fable-allotment.py balance).",
            file=sys.stderr,
        )

    if over or not accept:
        reason = "OVER the weekly cap" if over else "running without a live acceptance receipt"
        print(
            f"[fable-session-guard] HARD WARNING: Fable is {reason}. Fable is PLAN-ONLY and "
            f"~111x Opus cost. Switch off Fable now: {FABLE_SWITCH}  "
            "(see docs/fable-allotment.md).",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
