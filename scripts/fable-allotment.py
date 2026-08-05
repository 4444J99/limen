#!/usr/bin/env python3
"""Validate and record Fable 5 allotment acceptances.

Fable is a reserved Claude tier for a small set of high-leverage jobs. This tool is the
written acceptance command required before a Fable run starts. It records only metadata:
category, percent of the weekly allotment, sources by path/URL, and verification commands.
Do not put raw private prompts, secrets, or personal data in the receipt.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
DEFAULT_RECEIPTS = ROOT / "logs" / "fable-acceptance"

PLAN: dict[str, dict[str, Any]] = {
    "substrate": {
        "cap_percent": 15,
        "purpose": "Claude/Fable operating substrate audit and patch plan",
    },
    "prompt-corpus": {
        "cap_percent": 10,
        "purpose": "redacted prompt-corpus and session-lifecycle compression",
    },
    "governance": {
        "cap_percent": 10,
        "purpose": "canon/governance synthesis with validator-backed policy",
    },
    "adversarial-review": {
        "cap_percent": 5,
        "purpose": "skeptical review of recent high-impact changes",
    },
    "reserve": {
        "cap_percent": 10,
        "purpose": "single bounded follow-up repair exposed by a first-pass run",
        "reserve": True,
    },
}

DELIBERATE_CAP = 40
HARD_CAP = 50
SENSITIVE_RE = re.compile(
    r"\b(secret|token|credential|password|raw transcript|private personal data)\b",
    re.IGNORECASE,
)


class PolicyError(ValueError):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _week_key(moment: dt.datetime) -> str:
    monday = (moment - dt.timedelta(days=moment.weekday())).date()
    return monday.isoformat()


def _slug(value: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-").lower()
    if not out:
        raise PolicyError("slug must contain at least one alphanumeric character")
    return out[:80]


def _load_receipts(receipts_dir: Path, week: str) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    if not receipts_dir.exists():
        return receipts
    for path in sorted(receipts_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if data.get("week") == week:
            receipts.append(data)
    return receipts


def _spent(receipts: list[dict[str, Any]]) -> tuple[float, float]:
    deliberate = 0.0
    total = 0.0
    for receipt in receipts:
        percent = float(receipt.get("percent", 0))
        total += percent
        if receipt.get("category") != "reserve":
            deliberate += percent
    return deliberate, total


def _validate_sources(sources: list[str], redacted_packets: list[str]) -> None:
    text = "\n".join(sources + redacted_packets)
    if SENSITIVE_RE.search(text):
        raise PolicyError("receipt text mentions sensitive raw material; use source-indexed redacted packets")
    if not sources and not redacted_packets:
        raise PolicyError("at least one --source or --redacted-packet is required")


def _validate_receipt(
    receipt: dict[str, Any],
    *,
    receipts_dir: Path | None = None,
    include_existing: bool = True,
) -> None:
    category = str(receipt.get("category", ""))
    if category not in PLAN:
        raise PolicyError(f"unknown category {category!r}; choose one of {', '.join(sorted(PLAN))}")

    try:
        percent = float(receipt.get("percent"))
    except (TypeError, ValueError):
        raise PolicyError("percent must be numeric") from None
    if percent <= 0:
        raise PolicyError("percent must be positive")
    cap = float(PLAN[category]["cap_percent"])
    if percent > cap:
        raise PolicyError(f"{category} request is {percent:g}%, above category cap {cap:g}%")

    if category == "reserve" and not receipt.get("reserve_unlocked"):
        raise PolicyError("reserve spend requires --reserve-unlock")

    verifications = receipt.get("verification") or []
    if not verifications:
        raise PolicyError("at least one --verification command is required")
    if any(not isinstance(v, str) or not v.strip() for v in verifications):
        raise PolicyError("verification commands must be non-empty strings")

    _validate_sources(
        [str(s) for s in (receipt.get("sources") or [])],
        [str(s) for s in (receipt.get("redacted_packets") or [])],
    )

    if include_existing and receipts_dir is not None:
        week = str(receipt.get("week"))
        existing = _load_receipts(receipts_dir, week)
        deliberate, total = _spent(existing)
        category_total = sum(float(r.get("percent", 0)) for r in existing if r.get("category") == category)
        if category_total + percent > cap:
            raise PolicyError(
                f"{category} weekly spend would be {category_total + percent:g}%, above category cap {cap:g}%"
            )
        if category == "reserve":
            total += percent
        else:
            deliberate += percent
            total += percent
        if deliberate > DELIBERATE_CAP:
            raise PolicyError(f"deliberate Fable spend would be {deliberate:g}%, above {DELIBERATE_CAP}%")
        if total > HARD_CAP:
            raise PolicyError(f"total Fable spend would be {total:g}%, above {HARD_CAP}%")


def _receipt_from_args(args: argparse.Namespace) -> dict[str, Any]:
    created = _now()
    slug = _slug(args.slug)
    receipt = {
        "schema": "limen.fable_acceptance.v1",
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "week": _week_key(created),
        "category": args.category,
        "percent": float(args.percent),
        "slug": slug,
        "why": args.why,
        "sources": args.source or [],
        "redacted_packets": args.redacted_packet or [],
        "verification": args.verification or [],
        "reserve_unlocked": bool(getattr(args, "reserve_unlock", False)),
        "acceptance_command": " ".join(sys.argv),
    }
    return receipt


def cmd_plan(_: argparse.Namespace) -> int:
    print(json.dumps({"plan": PLAN, "deliberate_cap": DELIBERATE_CAP, "hard_cap": HARD_CAP}, indent=2))
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    receipts_dir = Path(args.receipts_dir)
    receipt = _receipt_from_args(args)
    _validate_receipt(receipt, receipts_dir=receipts_dir, include_existing=not args.no_existing)

    receipts_dir.mkdir(parents=True, exist_ok=True)
    stamp = receipt["created_at"].replace(":", "").replace("-", "")
    out = Path(args.out) if args.out else receipts_dir / f"{stamp}-{receipt['slug']}.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "receipt": str(out)}, indent=2))
    print(f"export LIMEN_FABLE_ACCEPTANCE={out}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    receipt = json.loads(Path(args.receipt).read_text())
    _validate_receipt(receipt, receipts_dir=Path(args.receipts_dir), include_existing=False)
    print(json.dumps({"ok": True, "receipt": str(args.receipt)}, indent=2))
    return 0


# ── Live weekly Fable balance (the runtime backstop meter) ───────────────────────────────
# The receipt ledger above records INTENDED spend (percent metadata at accept-time). The gate
# also needs ACTUAL Fable tokens burned this ISO-week. organs/financial/token-usage.json is a
# ROLLING 30-day window and CANNOT give the weekly figure, so the numerator comes from Claude
# Code's own per-session transcripts (~/.claude/projects/**/*.jsonl). If Anthropic's weekly
# unified rate-limit headers were captured (logs/anthropic-ratelimit.json), read the % directly —
# that is the truest source. Fail-open: a dark meter writes over_cap=false (never blocks a run on
# a measurement hiccup; the acceptance receipt organ remains the authorization).

_FABLE_WEEKLY_BUDGET_TOKENS_DEFAULT = 1_000_000_000  # ≈ the observed weekly Fable allotment ceiling
_WEEKLY_WIN_S = 7 * 86400


def _finite_int(value: object, default: int) -> int:
    try:
        parsed = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _transcripts_dir() -> Path:
    raw = os.environ.get("LIMEN_CLAUDE_TRANSCRIPTS_DIR")
    return Path(raw) if raw else (Path.home() / ".claude" / "projects")


def _iso_ts(value: str) -> float | None:
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _fable_ratelimit_pct() -> float | None:
    """If the fleet captured Anthropic's weekly unified rate-limit headers, read the Fable weekly
    used-percent directly. Truest source, zero measurement. Returns None if absent/malformed."""
    p = ROOT / "logs" / "anthropic-ratelimit.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except Exception:
        return None
    for key in ("fable_weekly_used_percent", "unified_weekly_used_percent"):
        v = d.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    wk = d.get("weekly")
    if isinstance(wk, dict):
        v = wk.get("fable_used_percent")
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _fable_weekly_tokens() -> int:
    """Sum Fable (claude-fable-5) billable tokens from Claude Code transcripts over the current
    ISO-week window. Bounded by file mtime so the scan stays cheap. Fail-open to 0."""
    import glob

    root = _transcripts_dir()
    if not root.exists():
        return 0
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    total = 0
    try:
        for f in glob.glob(str(root / "**" / "*.jsonl"), recursive=True):
            try:
                if now - os.path.getmtime(f) > _WEEKLY_WIN_S:
                    continue
            except OSError:
                continue
            with open(f, errors="ignore") as fh:
                for line in fh:
                    if "fable" not in line or '"usage"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    msg = o.get("message") or {}
                    model = str(msg.get("model") or o.get("model") or "")
                    if "fable" not in model.lower():
                        continue
                    ts = _iso_ts(o.get("timestamp", "")) if o.get("timestamp") else None
                    if ts is not None and now - ts > _WEEKLY_WIN_S:
                        continue
                    u = msg.get("usage") or o.get("usage")
                    if not isinstance(u, dict):
                        continue
                    total += (
                        int(u.get("input_tokens", 0) or 0)
                        + int(u.get("output_tokens", 0) or 0)
                        + int(u.get("cache_creation_input_tokens", 0) or 0)
                    )
    except Exception:
        return total
    return total


def compute_balance() -> dict[str, Any]:
    """The live weekly Fable balance: prefer a captured ratelimit % header, else token-sum vs a
    derived weekly budget. Timestamps derive from data (week key), never wall-clock in the body."""
    week = _week_key(_now())
    pct = _fable_ratelimit_pct()
    spent_tokens = _fable_weekly_tokens()
    source = "ratelimit-header"
    if pct is None:
        budget = _finite_int(
            os.environ.get("LIMEN_FABLE_WEEKLY_TOKENS"),
            _FABLE_WEEKLY_BUDGET_TOKENS_DEFAULT,
        )
        pct = round(100.0 * spent_tokens / budget, 2) if budget > 0 else 0.0
        source = "transcript-token-sum"
    return {
        "week": week,
        "spent_tokens": spent_tokens,
        "spent_pct": float(pct),
        "deliberate_cap": DELIBERATE_CAP,
        "hard_cap": HARD_CAP,
        "over_cap": float(pct) >= HARD_CAP,
        "source": source,
    }


def cmd_balance(args: argparse.Namespace) -> int:
    balance = compute_balance()
    out = Path(args.out) if args.out else ROOT / "logs" / "fable-allotment.json"
    if not args.no_write:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(balance, indent=2, sort_keys=True) + "\n")
    print(json.dumps(balance, indent=2, sort_keys=True))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    receipts_dir = Path(args.receipts_dir)
    week = args.week or _week_key(_now())
    receipts = _load_receipts(receipts_dir, week)
    deliberate, total = _spent(receipts)
    category_spend: dict[str, float] = {key: 0.0 for key in PLAN}
    errors: list[str] = []
    for receipt in receipts:
        try:
            _validate_receipt(receipt, include_existing=False)
        except PolicyError as exc:
            errors.append(f"{receipt.get('slug', '<unknown>')}: {exc}")
        category = str(receipt.get("category", ""))
        if category in category_spend:
            category_spend[category] += float(receipt.get("percent", 0))
    for category, spent in sorted(category_spend.items()):
        cap = float(PLAN[category]["cap_percent"])
        if spent > cap:
            errors.append(f"{category} spend {spent:g}% exceeds category cap {cap:g}%")
    if deliberate > DELIBERATE_CAP:
        errors.append(f"deliberate spend {deliberate:g}% exceeds {DELIBERATE_CAP}%")
    if total > HARD_CAP:
        errors.append(f"total spend {total:g}% exceeds {HARD_CAP}%")
    report = {
        "ok": not errors,
        "week": week,
        "receipt_count": len(receipts),
        "deliberate_percent": deliberate,
        "total_percent": total,
        "category_percent": category_spend,
        "errors": errors,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("plan").set_defaults(func=cmd_plan)

    accept = sub.add_parser("accept")
    accept.add_argument("--category", required=True, choices=sorted(PLAN))
    accept.add_argument("--percent", required=True, type=float)
    accept.add_argument("--slug", required=True)
    accept.add_argument("--why", required=True)
    accept.add_argument("--source", action="append", default=[])
    accept.add_argument("--redacted-packet", action="append", default=[])
    accept.add_argument("--verification", action="append", default=[])
    accept.add_argument("--reserve-unlock", action="store_true")
    accept.add_argument("--receipts-dir", default=str(DEFAULT_RECEIPTS))
    accept.add_argument("--out")
    accept.add_argument("--no-existing", action="store_true")
    accept.set_defaults(func=cmd_accept)

    validate = sub.add_parser("validate")
    validate.add_argument("receipt")
    validate.add_argument("--receipts-dir", default=str(DEFAULT_RECEIPTS))
    validate.set_defaults(func=cmd_validate)

    audit = sub.add_parser("audit")
    audit.add_argument("--receipts-dir", default=str(DEFAULT_RECEIPTS))
    audit.add_argument("--week")
    audit.set_defaults(func=cmd_audit)

    balance = sub.add_parser("balance")
    balance.add_argument("--out")
    balance.add_argument("--no-write", action="store_true")
    balance.set_defaults(func=cmd_balance)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PolicyError as exc:
        print(f"fable-allotment: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
