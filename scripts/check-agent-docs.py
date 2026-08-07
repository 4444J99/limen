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

  M. The four session-discipline rules (derive/no-menu, bounded-CI-waits, durable-homing,
     no-stall/BLOCKED-once) are present in the AGENTS.md shared layer (``## Session Discipline``
     section), and the home-scope Layer-1 AGENTS.md template defers to that shared layer rather
     than diverging.

  N. The six standing corrections from insights reports 2026-06-23 → 2026-07-17 are present in
     AGENTS.md under the ``### Standing Corrections`` subsection of ``## Session Discipline``:
     (a) predicate-not-prose done, (b) terminal closeout / fixed-point, (c) derive-before-asking,
     (d) durable-homing for all produced state, (e) active-unblocking, (f) triage-window anchor.

  O. The Peer Conductor Contract stays symmetric across the shared layer and native adapters:
     conductor is a capability rather than a rank, children are broker-reserved with attenuated
     authority, native identity and protected human sessions survive, hidden fanout is rejected,
     and no instruction surface tells an agent to write ``tasks.yaml`` directly.

  P. Concurrent integration is a shared invariant: moving main does not rewrite every PR head,
     queue mode uses ``merge_group``, and neither the shared nor tool-specific protocol permits an
     admin bypass of the serialization rail.

  Q. The closure covenant is lane-neutral: AGENTS.md ``## Full Lifecycle Closure`` binds every
     lane (CLI, desktop, IDE, fleet, MCP) to the predicate-backed fixed point
     (``no-tasks-on-me.sh`` + ``credential-wall.py --check``), the terminal statement, and the
     rule that menus/caveat-tails/transcript-parked items are not closure forms. (2026-08-06:
     three consecutive insights runs found the same defect in different lanes — the rule lived
     only in CLAUDE.md, the one file the other lanes never read.)

  R. Session-discipline rules 6/7 stay encoded in the AGENTS.md shared layer: read the
     predicate's own exit code, never a pipeline's (rule 6), and one command per judged
     invocation on hook-judged rails, with the scripts-chain-freely carve-out (rule 7).

  S. Instruction surfaces fit their declared byte budget (gates.yaml ``instruction_surfaces``;
     G1 2026-08-06 — codex silently truncated AGENTS.md at its default 32,768-byte cap):
     S1 the budget equals the weakest consumer's default cap (derived, not chosen); S2 every
     surface fits the shrink-only ceiling; S3 the ceiling follows the file down (dead headroom
     stays within slack); S4 the debt line exists exactly while a surface exceeds the budget.

Run directly (``scripts/check-agent-docs.py``) or via ``scripts/verify-whole.sh``.

Checks that read the domus-genoma templates run only when that repo is NESTED at
``./domus-genoma``; in the sibling-clone layout they are SKIPPED, and main() announces the
skip loudly instead of silently passing (the 8 dead-check incident, 2026-08-06).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp" / "src" / "limen_mcp" / "server.py"
DOCS = [ROOT / "AGENTS.md", ROOT / "GEMINI.md", ROOT / "CLAUDE.md"]
STANDARD = ROOT / "docs" / "agent-instruction-standard.md"
AGY_SKILL = ROOT / ".agents" / "skills" / "agy_conductor" / "SKILL.md"
COPILOT_PROFILE = ROOT / "integrations" / "copilot" / "limen-conductor.agent.md"
COPILOT_REPO_OVERRIDE = ROOT / ".github" / "agents" / "limen-conductor.agent.md"
COPILOT_POINTER = ROOT / ".github" / "copilot-instructions.md"
SCOPED_AGENTS = [ROOT / "apps" / "danse" / "AGENTS.md"]
REFERENCE_DOCS = DOCS + [
    ROOT / "CONTRIBUTING.md",
    STANDARD,
    ROOT / "docs" / "deployment.md",
    COPILOT_POINTER,
    *SCOPED_AGENTS,
]
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
        "Peer Conductor Contract",
        "Correction Propagation",
        "Engineering Ownership",
        "Session Discipline",
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
    for match in re.finditer(
        r"(?:`|\()((?:docs|scripts|mcp|web|cli|spec|institutio|integrations|apps|organs|censor|moneta|ianva)"
        r"/[A-Za-z0-9_.\-/]+)(?:`|\))",
        text,
    ):
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


