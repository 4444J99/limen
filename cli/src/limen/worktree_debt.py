from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, TypedDict

from limen.worktree_roots import effective_worktree_root, iter_worktree_targets

DEBT_REASONS = {
    "dirty",
    "not-a-git-dir",
    "not-merged-to-default",
    "unpushed-commits",
    "unresolved",
}
REAPABLE_REASONS = {
    "clean+merged+idle",
    "clean+pushed+idle",
    "receipt-remote-merged+clean+idle",
}

DOCUMENTED_RESIDUE_LANES = {"documented-residue"}
DOCUMENTED_RESIDUE_STATUSES = {
    "cache_only_residue",
    "documented_non_source_residue",
    "empty_generated_residue",
}
REMOTE_SUPERSEDED_LANES = {"remote-superseded"}
REMOTE_SUPERSEDED_STATUSES = {"superseded_on_origin_main"}
REMOTE_MERGED_LANES = {"remote-merged"}
REMOTE_MERGED_STATUSES = {"merged_pr_preserved"}
REMOTE_PR_OPEN_LANES = {"remote-pr-open"}
REMOTE_PR_OPEN_STATUSES = {"open_pr_preserved"}
OWNER_BLOCKER_LANES = {"owner-blocker"}
OWNER_BLOCKER_STATUSES = {"history_mismatch_patch_preserved", "private_patch_preserved"}
GENERATED_LOG_SHELL_FILES = {
    "logs/session-lifecycle-pressure.md",
    "logs/session-lifecycle-pressure.json",
}


class WorktreeDebtItem(TypedDict):
    name: str
    path: str
    reason: str
    debt: bool
    reapable: bool


class WorktreeDebtReport(TypedDict):
    total: int
    debt: int
    reapable: int
    by_reason: dict[str, int]
    by_reapable_reason: dict[str, int]
    items: list[WorktreeDebtItem]


def _git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def _remote_default_ref(cwd: Path) -> str | None:
    ref = _git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd)
    if ref.returncode == 0 and ref.stdout.strip():
        return ref.stdout.strip()
    for candidate in ("origin/main", "origin/master"):
        if _git(["show-ref", "--verify", "--quiet", f"refs/remotes/{candidate}"], cwd).returncode == 0:
            return candidate
    return None


def _reachable_from_remote(cwd: Path, head: str) -> bool:
    refs = _git(["for-each-ref", f"--contains={head}", "--format=%(refname)", "refs/remotes"], cwd)
    if refs.returncode != 0:
        return False
    return bool(refs.stdout.strip())


def _merged_into_default(cwd: Path, head: str) -> bool:
    ref = _remote_default_ref(cwd)
    return bool(ref and _git(["merge-base", "--is-ancestor", head, ref], cwd).returncode == 0)


def _patch_equivalent_to_default(cwd: Path) -> bool:
    ref = _remote_default_ref(cwd)
    if not ref:
        return False
    cherry = _git(["cherry", ref, "HEAD"], cwd)
    if cherry.returncode != 0:
        return False
    lines = [line.strip() for line in cherry.stdout.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("-") for line in lines)


def _git_toplevel(cwd: Path) -> Path | None:
    top = _git(["rev-parse", "--show-toplevel"], cwd)
    if top.returncode != 0 or not top.stdout.strip():
        return None
    try:
        return Path(top.stdout.strip()).resolve()
    except OSError:
        return Path(top.stdout.strip())


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _load_preservation_receipts(limen_root: Path) -> dict[str, dict[str, Any]]:
    path = limen_root / "docs" / "worktree-preservation-receipts.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    receipts: dict[str, dict[str, object]] = {}
    items = data.get("receipts")
    if isinstance(items, list):
        for receipt in items:
            if not isinstance(receipt, dict):
                continue
            root = receipt.get("root")
            if isinstance(root, str) and root:
                receipts[root] = receipt
    return receipts


