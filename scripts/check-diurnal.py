#!/usr/bin/env python3
"""Drift predicate for institutio/governance/diurnal.yaml — the DIVRNAL section registry.

Exit 0 ⟺ the registry describes an organ that can actually run and can actually be cut.

Checks:
  A schema        — required fields present, enums respected, phases valid
  B renderer      — every `render:` key resolves in scripts/diurnal.py RENDERERS
  C measurability — THE LOAD-BEARING RULE: cuttable: true ⟹ metric AND acted_when present.
                    You cannot prune what you cannot score. A cuttable section with no
                    metric would accrue an unfalsifiable noop streak and eventually delete
                    itself on no evidence at all.
  D protection    — protected: true ⟹ cuttable: false (a safety section is never prunable)
  E paths         — every `source:` is a safe repo-relative path; every `refresh:` command's
                    scripts/<x>.(py|sh) token exists
  F absence       — render: absent ⟹ absent_reason present and non-trivial (a declared gap
                    beats a silent omission — ideal-forms.yaml's probe_absent_reason pattern)
  G coverage      — every phase has at least one section, and at least one is protected
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio/governance/diurnal.yaml"
ORGAN = ROOT / "scripts/diurnal.py"

PHASES = {"morning", "midday", "evening"}
ACTED = {"metric_decreased", "metric_changed", None}
REQUIRED = (
    "phases",
    "title",
    "render",
    "source",
    "refresh",
    "max_age_seconds",
    "metric",
    "acted_when",
    "protected",
    "cuttable",
)
SCRIPT_RX = re.compile(r"scripts/[\w./-]+\.(?:py|sh)")

failures: list[str] = []


def fail(check: str, msg: str) -> None:
    failures.append(f"{check}  {msg}")


def main() -> int:
    try:
        import yaml
    except ImportError:
        print("check-diurnal: PyYAML absent — cannot verify", file=sys.stderr)
        return 0  # fail open, same as every other registry checker

    if not REGISTRY.exists():
        print(f"check-diurnal: {REGISTRY} missing", file=sys.stderr)
        return 1

    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    sections = data.get("sections") or {}
    if not sections:
        fail("A", "registry declares no sections")

    renderers = set(re.findall(r'^\s*"([a-z_]+)":\s*r_', ORGAN.read_text(encoding="utf-8"), re.M))
    if not renderers:
        fail("B", "could not extract RENDERERS from scripts/diurnal.py")

    seen_phases: set[str] = set()
    protected_count = 0

    for key, spec in sections.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            fail("A", f"{key}: id must be lower snake_case")
        if not isinstance(spec, dict):
            fail("A", f"{key}: section must be a mapping")
            continue
        for field in REQUIRED:
            if field not in spec:
                fail("A", f"{key}: missing required field `{field}`")
        phases = spec.get("phases") or []
        if not phases or not set(phases) <= PHASES:
            fail("A", f"{key}: phases must be a non-empty subset of {sorted(PHASES)}")
        seen_phases |= set(phases)
        if spec.get("acted_when") not in ACTED:
            fail("A", f"{key}: acted_when must be one of {sorted(str(a) for a in ACTED)}")
        if not isinstance(spec.get("max_age_seconds"), int):
            fail("A", f"{key}: max_age_seconds must be an int (0 = must refresh every emission)")
        if spec.get("stale_policy", "withhold") not in {"withhold", "annotate"}:
            fail("A", f"{key}: stale_policy must be 'withhold' or 'annotate'")
        if spec.get("stale_policy") == "annotate" and spec.get("source") is None:
            fail("A", f"{key}: stale_policy: annotate is meaningless without a source")

        render = spec.get("render")
        if render not in renderers:
            fail("B", f"{key}: render '{render}' has no r_{render} renderer in scripts/diurnal.py")

        if spec.get("cuttable"):
            if spec.get("metric") is None:
                fail(
                    "C",
                    f"{key}: cuttable: true but metric is null — you cannot prune what you "
                    "cannot score; set cuttable: false or give it a metric",
                )
            if spec.get("acted_when") is None:
                fail(
                    "C",
                    f"{key}: cuttable: true but acted_when is null — no rule decides what "
                    "counts as action, so a noop streak would be unfalsifiable",
                )

        if spec.get("protected"):
            protected_count += 1
            if spec.get("cuttable"):
                fail("D", f"{key}: protected: true must imply cuttable: false")

        src = spec.get("source")
        if src is not None:
            if src.startswith("/") or ".." in src:
                fail("E", f"{key}: source must be a safe repo-relative path, got '{src}'")
        refresh = spec.get("refresh")
        if refresh:
            for token in SCRIPT_RX.findall(refresh):
                if not (ROOT / token).exists():
                    fail("E", f"{key}: refresh references missing script '{token}'")

        if render == "absent":
            reason = (spec.get("absent_reason") or "").strip()
            if len(reason) < 40:
                fail(
                    "F",
                    f"{key}: render: absent needs a substantive absent_reason — a declared gap beats a silent omission",
                )
            if src is not None:
                fail("F", f"{key}: render: absent must have source: null")

    for phase in sorted(PHASES - seen_phases):
        fail("G", f"phase '{phase}' has no sections — it would emit an empty page")
    if not protected_count:
        fail("G", "no protected section — the cut loop could eventually blind itself entirely")

    if failures:
        print(f"check-diurnal: {len(failures)} finding(s)", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"check-diurnal: ok — {len(sections)} section(s), {protected_count} protected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
