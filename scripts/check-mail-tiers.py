#!/usr/bin/env python3
"""MAIL-TIERS registry drift-predicate — hold institutio/governance/mail-tiers.yaml to the code.

The correspondence organ's send-tier decision is declared data (mail-tiers.yaml), the mail-domain
twin of check-gates.py / check-sensors.py / check-params.py. Exit 0 ⟺ the registry is well-formed
and its load-bearing safety invariants hold:

  A schema      — schema_version present; the no_reply / hold / safe tier blocks exist.
  B no_reply    — esp_domains / role_localparts / subject_patterns / header_signals are non-empty
                  string lists; every subject_pattern compiles as a regex (the sender reuses them).
  C hold-safety — the invariant that makes auto-send safe BY CONSTRUCTION: hold.tags must cover
                  {legal, money} and hold.verify_first must be true, so a legal / money / phishing
                  class can never fall through to the SAFE tier no matter how it is scored.
  D safe-clean  — every safe intent has id/when/template, and every template is COMPLETE and
                  bracket-free: no `[...]` placeholder (draft_writer's starters are never sendable),
                  and the only interpolation permitted is `{first_name}`.
  E uma-parity  — ADVISORY, only when core/protocols.py is reachable (LIMEN_UMA_ROOT or the default
                  UMA checkout): every protocol class tagged legal/money/security or verify_first is
                  covered by hold. Absent (e.g. CI) → a skip note, never a failure.

  python3 scripts/check-mail-tiers.py     # gate (CI): exit 1 on any drift
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "mail-tiers.yaml"
DANGEROUS_TAGS = {"legal", "money"}
ALLOWED_INTERPOLATIONS = {"{first_name}"}
INTERP_RX = re.compile(r"\{[^}]*\}")

_failures: list[str] = []
_notes: list[str] = []


def fail(check: str, message: str) -> None:
    _failures.append(f"[{check}] {message}")


def _str_list(block: dict, key: str, check: str) -> list[str]:
    """Return block[key] asserted to be a non-empty list of non-empty strings."""
    val = block.get(key)
    if not isinstance(val, list) or not val:
        fail(check, f"no_reply.{key} must be a non-empty list")
        return []
    out: list[str] = []
    for item in val:
        if not isinstance(item, str) or not item.strip():
            fail(check, f"no_reply.{key} entries must be non-empty strings (got {item!r})")
            continue
        out.append(item)
    return out


def _uma_protocols_path() -> Path | None:
    root = os.environ.get("LIMEN_UMA_ROOT") or str(Path.home() / "Workspace" / "universal-mail--automation")
    path = Path(root) / "core" / "protocols.py"
    return path if path.exists() else None


def _load_uma_protocols(path: Path):
    """Import UMA core/protocols.py in isolation (it is stdlib-only) and return its _PROTOCOLS."""
    spec = importlib.util.spec_from_file_location("_uma_protocols_probe", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "_PROTOCOLS", None)


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()

    if not REGISTRY.exists():
        print(f"check-mail-tiers: FAIL — registry missing: {REGISTRY}")
        return 1
    try:
        reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        print(f"check-mail-tiers: FAIL — cannot parse registry: {exc}")
        return 1
    if not isinstance(reg, dict):
        print("check-mail-tiers: FAIL — registry root must be a mapping")
        return 1

    # A — schema
    if "schema_version" not in reg:
        fail("A", "schema_version missing")
    no_reply = reg.get("no_reply")
    hold = reg.get("hold")
    safe = reg.get("safe")
    for name, block in (("no_reply", no_reply), ("hold", hold), ("safe", safe)):
        if not isinstance(block, dict):
            fail("A", f"tier block {name!r} must be a mapping")

    # B — no_reply well-formed
    if isinstance(no_reply, dict):
        _str_list(no_reply, "esp_domains", "B")
        _str_list(no_reply, "role_localparts", "B")
        for pat in _str_list(no_reply, "subject_patterns", "B"):
            try:
                re.compile(pat)
            except re.error as exc:
                fail("B", f"subject_pattern {pat!r} is not a valid regex: {exc}")
        _str_list(no_reply, "header_signals", "B")

    # C — hold covers the dangerous set by construction
    if isinstance(hold, dict):
        hold_tags = set(hold.get("tags") or [])
        missing = DANGEROUS_TAGS - hold_tags
        if missing:
            fail("C", f"hold.tags must cover {sorted(DANGEROUS_TAGS)} — missing {sorted(missing)}")
        if hold.get("verify_first") is not True:
            fail("C", "hold.verify_first must be true (phishing-prone classes are always held)")
        if not isinstance(hold.get("classes"), list):
            fail("C", "hold.classes must be a list")

    # D — safe templates are complete and bracket-free
    if isinstance(safe, dict):
        intents = safe.get("intents")
        if not isinstance(intents, list) or not intents:
            fail("D", "safe.intents must be a non-empty list")
        else:
            seen_ids: set[str] = set()
            for i, intent in enumerate(intents):
                if not isinstance(intent, dict):
                    fail("D", f"safe.intents[{i}] must be a mapping")
                    continue
                for req in ("id", "when", "template"):
                    if not intent.get(req):
                        fail("D", f"safe.intents[{i}] missing {req!r}")
                iid = intent.get("id")
                if iid in seen_ids:
                    fail("D", f"duplicate safe intent id {iid!r}")
                seen_ids.add(iid)
                tmpl = intent.get("template") or ""
                if "[" in tmpl or "]" in tmpl:
                    fail("D", f"safe intent {iid!r} template has a square-bracket placeholder — never auto-sendable")
                for token in INTERP_RX.findall(tmpl):
                    if token not in ALLOWED_INTERPOLATIONS:
                        fail("D", f"safe intent {iid!r} uses interpolation {token!r} (only {sorted(ALLOWED_INTERPOLATIONS)} allowed)")

    # E — UMA class parity (advisory; skipped when UMA is absent)
    uma_path = _uma_protocols_path()
    if uma_path is None:
        _notes.append("E: UMA core/protocols.py not present — class-parity cross-check skipped")
    else:
        try:
            protocols = _load_uma_protocols(uma_path)
        except Exception as exc:  # noqa: BLE001 — never hard-fail CI on a UMA import quirk
            protocols = None
            _notes.append(f"E: could not import UMA protocols.py ({exc}) — cross-check skipped")
        if protocols:
            hold_tags = set((hold or {}).get("tags") or [])
            hold_classes = set((hold or {}).get("classes") or [])
            for p in protocols:
                tags = set(p.get("tags") or [])
                dangerous = bool(tags & (DANGEROUS_TAGS | {"security"})) or p.get("verify_first")
                if dangerous and not (tags & hold_tags) and p.get("cls") not in hold_classes:
                    fail("E", f"protocol class {p.get('cls')!r} is dangerous (tags={sorted(tags)}) but not held")

    for note in _notes:
        print(f"check-mail-tiers: note — {note}")
    if _failures:
        print("check-mail-tiers: FAIL")
        for f in _failures:
            print(f"  {f}")
        return 1
    print("check-mail-tiers: OK — no_reply/hold/safe declared, hold covers legal+money+verify_first, safe templates bracket-free")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