def _is_documented_residue(path: Path, preservation_receipts: dict[str, dict[str, object]]) -> bool:
    receipt = preservation_receipts.get(path.name)
    if not receipt:
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    classification = str(receipt.get("classification") or "")
    return (
        lane in DOCUMENTED_RESIDUE_LANES
        or status in DOCUMENTED_RESIDUE_STATUSES
        or classification == "documented non-source residue"
    )


def _is_remote_superseded(path: Path, preservation_receipts: dict[str, dict[str, object]]) -> bool:
    receipt = preservation_receipts.get(path.name)
    if not receipt:
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    return lane in REMOTE_SUPERSEDED_LANES or status in REMOTE_SUPERSEDED_STATUSES


def _is_remote_merged(path: Path, preservation_receipts: dict[str, dict[str, object]]) -> bool:
    """Match the accepted reaper's loss-free merged-PR receipt predicate exactly."""
    receipt = preservation_receipts.get(path.name)
    if not receipt:
        return False
    if receipt.get("private_receipt") or receipt.get("private_patch_sha256"):
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    pr_state = str(receipt.get("pr_state") or "")
    pr_url = str(receipt.get("pr_url") or "")
    return (
        lane in REMOTE_MERGED_LANES
        and status in REMOTE_MERGED_STATUSES
        and pr_state == "MERGED"
        and pr_url.startswith("https://")
    )


def _is_remote_pr_open(path: Path, preservation_receipts: dict[str, dict[str, object]]) -> bool:
    receipt = preservation_receipts.get(path.name)
    if not receipt:
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    return lane in REMOTE_PR_OPEN_LANES or status in REMOTE_PR_OPEN_STATUSES


def _is_owner_blocker(path: Path, preservation_receipts: dict[str, dict[str, object]]) -> bool:
    receipt = preservation_receipts.get(path.name)
    if not receipt:
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    has_private_receipt = bool(receipt.get("private_receipt") or receipt.get("private_patch_sha256"))
    return has_private_receipt and (lane in OWNER_BLOCKER_LANES or status in OWNER_BLOCKER_STATUSES)


def is_generated_log_shell(path: Path) -> bool:
    """True for disposable non-git worktree shells containing only pressure receipts."""
    if not path.is_dir():
        return False
    try:
        files = {item.relative_to(path).as_posix() for item in path.rglob("*") if item.is_file()}
    except OSError:
        return False
    return bool(files) and files <= GENERATED_LOG_SHELL_FILES


def _agy_scratch_root() -> Path:
    home = os.environ.get("HOME", "/Users/4jp")
    return Path(os.environ.get("LIMEN_AGY_SCRATCH_ROOT", f"{home}/.gemini/antigravity-cli/scratch")).expanduser()


def _inside_agy_scratch_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(_agy_scratch_root().resolve())
        return True
    except (OSError, ValueError):
        return False


def _classify(
    path: Path,
    now: float,
    min_age_h: float,
    self_guard: set[Path],
    preservation_receipts: dict[str, dict[str, object]],
) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        return "unresolved"
    if resolved in self_guard:
        return "self/live-checkout"
    if _inside_agy_scratch_root(path):
        return "antigravity-scratch-managed"
    if _is_documented_residue(path, preservation_receipts):
        return "documented-residue"
    if _is_remote_superseded(path, preservation_receipts):
        return "remote-superseded"
    if _is_remote_pr_open(path, preservation_receipts):
        return "remote-pr-open"
    if _is_owner_blocker(path, preservation_receipts):
        return "owner-blocker"
    top = _git_toplevel(path)
    if top is None:
        if is_generated_log_shell(path):
            return "generated-log-shell"
        return "not-a-git-dir"
    if top != resolved:
        return "self/live-checkout" if top in self_guard else "not-a-git-dir"
    age_h = (now - path.stat().st_mtime) / 3600.0
    if age_h < min_age_h:
        return f"active(<{min_age_h:g}h)"
    if _git(["status", "--porcelain"], path).stdout.strip():
        return "dirty"
    if _is_remote_merged(path, preservation_receipts):
        return "receipt-remote-merged+clean+idle"
    head = _git(["rev-parse", "HEAD"], path).stdout.strip()
    patch_equivalent = _patch_equivalent_to_default(path)
    if not head or (not _reachable_from_remote(path, head) and not patch_equivalent):
        return "unpushed-commits"
    if not (_merged_into_default(path, head) or patch_equivalent):
        if _flag("LIMEN_RECLAIM_PUSHED_OK", False):
            return "clean+pushed+idle"
        return "not-merged-to-default"
    return "clean+merged+idle"


