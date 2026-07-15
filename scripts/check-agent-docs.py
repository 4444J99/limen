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

  I. Generated instruction templates, when present, defer to AGENTS.md and do not publish
     divergent statuses.

  J. Deployment operations stay in docs/deployment.md, not in AGENTS.md.

  K. The 2026-07-09 insights standing corrections stay encoded: the closeout terminal
     statement, the BLOCKED-once protocol, and the registry-owns-the-answer rule are present
     in their owning CLAUDE.md sections and mirrored into the closeout skill.

  L. The prompt corpus remains the concurrent control plane: ask/correction atoms are the unit,
     completion is evidence-backed, and the human is not asked to restate settled intent.

Run directly (``scripts/check-agent-docs.py``) or via ``scripts/verify-whole.sh``.
"""

from __future__ import annotations

import re
import subprocess
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
        "Correction Propagation",
        "Engineering Ownership",
        "Prompt Corpus as the Control Plane",
        "Full Lifecycle Closure",
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
        "Engage the Real Problem First",
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


def canonical_agents() -> set[str]:
    """Parse the ``VALID_AGENTS = {...}`` literal out of the MCP server."""
    text = SERVER.read_text(encoding="utf-8")
    match = re.search(r"VALID_AGENTS\s*=\s*\{([^}]*)\}", text)
    if not match:
        raise SystemExit(f"FAIL: could not find VALID_AGENTS in {SERVER.relative_to(ROOT)}")
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
        re.sub(r"\s+", " ", item).strip() for item in re.findall(r"^\d+\.\s+(.+)$", section(text, "Precedence"), re.M)
    ]


def has_heading(text: str, heading: str) -> bool:
    """Return whether a second-level markdown heading exists exactly."""
    return re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.M) is not None


def expected_agents(agents_md: str) -> set[str]:
    """Parse the expected LIMEN_AGENT values documented in AGENTS.md."""
    match = re.search(r"Expected values:\s*([a-z_ |]+)", agents_md)
    if not match:
        raise SystemExit("FAIL: AGENTS.md does not document expected LIMEN_AGENT values")
    return {part.strip() for part in match.group(1).split("|") if part.strip()}


def normalize_agent_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def documented_agent_notes(agents_md: str) -> set[str]:
    """Parse the ### headings under Agent-Specific Notes."""
    notes = section(agents_md, "Agent-Specific Notes")
    return {normalize_agent_label(heading) for heading in re.findall(r"^###\s+(.+)$", notes, re.M)}


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
    valid_agents = canonical_agents()

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
            if not negation.search(text[max(0, match.start() - 30) : match.start()]):
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

    # 2026-07-09 insights standing corrections: terminal statement, BLOCKED-once, and
    # registry-owns-the-answer are phrase-checked in their owning sections and mirrored
    # into the closeout skill (censor precedents PREC-2026-07-09-*).
    terminal = "CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items"
    for heading, phrase, label in [
        ("Closeout Definition", terminal, f"the terminal-statement rule ('{terminal}')"),
        (
            "Standing Autonomy & Compliant Gate Reroute",
            "BLOCKED: <atom>",
            "the BLOCKED-once protocol ('BLOCKED: <atom>' stated once, filed, never looped on)",
        ),
        ("Engage the Real Problem First", "The registry owns the answer", "the registry-owns-the-answer rule"),
        (
            "Merge & Branch Protocol",
            "scripts/await-pr.sh",
            "the sanctioned-waiter rule (never hand-roll a background PR poll loop; "
            "scripts/await-pr.sh is the one bounded, loud waiter)",
        ),
        (
            "Closeout Definition",
            "merge-drain",
            "the green-pending-PR-is-homed rule (the beat's merge rung owns it; cite it and end)",
        ),
    ]:
        try:
            if phrase not in section(claude_text, heading):
                errors.append(f"CLAUDE.md '{heading}' lacks {label}")
        except ValueError as exc:
            errors.append(str(exc))
    # 2026-07-14 standing correction: chronic fleet-debt (reopened ≥3×, never a PR) parks in
    # failed_blocked, never needs_human — the human surface stays truthful. Bind the phrase so
    # the Task States semantic can't silently drift back to escalating churn at the human.
    try:
        if "chronic fleet-debt" not in section(agents_text, "Task States"):
            errors.append(
                "AGENTS.md 'Task States' must bind failed_blocked to chronic fleet-debt "
                "(heal-dispatch parks chronic churn there, not in needs_human)"
            )
    except ValueError as exc:
        errors.append(str(exc))

    closeout_skill = ROOT / ".claude" / "skills" / "closeout" / "SKILL.md"
    if closeout_skill.exists():
        skill_text = closeout_skill.read_text(encoding="utf-8")
        if terminal not in skill_text:
            errors.append(".claude/skills/closeout/SKILL.md lacks the closeout terminal statement")
        if "BLOCKED: <atom>" not in skill_text:
            errors.append(".claude/skills/closeout/SKILL.md lacks the BLOCKED-once protocol")

    standard_text = STANDARD.read_text(encoding="utf-8")
    try:
        if precedence_items(agents_text) != precedence_items(standard_text):
            errors.append("AGENTS.md and docs/agent-instruction-standard.md have different Precedence ladders")
    except ValueError as exc:
        errors.append(str(exc))

    prompt_control = section(agents_text, "Prompt Corpus as the Control Plane")
    for phrase, label in [
        ("individual ask or correction as the unit of intent", "ask-level intent unit"),
        ("Corpus governance and execution run concurrently", "concurrent corpus/execution loop"),
        ("Do not make the human restate settled intent", "no-restatement rule"),
        ("`done` requires a durable owner receipt and a satisfied predicate", "strict done proof"),
    ]:
        if phrase not in prompt_control:
            errors.append(f"AGENTS.md prompt-corpus control section lacks {label}")
    if "Treat the full prompt corpus as a concurrent control plane" not in standard_text:
        errors.append("agent instruction standard lacks the concurrent prompt-corpus rule")

    expected = expected_agents(agents_text)
    expected_canonical = valid_agents - {"any"}
    if expected != expected_canonical:
        errors.append(
            "AGENTS.md Expected values drift from VALID_AGENTS "
            f"(missing={sorted(expected_canonical - expected)}, extra={sorted(expected - expected_canonical)})"
        )

    missing_notes = {
        agent for agent in expected if normalize_agent_label(agent) not in documented_agent_notes(agents_text)
    }
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
        if not template.exists():
            continue
        text = template.read_text(encoding="utf-8")
        if "AGENTS.md" not in text:
            errors.append(f"{template.relative_to(ROOT)} does not defer to a project/home AGENTS.md")
        invalid_presented = presented_status_tokens(text) - valid
        if invalid_presented:
            errors.append(
                f"{template.relative_to(ROOT)} presents non-canonical status values: {sorted(invalid_presented)}"
            )

    student_email_check = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check-student-email-grounding.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    if student_email_check.returncode != 0:
        output = (student_email_check.stdout + student_email_check.stderr).strip()
        errors.append("student-email grounding predicate failed" + (f":\n{output}" if output else ""))

    if errors:
        print("Agent-instruction doc drift detected:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"Agent-instruction docs match canonical task states ({', '.join(sorted(valid))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
