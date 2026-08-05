#!/usr/bin/env python3
"""Guardrails for Claude dynamic workflows used by the Limen conductor.

This script exists because the b7efae9c session burned a large Opus fanout on
unparsed JSON-string args, producing 134 `undefined#undefined` verifier agents.

It gives the conductor three fail-closed checks:
  * normalize-candidates: parse JSON payloads, including accidental JSON strings,
    and reject any PR candidate without a real repo + PR number.
  * audit-workflow: inspect a saved Claude workflow JSON for unsafe fanout,
    undefined targets, hidden agent failures, or string args used without parsing.
  * audit-session: apply the workflow audit to every workflow in a Claude session.

Read-only. It writes no repo state unless --out is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BAD_TARGET_RE = re.compile(r"\bundefined#undefined\b|repo[=:]\\?\"?undefined|number[=:]\\?\"?undefined")
FAILED_LOG_RE = re.compile(r"\bfailed:|agent died|monthly spend limit|rate[_ -]?limit", re.IGNORECASE)
FABLE_ACCEPTANCE_RE = re.compile(
    r"fable-allotment\.py\s+accept|LIMEN_FABLE_ACCEPTANCE|fableAcceptance|fable-acceptance",
    re.IGNORECASE,
)

# pytest at command position, in any of its shapes (mirrors scripts/hooks/pytest-scope-guard.sh).
_PYTEST_CMD_RE = re.compile(
    r"(?:^|[;&|(]\s*|`\s*)\s*(?:command\s+)?"
    r"(?:env\s+(?:-u\s+\S+\s+|[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"
    r"(?:uv\s+run\s+(?:--\S+\s+)*)?"
    r"(?:\S*python3?(?:\.\d+)?\s+-m\s+)?"
    r"(?:\S*/)?pytest\b"
)
_VERIFY_WRAPPER_RE = re.compile(r"verify\.py|verify-scoped\.sh|verify-whole\.sh")
_PYTEST_SUITE_ROOTS = {"tests", "cli/tests", "web/api/tests"}
_PYTEST_VALUE_FLAGS = {
    "-k",
    "-m",
    "-p",
    "-o",
    "-W",
    "-c",
    "-n",
    "--tb",
    "--maxfail",
    "--durations",
    "--ignore",
    "--deselect",
    "--rootdir",
    "--confcutdir",
}


def _full_suite_pytest(cmd: str) -> bool:
    """Transcript-side heuristic for the scoped-verification law: a pytest invocation whose
    positional args are suite roots (or absent) is a full collection. The PreToolUse hook
    (scripts/hooks/pytest-scope-guard.sh) is the enforcement, with filesystem resolution;
    this audit is the backstop for shapes the hook structurally misses (heredocs, nested
    shells, daemon lanes). No cwd, no filesystem — suite roots by name only, advisory-grade.
    2026-07-15 host-thrash incident: two concurrent full cli suites from one session."""
    if not cmd or "pytest" not in cmd or _VERIFY_WRAPPER_RE.search(cmd):
        return False
    for m in _PYTEST_CMD_RE.finditer(cmd):
        tail = re.split(r"\d*>|<|;|\||&", cmd[m.end() :], maxsplit=1)[0]
        try:
            tokens = shlex.split(tail)
        except ValueError:
            continue
        paths, skip = [], False
        for tok in tokens:
            if skip:
                skip = False
                continue
            if tok.startswith("-"):
                skip = tok in _PYTEST_VALUE_FLAGS
                continue
            paths.append(tok.rstrip("/"))
        if any(".py" in os.path.basename(p.split("::")[0]) or "::" in p for p in paths):
            continue
        if not paths:
            return True
        if all(p in _PYTEST_SUITE_ROOTS or p.endswith(("/cli/tests", "/web/api/tests")) for p in paths):
            return True
    return False


def _model_selection() -> Any:
    """Load the shared tier vocabulary BY FILE PATH — the same self-contained importlib load
    ``scripts/shims/claude`` uses — so this guard never re-encodes the model ladder and never
    drags in the ``limen`` package ``__init__``. Fail-open to None so the guard still runs
    standalone if the module is missing. ([[fleet-model-floor-bleed]] [[derive-never-pin-hardcodes]])"""
    try:
        import importlib.util

        root = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[1])
        path = root / "cli" / "src" / "limen" / "model_selection.py"
        if not path.exists():
            path = Path(__file__).resolve().parents[1] / "cli" / "src" / "limen" / "model_selection.py"
        spec = importlib.util.spec_from_file_location("_limen_model_selection_guard", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _tier_order() -> tuple[str, ...]:
    mod = _model_selection()
    try:
        if mod is not None:
            return tuple(str(t) for t in mod._CLAUDE_TIER_ORDER)
    except Exception:
        pass
    return ("haiku", "sonnet", "opus")


def _expensive_tier() -> str:
    """The Opus-class expensive rung's alias. Fable is guarded separately because it has a
    written-acceptance rule; adding it above Opus must not make Opus fan-out invisible."""
    order = _tier_order()
    if "opus" in order:
        return "opus"
    try:
        return order[-1]
    except Exception:
        return "opus"


def _fable_tier() -> str:
    order = _tier_order()
    if "fable" in order:
        return "fable"
    return "fable"


# The expensive rung, resolved once per process from the one brain (not a hardcoded literal).
_EXPENSIVE = _expensive_tier()
_FABLE = _fable_tier()


def _read_text(path: str | None) -> str:
    if path and path != "-":
        return Path(path).read_text()
    return sys.stdin.read()


def _json_loads_nested(text: str) -> Any:
    data = json.loads(text)
    if isinstance(data, str):
        data = json.loads(data)
    return data


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _current_fable_acceptance_present() -> bool:
    mod = _model_selection()
    try:
        return bool(mod is not None and mod._claude_fable_acceptance_present())
    except Exception:
        return False


def _structured_fable_acceptance(value: Any) -> bool:
    text = _as_text(value).strip()
    return bool(text and FABLE_ACCEPTANCE_RE.search(text))


def normalize_candidates(data: Any, *, allow_empty: bool = False) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise ValueError(f"candidate payload must be a JSON list, got {type(data).__name__}")
    if not data and not allow_empty:
        raise ValueError("candidate payload is empty")

    seen: set[tuple[str, int]] = set()
    out: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"[{i}] candidate must be an object")
            continue
        repo = item.get("repo")
        number = item.get("number")
        title = item.get("title", "")
        if not isinstance(repo, str) or not REPO_RE.match(repo) or "undefined" in repo.lower():
            errors.append(f"[{i}] invalid repo: {repo!r}")
        if not isinstance(number, int) or number <= 0:
            errors.append(f"[{i}] invalid PR number: {number!r}")
        if isinstance(title, str) and title.lower() == "undefined":
            errors.append(f"[{i}] invalid title: {title!r}")
        if isinstance(repo, str) and isinstance(number, int):
            key = (repo, number)
            if key in seen:
                errors.append(f"[{i}] duplicate PR target: {repo}#{number}")
            seen.add(key)
        out.append(dict(item))

    if errors:
        raise ValueError("; ".join(errors))
    return out


def _workflow_violations(
    path: Path,
    wf: dict[str, Any],
    *,
    max_opus_agents: int,
    max_fable_agents: int,
) -> list[str]:
    violations: list[str] = []
    name = wf.get("workflowName") or wf.get("summary") or path.name
    progress = wf.get("workflowProgress") or []
    int(wf.get("agentCount") or len(progress) or 0)
    models = [str(p.get("model", "")) for p in progress if isinstance(p, dict)]
    opus_agents = sum(1 for m in models if _EXPENSIVE in m.lower())
    fable_agents = sum(1 for m in models if _FABLE in m.lower())

    if opus_agents > max_opus_agents and os.environ.get("LIMEN_ALLOW_OPUS_FANOUT") != "1":
        violations.append(f"{name}: Opus fanout blocked ({opus_agents} Opus agents; max {max_opus_agents})")
    if fable_agents > max_fable_agents and os.environ.get("LIMEN_ALLOW_FABLE_FANOUT") != "1":
        violations.append(f"{name}: Fable fanout blocked ({fable_agents} Fable agents; max {max_fable_agents})")

    scan_parts = [
        wf.get("args"),
        wf.get("script"),
        wf.get("logs"),
        wf.get("result"),
        wf.get("error"),
    ]
    for p in progress:
        if isinstance(p, dict):
            scan_parts.extend(
                [
                    p.get("label"),
                    p.get("promptPreview"),
                    p.get("resultPreview"),
                    p.get("lastToolSummary"),
                ]
            )
    scan = "\n".join(_as_text(x) for x in scan_parts)
    fable_acceptance_ok = _structured_fable_acceptance(wf.get("fableAcceptance"))
    if fable_agents and not fable_acceptance_ok and os.environ.get("LIMEN_ALLOW_UNACCEPTED_FABLE") != "1":
        violations.append(f"{name}: Fable run lacks written acceptance command")
    if BAD_TARGET_RE.search(scan):
        violations.append(f"{name}: undefined PR target detected")

    args = wf.get("args")
    script = str(wf.get("script") or "")
    if isinstance(args, str):
        try:
            parsed = _json_loads_nested(args)
            normalize_candidates(parsed, allow_empty=True)
            candidate_like = True
        except Exception:
            candidate_like = False
        if candidate_like and "JSON.parse(args)" not in script and "typeof args === 'string'" not in script:
            violations.append(f"{name}: candidate args are a JSON string but script does not parse args")

    states = [str(p.get("state", "")) for p in progress if isinstance(p, dict)]
    if wf.get("status") == "completed" and any(s == "error" for s in states):
        violations.append(f"{name}: completed workflow contains errored agents")
    logs_text = _as_text(wf.get("logs"))
    result_text = _as_text(wf.get("result"))
    if wf.get("status") == "completed" and (
        FAILED_LOG_RE.search(logs_text) or re.search(r"agent died", result_text, re.IGNORECASE)
    ):
        violations.append(f"{name}: completed workflow contains failure/dead-agent evidence")

    return violations


def audit_workflow(
    path: Path,
    *,
    max_opus_agents: int,
    max_fable_agents: int,
    live_merged: bool = False,
) -> dict[str, Any]:
    wf = json.loads(path.read_text())
    violations = _workflow_violations(
        path,
        wf,
        max_opus_agents=max_opus_agents,
        max_fable_agents=max_fable_agents,
    )
    live = None
    if live_merged:
        live = verify_claimed_merged(wf)
        if live["bad"]:
            violations.append(f"{path.name}: live merged verification failed for {len(live['bad'])} PRs")
    return {
        "path": str(path),
        "workflowName": wf.get("workflowName"),
        "status": wf.get("status"),
        "agentCount": wf.get("agentCount", 0),
        "totalTokens": wf.get("totalTokens", 0),
        "violations": violations,
        "liveMerged": live,
    }


def _find_session_dir(session: str) -> Path:
    root = Path.home() / ".claude" / "projects"
    matches = list(root.glob(f"*/{session}"))
    if not matches:
        raise FileNotFoundError(f"no Claude session directory found for {session}")
    return matches[0]


def _find_session_jsonl(session_or_path: str) -> Path:
    p = Path(session_or_path).expanduser()
    if p.exists():
        return p
    root = Path.home() / ".claude" / "projects"
    matches = list(root.glob(f"*/{session_or_path}.jsonl"))
    if not matches:
        raise FileNotFoundError(f"no Claude transcript found for {session_or_path}")
    return matches[0]


def _iter_jsonl(path: Path):
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return
    for line_no, line in enumerate(lines, start=1):
        try:
            yield line_no, json.loads(line)
        except Exception:
            continue


def _billable_usage(usage: dict[str, Any]) -> int:
    return (
        int(usage.get("input_tokens", 0))
        + int(usage.get("output_tokens", 0))
        + int(usage.get("cache_creation_input_tokens", 0))
    )


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return _as_text(content)
    out: list[str] = []
    for item in content:
        if isinstance(item, dict):
            if item.get("type") == "text":
                out.append(str(item.get("text", "")))
            elif item.get("type") == "tool_use":
                out.append(str(item.get("name", "")))
        elif isinstance(item, str):
            out.append(item)
    return "\n".join(out)


def audit_transcript(
    session_or_path: str,
    *,
    max_billable_tokens: int,
    max_opus_billable_tokens: int,
    max_fable_billable_tokens: int,
    max_agent_calls: int,
    max_opus_agents: int,
    max_fable_agents: int,
) -> dict[str, Any]:
    """Audit a Claude transcript for unbounded, expensive session shape.

    This intentionally ignores cache-read tokens for the budget gate; it counts the
    billable-ish part Claude exposes in transcripts: input + output + cache creation.
    """
    main = _find_session_jsonl(session_or_path)
    session_id = main.stem
    files = [main]
    subagents = main.with_suffix("") / "subagents"
    if subagents.exists():
        files.extend(sorted(p for p in subagents.rglob("*.jsonl") if p.is_file()))

    total_billable = 0
    cache_read_tokens = 0
    output_tokens = 0
    usage_messages = 0
    agent_calls = 0
    opus_billable = 0
    fable_billable = 0
    user_unbounded: list[dict[str, Any]] = []
    full_suite_pytest: list[dict[str, Any]] = []
    models: dict[str, int] = {}
    # A fan-out of subagents each riding the expensive tier is the exact shape of the
    # verify-studio-launch incident (6 trivial verifiers on Opus). Count subagent transcripts
    # (files[1:], never the main session) that ran ANY assistant turn on the costliest rung.
    subagent_paths = {str(p) for p in files[1:]}
    expensive_subagent_files: set[str] = set()
    fable_subagent_files: set[str] = set()
    fable_acceptance_seen = _current_fable_acceptance_present()

    unbounded_re = re.compile(
        r"\b(no stopping|indefinite|indefinitely|until ideal form|keep going until ideal form)\b",
        re.IGNORECASE,
    )

    for path in files:
        for line_no, row in _iter_jsonl(path):
            msg = row.get("message") or {}
            if _structured_fable_acceptance(row.get("fableAcceptance")) or (
                isinstance(msg, dict) and _structured_fable_acceptance(msg.get("fableAcceptance"))
            ):
                fable_acceptance_seen = True
            if row.get("type") == "user":
                text = _content_text(msg.get("content"))
                if unbounded_re.search(text):
                    user_unbounded.append(
                        {
                            "path": str(path),
                            "line": line_no,
                            "textSha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
                            "chars": len(text),
                        }
                    )
            if row.get("type") != "assistant":
                continue
            model = str(msg.get("model") or "unknown")
            if str(path) in subagent_paths and _EXPENSIVE in model.lower():
                expensive_subagent_files.add(str(path))
            if str(path) in subagent_paths and _FABLE in model.lower():
                fable_subagent_files.add(str(path))
            content = msg.get("content") or []
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict) or item.get("type") != "tool_use":
                        continue
                    if item.get("name") in {"Agent", "Workflow"}:
                        agent_calls += 1
                    elif item.get("name") == "Bash":
                        bash_cmd = str((item.get("input") or {}).get("command") or "")
                        if _full_suite_pytest(bash_cmd):
                            full_suite_pytest.append({"path": str(path), "line": line_no, "command": bash_cmd[:200]})
            usage = msg.get("usage") or {}
            if not usage:
                continue
            usage_messages += 1
            billable = _billable_usage(usage)
            total_billable += billable
            cache_read_tokens += int(usage.get("cache_read_input_tokens", 0))
            output_tokens += int(usage.get("output_tokens", 0))
            models[model] = models.get(model, 0) + billable
            if _EXPENSIVE in model.lower():
                opus_billable += billable
            if _FABLE in model.lower():
                fable_billable += billable

    violations: list[str] = []
    if total_billable > max_billable_tokens and os.environ.get("LIMEN_ALLOW_EXPENSIVE_SESSION") != "1":
        violations.append(f"billable token budget exceeded ({total_billable} > {max_billable_tokens})")
    if opus_billable > max_opus_billable_tokens and os.environ.get("LIMEN_ALLOW_OPUS_SESSION_BURN") != "1":
        violations.append(f"Opus billable budget exceeded ({opus_billable} > {max_opus_billable_tokens})")
    if fable_billable > max_fable_billable_tokens and os.environ.get("LIMEN_ALLOW_FABLE_SESSION_BURN") != "1":
        violations.append(f"Fable billable budget exceeded ({fable_billable} > {max_fable_billable_tokens})")
    if agent_calls > max_agent_calls and os.environ.get("LIMEN_ALLOW_AGENT_FANOUT") != "1":
        violations.append(f"agent/workflow fanout exceeded ({agent_calls} > {max_agent_calls})")
    expensive_subagents = len(expensive_subagent_files)
    if expensive_subagents > max_opus_agents and os.environ.get("LIMEN_ALLOW_OPUS_FANOUT") != "1":
        violations.append(
            f"{_EXPENSIVE} subagent fanout ({expensive_subagents} subagents on {_EXPENSIVE}; "
            f"max {max_opus_agents}) — tier each fan-out agent by job, don't inherit the session model"
        )
    fable_subagents = len(fable_subagent_files)
    if fable_subagents > max_fable_agents and os.environ.get("LIMEN_ALLOW_FABLE_FANOUT") != "1":
        violations.append(f"Fable subagent fanout ({fable_subagents} subagents on {_FABLE}; max {max_fable_agents})")
    if fable_billable and not fable_acceptance_seen and os.environ.get("LIMEN_ALLOW_UNACCEPTED_FABLE") != "1":
        violations.append("Fable run lacks written acceptance command")
    if user_unbounded and os.environ.get("LIMEN_ALLOW_UNBOUNDED_GOAL") != "1":
        violations.append(f"unbounded goal phrase detected ({len(user_unbounded)} occurrence(s))")
    if full_suite_pytest and os.environ.get("LIMEN_ALLOW_FULL_PYTEST") != "1":
        violations.append(
            f"full-suite pytest invoked directly ({len(full_suite_pytest)} call(s)) — "
            "scoped-verification law: run scripts/verify-scoped.sh "
            "(2026-07-15 host-thrash incident; the PreToolUse hook is the gate, this audit is the backstop)"
        )

    return {
        "ok": not violations,
        "session": session_id,
        "files": [str(p) for p in files],
        "usageMessages": usage_messages,
        "billableTokens": total_billable,
        "cacheReadTokens": cache_read_tokens,
        "outputTokens": output_tokens,
        "opusBillableTokens": opus_billable,
        "fableBillableTokens": fable_billable,
        "agentCalls": agent_calls,
        "expensiveSubagents": expensive_subagents,
        "fableSubagents": fable_subagents,
        "fableAcceptanceSeen": fable_acceptance_seen,
        "expensiveTier": _EXPENSIVE,
        "fableTier": _FABLE,
        "modelsBillable": models,
        "unboundedGoalEvidence": user_unbounded[:10],
        "fullSuitePytestCalls": len(full_suite_pytest),
        "fullSuitePytestEvidence": full_suite_pytest[:10],
        "violations": violations,
    }


def verify_claimed_merged(wf: dict[str, Any]) -> dict[str, Any]:
    merged = (wf.get("result") or {}).get("merged") or []
    ok: list[dict[str, Any]] = []
    bad: list[dict[str, Any]] = []
    for item in merged:
        repo = item.get("repo")
        num = item.get("number")
        if not repo or not num:
            bad.append({"repo": repo, "number": num, "state": "invalid"})
            continue
        proc = subprocess.run(
            ["gh", "pr", "view", str(num), "-R", str(repo), "--json", "state,mergedAt"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            bad.append({"repo": repo, "number": num, "state": "gh-error", "error": proc.stderr[:200]})
            continue
        data = json.loads(proc.stdout)
        state = "MERGED" if data.get("mergedAt") else data.get("state")
        target = {"repo": repo, "number": num, "state": state}
        (ok if state == "MERGED" else bad).append(target)
    return {"checked": len(merged), "ok": ok, "bad": bad}


def _emit(report: Any, out: str | None) -> None:
    text = json.dumps(report, indent=2, sort_keys=True)
    if out:
        Path(out).write_text(text + "\n")
    print(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    norm = sub.add_parser("normalize-candidates")
    norm.add_argument("input", nargs="?", default="-")
    norm.add_argument("--allow-empty", action="store_true")
    norm.add_argument("--out")

    aw = sub.add_parser("audit-workflow")
    aw.add_argument("workflow", nargs="+")
    aw.add_argument("--max-opus-agents", type=int, default=1)
    aw.add_argument("--max-fable-agents", type=int, default=1)
    aw.add_argument("--live-merged", action="store_true")
    aw.add_argument("--out")

    ases = sub.add_parser("audit-session")
    ases.add_argument("session")
    ases.add_argument("--max-opus-agents", type=int, default=1)
    ases.add_argument("--max-fable-agents", type=int, default=1)
    ases.add_argument("--live-merged", action="store_true")
    ases.add_argument("--out")

    at = sub.add_parser("audit-transcript")
    at.add_argument("session_or_jsonl")
    at.add_argument(
        "--max-billable-tokens", type=int, default=int(os.environ.get("LIMEN_MAX_CLAUDE_SESSION_TOKENS", "2000000"))
    )
    at.add_argument(
        "--max-opus-billable-tokens", type=int, default=int(os.environ.get("LIMEN_MAX_OPUS_SESSION_TOKENS", "750000"))
    )
    at.add_argument(
        "--max-fable-billable-tokens",
        type=int,
        default=int(os.environ.get("LIMEN_MAX_FABLE_SESSION_TOKENS", "1000000")),
    )
    at.add_argument("--max-agent-calls", type=int, default=int(os.environ.get("LIMEN_MAX_AGENT_CALLS", "8")))
    at.add_argument("--max-opus-agents", type=int, default=1)
    at.add_argument("--max-fable-agents", type=int, default=1)
    at.add_argument("--out")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "normalize-candidates":
            candidates = normalize_candidates(
                _json_loads_nested(_read_text(args.input)),
                allow_empty=args.allow_empty,
            )
            _emit(candidates, args.out)
            return 0

        if args.cmd == "audit-workflow":
            reports = [
                audit_workflow(
                    Path(p),
                    max_opus_agents=args.max_opus_agents,
                    max_fable_agents=args.max_fable_agents,
                    live_merged=args.live_merged,
                )
                for p in args.workflow
            ]
        elif args.cmd == "audit-session":
            session_dir = _find_session_dir(args.session)
            reports = [
                audit_workflow(
                    p,
                    max_opus_agents=args.max_opus_agents,
                    max_fable_agents=args.max_fable_agents,
                    live_merged=args.live_merged,
                )
                for p in sorted((session_dir / "workflows").glob("*.json"))
            ]
            summary = {
                "ok": not any(r["violations"] for r in reports),
                "workflowCount": len(reports),
                "reports": reports,
            }
            _emit(summary, args.out)
            return 0 if summary["ok"] else 2

        if args.cmd == "audit-transcript":
            report = audit_transcript(
                args.session_or_jsonl,
                max_billable_tokens=args.max_billable_tokens,
                max_opus_billable_tokens=args.max_opus_billable_tokens,
                max_fable_billable_tokens=args.max_fable_billable_tokens,
                max_agent_calls=args.max_agent_calls,
                max_opus_agents=args.max_opus_agents,
                max_fable_agents=args.max_fable_agents,
            )
            _emit(report, args.out)
            return 0 if report["ok"] else 2

        summary = {
            "ok": not any(r["violations"] for r in reports),
            "workflowCount": len(reports),
            "reports": reports,
        }
        _emit(summary, args.out)
        return 0 if summary["ok"] else 2
    except Exception as e:
        print(f"claude-workflow-guard: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