def worktree_debt_report(limen_root: Path | None = None, *, strict: bool = False) -> WorktreeDebtReport:
    """Classify every visible lifecycle target.

    Ordinary operational callers remain best-effort so an unavailable auxiliary scope cannot stop
    cleanup of healthy roots. Completion predicates must pass ``strict=True``: configured roots
    that cannot be read or registered repositories whose Git inventory fails then raise instead of
    disappearing from an apparently empty report.
    """
    root = limen_root or Path(os.environ.get("LIMEN_ROOT", f"{os.environ.get('HOME', '/Users/4jp')}/Workspace/limen"))
    self_guard: set[Path] = set()
    for candidate in (root, Path.cwd()):
        try:
            self_guard.add(candidate.resolve())
        except OSError:
            pass

    now = time.time()
    preservation_receipts = _load_preservation_receipts(root)
    items: list[WorktreeDebtItem] = []
    by_reason: dict[str, int] = {}
    by_reapable_reason: dict[str, int] = {}
    for target in iter_worktree_targets(root, strict=strict):
        path = target.path
        reason = _classify(path, now, target.min_age_h, self_guard, preservation_receipts)
        debt = reason in DEBT_REASONS
        reapable = reason in REAPABLE_REASONS
        by_reason[reason] = by_reason.get(reason, 0) + 1
        if reapable:
            by_reapable_reason[reason] = by_reapable_reason.get(reason, 0) + 1
        items.append({"name": path.name, "path": str(path), "reason": reason, "debt": debt, "reapable": reapable})

    debt_count = sum(1 for item in items if item["debt"])
    reapable_count = sum(1 for item in items if item["reapable"])
    return {
        "total": len(items),
        "debt": debt_count,
        "reapable": reapable_count,
        "by_reason": by_reason,
        "by_reapable_reason": by_reapable_reason,
        "items": items,
    }


def worktree_debt_zero(
    limen_root: Path | None = None,
    *,
    strict: bool = False,
) -> tuple[bool, WorktreeDebtReport]:
    """Exact-zero completion predicate. ``(debt == 0, report)``.

    There is no count cap: worktree lifecycle is complete only when EVERY preserved root has a
    terminal receipt (debt == 0). This replaces the retired ``worktree_debt_exceeded`` cap gate.
    """
    report = worktree_debt_report(limen_root, strict=strict)
    return report["debt"] == 0, report


def worktree_reapable_exceeded(limit: int | None = None) -> tuple[bool, WorktreeDebtReport, int]:
    effective_limit = limit
    if effective_limit is None:
        effective_limit = _int_env("LIMEN_WORKTREE_REAPABLE_MAX", 0)
    report = worktree_debt_report()
    return report["reapable"] > effective_limit, report, effective_limit


