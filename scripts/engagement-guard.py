#!/usr/bin/env python3
"""engagement-guard.py — the predicate for "is it safe to keep working for this client?"

Exit ``0`` ⟺ every condition that must hold before performing further billable work holds.
Non-zero prints the specific unmet conditions, each with the concrete next action.

WHY THIS EXISTS. Prose advice about contracts decays and is never read at the moment it
matters — which is the moment someone is being told to sign quickly. The charter's
§ Definition of Done requires the executable form: *an executable predicate, never
hand-maintained prose*. The standard this enforces is ``docs/engagement-intake-standard.md``;
this script is the half that runs.

WHAT IT HOLDS (offline, text-only — a gate that needs network is a gate that gets disabled):

  1. COUNTERSIGNED     — the instrument is signed by BOTH parties. One-sided signature is the
                         single most common failure: you are bound, they are not.
  2. NO-BLANK-FIELDS   — no compensation field was blank at the moment of signature.
  3. FIXED-COMPONENT   — compensation includes a fixed, dated, non-contingent amount. A pure
                         percentage of a counterparty's revenue is worth exactly that
                         counterparty's revenue, which is frequently zero.
  4. PAYMENT-DUE-DATE  — the fixed component names a date, not an event the client controls.
  5. UNPAID-CEILING    — work delivered without payment has not exceeded the configured
                         ceiling. This is the check that fires earliest and matters most.
  6. ASSET-CUSTODY     — you still hold the deliverable (repo, files, accounts) if you are
                         unpaid. Transfer is the LAST step, never a favour done early.
  7. PROMISES-ON-PAPER — no material promise lives only in chat. If it is not in the
                         instrument, it does not exist.
  8. CAN-PAY           — counterparty ability to pay has been verified, not assumed.
  9. COUNSEL-PARITY    — advisory. If they have counsel and you do not, you are negotiating
                         against a professional. Warn, do not fail.
 10. SCOPE-PRICED      — every category of work you have been assigned is priced in an
                         instrument. Scope creeping into an unpriced category while the
                         original scope is unpaid opens a second front on the first one's
                         terms, and makes walking away from either one costlier.

WHAT IT DOES NOT DO. It does not read contracts, judge enforceability, or give legal advice.
It reads a small hand-written YAML describing an engagement and holds it to conditions that
are checkable. Judgment stays with the human; this removes the excuse of not having noticed.

USAGE

    scripts/engagement-guard.py --config engagements/<name>.yaml
    scripts/engagement-guard.py --config engagements/<name>.yaml --json
    scripts/engagement-guard.py --all          # every engagement in engagements/

Severity: FAIL blocks (exit 1). WARN advises (exit 0 unless --strict).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    print("FATAL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    raise SystemExit(2) from None

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = REPO_ROOT / "engagements"

FAIL = "FAIL"
WARN = "WARN"
PASS = "PASS"


class Finding:
    """One check's verdict, with the action that clears it."""

    def __init__(self, check: str, severity: str, detail: str, action: str = "") -> None:
        self.check = check
        self.severity = severity
        self.detail = detail
        self.action = action

    def as_dict(self) -> dict[str, str]:
        return {"check": self.check, "severity": self.severity, "detail": self.detail, "action": self.action}


def _date(value: Any) -> dt.date | None:
    """Coerce a YAML scalar to a date. YAML parses bare dates already; strings need a nudge."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return dt.date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _truthy_amount(value: Any) -> bool:
    """A fixed amount counts only if it is a positive number. ``None``/0/"TBD" do not."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    return False


