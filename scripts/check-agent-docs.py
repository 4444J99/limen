#!/usr/bin/env python3
"""Drift predicate: bind the agent-instruction docs to the canonical task-state vocabulary.

The single source of truth for task states is ``VALID_STATUSES`` in
``mcp/src/limen_mcp/server.py``. The agent-instruction files (AGENTS.md / GEMINI.md /
CLAUDE.md) are hand-authored and have historically drifted from it — most recently
GEMINI.md documented a ``completed`` status that the MCP server never accepted (it uses
``done``). This script makes that drift a hard, machine-checked failure instead of a doc
bug nobody catches.

Checks (exit 0 iff all pass):

  A. AGENTS.md carries a canonical ``## Task States`` table whose enumerated states equal
     ``VALID_STATUSES`` exactly (no missing, no extra). This is the "machine-checkable
     example" — the docs' enumerated set is verified against code, not maintained by hand.

  B. No doc *presents* ``completed`` as a usable status. ``completed`` is never a valid limen
     status; ``done`` is. Only the backticked ``completed`` code token is considered, and only
     when it is offered as a value to use — a clarifying mention that forbids it ("there is no
     ``completed`` state", "do not use ``completed``") is allowed, as is prose like "completed
     work".

Run directly (``scripts/check-agent-docs.py``) or via ``scripts/verify-whole.sh``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp" / "src" / "limen_mcp" / "server.py"
DOCS = [ROOT / "AGENTS.md", ROOT / "GEMINI.md", ROOT / "CLAUDE.md"]


def canonical_statuses() -> set[str]:
    """Parse the ``VALID_STATUSES = {...}`` literal out of the MCP server."""
    text = SERVER.read_text(encoding="utf-8")
    match = re.search(r"VALID_STATUSES\s*=\s*\{([^}]*)\}", text)
    if not match:
        raise SystemExit(f"FAIL: could not find VALID_STATUSES in {SERVER.relative_to(ROOT)}")
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


def documented_states(agents_md: str) -> set[str]:
    """Extract the state tokens from the ``## Task States`` table in AGENTS.md.

    Looks at the section between ``## Task States`` and the next ``## `` heading, and
    collects the backticked token in the first column of each table row
    (``| `open` | ... |``).
    """
    section = re.search(r"^##\s+Task States\b(.*?)(?=^##\s)", agents_md, re.S | re.M)
    if not section:
        raise SystemExit("FAIL: AGENTS.md has no '## Task States' section to verify against code")
    rows = re.findall(r"^\|\s*`([a-z_]+)`\s*\|", section.group(1), re.M)
    return set(rows)


def main() -> int:
    errors: list[str] = []
    valid = canonical_statuses()

    agents_path = ROOT / "AGENTS.md"
    documented = documented_states(agents_path.read_text(encoding="utf-8"))
    missing = valid - documented
    extra = documented - valid
    if missing:
        errors.append(f"AGENTS.md '## Task States' is MISSING canonical states: {sorted(missing)}")
    if extra:
        errors.append(f"AGENTS.md '## Task States' lists NON-canonical states: {sorted(extra)}")

    # A negation cue within the ~30 chars before `completed` marks a clarifying mention
    # ("there is no `completed` state") rather than presenting it as a usable status.
    negation = re.compile(r"\bno\b|\bnot\b|n't|\bnever\b|\binstead\b|\bavoid\b", re.I)
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        for match in re.finditer(r"`completed`", text):
            if not negation.search(text[max(0, match.start() - 30):match.start()]):
                errors.append(
                    f"{doc.name} presents `completed` as a status — limen has no 'completed' "
                    f"state; use `done` (canonical set: {', '.join(sorted(valid))})"
                )
                break

    if errors:
        print("Agent-instruction doc drift detected:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"Agent-instruction docs match canonical task states ({', '.join(sorted(valid))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
