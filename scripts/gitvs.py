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
effector + identity, if a declared adapter command path does not exist, or if a class `required_checks`
names a job no .github/workflows file defines. GITVS cannot declare governance it can't enact.

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
import calendar
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
CLI_SRC = SCRIPT_DIR.parent / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))
from limen.ci_failure import classify_ci_failure

# ROOT is the script's OWN tree (never LIMEN_ROOT) — a registry-drift predicate must validate the tree
# it lives in, so the parity gate checks THIS checkout's estate.yaml in a worktree/CI, not wherever an
# ambient LIMEN_ROOT points. The check-gates.py / check-params.py / credential-wall.py invariant. In the
# live beat the script and the conductor tree coincide, so runtime behavior is unchanged.
ROOT = SCRIPT_DIR.parent.resolve()
ESTATE = Path(os.environ.get("LIMEN_GITVS_ESTATE") or (ROOT / "institutio" / "github" / "estate.yaml"))
LEDGER = ROOT / "docs" / "github-estate-ledger.json"
STAMP = ROOT / "logs" / "gitvs.json"
# Per-repo census FACTS (names + visibility + SEO signals, private repos included) live in the
# gitignored runtime sink, NEVER the git-tracked ledger: private repo names stay out of the public
# tree, and volatile fields (size, pushed_at) never churn the ledger's idempotent fixed point.
FACTS = ROOT / "logs" / "gitvs-census-facts.json"
PR_DEBT_LEDGER = ROOT / "docs" / "github-pr-debt-ledger.json"
PR_DEBT_FACTS = ROOT / "logs" / "gitvs-pr-debt-facts.json"
# The classify receipt (per-repo proposals + rationale + path histograms — private names included):
# a gitignored RECEIPT, never the durable record. The durable record is estate.yaml's repo_overrides,
# landed by PR from `classify --emit-overrides` output — registry edits are never auto-written.
DECISIONS = ROOT / "logs" / "estate-decisions.json"
_GB_KB = 1_048_576  # REST `size` is KB; above 1 GB is an oversize annotation (classify R9)
WORKFLOWS = ROOT / ".github" / "workflows"

REQUIRED_RESOURCE_FIELDS = ("identity", "desired", "observe", "effector", "status", "owner", "note")
VALID_STATUS = {"active", "envisioned"}
TERMINAL_LEVER_STATUSES = frozenset({"discharged", "retired", "done", "closed"})
REQUIRED_CLASS_FIELDS = ("match", "visibility", "branch_protection", "required_checks", "owner", "note")
VALID_VISIBILITY = {"public", "private", "any"}
VALID_MATCH_FACT_KEYS = {"fork", "archived", "private"}  # census-fact keys a class may match on
VALID_PUBLISH_ELIGIBLE = {"never", "form_twin"}
VALID_SEO_KEYS = {"description", "topics_min", "homepage", "readme"}
VALID_SEO_REQ = {"required", "optional"}
# The ONE sanctioned per-repo block: each row is a durable human judgment (class + why required).
VALID_OVERRIDE_KEYS = {"class", "why", "publish_candidate", "split", "oversize", "audience"}
VALID_AUDIENCES = {"world", "collab", "self"}
# ACCESS — the partner-partition registry (institutio/github/access.yaml): per-repo collaborator
# grants. Role rank is total-ordered so the policy ceiling composes; `admin` is deliberately
# absent — an admin partner is structurally impossible to declare, not merely drift.
ACCESS = Path(os.environ.get("LIMEN_GITVS_ACCESS") or (ROOT / "institutio" / "github" / "access.yaml"))
GRANT_ROLE_RANK = {"pull": 0, "triage": 1, "push": 2, "maintain": 3}
REQUIRED_GRANT_FIELDS = ("login", "person", "role", "granted", "why")
# GitHub's live role_name/permissions vocabulary → the registry's grant-role vocabulary.
ROLE_NAME_TO_GRANT = {"read": "pull", "write": "push"}
REQUIRED_INTEGRATION_FIELDS = (
    "category",
    "app_slug",
    "config_file",
    "install_scope",
    "effector",
    "status",
    "owner",
    "note",
)
# The effector's three total sinks — the closure that makes the form complete.
EFFECTOR_KINDS = {"delegate", "file-atom", "reap"}
EFFECTOR_KINDS_WITH_COMMAND = {"delegate", "reap"}

LEDGER_SCHEMA = "limen.github_estate.v1"
PR_DEBT_SCHEMA = "limen.github_pr_debt.v2"


