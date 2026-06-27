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

  C. Status assignments and transition examples mention only canonical statuses.

  D. The precedence ladder in AGENTS.md matches the portal copy in
     docs/agent-instruction-standard.md.

  E. The valid agent list in AGENTS.md has matching agent-specific notes.

  F. Concrete script/path references in the instruction docs still exist.

  G. The AGENTS.md quick reference does not skip the canonical in_progress state.

  H. Required instruction sections exist, and Claude's charter stays role-based rather than
     person-specific.

  I. Generated instruction templates defer to AGENTS.md and do not publish divergent statuses.

  J. Deployment operations stay in docs/deployment.md, not in AGENTS.md.

Run directly (``scripts/check-agent-docs.py``) or via ``scripts/verify-whole.sh``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp" / "src" / "limen_mcp" / "server.py"
DOCS = [ROOT / "AGENTS.md", ROOT / "GEMINI.md", ROOT / "CLAUDE.md"]
STANDARD = ROOT / "docs" / "agent-instruction-standard.md"
REFERENCE_DOCS = DOCS + [ROOT / "CONTRIBUTING.md", STANDARD, ROOT / "docs" / "deployment.md"]
TEMPLATE_DOCS = [
    ROOT / "domus-genoma" / "dot_config" / "ai-context" / "AGENTS.md.tmpl",
    ROOT / "domus-genoma" / "dot_local" / "share" / "codex" / "AGENTS.md.tmpl",
    ROOT / "domus-genoma" / "dot_local" / "share" / "private_gemini" / "GEMINI.md.tmpl",
    ROOT / "domus-genoma" / "private_dot_claude" / "CLAUDE.md.tmpl",
    ROOT / "domus-genoma" / "dot_config" / "ai-instructions" / "AGENTS.md.template",
    ROOT / "domus-genoma" / "dot_config" / "ai-instructions" / "copilot-instructions.md.tmpl",
    ROOT / "domus-genoma" / "dot_config" / "ai-instructions" / "cursor-rules" / "core.mdc.tmpl",
]
REQUIRED_SECTIONS = {
    "AGENTS.md": [
        "Operating Modes",
        "Startup Checklist (fast path)",
        "Precedence",
        "Task States",
        "Where to Find Tasks",
        "Session Start Ritual",
        "Session End Ritual",
        "Safety & Evidence",
        "Quick Reference",
    ],
    "CLAUDE.md": [
        "Instruction File Maintenance",
        "Architecture & Orientation",
        "Closeout Definition",
        "Definition of Done",
        "Credentials Are Organ-Owned (Never Recited in Chat)",
        "Standing Autonomy & Compliant Gate Reroute",
        "Merge & Branch Protocol",
    ],
    "GEMINI.md": [
        "Conductor Swarm MCP Integration",
        "Execution Protocols",
    ],
}


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


def section(text: str, heading: str) -> str:
    """Return a second-level markdown section by heading."""
    match = re.search(rf"^##\s+{re.escape(heading)}\b(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    if not match:
        raise ValueError(f"missing section: {heading}")
    return match.group(1)


def precedence_items(text: str) -> list[str]:
    """Extract normalized numbered-list items from the Precedence section."""
    return [
        re.sub(r"\s+", " ", item).strip()
        for item in re.findall(r"^\d+\.\s+(.+)$", section(text, "Precedence"), re.M)
    ]


def has_heading(text: str, heading: str) -> bool:
    """Return whether a second-level markdown heading exists exactly."""
    return re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.M) is not None


def expected_agents(agents_md: str) -> set[str]:
    """Parse the expected LIMEN_AGENT values documented in AGENTS.md."""
    match = re.search(r"Expected values:\s*([a-z |]+)", agents_md)
    if not match:
        raise SystemExit("FAIL: AGENTS.md does not document expected LIMEN_AGENT values")
    return {part.strip() for part in match.group(1).split("|") if part.strip()}


def documented_agent_notes(agents_md: str) -> set[str]:
    """Parse the ### headings under Agent-Specific Notes."""
    notes = section(agents_md, "Agent-Specific Notes")
    return {heading.lower().replace(" ", "") for heading in re.findall(r"^###\s+(.+)$", notes, re.M)}


