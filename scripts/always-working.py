#!/usr/bin/env python3
"""Reconcile user promises before dispatching more work.

This is the conductor's receipt-first gate. It does not assume a promise needs a
first run. For each standing workstream it first looks for existing local proof,
then classifies the state as done, assigned from existing work, needs assignment,
or blocked. Only unresolved work becomes a bounded packet.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "cli" / "src"))
from limen.worktree_debt import REAPABLE_REASONS  # noqa: E402

HOME = Path.home()
WORKSPACE = Path(os.environ.get("LIMEN_WORKSPACE_ROOT", HOME / "Workspace"))
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PRIVATE_INDEX = Path(
    os.environ.get("LIMEN_ALWAYS_WORKING_INDEX", PRIVATE_ROOT / "lifecycle" / "always-working.json")
)
DOC_PATH = Path(os.environ.get("LIMEN_ALWAYS_WORKING_DOC", ROOT / "docs" / "always-working.md"))

PROFILE_REPO = Path(os.environ.get("LIMEN_PROFILE_REPO", WORKSPACE / "organvm" / "4444J99"))
VISIBLE_PROFILE_REPO = os.environ.get("LIMEN_VISIBLE_PROFILE_REPO", "4444J99/4444J99")
CHECK_GITHUB_PROFILE = os.environ.get("LIMEN_CHECK_GITHUB_PROFILE", "1") != "0"
CORPVS_ROOT = Path(os.environ.get("LIMEN_CORPVS_ROOT", WORKSPACE / "organvm-corpvs-testamentvm"))
MAIL_INDEX = Path(
    os.environ.get(
        "LIMEN_MAIL_ENVELOPE_INDEX",
        HOME / "Library" / "Mail" / "V10" / "MailData" / "Envelope Index",
    )
)
MAIL_STORY_LOG = Path(os.environ.get("LIMEN_MAIL_STORY_LOG", ROOT / "logs" / "mail-story-ledger.json"))

PROMPT_PACKET_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-packet-ledger.json"
REPO_SURFACE_INDEX = PRIVATE_ROOT / "lifecycle" / "repo-surface-ledger.json"
PRODUCT_LEDGER_INDEX = PRIVATE_ROOT / "lifecycle" / "product-ledger.json"
VALUE_REPOS = ROOT / "value-repos.json"
CONTRIBUTION_BALANCE_SCRIPT = ROOT / "scripts" / "github-contribution-balance.py"
CONTRIBUTION_BALANCE_LOGIN = os.environ.get("LIMEN_CONTRIBUTION_BALANCE_LOGIN", "4444J99")
CONTRIBUTION_BALANCE_POLICY = ROOT / "docs" / "github-contribution-balance.md"
CONTRIBUTION_BALANCE_OWNER_ISSUE = "https://github.com/organvm/limen/issues/687"
CONTRIBUTION_BALANCE_PUBLIC_ROOT = os.environ.get("LIMEN_CONTRIBUTION_BALANCE_PUBLIC_ROOT", "~/Workspace/limen")
CREDENTIAL_TOMBSTONE_DOC = ROOT / "docs" / "credential-token-tombstone-audit.md"
ARCHIVE4T_ROOT = Path(os.environ.get("LIMEN_ARCHIVE4T_ROOT", "/Volumes/Archive4T"))
INGRESS_ROOT = Path(os.environ.get("LIMEN_INGRESS_ROOT", "/Volumes/Ingress"))
SCRATCH_ROOT = Path(os.environ.get("LIMEN_SCRATCH_ROOT", "/Volumes/Scratch"))
T7RECOVERY_ROOT = Path(os.environ.get("LIMEN_T7RECOVERY_ROOT", "/Volumes/T7Recovery"))
T7_LIFEBOAT_ROOT = T7RECOVERY_ROOT / "CleanUnique-Lifeboat-2026-06-13"
ESTATE_CUSTODY_DOC = ROOT / "docs" / "estate-custody-primitives.md"
ESTATE_CUSTODY_RECEIPT = ROOT / "docs" / "estate-custody-implementation-receipts.json"
GENERATED_STATE_RECLAIM_LOG = ROOT / "logs" / "reclaim-generated-state.jsonl"
TOOL_CACHE_RECLAIM_LOG = ROOT / "logs" / "reclaim-tool-caches.jsonl"
OLLAMA_MODEL_RECLAIM_LOG = ROOT / "logs" / "reclaim-ollama-models.jsonl"
CVSTOS_STATE = ROOT / "logs" / "cvstos-organ-state.json"
LIFECYCLE_PRESSURE_STATE = ROOT / "logs" / "session-lifecycle-pressure.json"
OPENCODE_DB_INTAKE_DOC = ROOT / "docs" / "opencode-db-corpus-intake.md"
SUBSTRATE_STORAGE_INDEX = PRIVATE_ROOT / "lifecycle" / "substrate-storage-pressure.json"
WORKTREE_RECLAIM_CANDIDATES_DOC = ROOT / "docs" / "worktree-reclaim-candidates.md"
WORKTREE_RECLAIM_CANDIDATES_JSON = ROOT / "docs" / "worktree-reclaim-candidates.json"
STORAGE_OPERATING_MANUAL = ARCHIVE4T_ROOT / "_OPERATIONS" / "STORAGE-OPERATING-MANUAL-2026-06-15.md"
LOCAL_DISK_EXPULSION_POLICY = ARCHIVE4T_ROOT / "_OPERATIONS" / "LOCAL-DISK-EXPULSION-POLICY-2026-06-15.md"
PROFILE_POSITIONING_RE = re.compile(
    r"top[- ]tier|top\s+\d+(?:\.\d+)?%\s+engineering|top[- ]1%|top engineer|top engineers|world",
    re.I,
)

STATUS_DONE = "done_from_receipt"
STATUS_ASSIGNED = "assigned_from_existing_work"
STATUS_NEEDS = "needs_assignment"
STATUS_BLOCKED = "blocked"

REQUIRED_OPEN = {STATUS_ASSIGNED, STATUS_NEEDS}
AGENT_BY_WORKSTREAM = {
    "substrate": "codex",
    "estate-custody": "codex",
    "public-face": "codex",
    "contribution-balance": "codex",
    "credential-wall": "codex",
    "mail-active": "opencode",
    "mail-historical": "opencode",
    "repo-boil-up": "agy",
    "prompt-packets": "codex",
    "revenue-value-repos": "jules",
    "tabularius": "codex",
}

PRIORITY = {
    "substrate": 0,
    "estate-custody": 5,
    "public-face": 10,
    "contribution-balance": 15,
    "credential-wall": 18,
    "mail-active": 20,
    "mail-historical": 30,
    "repo-boil-up": 40,
    "prompt-packets": 50,
    "revenue-value-repos": 60,
    "tabularius": 70,
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        try:
            return str(path.resolve().relative_to(ROOT))
        except (OSError, ValueError):
            return str(path)


def contribution_balance_public_path(path: Path) -> str:
    try:
        rel = path.expanduser().resolve().relative_to(ROOT.resolve())
    except (OSError, ValueError):
        return relpath(path)
    root = CONTRIBUTION_BALANCE_PUBLIC_ROOT.rstrip("/")
    if str(rel) == ".":
        return root
    return f"{root}/{rel.as_posix()}"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, TypeError):
        return default


def load_last_jsonl(path: Path) -> dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return {}


def reclaim_log_summary(path: Path, extra_fields: tuple[str, ...]) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    total_kib = 0
    apply_events = 0
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        latest = data
        if data.get("apply") is True:
            apply_events += 1
            try:
                total_kib += int(data.get("total_reclaimed_kib") or data.get("reclaimed_kib") or 0)
            except (TypeError, ValueError):
                pass
    summary = {
        "present": bool(latest),
        "generated_at": latest.get("generated_at"),
        "apply": latest.get("apply"),
        "apply_events": apply_events,
        "latest_reclaimed_size": latest.get("total_reclaimed_size") or latest.get("reclaimed_size"),
        "latest_reclaimed_kib": latest.get("total_reclaimed_kib") or latest.get("reclaimed_kib"),
        "cumulative_reclaimed_kib": total_kib,
        "cumulative_reclaimed_size": fmt_kib(total_kib),
    }
    for field in extra_fields:
        summary[field] = latest.get(field)
    return summary


def fmt_kib(value: int) -> str:
    amount = float(value) * 1024
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} KiB"


def iso_age_hours(generated: Any) -> float | None:
    if not generated:
        return None
    try:
        generated_at = dt.datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=dt.timezone.utc)
        return round((dt.datetime.now(dt.timezone.utc) - generated_at).total_seconds() / 3600, 1)
    except ValueError:
        return None


def run_command(args: list[str], *, cwd: Path = ROOT, timeout: int = 30) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timed_out": True,
        }
    except OSError as exc:
        return {"returncode": None, "stdout": "", "stderr": str(exc), "timed_out": False}


def yaml_scalar(path: Path, key: str) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*:\s*(.+?)\s*(?:#.*)?$", text)
    if not match:
        return None
    return match.group(1).strip().strip('"').strip("'")


def readme_marker(text: str, key: str) -> str | None:
    match = re.search(rf"<!-- v:{re.escape(key)} -->(.*?)<!-- /v -->", text, re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


def _json_command(args: list[str], *, timeout: int = 20) -> tuple[dict[str, Any] | None, str]:
    result = run_command(args, timeout=timeout)
    if result["returncode"] != 0:
        return None, (result["stderr"] or result["stdout"] or "command failed").strip()[:500]
    try:
        return json.loads(result["stdout"] or "{}"), ""
    except ValueError as exc:
        return None, f"invalid JSON: {exc}"


def _decode_github_content(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    if payload.get("encoding") != "base64":
        return ""
    raw = str(payload.get("content") or "").replace("\n", "")
    if not raw:
        return ""
    try:
        return base64.b64decode(raw).decode("utf-8", errors="replace")
    except (ValueError, OSError):
        return ""


def github_profile_surface() -> dict[str, Any]:
    """Verify the public profile surface GitHub actually renders."""
    if not CHECK_GITHUB_PROFILE:
        return {"checked": False, "verified": False, "reason": "disabled"}
    repo, error = _json_command(
        [
            "gh",
            "api",
            f"repos/{VISIBLE_PROFILE_REPO}",
            "--jq",
            "{full_name,owner:.owner.login,visibility,default_branch,pushed_at,html_url}",
        ]
    )
    if error:
        return {"checked": True, "verified": False, "repo": VISIBLE_PROFILE_REPO, "error": error}
    branch = str((repo or {}).get("default_branch") or "main")
    readme_payload, readme_error = _json_command(
        [
            "gh",
            "api",
            f"repos/{VISIBLE_PROFILE_REPO}/contents/README.md?ref={branch}",
            "--jq",
            "{path,sha,encoding,content,html_url}",
        ]
    )
    readme_text = _decode_github_content(readme_payload)
    user, user_error = _json_command(
        ["gh", "api", "user", "--jq", "{bio,blog,public_repos,updated_at}"]
    )
    bio = str((user or {}).get("bio") or "")
    blog = str((user or {}).get("blog") or "")
    stale_bio = bool(re.search(r"\b91 repos\b|3,586 code files|736 test files|58 CI workflows", bio))
    stale_blog = "4444j99.github.io/portfolio" in blog
    return {
        "checked": True,
        "verified": bool(repo and readme_text),
        "repo": VISIBLE_PROFILE_REPO,
        "repo_full_name": (repo or {}).get("full_name"),
        "repo_owner": (repo or {}).get("owner"),
        "repo_visibility": (repo or {}).get("visibility"),
        "repo_pushed_at": (repo or {}).get("pushed_at"),
        "repo_html_url": (repo or {}).get("html_url"),
        "readme_present": bool(readme_text),
        "readme_sha": (readme_payload or {}).get("sha"),
        "readme_total_repos": readme_marker(readme_text, "total_repos"),
        "old_portfolio_link_count": readme_text.count("4444j99.github.io/portfolio"),
        "live_portfolio_link_count": readme_text.count("organvm.github.io/portfolio"),
        "top_engineer_claim_present": bool(PROFILE_POSITIONING_RE.search(readme_text)),
        "account_bio": bio,
        "account_blog": blog,
        "account_public_repos": (user or {}).get("public_repos"),
        "account_profile_stale": stale_bio or stale_blog,
        "account_profile_error": user_error,
        "readme_error": readme_error,
    }


def disk_receipt() -> dict[str, Any]:
    usage = shutil.disk_usage(HOME)
    tmp_ok = True
    tmp_error = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="limen-always-working-", delete=True) as handle:
            handle.write(b"ok")
            handle.flush()
    except OSError as exc:
        tmp_ok = False
        tmp_error = str(exc)
    free_gib = round(usage.free / 1024**3, 1)
    return {
        "free_gib": free_gib,
        "used_pct": round(usage.used / usage.total * 100, 1) if usage.total else None,
        "tmp_ok": tmp_ok,
        "tmp_error": tmp_error,
    }


def _short_command_receipt(args: list[str], *, timeout: int = 90) -> dict[str, Any]:
    result = run_command(args, timeout=timeout)
    text = (result.get("stderr") or result.get("stdout") or "").strip()
    return {
        "returncode": result.get("returncode"),
        "ok": result.get("returncode") == 0,
        "timed_out": bool(result.get("timed_out")),
        "summary": text[:500],
    }


def _cached_state(path: Path) -> tuple[dict[str, Any], float | None]:
    data = load_json(path, {})
    if not isinstance(data, dict):
        return {}, None
    try:
        age_seconds = max(0.0, dt.datetime.now().timestamp() - path.stat().st_mtime)
    except OSError:
        age_seconds = None
    return data, age_seconds


def _positive_env_int(name: str, default: int, *, allow_zero: bool = False) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    if value < 0 or (value == 0 and not allow_zero):
        return default
    return value


def _lifecycle_cache_windows() -> tuple[int, int]:
    """Return freshness bounds derived from the heartbeat's actual producer cadences."""
    loop_max = _positive_env_int("LIMEN_LOOP_MAX", 1800)
    producer_timeout = _positive_env_int("LIMEN_RECLAIM_TIMEOUT", 300)
    cvstos_cadence = _positive_env_int("LIMEN_BEAT_CVSTOS", 24)
    pressure_cadence = _positive_env_int("LIMEN_BEAT_DRAIN", 3)
    pressure_throttle = _positive_env_int(
        "LIMEN_LIFECYCLE_PRESSURE_THROTTLE", 1800, allow_zero=True
    )

    # A throttled producer can be called just before its snapshot becomes eligible, then wait one
    # full scheduler cadence before the next call. Include both intervals and the bounded command
    # runtime. CVSTOS is not internally throttled, so only its cadence and runtime apply.
    cvstos_window = cvstos_cadence * loop_max + producer_timeout
    pressure_window = pressure_throttle + pressure_cadence * loop_max + producer_timeout
    return cvstos_window, pressure_window


