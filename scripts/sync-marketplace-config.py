#!/usr/bin/env python3
"""sync-marketplace-config.py — the config-push effector for the GITVS integrations pillar (§3).

Harnessing a free Marketplace App has two halves: the OAuth INSTALL (the human atom — a file-atom
lever, L-INTEGRATION-<APP>) and the CONFIG (the machine-ownable half — this script). For each ACTIVE
integration in institutio/github/estate.yaml, this ensures the app's `config_file` is present in every
repo of its `install_scope` classes. The config SOURCE is the conductor repo's own copy
(organvm/limen/.coderabbit.yaml, renovate.json, …) — so "push" means: copy the conductor's live config
into a target repo via a COMPLIANT PR (never a force-push, never a direct-to-main write).

The three target kinds, one contract:
  - CONDUCTOR (organvm/limen == this repo): the config lives at the repo root already → a local check;
    an absent source is a red (the config the fan-out copies is missing).
  - governed_public repos: push via the GitHub contents API on a fresh branch + `gh pr create`
    (cross-repo). The merge organs (merge-drain / merge-policy) land the PR — this only opens it.

DOUBLE-DARK, like the remote reaper (a cross-repo PR touches other repos): reports the gap by default;
opens PRs ONLY with --apply AND LIMEN_MARKETPLACE_APPLY=1 (default 0). Bounded (LIMEN_MARKETPLACE_MAX
per run), idempotent (skips a repo whose config already exists), fail-open, offline-safe.

  python3 scripts/sync-marketplace-config.py            # report the config gap (dry) — the default
  python3 scripts/sync-marketplace-config.py --check    # same, the sensor idiom (exit 0 unless a source is missing)
  python3 scripts/sync-marketplace-config.py --apply    # push missing configs — ONLY if LIMEN_MARKETPLACE_APPLY=1
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import subprocess
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.resolve()
ESTATE = Path(os.environ.get("LIMEN_GITVS_ESTATE") or (ROOT / "institutio" / "github" / "estate.yaml"))
CONDUCTOR_REPO = "organvm/limen"   # derived identity of this repo (the config SOURCE); see _conductor_repo()


def _bool_env(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip() in ("1", "true", "yes", "on")


def _conductor_repo() -> str:
    """Derive owner/repo of THIS checkout from the git remote ("names are outputs"); fall back to the
    known conductor slug so the effector still resolves in a detached CI checkout."""
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=10)
        url = (r.stdout or "").strip()
        if url:
            tail = url.split("github.com", 1)[-1].lstrip(":/").removesuffix(".git")
            if tail.count("/") == 1:
                return tail
    except Exception:
        pass
    return CONDUCTOR_REPO


def load_estate() -> dict:
    try:
        return yaml.safe_load(ESTATE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _gh(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """gh with the cascade token; fail-open (returncode 1), never raises."""
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return subprocess.CompletedProcess(args, 1, "", "offline")
    env = {**os.environ}
    try:
        tok = subprocess.run(["bash", str(SCRIPT_DIR / "gh-app-token.sh")],
                             capture_output=True, text=True, timeout=45)
        if tok.returncode == 0 and tok.stdout.strip():
            env["GH_TOKEN"] = env["GITHUB_TOKEN"] = tok.stdout.strip()
    except Exception:
        pass
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, env=env)
    except Exception as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def active_integrations(estate: dict) -> list[tuple[str, dict]]:
    """(name, descriptor) for every integration whose status is active AND declares a config_file."""
    out = []
    for name, ig in (estate.get("integrations") or {}).items():
        if isinstance(ig, dict) and ig.get("status") == "active" and ig.get("config_file"):
            out.append((name, ig))
    return out


def _class_globs(estate: dict, class_name: str) -> list[str]:
    return list((((estate.get("classes") or {}).get(class_name) or {}).get("match")) or [])


def _repo_has_file(repo: str, path: str) -> bool | None:
    """Does `repo` already carry `path`? True/False online; None if it can't be determined (fail-open)."""
    r = _gh(["api", f"/repos/{repo}/contents/{path}", "--jq", ".path"], timeout=30)
    if r.returncode == 0 and (r.stdout or "").strip():
        return True
    if "Not Found" in (r.stderr or "") or "404" in (r.stderr or ""):
        return False
    return None


def _governed_repos(estate: dict, globs: list[str], cap: int) -> list[str]:
    """Enumerate up to `cap` repos matching the governed_public globs (bounded — the fan-out is a
    rotating job, not a 301-repo stampede). Only called under --apply arming."""
    owners = sorted({g.split("/", 1)[0] for g in globs if "/" in g and g.split("/", 1)[0] not in ("*", "**")})
    repos: list[str] = []
    for owner in owners:
        r = _gh(["api", f"/users/{owner}/repos", "--paginate", "-X", "GET", "-F", "per_page=100",
                 "--jq", ".[] | select(.archived==false) | .full_name"], timeout=90)
        if r.returncode == 0:
            for full in (r.stdout or "").splitlines():
                full = full.strip()
                if full and any(fnmatch.fnmatch(full, g) for g in globs) and full != _conductor_repo():
                    repos.append(full)
    return repos[:cap]


