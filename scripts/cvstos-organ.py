#!/usr/bin/env python3
"""cvstos-organ.py — CVSTOS, THE KEEPER OF THE HOST.

The posture this organ exists to hold: *the Mac stays FACTORY; the system I'm building lives in
an ejectable CARTRIDGE (chezmoi → organvm/domus-genoma).* Nothing should be truly on the PATH or
local. CVSTOS (custos = the keeper/guardian) owns the TERMINAL stage of the local-artifact
lifecycle — **eviction readiness** — the stage that today never becomes accepted cleanup, which is
why the host accretes:

    spawn → work → preserve-to-cartridge → accepted eviction from host → factory restored

Three departments, each fail-open, none blocking another, all READ-ONLY on the host
(they size and classify; regenerable cache is reported, not physically removed):

  EVICTVS  — the debt the chat/agent apps leave on the host, for EVERY vendor, not just Claude:
             ChatGPT, Cursor, Windsurf, Copilot, the Claude desktop app, and Claude Code's own
             image-cache / jobs / shell-snapshots. Regenerable cache → an eviction candidate;
             irreplaceable/unsynced state (conversation blobs, ~/.claude/projects transcripts) →
             surfaced with its byte weight and NEVER touched. library-preserve.py already evicts
             ~/Library dev/build caches; EVICTVS covers the chat-app volumes it never enumerated.

  LIMES    — the factory-host invariant (limes = the frontier/boundary). Measures whether the
             posture actually holds: is the cartridge plugged in (chezmoi → organvm/domus-genoma);
             are there scripts on ~/.local/bin not backed by a cartridge source; are brew formulae
             installed but absent from the Brewfile manifest. Each orphan is system state that
             leaked onto the host instead of living in the cartridge. This is the predicate the
             posture demanded but nothing measured.

  PROPRIVS — one liveness roof over the scattered reapers (worktree / clone / branch / preserve).
             They run inline in the hygiene + backup voices with no health face of their own, so a
             stale or broken reaper is invisible and creep goes unbounded. Here it becomes visible.

DATA / SAFETY (the whole point — this organ must not become a side-door deletion surface):
  - READ-ONLY on the host. Physical cache removal needs a separate archive/redaction acceptance
    surface. Irreplaceable / unsynced app state is never an eviction candidate — it is surfaced so
    the human decides, matching library-preserve.py's "never auto-delete personal data" precedent.
  - Writes a COUNTS-ONLY liveness stamp to logs/cvstos-organ-state.json (bytes + counts only; no
    file contents, no per-file paths beyond app/dir names) so organ-health.py sees it fired.
  - Fail-open everywhere + lockless: a missing app, absent chezmoi, unreadable dir → a "skipped"
    note, never a crash, never a blocked beat.
  - Crawls the host with os.scandir to derive its census (the AVTOPOIESIS 'past' tense) — it does
    not read a hand-authored file.

  --check : the executable Definition of Done (exit 0 ⟺ the host is at factory). Composes the
            already-shipped cartridge-connected.py and worktree-debt.py predicates and adds the
            chat-app-debt + bin-orphan measures. exit 1 names each unmet invariant.
  --apply : compatibility flag — report the regenerable chat-app cache bytes that an accepted
            cache-reap organ could reclaim. It does not physically remove files.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
HOME = Path.home()

GB = 1024**3


def _env_positive_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value > 0 else default


def _env_positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


DEBT_CAP_GB = _env_positive_float("LIMEN_CVSTOS_DEBT_CAP_GB", 5)  # evictable chat-app cache over this ⇒ over cap
REAPER_STALE_H = _env_positive_float("LIMEN_CVSTOS_REAPER_STALE_H", 48)  # a reaper stamp older than this ⇒ stale
SCAN_ENTRY_CAP = _env_positive_int("LIMEN_CVSTOS_SCAN_CAP", 600000)  # bound the walk so a pathological tree can't hang the beat
AGY_SCRATCH_ROOT = Path(
    os.environ.get("LIMEN_AGY_SCRATCH_ROOT", HOME / ".gemini" / "antigravity-cli" / "scratch")
)
AGY_SCRATCH_MIN_IDLE_H = _env_positive_float("LIMEN_AGY_SCRATCH_MIN_IDLE_H", 24)
AGY_SCRATCH_PRESERVATION_LEDGER = ROOT / "docs" / "antigravity-scratch-preservation.jsonl"
AGY_UNSAFE_DISPOSITIONS = {
    "bridge_required",
    "preserve_required",
    "container_review_required",
    "non_git_review_required",
}

# Chromium/Electron subdirectories that regenerate on next launch — safe eviction candidates.
_REGEN_SUBDIRS = {
    "Cache",
    "Code Cache",
    "CachedData",
    "GPUCache",
    "DawnCache",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
    "ShaderCache",
    "GrShaderCache",
    "Crashpad",
    "logs",
    "Log",
    "blob_storage",
    "component_crx_cache",
    "Service Worker",
}

# The chat/agent-app debt map. Each entry: (app, home-relative glob, kind).
#   electron  — an app-support root; total sized, evictable = the regen subdirs within, rest retained.
#   regen     — the whole path is regenerable cache (an eviction candidate).
#   retained  — the whole path is irreplaceable / unsynced state (surfaced, never an eviction candidate).
_TARGETS = [
    ("ChatGPT", "Library/Application Support/com.openai.chat", "electron"),
    ("ChatGPT", "Library/Caches/com.openai.chat", "regen"),
    ("Cursor", "Library/Application Support/Cursor", "electron"),
    ("Cursor", "Library/Caches/com.todesktop.*", "regen"),
    ("Windsurf", "Library/Application Support/Windsurf", "electron"),
    ("Windsurf", "Library/Caches/com.exafunction.*", "regen"),
    ("Windsurf", "Library/Caches/com.codeium.*", "regen"),
    ("Copilot", "Library/Application Support/GitHub Copilot", "electron"),
    ("Claude Desktop", "Library/Application Support/Claude", "electron"),
    ("Claude Desktop", "Library/Caches/com.anthropic.*", "regen"),
    ("Claude Code", ".claude/image-cache", "regen"),
    ("Claude Code", ".claude/jobs", "regen"),
    ("Claude Code", ".claude/shell-snapshots", "regen"),
    ("Claude Code", ".claude/statsig", "regen"),
    ("Claude Code", ".claude/todos", "retained"),
    (
        "Claude Code",
        ".claude/projects",
        "retained",
    ),  # atomized into the corpus, but the raw transcripts are his — surface only
]

# A ~/.local/bin entry that resolves under one of these is package-manager-provisioned (pipx, brew,
# cargo, go, npm, …) — it survives a re-flash iff the manager's manifest is in the cartridge, which
# is the pkg_drift axis, NOT a hand-dropped host orphan. Only a real file backed by nothing is a leak.
_PM_PREFIXES = (
    "/opt/homebrew",
    "/usr/local/Cellar",
    "/usr/local/opt",
    str(HOME / ".local" / "pipx"),
    str(HOME / ".local" / "opt"),
    str(HOME / ".local" / "share" / "claude"),
    str(HOME / ".local" / "share" / "pipx"),
    str(HOME / ".local" / "share" / "uv"),
    str(HOME / ".cargo"),
    str(HOME / ".rustup"),
    str(HOME / "go"),
    str(HOME / ".bun"),
    str(HOME / ".deno"),
    str(HOME / ".volta"),
    str(HOME / ".nvm"),
    "/usr/local/lib/node_modules",
    str(HOME / ".npm-global"),
    str(HOME / ".local" / "share" / "mise"),
)


# ── bounded filesystem sizing (fail-open) ────────────────────────────────────────────────────
def _dir_bytes(path: Path) -> tuple[int, bool]:
    """Sum of file sizes under `path`, bounded by SCAN_ENTRY_CAP entries. Returns (bytes, approx).
    approx=True means the cap was hit and the real size is larger. Never raises."""
    total, seen, approx = 0, 0, False
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    seen += 1
                    if seen > SCAN_ENTRY_CAP:
                        return total, True
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(Path(e.path))
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total, approx


def _expand(glob_rel: str) -> list[Path]:
    """Expand a home-relative path or glob to existing paths. Never raises."""
    try:
        if any(c in glob_rel for c in "*?["):
            parts = glob_rel.split("/")
            base = HOME
            # walk fixed prefix, then glob the remainder
            i = 0
            for i, p in enumerate(parts):
                if any(c in p for c in "*?["):
                    break
                base = base / p
            pattern = "/".join(parts[i:])
            return [p for p in base.glob(pattern) if p.exists()]
        p = HOME / glob_rel
        return [p] if p.exists() else []
    except OSError:
        return []


# ── EVICTVS — the chat-app debt census ───────────────────────────────────────────────────────
def census_debt() -> dict:
    apps: dict[str, dict] = {}
    approx_any = False
    for app, glob_rel, kind in _TARGETS:
        for path in _expand(glob_rel):
            total, approx = _dir_bytes(path)
            approx_any = approx_any or approx
            evict = 0
            if kind == "regen":
                evict = total
            elif kind == "electron":
                for sub in _REGEN_SUBDIRS:
                    sp = path / sub
                    if sp.is_dir():
                        b, a = _dir_bytes(sp)
                        evict += b
                        approx_any = approx_any or a
            # kind == "retained" ⇒ evict stays 0 (surfaced only)
            a = apps.setdefault(app, {"total": 0, "evictable": 0, "retained": 0, "dirs": 0})
            a["total"] += total
            a["evictable"] += evict
            a["retained"] += total - evict
            a["dirs"] += 1
    evictable = sum(a["evictable"] for a in apps.values())
    retained = sum(a["retained"] for a in apps.values())
    return {
        "apps": apps,
        "evictable_bytes": evictable,
        "retained_bytes": retained,
        "evictable_gb": round(evictable / GB, 2),
        "retained_gb": round(retained / GB, 2),
        "over_cap": evictable > DEBT_CAP_GB * GB,
        "cap_gb": DEBT_CAP_GB,
        "approx": approx_any,
    }


def reclaim_debt(census: dict) -> int:
    """--apply compatibility: report regenerable eviction candidates without removing them.

    Only regen/electron-cache classes are counted; retained paths are never touched. Physical cache
    removal belongs to a future acceptance-gated cache reaper.
    """
    reclaimed = 0
    for _app, glob_rel, kind in _TARGETS:
        if kind == "retained":
            continue
        for path in _expand(glob_rel):
            targets = [path] if kind == "regen" else [path / s for s in _REGEN_SUBDIRS if (path / s).is_dir()]
            for t in targets:
                b, _ = _dir_bytes(t)
                reclaimed += b
    return reclaimed


# ── LIMES — the factory-host invariant ───────────────────────────────────────────────────────
def _run(cmd: list[str], timeout: float = 20.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)  # noqa: S603
        return p.returncode, (p.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def _cartridge_connected() -> bool | None:
    """Reuse the shipped predicate. True=connected, False=unplugged, None=unmeasurable (fail-open)."""
    script = ROOT / "scripts" / "cartridge-connected.py"
    if not script.exists():
        return None
    rc, _ = _run([sys.executable, str(script)])
    if rc == 127:
        return None
    return rc == 0


def _chezmoi_managed() -> set[str] | None:
    if not shutil.which("chezmoi"):
        return None
    rc, out = _run(["chezmoi", "managed", "--path-style", "absolute"])
    if rc != 0 or not out.strip():
        rc, out = _run(["chezmoi", "managed"])
        if rc != 0:
            return None
        return {str((HOME / ln.strip()).resolve()) for ln in out.splitlines() if ln.strip()}
    return {str(Path(ln.strip()).resolve()) for ln in out.splitlines() if ln.strip()}


def _chezmoi_source_dir() -> Path | None:
    if not shutil.which("chezmoi"):
        return None
    rc, out = _run(["chezmoi", "source-path"])
    if rc != 0 or not out.strip():
        return None
    return Path(out.strip())


def _shebang_interp(path: Path) -> str | None:
    """The interpreter a script's shebang points at (or None). A pip/uv/pipx console-script is a
    regular file whose shebang references its manager's venv — the general way to tell a
    package-provisioned entrypoint from a hand-dropped script."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(256)
    except OSError:
        return None
    if head[:2] != b"#!":
        return None
    line = head.split(b"\n", 1)[0][2:].decode("utf-8", "ignore").strip()
    return line.split()[0] if line else None