def evaluate(cfg: dict[str, Any], today: dt.date) -> list[Finding]:
    """Run every check against one engagement config. Pure — no I/O, so it is trivially testable."""
    out: list[Finding] = []
    inst = cfg.get("instrument") or {}
    comp = inst.get("compensation") or {}
    work = cfg.get("work") or {}
    asset = cfg.get("asset") or {}

    # 1. COUNTERSIGNED -----------------------------------------------------------------
    mine = _date(inst.get("signed_by_me"))
    theirs = _date(inst.get("signed_by_them"))
    if mine and not theirs:
        out.append(
            Finding(
                "COUNTERSIGNED",
                FAIL,
                f"You signed {inst.get('name', 'the instrument')} on {mine}; counterparty has NOT countersigned.",
                "Obtain the countersigned copy before further work. You are bound; they are not.",
            )
        )
    elif not mine and theirs:
        out.append(
            Finding(
                "COUNTERSIGNED",
                WARN,
                f"Counterparty signed on {theirs}; you have not. Nothing binds you yet.",
                "Do not sign until every FAIL below is cleared.",
            )
        )
    elif not mine and not theirs:
        out.append(
            Finding(
                "COUNTERSIGNED",
                FAIL,
                "No executed instrument at all.",
                "Do not perform billable work before a mutually signed agreement exists.",
            )
        )
    else:
        out.append(Finding("COUNTERSIGNED", PASS, f"Signed by both parties ({mine}, {theirs}).", ""))

    # 2. NO-BLANK-FIELDS ---------------------------------------------------------------
    if inst.get("blank_fields_at_signature"):
        out.append(
            Finding(
                "NO-BLANK-FIELDS",
                FAIL,
                "Compensation fields were blank when the instrument was signed.",
                "Never sign with blank money fields — the number gets set without you. Re-execute a complete copy.",
            )
        )
    else:
        out.append(Finding("NO-BLANK-FIELDS", PASS, "No blank fields recorded at signature.", ""))

    # 3. FIXED-COMPONENT ---------------------------------------------------------------
    fixed = comp.get("fixed_amount")
    if _truthy_amount(fixed):
        out.append(Finding("FIXED-COMPONENT", PASS, f"Fixed compensation: {fixed:,.2f}.", ""))
    else:
        contingent = comp.get("contingent")
        detail = "Compensation is entirely contingent." if contingent else "No compensation terms recorded."
        out.append(
            Finding(
                "FIXED-COMPONENT",
                FAIL,
                f"{detail} Contingent-only pay is worth the counterparty's revenue, which may be zero.",
                "Require a fixed, non-contingent amount — a deposit, a retainer, or a milestone fee.",
            )
        )

    # 4. PAYMENT-DUE-DATE --------------------------------------------------------------
    due = _date(comp.get("fixed_due"))
    if _truthy_amount(fixed) and not due:
        out.append(
            Finding(
                "PAYMENT-DUE-DATE",
                FAIL,
                "A fixed amount exists but no due date does.",
                "Money must be due on a DATE, not on an event the client controls.",
            )
        )
    elif due:
        overdue = (today - due).days
        if overdue > 0:
            out.append(
                Finding(
                    "PAYMENT-DUE-DATE",
                    FAIL,
                    f"Payment was due {due} — {overdue} days ago.",
                    "Stop new work and collect before continuing.",
                )
            )
        else:
            out.append(Finding("PAYMENT-DUE-DATE", PASS, f"Payment due {due}.", ""))

    # 5. UNPAID-CEILING ----------------------------------------------------------------
    received = cfg.get("payments_received") or 0
    ceiling_days = int(cfg.get("max_unpaid_days", 14))
    started = _date(work.get("started"))
    if not received and started:
        days = (today - started).days
        if days > ceiling_days:
            out.append(
                Finding(
                    "UNPAID-CEILING",
                    FAIL,
                    f"{days} days of unpaid work (ceiling {ceiling_days}); nothing received to date.",
                    "Stop. Every additional unpaid day worsens the position rather than improving it.",
                )
            )
        else:
            out.append(Finding("UNPAID-CEILING", PASS, f"{days} unpaid days, within ceiling {ceiling_days}.", ""))
    elif not received:
        out.append(
            Finding("UNPAID-CEILING", WARN, "No payment received; work start date unknown.", "Record work.started.")
        )
    else:
        out.append(Finding("UNPAID-CEILING", PASS, f"Payments received: {received:,.2f}.", ""))

    # 6. ASSET-CUSTODY -----------------------------------------------------------------
    custody = (asset.get("custody") or "").lower()
    requested = _date(asset.get("transfer_requested"))
    if custody and custody not in {"me", "mine", "self"}:
        if not received:
            out.append(
                Finding(
                    "ASSET-CUSTODY",
                    FAIL,
                    f"Deliverable '{asset.get('name', '?')}' is no longer in your custody and you are unpaid.",
                    "Leverage is gone. Recovery is now a collections problem, not a negotiation.",
                )
            )
        else:
            out.append(Finding("ASSET-CUSTODY", PASS, "Asset transferred, payment received.", ""))
    elif requested and not received:
        out.append(
            Finding(
                "ASSET-CUSTODY",
                WARN,
                f"Transfer of '{asset.get('name', '?')}' was requested {requested} while unpaid — not executed.",
                "Do not transfer until funds clear. It is one irreversible action.",
            )
        )
    else:
        out.append(Finding("ASSET-CUSTODY", PASS, "Deliverable remains in your custody.", ""))

    # 7. PROMISES-ON-PAPER -------------------------------------------------------------
    promises = cfg.get("promises_not_in_instrument") or []
    if promises:
        joined = "; ".join(f'"{p}"' for p in promises)
        out.append(
            Finding(
                "PROMISES-ON-PAPER",
                FAIL,
                f"{len(promises)} material promise(s) exist only in conversation: {joined}.",
                "Get them into the instrument or treat them as withdrawn — because they can be.",
            )
        )
    else:
        out.append(Finding("PROMISES-ON-PAPER", PASS, "No off-paper promises recorded.", ""))

    # 8. CAN-PAY -----------------------------------------------------------------------
    canpay = cfg.get("counterparty_can_pay") or {}
    if not canpay.get("verified"):
        ev = canpay.get("evidence") or "not assessed"
        out.append(
            Finding(
                "CAN-PAY",
                FAIL,
                f"Counterparty ability to pay is unverified ({ev}).",
                "Verify before extending credit-in-kind. Unpaid work IS an extension of credit.",
            )
        )
    else:
        out.append(Finding("CAN-PAY", PASS, "Ability to pay verified.", ""))

    # 9. COUNSEL-PARITY (advisory) -----------------------------------------------------
    counsel = cfg.get("counsel") or {}
    if counsel.get("them") and not counsel.get("me"):
        out.append(
            Finding(
                "COUNSEL-PARITY",
                WARN,
                "Counterparty has legal counsel; you do not.",
                "Consider counsel before signing. They are not negotiating unadvised.",
            )
        )
    else:
        out.append(Finding("COUNSEL-PARITY", PASS, "No counsel asymmetry recorded.", ""))

    # 10. SCOPE-PRICED -----------------------------------------------------------------
    # Scope creep is not the failure. Scope creep into a category the instrument does not
    # cover, at no rate, while the original scope is still unpaid — that is the failure,
    # and it compounds: each new front makes walking away from the first one costlier.
    unpriced = cfg.get("unpriced_scope") or []
    if unpriced:
        joined = "; ".join(f'"{s}"' for s in unpriced)
        out.append(
            Finding(
                "SCOPE-PRICED",
                FAIL,
                f"{len(unpriced)} work categor(ies) assigned with no rate in any instrument: {joined}.",
                "Price it or decline it. New scope is the moment to price it — never after delivery.",
            )
        )
    else:
        out.append(Finding("SCOPE-PRICED", PASS, "All assigned scope is priced in an instrument.", ""))

    return out