# ── auth (reuse the cascade; never touch App creds directly) ───────────────────────────────────
def _token() -> str | None:
    """Mint a token via the gh-app-token.sh cascade (App → PAT → gh). None if every path is exhausted."""
    if os.environ.get("LIMEN_OFFLINE"):
        return None
    try:
        r = subprocess.run(
            ["bash", str(ROOT / "scripts" / "gh-app-token.sh")],
            capture_output=True,
            text=True,
            timeout=45,
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


_GH_LOGIN_CACHE: dict[str, str | None] = {}


def _gh_login() -> str | None:
    """The keyring gh identity's login, cached per process. None ⟺ unauthenticated/offline.
    Routing predicate for the personal-estate lenses: /user/* routes are only truthful when the
    owner under census IS the authenticated user."""
    if "login" not in _GH_LOGIN_CACHE:
        r = _gh_user(["api", "user", "--jq", ".login"], timeout=15)
        _GH_LOGIN_CACHE["login"] = ((r.stdout or "").strip() or None) if r.returncode == 0 else None
    return _GH_LOGIN_CACHE["login"]


def _token_path() -> str:
    """Which cascade path resolves (app|pat|gh|none) — prints NO secret."""
    try:
        r = subprocess.run(
            ["bash", str(ROOT / "scripts" / "gh-app-token.sh"), "--which"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return (r.stdout or "").strip().split()[0] if r.returncode == 0 and r.stdout.strip() else "none"
    except Exception:
        return "none"


# ── the Estate (desired-state) ─────────────────────────────────────────────────────────────────
def load_estate() -> dict:
    """The public registry, plus the gitignored private overlay (estate.private.yaml) when present.
    The overlay may ONLY deepen repo_overrides (sensitive rationale rows — arca-sealed for
    durability); it can never touch classes/resources, so CI (which never has the overlay) and a
    hydrated live tree evaluate the same policy surface."""
    try:
        estate = yaml.safe_load(ESTATE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    overlay = ESTATE.parent / "estate.private.yaml"
    if overlay.exists():
        try:
            priv = yaml.safe_load(overlay.read_text(encoding="utf-8")) or {}
            merged = {**(estate.get("repo_overrides") or {}), **(priv.get("repo_overrides") or {})}
            if merged:
                estate["repo_overrides"] = merged
        except Exception:
            pass  # a broken overlay never breaks policy evaluation of the public registry
    return estate


def load_access() -> dict | None:
    """The partner-partition registry (ACCESS). None ⟺ absent — a skip, never a failure: the
    registry is sparse by design (only repos with grants), and fixture estates without an access
    file must evaluate exactly as before it existed."""
    if not ACCESS.exists():
        return None
    try:
        return yaml.safe_load(ACCESS.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}  # unparseable ≠ absent: parity reports it as a defect


def owners(estate: dict) -> list[str]:
    """Owners to enumerate — LIMEN_GITVS_OWNERS override, else derived from the class globs' owner
    prefixes ("names are outputs" — never pin a repo list). Falls back to the conductor owner."""
    raw = os.environ.get("LIMEN_GITVS_OWNERS", "")
    listed = [o.strip() for o in raw.split(",") if o.strip()]
    if listed:
        return listed
    derived: list[str] = []
    for cls in (estate.get("classes") or {}).values():
        for m in cls.get("match") or []:
            owner = str(m).split("/", 1)[0]
            if owner and "*" not in owner and owner not in derived:
                derived.append(owner)
    # Shelf orgs are declared registry data (shelf_assignments) — enumerate them too, or the
    # census never sees shelf repos and class P reads every declared shelf row as absent.
    for org in (estate.get("shelf_assignments") or {}).get("shelves") or {}:
        o = str(org)
        if o and o not in derived:
            derived.append(o)
    return derived or ["organvm"]


def classify_repo(repo: str, estate: dict, facts: dict | None = None) -> str | None:
    """First-match-wins bucket of an owner/repo into a class name. Precedence: an explicit
    `repo_overrides` row (durable per-repo human judgment, `why:` required by parity) wins; then
    fact-matched classes (`match_facts` diffed against the census facts — skipped when no facts are
    in hand, e.g. offline parity contexts); then the class globs (most-specific class first)."""
    row = (estate.get("repo_overrides") or {}).get(repo)
    if isinstance(row, dict) and row.get("class"):
        return str(row["class"])
    for name, cls in (estate.get("classes") or {}).items():
        mf = cls.get("match_facts")
        if mf:
            if not isinstance(facts, dict):
                continue
            if not all(bool(facts.get(k)) == bool(v) for k, v in mf.items()):
                continue
        for glob in cls.get("match") or []:
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
        # Unpack ALL of it: the closed-head map carries reap-branches' proof 3 (the DECIDED class),
        # and dropping it here would silently re-file every closed-PR branch as `livework` in this
        # histogram. The except-clause below returns {} on any error, so a stale arity would degrade
        # this lens to empty rather than fail — keep the call in exact lockstep with the module.
        merged, open_, closed, _online = rb.gh_head_states()
        hist: dict[str, int] = {}
        for b in rb.local_branches():
            v = rb.classify(rb.gather_facts(b, dref, checked, merged, open_, dname, closed))
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


def _owner_open_pr_counts(owner: str, token: str | None) -> dict[str, int] | None:
    """Return exact open-PR counts by repo through the paginated repository graph.

    GitHub search is capped and an App token makes ``--author @me`` mean the App, so neither is an
    estate census. Repository ``totalCount`` is exact and adding/removing repositories naturally
    changes the result without a repo list or scan ceiling in Limen.
    """

    for root_kind in ("organization", "user"):
        cursor: str | None = None
        counts: dict[str, int] = {}
        while True:
            affiliation = ",ownerAffiliations:OWNER" if root_kind == "user" else ""
            query = (
                "query($login:String!,$cursor:String){"
                f"{root_kind}(login:$login){{repositories(first:100,after:$cursor{affiliation}){{"
                "nodes{nameWithOwner pullRequests(states:OPEN){totalCount}}"
                "pageInfo{hasNextPage endCursor}}}}"
            )
            args = ["api", "graphql", "-f", f"query={query}", "-F", f"login={owner}"]
            if cursor:
                args.extend(["-F", f"cursor={cursor}"])
            result = _gh(args, token, timeout=60)
            if result.returncode != 0:
                return None
            try:
                payload = json.loads(result.stdout or "{}")
                owner_data = (payload.get("data") or {}).get(root_kind)
                if owner_data is None:
                    break
                repositories = owner_data["repositories"]
                for node in repositories.get("nodes") or []:
                    repo = str(node["nameWithOwner"])
                    counts[repo] = int((node.get("pullRequests") or {})["totalCount"])
                page = repositories["pageInfo"]
                if not page.get("hasNextPage"):
                    return counts
                cursor = str(page.get("endCursor") or "")
                if not cursor:
                    return None
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return None
    return None


def _resolve_owner_login(owner: str, token: str | None) -> str | None:
    """Resolve aliases and renamed accounts to GitHub's current canonical login."""

    del token
    result = _gh_user(["api", f"/users/{owner}", "--jq", ".login"], timeout=30)
    login = (result.stdout or "").strip()
    return login if result.returncode == 0 and login else None


def _owner_repo_inventory(owner: str, token: str | None) -> dict | None:
    """Enumerate one canonical owner's complete repository graph.

    Repository pages are reconciled against GraphQL ``totalCount``. Each row
    carries the repository's exact open-PR total so zero-PR repositories do not
    require a second request while every non-empty repository still gets its
    own independently paginated PR cursor.
    """

    del token
    for root_kind in ("organization", "user"):
        cursor: str | None = None
        expected_total: int | None = None
        repositories: dict[str, dict] = {}
        page_count = 0
        while True:
            affiliation = ",ownerAffiliations:OWNER" if root_kind == "user" else ""
            query = (
                "query($login:String!,$cursor:String){"
                f"{root_kind}(login:$login){{repositories(first:100,after:$cursor{affiliation}){{"
                "totalCount nodes{nameWithOwner isPrivate isArchived pullRequests(states:OPEN){totalCount}}"
                "pageInfo{hasNextPage endCursor}}}}"
            )
            args = ["api", "graphql", "-f", f"query={query}", "-F", f"login={owner}"]
            if cursor:
                args.extend(["-F", f"cursor={cursor}"])
            result = _gh_user(args, timeout=90)
            if result.returncode != 0:
                if cursor is None:
                    break
                return None
            try:
                payload = json.loads(result.stdout or "{}")
                owner_data = (payload.get("data") or {}).get(root_kind)
                if owner_data is None:
                    break
                block = owner_data["repositories"]
                total = int(block["totalCount"])
                if expected_total is None:
                    expected_total = total
                elif total != expected_total:
                    return None
                for node in block.get("nodes") or []:
                    name = str(node["nameWithOwner"])
                    if name in repositories:
                        return None
                    repositories[name] = {
                        "name_with_owner": name,
                        "private": bool(node.get("isPrivate")),
                        "archived": bool(node.get("isArchived")),
                        "open_pr_total": int((node.get("pullRequests") or {})["totalCount"]),
                    }
                page_count += 1
                page = block["pageInfo"]
                if not page.get("hasNextPage"):
                    if expected_total != len(repositories):
                        return None
                    return {
                        "owner": owner,
                        "repository_total": expected_total,
                        "page_count": page_count,
                        "repositories": [repositories[name] for name in sorted(repositories)],
                    }
                cursor = str(page.get("endCursor") or "")
                if not cursor:
                    return None
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return None
    return None


def _repo_open_prs(repo: str, expected_total: int, token: str | None) -> dict:
    """Page every open PR in one repository and reconcile its live total."""

    del token
    if expected_total == 0:
        return {"exhaustive": True, "expected_total": 0, "page_count": 0, "rows": [], "error": None}
    try:
        owner, name = repo.split("/", 1)
    except ValueError:
        return {
            "exhaustive": False,
            "expected_total": expected_total,
            "page_count": 0,
            "rows": [],
            "error": "invalid-repository-name",
        }
    cursor: str | None = None
    rows: dict[int, dict] = {}
    page_count = 0
    while True:
        query = (
            "query($owner:String!,$name:String!,$cursor:String){"
            "repository(owner:$owner,name:$name){pullRequests(states:OPEN,first:100,after:$cursor,"
            "orderBy:{field:UPDATED_AT,direction:DESC}){totalCount "
            "nodes{number url title isDraft updatedAt headRefName headRefOid body "
            "author{login} assignees(first:10){nodes{login}} labels(first:50){nodes{name}}} "
            "pageInfo{hasNextPage endCursor}}}}"
        )
        args = [
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
        ]
        if cursor:
            args.extend(["-F", f"cursor={cursor}"])
        result = _gh_user(args, timeout=90)
        if result.returncode != 0:
            return {
                "exhaustive": False,
                "expected_total": expected_total,
                "page_count": page_count,
                "rows": list(rows.values()),
                "error": "pull-request-page-failed",
            }
        try:
            payload = json.loads(result.stdout or "{}")
            repository = (payload.get("data") or {}).get("repository")
            if not isinstance(repository, dict):
                raise ValueError("repository unavailable")
            block = repository["pullRequests"]
            if int(block["totalCount"]) != expected_total:
                raise ValueError("pull-request-total-moved")
            for node in block.get("nodes") or []:
                number = int(node["number"])
                if number in rows:
                    raise ValueError("duplicate-pull-request-cursor-row")
                rows[number] = dict(node)
            page_count += 1
            page = block["pageInfo"]
            if not page.get("hasNextPage"):
                if len(rows) != expected_total:
                    raise ValueError("pull-request-total-not-reconciled")
                return {
                    "exhaustive": True,
                    "expected_total": expected_total,
                    "page_count": page_count,
                    "rows": [rows[number] for number in sorted(rows)],
                    "error": None,
                }
            cursor = str(page.get("endCursor") or "")
            if not cursor:
                raise ValueError("pull-request-cursor-missing")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return {
                "exhaustive": False,
                "expected_total": expected_total,
                "page_count": page_count,
                "rows": list(rows.values()),
                "error": str(exc),
            }


def _pr_owner(row: dict, owner_label_prefix: str) -> tuple[str | None, str | None]:
    labels = sorted(
        str(node.get("name") or "") for node in ((row.get("labels") or {}).get("nodes") or []) if isinstance(node, dict)
    )
    labelled = [label[len(owner_label_prefix) :].strip() for label in labels if label.startswith(owner_label_prefix)]
    labelled = [owner for owner in labelled if owner]
    if len(labelled) == 1:
        return labelled[0], "label"
    assignees = sorted(
        str(node.get("login") or "")
        for node in ((row.get("assignees") or {}).get("nodes") or [])
        if isinstance(node, dict) and node.get("login")
    )
    if assignees:
        return assignees[0], "assignee"
    author = row.get("author") or {}
    if isinstance(author, dict) and author.get("login"):
        return str(author["login"]), "author"
    return None, None


def _pr_lifecycle(
    labels: set[str],
    body: str,
    policy: dict,
) -> tuple[str | None, str, list[str]]:
    allowed = {
        str(value)
        for value in (
            policy.get("lifecycle_labels")
            or (
                "lifecycle:delivery",
                "lifecycle:preservation",
                "lifecycle:active-human",
                "lifecycle:blocked",
                "lifecycle:superseded",
            )
        )
    }
    matches = sorted(labels & allowed)
    if len(matches) == 1:
        return matches[0], "label", matches
    if len(matches) > 1:
        return None, "conflicting-labels", matches

    preservation_labels = {str(value) for value in (policy.get("preservation_labels") or ())}
    preservation_markers = [str(value) for value in (policy.get("preservation_markers") or ()) if str(value)]
    if labels.intersection(preservation_labels) or any(marker in body for marker in preservation_markers):
        return "lifecycle:preservation", "legacy-preservation-marker", []
    return None, "missing-label", []


def _body_receipt_references(body: str, marker: str) -> list[str]:
    pattern = re.compile(
        rf"(?im)^\s*{re.escape(marker)}\s*:\s*(https://github\.com/[^\s]+|[\w.-]+/[\w.-]+#\d+|#\d+)\s*$"
    )
    return sorted(set(pattern.findall(body)))


def _pr_lifecycle_debt_reasons(row: dict) -> list[str]:
    reasons: list[str] = []
    if not row.get("lifecycle_disposition"):
        reasons.append("missing-or-conflicting-lifecycle-disposition")
    exact_owner = row.get("exact_head_owner")
    if not isinstance(exact_owner, dict) or not exact_owner.get("owner") or not exact_owner.get("head_oid"):
        reasons.append("missing-exact-head-owner")
    if row.get("lifecycle_disposition") == "lifecycle:superseded" and not row.get("supersession_target"):
        reasons.append("missing-supersession-target")
    return reasons


def _classify_open_pr(repo: str, row: dict, policy: dict, now: datetime) -> dict:
    number = int(row["number"])
    owner_label_prefix = str(policy.get("owner_label_prefix") or "owner:")
    owner, owner_source = _pr_owner(row, owner_label_prefix)
    head_oid = str(row.get("headRefOid") or "")
    labels = {
        str(node.get("name") or "") for node in ((row.get("labels") or {}).get("nodes") or []) if isinstance(node, dict)
    }
    body = str(row.get("body") or "")
    lifecycle, lifecycle_source, lifecycle_matches = _pr_lifecycle(labels, body, policy)
    dependencies = _body_receipt_references(body, "Depends on")
    supersession_targets = _body_receipt_references(body, "Superseded by")
    supersession_target = supersession_targets[0] if len(supersession_targets) == 1 else None
    markers = [str(marker) for marker in (policy.get("preservation_markers") or []) if str(marker)]
    preservation = bool(labels.intersection(policy.get("preservation_labels") or [])) or any(
        marker in body for marker in markers
    )
    predicate = f"github:required-checks:{repo}@{head_oid}" if head_oid else None
    merge_condition = f"github:merge-queue:{repo}#{number}:ready-and-required-checks-green" if head_oid else None
    base = {
        "repository": repo,
        "number": number,
        "url": row.get("url"),
        "private": False,
        "owner": owner,
        "owner_source": owner_source,
        "exact_head_owner": {
            "owner": owner,
            "owner_source": owner_source,
            "head_oid": head_oid or None,
        },
        "predicate": predicate,
        "receipt_target": row.get("url"),
        "merge_condition": merge_condition,
        "head_oid": head_oid or None,
        "title": row.get("title"),
        "draft": bool(row.get("isDraft")),
        "dependencies": dependencies,
        "supersession_target": supersession_target,
        "lifecycle_disposition": lifecycle,
        "lifecycle_disposition_source": lifecycle_source,
        "lifecycle_label_matches": lifecycle_matches,
        "disposition_observed_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "updated_at": row.get("updatedAt"),
    }
    if preservation and owner and head_oid:
        result = {
            **base,
            "classification": "preservation",
            "classification_reason": "remote-preservation-marker",
        }
        result["lifecycle_debt_reasons"] = _pr_lifecycle_debt_reasons(result)
        result["lifecycle_complete"] = not result["lifecycle_debt_reasons"]
        return result

    try:
        updated = datetime.fromisoformat(str(row.get("updatedAt") or "").replace("Z", "+00:00"))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (now - updated.astimezone(timezone.utc)).total_seconds() / 3600)
    except ValueError:
        age_hours = float("inf")
    max_age = int(policy.get("active_owner_max_age_hours") or 168)
    if owner and head_oid and age_hours <= max_age:
        result = {
            **base,
            "classification": "active_custody",
            "classification_reason": "fresh-remote-owner-and-head",
            "age_hours": round(age_hours, 2),
        }
        result["lifecycle_debt_reasons"] = _pr_lifecycle_debt_reasons(result)
        result["lifecycle_complete"] = not result["lifecycle_debt_reasons"]
        return result
    if owner and predicate and merge_condition:
        result = {
            **base,
            "classification": "owner_route",
            "classification_reason": "stale-or-inactive-routed-to-live-owner",
            "age_hours": None if age_hours == float("inf") else round(age_hours, 2),
        }
        result["lifecycle_debt_reasons"] = _pr_lifecycle_debt_reasons(result)
        result["lifecycle_complete"] = not result["lifecycle_debt_reasons"]
        return result
    result = {
        **base,
        "classification": "untyped",
        "classification_reason": "missing-owner-or-remote-head",
        "age_hours": None if age_hours == float("inf") else round(age_hours, 2),
    }
    result["lifecycle_debt_reasons"] = _pr_lifecycle_debt_reasons(result)
    result["lifecycle_complete"] = not result["lifecycle_debt_reasons"]
    return result


def _redact_pr_row(row: dict) -> dict:
    if not row.get("private"):
        return row
    repo = str(row.get("repository") or "")
    number = int(row.get("number") or 0)
    owner = str(row.get("owner") or "")
    return {
        **row,
        "repository": None,
        "number": None,
        "url": None,
        "owner": None,
        "head_oid": None,
        "exact_head_owner": None,
        "predicate": None,
        "receipt_target": None,
        "merge_condition": None,
        "dependencies": None,
        "supersession_target": None,
        "pr_key": hashlib.sha256(f"{repo}#{number}".encode()).hexdigest(),
        "owner_key": hashlib.sha256(owner.encode()).hexdigest() if owner else None,
    }


def _apply_repository_state(row: dict, repository: dict) -> dict:
    result = {
        **row,
        "private": bool(repository["private"]),
        "repository_archived": bool(repository.get("archived")),
    }
    if result["repository_archived"] and result.get("lifecycle_disposition_source") == "missing-label":
        result["lifecycle_disposition"] = "lifecycle:blocked"
        result["lifecycle_disposition_source"] = "repository-archived-immutable"
        result["lifecycle_label_matches"] = []
        result["lifecycle_debt_reasons"] = _pr_lifecycle_debt_reasons(result)
        result["lifecycle_complete"] = not result["lifecycle_debt_reasons"]
    return result


def pr_debt_census(estate: dict, *, now: datetime | None = None) -> tuple[dict, dict]:
    """Return the full private runtime receipt and its tracked redacted projection."""

    observed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    online = not os.environ.get("LIMEN_OFFLINE") and shutil.which("gh") is not None
    token = "user-native" if online else None
    requested_owners = owners(estate)
    failures: list[str] = []
    canonical_owners: list[str] = []
    for requested in requested_owners:
        canonical = _resolve_owner_login(requested, token) if token else None
        if not canonical:
            failures.append(f"owner-unavailable:{requested}")
            continue
        if canonical not in canonical_owners:
            canonical_owners.append(canonical)

    repositories: dict[str, dict] = {}
    repository_pages = 0
    for owner in canonical_owners:
        inventory = _owner_repo_inventory(owner, token)
        if inventory is None:
            failures.append(f"repository-cursor-failed:{owner}")
            continue
        repository_pages += int(inventory["page_count"])
        for repository in inventory["repositories"]:
            name = str(repository["name_with_owner"])
            prior = repositories.get(name)
            if prior is not None and prior != repository:
                failures.append(f"repository-reconciliation-conflict:{name}")
                continue
            repositories[name] = repository

    policy = estate.get("pr_debt_policy") or {}
    classified: list[dict] = []
    pr_pages = 0
    expected_pr_total = sum(int(repo["open_pr_total"]) for repo in repositories.values())
    for repo_name in sorted(repositories):
        repository = repositories[repo_name]
        page = _repo_open_prs(repo_name, int(repository["open_pr_total"]), token)
        pr_pages += int(page["page_count"])
        if not page["exhaustive"]:
            failures.append(f"pull-request-cursor-failed:{repo_name}:{page['error']}")
        for pr in page["rows"]:
            row = _apply_repository_state(
                _classify_open_pr(repo_name, pr, policy, observed),
                repository,
            )
            classified.append(row)

    if len(classified) != expected_pr_total:
        failures.append(f"open-pr-total-not-reconciled:{len(classified)}/{expected_pr_total}")
    counts: dict[str, int] = {}
    lifecycle_counts: dict[str, int] = {}
    for row in classified:
        category = str(row["classification"])
        counts[category] = counts.get(category, 0) + 1
        disposition = str(row.get("lifecycle_disposition") or "untyped")
        lifecycle_counts[disposition] = lifecycle_counts.get(disposition, 0) + 1
    classification_untyped = counts.get("untyped", 0)
    lifecycle_untyped = sum(not bool(row.get("lifecycle_complete")) for row in classified)
    exhaustive = not failures
    full = {
        "schema": PR_DEBT_SCHEMA,
        "generated_at": observed.isoformat().replace("+00:00", "Z"),
        "exhaustive": exhaustive,
        "requested_owner_count": len(requested_owners),
        "canonical_owner_count": len(canonical_owners),
        "canonical_owners": sorted(canonical_owners),
        "repository_count": len(repositories),
        "private_repository_count": sum(bool(repo["private"]) for repo in repositories.values()),
        "open_pr_count": len(classified),
        "expected_open_pr_count": expected_pr_total,
        "classification_counts": dict(sorted(counts.items())),
        "lifecycle_disposition_counts": dict(sorted(lifecycle_counts.items())),
        "classification_untyped_count": classification_untyped,
        "lifecycle_untyped_count": lifecycle_untyped,
        "untyped_count": sum(
            row.get("classification") == "untyped" or not row.get("lifecycle_complete") for row in classified
        ),
        "cursor_reconciliation": {
            "repository_pages": repository_pages,
            "pull_request_pages": pr_pages,
            "failures": failures,
        },
        "pull_requests": classified,
    }
    public_rows = [_redact_pr_row(row) for row in classified]
    tracked = {
        **{key: value for key, value in full.items() if key not in {"canonical_owners", "pull_requests"}},
        "canonical_owner_count": len(canonical_owners),
        "cursor_reconciliation": {
            "repository_pages": repository_pages,
            "pull_request_pages": pr_pages,
            "failure_count": len(failures),
        },
        "pull_requests": public_rows,
    }
    tracked["content_sha256"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in tracked.items() if key not in {"generated_at", "content_sha256"}},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return full, tracked


def pr_debt(estate: dict, *, check: bool, print_json: bool, write_ledger: bool) -> int:
    full, tracked = pr_debt_census(estate)
    if write_ledger:
        PR_DEBT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        PR_DEBT_LEDGER.write_text(json.dumps(tracked, indent=2, sort_keys=True) + "\n")
        PR_DEBT_FACTS.parent.mkdir(parents=True, exist_ok=True)
        PR_DEBT_FACTS.write_text(json.dumps(full, indent=2, sort_keys=True) + "\n")
    if print_json:
        print(json.dumps(tracked, indent=2, sort_keys=True))
    ok = bool(full["exhaustive"] and full["untyped_count"] == 0)
    if not print_json:
        mark = "✓" if ok else "✗"
        print(
            f"{mark} gitvs pr-debt: repos={full['repository_count']} "
            f"open_prs={full['open_pr_count']} exhaustive={str(full['exhaustive']).lower()} "
            f"untyped={full['untyped_count']}"
        )
    return 1 if check and not ok else 0


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


def _org_class(org: str, estate: dict) -> tuple[str | None, dict | None]:
    """First-match-wins bucket of an org login into an `orgs:` registry row — the classify_repo
    analogue, one level up (the ACCOUNT layer)."""
    for name, row in (estate.get("orgs") or {}).items():
        if not isinstance(row, dict):
            continue
        for glob in row.get("match") or []:
            if fnmatch.fnmatch(org, glob):
                return name, row
    return None, None


def _org_posture(estate: dict, online: bool) -> dict:
    """The ACCOUNT-layer Lens: every org the owner belongs to, with its live billing plan and repo
    counts (gh api /orgs/{o}). User-scoped keyring auth (the _org_app_estate contract — the per-org
    App token structurally cannot see the user's other orgs). Pure observation: the policy diff
    against the `orgs:` registry is doctor class L. Fail-open; deterministic (sorted)."""
    out: dict = {"by_org": None}
    if not online or not (estate.get("orgs") or {}):
        return out
    r = _gh_user(["api", "/user/orgs", "--paginate", "--jq", ".[].login"], timeout=45)
    if r.returncode != 0:
        return out
    by_org: dict[str, dict] = {}
    for o in sorted({s.strip() for s in (r.stdout or "").splitlines() if s.strip()}):
        ri = _gh_user(
            ["api", f"/orgs/{o}", "--jq", "{plan: .plan.name, private: .total_private_repos, public: .public_repos}"],
            timeout=30,
        )
        if ri.returncode != 0:
            continue
        try:
            row = json.loads(ri.stdout or "{}")
        except json.JSONDecodeError:
            continue
        cls, _ = _org_class(o, estate)
        by_org[o] = {
            "plan": row.get("plan"),
            "repos": int(row.get("private") or 0) + int(row.get("public") or 0),
            "class": cls,
        }
    out["by_org"] = by_org
    return out


def _owner_repos(
    owner: str,
    token: str | None,  # allow-secret (type annotation, no value)
    user_scoped: bool = False,
) -> list[dict] | None:
    """Enumerate ALL repos of an owner with per-repo census facts. Tries the org route first —
    /orgs/{owner}/repos?type=all surfaces the private repos the cascade token can see (the /users
    route is structurally public-only, the census blindness this Lens fix removes) — then falls back
    to /users/{owner}/repos for personal accounts. `user_scoped` runs the read on the owner's
    NATIVE gh identity: non-canonical owners (personal estate, shelf orgs) sit outside the App
    installation, and the App token silently hides their PRIVATE repos. None ⟺ both routes
    failed (fail-open)."""
    jq = (
        ".[] | {full_name, private, fork, archived, size, description, homepage, "
        "stars: .stargazers_count, topics_count: ((.topics // []) | length), pushed_at}"
    )
    routes = [f"/orgs/{owner}/repos?type=all", f"/users/{owner}/repos"]
    if user_scoped and _gh_login() == owner:
        # The authenticated user's own estate: /user/repos?affiliation=owner is the ONLY route
        # that surfaces their PRIVATE repos (/users/{owner}/repos is structurally public-only —
        # the personal-estate half of the census blindness, PR B). The owner filter below drops
        # any affiliation row outside the {owner}/ namespace.
        routes.insert(0, "/user/repos?affiliation=owner")
    for route in routes:
        args = ["api", route, "--paginate", "-X", "GET", "-F", "per_page=100", "--jq", jq]
        r = _gh_user(args, timeout=180) if user_scoped else _gh(args, token, timeout=180)
        if r.returncode != 0:
            continue
        if not (r.stdout or "").strip():
            return []
        rows: list[dict] = []
        for ln in r.stdout.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                return None
            if not isinstance(row, dict) or not row.get("full_name"):
                return None
            if str(row["full_name"]).split("/", 1)[0] != owner:
                continue
            rows.append(row)
        return rows
    return None


def _write_census_facts(rows: list[dict]) -> None:
    """The per-repo facts sink (logs/, gitignored — see the FACTS note). Deterministic (sorted by
    full_name, sorted keys) so downstream consumers (classify, seo-audit) read a stable shape."""
    try:
        FACTS.parent.mkdir(parents=True, exist_ok=True)
        body = {"schema": "limen.gitvs_census_facts.v1", "repos": sorted(rows, key=lambda r: r["full_name"])}
        FACTS.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    except Exception as e:  # observability must never break the beat
        print(f"[gitvs] note: census-facts write skipped ({str(e)[:80]})")


def _collaborator_census(estate: dict, access: dict | None, token: str | None, online: bool) -> dict:
    """Class N's Lens: outside collaborators + pending invites over the bounded probe set
    (granted repos ∪ never-grant repos), plus each owner org's outside-collaborator roll.
    Logins + roles only — the same public facts the ACCESS registry already carries."""
    out: dict = {"complete": False, "by_repo": {}, "org_outside": {}}
    if not online or not isinstance(access, dict) or not access:
        return out
    grants = access.get("grants") or {}
    policy = access.get("policy") or {}
    probe = sorted({str(r) for r in grants} | {str(r) for r in (policy.get("never_grant_repos") or [])})
    ok = True

    def _owner_org_class(repo: str) -> str | None:
        # The orgs-registry class is the routing truth: 'canonical' rides the App token;
        # everything else (shelf orgs, and the personal account which matches NO orgs row)
        # sits outside the App installation and must read user-scoped. NOTE: owners(estate)
        # is NOT usable here — it includes the personal account via its class glob.
        cls_name, _row = _org_class(repo.split("/", 1)[0], estate)
        return cls_name

    def _roll(repo: str, path: str, jq: str) -> subprocess.CompletedProcess:
        if _owner_org_class(repo) == "canonical":
            return _gh(["api", path, "--jq", jq], token, timeout=30)
        return _gh_user(["api", path, "--jq", jq], timeout=30)

    def _outside_path_jq(repo: str) -> tuple[str, str]:
        owner, _, _name = repo.partition("/")
        if _owner_org_class(repo) is None:
            # 'outside' is an ORG affiliation — on a personal repo it misses direct invitees
            # (victoroff-os: david reads write in the full roll, absent from the outside roll).
            # The personal-estate lens is every collaborator except the owner.
            return (
                f"/repos/{repo}/collaborators?per_page=100",
                f'[.[] | select(.login != "{owner}") | {{login: .login, role: .role_name}}] | sort_by(.login)',
            )
        return (
            f"/repos/{repo}/collaborators?affiliation=outside&per_page=100",
            "[.[] | {login: .login, role: .role_name}] | sort_by(.login)",
        )

    for repo in probe:
        row: dict = {"outside": None, "invitations": None}
        r = _roll(repo, *_outside_path_jq(repo))
        if r.returncode == 0:
            try:
                row["outside"] = json.loads(r.stdout or "[]")
            except ValueError:
                ok = False
        else:
            ok = False
        r = _roll(
            repo,
            f"/repos/{repo}/invitations?per_page=100",
            "[.[] | {id: .id, login: .invitee.login, role: .permissions}] | sort_by(.login)",
        )
        if r.returncode == 0:
            try:
                row["invitations"] = json.loads(r.stdout or "[]")
            except ValueError:
                ok = False
        else:
            ok = False
        out["by_repo"][repo] = row
    for org in owners(estate):
        # Non-canonical org rolls (shelf orgs) sit outside the App installation — user-scoped.
        org_args = ["api", f"/orgs/{org}/outside_collaborators?per_page=100", "--jq", "[.[].login] | sort"]
        if _org_class(org, estate)[0] == "canonical":
            r = _gh(org_args, token, timeout=30)
        else:
            r = _gh_user(org_args, timeout=30)
        try:
            # personal accounts 404 here — degrade to None; class N skips that roll, never guesses
            out["org_outside"][org] = json.loads(r.stdout or "[]") if r.returncode == 0 else None
        except ValueError:
            out["org_outside"][org] = None
    # ── The personal-estate FULL-ROLL lens (rungs D + N, PR B). A personal account has no org
    # outside-collaborator roll (the 404 above), so derive the equivalent: enumerate the
    # authenticated owner's repos user-scoped (the only route that sees their privates) and take
    # each repo's every-collaborator-except-owner roll. personal_full feeds class D beyond N's
    # bounded probe set; the unioned logins become the synthesized org_outside roll, so class N
    # stops skipping the personal owner. Unreadable stays None — a SKIP, never a guess.
    out["personal_full"] = None
    for owner in owners(estate):
        if _org_class(owner, estate)[0] is not None or _gh_login() != owner:
            continue
        inventory = _owner_repos(owner, token, user_scoped=True)
        if inventory is None:
            out["org_outside"][owner] = None
            continue
        full_rolls: dict[str, list | None] = {}
        roll_logins: set[str] = set()
        for inv_row in inventory:
            repo = str(inv_row["full_name"])
            roll_path, roll_jq = _outside_path_jq(repo)
            r = _gh_user(["api", roll_path, "--jq", roll_jq], timeout=30)
            if r.returncode != 0:
                ok = False
                full_rolls[repo] = None
                continue
            try:
                outside = json.loads(r.stdout or "[]")
            except ValueError:
                ok = False
                full_rolls[repo] = None
                continue
            full_rolls[repo] = outside
            roll_logins |= {str(c.get("login") or "") for c in outside if isinstance(c, dict)}
        out["personal_full"] = full_rolls
        out["org_outside"][owner] = sorted(roll_logins)
    out["complete"] = ok
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
        "app": {
            "installed": None,
            "slug": (estate.get("app") or {}).get("slug"),
            "token_path": _token_path(),
            "installations": None,
        },
        "repos": {"total": None, "by_class": {}},
        "prs": {"open_total": None, "by_repo": {}, "complete": False},
        "branches": {"conductor_by_reason": _local_branch_reasons()},
        "secrets": {"homed": None},
        "usage": {"rate_limit_headroom_pct": None},
    }

    owner_list = owners(estate)

    # PRs — exact per-repository totalCount, paginated across the live owner graph. No search cap.
    if online:
        by_repo: dict[str, int] = {}
        complete = True
        for owner in owner_list:
            counts = _owner_open_pr_counts(owner, token)
            if counts is None:
                complete = False
                break
            by_repo.update(counts)
        if complete:
            nonzero = {repo: count for repo, count in by_repo.items() if count}
            led["prs"] = {
                "open_total": sum(by_repo.values()),
                "by_repo": dict(sorted(nonzero.items())),
                "complete": True,
            }

    # App installations (permissions posture; over-grant is class D).
    if online:
        r = _gh(["api", "/app/installations", "--jq", "length"], token, timeout=30)
        if r.returncode == 0 and (r.stdout or "").strip().isdigit():
            n = int(r.stdout.strip())
            led["app"]["installed"] = n > 0
            led["app"]["installations"] = n

    # Repo census by class — the FULL estate (org route; private repos included when the token can
    # see them). Aggregate counts land in the public ledger; per-repo facts go to the gitignored
    # FACTS sink only (private names never enter the git-tracked ledger).
    if online:
        total = 0
        by_class: dict[str, int] = {}
        vis = {"public": 0, "private": 0}
        fork_n = archived_n = 0
        facts_all: list[dict] = []
        complete = True
        for owner in owner_list:
            # Non-canonical owners (personal estate, shelf orgs) sit outside the App
            # installation — enumerate them user-scoped or their private repos vanish silently.
            cls_name, _row = _org_class(owner, estate)
            rows = _owner_repos(owner, token, user_scoped=(cls_name != "canonical"))
            if rows is None:
                complete = False
                continue
            for row in rows:
                full = str(row["full_name"])
                total += 1
                cls = classify_repo(full, estate, facts=row) or "unclassed"
                row["class"] = cls
                by_class[cls] = by_class.get(cls, 0) + 1
                vis["private" if row.get("private") else "public"] += 1
                fork_n += 1 if row.get("fork") else 0
                archived_n += 1 if row.get("archived") else 0
                facts_all.append(row)
        if total:
            led["repos"] = {
                "total": total,
                "complete": complete,
                "by_class": dict(sorted(by_class.items())),
                "by_visibility": vis,
                "forks": fork_n,
                "archived": archived_n,
            }
            _write_census_facts(facts_all)

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

    # SEO posture summary — fail-open read of the seo-audit sweep artifact (counts only; the
    # per-repo detail stays in the runtime sink so the ledger fixed point never churns on it).
    led["seo"] = _seo_summary()

    # Org posture — the ACCOUNT layer (billing plan + repo custody per org; class L's input).
    led["orgs"] = _org_posture(estate, online)

    # Collaborator census — the partner-partition layer (class N's input; ACCESS is desired-state).
    led["collaborators"] = _collaborator_census(estate, load_access(), token, online)
    return led


def _seo_summary() -> dict:
    try:
        body = json.loads((ROOT / "logs" / "seo-audit.json").read_text(encoding="utf-8"))
        return {
            "audited": body.get("audited"),
            "passing": body.get("passing"),
            "failing": len(body.get("failing") or []),
        }
    except Exception:
        return {"audited": None, "passing": None, "failing": None}


def write_ledger(led: dict) -> None:
    """Durable, git-tracked ground truth. Deterministic (sorted keys); the only volatile field is
    excluded from the doctor's diff so re-runs are an idempotent fixed point (census twice == identical)."""
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(led, indent=2, sort_keys=True) + "\n")
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        STAMP.write_text(
            json.dumps(
                {
                    "online": led.get("online"),
                    "prs": led["prs"]["open_total"],
                    "app_installed": led["app"]["installed"],
                },
                sort_keys=True,
            )
            + "\n"
        )
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
        for job in wf.get("jobs") or {}:
            ids.add(str(job))
    return ids


def _effector_defects(rt_name: str, effectors: object, *, require_reachable: bool) -> list[str]:
    """Validate the data-declared adapter, command, and activation policy for each effector."""
    defects: list[str] = []
    if not isinstance(effectors, list):
        return [f"resource '{rt_name}': effector must be a list of mappings"]
    for index, effector in enumerate(effectors):
        where = f"resource '{rt_name}' effector[{index}]"
        if not isinstance(effector, dict):
            defects.append(f"{where}: must be a mapping")
            continue
        kind = str(effector.get("kind") or "").strip()
        if kind == "manual":
            continue
        if kind not in EFFECTOR_KINDS:
            defects.append(f"{where}: kind '{kind}' not one of {sorted(EFFECTOR_KINDS | {'manual'})}")
            continue
        if kind == "file-atom":
            if not str(effector.get("target") or "").strip():
                defects.append(f"{where}: file-atom requires target")
            continue

        argv = effector.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg for arg in argv):
            defects.append(f"{where}: {kind} requires a non-empty string argv list")
            continue
        if require_reachable:
            for arg in argv[1:]:
                candidate = ROOT / arg
                if arg.startswith("scripts/") and not candidate.exists():
                    defects.append(f"{where}: command path '{arg}' does not exist")
        approval = effector.get("approval")
        if approval is not None:
            if not isinstance(approval, dict) or not str(approval.get("lever") or "").strip():
                defects.append(f"{where}: approval must name a lever")
    return defects