def bin_orphans() -> dict:
    """Scripts on ~/.local/bin that the cartridge does not back. A brew/pipx symlink, a uv/pip
    console-script (shebang into a manager venv), or a symlink into the chezmoi source is fine; a
    real hand-dropped file that no manager and no cartridge source backs is an orphan (system state
    leaked to the host that would not survive a re-flash)."""
    bindir = HOME / ".local" / "bin"
    if not bindir.is_dir():
        return {"measured": False, "count": 0, "names": []}
    managed = _chezmoi_managed()
    if managed is None:
        return {"measured": False, "count": 0, "names": []}
    source = _chezmoi_source_dir()
    orphans: list[str] = []
    try:
        entries = list(bindir.iterdir())
    except OSError:
        return {"measured": False, "count": 0, "names": []}
    for e in entries:
        try:
            if e.name == "__pycache__" and e.is_dir():
                continue  # generated bytecode cache, not a hand-dropped PATH script
            if str(e) in managed:
                continue  # chezmoi backs it (target path, before resolving symlinks)
            real = e.resolve()
            rp = str(real)
            if rp in managed:
                continue
            if any(rp.startswith(pfx) for pfx in _PM_PREFIXES):
                continue  # symlink into a package manager ⇒ domus's manifest axis, not a host orphan
            if source is not None and str(source) in rp:
                continue  # a symlink into the chezmoi source dir
            if e.is_symlink() and not real.exists():
                continue  # dangling symlink is a different hygiene problem, not a host orphan
            interp = _shebang_interp(e)
            if interp and any(interp.startswith(pfx) for pfx in _PM_PREFIXES):
                continue  # a uv/pip/pipx console-script ⇒ manager-provisioned, not hand-dropped
            orphans.append(e.name)
        except OSError:
            continue
    return {"measured": True, "count": len(orphans), "names": sorted(orphans)[:40]}