# ── Marginal live worktree-lifecycle admission ──────────────────────────────
#
# Every LOCAL_CHECKOUT_AGENT execution actually creates a worktree (dispatch runs each local lane
# in a fresh isolated checkout), so there is NO label/workstream that makes a local run
# non-worktree-creating — cleanup/receipt/substrate tasks create a worktree too. Impact is therefore
# binary and derives only from lane locality (limen.capacity.LOCAL_CHECKOUT_AGENTS / census
# local_checkout, resolved by the caller in dispatch.py):
#
#   IMPACT_REMOTE         — a non-local-checkout lane runs OFF-BOX; it creates no local worktree and
#                           is NEVER gated by local pressure.
#   IMPACT_DEBT_CREATING  — a local-checkout lane will spawn a fresh worktree (+1 local custody).
#
# A new local worktree is admitted only when the host can take custody of it. That decision folds
# THREE existing authoritative truths and fails CLOSED for new local creation on any unknown state
# (remote always continues):
#
#   1. RESOURCE  — free disk on ``effective_worktree_root()`` (where the worktree is actually
#                  created) vs the registered ``LIMEN_DISK_FLOOR_GIB`` parameter. Unknown free space
#                  or unknown floor → blocked.
#   2. VITALS    — ``vigilia.vitals.beat_gate(shed=False)``; ``action == 'shed'`` (critical memory
#                  pressure) blocks local +1. ``throttle`` is NOT a block here — it is already served
#                  by the separate reduced-concurrency ceiling, and we invent no score.
#   3. REAPER    — the heartbeat reaper must be live in apply mode. Standing acceptance versus
#                  explicit per-root acceptance is reaper policy, not liveness. A
#                  cheap direct target inventory decides whether a durable apply receipt is needed;
#                  no target needs no receipt after live enablement is proven. With any target, the
#                  marker and final receipt must agree, be fresh on the scheduler's worst-case
#                  cadence, and have no ``deferred_over_cap`` roots. Failed/kept roots are
#                  owner-routed individually and never globally block.
#
# Local CONCURRENCY remains the SEPARATE slot authority (``_running_local`` vs the
# ``--local-per-lane`` / ``LIMEN_LOCAL_LIMIT`` cap in ``dispatch-async.py``); it is not re-derived
# here. Exact-zero debt is the completion predicate (``worktree_debt_zero``); there is no count cap.

IMPACT_REMOTE = "remote"
IMPACT_DEBT_CREATING = "debt-creating"


class WorktreeAdmissionSnapshot(TypedDict):
    active: bool  # gate enabled for this dispatch cycle
    block_new_local: bool  # any authoritative reason to fail closed for a NEW LOCAL worktree
    reason: str  # first applicable block reason
    resource_blocked: bool  # free disk < floor, or disk/floor unknown
    vitals_shed: bool  # VITALS critical-memory shed
    reaper_blocked: bool  # target inventory/reaper state cannot prove bounded drain
    free_gib: float | None  # observed free space on effective_worktree_root()
    floor_gib: float | None  # positive registered LIMEN_DISK_FLOOR_GIB (None → unknown)
    reserved_gib: float  # checkout bytes already promised to selected LOCAL candidates
    room_gib: float | None  # free - floor - reserved; None when resource truth is unknown
    targets_present: bool | None  # cheap direct target inventory (None → unknown/fail closed)
    debt: int | None  # cached lifecycle-pressure diagnostic; never admission authority
    vitals_action: str  # 'ok' | 'throttle' | 'shed'


def _gate_active() -> bool:
    """Fail closed active; only the documented explicit ``0``/``false`` disables admission."""
    value = _live_parameter("LIMEN_WORKTREE_DEBT_GATE")
    if value is False or value == 0:
        return False
    if isinstance(value, str) and value.strip().lower() in {"0", "false"}:
        return False
    return True


def _worktree_disk_free_gib(path: Path) -> float | None:
    """Free GiB on ``path``'s partition, walking up to the first existing ancestor."""
    probe = path
    for _ in range(64):
        try:
            return shutil.disk_usage(probe).free / (1024**3)
        except OSError:
            parent = probe.parent
            if parent == probe:
                return None
            probe = parent
    return None