def _access_parity(estate: dict) -> list[str]:
    """The ACCESS registry's offline rung (partner partitioning): every grant row is a complete,
    ceiling-bounded human judgment, and no grant lands on an ungrantable repo/class. Absent file =
    skip (sparse-by-design); unparseable/malformed = defects. Mirrors the repo_overrides shape."""
    access = load_access()
    if access is None:
        return []
    fails: list[str] = []
    if not isinstance(access, dict) or not access:
        return [f"access registry {ACCESS.name}: missing or unparseable"]
    if "schema_version" not in access:
        fails.append("access: missing schema_version")
    for field in ("owner", "note"):
        if field not in access:
            fails.append(f"access: missing '{field}'")

    policy = access.get("policy")
    ceiling = "push"
    never_repos: set[str] = set()
    never_classes: set[str] = set()
    if not isinstance(policy, dict):
        fails.append("access: policy must be a mapping")
    else:
        for field in ("role_ceiling", "never_grant_classes", "never_grant_repos", "owner", "note"):
            if field not in policy:
                fails.append(f"access policy: missing '{field}'")
        ceiling = str(policy.get("role_ceiling") or "push")
        if ceiling not in GRANT_ROLE_RANK:
            fails.append(f"access policy: role_ceiling '{ceiling}' not in {sorted(GRANT_ROLE_RANK)}")
            ceiling = "push"
        declared_classes = estate.get("classes") or {}
        for cls_name in policy.get("never_grant_classes") or []:
            if cls_name not in declared_classes:
                fails.append(f"access policy: never_grant_class '{cls_name}' names no declared class")
            never_classes.add(str(cls_name))
        for repo in policy.get("never_grant_repos") or []:
            if not (isinstance(repo, str) and repo.count("/") == 1):
                fails.append(f"access policy: never_grant_repo '{repo}' is not an owner/repo name")
            never_repos.add(str(repo))

    grants = access.get("grants")
    if grants is None:
        grants = {}
    if not isinstance(grants, dict):
        fails.append("access: grants must be a mapping of repo → grant rows")
        grants = {}
    for repo, rows in grants.items():
        where = f"grant '{repo}'"
        if not (isinstance(repo, str) and repo.count("/") == 1):
            fails.append(f"{where}: not an owner/repo name")
            continue
        if repo in never_repos:
            fails.append(f"{where}: repo is in never_grant_repos — an engine repo never carries a grant")
        cls_name = classify_repo(repo, estate)
        if cls_name in never_classes:
            fails.append(f"{where}: class '{cls_name}' is in never_grant_classes — structurally ungrantable")
        if not isinstance(rows, list) or not rows:
            fails.append(f"{where}: must be a non-empty list of grant rows")
            continue
        for row in rows:
            if not isinstance(row, dict):
                fails.append(f"{where}: grant row is not a mapping")
                continue
            login = str(row.get("login") or "")
            rwhere = f"{where} login '{login or '<missing>'}'"
            for field in REQUIRED_GRANT_FIELDS:
                if not str(row.get(field) or "").strip():
                    fails.append(f"{rwhere}: missing '{field}' (a grant without it is not a durable judgment)")
            unknown = set(row) - set(REQUIRED_GRANT_FIELDS)
            if unknown:
                fails.append(f"{rwhere}: unknown key(s) {sorted(unknown)}")
            role = str(row.get("role") or "")
            if role not in GRANT_ROLE_RANK:
                fails.append(f"{rwhere}: role '{role}' not in {sorted(GRANT_ROLE_RANK)} (admin is undeclarable)")
            elif GRANT_ROLE_RANK[role] > GRANT_ROLE_RANK[ceiling]:
                fails.append(f"{rwhere}: role '{role}' exceeds the policy ceiling '{ceiling}'")
            granted = row.get("granted")
            if isinstance(granted, datetime):
                granted = granted.date()
            if not isinstance(granted, date):
                try:
                    datetime.strptime(str(granted), "%Y-%m-%d")
                except (TypeError, ValueError):
                    fails.append(f"{rwhere}: granted '{granted}' is not an ISO date (YYYY-MM-DD)")
    return fails


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
        effectors = rt.get("effector")
        fails.extend(_effector_defects(name, effectors, require_reachable=status == "active"))
        # THE WIRING-INTEGRITY LAW: an active type must be fully wired; its effector scripts must exist.
        if status == "active":
            for field in ("identity", "observe"):
                if not str(rt.get(field) or "").strip():
                    fails.append(
                        f"resource '{name}' is active but '{field}' is unwired (sensor-without-effector = defect)"
                    )
            if not effectors:
                fails.append(
                    f"resource '{name}' is active but 'effector' is unwired (sensor-without-effector = defect)"
                )

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
            for chk in checks or []:
                if chk not in job_ids:
                    fails.append(f"class '{name}': required_check '{chk}' names no .github/workflows job")
        vis = cls.get("visibility")
        if "visibility" in cls and vis not in VALID_VISIBILITY:
            fails.append(f"class '{name}': visibility '{vis}' not in {sorted(VALID_VISIBILITY)}")
        mf = cls.get("match_facts")
        if mf is not None and (
            not isinstance(mf, dict)
            or not mf
            or set(mf) - VALID_MATCH_FACT_KEYS
            or not all(isinstance(v, bool) for v in mf.values())
        ):
            fails.append(
                f"class '{name}': match_facts must be a non-empty mapping of {sorted(VALID_MATCH_FACT_KEYS)} → bool"
            )
        seo = cls.get("seo")
        if seo is not None:
            if not isinstance(seo, dict) or set(seo) - VALID_SEO_KEYS:
                fails.append(f"class '{name}': seo keys must be within {sorted(VALID_SEO_KEYS)}")
            else:
                for k in ("description", "homepage"):
                    if k in seo and seo[k] not in VALID_SEO_REQ:
                        fails.append(f"class '{name}': seo.{k} must be one of {sorted(VALID_SEO_REQ)}")
                tm = seo.get("topics_min")
                if tm is not None and (isinstance(tm, bool) or not isinstance(tm, int) or tm < 0):
                    fails.append(f"class '{name}': seo.topics_min must be a non-negative integer")
                rd = seo.get("readme")
                if rd is not None and not (isinstance(rd, str) and rd):
                    fails.append(f"class '{name}': seo.readme must be a non-empty string")
        pe = cls.get("publish_eligible")
        if pe is not None and pe not in VALID_PUBLISH_ELIGIBLE:
            fails.append(f"class '{name}': publish_eligible '{pe}' not in {sorted(VALID_PUBLISH_ELIGIBLE)}")

    # repo_overrides — the ONE sanctioned per-repo block: each row is a durable human judgment.
    # A row must name a declared class and carry a non-empty why; publish_candidate is only
    # meaningful on a private-visibility class (a public repo has nothing left to publish).
    overrides = estate.get("repo_overrides")
    if overrides is not None:
        if not isinstance(overrides, dict):
            fails.append("estate: repo_overrides must be a mapping")
        else:
            for repo, row in overrides.items():
                where = f"override '{repo}'"
                if not isinstance(row, dict):
                    fails.append(f"{where}: not a mapping")
                    continue
                unknown = set(row) - VALID_OVERRIDE_KEYS
                if unknown:
                    fails.append(f"{where}: unknown key(s) {sorted(unknown)}")
                cls_name = str(row.get("class") or "")
                target_cls = classes.get(cls_name)
                if not isinstance(target_cls, dict):
                    fails.append(f"{where}: class '{cls_name}' names no declared class")
                if not str(row.get("why") or "").strip():
                    fails.append(f"{where}: 'why' is required (a judgment without a rationale is not durable)")
                if row.get("publish_candidate") and isinstance(target_cls, dict):
                    if target_cls.get("visibility") != "private":
                        fails.append(f"{where}: publish_candidate requires a private-visibility class")
                # `audience` is declared INTENT, present only where it disagrees with the
                # derivation (public → world; private+grant → collab; else self). Parity checks the
                # value and the one combination that is structurally impossible rather than merely
                # unmet: a publish candidate is by definition on its way to `world`, so declaring
                # it `collab` asks for two contradictory futures at once. Everything softer —
                # "declared collab, nobody invited yet" — is an OWED judgment for check-audience
                # and rung Q, never a parity failure.
                aud = row.get("audience")
                if aud is not None:
                    if aud not in VALID_AUDIENCES:
                        fails.append(f"{where}: audience '{aud}' is not one of {sorted(VALID_AUDIENCES)}")
                    elif aud == "collab" and row.get("publish_candidate"):
                        fails.append(
                            f"{where}: audience 'collab' with publish_candidate — a shared operation "
                            "and a solo publication are contradictory futures; pick one"
                        )
                split = row.get("split")
                if split is not None:
                    into = split.get("into") if isinstance(split, dict) else None
                    ok = (
                        isinstance(split, dict)
                        and str(split.get("why") or "").strip()
                        and isinstance(into, list)
                        and into
                        and all(isinstance(x, str) and x for x in into)
                    )
                    if not ok:
                        fails.append(f"{where}: split must be {{into: [non-empty strings], why: non-empty}}")

    # expected_orgs — reserved namespaces are declared data; an unexpected org is drift (doctor rung).
    eo = estate.get("expected_orgs")
    if eo is not None:
        listed = eo.get("list") if isinstance(eo, dict) else None
        if not isinstance(listed, list) or not listed or not all(isinstance(o, str) and o for o in listed):
            fails.append("estate: expected_orgs.list must be a non-empty list of owner names")
        else:
            for field in ("owner", "note"):
                if field not in eo:
                    fails.append(f"expected_orgs: missing '{field}'")

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
                effectors = ig.get("effector")
                fails.extend(
                    _effector_defects(
                        f"integration/{iname}",
                        effectors,
                        require_reachable=st == "active",
                    )
                )
                if st == "active" and not effectors:
                    fails.append(f"integration '{iname}' is active but 'effector' is unwired")

    # owner/note discipline on budgets (parity with the gates.yaml/parameters.yaml rule).
    for bname, budget in (estate.get("budgets") or {}).items():
        if isinstance(budget, dict):
            for field in ("owner", "note"):
                if field not in budget:
                    fails.append(f"budget '{bname}': missing '{field}'")

    # `orgs:` (the ACCOUNT layer) — the same field discipline; plan_ok must be a non-empty string list.
    for oname, org_row in (estate.get("orgs") or {}).items():
        if not isinstance(org_row, dict):
            fails.append(f"org-class '{oname}': not a mapping")
            continue
        for field in ("match", "plan_ok", "repos", "owner", "note"):
            if field not in org_row:
                fails.append(f"org-class '{oname}': missing '{field}'")
        pok = org_row.get("plan_ok")
        if pok is not None and (not isinstance(pok, list) or not pok or not all(isinstance(p, str) and p for p in pok)):
            fails.append(f"org-class '{oname}': plan_ok must be a non-empty string list")

    # ACCESS (the partner-partition registry) — validated in the same offline rung so a malformed
    # grant, a ceiling breach, or a grant on an ungrantable repo/class reddens the PR gate.
    fails.extend(_access_parity(estate))
    return fails