def substrate_lifecycle_receipt() -> dict[str, Any]:
    # This function runs before every dispatch reservation. Full CVSTOS + worktree classification
    # costs roughly two estate scans (>100s on the current host), so consume the heartbeat's cached,
    # counts-only receipts here. Exact classification remains in the assignment/closeout predicate.
    cvstos_state, cvstos_age = _cached_state(CVSTOS_STATE)
    pressure_state, pressure_age = _cached_state(LIFECYCLE_PRESSURE_STATE)
    worktrees_raw = pressure_state.get("worktrees")
    worktrees = worktrees_raw if isinstance(worktrees_raw, dict) else {}
    try:
        raw_debt = worktrees["debt"]
        debt = raw_debt if isinstance(raw_debt, int) and not isinstance(raw_debt, bool) and raw_debt >= 0 else None
    except (TypeError, ValueError):
        debt = None
    except KeyError:
        debt = None
    by_reason_raw = worktrees.get("by_reason")
    by_reason = by_reason_raw if isinstance(by_reason_raw, dict) else None
    reapable_by_reason: dict[str, int] = {}
    if by_reason is not None:
        for reason in REAPABLE_REASONS:
            raw_count = by_reason.get(reason, 0)
            if not isinstance(raw_count, int) or isinstance(raw_count, bool) or raw_count < 0:
                reapable_by_reason = {}
                reapable = None
                break
            reapable_by_reason[reason] = raw_count
        else:
            reapable = sum(reapable_by_reason.values())
    else:
        reapable = None
    pressure_error = worktrees.get("error")
    pressure_complete = worktrees.get("complete")
    pressure_valid = bool(
        isinstance(worktrees_raw, dict)
        and debt is not None
        and isinstance(by_reason_raw, dict)
        and isinstance(pressure_error, str)
        and isinstance(pressure_complete, bool)
        and pressure_complete == (debt == 0)
    )
    cvstos_at_factory = cvstos_state.get("at_factory")
    cvstos_open_invariants = cvstos_state.get("open_invariants")
    cvstos_worktree_has_debt = cvstos_state.get("worktree_has_debt")
    cvstos_valid = bool(
        isinstance(cvstos_at_factory, bool)
        and isinstance(cvstos_open_invariants, list)
        and isinstance(cvstos_worktree_has_debt, bool)
        and cvstos_at_factory == (len(cvstos_open_invariants) == 0)
        and (not cvstos_at_factory or cvstos_worktree_has_debt is False)
    )
    cvstos_window, pressure_window = _lifecycle_cache_windows()
    cvstos = {
        "source": relpath(CVSTOS_STATE),
        "age_seconds": round(cvstos_age, 1) if cvstos_age is not None else None,
        "freshness_window_seconds": cvstos_window,
        "valid": cvstos_valid,
        "fresh": cvstos_age is not None and cvstos_age <= cvstos_window,
        "ok": cvstos_valid and cvstos_at_factory is True,
        "open_invariant_count": len(cvstos_state.get("open_invariants") or []),
    }
    worktree_debt = {
        "source": relpath(LIFECYCLE_PRESSURE_STATE),
        "age_seconds": round(pressure_age, 1) if pressure_age is not None else None,
        "freshness_window_seconds": pressure_window,
        "valid": pressure_valid,
        "fresh": pressure_age is not None and pressure_age <= pressure_window,
        "debt": debt,
        "debt_target": 0,
        "reapable": reapable,
        "reapable_target": 0,
        "reapable_by_reason": reapable_by_reason,
        "error": pressure_error if isinstance(pressure_error, str) else "invalid pressure receipt",
        "ok": pressure_valid and not pressure_error and debt == 0 and reapable == 0,
    }
    return {
        "cvstos": cvstos,
        "worktree_debt": worktree_debt,
        "predicate_ok": bool(
            cvstos["fresh"] and cvstos["ok"] and worktree_debt["fresh"] and worktree_debt["ok"]
        ),
        "generated_state_reclaim": reclaim_log_summary(
            GENERATED_STATE_RECLAIM_LOG, ("changed_roots", "failed_roots")
        ),
        "tool_cache_reclaim": reclaim_log_summary(TOOL_CACHE_RECLAIM_LOG, ("existing_paths", "failed_paths")),
        "ollama_model_reclaim": reclaim_log_summary(
            OLLAMA_MODEL_RECLAIM_LOG, ("model_count", "loaded_models", "blocked_reason", "failed")
        ),
    }


