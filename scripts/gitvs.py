#!/usr/bin/env python3
"""gitvs.py — GITVS, the GitHub custodian: GitHub as ONE declarative resource graph under ONE closed loop.

The ideal form (control-theory / GitOps applied to GitHub-as-the-cloud). Every GitHub thing — App,
installation, repo, branch, PR, issue, secret, ruleset, team, webhook, release — is the same object: a
Resource with a DERIVED identity ("names are outputs"), a DECLARED desired state, an OBSERVED actual
state. The total graph is the Estate (institutio/github/estate.yaml). The loop is three projections:

  census    observe() → the live estate → docs/github-estate-ledger.json          (the Lens)
  doctor    diff()   → desired − observed, exit 0 ⟺ drift == ∅                     (the Predicate)
  reconcile apply()  → drive drift → policy through the three total effector sinks (the Effector; PR B)

GITVS is ~90% orchestration: it never re-implements a mutation. Its effectors DELEGATE to the existing
compliant organs (merge-drain, self-heal, sync-*-issues, creds-hydrate), FILE a human atom (a lever /
the credential wall), or REAP through a native mutator behind the reclaim-worktrees safety-gate model.

THE WIRING-INTEGRITY LAW (sensor-without-effector = defect; #881/#883): `doctor --parity-only` (the
deterministic class-H rung, a PR gate) fails if a `status: active` resource type lacks a wired observe +
effector + identity, if a declared effector script does not exist, or if a class `required_checks` names a
job no .github/workflows file defines. GITVS cannot declare governance it can't enact.

Offline / no-gh is FAIL-OPEN (the sibling-organ contract): the git-derivable rungs (parity, local-branch
hygiene, secret homing) still run; the live gh rungs (repo/PR/protection/App/rate-limit) report SKIP,
never a faked PASS. A homed drift atom (App un-installed → L-LIMENBOT-INSTALL, protection → #257) is CITED
by lever id, not counted as a failure and never recited as a token.

  python3 scripts/gitvs.py census                     # observe → write the durable ledger + logs/gitvs.json
  python3 scripts/gitvs.py doctor                      # full predicate (live rungs run when gh is reachable)
  python3 scripts/gitvs.py doctor --offline            # det + offline-safe rungs; live rungs → SKIP
  python3 scripts/gitvs.py doctor --parity-only        # class H only (deterministic, the PR gate)

Env: LIMEN_ROOT, LIMEN_OFFLINE, LIMEN_GITVS_OWNERS (owners to enumerate; default derived from the remote).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _pr_scan import enumerate_open_prs  # noqa: E402  (shared, dependency-injected, fail-open)

# ROOT is the script's OWN tree (never LIMEN_ROOT) — a registry-drift predicate must validate the tree
# it lives in, so the parity gate checks THIS checkout's estate.yaml in a worktree/CI, not wherever an
# ambient LIMEN_ROOT points. The check-gates.py / check-params.py / credential-wall.py invariant. In the
# live beat the script and the conductor tree coincide, so runtime behavior is unchanged.
ROOT = SCRIPT_DIR.parent.resolve()
ESTATE = Path(os.environ.get("LIMEN_GITVS_ESTATE") or (ROOT / "institutio" / "github" / "estate.yaml"))
LEDGER = ROOT / "docs" / "github-estate-ledger.json"
STAMP = ROOT / "logs" / "gitvs.json"
WORKFLOWS = ROOT / ".github" / "workflows"

REQUIRED_RESOURCE_FIELDS = ("identity", "desired", "observe", "effector", "status", "owner", "note")
VALID_STATUS = {"active", "envisioned"}
REQUIRED_CLASS_FIELDS = ("match", "visibility", "branch_protection", "required_checks", "owner", "note")
REQUIRED_INTEGRATION_FIELDS = ("category", "app_slug", "config_file", "install_scope", "effector", "status", "owner", "note")
# The effector's three total sinks — the closure that makes the form complete.
EFFECTOR_KINDS = {"delegate", "file-atom", "reap"}
# Literal effector tokens that carry no script/lever (a human-obvious manual act).
EFFECTOR_LITERALS = {"manual"}

LEDGER_SCHEMA = "limen.github_estate.v1"


# ── auth (reuse the cascade; never touch App creds directly) ───────────────────────────────────
def _token() -> str | None:
    """Mint a token via the gh-app-token.sh cascade (App → PAT → gh). None if every path is exhausted."""
    if os.environ.get("LIMEN_OFFLINE"):
        return None
    try:
        r = subprocess.run(
            ["bash", str(ROOT / "scripts" / "gh-app-token.sh")],
            capture_output=True, text=True, timeout=45,
        )
    except Exception:
        return None
    tok = (r.stdout or "").strip()
    return tok if r.returncode == 0 and tok else None


def _gh(args: list[str], token: str | None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a `gh` command with the cascade token exported. Fails OPEN (returncode 1), never raises."""
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return subprocess.CompletedProcess(args, 1, "", "offline")
    env = {**os.environ}
    if token:
        env["GH_TOKEN"] = token
        env["GITHUB_TOKEN"] = token
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, env=env)
    except Exception as e:  # fail open
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _gh_user(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run `gh` with its NATIVE owner auth (the gh keyring PAT), NOT the App installation token. Cross-org
    reads (/user/orgs, another org's installations) need the OWNER's user scope — the per-org App token is
    installed on the conductor org only and structurally cannot enumerate the user's other orgs. Strips
    GH_TOKEN/GITHUB_TOKEN so gh falls back to its keyring. Fails OPEN, never raises."""
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return subprocess.CompletedProcess(args, 1, "", "offline")
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, env=env)
    except Exception as e:  # fail open
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _token_path() -> str:
    """Which cascade path resolves (app|pat|gh|none) — prints NO secret."""
    try:
        r = subprocess.run(
            ["bash", str(ROOT / "scripts" / "gh-app-token.sh"), "--which"],
            capture_output=True, text=True, timeout=20,
        )
        return (r.stdout or "").strip().split()[0] if r.returncode == 0 and r.stdout.strip() else "none"
    except Exception:
        return "none"


# ── the Estate (desired-state) ─────────────────────────────────────────────────────────────────
def load_estate() -> dict:
    try:
        return yaml.safe_load(ESTATE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def owners(estate: dict) -> list[str]:
    """Owners to enumerate — LIMEN_GITVS_OWNERS override, else derived from the class globs' owner
    prefixes ("names are outputs" — never pin a repo list). Falls back to the conductor owner."""
    raw = os.environ.get("LIMEN_GITVS_OWNERS", "")
    listed = [o.strip() for o in raw.split(",") if o.strip()]
    if listed:
        return listed
    derived: list[str] = []
    for cls in (estate.get("classes") or {}).values():
        for m in (cls.get("match") or []):
            owner = str(m).split("/", 1)[0]
            if owner and owner not in ("*", "**") and owner not in derived:
                derived.append(owner)
    return derived or ["organvm"]


def classify_repo(repo: str, estate: dict) -> str | None:
    """First-match-wins bucket of an owner/repo into a class name (most-specific class first in the file)."""
    for name, cls in (estate.get("classes") or {}).items():
        for glob in (cls.get("match") or []):
            if fnmatch.fnmatch(repo, glob):
                return name
    return None


# ── the Lens: observe() → the durable ledger ────────────────────────────────────────────────────
def _local_branch_reasons() -> dict[str, int]:
    """The per-branch closure reason histogram for the conductor repo — computed ONCE, by importing
    reap-branches' pure classifier (git-derivable, offline-safe). This is the durable home the ad-hoc
    session-lifecycle-pressure.py::remote_missing_counts() was missing (subsumed once the ratchet arms)."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("reap_branches", str(SCRIPT_DIR / "reap-branches.py"))
        rb = importlib.util.module_from_spec(spec)
        sys.modules["reap_branches"] = rb  # register before exec so @dataclass introspection resolves (py3.14)
        spec.loader.exec_module(rb)
        dref = rb.default_ref()
        dname = rb.default_name(dref)
        checked = rb.checked_out_branches()
        merged, open_, _ = rb.gh_head_states()
        hist: dict[str, int] = {}
        for b in rb.local_branches():
            v = rb.classify(rb.gather_facts(b, dref, checked, merged, open_, dname))
            hist[v.reason] = hist.get(v.reason, 0) + 1
        return hist
    except Exception:
        return {}


def _integration_observe(estate: dict, token: str | None, online: bool) -> dict:
    """Observe the ecosystem integrations: config-file presence in the conductor tree (git-derivable,
    offline-safe) + the set of installed app_slugs on the governed orgs (online). Read-only; the doctor's
    class I diffs desired − this. Deterministic (sorted) so the ledger stays an idempotent fixed point."""
    integrations = estate.get("integrations") or {}
    out: dict = {"declared": len(integrations), "config_present": {}, "installed_slugs": None}
    for iname, ig in integrations.items():
        cf = (ig or {}).get("config_file")
        if cf:
            out["config_present"][iname] = (ROOT / cf).exists()
    out["config_present"] = dict(sorted(out["config_present"].items()))
    if online:
        slugs: list[str] = []
        for owner in owners(estate):
            r = _gh(["api", f"/orgs/{owner}/installations", "--jq", ".installations[].app_slug"], token, timeout=30)
            if r.returncode == 0:
                slugs += [s.strip() for s in (r.stdout or "").splitlines() if s.strip()]
        out["installed_slugs"] = sorted(set(slugs))
    return out


def _org_app_estate(token: str | None, online: bool) -> dict:
    """The FULL cross-org app-installation inventory — the 'what is on ALL my orgs/accounts' portal.
    Enumerates the authed user's orgs (/user/orgs) and each org's installed app_slugs
    (/orgs/{o}/installations), so app-estate drift (a new app on one org, a removed one on another) is a
    governed living fact, never a manual re-discovery. Wider than the governed `owners` — pure
    observability across every org. Uses the OWNER's gh-native token (_gh_user), NOT the App installation
    token: the per-org App is installed on the conductor org only and cannot see the user's other orgs.
    Read-only, fail-open (offline → nulls); deterministic (sorted). `token` is unused (kept for the
    observe() call shape) — the cross-org read is deliberately user-scoped."""
    out: dict = {"orgs": None, "by_org": {}, "all_apps": None}
    if not online:
        return out
    r = _gh_user(["api", "/user/orgs", "--paginate", "--jq", ".[].login"], timeout=45)
    orgs = [o.strip() for o in (r.stdout or "").splitlines() if o.strip()] if r.returncode == 0 else []
    by_org: dict[str, list[str]] = {}
    all_apps: set[str] = set()
    for o in orgs:
        ri = _gh_user(["api", f"/orgs/{o}/installations", "--jq", ".installations[].app_slug"], timeout=30)
        if ri.returncode == 0:
            slugs = sorted({s.strip() for s in (ri.stdout or "").splitlines() if s.strip()})
            by_org[o] = slugs
            all_apps.update(slugs)
    out["orgs"] = len(orgs)
    out["by_org"] = dict(sorted(by_org.items()))
    out["all_apps"] = sorted(all_apps)
    return out


def observe(estate: dict) -> dict:
    """Build the actual-state ledger. Every block is fail-open: a gh/parse failure degrades to null,
    never raises; `online` records whether the live rungs ran. Counts + names only (the _scrub firewall —
    no secret VALUE is ever read here)."""
    token = _token()
    online = token is not None and shutil.which("gh") is not None
    led: dict = {
        "schema": LEDGER_SCHEMA,
        "online": bool(online),
        "app": {"installed": None, "slug": (estate.get("app") or {}).get("slug"),
                "token_path": _token_path(), "installations": None},
        "repos": {"total": None, "by_class": {}},
        "prs": {"open_total": 0, "by_repo": {}},
        "branches": {"conductor_by_reason": _local_branch_reasons()},
        "secrets": {"homed": None},
        "usage": {"rate_limit_headroom_pct": None},
    }

    owner_list = owners(estate)

    # PRs — reuse the shared enumerator (one cheap call, stable order, fail-open []).
    prs = enumerate_open_prs(owner_list, lambda a: _gh(a, token), want_url=False) if online else []
    by_repo: dict[str, int] = {}
    for repo, _num in prs:
        by_repo[repo] = by_repo.get(repo, 0) + 1
    led["prs"] = {"open_total": len(prs), "by_repo": dict(sorted(by_repo.items()))}

    # App installations (permissions posture; over-grant is class D).
    if online:
        r = _gh(["api", "/app/installations", "--jq", "length"], token, timeout=30)
        if r.returncode == 0 and (r.stdout or "").strip().isdigit():
            n = int(r.stdout.strip())
            led["app"]["installed"] = n > 0
            led["app"]["installations"] = n

    # Repo census by class (bounded: one search-count per owner).
    if online:
        total = 0
        by_class: dict[str, int] = {}
        for owner in owner_list:
            r = _gh(["api", f"/users/{owner}/repos", "--paginate", "-X", "GET",
                     "-F", "per_page=100", "--jq", ".[].full_name"], token, timeout=90)
            names = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()] if r.returncode == 0 else []
            for full in names:
                total += 1
                cls = classify_repo(full, estate) or "unclassed"
                by_class[cls] = by_class.get(cls, 0) + 1
        if total:
            led["repos"] = {"total": total, "by_class": dict(sorted(by_class.items()))}

    # Rate-limit headroom (class E).
    if online:
        r = _gh(["api", "/rate_limit", "--jq", ".resources.core"], token, timeout=20)
        try:
            core = json.loads(r.stdout) if r.returncode == 0 else {}
            limit, remaining = core.get("limit"), core.get("remaining")
            if isinstance(limit, int) and limit > 0 and isinstance(remaining, int):
                led["usage"]["rate_limit_headroom_pct"] = round(100 * remaining / limit)
        except Exception:
            pass

    # Secret homing — delegate to the existing offline-safe predicate (class B).
    led["secrets"]["homed"] = _delegate_ok(["credential-wall.py", "--check"])

    # Ecosystem integrations (the §3 harness) — config presence (offline) + installed slugs (online).
    led["integrations"] = _integration_observe(estate, token, online)

    # Cross-org app estate — the full 'what apps are on ALL my orgs' inventory (governed living fact).
    led["app_estate"] = _org_app_estate(token, online)
    return led


def write_ledger(led: dict) -> None:
    """Durable, git-tracked ground truth. Deterministic (sorted keys); the only volatile field is
    excluded from the doctor's diff so re-runs are an idempotent fixed point (census twice == identical)."""
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(led, indent=2, sort_keys=True) + "\n")
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        STAMP.write_text(json.dumps({"online": led.get("online"), "prs": led["prs"]["open_total"],
                                     "app_installed": led["app"]["installed"]}, sort_keys=True) + "\n")
    except Exception as e:  # observability must never break the beat
        print(f"[gitvs] note: ledger/stamp write skipped ({str(e)[:80]})")