def _facts_rows() -> list[dict] | None:
    """The per-repo census facts (written by observe()); None when no census has run."""
    try:
        return json.loads(FACTS.read_text(encoding="utf-8"))["repos"]
    except Exception:
        return None


def _audience_lens():
    """check-audience.py's (derive, assess) pair, or None when it cannot be loaded.

    Same fail-open contract as the sweep lens below, and the same reason for IMPORTING rather than
    re-deriving: the audience law (public → world; private+grant → collab; else self) already lives
    in one place, and a second copy inside the doctor is precisely the drift every registry in this
    estate exists to prevent. If the module is missing, rung Q skips — it never guesses.
    """
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("check_audience", str(SCRIPT_DIR / "check-audience.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["check_audience"] = mod
        spec.loader.exec_module(mod)
        return mod.derive, mod.assess
    except Exception:
        return None


def _sweep_receipt_lens():
    """publish-sweep.py's ``receipt_fresh_green``, or None when it cannot be loaded.

    Fail-open by construction: class G is a REPORTING rung, so a missing/broken sweep script must
    degrade it to the pure read (cite every public candidate) rather than break the whole doctor.
    Returning None — not a stub that answers True — keeps the failure legible: the un-lensed path
    over-cites, and over-citing is the safe direction for a posture rung."""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("publish_sweep", str(SCRIPT_DIR / "publish-sweep.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["publish_sweep"] = mod
        spec.loader.exec_module(mod)
        return mod.receipt_fresh_green
    except Exception:
        return None


def visibility_drift(rows: list[dict], estate: dict, receipt_ok=None) -> tuple[list[str], list[str]]:
    """Class G, pure: desired visibility − observed. ``publish_candidate`` is desired-public,
    matching apply-visibility.py: its nominal operation-private class preserves the pre-publication
    posture while a green history sweep gates the actual flip. A candidate still private is CITED
    (homed with the publish-wave owner). ``any`` is exempt. Every other mismatch, including
    desired-private observed-public, is drift.

    ``receipt_ok(repo) -> (bool, why)`` is the optional live sweep-receipt lens. Omitted (the pure
    fixture path) every already-public candidate is cited, because purity cannot tell an adjudicated
    public from an un-adjudicated one. Supplied (the live doctor), a green+fresh receipt legitimately
    OWNS the public posture and the repo is genuinely converged — so it is not cited at all. Without
    that distinction the rung cites all 32 swept-clean publics forever, and a rung that always cites
    is a rung nobody reads."""
    fails: list[str] = []
    cites: list[str] = []
    classes = estate.get("classes") or {}
    overrides = estate.get("repo_overrides") or {}
    for row in rows:
        full = str(row.get("full_name") or "")
        cls_name = classify_repo(full, estate, facts=row)
        desired = (classes.get(cls_name) or {}).get("visibility") if cls_name else None
        publish_candidate = bool((overrides.get(full) or {}).get("publish_candidate"))
        if publish_candidate:
            desired = "public"
        if desired not in ("public", "private"):
            continue  # 'any' is exempt; unclassed is rung J's finding
        observed = "private" if row.get("private") else "public"
        if desired == observed:
            if publish_candidate and observed == "public":
                # The old silent "converged" read let an un-gated public ride (micro-tato /
                # mirror-mirror, 2026-07-30): candidacy is a GATED desire — public without a
                # released wave receipt is a posture question, not a convergence.
                ok, why = receipt_ok(full) if receipt_ok else (False, "no receipt lens")
                if ok:
                    continue  # the receipt owns the flip — genuinely converged
                cites.append(
                    f"[G visibility-drift] {full}: publish candidate observed public with no receipt "
                    f"owning the flip ({why}) — publish-sweep.py adjudicates; RED demotes it"
                )
            continue
        if desired == "public" and publish_candidate:
            cites.append(
                f"[G visibility-drift] {full}: desired public, observed private — publish-wave pending (lever-gated)"
            )
        else:
            fails.append(f"[G visibility-drift] {full}: class '{cls_name}' demands {desired}, observed {observed}")
    return fails, cites


def seo_floor_gaps(rows: list[dict], estate: dict) -> list[str]:
    """Class K, pure: public repos below their class's declared SEO floor — metadata only
    (description/topics/homepage from the census facts; the README standard is the seo-audit
    organ's deeper rung). Forks/archived are exempt by their fact classes carrying no seo block."""
    classes = estate.get("classes") or {}
    gaps: list[str] = []
    for row in rows:
        if row.get("private"):
            continue
        full = str(row.get("full_name") or "")
        cls = classes.get(classify_repo(full, estate, facts=row) or "") or {}
        seo = cls.get("seo")
        if not isinstance(seo, dict):
            continue
        missing: list[str] = []
        if seo.get("description") == "required" and not str(row.get("description") or "").strip():
            missing.append("description")
        floor = int(seo.get("topics_min") or 0)
        if (row.get("topics_count") or 0) < floor:
            missing.append(f"topics<{floor}")
        if seo.get("homepage") == "required" and not str(row.get("homepage") or "").strip():
            missing.append("homepage")
        if missing:
            gaps.append(f"{full}: {','.join(missing)}")
    return gaps


def _lever_is_open(lever: dict) -> bool:
    """Return whether a human lever may still own current work."""
    if str(lever.get("discharged") or "").strip():
        return False
    status = str(lever.get("status") or "").strip().lower()
    return status not in TERMINAL_LEVER_STATUSES


def _homed_levers() -> set[str]:
    """Lever ids present (and open) in his-hand-levers.json — so the doctor can CITE a homed atom
    (App un-installed → L-LIMENBOT-INSTALL) instead of counting it as a failure. Absent file → empty."""
    try:
        data = json.loads((ROOT / "his-hand-levers.json").read_text(encoding="utf-8"))
    except Exception:
        return set()
    levers = data.get("levers", data) if isinstance(data, dict) else data
    out: set[str] = set()
    for lv in levers if isinstance(levers, list) else []:
        if isinstance(lv, dict) and lv.get("id") and _lever_is_open(lv):
            out.add(str(lv["id"]))
    return out


def custody_drift(ledger: list, grants: dict, by_repo: dict, org_set: set) -> list[str]:
    """The dual-estate custody rung's pure join (class O). A register-marked product
    (ASSET LEDGER `product_ledger`, owner-independent names) that still lives in an ORG
    while a DECLARED partner grant is LIVE on it has the wrong custody home — partnered
    products belong to the personal estate (seats free forever, moat insulated; see the
    repo_custody resource type). Staged-never-sent grants and undeclared collaborators
    are class N's jurisdiction, not custody evidence. Deterministic (sorted)."""
    ledger_set = {str(n) for n in ledger}
    out: list[str] = []
    for repo, obs in sorted((by_repo or {}).items()):
        owner, _, name = str(repo).partition("/")
        if name not in ledger_set or owner not in org_set:
            continue
        outside = (obs or {}).get("outside")
        if outside is None:
            continue  # unreadable roll → class N already SKIPs it; custody never guesses
        declared = {str(g.get("login", "")).lower() for g in (grants.get(repo) or []) if isinstance(g, dict)}
        live = sorted({str(c.get("login") or "") for c in outside if str(c.get("login") or "").lower() in declared})
        if live:
            out.append(f"{repo}: register-marked product with LIVE partner lane ({', '.join(live)}) still org-side")
    return out


def shelf_drift(shelves: dict, rows: list) -> list[str]:
    """Class P's pure join (shelf parity, custody v4.0.0 Phase 2): declared shelf membership
    (estate shelf_assignments, bare names) vs census owner, BOTH directions — a declared repo
    living elsewhere is drift, and an undeclared repo squatting in a shelf org is drift.
    Deterministic (sorted); reports remediation, never fires a transfer."""
    declared: dict[str, set[str]] = {str(o): {str(n) for n in (ns or [])} for o, ns in (shelves or {}).items()}
    owners_by_name: dict[str, set[str]] = {}
    for r in rows or []:
        full = str((r or {}).get("full_name") or "")
        o, _, n = full.partition("/")
        if o and n:
            owners_by_name.setdefault(n, set()).add(o)
    out: list[str] = []
    for org, names in sorted(declared.items()):
        for n in sorted(names):
            owners_ = owners_by_name.get(n) or set()
            if not owners_:
                out.append(f"{org}/{n}: declared on the shelf but absent from the census")
            elif org not in owners_:
                out.append(f"{n}: declared shelf {org}, census owner {'/'.join(sorted(owners_))} — transfer owed")
    for n, owners_ in sorted(owners_by_name.items()):
        for o in sorted(owners_):
            if o in declared and n not in declared[o]:
                out.append(f"{o}/{n}: undeclared repo in a shelf org — declare the row or move it out")
    return out


def permission_over_grant(personal_full: dict, grants: dict, probed: set[str]) -> list[str]:
    """Class D, pure: the personal estate's FULL collaborator roll vs the ACCESS registry — the
    lens beyond class N's bounded probe set (granted ∪ never-grant). A collaborator on an
    UNLISTED personal repo, or any live role above the declared grant, is drift. Probed repos
    are class N's finding, never double-reported here; unreadable rolls (None) are the caller's
    SKIP. The rung only ever reports — permission changes stay with collab-sync / his hand."""
    drifts: list[str] = []
    for repo, outside in sorted((personal_full or {}).items()):
        if repo in probed or outside is None:
            continue
        declared = {str(g.get("login", "")).lower(): g for g in (grants.get(repo) or []) if isinstance(g, dict)}
        for c in outside:
            if not isinstance(c, dict):
                continue
            login = str(c.get("login") or "")
            role = ROLE_NAME_TO_GRANT.get(str(c.get("role")), str(c.get("role")))
            g = declared.get(login.lower())
            if g is None:
                drifts.append(f"{repo}: {login} ({role}) has live access with NO grant row (repo unlisted in ACCESS)")
            elif GRANT_ROLE_RANK.get(role, 99) > GRANT_ROLE_RANK.get(str(g.get("role")), -1):
                drifts.append(f"{repo}: {login} live role {role} exceeds declared {g.get('role')}")
    return drifts


def posture_window(eligible: list[str], size: int, ordinal: int) -> list[str]:
    """Class A's bounded rotating window, pure and stateless: a deterministic size-`size` slice of
    the sorted eligible set, rotated by day ordinal — full coverage every ceil(n/size) days with
    zero persisted cursor. Same ordinal ⇒ same slice (a doctor re-run probes identical repos)."""
    if not eligible or size <= 0:
        return []
    ordered = sorted(eligible)
    if size >= len(ordered):
        return ordered
    start = (ordinal * size) % len(ordered)
    return (ordered + ordered)[start : start + size]


def _protection_probe(
    repos: list[str],
    estate: dict,
    token: str | None,  # allow-secret (type annotation, no value)
) -> dict[str, str]:
    """Class A's Lens: live branch-protection state per repo → 'protected' | 'missing' |
    'plan-gated' | 'unreadable'. Canonical-org repos ride the App token; personal/shelf owners
    sit outside the installation and read user-scoped. plan-gated = GitHub refuses protection on
    a free-plan private repo (the billing levers own the fix, not the rung)."""
    out: dict[str, str] = {}
    for repo in repos:
        canonical = _org_class(repo.split("/", 1)[0], estate)[0] == "canonical"
        args = ["api", f"/repos/{repo}", "--jq", ".default_branch"]
        r = _gh(args, token, timeout=30) if canonical else _gh_user(args, timeout=30)
        if r.returncode != 0 or not (r.stdout or "").strip():
            out[repo] = "unreadable"
            continue
        branch = r.stdout.strip().splitlines()[0]
        args = ["api", f"/repos/{repo}/branches/{branch}/protection", "--jq", ".url"]
        r = _gh(args, token, timeout=30) if canonical else _gh_user(args, timeout=30)
        if r.returncode == 0:
            out[repo] = "protected"
            continue
        blob = f"{r.stdout or ''}\n{r.stderr or ''}"
        if "Upgrade to GitHub" in blob:
            out[repo] = "plan-gated"
        elif "Branch not protected" in blob or "Not Found" in blob or "HTTP 404" in blob:
            out[repo] = "missing"
        else:
            out[repo] = "unreadable"
    return out


def doctor(estate: dict, *, parity_only: bool, offline: bool, strict: bool = False) -> int:
    """The Diff operator. Exit 0 ⟺ drift == ∅ (over the rungs that could run). SKIP is never a faked PASS."""
    fails: list[str] = []
    cites: list[str] = []
    skips: list[str] = []

    # ── Class H — parity / wiring-integrity (deterministic, always runs). The PR gate. ──
    h = parity(estate)
    fails += [f"[H parity] {m}" for m in h]

    if parity_only:
        return _verdict(fails, cites, skips, "parity-only", strict=strict)

    # SPLIT — owed form-twin/eviction work: every override row carrying split: is CITED until the
    # hygiene predicate (scripts/check-split-hygiene.py) retires the row — owned, never a memory chore.
    owed_splits = sorted(
        f"{repo} → {', '.join((row.get('split') or {}).get('into') or [])}"
        for repo, row in (estate.get("repo_overrides") or {}).items()
        if isinstance(row, dict) and row.get("split")
    )
    if owed_splits:
        cites.append(f"[SPLIT owed] {len(owed_splits)} registered: " + "; ".join(owed_splits))

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

    # Q — audience intent (2026-07-30, decision 4): who each repo actually faces vs who it was
    # meant to. The audience is DERIVED, never stored (public → world; private+grant → collab;
    # else self) — and the derivation alone has a blind spot big enough to hide the defect: a
    # partner lane with nobody invited derives `self`, `self` is self-consistent, and a repo the
    # partner CANNOT SEE certifies green. So intent comes from the estate's declared `audience:`
    # rows and, as a hint only, the constellation register.
    #
    # CITES ONLY, and never a flip demand. Two hard constraints the first draft of this rung got
    # wrong and would have made permanent:
    #   · `world` is defined as "public, SOLO", so a public repo carrying a live grant is a FOURTH
    #     state the enum cannot express — not drift. Reading it as drift would demand a
    #     public→private flip of a traction repo and put Q permanently at war with class G.
    #   · the register may SUGGEST a lane and never decide one. Its rows are people-data; if an
    #     editorial removal could flip a repo to `self`, a live human-decided grant would read as
    #     "undeclared exposure" whose machine-runnable direction (L-PARTNER-GRANTS) is REMOVAL.
    # Behind ratchets.audience_parity_armed, per the house observable-before-autonomous pattern.
    q_atom = "L-PARTNER-GRANTS"
    q_armed = bool(((estate.get("ratchets") or {}).get("audience_parity_armed")))
    q_lens = _audience_lens()
    # Loaded here rather than reused from the live section below: Q runs BEFORE the offline
    # early-return (it is a pure registry join — estate + access + register, zero gh calls), so it
    # must not depend on a binding that only exists on the online path.
    q_access = load_access()
    if not q_armed:
        skips.append("[Q audience-intent] ratchets.audience_parity_armed is false (observable-before-autonomous)")
    elif q_lens is None:
        skips.append("[Q audience-intent] scripts/check-audience.py unavailable — the rung never re-derives the law")
    elif not q_access:
        skips.append("[Q audience-intent] no ACCESS registry")
    else:
        q_derive, q_assess = q_lens
        try:
            q_reg_path = SCRIPT_DIR.parent / "organs" / "consulting" / "constellation" / "registry.yaml"
            q_reg = yaml.safe_load(q_reg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            q_reg = {}  # no register ⇒ no lane HINTS; declared `audience:` rows still evaluate
        q_breaks, q_owed = q_assess(q_derive(estate, q_access, q_reg))
        for b in q_breaks:
            fails.append(f"[Q audience-intent] {b} — the estate contradicts itself; check-audience.py --check")
        for o in q_owed:
            (cites if q_atom in homed else fails).append(
                f"[Q audience-intent] {o} → "
                + (f"{q_atom} (owned, open)" if q_atom in homed else f"{q_atom} (UNHOMED)")
            )

    # ── Live classes (A/D/E/F/G/J/K/M) — need gh; SKIP offline, cite a homed atom instead of failing. ──
    if offline:
        for tag in (
            "A protection",
            "D permission-over-grant",
            "E rate-limit",
            "F app-installed",
            "G visibility",
            "J unclassified",
            "K seo-floor",
            "L org-posture",
            "M org-namespace",
            "N collaborator-drift",
        ):
            skips.append(f"[{tag}] live rung — offline")
        return _verdict(fails, cites, skips, "offline", strict=strict)

    led = observe(estate)

    # F — App installed where a class requires it (homed → cite L-LIMENBOT-INSTALL, don't fail).
    installed = led["app"].get("installed")
    if installed is None:
        skips.append("[F app-installed] could not read /app/installations")
    elif not installed:
        atom = (estate.get("human_atoms") or {}).get("app_creation", {}).get("lever", "L-LIMENBOT-INSTALL")
        (cites if atom in homed else fails).append(
            f"[F app-installed] limen[bot] not installed → {atom}"
            + (" (owned, open)" if atom in homed else " (UNHOMED)")
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
            1 for n, ig in (estate.get("integrations") or {}).items() if ig.get("app_slug") in slugs or cfg.get(n)
        )
        owed = integ["declared"] - satisfied
        if owed:
            cites.append(
                f"[I integration-gap] {satisfied}/{integ['declared']} ecosystem integrations present; "
                f"{owed} owed (envisioned — detail in the census ledger; $0-labor harness pending §3 D2)"
            )

    # ── The publication rungs (G/J/K) — per-repo, over the census facts the Lens just wrote. ──
    ratchets = estate.get("ratchets") or {}
    rows = _facts_rows()

    # G — visibility drift (armed by the visibility_gate_armed ratchet; the taxonomy defused the
    # latent glob flip, so desired-state is finally truthful enough to assert).
    if not ratchets.get("visibility_gate_armed"):
        skips.append("[G visibility-drift] ratchet visibility_gate_armed=false — arms with the decision registry")
    elif rows is None:
        skips.append("[G visibility-drift] no census facts (run census online first)")
    else:
        g_fails, g_cites = visibility_drift(rows, estate, receipt_ok=_sweep_receipt_lens())
        fails += g_fails
        cites += g_cites

    # J — unclassified: the decision registry is TOTAL; a repo in no class is a missing judgment.
    if rows is None:
        skips.append("[J unclassified] no census facts")
    else:
        unclassed = [
            str(r.get("full_name")) for r in rows if (classify_repo(str(r.get("full_name")), estate, facts=r)) is None
        ]
        if unclassed:
            head = ", ".join(unclassed[:5]) + ("…" if len(unclassed) > 5 else "")
            fails.append(f"[J unclassified] {len(unclassed)} repo(s) in no class — judge them: {head}")

    # K — SEO floor (metadata half): cited-owed until the seo_drift_gates ratchet arms post-backfill.
    if rows is None:
        skips.append("[K seo-floor] no census facts")
    else:
        gaps = seo_floor_gaps(rows, estate)
        if gaps:
            msg = f"[K seo-floor] {len(gaps)} public repo(s) below their class SEO floor (description/topics/homepage)"
            if ratchets.get("seo_drift_gates"):
                fails.append(msg)
            else:
                cites.append(msg + " — owed; the repo-metadata effector converges it, ratchet arms post-backfill")

    # M — org namespaces: reserved orgs are declared; an unexpected org is a judgment owed.
    expected = ((estate.get("expected_orgs") or {}).get("list")) or []
    observed_orgs = sorted((led.get("app_estate") or {}).get("by_org") or {})
    if expected and observed_orgs:
        unexpected = sorted(set(observed_orgs) - set(expected))
        if unexpected:
            cites.append(
                f"[M org-namespace] unexpected org(s): {', '.join(unexpected)} — add to expected_orgs or lever a deletion"
            )

    # L — org posture (the ACCOUNT layer): every org's live plan + repo custody vs the `orgs:`
    # registry. An empty org riding a paid plan, or repos held outside the canonical org,
    # is drift → cite the account-purchase atom when homed (account billing is never machine-run).
    orgs_reg = estate.get("orgs") or {}
    orgs_led = (led.get("orgs") or {}).get("by_org")
    if orgs_reg:
        if orgs_led is None:
            skips.append("[L org-posture] could not read /user/orgs (user-scoped)")
        else:
            drifts: list[str] = []
            for org, ob in sorted(orgs_led.items()):
                _, row = _org_class(org, estate)
                if not row:
                    drifts.append(f"{org}: unclassed (no `orgs:` row)")
                    continue
                plan_ok = [str(p) for p in (row.get("plan_ok") or [])]
                if plan_ok and str(ob.get("plan")) not in plan_ok:
                    drifts.append(f"{org}: plan '{ob.get('plan')}' not in {plan_ok}")
                ceiling = row.get("repos")
                if isinstance(ceiling, int) and (ob.get("repos") or 0) > ceiling:
                    drifts.append(f"{org}: holds {ob.get('repos')} repo(s), declared {ceiling}")
            if drifts:
                atom = (estate.get("human_atoms") or {}).get("enterprise_cancel", {}).get("lever", "L-ORG-TEAM-UPGRADE")
                more = f"; +{len(drifts) - 4} more" if len(drifts) > 4 else ""
                line = (
                    f"[L org-posture] {len(drifts)} org(s) off account policy ({'; '.join(drifts[:4])}{more}) → {atom}"
                )
                (cites if atom in homed else fails).append(line + (" (owned, open)" if atom in homed else " (UNHOMED)"))

    # N — collaborator drift (the partner-partition rung): live outside collaborators vs the
    # ACCESS registry. Undeclared access or an over-ceiling role is RED (removal is the machine-
    # runnable direction, via collab-sync --apply); a declared-but-absent grant is a STAGED INVITE —
    # outbound is his hand, so it is cited on the lever, never auto-sent.
    access = load_access()
    coll = led.get("collaborators") or {}
    n_atom = "L-PARTNER-GRANTS"
    if access is None:
        skips.append("[N collaborator-drift] no ACCESS registry (institutio/github/access.yaml absent)")
    elif not access:
        pass  # unparseable registry is already a class-H parity defect this run
    elif not coll.get("complete"):
        skips.append("[N collaborator-drift] census incomplete (gh errors)")
    else:
        grants = access.get("grants") or {}
        declared_logins = {
            str(g.get("login", "")).lower()
            for rows_ in grants.values()
            if isinstance(rows_, list)
            for g in rows_
            if isinstance(g, dict)
        }
        for org, roll in sorted((coll.get("org_outside") or {}).items()):
            if roll is None:
                skips.append(f"[N collaborator-drift] {org}: outside-collaborator roll unreadable")
                continue
            undeclared = sorted(login for login in roll if str(login).lower() not in declared_logins)
            if undeclared:
                fails.append(
                    f"[N collaborator-drift] {org}: undeclared outside collaborator(s): {', '.join(undeclared)}"
                )
        for repo, obs in sorted((coll.get("by_repo") or {}).items()):
            declared = {str(g.get("login", "")).lower(): g for g in (grants.get(repo) or []) if isinstance(g, dict)}
            outside = obs.get("outside")
            if outside is None:
                skips.append(f"[N collaborator-drift] {repo}: collaborator list unreadable")
                continue
            for c in outside:
                login = str(c.get("login") or "")
                role = ROLE_NAME_TO_GRANT.get(str(c.get("role")), str(c.get("role")))
                g = declared.get(login.lower())
                if g is None:
                    fails.append(f"[N collaborator-drift] {repo}: {login} ({role}) has no grant row")
                elif GRANT_ROLE_RANK.get(role, 99) > GRANT_ROLE_RANK.get(str(g.get("role")), -1):
                    fails.append(
                        f"[N collaborator-drift] {repo}: {login} live role {role} exceeds declared {g.get('role')}"
                    )
            live = {str(c.get("login") or "").lower() for c in outside}
            pending = {str(i.get("login") or "").lower() for i in (obs.get("invitations") or [])}
            for login_l, g in sorted(declared.items()):
                if login_l in live:
                    continue
                if login_l in pending:
                    cites.append(f"[N collaborator-drift] {repo}: invite pending for {g.get('login')} → {n_atom}")
                else:
                    (cites if n_atom in homed else fails).append(
                        f"[N collaborator-drift] {repo}: {g.get('login')} declared but absent — staged invite → "
                        + (f"{n_atom} (owned, open)" if n_atom in homed else f"{n_atom} (UNHOMED)")
                    )

    # O — custody drift (the dual-estate rung, v4.0.0): ASSET LEDGER ∧ live declared grant ∧
    # org owner. A partnered product's custody home is the personal estate; the transfer
    # effector is outward-facing multi-repo custody movement — his hand — so drift CITES
    # L-CONST-CUSTODY-MIGRATION while homed and reds only if the atom loses its owner.
    ledger_rows = ((estate.get("product_ledger") or {}).get("repos")) or []
    o_atom = "L-CONST-CUSTODY-MIGRATION"
    org_set = set(((led.get("orgs") or {}).get("by_org")) or {})
    if not ledger_rows:
        skips.append("[O custody-drift] no product_ledger in ESTATE")
    elif access is None or not access:
        skips.append("[O custody-drift] no ACCESS registry")
    elif not coll.get("complete"):
        skips.append("[O custody-drift] census incomplete (gh errors)")
    elif not org_set:
        skips.append("[O custody-drift] org roll unavailable (user-scoped read failed)")
    else:
        for d in custody_drift(ledger_rows, access.get("grants") or {}, coll.get("by_repo") or {}, org_set):
            (cites if o_atom in homed else fails).append(
                f"[O custody-drift] {d} → " + (f"{o_atom} (owned, open)" if o_atom in homed else f"{o_atom} (UNHOMED)")
            )

    # P — shelf parity (custody v4.0.0 Phase 2): declared shelf membership vs census owner,
    # both directions. Real drift is RED with the exact remediation named; the rung never
    # fires a transfer itself.
    shelves_reg = ((estate.get("shelf_assignments") or {}).get("shelves")) or {}
    if shelves_reg:
        if not rows:
            skips.append("[P shelf-parity] no census facts (run census online first)")
        else:
            for d in shelf_drift(shelves_reg, rows):
                fails.append(f"[P shelf-parity] {d}")

    # D — permission-over-grant (PR B, armed): the personal estate's FULL roll vs ACCESS — the
    # lens beyond N's bounded probe set. A collaborator on an unlisted personal repo was
    # structurally invisible before this rung. Report-only; remediation is named, never fired.
    personal_full = coll.get("personal_full")
    if access is None or not access:
        skips.append("[D permission-over-grant] no ACCESS registry")
    elif personal_full is None:
        skips.append("[D permission-over-grant] personal full-roll unavailable (user-scoped read failed)")
    else:
        for repo_ in sorted(r_ for r_, v_ in personal_full.items() if v_ is None):
            skips.append(f"[D permission-over-grant] {repo_}: collaborator roll unreadable")
        for d in permission_over_grant(personal_full, access.get("grants") or {}, set(coll.get("by_repo") or {})):
            fails.append(
                f"[D permission-over-grant] {d} — remediation: declare the grant row in ACCESS "
                f"(or remove the access via collab-sync); the rung never edits"
            )

    # A — protection-missing (PR B, armed): declared class posture (branch_protection: required)
    # vs live branch protection, over a bounded stateless rotating window (full coverage cycles
    # by day ordinal). plan-gated repos cite their billing lever (Pro/Team); missing protection
    # cites L-BRANCH-PROTECTION while homed — posture writes stay with the levers, never the rung.
    a_atom = "L-BRANCH-PROTECTION"
    if not rows:
        skips.append("[A protection-missing] no census facts (run census online first)")
    else:
        classes_ = estate.get("classes") or {}
        eligible = [
            str(row.get("full_name"))
            for row in rows
            if (classes_.get(classify_repo(str(row.get("full_name")), estate, facts=row) or "") or {}).get(
                "branch_protection"
            )
            == "required"
        ]
        try:
            win_size = int(os.environ.get("LIMEN_GITVS_POSTURE_WINDOW", "15"))
        except ValueError:
            win_size = 15
        window = posture_window(eligible, win_size, datetime.now(timezone.utc).toordinal())
        if len(window) < len(eligible):
            skips.append(
                f"[A protection-missing] rotating window: {len(window)}/{len(eligible)} eligible probed this run"
            )
        probe = _protection_probe(window, estate, _token())
        by_owner_private = {str(r_.get("full_name")): bool(r_.get("private")) for r_ in rows}
        for repo_, state in sorted(probe.items()):
            if state == "protected":
                continue
            if state == "unreadable":
                skips.append(f"[A protection-missing] {repo_}: protection state unreadable")
                continue
            if state == "plan-gated":
                owner_ = repo_.split("/", 1)[0]
                lever = "L-PERSONAL-PRO" if _org_class(owner_, estate)[0] is None else "L-ORG-TEAM-UPGRADE"
                (cites if lever in homed else fails).append(
                    f"[A protection-missing] {repo_}: private repo protection is plan-gated → "
                    + (f"{lever} (owned, open)" if lever in homed else f"{lever} (UNHOMED)")
                )
                continue
            suffix = (
                " (private repo — free-plan personal protection may also need L-PERSONAL-PRO)"
                if by_owner_private.get(repo_)
                else ""
            )
            (cites if a_atom in homed else fails).append(
                f"[A protection-missing] {repo_}: class demands branch_protection, none live{suffix} → "
                + (f"{a_atom} (owned, open)" if a_atom in homed else f"{a_atom} (UNHOMED)")
            )

    return _verdict(fails, cites, skips, "live", strict=strict)


def _verdict(
    fails: list[str],
    cites: list[str],
    skips: list[str],
    mode: str,
    *,
    strict: bool = False,
) -> int:
    for c in cites:
        print(f"  · cited (homed) {c}")
    for s in skips:
        print(f"  ~ SKIP {s}")
    if fails:
        print(f"\n✗ gitvs doctor ({mode}): {len(fails)} drift(s) — the estate does not match policy:")
        for f in fails:
            print(f"   {f}")
        return 1
    if strict and skips:
        print(f"\n~ gitvs doctor ({mode}): {len(skips)} rung(s) unavailable under --strict")
        return 77
    print(
        f"✓ gitvs doctor ({mode}): drift == ∅ over {len(skips)} skipped + all run rungs; "
        f"{len(cites)} homed atom(s) cited."
    )
    return 0


# ── the Effector: reconcile() — the third projection of the loop ────────────────────────────────


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
        if isinstance(lv, dict) and lv.get("id") and _lever_is_open(lv)
    }


def _cite(target: str, levers: dict[str, dict]) -> str:
    """Render a file-atom citation (lever id + issue if homed) — resolves id → object, never a value."""
    lv = levers.get(target)
    issue = lv.get("issue") if lv else None
    if issue:
        return f"{target} (#{issue}, owned)"
    return f"{target} (owned)" if lv else f"{target} (cited)"


def _effector_label(effector: dict) -> str:
    kind = str(effector.get("kind") or "unknown")
    if kind == "file-atom":
        return f"file-atom:{effector.get('target', '')}"
    argv = effector.get("argv") or []
    return f"{kind}:{shlex.join(argv)}" if isinstance(argv, list) else kind


def _run_effector(effector: dict) -> str:
    """Invoke the exact adapter command declared by the registry, if its executable is reachable."""
    argv = effector.get("argv") or []
    if not isinstance(argv, list) or not argv:
        return "BLOCKED invalid argv"
    executable = argv[0]
    if os.path.sep in executable:
        executable_path = Path(executable)
        if not executable_path.is_absolute():
            executable_path = ROOT / executable_path
        available = executable_path.exists()
    else:
        available = shutil.which(executable) is not None
    if not available:
        return f"BLOCKED missing executable {executable}"
    try:
        r = subprocess.run(
            argv,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("LIMEN_GITVS_TIMEOUT", "120")),
        )
        tail = (r.stdout or r.stderr or "").strip().splitlines()
        return (tail[-1] if tail else f"exit={r.returncode}")[:200]
    except Exception as e:  # fail open — a delegate must never break the reconcile loop
        return f"skipped ({str(e)[:80]})"


def reconcile(estate: dict, *, apply: bool) -> int:
    """The Effector — a GENERIC dispatcher (the mapping is DATA in estate.yaml, never a table here).
    Walk every active registry owner (resource type or ecosystem integration) and route its structured
    effectors. Executable adapter, argv, and any human approval lever live in estate.yaml, so a new tool
    or policy is a data change, never a target-name exception in this engine. DRY by default (report the
    plan, mutate nothing). Always exit 0: reconcile is advisory and must be fail-open in the beat."""
    registries = (
        ("resource", estate.get("resource_types") or {}),
        ("integration", estate.get("integrations") or {}),
    )
    levers = _lever_index()
    acted: list[str] = []  # ran (apply) or planned (dry)
    cited: list[str] = []
    skipped: list[str] = []
    declared = 0
    for registry_name, entries in registries:
        declared += len(entries) if isinstance(entries, dict) else 0
        for name, spec in entries.items() if isinstance(entries, dict) else ():
            owner = f"{registry_name}/{name}"
            if not isinstance(spec, dict) or spec.get("status") != "active":
                continue
            effectors = spec.get("effector") or []
            if not isinstance(effectors, list):
                skipped.append(f"{owner}: malformed effector registry")
                continue
            for effector in effectors:
                if not isinstance(effector, dict):
                    skipped.append(f"{owner}: malformed effector entry")
                    continue
                kind = str(effector.get("kind") or "").strip()
                if kind == "manual":
                    skipped.append(f"{owner}: manual (human-obvious act)")
                    continue
                if kind == "file-atom":
                    target = str(effector.get("target") or "").strip()
                    cited.append(f"{owner} → {_cite(target, levers)}")
                elif kind in EFFECTOR_KINDS_WITH_COMMAND:
                    label = _effector_label(effector)
                    approval = effector.get("approval")
                    if isinstance(approval, dict):
                        lever = str(approval.get("lever") or "").strip()
                        skipped.append(f"{owner}: {label} gated by {_cite(lever, levers)}")
                        continue
                    if apply:
                        acted.append(f"{owner} {label} → {_run_effector(effector)}")
                    else:
                        note = "  (reap: still needs its own dark-arming to delete)" if kind == "reap" else ""
                        acted.append(f"WOULD {owner} {label}{note}")
                else:
                    skipped.append(f"{owner}: unknown sink '{kind}'")

    mode = "APPLY" if apply else "report (dry)"
    print(
        f"[gitvs] reconcile ({mode}): {declared} registry owners → "
        f"{len(acted)} effector(s) {'ran' if apply else 'planned'}, "
        f"{len(cited)} file-atom(s) cited, {len(skipped)} skipped."
    )
    for line in acted:
        print(f"   {'✓' if apply else '·'} {line}")
    for c in cited:
        print(f"   ⚑ owed  {c}")
    for s in skipped:
        print(f"   ~ skip  {s}")
    return 0


# ── the Classifier: propose per-repo publication decisions (rules R1–R9) ─────────────────────────
def _pubpolicy():
    """Import publication-policy.py's pure classify() (the reap-branches importlib pattern).
    None on failure — the caller degrades to registry-only rules, never raises."""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("publication_policy", str(SCRIPT_DIR / "publication-policy.py"))
        pp = importlib.util.module_from_spec(spec)
        sys.modules["publication_policy"] = pp
        spec.loader.exec_module(pp)
        return pp
    except Exception:
        return None


def _tree_paths(repo: str, token: str | None, cap: int) -> list[str] | None:
    """HEAD tree paths (no clone, no content — path shapes are publication-policy's cheap decisive
    signal). Truncation by `cap` or GitHub's own trees cap is fine: this is sampling, not audit."""
    r = _gh(
        ["api", f"/repos/{repo}/git/trees/HEAD?recursive=1", "--jq", ".tree[].path"],
        token,
        timeout=60,
    )
    if r.returncode != 0:
        return None
    paths = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    return paths[:cap]


def _path_histogram(repo: str, token: str | None, pp, cap: int) -> tuple[dict[str, int], int]:
    """Content-class histogram over sampled tree paths (publication-policy taxonomy, path-only)."""
    paths = _tree_paths(repo, token, cap)
    if paths is None or pp is None:
        return {}, 0
    hist: dict[str, int] = {}
    for p in paths:
        c, _ = pp.classify(p)
        hist[c] = hist.get(c, 0) + 1
    return dict(sorted(hist.items())), len(paths)


def _registry_repo_set(path: Path, key: str = "repos") -> set[str]:
    """owner/repo membership from a JSON registry (value-repos.json list / positioning-seeds map)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        block = data.get(key) or []
        if isinstance(block, dict):
            return {str(k) for k in block}
        return {str(r) for r in block if isinstance(r, str)}
    except Exception:
        return set()


def classify_estate(estate: dict, *, fresh: bool, sample_max: int, emit: bool, only: str | None) -> int:
    """Propose a publication class per repo (R1–R9 over census facts + path sampling). Writes the
    gitignored receipt (DECISIONS); --emit-overrides prints ready-to-paste registry rows. The
    PROPOSAL engine — the durable decision is the estate.yaml row a human-reviewed PR lands."""
    if fresh or not FACTS.exists():
        print("[gitvs] classify: refreshing census facts …")
        observe(estate)
    try:
        rows = json.loads(FACTS.read_text(encoding="utf-8"))["repos"]
    except Exception:
        print("[gitvs] classify: no census facts (run `gitvs.py census` online first)")
        return 1

    pp = _pubpolicy()
    token = _token()
    value = _registry_repo_set(ROOT / "value-repos.json")
    seeded = _registry_repo_set(ROOT / "positioning-seeds.json")
    stars_floor = int(os.environ.get("LIMEN_GITVS_PORTAL_STARS", "3"))
    overrides = estate.get("repo_overrides") or {}

    decisions: list[dict] = []
    rule_counts: dict[str, int] = {}
    for row in rows:
        full = str(row["full_name"])
        if only and full != only:
            continue
        private = bool(row.get("private"))
        d: dict = {
            "repo": full,
            "visibility": "private" if private else "public",
            "current_class": row.get("class") or classify_repo(full, estate, facts=row) or "unclassed",
            "publish_candidate": False,
            "oversize": bool((row.get("size") or 0) > _GB_KB),
        }
        if full in overrides:
            d.update(
                proposed_class=str(overrides[full].get("class")),
                rule="R1",
                rationale="explicit override row — settled judgment",
            )
        elif row.get("fork"):
            d.update(proposed_class="contrib_fork", rule="R2", rationale="fork (census fact)")
        elif row.get("archived"):
            d.update(proposed_class="frozen", rule="R3", rationale="archived (census fact)")
        elif private:
            hist, n = _path_histogram(full, token, pp, sample_max)
            d["path_histogram"] = hist
            d["paths_sampled"] = n
            risky = hist.get("internal_strategy", 0) + hist.get("personal_pii", 0) + hist.get("secret", 0)
            clean = hist.get("public_safe", 0) + hist.get("product_content", 0)
            if n and risky / n >= 0.05:
                d.update(
                    proposed_class="vault_private",
                    rule="R4",
                    rationale=f"{risky}/{n} sampled paths signal strategy/PII/secret material",
                )
            elif full in value or full in seeded:
                d.update(
                    proposed_class="operation_private",
                    rule="R5",
                    rationale="value-tier/seeded product — the operation is the moat; form-twin eligible",
                )
            elif n and clean / n >= 0.95:
                d.update(
                    proposed_class="operation_private",
                    rule="R6",
                    publish_candidate=True,
                    rationale=f"{clean}/{n} sampled paths public-safe/product — publish-wave candidate (lever-gated)",
                )
            else:
                d.update(
                    proposed_class="private_unreviewed",
                    rule="HOLD",
                    rationale=f"insufficient signal ({n} paths sampled) — held private pending judgment",
                )
        elif full in value or full in seeded or (row.get("stars") or 0) >= stars_floor:
            d.update(
                proposed_class="portal_public",
                rule="R7",
                rationale="value-tier/seeded/star leader — the SEO lure tier",
            )
        else:
            d.update(
                proposed_class="governed_public",
                rule="R8",
                rationale="public long-tail floor (glob — no row needed)",
            )
        rule_counts[d["rule"]] = rule_counts.get(d["rule"], 0) + 1
        decisions.append(d)

    decisions.sort(key=lambda x: x["repo"])
    try:
        DECISIONS.parent.mkdir(parents=True, exist_ok=True)
        DECISIONS.write_text(
            json.dumps({"schema": "limen.estate_decisions.v1", "rows": decisions}, indent=2, sort_keys=True) + "\n"
        )
    except Exception as e:
        print(f"[gitvs] note: decisions receipt write skipped ({str(e)[:80]})")

    needs_row = [
        d
        for d in decisions
        if d["rule"] != "R1"
        and (
            d["proposed_class"] in ("vault_private", "operation_private")
            or (d["proposed_class"] == "portal_public" and d["current_class"] != "portal_public")
            or d["publish_candidate"]
            or d["oversize"]
        )
    ]
    print(
        f"[gitvs] classify: {len(decisions)} repos → "
        + ", ".join(f"{k}={v}" for k, v in sorted(rule_counts.items()))
        + f"; {len(needs_row)} need an override row → {DECISIONS.relative_to(ROOT)}"
    )
    if emit:
        print("# paste into estate.yaml repo_overrides (curate the why lines — this file is public):")
        for d in needs_row:
            extras = ""
            if d["publish_candidate"]:
                extras += ", publish_candidate: true"
            if d["oversize"]:
                extras += ", oversize: true"
            why = str(d["rationale"]).replace('"', "'")
            print(f'  {d["repo"]}: {{class: {d["proposed_class"]}, why: "{why}"{extras}}}')
    return 0


# ── the Meter: Actions spend telemetry + runner-admission observation ───────────────────────────
USAGE_DOC = ROOT / "docs" / "github-actions-usage.json"
USAGE_STAMP = ROOT / "logs" / "gh-usage.json"


def _usage_month(org: str, year: int, month: int) -> dict | None:
    """One month's enhanced-billing usage report, rolled up by product + the top Actions repos by
    minutes. User-scoped keyring auth (_gh_user) — account billing is structurally invisible to the
    App token. None ⟺ endpoint unreadable (fail-open, never a faked verdict)."""
    r = _gh_user(
        ["api", f"/organizations/{org}/settings/billing/usage?year={year}&month={month}"],
        timeout=60,
    )
    if r.returncode != 0:
        return None
    try:
        items = (json.loads(r.stdout or "{}")).get("usageItems") or []
    except json.JSONDecodeError:
        return None
    by_product: dict[str, dict[str, float]] = {}
    actions_minutes_by_repo: dict[str, float] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        product = str(it.get("product") or "?")
        row = by_product.setdefault(product, {"quantity": 0.0, "gross_usd": 0.0, "net_usd": 0.0})
        row["quantity"] += float(it.get("quantity") or 0)
        row["gross_usd"] += float(it.get("grossAmount") or 0)
        row["net_usd"] += float(it.get("netAmount") or 0)
        if product == "actions":
            repo = str(it.get("repositoryName") or "?")
            actions_minutes_by_repo[repo] = actions_minutes_by_repo.get(repo, 0.0) + float(it.get("quantity") or 0)
    top = sorted(actions_minutes_by_repo.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return {
        "by_product": {k: {f: round(x, 2) for f, x in v.items()} for k, v in sorted(by_product.items())},
        "actions_top_repos_minutes": {k: round(v) for k, v in top},
        "gross_usd_total": round(sum(v["gross_usd"] for v in by_product.values()), 2),
        "net_usd_total": round(sum(v["net_usd"] for v in by_product.values()), 2),
    }


def _runner_admission_observation(repo: str) -> tuple[bool | None, str]:
    """Observe, without diagnosing, GitHub's billing-related runner-admission annotation.

    True means the provider text was present, not that the account is billing-locked. False means
    it was absent from the newest completed run. None means the evidence was unreadable.
    """
    r = _gh_user(
        [
            "api",
            f"/repos/{repo}/actions/runs?per_page=1&status=completed",
            "--jq",
            "{id: .workflow_runs[0].id, conclusion: .workflow_runs[0].conclusion}",
        ],
        timeout=30,
    )
    if r.returncode != 0:
        return None, "runs unreadable"
    try:
        run = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return None, "runs unparseable"
    run_id, conclusion = run.get("id"), run.get("conclusion")
    if not run_id:
        return None, "no completed runs"
    if conclusion != "failure":
        return False, f"newest run {run_id} concluded '{conclusion}'"
    rj = _gh_user(
        [
            "api",
            "--paginate",
            "--slurp",
            f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100",
            "--jq",
            "map(.jobs[]) | map({id, conclusion, steps})",
        ],
        timeout=30,
    )
    if rj.returncode != 0:
        return None, "jobs unreadable"
    try:
        jobs = json.loads(rj.stdout or "[]")
    except json.JSONDecodeError:
        return None, "jobs unparseable"
    if not isinstance(jobs, list):
        return None, "jobs unparseable"
    job_ids = [str(job.get("id")) for job in jobs if isinstance(job, dict) and job.get("id")]
    annotations: list[dict] = []
    for jid in job_ids:
        ra = _gh_user(
            ["api", "--paginate", f"/repos/{repo}/check-runs/{jid}/annotations?per_page=100", "--jq", ".[].message"],
            timeout=30,
        )
        if ra.returncode != 0:
            return None, f"annotations unreadable for job {jid}"
        annotations.extend({"message": message} for message in (ra.stdout or "").splitlines() if message)
    failure = classify_ci_failure((job for job in jobs if isinstance(job, dict)), annotations)
    if failure.classification == "provider_runner_admission":
        return True, f"run {run_id}: {failure.detail}"
    return False, f"newest run {run_id} failed without the matching admission annotation"


def usage(estate: dict, *, check: bool, print_json: bool, strict: bool = False, write: bool = True) -> int:
    """Meter Actions spend and preserve runner-admission text without inferring account state."""
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        print("[gitvs] usage: SKIP (offline)")
        return 77 if strict else 0
    now = datetime.now(timezone.utc)
    org = owners(estate)[0]
    month_data = _usage_month(org, now.year, now.month)
    if month_data is None:
        print(
            f"[gitvs] usage: SKIP (billing usage endpoint unreadable for {org} — needs the user-scoped keyring token)"
        )
        return 77 if strict else 0
    probe_repo = os.environ.get("LIMEN_RUNNER_ADMISSION_PROBE_REPO") or "organvm/limen"
    admission_present, admission_detail = _runner_admission_observation(probe_repo)
    budget_default = ((estate.get("budgets") or {}).get("actions_spend") or {}).get("monthly_net_usd_max", 25)
    try:
        budget = float(os.environ.get("LIMEN_ACTIONS_BUDGET") or budget_default)
    except ValueError:
        budget = float(budget_default)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    actions_product = (month_data.get("by_product") or {}).get("actions") or {}
    actions_net = round(float(actions_product.get("net_usd") or 0.0), 2)
    projected = round(actions_net / max(now.day, 1) * days_in_month, 2)
    doc = {
        "schema": "limen.github_actions_usage.v2",
        "org": org,
        "month": f"{now.year:04d}-{now.month:02d}",
        "as_of_day": now.day,
        **month_data,
        "actions_net_usd_mtd": actions_net,
        "actions_net_usd_projected_month_end": projected,
        "budget_net_usd": budget,
        "runner_admission_observation": {
            "repo": probe_repo,
            "annotation_present": admission_present,
            "detail": admission_detail,
            "account_cause_verified": False,
            "remediation_verified": False,
        },
    }
    if write:
        try:
            USAGE_DOC.parent.mkdir(parents=True, exist_ok=True)
            USAGE_DOC.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
            USAGE_STAMP.parent.mkdir(parents=True, exist_ok=True)
            USAGE_STAMP.write_text(
                json.dumps(
                    {
                        "month": doc["month"],
                        "actions_net": actions_net,
                        "actions_projected": projected,
                        "admission_annotation_present": admission_present,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        except Exception as e:  # observability must never break the beat
            print(f"[gitvs] note: usage doc write skipped ({str(e)[:80]})")
    if print_json:
        print(json.dumps(doc, indent=2, sort_keys=True))
    fails: list[str] = []
    if projected > budget:
        fails.append(f"projected ${projected} exceeds budget ${budget}")
    if admission_present is True:
        fails.append(
            f"runner admission annotation observed on {probe_repo} ({admission_detail}); "
            "account cause and remediation are unverified"
        )
    if strict and admission_present is None:
        print("[gitvs] usage: SKIP (runner-admission observation unreadable)")
        return 77
    if fails:
        marker = "✗" if check or strict else "~"
        print(f"{marker} gitvs usage: {'; '.join(fails)} — see {USAGE_DOC.relative_to(ROOT)}")
        return 1 if check or strict else 0
    admission_word = (
        "present" if admission_present is True else ("absent" if admission_present is False else "unreadable")
    )
    print(
        f"✓ gitvs usage: Actions net MTD ${actions_net}, projected ${projected} vs budget ${budget}, "
        f"runner-admission annotation {admission_word} → {USAGE_DOC.relative_to(ROOT)}"
    )
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
    pd.add_argument("--strict", action="store_true", help="exit 77 when any declared rung is skipped")
    prc = sub.add_parser("reconcile", help="drive drift → policy via the three effector sinks (the Effector)")
    prc.add_argument(
        "--apply",
        action="store_true",
        help="invoke the delegate/reap organs (each self-gates); default is a dry report",
    )
    prc.add_argument(
        "--check", action="store_true", help="report-only alias (the metabolize sensor idiom); never mutates"
    )
    pk = sub.add_parser("classify", help="propose per-repo publication classes (R1–R9) → the decisions receipt")
    pk.add_argument("--fresh", action="store_true", help="re-run the census before classifying")
    pk.add_argument("--sample-max", type=int, default=2000, help="tree-path sample cap per private repo")
    pk.add_argument("--emit-overrides", action="store_true", help="print ready-to-paste repo_overrides YAML")
    pk.add_argument("--repo", help="classify a single owner/repo only")
    pu = sub.add_parser("usage", help="Actions spend telemetry + runner-admission observation (the Meter)")
    pu.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when projected Actions spend exceeds budget or the admission annotation is present",
    )
    pu.add_argument(
        "--strict",
        action="store_true",
        help="exit 77 when live usage or runner-admission evidence is unavailable",
    )
    pu.add_argument("--print", action="store_true", help="print the usage doc JSON to stdout too")
    pu.add_argument("--no-write", action="store_true", help="report only; write no usage receipt")
    ppd = sub.add_parser("pr-debt", help="exact paginated open-PR custody and owner-route predicate")
    ppd.add_argument("--check", action="store_true", help="exit 1 unless enumeration is exhaustive and typed")
    ppd.add_argument("--json", action="store_true", help="print the redacted machine-readable census")
    ppd.add_argument(
        "--write-ledger",
        action="store_true",
        help="write the tracked redacted ledger and gitignored private facts receipt",
    )
    args = ap.parse_args(argv)

    estate = load_estate()

    if args.cmd == "census":
        led = observe(estate)
        write_ledger(led)
        n = led["repos"]["total"]
        print(
            f"[gitvs] census: online={led['online']} token={led['app']['token_path']} "
            f"repos={n if n is not None else '—'} "
            f"open_prs={led['prs']['open_total'] if led['prs']['open_total'] is not None else '—'} "
            f"→ {LEDGER.relative_to(ROOT)}"
        )
        if args.print:
            print(json.dumps(led, indent=2, sort_keys=True))
        return 0

    if args.cmd == "doctor":
        offline = bool(args.offline) or bool(os.environ.get("LIMEN_OFFLINE"))
        return doctor(
            estate,
            parity_only=bool(args.parity_only),
            offline=offline,
            strict=bool(args.strict),
        )

    if args.cmd == "reconcile":
        # --check is the report-only sensor idiom; --apply mutates. Report wins if both are given (safety).
        return reconcile(estate, apply=bool(args.apply) and not bool(args.check))

    if args.cmd == "classify":
        return classify_estate(
            estate,
            fresh=bool(args.fresh),
            sample_max=int(args.sample_max),
            emit=bool(args.emit_overrides),
            only=args.repo,
        )

    if args.cmd == "usage":
        return usage(
            estate,
            check=bool(args.check),
            print_json=bool(args.print),
            strict=bool(args.strict),
            write=not bool(args.no_write),
        )

    if args.cmd == "pr-debt":
        return pr_debt(
            estate,
            check=bool(args.check),
            print_json=bool(args.json),
            write_ledger=bool(args.write_ledger),
        )

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