def referenced_paths(text: str) -> set[str]:
    """Find concrete repo-relative paths mentioned in code spans or markdown links."""
    paths: set[str] = set()
    for match in re.finditer(r"(?:`|\()((?:docs|scripts|mcp|web|cli|spec)/[A-Za-z0-9_.\-/]+)(?:`|\))", text):
        path = match.group(1).rstrip(".,)")
        if "*" in path or "<" in path:
            continue
        paths.add(path)
    return paths


def presented_status_tokens(text: str) -> set[str]:
    """Find status values presented in examples or transition wording."""
    tokens: set[str] = set()
    patterns = [
        r"\bstatus:\s*([a-z_]+)\b",
        r"\bstatus\s*==\s*[\"`]([a-z_]+)[\"`]",
        r"\bstatus\s+(?:is|to)\s+`([a-z_]+)`",
        r"\bto\s+`([a-z_]+)`\s+status",
        r"`([a-z_]+)`\s*→\s*`[a-z_]+`",
        r"`[a-z_]+`\s*→\s*`([a-z_]+)`",
    ]
    for pattern in patterns:
        tokens.update(re.findall(pattern, text))
    return tokens


def main() -> int:
    errors: list[str] = []
    valid = canonical_statuses()

    agents_path = ROOT / "AGENTS.md"
    agents_text = agents_path.read_text(encoding="utf-8")
    documented = documented_states(agents_text)
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
        for heading in REQUIRED_SECTIONS.get(doc.name, []):
            if not has_heading(text, heading):
                errors.append(f"{doc.name} is missing required section: {heading}")
        for match in re.finditer(r"`completed`", text):
            if not negation.search(text[max(0, match.start() - 30):match.start()]):
                errors.append(
                    f"{doc.name} presents `completed` as a status — limen has no 'completed' "
                    f"state; use `done` (canonical set: {', '.join(sorted(valid))})"
                )
                break
        invalid_presented = presented_status_tokens(text) - valid
        if invalid_presented:
            errors.append(f"{doc.name} presents non-canonical status values: {sorted(invalid_presented)}")

    claude_text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    if "Anthony" in claude_text:
        errors.append("CLAUDE.md should use role-based wording, not the operator's personal name")
    if re.search(r"\broute around\b", claude_text, re.I):
        errors.append("CLAUDE.md should describe compliant reroutes, not 'route around' safety gates")

    standard_text = STANDARD.read_text(encoding="utf-8")
    try:
        if precedence_items(agents_text) != precedence_items(standard_text):
            errors.append("AGENTS.md and docs/agent-instruction-standard.md have different Precedence ladders")
    except ValueError as exc:
        errors.append(str(exc))

    missing_notes = expected_agents(agents_text) - documented_agent_notes(agents_text)
    if missing_notes:
        errors.append(f"AGENTS.md is missing Agent-Specific Notes for: {sorted(missing_notes)}")

    quick_ref = section(agents_text, "Quick Reference")
    if re.search(r"Report done\s*\|[^\n]*dispatched[^\n]*done", quick_ref):
        errors.append("AGENTS.md Quick Reference skips in_progress when reporting done")
    if "## SaaS Deployment" in agents_text or "railway login" in agents_text or "vercel --prod" in agents_text:
        errors.append("AGENTS.md contains deployment operations; keep them in docs/deployment.md")

    for doc in REFERENCE_DOCS:
        for path in sorted(referenced_paths(doc.read_text(encoding="utf-8"))):
            if not (ROOT / path).exists():
                errors.append(f"{doc.relative_to(ROOT)} references missing path: {path}")

    for template in TEMPLATE_DOCS:
        text = template.read_text(encoding="utf-8")
        if "AGENTS.md" not in text:
            errors.append(f"{template.relative_to(ROOT)} does not defer to a project/home AGENTS.md")
        invalid_presented = presented_status_tokens(text) - valid
        if invalid_presented:
            errors.append(
                f"{template.relative_to(ROOT)} presents non-canonical status values: {sorted(invalid_presented)}"
            )

    if errors:
        print("Agent-instruction doc drift detected:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"Agent-instruction docs match canonical task states ({', '.join(sorted(valid))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
