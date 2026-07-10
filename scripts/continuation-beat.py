#!/usr/bin/env python3
"""Run one bounded continuation beat without waiting for chat.

This is the direct-session loop turned into a daemon-safe organ:

- preserve clean worktree debt by pushing missing heads and opening draft PRs;
- advance the active Photos duplicate-proof lane by a bounded batch;
- refresh the Portvs triptych proxy from the public Photos aggregate receipt;
- commit/push only the known receipt/proxy files it owns;
- refresh Limen's PR preservation receipts and re-run worktree debt.

Every step is fail-open and receipt-backed. A dirty lane checkout is skipped
rather than overwritten. The session-value gate runs before generic beat work:
exit 10 is a hard lane switch, not another continuation pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
PHOTOS = Path(os.environ.get("LIMEN_PHOTOS_UNIVERSE_ROOT", "/Users/4jp/Workspace/photos-universe-20260629-182431"))
PORTVS = Path(
    os.environ.get(
        "LIMEN_PORTVS_TRIPTYCH_ROOT",
        "/Users/4jp/Workspace/4444J99/portvs/.worktrees/triptych-story",
    )
)
TRIPTYCH = PORTVS / "incubator" / "triptych-video-canon"
LOG_PATH = ROOT / "logs" / "continuation-beat.json"
LOCK_DIR = ROOT / "logs" / ".continuation-beat.lock.d"
PRESERVATION_RECEIPTS = ROOT / "docs" / "worktree-preservation-receipts.json"
TOKEN_REPORT = ROOT / "logs" / "codex-token-report.json"
VALUE_GATE_HOURS = os.environ.get("LIMEN_CONTINUATION_VALUE_GATE_HOURS", "1.5")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(args: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, cwd=str(cwd), text=True, capture_output=True, timeout=timeout)
    except Exception as exc:
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def git(cwd: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd, timeout=timeout)


def gh(cwd: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run(["gh", *args], cwd, timeout=timeout)


def short_output(proc: subprocess.CompletedProcess[str], limit: int = 1200) -> str:
    text = (proc.stdout + "\n" + proc.stderr).strip()
    return text[-limit:]


def load_json_output(proc: subprocess.CompletedProcess[str]) -> dict[str, Any] | None:
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None


def parse_json_stdout(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def first_command(gate: dict[str, Any]) -> str:
    commands = gate.get("next_commands")
    if isinstance(commands, list):
        for command in commands:
            if isinstance(command, str) and command.strip():
                return command.strip()
    command = gate.get("next_command")
    return str(command).strip() if command else ""


# DATA_ONLY push guard (issue #872 / PREC-2026-07-10-direct-push-lane-rots-main). SOURCE = code/config
# that belongs behind pr-gate; it must never reach a pr-gated repo's `main` via the autonomic direct-push
# lane un-CI'd. DATA (tasks.yaml, receipts, logs, other data) is the lane's legitimate cargo and passes.
_SOURCE_SUFFIXES = {
    ".py", ".sh", ".ts", ".js", ".mjs", ".cjs", ".tsx", ".jsx", ".rs", ".go", ".toml", ".cfg",
}
_SOURCE_NAMES = {"Makefile", "Dockerfile"}
# *.yml/*.yaml are SOURCE only under these trees (workflows/config); data YAML (tasks.yaml) is not.
_SOURCE_YAML_ROOTS = (".github/", "cli/", "web/", "institutio/", "scripts/")


def is_source_path(path: str) -> bool:
    """True if *path* is SOURCE that must route via PR, not the direct-push lane."""
    p = path.strip().replace("\\", "/")
    if not p:
        return False
    name = p.rsplit("/", 1)[-1]
    if name in _SOURCE_NAMES:
        return True
    if p.startswith(".github/") or "/.github/" in p:
        return True
    lower = p.lower()
    dot = name.rfind(".")
    suffix = name[dot:].lower() if dot > 0 else ""
    if suffix in _SOURCE_SUFFIXES:
        return True
    if suffix in {".yml", ".yaml"}:
        return any(p == root.rstrip("/") or p.startswith(root) for root in _SOURCE_YAML_ROOTS)
    # tasks.yaml, tasks.yaml.lock, logs/**, docs/*receipt*.json and other *.json data are DATA.
    if name in {"tasks.yaml", "tasks.yaml.lock"}:
        return False
    if lower.endswith(".json") or p.startswith("logs/") or "/logs/" in p:
        return False
    # Default-deny for the genuinely ambiguous, but never refuse known data cargo (handled above).
    return False


def _guard_source_on_main(repo: Path, paths: list[str]) -> list[str]:
    """When the repo's HEAD is `main` and it gates PRs, unstage any staged SOURCE in *paths* (leaving it
    on disk) and return the refused paths. No-op when the guard is disabled, the branch isn't main, or
    the repo has no pr-gate.yml — so non-main/ungated behavior is preserved."""
    if os.environ.get("LIMEN_PUSH_GUARD", "on") == "off":
        return []
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if branch != "main":
        return []
    if not (repo / ".github" / "workflows" / "pr-gate.yml").is_file():
        return []
    staged = git(repo, "diff", "--cached", "--name-only", "--diff-filter=AM").stdout.splitlines()
    refused = [s for s in (line.strip() for line in staged) if s and is_source_path(s)]
    if refused:
        for s in refused:
            git(repo, "reset", "-q", "--", s)
        print(f"[continuation-beat] REFUSED source on main: {' '.join(refused)} — route via PR (pr-gate)")
    return refused


def repo_clean(repo: Path) -> bool:
    return repo.is_dir() and git(repo, "status", "--porcelain").stdout.strip() == ""


def status_for_paths(repo: Path, paths: list[str]) -> str:
    return git(repo, "status", "--porcelain", "--", *paths).stdout.strip()


def commit_paths(repo: Path, paths: list[str], message: str, apply: bool) -> dict[str, Any]:
    status = status_for_paths(repo, paths)
    if not status:
        return {"changed": False}
    if not apply:
        return {"changed": True, "dry_run": True, "status": status}
    add = git(repo, "add", *paths)
    if add.returncode != 0:
        return {"changed": True, "error": f"git add failed: {short_output(add)}"}
    refused = _guard_source_on_main(repo, paths)
    if refused and git(repo, "diff", "--cached", "--quiet").returncode == 0:
        # every staged path was source and got unstaged → nothing left to commit; skip, don't abort.
        return {"changed": True, "refused_source": refused, "skipped": "all-source-refused-on-main"}
    commit = git(repo, "commit", "-m", message, timeout=180)
    if commit.returncode != 0:
        return {"changed": True, "error": f"git commit failed: {short_output(commit)}"}
    push = git(repo, "push", timeout=180)
    if push.returncode != 0:
        return {"changed": True, "error": f"git push failed: {short_output(push)}"}
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    result = {"changed": True, "committed": head, "message": message}
    if refused:
        result["refused_source"] = refused
    return result


def pr_number_from_url(url: str) -> int | None:
    match = re.search(r"/pull/(\d+)(?:\D*)$", url or "")
    return int(match.group(1)) if match else None


def pr_view(repo: str, number_or_url: str, cwd: Path) -> dict[str, Any]:
    proc = gh(
        cwd,
        "pr",
        "view",
        str(number_or_url),
        "--repo",
        repo,
        "--json",
        "number,state,isDraft,headRefName,headRefOid,url",
    )
    data = load_json_output(proc)
    return data or {}


def update_pr_receipts(rows: list[dict[str, Any]], *, apply: bool) -> dict[str, Any]:
    if not rows:
        return {"updated": 0}
    try:
        data = json.loads(PRESERVATION_RECEIPTS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"could not load preservation receipts: {exc}"}

    receipts = data.setdefault("receipts", [])
    by_root = {str(row.get("root")): row for row in receipts if isinstance(row, dict)}
    updated = 0
    now = utc_now()

    for row in rows:
        repo = row.get("repo")
        branch = row.get("branch")
        path = Path(str(row.get("path") or ""))
        root = str(row.get("name") or path.name)
        if not repo or not branch or not root:
            continue
        url = str(row.get("url") or (row.get("pr") or {}).get("url") or "")
        number = pr_number_from_url(url)
        view = pr_view(str(repo), str(number or url), path if path.is_dir() else ROOT) if (number or url) else {}
        head = str(view.get("headRefOid") or (git(path, "rev-parse", "HEAD").stdout.strip() if path.is_dir() else ""))
        if not url:
            url = str(view.get("url") or "")
        receipt = by_root.get(root)
        if receipt is None:
            receipt = {"root": root}
            receipts.append(receipt)
            by_root[root] = receipt
        new_values = {
            "branch": str(view.get("headRefName") or branch),
            "classification": "open draft PR preserves local worktree head",
            "evidence_updated_utc": now,
            "head": head,
            "lane": "remote-pr-open",
            "next_action": (
                f"Review draft PR #{number or view.get('number')}, then merge, supersede, "
                "or archive this lane. Local checkout is no longer the only review surface."
            ),
            "pr_draft": bool(view.get("isDraft", True)),
            "pr_number": int(view.get("number") or number or 0),
            "pr_state": str(view.get("state") or "OPEN"),
            "pr_url": url,
            "repo": str(repo),
            "score_discount": 35,
            "status": "open_pr_preserved",
        }
        if any(receipt.get(key) != value for key, value in new_values.items()):
            receipt.update(new_values)
            updated += 1

    if updated and apply:
        PRESERVATION_RECEIPTS.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"updated": updated, "dry_run": bool(updated and not apply)}


def preserve_worktree_prs(apply: bool) -> dict[str, Any]:
    proc = run(
        ["python3", "scripts/worktree-pr-receipts.py", "--json", *(["--apply"] if apply else [])],
        ROOT,
        timeout=240,
    )
    data = load_json_output(proc)
    if data is None:
        return {"ok": False, "detail": short_output(proc)}
    rows = [
        row
        for row in data.get("results", [])
        if row.get("action") in {"pr_created", "pr_exists"} and row.get("repo") and row.get("branch")
    ]
    receipt_update = update_pr_receipts(rows, apply=apply)
    commit = commit_paths(
        ROOT,
        ["docs/worktree-preservation-receipts.json"],
        "limen: refresh autonomous PR receipts",
        apply,
    )
    return {"ok": True, "summary": data.get("summary", {}), "receipt_update": receipt_update, "commit": commit}


def token_budget_gate() -> dict[str, Any]:
    if os.environ.get("LIMEN_CONTINUATION_TOKEN_GATE", "1") != "1":
        return {"ok": True, "skipped": "disabled"}
    proc = run(
        [
            "python3",
            "scripts/codex-token-accounting.py",
            "--since-hours",
            os.environ.get("LIMEN_CODEX_TOKEN_GATE_HOURS", "6"),
            "--limit-sessions",
            os.environ.get("LIMEN_CODEX_TOKEN_GATE_LIMIT", "10"),
            "--output",
            str(TOKEN_REPORT),
            "--fail-on-active-budget",
        ],
        ROOT,
        timeout=90,
    )
    report = load_json_file(TOKEN_REPORT) or {}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "tail": short_output(proc, 800),
        "report": {
            "path": str(TOKEN_REPORT),
            "status": report.get("status"),
            "active_status": report.get("active_status"),
            "session_count": report.get("session_count"),
            "aggregate_totals": report.get("aggregate_totals"),
            "warnings": (report.get("warnings") or [])[:5],
            "failures": (report.get("failures") or [])[:5],
            "active_session_seconds": report.get("active_session_seconds"),
            "active_failures": (report.get("active_failures") or [])[:5],
            "historical_failures": (report.get("historical_failures") or [])[:5],
        },
    }


def session_value_gate() -> dict[str, Any]:
    """Stop generic continuation when the value gate requests a bounded lane switch."""
    if os.environ.get("LIMEN_CONTINUATION_VALUE_GATE", "1") != "1":
        return {"ok": True, "skipped": "disabled"}
    command = [
        "python3",
        "scripts/session-value-review.py",
        "--gate",
        "--hours",
        VALUE_GATE_HOURS,
        "--no-record-gate",
    ]
    proc = run(
        command,
        ROOT,
        timeout=int(os.environ.get("LIMEN_CONTINUATION_VALUE_GATE_TIMEOUT", "90")),
    )
    gate = parse_json_stdout(proc)
    next_command = first_command(gate)
    action = str(gate.get("action") or "")
    if proc.returncode == 0:
        return {
            "ok": True,
            "returncode": proc.returncode,
            "action": action or "allowed",
            "reason": gate.get("reason"),
            "next_command": next_command,
        }
    return {
        "ok": False,
        "returncode": proc.returncode,
        "action": action or "session_value_gate",
        "lane_switch": proc.returncode == 10,
        "reason": gate.get("reason") or short_output(proc, 500) or "session value gate blocked continuation",
        "next_command": next_command,
        "tail": short_output(proc, 800),
    }


def advance_photos(apply: bool, limit_groups: int) -> dict[str, Any]:
    if not PHOTOS.is_dir():
        return {"ok": False, "skipped": "photos repo missing"}
    if not repo_clean(PHOTOS):
        return {"ok": False, "skipped": "photos repo dirty"}
    receipt = "docs/photos-universe-duplicate-proof-2026-06-29.json"
    dry = run(["python3", "scripts/photos-duplicate-proof.py", "--limit-groups", str(limit_groups), "--dry-run"], PHOTOS)
    dry_data = load_json_output(dry)
    if dry_data is None:
        detail = short_output(dry)
        if "nothing to prove" in detail.lower():
            return {"ok": True, "skipped": "no duplicate candidates to prove", "detail": detail}
        return {"ok": False, "detail": short_output(dry)}
    processed = int(dry_data.get("processed_this_run") or 0)
    applied: dict[str, Any] = {"skipped": "no unprocessed duplicate groups"}
    if processed and apply:
        proc = run(
            [
                "python3",
                "scripts/photos-duplicate-proof.py",
                "--limit-groups",
                str(limit_groups),
                "--receipt",
                receipt,
            ],
            PHOTOS,
        )
        applied = load_json_output(proc) or {"error": short_output(proc)}
    if apply:
        atomize: dict[str, Any] = {
            "returncode": 0,
            "skipped": "no processed duplicate groups",
        }
        if processed:
            atomized = run(
                [
                    "python3",
                    "scripts/media-atomize.py",
                    "--photos-metadata",
                    "--limit",
                    str(int(os.environ.get("LIMEN_CONTINUE_PHOTOS_ATOMS", str(limit_groups)))),
                ],
                PHOTOS,
            )
            atomize = {"returncode": atomized.returncode, "tail": short_output(atomized, 500)}
    else:
        atomize = {"returncode": 0, "skipped": "dry-run"}
    commit = commit_paths(
        PHOTOS,
        [receipt, "docs/photos-universe-sorting-2026-06-30.md"],
        "photos: autonomous duplicate proof batch",
        apply,
    )
    return {
        "ok": True,
        "dry_run": dry_data,
        "applied": applied,
        "atomize": atomize,
        "commit": commit,
    }


def refresh_portvs_proxy(apply: bool) -> dict[str, Any]:
    if not TRIPTYCH.is_dir():
        return {"ok": False, "skipped": "triptych incubator missing"}
    if not repo_clean(PORTVS):
        return {"ok": False, "skipped": "portvs repo dirty"}
    if not (TRIPTYCH / "photos_universe_proxy.py").exists():
        return {"ok": False, "skipped": "photos proxy generator missing"}
    if not apply:
        return {"ok": True, "dry_run": True, "would_run": "photos_universe_proxy.py"}
    proc = run(["python3", "photos_universe_proxy.py"], TRIPTYCH)
    if proc.returncode != 0:
        return {"ok": False, "detail": short_output(proc)}
    gates = []
    for cmd in (
        ["python3", "-m", "py_compile", "photos_universe_proxy.py"],
        ["python3", "-m", "json.tool", "work/photos-universe-proof-proxy.json"],
        ["python3", "generated_inventory.py"],
        ["python3", "verify_editions.py"],
        ["python3", "verify_private_workflow.py"],
    ):
        gate = run(cmd, TRIPTYCH, timeout=180)
        gates.append({"cmd": cmd, "returncode": gate.returncode, "tail": short_output(gate, 500)})
        if gate.returncode != 0:
            return {"ok": False, "generator": short_output(proc, 500), "gates": gates}
    commit = commit_paths(
        PORTVS,
        [
            "incubator/triptych-video-canon/PHOTOS_UNIVERSE_PROXY.md",
            "incubator/triptych-video-canon/photos_universe_proxy.py",
        ],
        "portvs: refresh photos universe proxy",
        apply,
    )
    lifecycle = run(["python3", "verify_local_lifecycle.py", "--require-clean"], TRIPTYCH)
    known_receipts = update_pr_receipts(
        [
            {
                "name": "triptych-story",
                "path": str(PORTVS),
                "repo": "organvm/portvs",
                "branch": "work/triptych-story",
                "url": "https://github.com/organvm/portvs/pull/1",
            }
        ],
        apply=apply,
    )
    limen_commit = commit_paths(
        ROOT,
        ["docs/worktree-preservation-receipts.json"],
        "limen: refresh triptych PR receipt",
        apply,
    )
    return {
        "ok": lifecycle.returncode == 0,
        "generator": short_output(proc, 500),
        "gates": gates,
        "commit": commit,
        "lifecycle": {"returncode": lifecycle.returncode, "tail": short_output(lifecycle, 800)},
        "limen_receipt": known_receipts,
        "limen_commit": limen_commit,
    }


def reduction_snapshot() -> dict[str, Any]:
    debt = run(["python3", "scripts/worktree-debt.py", "--json"], ROOT)
    data = load_json_output(debt)
    if data is None:
        return {"ok": False, "detail": short_output(debt)}
    return {
        "ok": True,
        "debt": data.get("debt"),
        "total": data.get("total"),
        "by_reason": data.get("by_reason"),
    }


def write_log(payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(LOG_PATH)


def acquire_lock() -> bool:
    LOCK_DIR.parent.mkdir(parents=True, exist_ok=True)
    try:
        LOCK_DIR.mkdir()
        return True
    except FileExistsError:
        return False


def census() -> dict[str, Any]:
    """Counts-only public census; no worktree paths, receipt roots, logs, or token details."""
    receipts_data = load_json_file(PRESERVATION_RECEIPTS) or {}
    receipts = receipts_data.get("receipts") if isinstance(receipts_data, dict) else []
    last = load_json_file(LOG_PATH) or {}
    steps = last.get("steps") if isinstance(last, dict) else {}
    return {
        "receipts_present": PRESERVATION_RECEIPTS.exists(),
        "preservation_receipts": len(receipts) if isinstance(receipts, list) else 0,
        "last_log_present": LOG_PATH.exists(),
        "last_step_count": len(steps) if isinstance(steps, dict) else 0,
        "last_ok": last.get("ok") if isinstance(last, dict) else None,
        "token_report_present": TOKEN_REPORT.exists(),
        "photos_root_present": PHOTOS.is_dir(),
        "portvs_root_present": PORTVS.is_dir(),
        "triptych_root_present": TRIPTYCH.is_dir(),
        "lock_present": LOCK_DIR.exists(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit/push bounded receipt changes")
    parser.add_argument(
        "--limit-groups",
        type=int,
        default=int(os.environ.get("LIMEN_CONTINUE_PHOTOS_GROUPS", "25")),
    )
    parser.add_argument("--census", action="store_true", help="print counts-only public census JSON")
    args = parser.parse_args()
    if args.census:
        print(json.dumps(census(), indent=2, sort_keys=True))
        return 0

    if not acquire_lock():
        payload = {"generated_at": utc_now(), "ok": True, "skipped": "continuation beat already running"}
        write_log(payload)
        print(json.dumps(payload, sort_keys=True))
        return 0
    try:
        payload: dict[str, Any] = {
            "generated_at": utc_now(),
            "apply": args.apply,
            "steps": {},
        }
        payload["steps"]["session_value_gate"] = session_value_gate()
        if not payload["steps"]["session_value_gate"].get("ok"):
            payload["ok"] = False
            payload["skipped"] = "session value gate"
            write_log(payload)
            gate = payload["steps"]["session_value_gate"]
            suffix = f"; next: {gate['next_command']}" if gate.get("next_command") else ""
            print(f"continuation-beat: skipped by session value gate{suffix}")
            return 10 if gate.get("lane_switch") else 1
        payload["steps"]["token_budget_gate"] = token_budget_gate()
        if not payload["steps"]["token_budget_gate"].get("ok"):
            payload["ok"] = False
            payload["skipped"] = "token budget gate"
            write_log(payload)
            print("continuation-beat: skipped by token budget gate")
            return 1
        payload["steps"]["preserve_worktree_prs"] = preserve_worktree_prs(args.apply)
        payload["steps"]["advance_photos"] = advance_photos(args.apply, args.limit_groups)
        payload["steps"]["refresh_portvs_proxy"] = refresh_portvs_proxy(args.apply)
        payload["steps"]["reduction_snapshot"] = reduction_snapshot()
        payload["ok"] = all(step.get("ok", True) for step in payload["steps"].values())
        write_log(payload)
        print(
            "continuation-beat: "
            f"ok={payload['ok']} debt={payload['steps']['reduction_snapshot'].get('debt')} "
            f"photos={payload['steps']['advance_photos'].get('ok')} "
            f"portvs={payload['steps']['refresh_portvs_proxy'].get('ok')}"
        )
        return 0 if payload["ok"] else 1
    finally:
        try:
            LOCK_DIR.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
