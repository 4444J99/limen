#!/usr/bin/env python3
"""publish-sweep.py — the pre-publication gate for a private→public visibility flip.

A flip exposes HISTORY, not just HEAD (every blob in every commit becomes world-readable), which the
publication-policy KEEP_OFF_PUBLIC_HEAD doctrine does not cover. So the sweep is three scans per repo,
all delegating classification to scripts/publication-policy.py (the ONE disposition engine):

  1. HEAD content   — classify(path, text) per HEAD file: secret / personal_pii / internal_strategy
                      anywhere on HEAD is a red finding.
  2. History blobs  — _SECRET_RX over every text blob reachable from ANY ref (bounded per-blob size):
                      a secret that was "deleted" is still published by a flip.
  3. Verdict        — green ⟺ zero secret hits (history + HEAD) ∧ zero personal_pii ∧ zero
                      internal_strategy on HEAD.

Receipts land in logs/publish-sweeps/{owner}__{name}.json (gitignored; counts + paths + blob ids —
NEVER a secret value: the _scrub firewall). scripts/apply-visibility.py refuses to flip a repo whose
receipt is missing, red, or stale (LIMEN_SWEEP_FRESH_DAYS).

  python3 scripts/publish-sweep.py --repo organvm/name        # sweep one repo
  python3 scripts/publish-sweep.py --candidates               # sweep publish_candidate rows (bounded)
  python3 scripts/publish-sweep.py --check                    # exit 0 ⟺ every candidate green + fresh

Env: LIMEN_SWEEP_MAX (candidates per run, default 5), LIMEN_SWEEP_MAX_BLOB_KB (per-blob scan cap,
default 512), LIMEN_SWEEP_FRESH_DAYS (receipt freshness, default 7), LIMEN_OFFLINE (skip, fail-open).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.resolve()
RECEIPTS = ROOT / "logs" / "publish-sweeps"

sys.path.insert(0, str(SCRIPT_DIR))


def _module(name: str, filename: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, str(SCRIPT_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _pp():
    return _module("publication_policy", "publication-policy.py")


def _gitvs():
    return _module("gitvs", "gitvs.py")


def _git(clone: Path, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    # errors="replace": a full-history / HEAD-blob sweep reads real repo content, which includes
    # binary blobs (images, archives). Strict UTF-8 decoding crashed the whole sweep on the first
    # non-UTF-8 byte (limen HEAD, 2026-07-17). Secrets/PII shapes are ASCII, so replacing the
    # undecodable bytes preserves every match while making the gate robust to binary.
    return subprocess.run(
        ["git", "-C", str(clone), *args], capture_output=True, text=True, errors="replace", timeout=timeout
    )


def _clone(repo: str, dest: Path, clone_from: str | None) -> bool:
    """Bare clone (full history). --clone-from is the offline test seam; live path uses gh (native
    auth — no token ever appears in argv)."""
    src = clone_from or repo
    if clone_from:
        r = subprocess.run(
            ["git", "clone", "--bare", "--quiet", src, str(dest)], capture_output=True, text=True, timeout=600
        )
        return r.returncode == 0
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return False
    r = subprocess.run(
        ["gh", "repo", "clone", repo, str(dest), "--", "--bare", "--quiet"],
        capture_output=True,
        text=True,
        timeout=1200,
    )
    return r.returncode == 0


def _head_findings(clone: Path, pp) -> tuple[dict[str, int], list[dict]]:
    """classify(path, text) per HEAD file — content-aware (PII/secret shapes inside text count)."""
    hist: dict[str, int] = {}
    findings: list[dict] = []
    ls = _git(clone, "ls-tree", "-r", "HEAD", "--format=%(objectname) %(path)")
    if ls.returncode != 0:
        return hist, findings
    cap = int(os.environ.get("LIMEN_SWEEP_MAX_BLOB_KB", "512")) * 1024
    for line in ls.stdout.splitlines():
        try:
            oid, path = line.split(" ", 1)
        except ValueError:
            continue
        show = _git(clone, "cat-file", "blob", oid, timeout=60)
        text = (show.stdout or "")[:cap] if show.returncode == 0 else None
        cls, reason = pp.classify(path, text or None)
        hist[cls] = hist.get(cls, 0) + 1
        if cls in ("secret", "personal_pii", "internal_strategy") and len(findings) < 50:
            findings.append({"path": path, "class": cls, "reason": reason})
    return dict(sorted(hist.items())), findings


def _history_secret_hits(clone: Path, pp) -> tuple[list[dict], int, int]:
    """_SECRET_RX over every reachable text blob (bounded size). Returns (hits, scanned, skipped)."""
    rl = _git(clone, "rev-list", "--objects", "--all", timeout=600)
    if rl.returncode != 0:
        return [], 0, 0
    cap_kb = int(os.environ.get("LIMEN_SWEEP_MAX_BLOB_KB", "512"))
    objects: dict[str, str] = {}
    for line in rl.stdout.splitlines():
        parts = line.split(" ", 1)
        if parts[0]:
            objects[parts[0]] = parts[1] if len(parts) > 1 else ""
    hits: list[dict] = []
    scanned = skipped = 0

    def _read_exact(stream, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = stream.read(n - len(buf))
            if not chunk:
                break
            buf += chunk
        return buf

    batch = subprocess.Popen(
        ["git", "-C", str(clone), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    try:
        for oid, path in objects.items():
            batch.stdin.write((oid + "\n").encode())
            batch.stdin.flush()
            header = batch.stdout.readline().decode(errors="replace").strip()
            parts = header.split()
            if len(parts) == 2 and parts[1] == "missing":
                continue
            if len(parts) != 3:
                continue
            size = int(parts[2])
            # --batch emits the body for EVERY object type — consume it or the stream desyncs.
            body = _read_exact(batch.stdout, size)
            _read_exact(batch.stdout, 1)  # trailing LF
            if parts[1] != "blob":
                continue
            if size > cap_kb * 1024:
                skipped += 1
                continue
            scanned += 1
            text = body.decode("utf-8", errors="replace")
            if pp._SECRET_RX.search(text):
                if len(hits) < 50:
                    hits.append({"path": path or "(unknown)", "oid": oid[:8]})
    finally:
        try:
            batch.stdin.close()
            batch.wait(timeout=30)
        except Exception:
            batch.kill()
    return hits, scanned, skipped


def sweep(repo: str, pp, clone_from: str | None = None) -> dict:
    """One repo → one receipt. Fail-open: an unreachable repo is a not-green receipt, never a raise."""
    receipt: dict = {"schema": "limen.publish_sweep.v1", "repo": repo, "green": False}
    with tempfile.TemporaryDirectory(prefix="publish-sweep-") as td:
        clone = Path(td) / "repo.git"
        if not _clone(repo, clone, clone_from):
            receipt["error"] = "clone failed (offline or unreachable)"
            return receipt
        head = _git(clone, "rev-parse", "HEAD")
        receipt["head"] = (head.stdout or "").strip()[:12]
        hist, findings = _head_findings(clone, pp)
        hits, scanned, skipped = _history_secret_hits(clone, pp)
        receipt.update(
            head_histogram=hist,
            head_findings=findings,
            history_secret_hits=hits,
            history_blobs_scanned=scanned,
            history_blobs_skipped_large=skipped,
        )
        red_head = (
            hist.get("secret", 0) + hist.get("personal_pii", 0) + hist.get("internal_strategy", 0)
        )
        receipt["green"] = red_head == 0 and not hits
    receipt["swept_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return receipt


def _receipt_path(repo: str) -> Path:
    return RECEIPTS / (repo.replace("/", "__") + ".json")


def _write_receipt(receipt: dict) -> None:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    _receipt_path(receipt["repo"]).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def _candidates(estate: dict) -> list[str]:
    return sorted(
        repo
        for repo, row in (estate.get("repo_overrides") or {}).items()
        if isinstance(row, dict) and row.get("publish_candidate")
    )


def receipt_fresh_green(repo: str) -> tuple[bool, str]:
    """The contract apply-visibility.py enforces: green AND younger than LIMEN_SWEEP_FRESH_DAYS."""
    path = _receipt_path(repo)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False, "no receipt"
    if not receipt.get("green"):
        return False, "receipt red"
    try:
        swept = datetime.fromisoformat(receipt["swept_at"])
    except Exception:
        return False, "receipt undated"
    days = int(os.environ.get("LIMEN_SWEEP_FRESH_DAYS", "7"))
    if datetime.now(timezone.utc) - swept > timedelta(days=days):
        return False, f"receipt stale (>{days}d)"
    return True, "green+fresh"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pre-publication sweep: HEAD content + full-history secrets.")
    ap.add_argument("--repo", help="sweep one owner/repo")
    ap.add_argument("--candidates", action="store_true", help="sweep publish_candidate rows (bounded)")
    ap.add_argument("--check", action="store_true", help="exit 0 ⟺ every candidate has a green+fresh receipt")
    ap.add_argument("--clone-from", help="(test seam) clone from a local path instead of GitHub")
    args = ap.parse_args(argv)

    estate = _gitvs().load_estate()

    if args.check:
        missing = []
        for repo in _candidates(estate):
            ok, why = receipt_fresh_green(repo)
            if not ok:
                missing.append(f"{repo}: {why}")
        if missing:
            print(f"[publish-sweep] {len(missing)} candidate(s) without a green+fresh receipt:")
            for m in missing[:20]:
                print(f"   {m}")
            return 1
        print("[publish-sweep] every publish candidate holds a green+fresh receipt")
        return 0

    if args.repo:
        targets = [args.repo]
    elif args.candidates:
        cap = int(os.environ.get("LIMEN_SWEEP_MAX", "5"))
        targets = [r for r in _candidates(estate) if not receipt_fresh_green(r)[0]][:cap]
        if not targets:
            print("[publish-sweep] nothing to sweep — all candidates green+fresh")
            return 0
    else:
        ap.print_help()
        return 2

    pp = _pp()
    reds = 0
    for repo in targets:
        receipt = sweep(repo, pp, clone_from=args.clone_from)
        _write_receipt(receipt)
        verdict = "GREEN" if receipt.get("green") else "RED"
        reds += 0 if receipt.get("green") else 1
        hits = len(receipt.get("history_secret_hits") or [])
        finds = len(receipt.get("head_findings") or [])
        print(
            f"[publish-sweep] {repo}: {verdict} — head findings {finds}, history secret hits {hits}"
            f" → {_receipt_path(repo).relative_to(ROOT)}"
        )
    return 1 if reds else 0


if __name__ == "__main__":
    raise SystemExit(main())