def peer_conductor_errors(documents: dict[str, str]) -> list[str]:
    """Return symmetric-conduct doctrine violations in instruction surfaces."""

    errors: list[str] = []
    agents_text = documents.get("AGENTS.md", "")
    try:
        contract = section(agents_text, "Peer Conductor Contract")
    except ValueError as exc:
        return [str(exc)]
    normalized_contract = re.sub(r"\s+", " ", contract)

    for phrase, label in [
        ("temporary capability, never a rank", "temporary-capability rule"),
        ("no master agent or model hierarchy", "no-hierarchy rule"),
        ("shared conduct broker", "shared-broker rule"),
        ("only reduce its parent's authority", "authority-attenuation rule"),
        ("Preserve native identity", "native-identity rule"),
        ("human_protected: true", "protected-human-session rule"),
        ("Hidden native fanout is rejected", "hidden-fanout rule"),
        ("Never edit `tasks.yaml` directly", "single-writer projection rule"),
    ]:
        if phrase not in normalized_contract:
            errors.append(f"AGENTS.md 'Peer Conductor Contract' lacks the {label}")

    rank_patterns = [
        (re.compile(r"\bmaster conductor\b", re.I), "master-conductor rank wording"),
        (re.compile(r"\bprimary agent swarm\s*\(\s*`?conductor`?\s*\)", re.I), "primary-conductor wording"),
        (re.compile(r"\bCodex(?:-only)?[- ]conductor\b", re.I), "fixed Codex-conductor wording"),
        (re.compile(r"\bsimilar to Claude or Codex\b", re.I), "model-hierarchy comparison"),
    ]
    direct_board = re.compile(
        r"\b(?:edit|editing|write|writing|rewrite|rewriting|read/write|commit(?:\s+and\s+push)?|push|"
        r"mutate|update)\b[^\n]{0,60}\btasks\.yaml\b",
        re.I,
    )
    negation = re.compile(r"\b(?:never|not|no|cannot|mustn't|must not|do not|does not|don't|doesn't)\b", re.I)
    for name, text in documents.items():
        for pattern, label in rank_patterns:
            if pattern.search(text):
                errors.append(f"{name} contains forbidden {label}")
        lines = text.splitlines()
        for line_number, line in enumerate(lines, start=1):
            context = (lines[line_number - 2] + " " + line) if line_number > 1 else line
            for match in direct_board.finditer(line):
                context_match = direct_board.search(context)
                if context_match and not negation.search(context[: context_match.start()]):
                    errors.append(f"{name}:{line_number} contains direct tasks.yaml write guidance")
                    break

    adapters = {
        name: documents.get(name, "")
        for name in (
            "CLAUDE.md",
            "GEMINI.md",
            ".agents/skills/agy_conductor/SKILL.md",
            "integrations/copilot/limen-conductor.agent.md",
        )
    }
    for name, text in adapters.items():
        if not text:
            errors.append(f"missing peer-conductor adapter: {name}")
        elif "Peer Conductor Contract" not in text:
            errors.append(f"{name} does not defer to AGENTS.md 'Peer Conductor Contract'")

    lifecycle_patterns = [
        re.compile(r"\bConductor Execution Loop\b", re.I),
        re.compile(r"\bThe lifecycle is the durable contract\b", re.I),
        re.compile(r"\b(?:Claude|Gemini|Agy|Copilot)\s+(?:owns|defines)\s+(?:the\s+)?(?:task\s+)?lifecycle\b", re.I),
        re.compile(r"\bStatus Updates:\s+As work progresses\b", re.I),
    ]
    for name, text in adapters.items():
        for pattern in lifecycle_patterns:
            if pattern.search(text):
                errors.append(f"{name} defines tool-specific lifecycle rules")
                break

    copilot = adapters["integrations/copilot/limen-conductor.agent.md"]
    if COPILOT_REPO_OVERRIDE.exists():
        errors.append(
            "repository-level Copilot conductor profile overrides the organization profile; "
            "keep only integrations/copilot/limen-conductor.agent.md as the publication source"
        )
    for phrase, label in [
        ("target: github-copilot", "GitHub Copilot target"),
        ("COPILOT_MCP_LIMEN_CONDUCT_URL", "Agents variable-owned remote MCP URL"),
        ("COPILOT_MCP_LIMEN_CONDUCT_TOKEN", "Agents secret-owned bearer"),
        ("limen-conductor/*", "conduct MCP tool namespace"),
    ]:
        if phrase not in copilot:
            errors.append(f"Copilot conductor profile lacks {label}")
    frontmatter = copilot.split("---", 2)[1] if copilot.count("---") >= 2 else copilot
    if re.search(r"^model\s*:", frontmatter, re.M):
        errors.append("Copilot conductor profile pins a model instead of using provider Auto")
    if re.search(r"^\s*-\s*agent\s*$", frontmatter, re.M):
        errors.append("Copilot conductor profile enables hidden native agent fanout")

    return errors


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

    # Template checks require the domus-genoma clone NESTED at ./domus-genoma. In the
    # sibling-clone layout every one of these silently never ran (8 dead checks,
    # 2026-08-06) — a skipped check must announce itself so absence of findings is
    # never mistaken for a green.
    skipped_templates = [t for t in TEMPLATE_DOCS if not t.exists()]
    if skipped_templates:
        print(
            f"NOTE: {len(skipped_templates)} domus-genoma template check(s) SKIPPED — "
            "no nested clone at ./domus-genoma (sibling-clone layout); these run only "
            "when the clone is nested"
        )
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

    # M. Four session-discipline rules must be present in AGENTS.md ## Session Discipline section
    # and the home-scope Layer-1 AGENTS.md template must defer to the shared layer.
    try:
        discipline_section = section(agents_text, "Session Discipline")
        for phrase, label in [
            ("scripts/verify-scoped.sh", "bounded-CI-waits rule (verify-scoped.sh is the default gate)"),
            ("scripts/await-pr.sh", "bounded-CI-waits rule (await-pr.sh is the one sanctioned waiter)"),
            ("BLOCKED: <atom>", "no-stall/BLOCKED-once rule"),
            ("his-hand-levers.json", "durable-homing rule (human-gated atoms file in his-hand-levers.json)"),
            ("registry already owns the answer", "derive/no-menu rule (registry owns the answer)"),
        ]:
            if phrase not in discipline_section:
                errors.append(
                    f"AGENTS.md 'Session Discipline' lacks the {label} "
                    f"(fix: add the phrase '{phrase}' to ## Session Discipline)"
                )
    except ValueError as exc:
        errors.append(str(exc))

    home_agents_tmpl = ROOT / "domus-genoma" / "dot_config" / "ai-context" / "AGENTS.md.tmpl"
    if not home_agents_tmpl.exists():
        print(
            "NOTE: home-scope Layer-1 AGENTS.md.tmpl deferral check SKIPPED — "
            "no nested domus-genoma clone (sibling-clone layout)"
        )
    if home_agents_tmpl.exists():
        tmpl_text = home_agents_tmpl.read_text(encoding="utf-8")
        for phrase, label in [
            ("Session Discipline", "Session Discipline section pointer"),
            ("verify-scoped.sh", "bounded-CI-waits rule"),
            ("await-pr.sh", "bounded-CI-waits sanctioned-waiter rule"),
            ("BLOCKED:", "no-stall/BLOCKED-once rule"),
        ]:
            if phrase not in tmpl_text:
                errors.append(
                    f"domus-genoma/dot_config/ai-context/AGENTS.md.tmpl lacks the {label} "
                    f"(the home-scope Layer-1 template must defer to the shared-layer disciplines; "
                    f"fix: ensure the Session Discipline summary block is present)"
                )

    # N. Six standing corrections from insights reports 2026-06-23 → 2026-07-17 must be present
    # in the AGENTS.md ## Session Discipline section (### Standing Corrections subsection).
    try:
        discipline_section = section(agents_text, "Session Discipline")
        for phrase, label in [
            (
                "owning predicate or tests pass on live state",
                "N-a predicate-not-prose done rule "
                "(no agent claims completion until the owning predicate or tests pass on live state)",
            ),
            (
                "File residual work with its durable owner",
                "N-b terminal-closeout / fixed-point rule "
                "(file residual work with its durable owner; never hand it back as a list)",
            ),
            (
                "A decision already answered by charter, registry, or precedent is queried and applied",
                "N-c derive-before-asking rule "
                "(a decision already answered by charter, registry, or precedent is queried and applied)",
            ),
            (
                "Config, data, docs, and receipts produced in a session land in their git-tracked owner",
                "N-d durable-homing-for-all-produced-state rule "
                "(config, data, docs, and receipts produced in a session land in their git-tracked owner)",
            ),
            (
                "attempt its documented bootstrap path once",
                "N-e active-unblocking rule "
                "(when a bridge/auth/gate is blocked, attempt its documented bootstrap path once)",
            ),
            (
                "Triage windows start at the last human review",
                "N-f triage-window-anchor rule "
                "(triage windows start at the last human review, not the last automated run)",
            ),
        ]:
            if phrase not in discipline_section:
                errors.append(
                    f"AGENTS.md 'Session Discipline' lacks {label} "
                    f"(fix: add the phrase to the ### Standing Corrections subsection)"
                )
    except ValueError as exc:
        errors.append(str(exc))

    peer_documents = {doc.name: doc.read_text(encoding="utf-8") for doc in DOCS}
    peer_documents[str(AGY_SKILL.relative_to(ROOT))] = AGY_SKILL.read_text(encoding="utf-8")
    peer_documents[str(COPILOT_PROFILE.relative_to(ROOT))] = COPILOT_PROFILE.read_text(encoding="utf-8")
    errors.extend(peer_conductor_errors(peer_documents))

    # P. 2026-07-18 concurrent-session correction: exact PR-head proof is immutable; latest-base
    # composition belongs to the queue. Bind both the canonical shared rule and Claude's concrete
    # merge cadence so a later doc edit cannot silently recreate the update-branch/full-CI loop.
    try:
        discipline_section = section(agents_text, "Session Discipline")
        for phrase, label in [
            ("moving `main` is normal", "moving-main-is-normal rule"),
            ("synthetic `merge_group`", "merge-group composition rule"),
            ("never `--admin`", "no-admin-bypass rule"),
        ]:
            if phrase not in discipline_section:
                errors.append(f"AGENTS.md 'Session Discipline' lacks the concurrent-integration {label}")
        merge_section = section(claude_text, "Merge & Branch Protocol")
        for phrase, label in [
            ("MERGE-MODE: queue|direct", "explicit merge-mode contract"),
            ("synthetic latest-base merge group", "queue composition contract"),
            ("repeated branch-rewrite/full-CI loop", "no branch-rewrite starvation rule"),
        ]:
            if phrase not in merge_section:
                errors.append(f"CLAUDE.md 'Merge & Branch Protocol' lacks the concurrent-integration {label}")
        if "moving `main` is integrated by the repository merge" not in standard_text:
            errors.append("agent instruction standard lacks the concurrent-integration rule")
    except ValueError as exc:
        errors.append(str(exc))

    # Q. 2026-08-06 universal-covenant correction: the closure covenant binds every lane, so it
    # lives in AGENTS.md ## Full Lifecycle Closure — phrase-bound here so a doc edit cannot
    # quietly demote it back to a single lane's charter.
    try:
        closure_section = section(agents_text, "Full Lifecycle Closure")
        for phrase, label in [
            ("Closure is a covenant", "lane-neutral covenant framing ('Closure is a covenant, not one lane's ritual')"),
            ("scripts/no-tasks-on-me.sh", "nothing-hangs predicate citation"),
            ("scripts/credential-wall.py", "credential-wall predicate citation"),
            (terminal, f"closure terminal statement ('{terminal}')"),
            ("are not closure forms", "non-closure-forms rule (menus, caveat tails, transcript-parked items)"),
        ]:
            if phrase not in closure_section:
                errors.append(f"AGENTS.md 'Full Lifecycle Closure' lacks the {label}")
    except ValueError as exc:
        errors.append(str(exc))

    # R. Session-discipline rules 6/7 (2026-08-06 covenant additions): pipeline exit-code honesty
    # and one-command-per-judged-invocation, including the scripts-chain-freely carve-out that
    # keeps the rule from being misread as a ban on composition inside committed scripts.
    try:
        discipline_section = section(agents_text, "Session Discipline")
        for phrase, label in [
            ("Read the predicate's own exit code", "rule-6 pipeline-exit-code rule"),
            ("PIPESTATUS", "rule-6 PIPESTATUS mechanism"),
            ("One command per judged invocation", "rule-7 one-command-per-judged-invocation rule"),
            ("Shell **scripts** chain freely", "rule-7 scripts-chain-freely carve-out"),
        ]:
            if phrase not in discipline_section:
                errors.append(f"AGENTS.md 'Session Discipline' lacks the {label}")
    except ValueError as exc:
        errors.append(str(exc))

    # S. Instruction-surface byte budget (G1, 2026-08-06): codex truncated AGENTS.md at its
    # default 32,768-byte cap and silently dropped every section past it — including its own
    # Agent-Specific Note. The registry declares the budget; this check makes surface size a
    # ratchet instead of a surprise.
    gates_registry = ROOT / "institutio" / "governance" / "gates.yaml"
    surfaces_cfg = None
    try:
        surfaces_cfg = (yaml.safe_load(gates_registry.read_text(encoding="utf-8")) or {}).get("instruction_surfaces")
    except yaml.YAMLError as exc:
        errors.append(f"instruction_surfaces unreadable in {gates_registry.relative_to(ROOT)}: {exc}")
    if surfaces_cfg:
        budget = int(surfaces_cfg.get("budget_bytes") or 0)
        ceiling = int(surfaces_cfg.get("ceiling_bytes") or 0)
        slack = int(surfaces_cfg.get("slack_bytes") or 0)
        consumer_caps = [
            int(c["default_bytes"])
            for c in surfaces_cfg.get("consumers") or []
            if isinstance(c, dict) and c.get("default_bytes") is not None
        ]
        # S1 — the budget IS the weakest consumer's default cap, not a hand-picked number.
        if consumer_caps and budget != min(consumer_caps):
            errors.append(
                f"instruction_surfaces budget_bytes={budget} must equal the minimum consumer "
                f"default cap ({min(consumer_caps)}) — the budget is derived, not chosen (S1)"
            )
        has_debt = bool(str(surfaces_cfg.get("debt") or "").strip())
        for name in surfaces_cfg.get("surfaces") or []:
            surface = ROOT / str(name)
            if not surface.exists():
                errors.append(f"instruction_surfaces names a missing surface: {name} (S2)")
                continue
            size = surface.stat().st_size
            # S2 — shrink-only ratchet: the surface never outgrows the declared ceiling.
            if size > ceiling:
                errors.append(
                    f"{name} is {size} B, over the {ceiling} B ceiling — trim the surface or "
                    f"relocate doctrine to Tier-1 homes; never raise the ceiling to fit (S2)"
                )
            # S3 — the ceiling follows the file down: dead headroom stays within slack.
            elif ceiling - size > slack:
                errors.append(
                    f"{name} shrank to {size} B but ceiling_bytes={ceiling} leaves "
                    f"{ceiling - size} B dead headroom (> slack {slack}) — lower the ceiling (S3)"
                )
            # S4 — the debt line exists exactly while the surface exceeds the budget.
            if size > budget and not has_debt:
                errors.append(
                    f"{name} is {size} B (> budget {budget}) but instruction_surfaces carries no "
                    f"debt line naming the retirement owner (S4)"
                )
            if size <= budget and has_debt:
                errors.append(
                    f"{name} fits the {budget} B budget but the debt line is still present — "
                    f"the debt is paid; remove the line (S4)"
                )

    # T — the pointer file and directory-scoped surfaces are part of the estate
    # (2026-08-06 audit: both were checked by NOTHING, so the pointer could silently
    # grow into the competing rulebook AGENTS.md forbids, and a scoped AGENTS.md could
    # invert precedence or invent states with no predicate objecting).
    if not COPILOT_POINTER.exists():
        errors.append(".github/copilot-instructions.md is missing — Copilot reads this path natively (T)")
    else:
        pointer_text = COPILOT_POINTER.read_text(encoding="utf-8")
        if "AGENTS.md" not in pointer_text:
            errors.append(".github/copilot-instructions.md does not point at AGENTS.md (T)")
        if "this file is stale" not in pointer_text:
            errors.append(
                ".github/copilot-instructions.md lost its self-subordination clause "
                "('they win and this file is stale') — it is a pointer, never a second rulebook (T)"
            )
        invalid_presented = presented_status_tokens(pointer_text) - valid
        if invalid_presented:
            errors.append(
                f".github/copilot-instructions.md presents non-canonical status values: {sorted(invalid_presented)} (T)"
            )
    for scoped in SCOPED_AGENTS:
        if not scoped.exists():
            errors.append(f"{scoped.relative_to(ROOT)} is a declared scoped surface but is missing (T)")
            continue
        scoped_text = scoped.read_text(encoding="utf-8")
        if "AGENTS.md" not in scoped_text or "root wins" not in scoped_text:
            errors.append(
                f"{scoped.relative_to(ROOT)} must defer to the root contract "
                f"(a root AGENTS.md reference plus 'root wins') — closest wins, never higher-ranked (T)"
            )
        invalid_presented = presented_status_tokens(scoped_text) - valid
        if invalid_presented:
            errors.append(
                f"{scoped.relative_to(ROOT)} presents non-canonical status values: {sorted(invalid_presented)} (T)"
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