def _push_config(repo: str, path: str, content: str, app: str) -> str:
    """Open a compliant PR adding `path` to `repo` via the contents API on a fresh branch. Never
    force-pushes, never writes to the default branch — the merge organs land the PR. Idempotent-safe:
    caller has already confirmed the file is absent."""
    branch = f"gitvs/integration-{app}"
    base = _gh(["api", f"/repos/{repo}", "--jq", ".default_branch"], timeout=20)
    default = (base.stdout or "").strip() or "main"
    sha = _gh(["api", f"/repos/{repo}/git/ref/heads/{default}", "--jq", ".object.sha"], timeout=20)
    head_sha = (sha.stdout or "").strip()
    if not head_sha:
        return f"{repo}: could not read {default} head"
    mk = _gh(["api", "-X", "POST", f"/repos/{repo}/git/refs", "-f", f"ref=refs/heads/{branch}",
              "-f", f"sha={head_sha}"], timeout=20)
    if mk.returncode != 0 and "already exists" not in (mk.stderr or ""):
        return f"{repo}: branch create failed"
    import base64
    b64 = base64.b64encode(content.encode()).decode()
    put = _gh(["api", "-X", "PUT", f"/repos/{repo}/contents/{path}",
               "-f", f"message=chore(gitvs): add {path} — {app} config (GITVS integrations)",
               "-f", f"content={b64}", "-f", f"branch={branch}"], timeout=30)
    if put.returncode != 0:
        return f"{repo}: contents PUT failed"
    pr = _gh(["pr", "create", "--repo", repo, "--base", default, "--head", branch,
              "--title", f"chore(gitvs): {app} config ({path})",
              "--body", f"GITVS integrations pillar — machine-pushed {app} config so the repo is ready "
                        f"the moment the Marketplace app is installed. Config sourced from {_conductor_repo()}."],
             timeout=45)
    return f"{repo}: PR opened" if pr.returncode == 0 else f"{repo}: PR create failed ({(pr.stderr or '')[:60]})"


def run(estate: dict, *, apply: bool) -> int:
    armed = apply and _bool_env("LIMEN_MARKETPLACE_APPLY", default=False)
    cap = int(os.environ.get("LIMEN_MARKETPLACE_MAX", "20"))
    conductor = _conductor_repo()
    integrations = active_integrations(estate)
    if not integrations:
        print("[sync-marketplace-config] no active integrations with a config_file — nothing to sync.")
        return 0
    if apply and not armed:
        print("[sync-marketplace-config] --apply WITHOUT LIMEN_MARKETPLACE_APPLY=1 → staying DARK (dry report).")

    source_missing = 0
    pushed: list[str] = []
    for name, ig in integrations:
        cf = ig["config_file"]
        src = ROOT / cf
        present = src.exists()
        scope = ig.get("install_scope") or []
        line = f"  {name:12s} {cf:28s} source={'present' if present else 'MISSING'} scope={scope}"
        print(line)
        if not present:
            source_missing += 1   # the conductor's own config (the fan-out template) is absent — a defect
            continue
        content = src.read_text(encoding="utf-8")
        for cls in scope:
            if cls == "conductor":
                print(f"     · conductor {conductor}: config present at root (satisfied)")
                continue
            globs = _class_globs(estate, cls)
            if not armed:
                print(f"     · {cls}: fan-out to matching repos — DARK (arm --apply + LIMEN_MARKETPLACE_APPLY=1)")
                continue
            targets = _governed_repos(estate, globs, cap)
            for repo in targets:
                has = _repo_has_file(repo, cf)
                if has:
                    continue
                if has is None:
                    print(f"     ~ {repo}: config presence unknown — skipped (fail-safe)")
                    continue
                pushed.append(_push_config(repo, cf, content, name))
                print(f"     ✓ {pushed[-1]}")

    print(f"[sync-marketplace-config] {len(integrations)} active integration(s); "
          f"{len(pushed)} config PR(s) opened; source_missing={source_missing}.")
    return 1 if source_missing else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GITVS integrations config-push effector (double-dark).")
    ap.add_argument("--apply", action="store_true", help="open config PRs (ONLY if LIMEN_MARKETPLACE_APPLY=1)")
    ap.add_argument("--check", action="store_true", help="report-only (the sensor idiom); never mutates")
    args = ap.parse_args(argv)
    estate = load_estate()
    return run(estate, apply=bool(args.apply) and not bool(args.check))


if __name__ == "__main__":
    raise SystemExit(main())