def _scalar_float(value: object) -> float | None:
    """Coerce a simple configuration/receipt scalar to a float."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _finite_float(value: object) -> float | None:
    """Coerce a simple configuration/receipt scalar to a finite float."""
    number = _scalar_float(value)
    return number if number is not None and math.isfinite(number) else None


def _disk_floor_gib() -> float | None:
    """Registered LIMEN_DISK_FLOOR_GIB (env override > panel default). None if unresolvable.

    Uses the parameter-panel authority — never a hardcoded fallback number.
    """
    raw = _live_parameter("LIMEN_DISK_FLOOR_GIB")
    floor = _finite_float(raw)
    return floor if floor is not None and floor > 0 else None


def _vitals_action() -> str:
    """VITALS action ('ok'|'throttle'|'shed'); fail-open to 'ok' on any fault."""
    try:
        from limen.vigilia import vitals

        return str(vitals.beat_gate(shed=False).get("action") or "ok")
    except Exception:
        return "ok"


def _live_parameter(name: str) -> object | None:
    """Read a registered VIGILIA parameter, preserving fail-closed ``None`` on faults."""
    try:
        from limen.vigilia import params as _params

        return _params.get(name, None)
    except Exception:
        return os.environ.get(name)


def _live_enabled(name: str) -> bool:
    """Only the registered, explicit value ``1`` proves a reaper switch is live."""
    value = _live_parameter(name)
    return str(value).strip() == "1" if value is not None else False


def _positive_finite_parameter(name: str) -> float | None:
    number = _finite_float(_live_parameter(name))
    return number if number is not None and number > 0 else None


def _reaper_freshness_minutes() -> float | None:
    """Worst-case scheduler window, derived only from registered live parameters."""
    every_min = _positive_finite_parameter("LIMEN_RECLAIM_EVERY_MIN")
    beat_drain = _positive_finite_parameter("LIMEN_BEAT_DRAIN")
    loop_max_seconds = _positive_finite_parameter("LIMEN_LOOP_MAX")
    timeout_seconds = _positive_finite_parameter("LIMEN_RECLAIM_TIMEOUT")
    if None in (every_min, beat_drain, loop_max_seconds, timeout_seconds):
        return None
    assert every_min is not None
    assert beat_drain is not None
    assert loop_max_seconds is not None
    assert timeout_seconds is not None
    return max(
        2 * every_min,
        beat_drain * loop_max_seconds / 60 + timeout_seconds / 60,
    )


def _last_nonblank_line(path: Path, *, chunk_size: int = 8192) -> bytes | None:
    """Reverse-tail ``path`` and return only its final nonblank line.

    Normal receipts cost one bounded tail read regardless of log size. A final line longer than one
    chunk is assembled backwards as needed; earlier log records are never parsed.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            position = handle.tell()
            suffix = b""
            while position > 0:
                size = min(chunk_size, position)
                position -= size
                handle.seek(position)
                suffix = handle.read(size) + suffix
                candidate = suffix.rstrip()
                newline = candidate.rfind(b"\n")
                if newline >= 0:
                    return candidate[newline + 1 :]
            candidate = suffix.strip()
            return candidate or None
    except OSError:
        return None


def _last_reclaim_event(log_path: Path) -> tuple[dict[str, Any] | None, str]:
    """Parse exactly the final nonblank reclaim receipt; malformed tails fail closed."""
    line = _last_nonblank_line(log_path)
    if line is None:
        return None, "reclaim receipt missing or empty"
    try:
        event = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "final reclaim receipt is malformed or truncated"
    if not isinstance(event, dict):
        return None, "final reclaim receipt is not an object"
    return event, ""