def domus_pkg_report() -> dict:
    """DELEGATE to domus — package-manifest drift is domus's owned concern, not CVSTOS's to
    re-adjudicate (its report floods 'extra' for every transitive brew dep). CVSTOS only surfaces a
    pointer: does domus see drift at all. Advisory — never a hard-predicate failure here."""
    if not shutil.which("domus"):
        return {"measured": False, "drift": False}
    rc, out = _run(["domus", "packages", "diff"])
    if rc == 127:
        return {"measured": False, "drift": False}
    drift = any(ln.lstrip().startswith(("+ ", "- ")) for ln in out.splitlines())
    return {"measured": True, "drift": drift}


def factory_invariant() -> dict:
    return {
        "cartridge_connected": _cartridge_connected(),
        "bin_orphans": bin_orphans(),
        "domus_packages": domus_pkg_report(),
    }


# ── PROPRIVS — one liveness roof over the reapers ────────────────────────────────────────────
_REAPERS = [
    ("worktree+clone+branch", LOGS / ".voice" / "hygiene"),  # all three ride clone-maintenance.sh (hygiene voice)
    ("preserve", LOGS / ".voice" / "backup"),  # library-preserve.py (backup voice)
    ("branch-reap", LOGS / "reap-branches-state.json"),  # stamped every run
    ("pressure-gauge", LOGS / "session-lifecycle-pressure.json"),
]