def _delegate_ok(argv: list[str]) -> bool | None:
    """Run a sibling predicate script; True/False on exit 0/non-0, None if it can't run. Fail-open."""
    script = SCRIPT_DIR / argv[0]
    if not script.exists():
        return None
    try:
        r = subprocess.run(["python3", str(script), *argv[1:]], capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return None


# ── the Predicate: diff() ───────────────────────────────────────────────────────────────────────
def _workflow_job_ids() -> set[str]:
    """Every job id + workflow name declared in .github/workflows — the universe a class required_check
    must name (a dead reference is a red predicate, not a silent typo)."""
    ids: set[str] = set()
    if not WORKFLOWS.exists():
        return ids
    for f in sorted(WORKFLOWS.glob("*.y*ml")):
        try:
            wf = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if isinstance(wf.get("name"), str):
            ids.add(wf["name"])
        for job in (wf.get("jobs") or {}):
            ids.add(str(job))
    return ids


def _effector_defects(rt_name: str, effector: str) -> list[str]:
    """A declared effector must resolve to the three total sinks, and any delegate/reap script must EXIST."""
    defects: list[str] = []
    for tok in [t.strip() for t in str(effector).split("|") if t.strip()]:
        if tok in EFFECTOR_LITERALS:
            continue
        if ":" not in tok:
            defects.append(f"resource '{rt_name}': effector token '{tok}' is not <sink>:<target> or a literal")
            continue
        kind, target = tok.split(":", 1)
        if kind not in EFFECTOR_KINDS:
            defects.append(f"resource '{rt_name}': effector kind '{kind}' not one of {sorted(EFFECTOR_KINDS)}")
            continue
        if kind in ("delegate", "reap"):
            if not (ROOT / target.strip()).exists():
                defects.append(f"resource '{rt_name}': {kind} effector script '{target.strip()}' does not exist")
    return defects


def parity(estate: dict) -> list[str]:
    """Class H — the deterministic, offline-safe rung (the PR gate). Schema + wiring-integrity + parity."""
    fails: list[str] = []
    if not estate:
        return [f"estate registry {ESTATE.relative_to(ROOT)} is missing or unparseable"]
    if "schema_version" not in estate:
        fails.append("estate: missing schema_version")

    rts = estate.get("resource_types")
    if not isinstance(rts, dict) or not rts:
        fails.append("estate: resource_types must be a non-empty mapping")
        rts = {}
    for name, rt in rts.items():
        if not isinstance(rt, dict):
            fails.append(f"resource '{name}': not a mapping")
            continue
        for field in REQUIRED_RESOURCE_FIELDS:
            if field not in rt:
                fails.append(f"resource '{name}': missing '{field}'")
        status = rt.get("status")
        if status not in VALID_STATUS:
            fails.append(f"resource '{name}': status '{status}' not in {sorted(VALID_STATUS)}")
        # THE WIRING-INTEGRITY LAW: an active type must be fully wired; its effector scripts must exist.
        if status == "active":
            for field in ("identity", "observe", "effector"):
                if not str(rt.get(field) or "").strip():
                    fails.append(f"resource '{name}' is active but '{field}' is unwired (sensor-without-effector = defect)")
            fails.extend(_effector_defects(name, rt.get("effector") or ""))

    classes = estate.get("classes")
    if not isinstance(classes, dict) or not classes:
        fails.append("estate: classes must be a non-empty mapping")
        classes = {}
    job_ids = _workflow_job_ids()
    for name, cls in classes.items():
        if not isinstance(cls, dict):
            fails.append(f"class '{name}': not a mapping")
            continue
        for field in REQUIRED_CLASS_FIELDS:
            if field not in cls:
                fails.append(f"class '{name}': missing '{field}'")
        checks = cls.get("required_checks")
        if checks is not None and not isinstance(checks, list):
            fails.append(f"class '{name}': required_checks must be a list")
        elif job_ids:  # only assert names once we can read the workflow universe
            for chk in (checks or []):
                if chk not in job_ids:
                    fails.append(f"class '{name}': required_check '{chk}' names no .github/workflows job")

    # integrations (the ecosystem registry) — the same field discipline; an `active` integration must
    # carry a config-push effector script that exists (the wiring-integrity law extended to the App plane).
    integrations = estate.get("integrations")
    if integrations is not None:
        if not isinstance(integrations, dict):
            fails.append("estate: integrations must be a mapping")
        else:
            for iname, ig in integrations.items():
                if not isinstance(ig, dict):
                    fails.append(f"integration '{iname}': not a mapping")
                    continue
                for field in REQUIRED_INTEGRATION_FIELDS:
                    if field not in ig:
                        fails.append(f"integration '{iname}': missing '{field}'")
                st = ig.get("status")
                if st not in VALID_STATUS:
                    fails.append(f"integration '{iname}': status '{st}' not in {sorted(VALID_STATUS)}")
                if st == "active":
                    fails.extend(_effector_defects(iname, ig.get("effector") or ""))

    # owner/note discipline on budgets (parity with the gates.yaml/parameters.yaml rule).
    for bname, budget in (estate.get("budgets") or {}).items():
        if isinstance(budget, dict):
            for field in ("owner", "note"):
                if field not in budget:
                    fails.append(f"budget '{bname}': missing '{field}'")
    return fails


def _homed_levers() -> set[str]:
    """Lever ids present (and open) in his-hand-levers.json — so the doctor can CITE a homed atom
    (App un-installed → L-LIMENBOT-INSTALL) instead of counting it as a failure. Absent file → empty."""
    try:
        data = json.loads((ROOT / "his-hand-levers.json").read_text(encoding="utf-8"))
    except Exception:
        return set()
    levers = data.get("levers", data) if isinstance(data, dict) else data
    out: set[str] = set()
    for lv in (levers if isinstance(levers, list) else []):
        if isinstance(lv, dict) and lv.get("id"):
            out.add(str(lv["id"]))
    return out


def doctor(estate: dict, *, parity_only: bool, offline: bool) -> int:
    """The Diff operator. Exit 0 ⟺ drift == ∅ (over the rungs that could run). SKIP is never a faked PASS."""
    fails: list[str] = []
    cites: list[str] = []
    skips: list[str] = []

    # ── Class H — parity / wiring-integrity (deterministic, always runs). The PR gate. ──
    h = parity(estate)
    fails += [f"[H parity] {m}" for m in h]

    if parity_only:
        return _verdict(fails, cites, skips, "parity-only")

    homed = _homed_levers()

    # ── Class B — homeless secret (delegate to the offline-safe credential-wall predicate). ──
    b = _delegate_ok(["credential-wall.py", "--check"])
    if b is None:
        skips.append("[B homeless-secret] credential-wall.py unavailable")
    elif not b:
        fails.append("[B homeless-secret] credential-wall.py --check failed (a secret atom lacks a home)")

    # ── Class C — orphaned local branch past grace (delegate to reap-branches --check). ──
    c = _delegate_ok(["reap-branches.py", "--check"])
    if c is None:
        skips.append("[C orphaned-branch] reap-branches.py unavailable")
    elif not c:
        fails.append("[C orphaned-branch] a provably-landed local branch lingers past the grace window")

    # ── Live classes (A/D/E/F/G) — need gh; SKIP offline, cite a homed atom instead of failing. ──
    if offline:
        for tag in ("A protection", "D permission-over-grant", "E rate-limit", "F app-installed", "G visibility"):
            skips.append(f"[{tag}] live rung — offline")
        return _verdict(fails, cites, skips, "offline")

    led = observe(estate)

    # F — App installed where a class requires it (homed → cite L-LIMENBOT-INSTALL, don't fail).
    installed = led["app"].get("installed")
    if installed is None:
        skips.append("[F app-installed] could not read /app/installations")
    elif not installed:
        atom = (estate.get("human_atoms") or {}).get("app_creation", {}).get("lever", "L-LIMENBOT-INSTALL")
        (cites if atom in homed else fails).append(
            f"[F app-installed] limen[bot] not installed → {atom}" + (" (owned, open)" if atom in homed else " (UNHOMED)")
        )

    # E — rate-limit headroom.
    hp = led["usage"].get("rate_limit_headroom_pct")
    floor = ((estate.get("budgets") or {}).get("api_rate_limit") or {}).get("headroom_pct_min", 15)
    if hp is None:
        skips.append("[E rate-limit] could not read /rate_limit")
    elif hp < floor:
        fails.append(f"[E rate-limit] core headroom {hp}% < floor {floor}%")

    # I — ecosystem integration gap (the §3 harness): declared in the estate vs installed/configured on
    # the org. Envisioned integrations are OWED (cited as a summary, never failed — GITVS cannot yet enact
    # them); a config-present or installed one is already satisfied. Detail lives in the census ledger.
    integ = led.get("integrations") or {}
    if integ.get("installed_slugs") is None:
        skips.append("[I integration-gap] could not read /orgs/*/installations")
    elif integ.get("declared"):
        slugs = set(integ.get("installed_slugs") or [])
        cfg = integ.get("config_present") or {}
        satisfied = sum(
            1 for n, ig in (estate.get("integrations") or {}).items()
            if ig.get("app_slug") in slugs or cfg.get(n)
        )
        owed = integ["declared"] - satisfied
        if owed:
            cites.append(f"[I integration-gap] {satisfied}/{integ['declared']} ecosystem integrations present; "
                         f"{owed} owed (envisioned — detail in the census ledger; $0-labor harness pending §3 D2)")

    # A/D/G are per-repo posture rungs — the census surfaces the inputs; the full per-301-repo
    # assertion arms with the reconcile layer (bounded rotating window). Reported SKIP, never faked.
    for tag in ("A protection-missing", "D permission-over-grant", "G visibility-drift"):
        skips.append(f"[{tag}] per-repo posture rung — arms with the reconcile layer (PR B)")

    return _verdict(fails, cites, skips, "live")


def _verdict(fails: list[str], cites: list[str], skips: list[str], mode: str) -> int:
    for c in cites:
        print(f"  · cited (homed) {c}")
    for s in skips:
        print(f"  ~ SKIP {s}")
    if fails:
        print(f"\n✗ gitvs doctor ({mode}): {len(fails)} drift(s) — the estate does not match policy:")
        for f in fails:
            print(f"   {f}")
        return 1
    print(f"✓ gitvs doctor ({mode}): drift == ∅ over {len(skips)} skipped + all run rungs; "
          f"{len(cites)} homed atom(s) cited.")
    return 0


# ── the Effector: reconcile() — the third projection of the loop ────────────────────────────────
# setup-rulesets.py is the ONE delegate GITVS must never auto-run: arming branch protection fleet-wide
# is his-hand (#257 / L-BRANCH-PROTECTION), and blanket protection would block the machine board writes.
# Its drift is CITED to the lever, never enacted by the beat. Everything else auto-runs dry-safe.
HUMAN_GATED_DELEGATES = {"scripts/setup-rulesets.py"}


def _lever_index() -> dict[str, dict]:
    """id → lever object (his-hand-levers.json), so a file-atom is CITED with its issue — never a value."""
    try:
        data = json.loads((ROOT / "his-hand-levers.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    levers = data.get("levers", data) if isinstance(data, dict) else data
    return {
        str(lv["id"]): lv
        for lv in (levers if isinstance(levers, list) else [])
        if isinstance(lv, dict) and lv.get("id")
    }


def _cite(target: str, levers: dict[str, dict]) -> str:
    """Render a file-atom citation (lever id + issue if homed) — resolves id → object, never a value."""
    lv = levers.get(target)
    issue = lv.get("issue") if lv else None
    if issue:
        return f"{target} (#{issue}, owned)"
    return f"{target} (owned)" if lv else f"{target} (cited)"


def _run_effector(script: str, *, apply: bool) -> str:
    """Invoke a delegate/reap organ. Each keeps its OWN arming (merge-policy guardrail, the reapers'
    double-dark, env-gated issue mirrors) — GITVS only passes the global --apply through, NEVER forces
    more and NEVER adds a self-merge path. Timeout-bounded, fail-open (a delegate crash never breaks
    the loop); returns the delegate's last line for the beat log."""
    path = ROOT / script
    if not path.exists():
        return f"MISSING {script}"
    argv = ["python3", str(path)] + (["--apply"] if apply else [])
    try:
        r = subprocess.run(
            argv, capture_output=True, text=True,
            timeout=int(os.environ.get("LIMEN_GITVS_TIMEOUT", "120")),
        )
        tail = (r.stdout or r.stderr or "").strip().splitlines()
        return (tail[-1] if tail else f"exit={r.returncode}")[:200]
    except Exception as e:  # fail open — a delegate must never break the reconcile loop
        return f"skipped ({str(e)[:80]})"


def reconcile(estate: dict, *, apply: bool) -> int:
    """The Effector — a GENERIC dispatcher (the mapping is DATA in estate.yaml, never a table here).
    Walk each `status: active` resource type and route its declared effector to one of the three total
    sinks: delegate (an existing compliant organ), reap (a native mutator behind its own dark-arming),
    file-atom (CITE a lever — never recite a value). DRY by default (report the plan, mutate nothing) —
    the observable-before-autonomous contract; --apply invokes the delegate/reap organs, each of which
    still self-gates. Always exit 0: reconcile is an advisory effector, not the predicate (doctor owns
    the drift verdict), and it must be fail-open in the beat."""
    rts = estate.get("resource_types") or {}
    levers = _lever_index()
    acted: list[str] = []          # ran (apply) or planned (dry)
    cited: list[str] = []
    skipped: list[str] = []
    for name, rt in rts.items():
        if not isinstance(rt, dict) or rt.get("status") != "active":
            continue
        for tok in [t.strip() for t in str(rt.get("effector") or "").split("|") if t.strip()]:
            if tok in EFFECTOR_LITERALS:
                skipped.append(f"{name}: {tok} (human-obvious manual act)")
                continue
            if ":" not in tok:
                skipped.append(f"{name}: malformed effector '{tok}'")
                continue
            kind, target = tok.split(":", 1)
            target = target.strip()
            if kind == "file-atom":
                cited.append(f"{name} → {_cite(target, levers)}")
            elif kind in ("delegate", "reap"):
                if kind == "delegate" and target in HUMAN_GATED_DELEGATES:
                    skipped.append(f"{name}: {target} is his-hand (#257) — cited to its lever, never auto-run")
                    continue
                if apply:
                    acted.append(f"{name} {kind}:{target} → {_run_effector(target, apply=True)}")
                else:
                    note = "  (reap: still needs its own dark-arming to delete)" if kind == "reap" else ""
                    acted.append(f"WOULD {kind}:{target} --apply{note}")
            else:
                skipped.append(f"{name}: unknown sink '{kind}'")

    mode = "APPLY" if apply else "report (dry)"
    print(f"[gitvs] reconcile ({mode}): {len(rts)} resource types → "
          f"{len(acted)} effector(s) {'ran' if apply else 'planned'}, "
          f"{len(cited)} file-atom(s) cited, {len(skipped)} skipped.")
    for line in acted:
        print(f"   {'✓' if apply else '·'} {line}")
    for c in cited:
        print(f"   ⚑ owed  {c}")
    for s in skipped:
        print(f"   ~ skip  {s}")
    return 0


# ── entry ────────────────────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GITVS — the GitHub custodian: one resource graph, one loop.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("census", help="observe the live estate → the durable ledger (the Lens)")
    pc.add_argument("--print", action="store_true", help="print the ledger JSON to stdout too")
    pd = sub.add_parser("doctor", help="diff desired − observed; exit 0 ⟺ drift == ∅ (the Predicate)")
    pd.add_argument("--parity-only", action="store_true", help="class H only (deterministic, the PR gate)")
    pd.add_argument("--offline", action="store_true", help="det + offline-safe rungs; live rungs → SKIP")
    prc = sub.add_parser("reconcile", help="drive drift → policy via the three effector sinks (the Effector)")
    prc.add_argument("--apply", action="store_true", help="invoke the delegate/reap organs (each self-gates); default is a dry report")
    prc.add_argument("--check", action="store_true", help="report-only alias (the metabolize sensor idiom); never mutates")
    args = ap.parse_args(argv)

    estate = load_estate()

    if args.cmd == "census":
        led = observe(estate)
        write_ledger(led)
        n = led["repos"]["total"]
        print(f"[gitvs] census: online={led['online']} token={led['app']['token_path']} "
              f"repos={n if n is not None else '—'} open_prs={led['prs']['open_total']} "
              f"→ {LEDGER.relative_to(ROOT)}")
        if args.print:
            print(json.dumps(led, indent=2, sort_keys=True))
        return 0

    if args.cmd == "doctor":
        offline = bool(args.offline) or bool(os.environ.get("LIMEN_OFFLINE"))
        return doctor(estate, parity_only=bool(args.parity_only), offline=offline)

    if args.cmd == "reconcile":
        # --check is the report-only sensor idiom; --apply mutates. Report wins if both are given (safety).
        return reconcile(estate, apply=bool(args.apply) and not bool(args.check))

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