def profile_receipt() -> dict[str, Any]:
    readme = PROFILE_REPO / "README.md"
    data = PROFILE_REPO / "data" / "ecosystem.yml"
    metrics = load_json(CORPVS_ROOT / "system-metrics.json", {})
    computed = metrics.get("computed") if isinstance(metrics, dict) else {}
    computed = computed if isinstance(computed, dict) else {}
    ssot_repos = computed.get("total_repos")
    public_repos_all = computed.get("public_repos_all")
    ssot_words = computed.get("total_words_numeric")
    text = ""
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    current = {
        "readme_present": readme.exists(),
        "data_present": data.exists(),
        "readme_total_repos": readme_marker(text, "total_repos"),
        "data_total_repos": yaml_scalar(data, "total_repos"),
        "ssot_total_repos": ssot_repos,
        "ssot_public_repos_all": public_repos_all,
        "ssot_total_words_numeric": ssot_words,
        "old_portfolio_link_count": text.count("4444j99.github.io/portfolio"),
        "live_portfolio_link_count": text.count("organvm.github.io/portfolio"),
        "top_engineer_claim_present": bool(PROFILE_POSITIONING_RE.search(text)),
        "frontdoor_present": (ROOT / "docs" / "positioning" / "_frontdoor.md").exists(),
    }
    visible = github_profile_surface()
    current["visible_profile"] = visible
    stale_count = str(current["readme_total_repos"] or "") != str(ssot_repos or "")
    stale_words = bool(ssot_words) and "988K+" not in text
    old_links = int(current["old_portfolio_link_count"] or 0) > 0
    missing_claim = not current["top_engineer_claim_present"]
    visible_checked = bool(visible.get("checked"))
    visible_missing = visible_checked and not visible.get("verified")
    visible_stale_count = visible_checked and str(visible.get("readme_total_repos") or "") != str(ssot_repos or "")
    visible_old_links = visible_checked and int(visible.get("old_portfolio_link_count") or 0) > 0
    visible_missing_claim = visible_checked and not visible.get("top_engineer_claim_present")
    account_profile_stale = visible_checked and bool(visible.get("account_profile_stale"))
    if not readme.exists():
        status = STATUS_BLOCKED
        verdict = "profile repo README missing"
    elif stale_count or stale_words or old_links or missing_claim:
        status = STATUS_ASSIGNED
        verdict = "existing profile/frontdoor work is present but not projected"
    elif visible_missing or visible_stale_count or visible_old_links or visible_missing_claim:
        status = STATUS_ASSIGNED
        verdict = "visible GitHub profile README is missing or stale"
    elif account_profile_stale:
        status = STATUS_BLOCKED
        verdict = "visible profile README is current; GitHub sidebar bio/link needs profile-settings scope"
    else:
        status = STATUS_DONE
        verdict = "visible profile README reflects current proof surface"
    return {
        "id": "PUBLIC-FACE-PROFILE",
        "workstream": "public-face",
        "priority": PRIORITY["public-face"],
        "status": status,
        "title": "Reconcile and project the GitHub profile/public face",
        "verdict": verdict,
        "evidence": current,
        "existing_receipts": [
            relpath(ROOT / "docs" / "positioning" / "_frontdoor.md"),
            relpath(ROOT / "his-hand-levers.json"),
            relpath(ROOT / "face-ownership.json"),
            relpath(PROFILE_REPO / "README.md"),
            f"https://github.com/{VISIBLE_PROFILE_REPO}",
        ],
        "assignment_packet": {
            "lane_fit": "codex-integrator",
            "repo": VISIBLE_PROFILE_REPO,
            "task": "Project the existing positioning/frontdoor and current metrics onto the profile README; fix stale counts and dead links.",
            "predicate": "python3 scripts/test_sync_readme.py && python3 scripts/sync-readme.py --check",
            "receipt_target": f"git:{VISIBLE_PROFILE_REPO}:README.md",
            "stop_condition": "profile README has current metrics, live links, and evidence-backed top-engineer positioning",
        },
    }


