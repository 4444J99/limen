from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-agent-docs.py"
SPEC = importlib.util.spec_from_file_location("check_agent_docs_peer_contract", SCRIPT)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def _documents() -> dict[str, str]:
    paths = [
        ROOT / "AGENTS.md",
        ROOT / "CLAUDE.md",
        ROOT / "GEMINI.md",
        ROOT / ".agents" / "skills" / "agy_conductor" / "SKILL.md",
        ROOT / "integrations" / "copilot" / "limen-conductor.agent.md",
    ]
    return {str(path.relative_to(ROOT)): path.read_text(encoding="utf-8") for path in paths}


def test_live_instruction_surfaces_satisfy_peer_conductor_contract() -> None:
    assert not (ROOT / ".github" / "agents" / "limen-conductor.agent.md").exists()
    assert CHECKER.peer_conductor_errors(_documents()) == []


def test_peer_conductor_predicate_rejects_rank_and_direct_board_guidance() -> None:
    documents = _documents()
    documents["GEMINI.md"] += "\nYou are the master conductor. Edit tasks.yaml after work.\n"
    documents["CLAUDE.md"] += "\nThe Codex-conductor decides. Claude owns the task lifecycle.\n"

    errors = CHECKER.peer_conductor_errors(documents)

    assert any("master-conductor rank wording" in error for error in errors)
    assert any("fixed Codex-conductor wording" in error for error in errors)
    assert any("direct tasks.yaml write guidance" in error for error in errors)
    assert "CLAUDE.md defines tool-specific lifecycle rules" in errors


def test_peer_conductor_predicate_rejects_hidden_copilot_fanout_and_model_pin() -> None:
    documents = _documents()
    profile = documents["integrations/copilot/limen-conductor.agent.md"]
    documents["integrations/copilot/limen-conductor.agent.md"] = profile.replace(
        "  - read",
        "model: fixed-model\n  - agent\n  - read",
        1,
    )

    errors = CHECKER.peer_conductor_errors(documents)

    assert "Copilot conductor profile pins a model instead of using provider Auto" in errors
    assert "Copilot conductor profile enables hidden native agent fanout" in errors
