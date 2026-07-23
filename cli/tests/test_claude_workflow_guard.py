import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "claude-workflow-guard.py"


def run_guard(*args, input_text=None, env=None):
    child_env = os.environ.copy()
    if env:
        child_env.update(env)
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        input=input_text,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=child_env,
    )


def write_fable_receipt(tmp_path: Path) -> Path:
    now = datetime.now(UTC)
    monday = (now - timedelta(days=now.weekday())).date().isoformat()
    receipt = tmp_path / "fable-acceptance.json"
    receipt.write_text(
        json.dumps(
            {
                "schema": "limen.fable_acceptance.v1",
                "week": monday,
                "category": "adversarial-review",
                "percent": 5,
                "sources": ["docs/fable-allotment.md"],
                "verification": ["python3 scripts/fable-allotment.py audit"],
            }
        )
    )
    return receipt


def test_normalize_candidates_accepts_nested_json_string():
    payload = json.dumps(json.dumps([{"repo": "a-organvm/a-i-chat--exporter", "number": 44, "title": "ship"}]))
    proc = run_guard("normalize-candidates", input_text=payload)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)[0]["repo"] == "a-organvm/a-i-chat--exporter"


def test_normalize_candidates_rejects_undefined_target():
    proc = run_guard(
        "normalize-candidates",
        input_text=json.dumps([{"repo": "undefined", "number": 0, "title": "undefined"}]),
    )
    assert proc.returncode != 0
    assert "invalid repo" in proc.stderr


def test_audit_workflow_blocks_opus_fanout_and_unparsed_string_args(tmp_path):
    wf = {
        "workflowName": "verify-and-ship-clean-prs",
        "status": "killed",
        "agentCount": 2,
        "args": json.dumps([{"repo": "a-organvm/a-i-chat--exporter", "number": 44, "title": "ship"}]),
        "script": "const cands = args\nagent(prompt(c))",
        "workflowProgress": [
            {"model": "claude-opus-4-8[1m]", "label": "ship:undefined#undefined"},
            {"model": "claude-opus-4-8[1m]", "label": "ship:undefined#undefined"},
        ],
    }
    p = tmp_path / "wf.json"
    p.write_text(json.dumps(wf))
    proc = run_guard("audit-workflow", str(p), "--max-opus-agents", "1")
    assert proc.returncode == 2
    report = json.loads(proc.stdout)
    violations = "\n".join(report["reports"][0]["violations"])
    assert "Opus fanout blocked" in violations
    assert "undefined PR target detected" in violations
    assert "script does not parse args" in violations


def test_audit_workflow_blocks_unaccepted_fable(tmp_path):
    wf = {
        "workflowName": "canonical-fable-synthesis",
        "status": "completed",
        "agentCount": 1,
        "workflowProgress": [{"model": "claude-fable-5", "state": "done"}],
        "result": {"summary": "done"},
    }
    p = tmp_path / "wf.json"
    p.write_text(json.dumps(wf))
    proc = run_guard("audit-workflow", str(p))
    assert proc.returncode == 2
    violations = "\n".join(json.loads(proc.stdout)["reports"][0]["violations"])
    assert "Fable run lacks written acceptance command" in violations


def test_audit_workflow_allows_accepted_single_fable(tmp_path):
    receipt = tmp_path / "logs" / "fable-acceptance" / "accepted.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}")
    wf = {
        "workflowName": "canonical-fable-synthesis",
        "status": "completed",
        "agentCount": 1,
        "fableAcceptance": str(receipt),
        "workflowProgress": [{"model": "claude-fable-5", "state": "done"}],
        "result": {"summary": "done"},
    }
    p = tmp_path / "wf.json"
    p.write_text(json.dumps(wf))
    proc = run_guard("audit-workflow", str(p))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["ok"] is True


def test_audit_workflow_allows_sonnet_success_with_ci_failure_words(tmp_path):
    wf = {
        "workflowName": "heal-stuck-prs",
        "status": "completed",
        "agentCount": 1,
        "logs": ["HEAL wave done: 1 PRs touched"],
        "result": {"merged": [{"repo": "x/y", "number": 1, "proof": "fixed failing CI"}]},
        "workflowProgress": [{"model": "claude-sonnet-4-6", "state": "done"}],
    }
    p = tmp_path / "wf.json"
    p.write_text(json.dumps(wf))
    proc = run_guard("audit-workflow", str(p))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["ok"] is True


