#!/usr/bin/env python3
"""Hermetic regression for claude-workflow-guard's phase-tier law (Fable plans, cheaper tiers build).

Two audit lanes, no live transcripts:
  1. audit-transcript — a mutation tool call (Edit / mutating Bash) on a Fable-model assistant
     turn is a "building on Fable" violation; LIMEN_ALLOW_FABLE_BUILD=1 clears it; the same
     mutation on a haiku turn is clean.
  2. _workflow_violations — a workflow whose scan blob carries mode:build-from-plan and whose
     progress ran an expensive (opus/fable) model is a violation; the same workflow on sonnet
     is clean; LIMEN_ALLOW_EXPENSIVE_BUILD=1 clears it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]

_PHASE_ENV = (
    "LIMEN_ALLOW_FABLE_BUILD",
    "LIMEN_ALLOW_EXPENSIVE_BUILD",
    "LIMEN_ALLOW_UNACCEPTED_FABLE",
    "LIMEN_FABLE_ACCEPTANCE",
)


def _load_guard():
    spec = importlib.util.spec_from_file_location("claude_workflow_guard", SCRIPTS / "claude-workflow-guard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _assistant_row(model: str, tool: str, tool_input: dict | None = None) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "model": model,
                "content": [{"type": "tool_use", "name": tool, "input": tool_input or {}}],
            },
        }
    )


def _audit(mod, path: Path) -> dict:
    return mod.audit_transcript(
        str(path),
        max_billable_tokens=10**9,
        max_opus_billable_tokens=10**9,
        max_fable_billable_tokens=10**9,
        max_agent_calls=10**6,
        max_opus_agents=10**6,
        max_fable_agents=10**6,
    )


def main() -> int:
    for key in _PHASE_ENV:
        os.environ.pop(key, None)
    mod = _load_guard()

    with tempfile.TemporaryDirectory() as td:
        # 1. Edit + mutating Bash on Fable turns → building-on-Fable violation, evidence for both.
        fable = Path(td) / "fable-session.jsonl"
        fable.write_text(
            "\n".join(
                [
                    _assistant_row("claude-fable-5", "Edit", {"file_path": "x.py"}),
                    _assistant_row("claude-fable-5", "Bash", {"command": "git commit -m x"}),
                ]
            )
        )
        report = _audit(mod, fable)
        assert any("building on Fable" in v for v in report["violations"]), report["violations"]
        assert report["fableBuildToolCalls"] == 2, report
        assert {e["tool"] for e in report["fableBuildEvidence"]} == {"Edit", "Bash"}, report

        # 1b. The escape hatch clears the violation (evidence still reported).
        os.environ["LIMEN_ALLOW_FABLE_BUILD"] = "1"
        try:
            allowed = _audit(mod, fable)
            assert not any("building on Fable" in v for v in allowed["violations"]), allowed["violations"]
            assert allowed["fableBuildToolCalls"] == 2, allowed
        finally:
            os.environ.pop("LIMEN_ALLOW_FABLE_BUILD", None)

        # 1c. The same mutation on a cheap turn is clean — the law binds the tier, not the tool.
        haiku = Path(td) / "haiku-session.jsonl"
        haiku.write_text(_assistant_row("claude-haiku-4-5", "Edit", {"file_path": "x.py"}))
        clean = _audit(mod, haiku)
        assert clean["fableBuildToolCalls"] == 0, clean
        assert not any("building on Fable" in v for v in clean["violations"]), clean["violations"]

    # 2. Workflow lane: build-from-plan on an expensive model → violation; sonnet → clean.
    def wf(model: str) -> dict:
        return {
            "workflowName": "phase-test",
            "workflowProgress": [{"model": model, "promptPreview": "mode:build-from-plan: apply the plan"}],
        }

    expensive = mod._workflow_violations(Path("wf.json"), wf("claude-opus-5"), max_opus_agents=99, max_fable_agents=99)
    assert any("build-from-plan ran on an expensive tier" in v for v in expensive), expensive
    cheap = mod._workflow_violations(Path("wf.json"), wf("claude-sonnet-5"), max_opus_agents=99, max_fable_agents=99)
    assert not any("build-from-plan" in v for v in cheap), cheap
    os.environ["LIMEN_ALLOW_EXPENSIVE_BUILD"] = "1"
    try:
        waived = mod._workflow_violations(Path("wf.json"), wf("claude-opus-5"), max_opus_agents=99, max_fable_agents=99)
        assert not any("build-from-plan" in v for v in waived), waived
    finally:
        os.environ.pop("LIMEN_ALLOW_EXPENSIVE_BUILD", None)

    print("claude-workflow-guard-phase: OK (fable-build violation, escape hatch, cheap-turn clean, workflow lane)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