def reaper_proprioception() -> dict:
    now = time.time()
    rows = []
    fresh = stale = unknown = 0
    for name, path in _REAPERS:
        try:
            age_h = (now - path.stat().st_mtime) / 3600.0
        except OSError:
            rows.append({"reaper": name, "state": "unknown", "age_h": None})
            unknown += 1
            continue
        state = "fresh" if age_h <= REAPER_STALE_H else "stale"
        rows.append({"reaper": name, "state": state, "age_h": round(age_h, 1)})
        fresh += state == "fresh"
        stale += state == "stale"
    return {"reapers": rows, "fresh": fresh, "stale": stale, "unknown": unknown, "stale_after_h": REAPER_STALE_H}


def _worktree_over_cap() -> bool | None:
    script = ROOT / "scripts" / "worktree-debt.py"
    if not script.exists():
        return None
    rc, _ = _run([sys.executable, str(script), "--fail-over-cap"])
    if rc == 127:
        return None
    return rc != 0


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _matching_preservation(row: dict, history: list[dict]) -> dict | None:
    name = str(row.get("name") or "")
    head = row.get("head")
    disposition = row.get("disposition")
    size_bytes = row.get("size_bytes")
    for event in reversed(history):
        if event.get("root") != name:
            continue
        if not event.get("archive_verified"):
            continue
        if not event.get("archive_path"):
            continue
        if not event.get("private_receipt") or not event.get("private_receipt_sha256"):
            continue
        if head and event.get("head") and event.get("head") != head:
            continue
        if disposition and event.get("disposition") and event.get("disposition") != disposition:
            continue
        if size_bytes is not None and event.get("size_bytes") is not None:
            try:
                if int(event["size_bytes"]) != int(size_bytes):
                    continue
            except (TypeError, ValueError):
                continue
        return event
    return None


