import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "claude-workflow-guard.py"


def run_guard(*args, input_text=None):
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        input=input_text,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


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
