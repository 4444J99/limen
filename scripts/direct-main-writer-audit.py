#!/usr/bin/env python3
"""Fail closed when a production Git/default-branch write seam is unclassified.

The remote no-bypass pull-request rule is the ultimate enforcement edge. This
audit is the earlier repository predicate: every executable-looking git push,
GitHub Contents PUT, and literal main-ref sink must have an exact reviewed
count and disposition in the governance registry.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "direct-main-writers.yaml"
KINDS = ("git_push", "push_literal", "contents_put", "default_ref_literal")
SOURCE_GLOBS = (
    ".github/workflows/*.yml",
    "scripts/*.sh",
    "scripts/*.py",
    "cli/src/**/*.py",
    "mcp/src/**/*.py",
    "web/api/**/*.py",
    "web/worker/src/**/*.js",
)


def production_sources() -> list[Path]:
    paths: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        paths.update(ROOT.glob(pattern))
    return sorted(
        path
        for path in paths
        if "/tests/" not in path.as_posix() and "/templates/" not in path.as_posix()
        and path != Path(__file__).resolve()
    )


def counts(path: Path) -> dict[str, int]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    git_push = sum(
        1
        for line in lines
        if not line.lstrip().startswith("#")
        and re.search(r"\b(?:git|_bounded_git)\b.{0,180}\bpush\b", line)
    )
    git_push += len(
        re.findall(
            r"\b(?:git|_bounded_git)\b[^\n]*\\\n\s*push\b",
            source,
        )
    )
    push_literal = len(
        re.findall(
            r"""(?:\[\s*["']push["']|
                    \[\s*["']git["']\s*,\s*["']push["']|
                    push_args\s*=\s*\[\s*["']push["'])""",
            source,
            re.X,
        )
    )
    direct_contents_put = len(
        re.findall(
            r"""(?:github_request|githubRequest)\s*\([^\n]{0,80}["']PUT["']""",
            source,
        )
    )
    gh_contents_put = len(
        re.findall(
            r"""(?:["']PUT["'].{0,800}/contents/|/contents/.{0,800}["']PUT["'])""",
            source,
            re.S,
        )
    )
    return {
        "git_push": git_push,
        "push_literal": push_literal,
        "contents_put": direct_contents_put + gh_contents_put,
        "default_ref_literal": len(re.findall(r"(?:HEAD:main|refs/heads/main)", source)),
    }


def compact(values: dict[str, int]) -> dict[str, int]:
    return {kind: int(values.get(kind, 0)) for kind in KINDS if int(values.get(kind, 0))}


def main() -> int:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    surfaces = data.get("surfaces") or {}
    failures: list[str] = []

    if data.get("protected_repository") != "organvm/limen" or data.get("protected_branch") != "main":
        failures.append("registry must protect organvm/limen main")
    remote = data.get("remote_enforcement") or {}
    if remote.get("required_rules") != ["pull_request", "merge_queue"] or remote.get("bypass_actors") != []:
        failures.append("remote enforcement must require pull_request + merge_queue with no bypass actors")

    discovered: dict[str, dict[str, int]] = {}
    for path in production_sources():
        relative = path.relative_to(ROOT).as_posix()
        found = compact(counts(path))
        if found:
            discovered[relative] = found

    for relative, found in discovered.items():
        entry = surfaces.get(relative)
        if not isinstance(entry, dict):
            failures.append(f"unclassified write seam: {relative} {found}")
            continue
        expected = compact(entry.get("expected") or {})
        if found != expected:
            failures.append(f"{relative}: discovered {found}, registry expects {expected}")
        if not entry.get("disposition"):
            failures.append(f"{relative}: missing disposition")

    for relative, entry in surfaces.items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"registered surface is missing: {relative}")
            continue
        expected = compact((entry or {}).get("expected") or {})
        found = discovered.get(relative, {})
        if found != expected:
            failures.append(f"{relative}: registry expects {expected}, discovered {found}")
        if not (entry or {}).get("disposition"):
            failures.append(f"{relative}: missing disposition")

    if failures:
        print("direct-main-writer-audit: FAIL")
        for failure in sorted(set(failures)):
            print(f"  - {failure}")
        return 1
    print(
        "direct-main-writer-audit: PASS — "
        f"{len(surfaces)} classified surfaces; no unclassified production write seam"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
