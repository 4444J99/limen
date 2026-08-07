#!/usr/bin/env python3
"""fable-session-guard.py — SessionStart guard that closes the INTERACTIVE Fable bypass.

The non-bypassable model shim (`scripts/shims/claude`, the #328 fix) governs only daemon / `claude -p`
spawns. INTERACTIVE Claude Code sessions bypass it entirely and use the account default model — which
was Fable when the weekly allotment blew out on 2026-07-09. This guard is the only control that reaches
an interactive session:

  * If the session model is `claude-fable-5`, it prints the live weekly Fable balance loudly.
  * If the week is OVER CAP, or no live acceptance receipt is present, OR THE METER CANNOT BE
    TRUSTED, it emits a HARD WARNING plus the exact `/model` switch to drop off Fable.
  * On any non-Fable model, it is a clean no-op.

2026-08-07 — a guard that cannot see must WARN, not pass. This previously read the meter itself,
one of three forked copies, all typed `dict | None`; an absent/stale/unreadable meter produced
`None`, the guard printed "no live weekly balance meter found", and then set `over = False` and
fell through to a clean exit. It named the problem in prose and ignored it in the verdict. The
meter read now lives once, in `model_selection.balance_verdict()`, and returns an explicit state;
every untrusted state reaches the hard warning.

Wired as a SessionStart hook in settings.json (staged, human-armed — see
`docs/keys/fable-guard-settings-snippet.json`). Fail-open by construction: a SessionStart hook cannot
block a session, and this one is read-only. The model is resolved from the hook stdin payload when the
harness provides it, else from ANTHROPIC_MODEL / an explicit --model, so the guard is testable.

Exit codes (for the verify harness, NOT to block a live session):
  0 — non-Fable model, or Fable under cap with a live receipt (clean).
  2 — Fable model AND (over_cap OR no live acceptance receipt OR an untrusted meter) — hard warn.
  3 — the session tier could not be ESTABLISHED (no model resolved, or a model matching no rung).
  4 — the session opens ABOVE the declared cadence ceiling (LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER).

Exit 4 exists because `"fable" in model` guarded ONE rung of a four-rung ladder: every tier
between the cadence floor and Fable was unguarded, so a saved Opus default (~15x sonnet) opened
every session while this guard reported a clean no-op. Guarding a literal string guards a value;
guarding an ORDINAL guards the policy. The Fable arm still evaluates first and unconditionally —
defence in depth, not a replacement.

Exit 3 is the SECOND instance of this file's own defect class, closed on the same day as the
first: `_resolve_model` used to return "" for an unresolvable model, `_is_fable("")` is False, and
the guard took the clean-no-op branch — exit 0 with zero bytes on stderr, byte-identical to a
session confirmed to be running on a cheap tier. The guard's most consequential input had a
failure mode indistinguishable from success.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
FABLE_SWITCH = "/model sonnet"  # the exact in-session switch off Fable (sonnet = the session-opening tier)


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


def _resolve_model(payload: dict, explicit: str | None) -> tuple[str, str]:
    """(model, source) — and an EMPTY model is a third state, not a cheap one.

    This used to return a bare ``str`` and fall through to ``""``. ``_is_fable("")`` is False, so
    an unresolvable session model took the "clean no-op" branch: exit 0, zero bytes on stderr —
    byte-identical, to every observer, to a session confirmed to be running on a cheap tier. The
    guard's single most consequential input had a failure mode that looked exactly like success.

    Returning the SOURCE alongside the value is what makes the difference observable: the caller
    can say which rung answered, or that none did.
    """
    if explicit:
        return explicit, "--model"
    # SessionStart payloads may carry the model under a few shapes; be permissive.
    for key in ("model", "model_id"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            return v, f"payload.{key}"
    m = payload.get("model")
    if isinstance(m, dict):
        for key in ("id", "name"):
            v = m.get(key)
            if isinstance(v, str) and v:
                return v, f"payload.model.{key}"
    for env_key in ("ANTHROPIC_MODEL", "CLAUDE_MODEL", "LIMEN_SESSION_MODEL"):
        v = os.environ.get(env_key)
        if v:
            return v, f"env:{env_key}"
    return "", ""


def _is_fable(model: str) -> bool:
    return "fable" in (model or "").lower()


def _model_selection():
    """Load the SHARED meter reader by file path from this script's own repo tree.

    Pinned to ``__file__``, deliberately NOT to ``LIMEN_ROOT``: a worktree-run verification must
    resolve the code it is verifying, never the live checkout's copy — and that exact divergence
    is what produced the 2026-08-07 incident. The split is: CODE by ``__file__``, RUNTIME STATE by
    ``LIMEN_ROOT``. ``model_selection`` is pure-stdlib by contract, so loading it this way pulls in
    no package ``__init__`` and needs no PYTHONPATH.

    Returns None if it cannot be loaded — which the caller treats as UNRESOLVABLE (warn), never as
    fine. A guard that cannot reach its own meter has learned something, and it is not "no problem".
    """
    path = Path(__file__).resolve().parents[1] / "cli" / "src" / "limen" / "model_selection.py"
    try:
        spec = importlib.util.spec_from_file_location("_limen_model_selection_guard", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 — an unloadable reader is a finding, not a crash
        return None


def _balance_verdict() -> dict:
    """The weekly meter's verdict, via the ONE shared reader (design decision D2).

    Three forked copies of this read used to exist — here, in ``model_selection``, and in
    ``vendor-cancel-advisor`` — each typed ``dict | None`` with None meaning both "no meter" and
    "a meter I decided not to trust", and every caller reading it as permissive. This function's
    only job now is to degrade honestly when the shared reader itself is unreachable.
    """
    mod = _model_selection()
    if mod is None:
        return {
            "state": "reader-unavailable",
            "trusted": False,
            "balance": None,
            "age_s": None,
            "provenance": "unknown",
            "detail": "could not load cli/src/limen/model_selection.py beside this script",
        }
    return mod.balance_verdict()


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
    ap.add_argument(
        "--ceiling",
        default=None,
        help="override the cadence opening ceiling (default LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER, "
        "itself defaulting to sonnet). Hard-capped at opus by the SAME accessor the env var uses — "
        "the cap belongs to the value, not to one entry point, so no flag can declare Fable an "
        "acceptable opening default.",
    )
    args = ap.parse_args(argv)

    payload = _read_stdin_payload()
    model, source = _resolve_model(payload, args.model)

    if not model:
        # THE THIRD STATE. Not "fine" and not a hard warning — an honest "I could not establish
        # this", which is information the previous silence destroyed. Deliberately a one-line
        # NOTICE rather than the HARD WARNING: "I could not see" and "I saw something bad" are
        # different findings and must not print the same way, or the loud case stops carrying
        # signal. Proportionate, but never silent.
        print(
            "[fable-session-guard] Session model UNRESOLVED — no --model, no model field in the "
            "SessionStart payload, and none of ANTHROPIC_MODEL / CLAUDE_MODEL / LIMEN_SESSION_MODEL "
            "is set. This guard cannot confirm the session tier, so treat it as UNKNOWN rather than "
            "cheap. (The harness's SessionStart model field is documented as not guaranteed present; "
            "export LIMEN_SESSION_MODEL to make it resolvable.)",
            file=sys.stderr,
        )
        return 3

    # THE CADENCE CEILING (F3). The Fable arm below evaluates first and unconditionally — defence
    # in depth — but `"fable" in model` guards ONE rung of a four-rung ladder. Every tier between
    # the cadence floor and Fable was unguarded, so a saved Opus default (~15x sonnet) opened
    # every session while this guard reported a clean no-op. Guarding a literal string guards a
    # value; guarding an ORDINAL guards the policy.
    if not _is_fable(model):
        mod = _model_selection()
        if mod is None:
            print(
                "[fable-session-guard] Cannot classify the session model — the shared tier ladder "
                "(cli/src/limen/model_selection.py) could not be loaded beside this script. Session "
                "tier UNVERIFIED.",
                file=sys.stderr,
            )
            return 3
        opening = mod.opening_verdict(model, args.ceiling)
        if opening["state"] == "unresolved":
            print(
                f"[fable-session-guard] Session model {model!r} (via {source}) matches no rung of the "
                f"tier ladder, so its cost cannot be placed against the cadence ceiling "
                f"({opening['ceiling']}). Session tier UNVERIFIED — treat as UNKNOWN, not cheap.",
                file=sys.stderr,
            )
            return 3
        if opening["state"] == "above-ceiling":
            print(
                f"[fable-session-guard] Session OPENS ABOVE THE CADENCE CEILING: {model!r} is the "
                f"{opening['rung']!r} rung (via {source}); the declared opening ceiling is "
                f"{opening['ceiling']!r}. CLAUDE.md's Session Phase Entry opens cheap and escalates "
                f"deliberately — if this escalation is deliberate, nothing is wrong; if it is a saved "
                f"default from an earlier session, {FABLE_SWITCH} restores the cadence. "
                "(Ceiling: LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER.)",
                file=sys.stderr,
            )
            return 4
        return 0  # at or below the cadence ceiling — clean

    verdict = _balance_verdict()
    accept = _live_acceptance_present()
    bal = verdict.get("balance")
    trusted = bool(verdict.get("trusted"))
    mod = _model_selection()
    over = bool(mod._balance_over_cap(bal)) if (mod is not None and isinstance(bal, dict)) else False

    if trusted and isinstance(bal, dict):
        print(
            f"[fable-session-guard] Interactive session model is Fable ({model}). "
            f"Weekly Fable spend: {bal.get('spent_pct')}% (deliberate cap {bal.get('deliberate_cap')}%, "
            f"hard cap {bal.get('hard_cap')}%; over_cap={over}).",
            file=sys.stderr,
        )
    else:
        # The whole point of the arc: an unresolvable meter SPEAKS its state and its reason. It
        # used to print "no meter found" and then fall through to over=False — a sentence that
        # named the problem and a verdict that ignored it.
        print(
            f"[fable-session-guard] Interactive session model is Fable ({model}). "
            f"Weekly meter UNTRUSTED (state={verdict.get('state')}, "
            f"deployment={verdict.get('provenance')}): {verdict.get('detail')}",
            file=sys.stderr,
        )

    # The declared hatch (LIMEN_FABLE_BALANCE_MAX_AGE_S <= 0) suppresses the WARNING, never the
    # report: the untrusted line above still prints, so an operator who armed the hatch still
    # sees what the guard could not establish.
    untrusted_counts = not trusted and bool(verdict.get("enforced", True))
    if over or not accept or untrusted_counts:
        if over:
            reason = "OVER the weekly cap"
        elif untrusted_counts:
            reason = f"running against an UNVERIFIABLE weekly meter ({verdict.get('state')})"
        else:
            reason = "running without a live acceptance receipt"
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