def test_audit_transcript_blocks_unbounded_expensive_opus_fanout(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "message": {"content": "keep going until ideal form; there is no stopping"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "model": "claude-opus-4-8",
                            "content": [
                                {"type": "tool_use", "name": "Agent", "input": {}},
                                {"type": "tool_use", "name": "Workflow", "input": {}},
                            ],
                            "usage": {
                                "input_tokens": 10,
                                "cache_creation_input_tokens": 20,
                                "cache_read_input_tokens": 1000,
                                "output_tokens": 30,
                            },
                        },
                    }
                ),
            ]
        )
        + "\n"
    )
    proc = run_guard(
        "audit-transcript",
        str(transcript),
        "--max-billable-tokens",
        "50",
        "--max-opus-billable-tokens",
        "50",
        "--max-agent-calls",
        "1",
    )
    assert proc.returncode == 2
    report = json.loads(proc.stdout)
    violations = "\n".join(report["violations"])
    assert "billable token budget exceeded" in violations
    assert "Opus billable budget exceeded" in violations
    assert "agent/workflow fanout exceeded" in violations
    assert "unbounded goal phrase detected" in violations


def test_audit_transcript_redacts_unbounded_prompt_text(tmp_path):
    transcript = tmp_path / "session.jsonl"
    prompt = "keep going until ideal form with private local details"
    transcript.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {"content": prompt},
            }
        )
        + "\n"
    )

    proc = run_guard("audit-transcript", str(transcript), "--max-billable-tokens", "1000000")
    assert proc.returncode == 2
    assert prompt not in proc.stdout
    report = json.loads(proc.stdout)
    evidence = report["unboundedGoalEvidence"][0]
    assert "text" not in evidence
    assert evidence["textSha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert evidence["chars"] == len(prompt)


def test_audit_transcript_flags_opus_subagent_fanout(tmp_path):
    """The verify-studio-launch shape: a cheap orchestrator that fans out expensive-tier
    subagents. The guard reads each subagent's REAL model field and flags the fan-out."""
    main = tmp_path / "session.jsonl"
    main.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "content": [{"type": "text", "text": "orchestrating"}],
                    "usage": {"input_tokens": 5, "output_tokens": 5},
                },
            }
        )
        + "\n"
    )
    subdir = tmp_path / "session" / "subagents"
    subdir.mkdir(parents=True)
    for name in ("verify-a", "verify-b"):
        (subdir / f"{name}.jsonl").write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "model": "claude-opus-4-8[1m]",
                        "content": [{"type": "text", "text": "trivial verify"}],
                        "usage": {"input_tokens": 5, "output_tokens": 5},
                    },
                }
            )
            + "\n"
        )
    proc = run_guard(
        "audit-transcript",
        str(main),
        "--max-billable-tokens",
        "1000000",
        "--max-opus-billable-tokens",
        "1000000",
        "--max-agent-calls",
        "100",
        "--max-opus-agents",
        "1",
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["expensiveSubagents"] == 2
    assert report["expensiveTier"] == "opus"
    assert "subagent fanout" in "\n".join(report["violations"])


def test_audit_transcript_recurses_workflow_subagent_dirs(tmp_path):
    main = tmp_path / "session.jsonl"
    main.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "content": [{"type": "text", "text": "orchestrating"}],
                    "usage": {"input_tokens": 5, "output_tokens": 5},
                },
            }
        )
        + "\n"
    )
    nested = tmp_path / "session" / "subagents" / "workflows" / "wf_123" / "agent-a.jsonl"
    nested.parent.mkdir(parents=True)
    nested.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-8[1m]",
                    "content": [{"type": "text", "text": "nested verifier"}],
                    "usage": {"input_tokens": 5, "output_tokens": 5},
                },
            }
        )
        + "\n"
    )

    proc = run_guard(
        "audit-transcript",
        str(main),
        "--max-billable-tokens",
        "1000000",
        "--max-opus-billable-tokens",
        "1000000",
        "--max-agent-calls",
        "100",
        "--max-opus-agents",
        "0",
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["files"] == [str(main), str(nested)]
    assert report["expensiveSubagents"] == 1
    assert "subagent fanout" in "\n".join(report["violations"])


def test_audit_transcript_blocks_unaccepted_fable(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-fable-5",
                    "content": [{"type": "text", "text": "canonical answer"}],
                    "usage": {"input_tokens": 5, "output_tokens": 5},
                },
            }
        )
        + "\n"
    )
    proc = run_guard("audit-transcript", str(transcript), "--max-billable-tokens", "1000000")
    assert proc.returncode == 2
    report = json.loads(proc.stdout)
    assert report["fableBillableTokens"] == 10
    assert "Fable run lacks written acceptance command" in "\n".join(report["violations"])