def _count_by_disposition(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("disposition") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def antigravity_scratch() -> dict:
    script = ROOT / "scripts" / "antigravity-scratch-bridge.py"
    if not script.exists():
        return {"measured": False, "reason": "bridge-missing"}
    rc, out = _run(
        [
            sys.executable,
            str(script),
            "--root",
            str(AGY_SCRATCH_ROOT),
            "--min-idle-hours",
            str(AGY_SCRATCH_MIN_IDLE_H),
            "--json",
        ],
        timeout=180,
    )
    if rc != 0:
        return {"measured": False, "reason": "bridge-failed", "returncode": rc}
    try:
        report = json.loads(out)
    except ValueError:
        return {"measured": False, "reason": "invalid-json"}
    summary = report.get("summary") or {}
    by_disp = summary.get("by_disposition") or {}
    unsafe_rows = [row for row in report.get("roots", []) if row.get("disposition") in AGY_UNSAFE_DISPOSITIONS]
    preservation_history = _load_jsonl(AGY_SCRATCH_PRESERVATION_LEDGER)
    preserved_unsafe = []
    unpreserved_unsafe = []
    for row in unsafe_rows:
        if _matching_preservation(row, preservation_history):
            preserved_unsafe.append(row)
        else:
            unpreserved_unsafe.append(row)
    return {
        "measured": True,
        "root": str(AGY_SCRATCH_ROOT),
        "total_roots": int(summary.get("total_roots") or 0),
        "total_bytes": int(summary.get("total_bytes") or 0),
        "total_gb": round(int(summary.get("total_bytes") or 0) / GB, 2),
        "safe_reap_bytes": int(summary.get("safe_reap_bytes") or 0),
        "safe_reap_gb": round(int(summary.get("safe_reap_bytes") or 0) / GB, 2),
        "by_disposition": by_disp,
        "unsafe_dispositions": _count_by_disposition(unsafe_rows),
        "unsafe_preserved_dispositions": _count_by_disposition(preserved_unsafe),
        "unsafe_unpreserved_dispositions": _count_by_disposition(unpreserved_unsafe),
        "unsafe_unpreserved_roots": [row.get("name") for row in unpreserved_unsafe if row.get("name")],
    }


# ── assembly ─────────────────────────────────────────────────────────────────────────────────
def assess() -> dict:
    return {
        "debt": census_debt(),
        "factory": factory_invariant(),
        "reapers": reaper_proprioception(),
        "worktree_over_cap": _worktree_over_cap(),
        "antigravity_scratch": antigravity_scratch(),
    }


def failures(a: dict) -> list[str]:
    """The Definition of Done, as a list of unmet invariants. Empty ⇒ the host is at factory.
    Unmeasurable signals never fail the predicate — only a measured leak does."""
    out = []
    fac = a["factory"]
    if fac["cartridge_connected"] is False:
        out.append("cartridge UNPLUGGED (chezmoi source is not organvm/domus-genoma)")
    if fac["bin_orphans"]["measured"] and fac["bin_orphans"]["count"] > 0:
        out.append(f"{fac['bin_orphans']['count']} hand-dropped script(s) on ~/.local/bin not backed by the cartridge")
    if a["reapers"]["stale"] > 0:
        out.append(f"{a['reapers']['stale']} reaper(s) stale (no fire in {REAPER_STALE_H:g}h)")
    if a["worktree_over_cap"] is True:
        out.append("worktree debt over cap (worktree-debt.py --fail-over-cap)")
    if a["debt"]["over_cap"]:
        out.append(
            f"chat-app evictable cache {a['debt']['evictable_gb']}GB over the {a['debt']['cap_gb']:g}GB cap "
            "(eviction stage has not fired — run --apply or arm the reclaimer)"
        )
    agy = a.get("antigravity_scratch") or {}
    unpreserved_unsafe = agy.get("unsafe_unpreserved_dispositions")
    if unpreserved_unsafe is None:
        unpreserved_unsafe = agy.get("unsafe_dispositions")
    if agy.get("measured") and unpreserved_unsafe:
        unsafe = ", ".join(f"{key}={count}" for key, count in sorted(unpreserved_unsafe.items()))
        out.append(f"Antigravity scratch roots need bridge/preserve/review before local deletion ({unsafe})")
    return out


# ── liveness stamp (counts-only, PII-free) ───────────────────────────────────────────────────
def write_stamp(a: dict, reclaimed: int | None = None) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    fac = a["factory"]
    rec = {
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "evictable_gb": a["debt"]["evictable_gb"],
        "retained_gb": a["debt"]["retained_gb"],
        "apps": {
            k: {"total_gb": round(v["total"] / GB, 2), "evictable_gb": round(v["evictable"] / GB, 2)}
            for k, v in a["debt"]["apps"].items()
        },
        "cartridge_connected": fac["cartridge_connected"],
        "bin_orphans": fac["bin_orphans"]["count"] if fac["bin_orphans"]["measured"] else None,
        "bin_orphan_names": fac["bin_orphans"]["names"],
        "domus_pkg_drift": fac["domus_packages"]["drift"] if fac["domus_packages"]["measured"] else None,
        "reapers_fresh": a["reapers"]["fresh"],
        "reapers_stale": a["reapers"]["stale"],
        "worktree_over_cap": a["worktree_over_cap"],
        "antigravity_scratch": {
            "measured": a["antigravity_scratch"].get("measured"),
            "total_roots": a["antigravity_scratch"].get("total_roots"),
            "total_gb": a["antigravity_scratch"].get("total_gb"),
            "safe_reap_gb": a["antigravity_scratch"].get("safe_reap_gb"),
            "by_disposition": a["antigravity_scratch"].get("by_disposition"),
            "unsafe_preserved_dispositions": a["antigravity_scratch"].get("unsafe_preserved_dispositions"),
            "unsafe_unpreserved_dispositions": a["antigravity_scratch"].get("unsafe_unpreserved_dispositions"),
        },
        "at_factory": not failures(a),
        "open_invariants": failures(a),
    }
    if reclaimed is not None:
        rec["reclaimable_gb"] = round(reclaimed / GB, 2)
    (LOGS / "cvstos-organ-state.json").write_text(json.dumps(rec, indent=2))
    try:
        vd = LOGS / ".voice"
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "cvstos").write_text(rec["ran_at"])
    except OSError:
        pass