def mail_stats() -> dict[str, Any]:
    if not MAIL_INDEX.exists():
        return {"present": False, "error": f"missing {MAIL_INDEX}"}
    try:
        conn = sqlite3.connect(f"{MAIL_INDEX.resolve().as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS total_messages,
              SUM(CASE WHEN deleted = 0 THEN 1 ELSE 0 END) AS not_deleted_messages,
              SUM(CASE WHEN deleted = 0 AND flagged = 1 THEN 1 ELSE 0 END) AS flagged_non_deleted,
              MIN(datetime(date_received, 'unixepoch')) AS first_received_at,
              MAX(datetime(date_received, 'unixepoch')) AS last_received_at
            FROM messages
            """
        ).fetchone()
        conn.close()
    except sqlite3.Error as exc:
        return {"present": True, "error": str(exc)}
    return {"present": True, **dict(row or {})}


def mail_census() -> dict[str, Any]:
    result = run_command(["bash", "scripts/mail-beat.sh", "--census"], timeout=45)
    if result["returncode"] != 0:
        return {"ok": False, "error": (result["stderr"] or result["stdout"]).strip()[:500]}
    try:
        return {"ok": True, **json.loads(result["stdout"])}
    except (ValueError, TypeError):
        return {"ok": False, "error": "mail census did not return JSON"}


def mail_story_receipt(
    scope: str,
    expected_count: int,
    *,
    expected_limit: int | None = None,
    require_flagged_total: bool = True,
) -> dict[str, Any]:
    scoped_log = MAIL_STORY_LOG.with_name(f"{MAIL_STORY_LOG.stem}-{scope}{MAIL_STORY_LOG.suffix}")
    ledger = load_json(scoped_log, None)
    if not isinstance(ledger, dict):
        ledger = load_json(MAIL_STORY_LOG, {})
    if not isinstance(ledger, dict):
        ledger = {}
    mode = ledger.get("mode") if isinstance(ledger.get("mode"), dict) else {}
    stats = ledger.get("stats") if isinstance(ledger.get("stats"), dict) else {}
    clusters = ledger.get("clusters") if isinstance(ledger.get("clusters"), list) else []
    atom_count = int(ledger.get("atom_count") or 0)
    cluster_atom_count = sum(int(cluster.get("atom_count") or 0) for cluster in clusters if isinstance(cluster, dict))
    next_action_count = 0
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        actions = cluster.get("next_actions") if isinstance(cluster.get("next_actions"), dict) else {}
        next_action_count += sum(int(value or 0) for value in actions.values())
    flagged_total_ok = True
    if require_flagged_total:
        flagged_total_ok = int(stats.get("flagged_non_deleted") or -1) == expected_count
    limit_ok = True if expected_limit is None else mode.get("limit") == expected_limit
    classified_current = (
        mode.get("scope") == scope
        and limit_ok
        and mode.get("read_only") is True
        and mode.get("body_reads") is False
        and mode.get("mailbox_mutations") is False
        and mode.get("gmail_writes") is False
        and flagged_total_ok
        and atom_count == expected_count
        and cluster_atom_count == atom_count
        and next_action_count == atom_count
        and bool(clusters)
    )
    return {
        "present": bool(ledger),
        "generated_at": ledger.get("generated_at"),
        "scope": mode.get("scope"),
        "limit": mode.get("limit"),
        "atom_count": atom_count,
        "cluster_count": len(clusters),
        "cluster_atom_count": cluster_atom_count,
        "next_action_count": next_action_count,
        "read_only": mode.get("read_only"),
        "body_reads": mode.get("body_reads"),
        "mailbox_mutations": mode.get("mailbox_mutations"),
        "gmail_writes": mode.get("gmail_writes"),
        "classified_current": classified_current,
    }


def mail_receipts() -> list[dict[str, Any]]:
    stats = mail_stats()
    census = mail_census()
    flagged = int(stats.get("flagged_non_deleted") or 0)
    not_deleted = int(stats.get("not_deleted_messages") or 0)
    flagged_story = mail_story_receipt("flagged", flagged)
    history_batch_target = min(500, not_deleted) if not_deleted else 0
    history_story = mail_story_receipt(
        "all",
        history_batch_target,
        expected_limit=500,
        require_flagged_total=False,
    )
    active_done = flagged == 0 or bool(flagged_story.get("classified_current"))
    active_status = STATUS_DONE if active_done else STATUS_ASSIGNED
    history_done = not_deleted == 0 or bool(history_story.get("classified_current"))
    history_status = STATUS_DONE if history_done else STATUS_ASSIGNED
    common = {
        "evidence": {"mail_stats": stats, "mail_census": census, "mail_story": flagged_story},
        "existing_receipts": [
            relpath(ROOT / "docs" / "mail-story-ledger.md"),
            relpath(ROOT / "docs" / "his-hand-registry-mail-a290329e.md"),
            relpath(ROOT / "obligations-ledger.json"),
            relpath(ROOT / "scripts" / "mail-story-ledger.py"),
            relpath(ROOT / "scripts" / "mail-beat.sh"),
        ],
    }
    return [
        {
            "id": "MAIL-ACTIVE-FLAGGED",
            "workstream": "mail-active",
            "priority": PRIORITY["mail-active"],
            "status": active_status,
            "title": "Reconcile active flagged mail before historical sweep",
            "verdict": (
                f"{flagged} active flagged messages classified into {flagged_story.get('cluster_count')} clusters; no body reads or mailbox mutations"
                if active_done and flagged
                else f"{flagged} active flagged non-deleted messages require classification" if flagged else "no active flagged messages remain"
            ),
            **common,
            "assignment_packet": {
                "lane_fit": "local-codex-or-opencode",
                "repo": "organvm/limen",
                "task": "Run python3 scripts/mail-story-ledger.py --scope flagged --write. Use existing mail-story atoms and UMA obligations to classify the active flagged set; draft/park, never send.",
                "predicate": "python3 -m pytest cli/tests/test_mail_story_ledger.py -q",
                "receipt_target": "git:organvm/limen:docs/mail-story-ledger.md",
                "stop_condition": "flagged set has classified atoms, obligations, and needs-human buckets",
            },
        },
        {
            "id": "MAIL-HISTORICAL-BACKLOG",
            "workstream": "mail-historical",
            "priority": PRIORITY["mail-historical"],
            "status": history_status,
            "title": "Continue historical mail backlog in resumable batches",
            "verdict": (
                f"{history_story.get('atom_count')} historical messages atomized in this bounded batch; {not_deleted} indexed non-deleted messages remain for future batches"
                if history_done and not_deleted
                else f"{not_deleted} indexed non-deleted messages exist; process in batches, not one giant run"
                if not_deleted
                else "no indexed mail backlog visible"
            ),
            **{**common, "evidence": {**common["evidence"], "mail_story": history_story}},
            "assignment_packet": {
                "lane_fit": "local-codex-or-opencode",
                "repo": "organvm/limen",
                "task": "Continue the historical metadata sweep from existing receipts; emit batch cursor/count receipt before any thread enrichment.",
                "predicate": "python3 scripts/mail-story-ledger.py --scope all --limit 500 --write",
                "receipt_target": "git:organvm/limen:docs/mail-story-ledger.md",
                "stop_condition": "next 500 historical messages are atomized or a precise cursor/blocker is recorded",
            },
        },
    ]


def repo_surface_receipt() -> dict[str, Any]:
    index = load_json(REPO_SURFACE_INDEX, {})
    generated = index.get("generated_at") if isinstance(index, dict) else None
    generated_age_hours = iso_age_hours(generated)
    repo_count = int(index.get("repo_count") or 0) if isinstance(index, dict) else 0
    duplicate_groups = index.get("duplicate_remotes") if isinstance(index, dict) else []
    duplicate_count = len(duplicate_groups) if isinstance(duplicate_groups, list) else 0
    status = STATUS_ASSIGNED
    verdict = "repo surface ledger exists but needs boil-up assignment"
    if not index:
        status = STATUS_NEEDS
        verdict = "repo surface ledger missing; assignment must refresh existing roots before new work"
    elif repo_count >= 200 and generated_age_hours is not None and generated_age_hours <= 24:
        status = STATUS_DONE
        verdict = f"fresh repo surface ledger covers broad repo estate; {duplicate_count} duplicate remote group(s) recorded"
    elif repo_count >= 200:
        verdict = "broad repo surface ledger exists, but it is stale for current boil-up work"
    return {
        "id": "REPO-BOIL-UP",
        "workstream": "repo-boil-up",
        "priority": PRIORITY["repo-boil-up"],
        "status": status,
        "title": "Reconcile local, nested, archive, and GitHub repo boil-up receipts",
        "verdict": verdict,
        "evidence": {
            "repo_surface_index_present": bool(index),
            "generated_at": generated,
            "generated_age_hours": generated_age_hours,
            "repo_count": repo_count,
            "duplicate_remote_groups": duplicate_count,
        },
        "existing_receipts": [
            relpath(ROOT / "docs" / "repo-surface-ledger.md"),
            relpath(ROOT / "docs" / "consolidation" / "GATES.md"),
            relpath(ROOT / "docs" / "consolidation" / "EXECUTION-MANIFEST.md"),
            relpath(ROOT / "scripts" / "repo-surface-ledger.py"),
            relpath(ROOT / "scripts" / "salvage-yard-map.py"),
        ],
        "assignment_packet": {
            "lane_fit": "agy-or-opencode-readonly",
            "repo": "organvm/limen",
            "task": "Run python3 scripts/repo-surface-ledger.py --scan-root ~/Workspace --max-depth 6 --write. Harvest existing repo-surface and consolidation receipts, then assign only missing classifications.",
            "predicate": "scripts/verify-scoped.sh",
            "receipt_target": "git:organvm/limen:docs/repo-surface-ledger.md",
            "stop_condition": "all discovered roots are classified or recorded with blocker/gate",
        },
    }


def prompt_packet_receipt() -> dict[str, Any]:
    index = load_json(PROMPT_PACKET_INDEX, {})
    open_packets = index.get("open_packets") if isinstance(index, dict) else []
    recorded = index.get("recorded_packets") if isinstance(index, dict) else []
    open_count = len(open_packets) if isinstance(open_packets, list) else 0
    status = STATUS_DONE if index and open_count == 0 else STATUS_ASSIGNED
    return {
        "id": "PROMPT-PACKETS",
        "workstream": "prompt-packets",
        "priority": PRIORITY["prompt-packets"],
        "status": status,
        "title": "Reconcile prompt packet receipts before counting prompt progress",
        "verdict": f"{open_count} open packet(s)" if open_count else "packet ledger clear from receipts",
        "evidence": {
            "index_present": bool(index),
            "open_packets": open_count,
            "recorded_packets": len(recorded) if isinstance(recorded, list) else 0,
        },
        "existing_receipts": [
            relpath(ROOT / "docs" / "prompt-packet-ledger.md"),
            relpath(ROOT / "docs" / "prompt-packet-resolution-receipts.json"),
            relpath(ROOT / "docs" / "current-session-fanout.md"),
        ],
        "assignment_packet": {
            "lane_fit": "codex-conductor",
            "repo": "organvm/limen",
            "task": "Map each open prompt packet to merged PR, open PR, owner task, supersession, or precise blocker.",
            "predicate": "python3 scripts/prompt-packet-ledger.py --write",
            "receipt_target": "git:organvm/limen:docs/prompt-packet-ledger.md",
            "stop_condition": "open prompt packet count is zero or every packet has an owner receipt",
        },
    }


def value_repo_receipt() -> dict[str, Any]:
    values = load_json(VALUE_REPOS, {})
    repos = [str(repo) for repo in values.get("repos", [])] if isinstance(values, dict) else []
    product = load_json(PRODUCT_LEDGER_INDEX, {})
    next_rows = product.get("next_unblocked") if isinstance(product, dict) else []
    products = product.get("products") if isinstance(product, dict) else []
    products = products if isinstance(products, list) else []
    generated = product.get("generated_at") if isinstance(product, dict) else None
    generated_age_hours = iso_age_hours(generated)
    top_repos = repos[:5]
    sell_ready_owners = {
        str(row.get("owner"))
        for row in products
        if isinstance(row, dict)
        and row.get("source_kind") == "repo"
        and row.get("state") == "ship"
        and row.get("disposition") == "sell-ready"
    }
    independent_receipt_owners = {
        str(row.get("owner"))
        for row in products
        if isinstance(row, dict)
        and row.get("source_kind") != "repo"
        and str(row.get("owner") or "") in repos
    }
    missing_sell_ready = [repo for repo in repos if repo not in sell_ready_owners]
    missing_top_receipts = [repo for repo in top_repos if repo not in independent_receipt_owners]
    fresh_product = generated_age_hours is not None and generated_age_hours <= 24
    if not repos:
        status = STATUS_BLOCKED
        verdict = "value repo list missing or empty"
    elif (
        product
        and fresh_product
        and not missing_sell_ready
        and not missing_top_receipts
        and isinstance(next_rows, list)
        and next_rows
    ):
        status = STATUS_DONE
        verdict = (
            f"top {len(top_repos)} value repos have owner receipts; "
            f"{len(sell_ready_owners & set(repos))} value repos are sell-ready in the product ledger"
        )
    elif product and not fresh_product:
        status = STATUS_ASSIGNED
        verdict = "value repo product ledger exists, but it is stale for current funded-lane steering"
    elif product and missing_top_receipts:
        status = STATUS_ASSIGNED
        verdict = "top value repos still need owner receipts: " + ", ".join(missing_top_receipts[:5])
    elif product and missing_sell_ready:
        status = STATUS_ASSIGNED
        verdict = "value repo product ledger is missing sell-ready rows: " + ", ".join(missing_sell_ready[:5])
    else:
        status = STATUS_ASSIGNED
        verdict = f"{len(repos)} value repos define the funded work lane"
    return {
        "id": "VALUE-REPOS",
        "workstream": "revenue-value-repos",
        "priority": PRIORITY["revenue-value-repos"],
        "status": status,
        "title": "Assign revenue/value repo work from existing ledgers",
        "verdict": verdict,
        "evidence": {
            "value_repo_count": len(repos),
            "top_value_repos": repos[:8],
            "product_ledger_present": bool(product),
            "product_ledger_generated_at": generated,
            "product_ledger_age_hours": generated_age_hours,
            "next_unblocked_count": len(next_rows) if isinstance(next_rows, list) else 0,
            "sell_ready_value_repo_count": len(sell_ready_owners & set(repos)),
            "top_value_repos_with_owner_receipts": [repo for repo in top_repos if repo in independent_receipt_owners],
            "missing_top_value_receipts": missing_top_receipts,
            "missing_sell_ready_value_repos": missing_sell_ready,
        },
        "existing_receipts": [
            relpath(ROOT / "value-repos.json"),
            relpath(ROOT / "docs" / "product-ledger.md"),
            relpath(ROOT / "docs" / "positioning" / "_frontdoor.md"),
        ],
        "assignment_packet": {
            "lane_fit": "jules-or-opencode-repo-specific",
            "repo": "organvm/limen",
            "task": "Harvest existing PRs/tasks for top value repos, then assign only clean bounded ship predicates.",
            "predicate": "python3 scripts/product-ledger.py --write",
            "receipt_target": "git:organvm/limen:docs/product-ledger.md",
            "stop_condition": "top value repo has shipped PR, open PR with predicate, owner task, or blocker",
        },
    }


def estate_custody_receipt() -> dict[str, Any]:
    volumes = {
        "Archive4T": ARCHIVE4T_ROOT.exists(),
        "Ingress": INGRESS_ROOT.exists(),
        "Scratch": SCRATCH_ROOT.exists(),
        "T7Recovery": T7RECOVERY_ROOT.exists(),
    }
    required_docs = [
        STORAGE_OPERATING_MANUAL,
        LOCAL_DISK_EXPULSION_POLICY,
        ROOT / "docs" / "vltima-absorb-cadence.md",
        ROOT / "docs" / "vltima-prior-excavations.md",
        ROOT / "docs" / "photos-universe-recovery-2026-06-29.md",
    ]
    primitive_layers = [
        T7_LIFEBOAT_ROOT / "00_SUBSTRATE",
        T7_LIFEBOAT_ROOT / "10_PROFILE",
        T7_LIFEBOAT_ROOT / "20_TEXT",
        T7_LIFEBOAT_ROOT / "30_CODE",
        T7_LIFEBOAT_ROOT / "_MANIFESTS",
    ]
    missing_volumes = [name for name, mounted in volumes.items() if not mounted]
    missing_docs = [relpath(path) for path in required_docs if not path.exists()]
    missing_layers = [relpath(path) for path in primitive_layers if not path.exists()]
    doctrine_present = ESTATE_CUSTODY_DOC.exists()
    receipt = load_json(ESTATE_CUSTODY_RECEIPT, {})
    reclaim_candidates = load_json(WORKTREE_RECLAIM_CANDIDATES_JSON, {})
    implementation_receipts = receipt.get("receipts") if isinstance(receipt, dict) else []
    implementation_status = str(receipt.get("status") or "") if isinstance(receipt, dict) else ""
    implementation_complete = bool(implementation_receipts) and (
        receipt.get("complete") is True
        or implementation_status in {"complete", "owner_receipts_complete"}
    )
    if missing_volumes or missing_docs or missing_layers:
        status = STATUS_BLOCKED
        verdict = "external estate custody is missing required mounted evidence"
    elif not doctrine_present:
        status = STATUS_ASSIGNED
        verdict = "external estate doctrine needs a tracked owner surface"
    elif not implementation_complete:
        status = STATUS_ASSIGNED
        verdict = "estate doctrine exists; implementation receipt is not complete"
    else:
        status = STATUS_DONE
        verdict = "run-and-gun laptop cache and external estate custody have implementation receipts"
    return {
        "id": "ESTATE-CUSTODY",
        "workstream": "estate-custody",
        "priority": PRIORITY["estate-custody"],
        "status": status,
        "title": "Make external SSDs the durable estate and the laptop a hot cache",
        "verdict": verdict,
        "evidence": {
            "volumes": volumes,
            "missing_volumes": missing_volumes,
            "required_docs_missing": missing_docs,
            "primitive_layers_missing": missing_layers,
            "doctrine_doc_present": doctrine_present,
            "doctrine_doc": relpath(ESTATE_CUSTODY_DOC),
            "implementation_receipt_present": bool(receipt),
            "implementation_receipt_status": implementation_status,
            "implementation_receipt_complete": implementation_complete,
            "implementation_receipt": relpath(ESTATE_CUSTODY_RECEIPT),
            "implementation_receipt_count": len(implementation_receipts) if isinstance(implementation_receipts, list) else 0,
            "worktree_reclaim_candidates_present": WORKTREE_RECLAIM_CANDIDATES_DOC.exists(),
            "worktree_reclaim_candidate_roots": (reclaim_candidates.get("summary") or {}).get("candidate_roots")
            if isinstance(reclaim_candidates, dict)
            else None,
            "worktree_reclaim_candidate_size": (reclaim_candidates.get("summary") or {}).get(
                "measured_candidate_size"
            )
            if isinstance(reclaim_candidates, dict)
            else None,
        },
        "existing_receipts": [
            relpath(STORAGE_OPERATING_MANUAL),
            relpath(LOCAL_DISK_EXPULSION_POLICY),
            relpath(ROOT / "docs" / "vltima-absorb-cadence.md"),
            relpath(ROOT / "docs" / "vltima-prior-excavations.md"),
            relpath(ROOT / "docs" / "photos-universe-recovery-2026-06-29.md"),
            relpath(ESTATE_CUSTODY_DOC),
            relpath(WORKTREE_RECLAIM_CANDIDATES_DOC),
            relpath(WORKTREE_RECLAIM_CANDIDATES_JSON),
            "https://github.com/organvm/limen/issues/685",
            "https://github.com/organvm/limen/issues/688",
            "https://github.com/organvm/media-ark/issues/56",
            "https://github.com/organvm/portvs/issues/2",
        ],
        "assignment_packet": {
            "lane_fit": "codex-conductor",
            "repo": "organvm/limen",
            "task": (
                "Build the run-and-gun estate lifecycle: external SSDs hold durable private/raw data, "
                "processed/redacted corpora, repo/org mirrors, photos/media packages, and recovery copies; "
                "the laptop stays a thin hot cache. Route every pain point to an owner repo and a reusable "
                "public shell when private data can be redacted. Use the worktree reclaim candidate packet "
                "as the score-gated cleanup input; do not delete local roots without acceptance/redaction proof."
            ),
            "predicate": (
                "test -f docs/estate-custody-primitives.md && "
                "python3 scripts/worktree-reclaim-candidates.py --write --limit 50 && "
                "python3 scripts/substrate-ledger.py --write && "
                "python3 scripts/vltima-prior-excavations.py --write"
            ),
            "receipt_target": "git:organvm/limen:docs/estate-custody-implementation-receipts.json",
            "stop_condition": (
                "external estate cleanup, prompt chronology, repo/org custody, photos processing, and "
                "pain-point productization each have owner receipts without destructive local-only action"
            ),
        },
    }


def contribution_balance_receipt() -> dict[str, Any]:
    result = run_command(
        ["python3", str(CONTRIBUTION_BALANCE_SCRIPT), "--login", CONTRIBUTION_BALANCE_LOGIN, "--json"],
        timeout=90,
    )
    report: dict[str, Any] = {}
    error = ""
    if result["returncode"] == 0:
        try:
            loaded = json.loads(result["stdout"] or "{}")
            if isinstance(loaded, dict):
                report = loaded
        except ValueError as exc:
            error = f"invalid contribution balance JSON: {exc}"
    else:
        error = (result["stderr"] or result["stdout"] or "contribution balance command failed").strip()[:500]

    needs_balance = report.get("status") == "needs_balance"
    status = STATUS_ASSIGNED if error or needs_balance else STATUS_DONE
    shares = report.get("shares") if isinstance(report.get("shares"), dict) else {}
    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    if error:
        verdict = f"contribution balance receipt failed: {error}"
    elif needs_balance:
        verdict = (
            "GitHub activity mix needs owner action: "
            f"commits {float(shares.get('commits') or 0):.1%}, "
            f"PRs {float(shares.get('pull_requests') or 0):.1%}, "
            f"issues {float(shares.get('issues') or 0):.1%}, "
            f"reviews {float(shares.get('reviews') or 0):.1%}"
        )
    else:
        verdict = "GitHub activity mix is within the configured issue -> PR -> review target"
    return {
        "id": "PUBLIC-FACE-CONTRIBUTION-BALANCE",
        "workstream": "contribution-balance",
        "priority": PRIORITY["contribution-balance"],
        "status": status,
        "title": "Rebalance public GitHub activity away from commit-only churn",
        "verdict": verdict,
        "evidence": {
            "login": report.get("login") or CONTRIBUTION_BALANCE_LOGIN,
            "status": report.get("status") or ("error" if error else "unknown"),
            "counts": counts,
            "shares": shares,
            "targets": report.get("targets") if isinstance(report.get("targets"), dict) else {},
            "next_action": report.get("next_action") or "",
            "error": error,
        },
        "existing_receipts": [
            contribution_balance_public_path(CONTRIBUTION_BALANCE_POLICY),
            contribution_balance_public_path(CONTRIBUTION_BALANCE_SCRIPT),
            contribution_balance_public_path(ROOT / "cli" / "tests" / "test_github_contribution_balance.py"),
            CONTRIBUTION_BALANCE_OWNER_ISSUE,
            "https://github.com/4444J99",
        ],
        "assignment_packet": {
            "lane_fit": "codex-conductor",
            "repo": "organvm/limen",
            "task": (
                f"Run python3 scripts/github-contribution-balance.py --login {CONTRIBUTION_BALANCE_LOGIN} --json and use the live contribution balance as a value gate: route the next public work to "
                "substantive PR review first, then real issue criteria and PR packaging, before more "
                "commit-heavy implementation churn."
            ),
            "predicate": "python3 -m pytest cli/tests/test_github_contribution_balance.py -q",
            "receipt_target": "git:organvm/limen:docs/always-working.md",
            "stop_condition": "reviews/issues/PRs have owner receipts and commit-only churn is no longer the next public action",
        },
    }


def credential_wall_receipt() -> dict[str, Any]:
    check = run_command(["python3", "scripts/credential-wall.py", "--check"], timeout=60)
    census_result = run_command(["python3", "scripts/credential-wall.py", "--census"], timeout=60)
    census: dict[str, Any] = {}
    census_error = ""
    if census_result["returncode"] == 0:
        try:
            loaded = json.loads(census_result["stdout"] or "{}")
            if isinstance(loaded, dict):
                census = loaded
        except ValueError as exc:
            census_error = f"invalid credential census JSON: {exc}"
    else:
        census_error = (census_result["stderr"] or census_result["stdout"] or "credential census failed").strip()[:500]

    tombstone_present = CREDENTIAL_TOMBSTONE_DOC.exists()
    check_ok = check["returncode"] == 0
    status = STATUS_DONE if check_ok and tombstone_present and not census_error else STATUS_ASSIGNED
    if not check_ok:
        verdict = "credential wall check failed; token/secret ownership has gaps"
    elif census_error:
        verdict = f"credential wall census failed: {census_error}"
    elif not tombstone_present:
        verdict = "credential wall passes current-home check; historical token tombstone audit still needs owner receipt"
    else:
        verdict = "credential wall and historical token tombstone receipt are present"
    return {
        "id": "CREDENTIAL-WALL-TOKEN-HYGIENE",
        "workstream": "credential-wall",
        "priority": PRIORITY["credential-wall"],
        "status": status,
        "title": "Own every token, secret, scope, and credential pain point in the credential wall",
        "verdict": verdict,
        "evidence": {
            "credential_wall_check_returncode": check["returncode"],
            "credential_wall_check_first_line": (check["stdout"] or check["stderr"]).splitlines()[0]
            if (check["stdout"] or check["stderr"]).splitlines()
            else "",
            "credential_census": census,
            "credential_census_error": census_error,
            "historical_token_tombstone_doc_present": tombstone_present,
            "historical_token_tombstone_doc": relpath(CREDENTIAL_TOMBSTONE_DOC),
        },
        "existing_receipts": [
            relpath(ROOT / "scripts" / "credential-wall.py"),
            relpath(ROOT / "scripts" / "creds-hydrate.py"),
            "https://github.com/organvm/limen/issues/320",
            "https://github.com/organvm/limen/labels/credential",
        ],
        "assignment_packet": {
            "lane_fit": "codex-integrator",
            "repo": "organvm/limen",
            "task": (
                "Keep token/scope failures out of chat by registering every current credential atom "
                "and adding a historical tombstone receipt for formerly exposed or rotated tokens. "
                "Never record secret values."
            ),
            "predicate": "python3 scripts/credential-wall.py --check && test -f docs/credential-token-tombstone-audit.md",
            "receipt_target": "git:organvm/limen:docs/credential-token-tombstone-audit.md",
            "stop_condition": "current credential wall passes and historic token existence/revocation custody is recorded without values",
        },
    }


def tabularius_receipt() -> dict[str, Any]:
    doc = ROOT / "docs" / "tabularius-record-keeper.md"
    audit_doc = ROOT / "docs" / "tabularius-writer-audit.md"
    audit_log = ROOT / "logs" / "task-writer-audit.json"
    text = ""
    audit_text = ""
    try:
        text = doc.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    try:
        audit_text = audit_doc.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    audit = load_json(audit_log, {})
    packet_counts = audit.get("owner_packet_counts") if isinstance(audit, dict) else {}
    unclassified = int((packet_counts or {}).get("TAB-UNCLASSIFIED-WRITER") or 0) if isinstance(packet_counts, dict) else 0
    step_22_open = bool(re.search(r"(?m)^- \[ \] Step 2\.2(?:\s|$|—)", text))
    owner_recorded = "tabularius-writer-audit:owner-recorded" in audit_text and unclassified == 0
    status = STATUS_DONE if not step_22_open or owner_recorded else STATUS_ASSIGNED
    if owner_recorded and step_22_open:
        verdict = "Step 2.2 status/result writers are owner-recorded in the tracked writer audit"
    elif step_22_open:
        verdict = "Step 2.2 still open in the keeper doc"
    else:
        verdict = "status-mutator tier is recorded closed"
    return {
        "id": "TABVLARIVS-STATUS-WRITERS",
        "workstream": "tabularius",
        "priority": PRIORITY["tabularius"],
        "status": status,
        "title": "Finish single-writer status/result mutation conversion",
        "verdict": verdict,
        "evidence": {
            "step_2_2_open": step_22_open,
            "writer_audit_doc_present": audit_doc.exists(),
            "writer_audit_owner_recorded": owner_recorded,
            "writer_audit_direct_writer_count": audit.get("direct_writer_count") if isinstance(audit, dict) else None,
            "writer_audit_unclassified_count": unclassified,
            "writer_audit_owner_packet_counts": packet_counts if isinstance(packet_counts, dict) else {},
        },
        "existing_receipts": [relpath(doc), relpath(audit_doc), relpath(ROOT / "cli" / "src" / "limen" / "tabularius.py")],
        "assignment_packet": {
            "lane_fit": "codex-integrator",
            "repo": "organvm/limen",
            "task": "Convert status/result writers to keeper tickets; preserve tasks.yaml drift as separate board state.",
            "predicate": "python3 scripts/task-writer-audit.py && PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q",
            "receipt_target": "git:organvm/limen:docs/tabularius-writer-audit.md",
            "stop_condition": "non-keeper status/result direct writers are converted or explicitly owner-recorded",
        },
    }


def substrate_receipt() -> dict[str, Any]:
    disk = disk_receipt()
    target_free_gib = float(os.environ.get("LIMEN_ALWAYS_WORKING_TARGET_FREE_GIB", "200"))
    lifecycle = substrate_lifecycle_receipt()
    storage_pressure = load_json(SUBSTRATE_STORAGE_INDEX, {})
    shortfall_gib = round(max(target_free_gib - float(disk["free_gib"]), 0.0), 1)
    open_substrate = bool(shortfall_gib > 0 or not disk["tmp_ok"] or not lifecycle["predicate_ok"])
    owner_gated = bool(
        shortfall_gib > 0
        and disk["tmp_ok"]
        and lifecycle["predicate_ok"]
        and isinstance(storage_pressure, dict)
        and storage_pressure.get("status") == "needs-owner-gates"
    )
    if not lifecycle["predicate_ok"]:
        verdict = "substrate lifecycle predicate is failing"
    elif shortfall_gib > 0:
        last_reclaim = lifecycle["generated_state_reclaim"]
        last_tool_reclaim = lifecycle["tool_cache_reclaim"]
        last_ollama_reclaim = lifecycle["ollama_model_reclaim"]
        reclaim_parts = []
        if last_reclaim.get("present") and last_reclaim.get("cumulative_reclaimed_size"):
            reclaim_parts.append(f"generated-state {last_reclaim['cumulative_reclaimed_size']}")
        if last_tool_reclaim.get("present") and last_tool_reclaim.get("cumulative_reclaimed_size"):
            reclaim_parts.append(f"tool-cache {last_tool_reclaim['cumulative_reclaimed_size']}")
        if last_ollama_reclaim.get("present") and last_ollama_reclaim.get("cumulative_reclaimed_size"):
            reclaim_parts.append(f"ollama-models {last_ollama_reclaim['cumulative_reclaimed_size']}")
        suffix = f"; recorded reclaim freed {', '.join(reclaim_parts)}" if reclaim_parts else ""
        if owner_gated:
            verdict = f"internal free space is {shortfall_gib} GiB below target{suffix}; remaining bytes require owner gates"
        else:
            verdict = f"internal free space is {shortfall_gib} GiB below target{suffix}"
    elif not disk["tmp_ok"]:
        verdict = "temp writes are failing"
    else:
        verdict = "disk/temp substrate predicate is green"
    return {
        "id": "SUBSTRATE-DISK-TEMP",
        "workstream": "substrate",
        "priority": PRIORITY["substrate"],
        "status": STATUS_BLOCKED if owner_gated else (STATUS_ASSIGNED if open_substrate else STATUS_DONE),
        "title": "Keep disk/temp/voice substrate from starving the swarm",
        "verdict": verdict,
        "evidence": {
            **disk,
            "target_free_gib": target_free_gib,
            "shortfall_gib": shortfall_gib,
            "lifecycle": lifecycle,
            "storage_pressure_status": storage_pressure.get("status") if isinstance(storage_pressure, dict) else None,
        },
        "existing_receipts": [
            relpath(ROOT / "logs" / "heartbeat.out.log"),
            relpath(GENERATED_STATE_RECLAIM_LOG),
            relpath(TOOL_CACHE_RECLAIM_LOG),
            relpath(OLLAMA_MODEL_RECLAIM_LOG),
            relpath(ROOT / "docs" / "substrate-storage-pressure.md"),
            relpath(OPENCODE_DB_INTAKE_DOC),
            relpath(ROOT / "scripts" / "cvstos-organ.py"),
            relpath(ROOT / "scripts" / "dispatch-health.py"),
            relpath(ROOT / "scripts" / "opencode-db-corpus-intake.py"),
            relpath(ROOT / "scripts" / "reclaim-generated-state.py"),
            relpath(ROOT / "scripts" / "reclaim-ollama-models.py"),
            relpath(ROOT / "scripts" / "reclaim-tool-caches.py"),
            relpath(ROOT / "scripts" / "reclaim-worktrees.py"),
            relpath(ROOT / "scripts" / "reap-clones.py"),
            relpath(ROOT / "scripts" / "substrate-storage-pressure.py"),
            relpath(ROOT / "scripts" / "worktree-debt.py"),
        ],
        "assignment_packet": {
            "lane_fit": "codex-local",
            "repo": "organvm/limen",
            "task": "Run the full disk-relief pass in a worktree: python3 scripts/reclaim-generated-state.py --apply && python3 scripts/reclaim-tool-caches.py --apply && python3 scripts/reclaim-ollama-models.py --apply && python3 scripts/substrate-storage-pressure.py --write && python3 scripts/cvstos-organ.py --check && python3 scripts/worktree-debt.py --fail-on-debt --fail-reapable-over-cap. Reclaim ignored generated state, preserve or owner-route local-only payloads, and keep Scratch as the active work substrate.",
            "predicate": "python3 -m pytest cli/tests/test_substrate_storage_pressure.py -q",
            "receipt_target": "git:organvm/limen:logs/reclaim-generated-state.jsonl",
            "stop_condition": "free disk is at target, temp writes are usable, worktree debt is exactly zero, and reapable roots are zero",
        },
    }


def build_snapshot() -> dict[str, Any]:
    items = [
        substrate_receipt(),
        estate_custody_receipt(),
        profile_receipt(),
        contribution_balance_receipt(),
        credential_wall_receipt(),
        *mail_receipts(),
        repo_surface_receipt(),
        prompt_packet_receipt(),
        value_repo_receipt(),
        tabularius_receipt(),
    ]
    # Carry the already-derived lane choice in the machine snapshot so downstream
    # conductors can validate and route one packet without copying this workstream
    # map or guessing a provider from prose such as ``lane_fit``.
    for item in items:
        item["target_agent"] = AGENT_BY_WORKSTREAM.get(str(item.get("workstream") or ""), "codex")
    items = sorted(items, key=lambda row: (int(row["priority"]), str(row["id"])))
    open_items = [item for item in items if item["status"] in REQUIRED_OPEN]
    blocked_items = [item for item in items if item["status"] == STATUS_BLOCKED]
    done_items = [item for item in items if item["status"] == STATUS_DONE]
    next_item = open_items[0] if open_items else (blocked_items[0] if blocked_items else None)
    return {
        "generated_at": now_iso(),
        "schema": "limen.always_working.v1",
        "status": "needs-work" if open_items else ("blocked" if blocked_items else "clear"),
        "required_open_count": len(open_items),
        "blocked_count": len(blocked_items),
        "done_count": len(done_items),
        "next_item_id": next_item["id"] if next_item else None,
        "next_item_status": next_item["status"] if next_item else None,
        "items": items,
        "contract": {
            "receipt_first": True,
            "first_run_forbidden": True,
            "generic_ci_counts_as_progress": False,
            "auto_send_email": False,
            "destructive_repo_actions": False,
        },
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# Always-Working Reconciliation",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Status: `{snapshot['status']}`",
        f"Required open: `{snapshot['required_open_count']}`",
        f"Blocked: `{snapshot['blocked_count']}`",
        f"Done from receipt: `{snapshot['done_count']}`",
        "",
        "## Contract",
        "",
        "- Start by harvesting existing receipts, not by doing a first run.",
        "- A workstream is `done_from_receipt`, `assigned_from_existing_work`, `needs_assignment`, or `blocked`.",
        "- Generic CI, rebase, and queue draining do not count while required user-promise work is open.",
        "- Email send and destructive repo consolidation remain gated.",
        "- Missing assignments are emitted through TABVLARIVS tickets, never by direct board edits.",
        "",
        "## Next Packet",
        "",
    ]
    next_item = next((item for item in snapshot["items"] if item["id"] == snapshot.get("next_item_id")), None)
    if next_item:
        packet = next_item.get("assignment_packet") or {}
        lines += [
            f"- ID: `{next_item['id']}`",
            f"- Workstream: `{next_item['workstream']}`",
            f"- Status: `{next_item['status']}`",
            f"- Verdict: {next_item['verdict']}",
            f"- Lane fit: `{packet.get('lane_fit', '')}`",
            f"- Predicate: `{packet.get('predicate', '')}`",
            f"- Receipt target: `{packet.get('receipt_target', '')}`",
        ]
    else:
        lines.append("- none")
    lines += [
        "",
        "## Workstreams",
        "",
        "| Priority | ID | Status | Verdict |",
        "|---:|---|---|---|",
    ]
    for item in snapshot["items"]:
        verdict = str(item.get("verdict") or "").replace("|", "\\|")
        lines.append(f"| {item['priority']} | `{item['id']}` | `{item['status']}` | {verdict} |")
    lines += [
        "",
        "## Assignment Packets",
        "",
    ]
    for item in snapshot["items"]:
        packet = item.get("assignment_packet") or {}
        if item["status"] == STATUS_DONE:
            continue
        lines += [
            f"### {item['id']}",
            "",
            f"- Lane fit: `{packet.get('lane_fit', '')}`",
            f"- Repo/root: `{packet.get('repo', '')}`",
            f"- Task: {packet.get('task', '')}",
            f"- Predicate: `{packet.get('predicate', '')}`",
            f"- Receipt target: `{packet.get('receipt_target', '')}`",
            f"- Stop condition: {packet.get('stop_condition', '')}",
            "- Existing receipts:",
        ]
        for receipt in item.get("existing_receipts") or []:
            lines.append(f"  - `{receipt}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    DOC_PATH.write_text(markdown, encoding="utf-8")


def _task_id(item: dict[str, Any]) -> str:
    raw = re.sub(r"[^A-Za-z0-9._/-]+", "-", str(item.get("id") or "")).strip("-")
    return f"AW-{raw}"[:128]


def _priority(item: dict[str, Any]) -> str:
    raw = item.get("priority")
    value = 100 if raw is None else int(raw)
    if value <= 20:
        return "critical"
    if value <= 50:
        return "high"
    return "medium"


def _task_from_item(item: dict[str, Any]) -> dict[str, Any]:
    packet = item.get("assignment_packet") or {}
    workstream = str(item.get("workstream") or "always-working")
    context = "\n".join(
        [
            f"Receipt-first verdict: {item.get('verdict') or ''}",
            f"Task: {packet.get('task') or item.get('title') or ''}",
            f"Predicate: {packet.get('predicate') or ''}",
            f"Receipt target: {packet.get('receipt_target') or ''}",
            f"Stop condition: {packet.get('stop_condition') or ''}",
            "Do not start a first run until existing receipts/PRs/tasks for this packet have been harvested.",
        ]
    )
    return {
        "id": _task_id(item),
        "title": str(item.get("title") or item.get("id") or "Always-working promise packet"),
        "description": str(item.get("verdict") or ""),
        "repo": str(packet.get("repo") or relpath(ROOT)),
        "type": "coordination",
        "target_agent": str(item.get("target_agent") or AGENT_BY_WORKSTREAM.get(workstream, "codex")),
        "workstream": workstream,
        "priority": _priority(item),
        "budget_cost": 1,
        "status": "open",
        "labels": ["always-working", "receipt-first", workstream],
        "urls": [str(value) for value in item.get("existing_receipts") or []][:10],
        "context": context,
        "predicate": str(packet.get("predicate") or ""),
        "receipt_target": str(packet.get("receipt_target") or ""),
        "created": dt.datetime.now(dt.timezone.utc).date().isoformat(),
    }


def emit_task_tickets(
    snapshot: dict[str, Any],
    *,
    board_path: Path,
    agent: str,
    session_id: str,
) -> dict[str, Any]:
    from limen.io import load_limen_file
    from limen.tabularius import submit_task_upsert

    board = load_limen_file(board_path)
    existing = {task.id for task in board.tasks}
    emitted: list[str] = []
    skipped_existing: list[str] = []
    for item in snapshot["items"]:
        if item.get("status") not in REQUIRED_OPEN:
            continue
        task = _task_from_item(item)
        task_id = str(task["id"])
        if task_id in existing:
            skipped_existing.append(task_id)
            continue
        submit_task_upsert(board_path, task, agent=agent, session_id=session_id)
        emitted.append(task_id)
    return {
        "board_path": str(board_path),
        "emitted": emitted,
        "skipped_existing": skipped_existing,
        "emitted_count": len(emitted),
        "skipped_existing_count": len(skipped_existing),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile always-working user promises from existing receipts.")
    parser.add_argument("--write", action="store_true", help="write private JSON and tracked Markdown")
    parser.add_argument("--json", action="store_true", help="print snapshot JSON")
    parser.add_argument("--check", action="store_true", help="fail if required work is open or blockers exist")
    parser.add_argument(
        "--emit-task-tickets",
        action="store_true",
        help="submit missing AW-* assignment tasks through TABVLARIVS tickets",
    )
    parser.add_argument("--tasks", type=Path, default=Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml")))
    parser.add_argument("--agent", default=os.environ.get("LIMEN_AGENT", "codex"))
    parser.add_argument("--session-id", default=os.environ.get("LIMEN_SESSION_ID", "always-working"))
    args = parser.parse_args()
    snapshot = build_snapshot()
    markdown = render_markdown(snapshot)
    emission = None
    if args.write:
        write_outputs(snapshot, markdown)
        print(f"always-working: {snapshot['status']} required_open={snapshot['required_open_count']}; wrote {DOC_PATH}")
    elif args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print(markdown, end="")
        print("always-working: dry-run")
    if args.emit_task_tickets:
        emission = emit_task_tickets(
            snapshot,
            board_path=args.tasks,
            agent=args.agent,
            session_id=args.session_id,
        )
        print(
            "always-working: emitted "
            f"{emission['emitted_count']} keeper ticket(s), skipped {emission['skipped_existing_count']} existing task(s)"
        )
    if args.check and (snapshot["required_open_count"] or snapshot["blocked_count"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