def test_audit_transcript_policy_mentions_do_not_accept_fable(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "message": {"content": "docs mention LIMEN_FABLE_ACCEPTANCE and fable-allotment.py accept"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "model": "claude-fable-5",
                            "content": [{"type": "text", "text": "done"}],
                            "usage": {"input_tokens": 5, "output_tokens": 5},
                        },
                    }
                ),
            ]
        )
        + "\n"
    )
    proc = run_guard("audit-transcript", str(transcript), "--max-billable-tokens", "1000000")
    assert proc.returncode == 2
    assert "Fable run lacks written acceptance command" in "\n".join(json.loads(proc.stdout)["violations"])


def test_audit_transcript_allows_current_receipt_env(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-fable-5",
                    "content": [{"type": "text", "text": "accepted"}],
                    "usage": {"input_tokens": 5, "output_tokens": 5},
                },
            }
        )
        + "\n"
    )
    receipt = write_fable_receipt(tmp_path)
    proc = run_guard(
        "audit-transcript",
        str(transcript),
        "--max-billable-tokens",
        "1000000",
        env={"LIMEN_FABLE_ACCEPTANCE": str(receipt)},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["fableAcceptanceSeen"] is True


def test_audit_transcript_gates_fable_billable_tokens(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-fable-5",
                    "content": [{"type": "text", "text": "expensive"}],
                    "usage": {"input_tokens": 40, "cache_creation_input_tokens": 40, "output_tokens": 40},
                },
            }
        )
        + "\n"
    )
    proc = run_guard(
        "audit-transcript",
        str(transcript),
        "--max-billable-tokens",
        "1000000",
        "--max-fable-billable-tokens",
        "100",
    )
    assert proc.returncode == 2
    assert "Fable billable budget exceeded" in "\n".join(json.loads(proc.stdout)["violations"])


def test_audit_transcript_allows_small_bounded_sonnet_session(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "content": [{"type": "text", "text": "done"}],
                    "usage": {
                        "input_tokens": 10,
                        "cache_creation_input_tokens": 0,
                        "output_tokens": 20,
                    },
                },
            }
        )
        + "\n"
    )
    proc = run_guard("audit-transcript", str(transcript), "--max-billable-tokens", "100")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["ok"] is True


def _bash_transcript(tmp_path, command):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "content": [{"type": "tool_use", "name": "Bash", "input": {"command": command}}],
                    "usage": {"input_tokens": 10, "output_tokens": 20},
                },
            }
        )
        + "\n"
    )
    return transcript


def test_audit_transcript_flags_full_suite_pytest(tmp_path):
    # The 2026-07-15 host-thrash incident command, verbatim.
    transcript = _bash_transcript(tmp_path, "cd cli && uv run python -m pytest tests/ -q 2>&1 | tail -15")
    proc = run_guard("audit-transcript", str(transcript), env={"LIMEN_ALLOW_FULL_PYTEST": "0"})
    report = json.loads(proc.stdout)
    assert proc.returncode != 0
    assert report["fullSuitePytestCalls"] == 1
    assert any("scoped-verification law" in v for v in report["violations"])


def test_audit_transcript_allows_scoped_pytest_and_verify_wrappers(tmp_path):
    for command in (
        "pytest cli/tests/test_dispatch.py -q",
        "python3 -m pytest cli/tests/test_dispatch.py::test_x",
        "bash scripts/verify-scoped.sh",
        "pip install pytest",
        "grep -r pytest tests/",
    ):
        transcript = _bash_transcript(tmp_path, command)
        proc = run_guard("audit-transcript", str(transcript), env={"LIMEN_ALLOW_FULL_PYTEST": "0"})
        report = json.loads(proc.stdout)
        assert report["fullSuitePytestCalls"] == 0, command
        assert proc.returncode == 0, command


def test_audit_transcript_full_pytest_escape_hatch(tmp_path):
    transcript = _bash_transcript(tmp_path, "python3 -m pytest cli/tests -q")
    proc = run_guard("audit-transcript", str(transcript), env={"LIMEN_ALLOW_FULL_PYTEST": "1"})
    report = json.loads(proc.stdout)
    assert report["fullSuitePytestCalls"] == 1  # still counted — only the violation is waived
    assert proc.returncode == 0