def _oneliner(a: dict) -> str:
    d, fac, r = a["debt"], a["factory"], a["reapers"]
    cart = {True: "ok", False: "UNPLUGGED", None: "?"}[fac["cartridge_connected"]]
    binc = fac["bin_orphans"]["count"] if fac["bin_orphans"]["measured"] else "?"
    pkg = "drift" if fac["domus_packages"].get("drift") else ("clean" if fac["domus_packages"]["measured"] else "?")
    line = (
        f"cvstos: debt {d['evictable_gb']}GB evictable / {d['retained_gb']}GB retained "
        f"across {len(d['apps'])} apps · factory: cartridge {cart}, {binc} bin-orphans, domus {pkg} · "
        f"reapers {r['fresh']}/{r['fresh'] + r['stale'] + r['unknown']} fresh"
    )
    agy = a.get("antigravity_scratch") or {}
    if agy.get("measured"):
        line += f" · agy-scratch {agy.get('total_gb', 0)}GB / safe {agy.get('safe_reap_gb', 0)}GB"
    return line


def main() -> int:
    ap = argparse.ArgumentParser(description="CVSTOS — keeper of the host (factory ⇄ cartridge).")
    ap.add_argument("--check", action="store_true", help="Definition of Done: exit 0 iff the host is at factory")
    ap.add_argument("--apply", action="store_true", help="report accepted-reaper candidate cache bytes")
    ap.add_argument("--json", action="store_true", help="print the full assessment as JSON")
    args = ap.parse_args()

    a = assess()

    reclaimed = None
    if args.apply:
        reclaimed = reclaim_debt(a["debt"])

    write_stamp(a, reclaimed)

    if args.json:
        print(json.dumps(a, indent=2, default=str))
        return 0

    if args.check:
        fails = failures(a)
        if not fails:
            print("cvstos --check: host at factory ✓ (cartridge connected, no orphans, reapers fresh, debt under cap)")
            return 0
        print("cvstos --check: NOT at factory — open invariants:")
        for f in fails:
            print(f"  ✗ {f}")
        return 1

    line = _oneliner(a)
    if reclaimed is not None:
        line += f" · reclaimed {round(reclaimed / GB, 2)}GB"
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