def report(name: str, findings: list[Finding], verbose: bool) -> tuple[int, int]:
    fails = [f for f in findings if f.severity == FAIL]
    warns = [f for f in findings if f.severity == WARN]
    status = "BLOCKED" if fails else ("PROCEED WITH CAUTION" if warns else "CLEAR")
    print(f"\n=== {name} — {status} ===")
    for f in findings:
        if f.severity == PASS and not verbose:
            continue
        mark = {FAIL: "✗", WARN: "!", PASS: "✓"}[f.severity]
        print(f"  {mark} {f.severity:4} {f.check}")
        print(f"        {f.detail}")
        if f.action:
            print(f"        → {f.action}")
    if not fails and not warns:
        print("  ✓ all checks pass")
    return len(fails), len(warns)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Is it safe to keep working for this client?")
    ap.add_argument("--config", type=Path, help="engagement YAML")
    ap.add_argument("--all", action="store_true", help=f"every *.yaml under {DEFAULT_DIR.name}/")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="warnings also fail")
    ap.add_argument("--verbose", "-v", action="store_true", help="show passing checks too")
    ap.add_argument("--today", help="override today's date (ISO) for testing")
    args = ap.parse_args(argv)

    today = _date(args.today) or dt.date.today()

    if args.all:
        configs = sorted(p for p in DEFAULT_DIR.glob("*.yaml"))
    elif args.config:
        configs = [args.config]
    else:
        ap.error("pass --config <file> or --all")

    if not configs:
        print(f"no engagement configs found under {DEFAULT_DIR}", file=sys.stderr)
        return 2

    total_fail = total_warn = 0
    payload = []
    for path in configs:
        if not path.exists():
            print(f"FATAL: no such config: {path}", file=sys.stderr)
            return 2
        cfg = yaml.safe_load(path.read_text()) or {}
        findings = evaluate(cfg, today)
        name = cfg.get("engagement", path.stem)
        if args.json:
            payload.append({"engagement": name, "findings": [f.as_dict() for f in findings]})
        else:
            f, w = report(name, findings, args.verbose)
            total_fail += f
            total_warn += w

    if args.json:
        fails = sum(1 for e in payload for f in e["findings"] if f["severity"] == FAIL)
        warns = sum(1 for e in payload for f in e["findings"] if f["severity"] == WARN)
        print(json.dumps({"engagements": payload, "fail": fails, "warn": warns}, indent=2))
        total_fail, total_warn = fails, warns
    else:
        print(f"\n{total_fail} FAIL · {total_warn} WARN")

    if total_fail:
        return 1
    if total_warn and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
