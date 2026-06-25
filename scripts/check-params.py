#!/usr/bin/env python3
"""No-hardcode gate — the VIGILIA spine's '100x' enforcement (build order #3).

Mandate (the parameter panel): every ``LIMEN_*`` knob the body uses should be a
declared parameter in ``institutio/governance/parameters.yaml``. We are not there
yet — the 2026-06-25 excavation found ~250 ``LIMEN_*`` vars scattered across the
codebase — so this gate **ratchets** instead of red-walling: it fails the build
only when a *new* undeclared ``LIMEN_*`` var appears that isn't in the committed
baseline. Existing vars fold into the panel incrementally (each fold prunes the
baseline); meanwhile no new hardcodes slip in. Exactly the nomenclator name-gate
pattern, one domain over.

It also fails on a broken panel: invalid YAML, a duplicate key, or a declared
param missing its ``default`` / ``env`` / ``owner``.

  python3 scripts/check-params.py            # gate (CI): exit 1 on violation
  python3 scripts/check-params.py --update   # rewrite the baseline to current
                                             #   (run after folding vars into the panel)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT / "institutio" / "governance" / "parameters.yaml"
BASELINE = ROOT / "institutio" / "governance" / "undeclared-params-baseline.txt"
SCAN_DIRS = ("cli/src", "scripts", "web/api", "mcp")
SCAN_SUFFIXES = (".py", ".sh", ".mjs", ".js", ".ts", ".yaml", ".yml", ".json")
TOKEN = re.compile(r"LIMEN_[A-Z0-9_]+")

# Env names the body legitimately uses that we do NOT own as LIMEN_ params
# (external mechanisms / third-party levers). The gate never chases these.
EXTERNAL_ALLOW = {
    "DISABLE_AUTOUPDATER",  # the autoupdater mechanism, governed by the INTEGRITY organ
}


def normalize(token: str) -> str:
    """Deterministic token normalization: drop trailing underscores (f-string prefixes)."""
    return token.rstrip("_")


def referenced_tokens(root: Path = ROOT) -> set[str]:
    found: set[str] = set()
    for d in SCAN_DIRS:
        base = root / d
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in SCAN_SUFFIXES or not path.is_file():
                continue
            try:
                text = path.read_text(errors="ignore")
            except Exception:
                continue
            for raw in TOKEN.findall(text):
                tok = normalize(raw)
                if tok and tok != "LIMEN":
                    found.add(tok)
    return found


def load_panel_text() -> str:
    return PANEL.read_text()


def declared_envs(panel: dict) -> set[str]:
    out: set[str] = set()
    for key, spec in (panel.get("parameters") or {}).items():
        out.add(key)
        if isinstance(spec, dict) and spec.get("env"):
            out.add(str(spec["env"]))
    return out


def panel_integrity_errors(text: str) -> list[str]:
    """YAML validity + duplicate keys + each param has default/env/owner."""
    errors: list[str] = []
    try:
        data = yaml.safe_load(text) or {}
    except Exception as exc:
        return [f"parameters.yaml is not valid YAML: {str(exc)[:160]}"]
    params = data.get("parameters")
    if not isinstance(params, dict):
        return ["parameters.yaml has no 'parameters:' mapping"]
    # duplicate top-level param keys (safe_load silently drops dups; detect textually)
    seen: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"^  ([A-Z][A-Z0-9_]+):\s*$", line)
        if m:
            seen[m.group(1)] = seen.get(m.group(1), 0) + 1
    for key, n in seen.items():
        if n > 1:
            errors.append(f"duplicate param key: {key} (declared {n}x)")
    for key, spec in params.items():
        if not isinstance(spec, dict):
            errors.append(f"param {key}: not a mapping")
            continue
        for field in ("default", "env", "owner"):
            if field not in spec:
                errors.append(f"param {key}: missing '{field}'")
    return errors


def read_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        ln.strip()
        for ln in BASELINE.read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    }


def write_baseline(undeclared: set[str]) -> None:
    header = (
        "# undeclared-params-baseline — the LIMEN_* vars referenced in code but not yet\n"
        "# declared in parameters.yaml. The no-hardcode gate fails on any NEW entry.\n"
        "# Fold vars into the panel, then run: python3 scripts/check-params.py --update\n"
    )
    body = "\n".join(sorted(undeclared))
    BASELINE.write_text(header + body + "\n")


def compute_undeclared(referenced: set[str], declared: set[str]) -> set[str]:
    return {t for t in referenced if t not in declared and t not in EXTERNAL_ALLOW}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = load_panel_text()

    integrity = panel_integrity_errors(text)
    panel = yaml.safe_load(text) or {}
    declared = declared_envs(panel)
    referenced = referenced_tokens()
    undeclared = compute_undeclared(referenced, declared)

    if "--update" in argv:
        write_baseline(undeclared)
        print(f"baseline updated: {len(undeclared)} undeclared LIMEN_* vars recorded")
        return 0

    baseline = read_baseline()
    new = sorted(undeclared - baseline)
    stale = sorted(baseline - undeclared)

    if integrity:
        print("PANEL INTEGRITY FAILURES:")
        for e in integrity:
            print(f"  ✗ {e}")

    if new:
        print(f"\nNO-HARDCODE GATE: {len(new)} new undeclared LIMEN_* var(s) — declare in")
        print(f"  {PANEL.relative_to(ROOT)} (or prune via --update if intentional):")
        for t in new:
            print(f"  ✗ {t}")

    if stale:
        print(f"\nnote: {len(stale)} baseline var(s) now declared/removed — run --update to prune.")

    if integrity or new:
        return 1
    print(
        f"check-params: OK — {len(declared)} declared, "
        f"{len(undeclared)} undeclared (baseline {len(baseline)}), no new hardcodes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