def _cached_worktree_debt(root: Path) -> int | None:
    """Read the cheap lifecycle-pressure debt diagnostic without making it authority."""
    try:
        payload = json.loads((root / "logs" / "session-lifecycle-pressure.json").read_text(encoding="utf-8"))
        worktrees = payload.get("worktrees") if isinstance(payload, dict) else None
        debt = worktrees.get("debt") if isinstance(worktrees, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(debt, bool) or not isinstance(debt, int) or debt < 0:
        return None
    return debt


def _reaper_blocks_new_local(root: Path, targets_present: bool | None) -> tuple[bool, str]:
    """Whether durable live-reaper truth blocks a NEW LOCAL worktree."""
    for switch in (
        "LIMEN_RECLAIM",
        "LIMEN_RECLAIM_APPLY",
    ):
        if not _live_enabled(switch):
            return True, f"{switch} is not live at 1 — heartbeat reaper cannot drain"
    if targets_present is None:
        return True, "worktree target inventory unknown — failing closed for new local worktree"
    if not targets_present:
        return False, ""

    marker = root / "logs" / ".reclaim-last"
    log = root / "logs" / "reclaim-worktrees.jsonl"

    event, event_error = _last_reclaim_event(log)
    if event is None:
        return True, f"worktree targets present: {event_error}"
    if event.get("apply") is not True:
        return True, "worktree targets present: final reclaim receipt is not an apply run"

    event_ts = _scalar_float(event.get("ts"))
    if event_ts is None:
        return True, "worktree targets present: reclaim event timestamp is invalid"
    if not math.isfinite(event_ts) or event_ts <= 0:
        return True, "worktree targets present: reclaim event timestamp is not finite and positive"

    completed_ts_raw = event.get("completed_ts")
    if completed_ts_raw is None:
        return True, "worktree targets present: strict receipt missing finite completed_ts; await next apply run"
    completed_ts = _scalar_float(completed_ts_raw)
    if completed_ts is None:
        return True, "worktree targets present: reclaim completion timestamp is invalid"
    if not math.isfinite(completed_ts) or completed_ts <= 0:
        return True, "worktree targets present: reclaim completion timestamp is not finite and positive"

    deferred = event.get("deferred_over_cap")
    if not isinstance(deferred, list):
        return True, "worktree targets present: deferred_over_cap is not a list"
    if deferred:
        return True, f"reaper deferred {len(deferred)} root(s) over cap — target inventory not draining"

    try:
        marker_text = marker.read_text(encoding="utf-8").strip()
        marker_ts = float(marker_text)
        marker_mtime = marker.stat().st_mtime
        log_mtime = log.stat().st_mtime
    except (OSError, TypeError, ValueError):
        return True, "worktree targets present: reclaim marker/receipt is missing or unreadable"
    if not all(math.isfinite(value) and value > 0 for value in (marker_ts, marker_mtime, log_mtime)):
        return True, "worktree targets present: reclaim marker/receipt timestamp is not finite and positive"
    if marker_ts != completed_ts:
        return True, "worktree targets present: reclaim marker does not match final receipt"

    freshness_min = _reaper_freshness_minutes()
    if freshness_min is None:
        return True, "worktree targets present: reclaim scheduler parameters are invalid"
    now = time.time()
    durable_mtime = min(marker_mtime, log_mtime)
    if not math.isfinite(now) or event_ts > completed_ts or completed_ts > durable_mtime or durable_mtime > now:
        return True, "worktree targets present: reclaim receipt chronology is invalid or future-dated"
    age_min = (now - completed_ts) / 60
    if age_min > freshness_min:
        return True, (
            f"reclaim receipt stale ({age_min:.0f}min > {freshness_min:.0f}min scheduler window) "
            "— target inventory not draining"
        )
    return False, ""


def take_admission_snapshot(limen_root: Path | None = None) -> WorktreeAdmissionSnapshot:
    """One admission reading for a whole dispatch cycle, folding resource + VITALS + reaper truth.

    Fails CLOSED for NEW LOCAL creation on any unknown state; remote lanes always continue.
    """
    root = limen_root or Path(os.environ.get("LIMEN_ROOT", "."))
    floor = _disk_floor_gib()
    if not _gate_active():
        # Operator override (LIMEN_WORKTREE_DEBT_GATE=0, documented reason/receipt): admit everything.
        return {
            "active": False,
            "block_new_local": False,
            "reason": "",
            "resource_blocked": False,
            "vitals_shed": False,
            "reaper_blocked": False,
            "free_gib": None,
            "floor_gib": floor,
            "reserved_gib": 0.0,
            "room_gib": None,
            "targets_present": None,
            "debt": None,
            "vitals_action": "ok",
        }

    # 1. RESOURCE custody on the root where the worktree is actually created.
    partition = effective_worktree_root()
    free = _worktree_disk_free_gib(partition)
    if free is None or floor is None:
        resource_blocked = True
        resource_reason = f"disk/floor unknown ({partition}) — failing closed for new local worktree"
    else:
        resource_blocked = free < floor
        resource_reason = f"local free {free:.1f} GiB < {floor:g} GiB floor on {partition}" if resource_blocked else ""

    # 2. VITALS memory-pressure shed.
    vitals_action = _vitals_action()
    vitals_shed = vitals_action == "shed"

    # 3. REAPER drain state from cheap direct inventory. Full classification is completion-only and
    # never runs in this dispatch hot path. The lifecycle-pressure debt count is display-only cache.
    try:
        targets = iter_worktree_targets(root, strict=True)
        targets_present: bool | None = bool(targets) if isinstance(targets, list) else None
    except Exception:
        targets_present = None
    debt = _cached_worktree_debt(root)
    reaper_blocked, reaper_reason = _reaper_blocks_new_local(root, targets_present)

    block = resource_blocked or vitals_shed or reaper_blocked
    if resource_blocked:
        reason = resource_reason
    elif vitals_shed:
        reason = "VITALS shed (critical memory pressure) — no new local worktree this beat"
    elif reaper_blocked:
        reason = reaper_reason
    else:
        reason = ""

    return {
        "active": True,
        "block_new_local": block,
        "reason": reason,
        "resource_blocked": resource_blocked,
        "vitals_shed": vitals_shed,
        "reaper_blocked": reaper_blocked,
        "free_gib": free,
        "floor_gib": floor,
        "reserved_gib": 0.0,
        "room_gib": max(0.0, free - floor) if free is not None and floor is not None else None,
        "targets_present": targets_present,
        "debt": debt,
        "vitals_action": vitals_action,
    }


def admission_blocks(
    impact: str,
    snapshot: WorktreeAdmissionSnapshot,
    checkout_gib: float | None = None,
    *,
    reserve: bool = False,
) -> tuple[bool, str]:
    """Per-candidate admission decision → ``(blocked, reason)``.

    Remote lanes are never blocked. A local (debt-creating) candidate is blocked whenever the
    snapshot's fail-closed ``block_new_local`` is set (resource, VITALS shed, or reaper not draining),
    when its tracked-HEAD checkout size is unknown, or when the cycle's remaining unreserved disk
    room cannot hold it. ``reserve=True`` mutates this cycle snapshot only after the caller has
    actually selected the candidate; merely scanning a candidate never consumes room.
    """
    if not snapshot.get("active"):
        return False, ""
    if impact == IMPACT_REMOTE:
        return False, ""
    if snapshot.get("block_new_local"):
        return True, snapshot.get("reason") or "new local worktree blocked (host cannot take custody)"

    if isinstance(checkout_gib, bool) or checkout_gib is None:
        return True, "tracked HEAD checkout size is unknown — failing closed for new local worktree"
    estimate = _finite_float(checkout_gib)
    if estimate is None:
        return True, "tracked HEAD checkout size is unknown — failing closed for new local worktree"
    if estimate <= 0:
        return True, "tracked HEAD checkout size is invalid — failing closed for new local worktree"

    room_raw = snapshot.get("room_gib")
    if isinstance(room_raw, bool) or room_raw is None:
        free = snapshot.get("free_gib")
        floor = snapshot.get("floor_gib")
        reserved = snapshot.get("reserved_gib", 0.0)
        free_number = _finite_float(free)
        floor_number = _finite_float(floor)
        reserved_number = _finite_float(reserved)
        if free_number is None or floor_number is None or reserved_number is None:
            return True, "local checkout room is unknown — failing closed for new local worktree"
        room = max(0.0, free_number - floor_number - reserved_number)
    else:
        room_number = _finite_float(room_raw)
        if room_number is None:
            return True, "local checkout room is unknown — failing closed for new local worktree"
        room = room_number
    if room < 0:
        return True, "local checkout room is invalid — failing closed for new local worktree"
    if estimate > room:
        return True, f"tracked HEAD checkout needs {estimate:.3f} GiB but only {room:.3f} GiB remains above floor"

    if reserve:
        reserved_raw = snapshot.get("reserved_gib", 0.0)
        current_reserved = _finite_float(reserved_raw)
        if current_reserved is None:
            return True, "local checkout reservation state is invalid — failing closed"
        if current_reserved < 0:
            return True, "local checkout reservation state is invalid — failing closed"
        snapshot["reserved_gib"] = current_reserved + estimate
        snapshot["room_gib"] = room - estimate
    return False, ""
