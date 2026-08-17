#!/usr/bin/env python3
"""vvltvs-organ.py — VVLTVS, THE COUNTENANCE (the face turned to the world).

Sibling of CVSTOS. Where CVSTOS (custos = keeper) faces the MACHINE and owns the local-artifact
lifecycle's terminal stage — EVICTION — VVLTVS (vultus = countenance/face) faces the WORLD and owns
the *public-identity* lifecycle's terminal stage — **verify-the-projection**:

    enumerate → compute → stamp → PROJECT-onto-a-face → ❓VERIFY-face-matches-source → true face

The public numbers drifted because that last step never fired AND the projection is not one step but
a PIPELINE whose segments silently severed. The GitHub profile is a PROJECTION of a source of truth
(like the board is a fold of the event log): a live compute (system-metrics.json) feeds a variable
register (system-vars.json) which feeds the bio. The register's daily write step was dropped from CI
after 2026-05-22 — so the bio froze at 148 repos while the live system grew to 171. A value-checker
cannot catch that until the value has already drifted; you must verify the CONDUIT still flows.

VVLTVS does NOT become another stamper (that is the four-stampers disease). It READS the declared
ownership topology (../face-ownership.json — the DATA-OWNERSHIP CONSTITUTION), the live SSOT, each
register, and each downstream face, and ENFORCES that the projection is coherent end to end. Prior
sessions hand-fixed specific drifts (a one-off); VVLTVS makes both value-drift AND severed-pipe
self-surfacing (the process), so the face can never silently rot again.

Three departments + one surfaced absence, each fail-open, none blocking another, all READ-ONLY on his
repos (they compare; they never write his public face — that stays his):

  SPECVLVM — the mirror. For each downstream face declared in the constitution, read its metric and
             compare against its declared source (the live SSOT, or a specialised register such as
             code-substance). A face that disagrees with a FRESH source is DRIFT (a measured leak ⇒
             --check fails). A face bound to a source whose own pipe is severed/stale is downgraded to
             advisory (you cannot hold a face to a stale target — fix the conduit first).

  VENA     — the conduit/vein. For each register the constitution declares, verify the PIPE that
             should keep it fed from its source is LIVE: the register's tracked value must equal the
             SSOT it tracks (divergence ⇒ SEVERED), a freshness-dated register must be within its lag
             + coverage budget (else STALE), and the writer must still be wired into its workflow.
             This is the department that would have caught the frozen bio at the register, upstream of
             any face. A measured severed/stale pipe ⇒ --check fails.

  NVMERVS  — the number/shape: the contribution activity mix (the radar). The tell for the
             Applied-AI / FDE lane is not the volume, it is the REVIEW fraction: a profile that is
             ~0.6% code-review reads as a high-volume solo operator who does not review others' code —
             the opposite of a collaborative Forward-Deployed Engineer. VVLTVS SURFACES this; it never
             inflates volume to game the graph. Below the review floor ⇒ a flagged liability.

  LINKS    — the constitution names one genuinely MISSING owner: a canonical links home. Deployment
             URLs, social handles and custom domains are scattered across four partial homes with no
             sync. VVLTVS surfaces the absence (advisory) until the home is built by convergence.

DATA / SAFETY:
  - READ-ONLY on his public repos. VVLTVS never mutates a face or a register. --apply prints the
    remediation PLAN (revive the severed pipe / retire the fork / build the links home / which stamper
    to re-run) — the reroute that surfaces the irreducible action without touching his identity.
  - stdlib-only so the beat's python3 needs no deps: the constitution is JSON (not YAML). If the
    manifest is absent or unreadable, VVLTVS degrades to a built-in default face set and still runs.
  - The BEAT is OFFLINE by default: it reads the constitution + SSOT + register/face files + a cached
    contribution-mix; it does NOT call `gh api` per beat (LIMEN_VVLTVS_REFRESH=0). --refresh recomputes
    the mix via one bounded `gh api graphql` call and caches it.
  - Writes a COUNTS-ONLY, PII-free liveness stamp to logs/vvltvs-organ-state.json so organ-health.py
    sees it fired.
  - Fail-open everywhere + lockless: an absent repo (e.g. a CI runner with no workspace) → that face /
    register is "unmeasurable" and is SKIPPED, never a failure. Only a measured leak fails the predicate.

  --check : the executable Definition of Done (exit 0 ⟺ every measurable face reflects its source AND
            every measurable conduit still flows). exit 1 names each drifted face and severed pipe.
  --refresh : recompute the contribution mix from `gh api graphql` and cache it (bounded, one call).
  --apply : print the remediation plan. Read-only; never writes his repos.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
HOME = Path.home()
WORKSPACE = Path(os.environ.get("LIMEN_WORKSPACE_ROOT", str(HOME / "Workspace")))


def _float_or_default(value, default: float, minimum: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    return _float_or_default(os.environ.get(name, str(default)), default, minimum=minimum)


def _int_or_none(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed)


REVIEW_FLOOR = _env_float("LIMEN_VVLTVS_REVIEW_FLOOR", 10, minimum=0)  # review % below this ⇒ FDE-lane liability
REFRESH_ON_BEAT = os.environ.get("LIMEN_VVLTVS_REFRESH", "0") == "1"  # may the beat hit gh api when the mix is stale
MIX_STALE_DAYS = _env_float("LIMEN_VVLTVS_MIX_STALE_DAYS", 7, minimum=0)  # cached mix older than this ⇒ stale

MIX_CACHE = LOGS / "vvltvs-contribution-mix.json"

# The DATA-OWNERSHIP CONSTITUTION — the single declared topology of who owns each answer, how each
# register is fed, and what each face projects from. VVLTVS reads and enforces it; it is a top-level
# declarative registry (peer of organ-ladder.json / his-hand-levers.json).
MANIFEST = ROOT / "face-ownership.json"

# The live source of truth (constitution default). Its repo count derives live from `gh api` at
# generate-time (repo_count_basis: live-public-gh-api); VVLTVS reads it, never recomputes it.
SSOT_REL_DEFAULT = "organvm-corpvs-testamentvm/system-metrics.json"

# Fail-open default face set — used only if face-ownership.json is missing/unreadable. Mirrors the
# constitution's `faces` in the built-in tuple form so the organ never dies on a partial checkout.
DEFAULT_FACES = [
    {
        "key": "profile-bio",
        "path": "organvm/4444J99/data/ecosystem.yml",
        "format": "yaml",
        "binds": "system-vars",
        "checks": [
            {
                "metric": "repos",
                "locator": "total_repos",
                "source": "ssot",
                "ssot_key": "total_repos",
                "kind": "metric",
            },
            {
                "metric": "organs",
                "locator": "total_organs",
                "source": "ssot",
                "ssot_key": "total_organs",
                "kind": "metric",
            },
            {
                "metric": "words",
                "locator": "total_words_short",
                "source": "ssot",
                "ssot_key": "total_words_numeric",
                "kind": "wordshort",
            },
        ],
        "stamper": "hand-edited wire: ecosystem.yml → README via scripts/sync-readme.py",
    },
]


# ── the constitution ──────────────────────────────────────────────────────────────────────────
def _load_manifest() -> dict | None:
    try:
        return json.loads(MANIFEST.read_text())
    except (OSError, ValueError):
        return None


_MAN = _load_manifest()


def _ssot_rel(man: dict | None) -> str:
    if man and isinstance(man.get("ssot"), dict) and man["ssot"].get("home"):
        return man["ssot"]["home"]
    return SSOT_REL_DEFAULT


def _ssot_block(man: dict | None) -> str:
    if man and isinstance(man.get("ssot"), dict) and man["ssot"].get("block"):
        return man["ssot"]["block"]
    return "computed"


def _faces_spec(man: dict | None) -> list[dict]:
    if man and isinstance(man.get("faces"), list) and man["faces"]:
        return man["faces"]
    return DEFAULT_FACES


def _registers_spec(man: dict | None) -> list[dict]:
    if man and isinstance(man.get("registers"), list):
        return man["registers"]
    return []


GB = 1024**3


# ── shared readers (fail-open, stdlib-only so the beat's python3 needs no deps) ───────────────
def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _dig(obj, dotted: str):
    """Walk a dotted path (a.b.c) into nested dicts. None if any hop is missing."""
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _yaml_scalar_text(text: str, key: str):
    """Pull a top-level `key: value` scalar from flat-YAML TEXT by regex (no pyyaml dep)."""
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*(?:#.*)?$", text, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


def _yaml_scalar(path: Path, key: str):
    """Pull a top-level `key: value` scalar from a simple flat YAML file by regex (no pyyaml dep —
    ecosystem.yml is flat key:value). Returns the raw string (quotes/comment stripped) or None."""
    try:
        text = path.read_text()
    except OSError:
        return None
    return _yaml_scalar_text(text, key)


def _file_contains(rel: str, marker: str):
    """Offline read: is `marker` present in WORKSPACE/rel? None ⇒ unmeasurable (file absent)."""
    try:
        return marker in (WORKSPACE / rel).read_text(errors="ignore")
    except OSError:
        return None


def _iso_age_days(iso: str) -> float | None:
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return None


def _short_to_num(s: str) -> int | None:
    """'6K+' -> 6000, '988K' -> 988000, '1.2M' -> 1200000. None if unparseable."""
    m = re.match(r"\s*([\d.]+)\s*([KkMm]?)", str(s))
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    mult = {"k": 1_000, "m": 1_000_000, "": 1}[m.group(2).lower()]
    return int(n * mult)


def _num_to_short(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".rstrip("0").rstrip(".") + "+"
    if n >= 1_000:
        return f"{n // 1000}K+"
    return str(n)


# ── the live source of truth ─────────────────────────────────────────────────────────────────
def ssot(man: dict | None = _MAN) -> dict:
    """The live-derived metrics everything else must reflect. Reads the corpus artifact (whose repo
    count already derives from `gh api`); returns the computed block, PII-free. Never enumerates."""
    path = WORKSPACE / _ssot_rel(man)
    doc = _load_json(path)
    if not isinstance(doc, dict):
        return {"present": False, "path": str(path)}
    computed = doc.get(_ssot_block(man), doc)  # tolerate flat shape
    if not isinstance(computed, dict):
        return {"present": False, "path": str(path)}
    keys = (
        "total_repos",
        "active_repos",
        "ci_workflows",
        "total_organs",
        "total_words_numeric",
        "curated_repos",
        "public_repos_all",
    )
    out = {"present": True, "path": str(path), "basis": computed.get("repo_count_basis")}
    for k in keys:
        out[k] = computed.get(k)
    return out


# ── VENA — the conduit/vein (register ⇄ source pipe integrity) ────────────────────────────────
def vena(src: dict, man: dict | None = _MAN) -> list[dict]:
    """For each declared register, verify the pipe keeping it fed from its source still flows.
    live / severed (tracked value diverges from SSOT) / stale (past lag or coverage budget) /
    unmeasurable (register file absent here). Also probes whether the writer is still wired in CI.
    Loads and returns each register's doc so faces can resolve register-sourced values."""
    rows: list[dict] = []
    for reg in _registers_spec(man):
        if not isinstance(reg, dict):
            continue
        key = reg.get("key", "?")
        home = reg.get("home", "")
        doc = _load_json(WORKSPACE / home) if home else None
        fed = reg.get("fed_by", {}) or {}
        wired = None
        if fed.get("wired_in") and fed.get("writer_marker"):
            wired = _file_contains(fed["wired_in"], fed["writer_marker"])
        row = {
            "key": key,
            "home": home,
            "doc": doc,
            "wired": wired,
            "state": "unmeasurable",
            "detail": "",
            "diverge": [],
        }
        if doc is None:
            row["detail"] = "register file not present here"
            rows.append(row)
            continue
        if not isinstance(doc, dict):
            row["detail"] = "register file is not a JSON object"
            rows.append(row)
            continue

        # tracked-value integrity: register value must equal the SSOT it tracks
        diverge = []
        for t in reg.get("tracks", []) or []:
            if not isinstance(t, dict):
                continue
            locator = t.get("locator")
            if not locator:
                continue
            locator_s = str(locator)
            rv = _dig(doc, locator_s) if "." in locator_s else doc.get(locator_s)
            sv = src.get(t.get("ssot_key")) if src.get("present") and t.get("ssot_key") else None
            if rv is not None and sv is not None and str(rv) != str(sv):
                diverge.append({"key": t.get("key", locator_s), "register": rv, "ssot": sv})
        row["diverge"] = diverge

        # freshness integrity: a dated register must be within its lag + coverage budget
        stale_bits = []
        fr = reg.get("freshness")
        if isinstance(fr, dict):
            date_locator = fr.get("date_locator")
            age = None
            if date_locator:
                age = _iso_age_days(_dig(doc, date_locator) if "." in date_locator else doc.get(date_locator))
                max_lag_days = _float_or_default(fr.get("max_lag_days"), 1e9, minimum=0)
                if age is not None and age > max_lag_days:
                    stale_bits.append(f"audit {int(age)}d old (max {max_lag_days:g})")
            cov_n = doc.get(fr["coverage_locator"]) if fr.get("coverage_locator") else None
            cov_d = src.get(fr.get("coverage_of")) if src.get("present") and fr.get("coverage_of") else None
            if isinstance(cov_n, (int, float)) and isinstance(cov_d, (int, float)) and cov_d:
                cov = cov_n / cov_d
                min_coverage = _float_or_default(fr.get("min_coverage"), 0, minimum=0)
                if cov < min_coverage:
                    stale_bits.append(
                        f"coverage {cov_n}/{cov_d}={int(cov * 100)}% (min {int(min_coverage * 100)}%)"
                    )

        if diverge:
            det = "; ".join(f"{d['key']} {d['register']} vs live {d['ssot']}" for d in diverge)
            if wired is False:
                det += f"; writer '{fed.get('writer_marker')}' not in {Path(fed.get('wired_in', '')).name}"
            row["state"], row["detail"] = "severed", det
        elif stale_bits:
            det = " · ".join(stale_bits)
            if wired is False:
                det += f" · writer '{fed.get('writer_marker')}' not in {Path(fed.get('wired_in', '')).name}"
            row["state"], row["detail"] = "stale", det
        else:
            row["state"] = "live"
            if wired is False:
                row["state"], row["detail"] = (
                    "stale",
                    f"values agree but writer '{fed.get('writer_marker')}' not in {Path(fed.get('wired_in', '')).name}",
                )
        rows.append(row)
    return rows


def _register_state(pipes: list[dict], key: str) -> dict | None:
    for p in pipes:
        if p.get("key") == key:
            return p
    return None


# ── SPECVLVM — the mirror (each face ⇄ its declared source) ───────────────────────────────────
def _published_text(path: Path) -> str | None:
    """A face is HIS PUBLIC repo, so measure the PUBLISHED blob on origin's default branch — NOT the
    local working tree. A local clone drifts behind origin (an un-pulled checkout can be dozens of
    commits stale and report a phantom drift the live public site never had — e.g. a portfolio clone
    41 commits behind showed 116 repos while origin/main already published the correct 171). We read
    the origin ref the clone already has on disk (no network fetch — keeps the beat offline by
    default), and fail open to the working-tree read when git/origin is unavailable."""
    try:
        top = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if top.returncode != 0:
            return None
        root = Path(top.stdout.strip())
        rel = path.relative_to(root).as_posix()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    refs = []
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if head.returncode == 0 and head.stdout.strip():
            refs.append(head.stdout.strip().replace("refs/remotes/", ""))  # e.g. origin/main
    except (OSError, subprocess.SubprocessError):
        pass
    for ref in refs + ["origin/main", "origin/master"]:
        try:
            show = subprocess.run(
                ["git", "-C", str(root), "show", f"{ref}:{rel}"],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if show.returncode == 0:
            return show.stdout
    return None


def _face_text(path: Path) -> str | None:
    """Prefer the published origin blob; fall back to the working-tree file (fail-open)."""
    text = _published_text(path)
    if text is not None:
        return text
    try:
        return path.read_text()
    except OSError:
        return None


def _face_value(path: Path, fmt: str, locator: str):
    text = _face_text(path)
    if text is None:
        return None
    if fmt == "json":
        try:
            doc = json.loads(text)
        except ValueError:
            return None
        return _dig(doc, locator)
    return _yaml_scalar_text(text, locator)  # yaml


def _resolve_source(check: dict, src: dict, pipes: list[dict]):
    """Return (value, is_fresh) for a check's declared source — the live SSOT (always fresh), or a
    named register (fresh only if its conduit is live)."""
    source = check.get("source", "ssot")
    if source == "ssot":
        return (src.get(check.get("ssot_key")) if src.get("present") else None), True
    reg = _register_state(pipes, source)
    if not reg or reg.get("doc") is None:
        return None, False
    sk = check.get("source_key")
    val = _dig(reg["doc"], sk) if sk and "." in sk else (reg["doc"].get(sk) if sk else None)
    return val, (reg.get("state") == "live")


def mirror(src: dict, pipes: list[dict], man: dict | None = _MAN) -> dict:
    rows = []
    for face in _faces_spec(man):
        if not isinstance(face, dict):
            continue
        face_key = face.get("key", "?")
        face_path = face.get("path")
        if not face_path:
            rows.append({"face": face_key, "present": False, "checks": []})
            continue
        path = WORKSPACE / face_path
        if not path.exists():
            rows.append({"face": face_key, "present": False, "checks": []})
            continue
        crows = []
        for c in face.get("checks", []) or []:
            if not isinstance(c, dict):
                continue
            metric = c.get("metric", c.get("locator", "?"))
            locator = c.get("locator")
            if not locator:
                crows.append(
                    {
                        "metric": metric,
                        "state": "unmeasurable",
                        "face": None,
                        "src": None,
                        "source": c.get("source", "ssot"),
                    }
                )
                continue
            fv = _face_value(path, face.get("format", "json"), str(locator))
            if fv is None:
                crows.append(
                    {
                        "metric": metric,
                        "state": "unmeasurable",
                        "face": None,
                        "src": None,
                        "source": c.get("source", "ssot"),
                    }
                )
                continue
            if c.get("kind") == "fabricated":  # legacy default-face path: no declared source at all
                crows.append({"metric": metric, "state": "unbacked", "face": fv, "src": None, "source": None})
                continue
            sv, fresh = _resolve_source(c, src, pipes)
            if sv is None:
                crows.append(
                    {
                        "metric": metric,
                        "state": "unmeasurable",
                        "face": fv,
                        "src": None,
                        "source": c.get("source", "ssot"),
                    }
                )
                continue
            if c.get("kind") == "wordshort":
                fn = _short_to_num(fv)
                sn = _int_or_none(sv)
                if sn is None:
                    crows.append(
                        {
                            "metric": metric,
                            "state": "unmeasurable",
                            "face": fv,
                            "src": sv,
                            "source": c.get("source", "ssot"),
                        }
                    )
                    continue
                agree = fn is not None and abs(fn - sn) <= 0.15 * sn
                disp = _num_to_short(sn)
            else:
                agree = str(fv) == str(sv)
                disp = sv
            if agree:
                state = "agree"
            elif fresh:
                state = "drift"
            else:
                state = "source-stale"  # face differs from a target whose own pipe is severed/stale
            crows.append(
                {"metric": metric, "state": state, "face": fv, "src": disp, "source": c.get("source", "ssot")}
            )
        rows.append({"face": face_key, "present": True, "checks": crows})
    return {"faces": rows}


# ── the LINKS home — the missing owner (surfaced, advisory) ───────────────────────────────────
def links_status(man: dict | None = _MAN) -> dict:
    lh = (man or {}).get("links_home") if man else None
    if not isinstance(lh, dict):
        return {"declared": False}
    out = {
        "declared": True,
        "status": lh.get("status"),
        "target": lh.get("target"),
        "converges": [c.get("home") for c in lh.get("converges", []) if isinstance(c, dict)],
    }
    # once built, read the folded count from the register so the beat can prove the home is populated
    if lh.get("status") == "present" and lh.get("target"):
        doc = _load_json(WORKSPACE / lh["target"])
        if isinstance(doc, dict):
            out["count"] = (doc.get("summary") or {}).get("total")
    return out


# ── NVMERVS — the contribution activity shape (the radar) ─────────────────────────────────────
_GQL = (
    "query{viewer{contributionsCollection{"
    "totalCommitContributions totalIssueContributions totalPullRequestContributions "
    "totalPullRequestReviewContributions restrictedContributionsCount}}}"
)


def _which(name: str) -> bool:
    from shutil import which

    return which(name) is not None


def _compute_mix() -> dict | None:
    """One bounded `gh api graphql` call for the last-year contribution breakdown. Fail-open."""
    if not _which("gh"):
        return None
    try:
        p = subprocess.run(  # noqa: S603
            ["gh", "api", "graphql", "-f", f"query={_GQL}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    try:
        doc = json.loads(p.stdout)
    except ValueError:
        return None
    c = (((doc or {}).get("data") or {}).get("viewer") or {}).get("contributionsCollection")
    if not isinstance(c, dict):
        return None
    commits = c.get("totalCommitContributions", 0)
    issues = c.get("totalIssueContributions", 0)
    prs = c.get("totalPullRequestContributions", 0)
    reviews = c.get("totalPullRequestReviewContributions", 0)
    restricted = c.get("restrictedContributionsCount", 0)
    pub = commits + issues + prs + reviews
    if pub <= 0:
        return None

    def pct(x):
        return round(x / pub * 100, 1)

    return {
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "commits": commits,
        "issues": issues,
        "prs": prs,
        "reviews": reviews,
        "restricted": restricted,
        "public_total": pub,
        "commit_pct": pct(commits),
        "issue_pct": pct(issues),
        "pr_pct": pct(prs),
        "review_pct": pct(reviews),
        "hidden_pct": round(restricted / (pub + restricted) * 100, 1) if (pub + restricted) else 0.0,
    }


def _cache_age_days() -> float | None:
    try:
        return (time.time() - MIX_CACHE.stat().st_mtime) / 86400.0
    except OSError:
        return None


def mix(refresh: bool) -> dict:
    """Return the contribution mix. On the beat (refresh False) read the cache only — never touch the
    network — unless LIMEN_VVLTVS_REFRESH=1 AND the cache is stale. --refresh forces recompute."""
    age = _cache_age_days()
    cached = _load_json(MIX_CACHE) if MIX_CACHE.exists() else None
    want = refresh or (REFRESH_ON_BEAT and (age is None or age > MIX_STALE_DAYS))
    if want:
        fresh = _compute_mix()
        if fresh is not None:
            try:
                LOGS.mkdir(parents=True, exist_ok=True)
                MIX_CACHE.write_text(json.dumps(fresh, indent=2))
            except OSError:
                pass
            fresh["source"] = "live"
            fresh["stale"] = False
            return fresh
    if cached is not None:
        cached["source"] = "cache"
        cached["stale"] = age is not None and age > MIX_STALE_DAYS
        cached["age_days"] = round(age, 1) if age is not None else None
        return cached
    return {"present": False, "source": "none"}


def prose_lag() -> dict:
    """Advisory: count prose/résumé/ticker files still carrying stale hand-set literals. A snapshot
    allowed to lag — surfaced, never a hard fail."""
    markers = ("3,586", "736 test", "58 CI", "58 passing CI", "91 repositories", "91 repos")
    globs = ["organvm/portfolio/resume", "organvm/portfolio/src/components/sketches"]
    hits = files = 0
    for glob_rel in globs:
        base = WORKSPACE / glob_rel
        if not base.exists():
            continue
        for p in base.rglob("*"):
            try:
                if not p.is_file() or p.stat().st_size > 512_000:
                    continue
                text = p.read_text(errors="ignore")
            except OSError:
                continue
            n = sum(1 for m in markers if m in text)
            if n:
                files += 1
                hits += n
    return {"files": files, "markers": hits}


# ── assembly + the Definition of Done ─────────────────────────────────────────────────────────
def assess(refresh: bool = False, man: dict | None = _MAN) -> dict:
    src = ssot(man)
    pipes = vena(src, man)
    return {
        "ssot": src,
        "pipes": pipes,
        "mirror": mirror(src, pipes, man),
        "links": links_status(man),
        "prose": prose_lag(),
        "mix": mix(refresh),
    }


def _drifts(a: dict) -> list[dict]:
    out = []
    for row in a["mirror"]["faces"]:
        for c in row.get("checks", []):
            if c["state"] == "drift":
                out.append(
                    {
                        "face": row["face"],
                        "metric": c["metric"],
                        "face_value": c["face"],
                        "src": c["src"],
                        "source": c.get("source"),
                    }
                )
    return out


def _source_stale(a: dict) -> list[dict]:
    out = []
    for row in a["mirror"]["faces"]:
        for c in row.get("checks", []):
            if c["state"] in ("source-stale", "unbacked"):
                out.append(
                    {"face": row["face"], "metric": c["metric"], "face_value": c["face"], "source": c.get("source")}
                )
    return out


def _severed(a: dict) -> list[dict]:
    return [p for p in a.get("pipes", []) if p["state"] in ("severed", "stale")]


def failures(a: dict) -> list[str]:
    """Definition of Done: exit 0 ⟺ every MEASURABLE face reflects its FRESH source AND every
    MEASURABLE conduit still flows. Unmeasurable faces/registers (no workspace) never fail — only a
    measured leak does. Source-stale faces, unbacked metrics, stale-mix and prose-lag are advisories."""
    out = []
    if not a["ssot"].get("present"):
        return out  # no live source visible here (e.g. CI runner) ⇒ nothing to reconcile against
    for p in _severed(a):  # the root-cause class: a conduit that stopped flowing
        out.append(f"conduit[{p['key']}] {p['state']} — {p['detail']}")
    for d in _drifts(a):
        out.append(
            f"{d['face']}.{d['metric']} = {d['face_value']} but {d['source']} = {d['src']} (projection stale — re-stamp owed)"
        )
    return out


# ── liveness stamp (counts + percentages only, PII-free) ─────────────────────────────────────
def write_stamp(a: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    src, mx = a["ssot"], a["mix"]
    drifts, sstale, severed = _drifts(a), _source_stale(a), _severed(a)
    faces = a["mirror"]["faces"]
    measurable = [f for f in faces if f["present"]]
    true_faces = [f for f in measurable if all(c["state"] in ("agree", "unmeasurable") for c in f["checks"])]
    pipes = a.get("pipes", [])
    pipes_meas = [p for p in pipes if p["state"] != "unmeasurable"]
    pipes_live = [p for p in pipes_meas if p["state"] == "live"]
    rec = {
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ssot_present": src.get("present", False),
        "ssot_repos": src.get("total_repos"),
        "ssot_curated": src.get("curated_repos"),
        "ssot_ci": src.get("ci_workflows"),
        "ssot_words": src.get("total_words_numeric"),
        "ssot_basis": src.get("basis"),
        "faces_measurable": len(measurable),
        "faces_true": len(true_faces),
        "drift_count": len(drifts),
        "drifts": [f"{d['face']}.{d['metric']}" for d in drifts],
        "source_stale_count": len(sstale),
        "pipes_measurable": len(pipes_meas),
        "pipes_live": len(pipes_live),
        "pipes_severed": [f"{p['key']}:{p['state']}" for p in severed],
        "links_home_missing": a.get("links", {}).get("status") == "missing",
        "prose_lag_files": a["prose"]["files"],
        "mix_present": mx.get("present", True) and "review_pct" in mx,
        "review_pct": mx.get("review_pct"),
        "commit_pct": mx.get("commit_pct"),
        "hidden_pct": mx.get("hidden_pct"),
        "mix_stale": mx.get("stale"),
        "review_liability": ("review_pct" in mx and mx.get("review_pct", 100) < REVIEW_FLOOR),
        "review_floor": REVIEW_FLOOR,
        "at_true": not failures(a),
        "open_drifts": failures(a),
    }
    (LOGS / "vvltvs-organ-state.json").write_text(json.dumps(rec, indent=2))
    try:
        vd = LOGS / ".voice"
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "vvltvs").write_text(rec["ran_at"])
    except OSError:
        pass


def _oneliner(a: dict) -> str:
    src, mx = a["ssot"], a["mix"]
    faces = a["mirror"]["faces"]
    measurable = [f for f in faces if f["present"]]
    true_faces = [f for f in measurable if all(c["state"] in ("agree", "unmeasurable") for c in f["checks"])]
    if not src.get("present"):
        head = "vvltvs: live SSOT not visible here (no workspace) — faces/conduits unmeasurable"
    else:
        head = (
            f"vvltvs: faces {len(true_faces)}/{len(measurable)} true · "
            f"SSOT {src.get('total_repos')} repos ({src.get('curated_repos')} curated) / {src.get('ci_workflows')} CI / "
            f"{_num_to_short(src['total_words_numeric']) if src.get('total_words_numeric') else '?'} words"
        )
    pipes = a.get("pipes", [])
    pipes_meas = [p for p in pipes if p["state"] != "unmeasurable"]
    if pipes_meas:
        live = sum(1 for p in pipes_meas if p["state"] == "live")
        head += f" · conduits {live}/{len(pipes_meas)} flowing"
        bad = [p for p in pipes_meas if p["state"] in ("severed", "stale")]
        if bad:
            head += " (" + ", ".join(f"{p['key']}✂{p['state']}" for p in bad) + ")"
    drifts = _drifts(a)
    if drifts:
        d = ", ".join(f"{x['face']}.{x['metric']} {x['face_value']}→{x['src']}" for x in drifts[:3])
        head += f" · drift: {d}"
    lk = a.get("links", {})
    if lk.get("status") == "missing":
        head += " · links home: MISSING"
    elif lk.get("status") == "present":
        head += f" · links home: {lk['count']}" if lk.get("count") is not None else " · links home: ✓"
    if "review_pct" in mx:
        tell = " ⚠" if mx["review_pct"] < REVIEW_FLOOR else ""
        stale = " (stale)" if mx.get("stale") else ""
        head += f" · mix {mx['commit_pct']}% commit / {mx['review_pct']}% review{tell} / {mx.get('hidden_pct', 0)}% hidden{stale}"
    else:
        head += " · mix: not yet computed (--refresh)"
    return head


def _face_stamper(face_key: str, man: dict | None = _MAN) -> str:
    for f in _faces_spec(man):
        if f.get("key") == face_key:
            return f.get("stamper", "unknown")
    return "unknown"


def _reg_remedy(reg_key: str, man: dict | None = _MAN) -> str:
    for r in _registers_spec(man):
        if r.get("key") == reg_key:
            note = (r.get("fed_by", {}) or {}).get("_note")
            return note or f"re-establish the pipe feeding {reg_key}"
    return f"re-establish the pipe feeding {reg_key}"


def _remediation(a: dict, man: dict | None = _MAN) -> int:
    """--apply: the plan, not the mutation. Print the conduit revivals, face re-stamps, and the
    links-home build — read-only. His public face + the org-repo pipes stay his gated levers."""
    severed = _severed(a)
    drifts = _drifts(a)
    sstale = _source_stale(a)
    links = a.get("links", {})
    if not severed and not drifts and not sstale and links.get("status") != "missing":
        print("vvltvs --apply: nothing to reconcile — every face reflects its source and every conduit flows.")
        return 0
    print("vvltvs --apply — remediation plan (VVLTVS never writes; run the owning fix):\n")

    if severed:
        print("  ═ CONDUITS (fix these FIRST — a severed pipe is the root cause; faces auto-heal once it flows) ═")
        for p in severed:
            print(f"  ✂ {p['key']} [{p['state']}] — {p['detail']}")
            print(f"    ↳ {_reg_remedy(p['key'], man)}\n")

    faces: dict[str, list[str]] = {}
    for d in drifts:
        faces.setdefault(d["face"], []).append(f"    {d['metric']}: {d['face_value']} → {d['src']}")
    for u in sstale:
        faces.setdefault(u["face"], []).append(
            f"    {u['metric']}: {u['face_value']} (source '{u['source']}' stale — fix its conduit first)"
        )
    if faces:
        print("  ═ FACES (re-stamp from the reconciled source) ═")
        for face, lines in faces.items():
            print(f"  ▸ {face}")
            for ln in lines:
                print(ln)
            print(f"    ↳ owner: {_face_stamper(face, man)}\n")

    if links.get("status") == "missing":
        print("  ═ LINKS HOME (the missing owner — build by CONVERGING these partial homes) ═")
        print(f"    target: {links.get('target')}")
        for h in links.get("converges", []):
            print(f"      · {h}")
        print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="VVLTVS — the countenance (verify the public face reflects the SSOT).")
    ap.add_argument(
        "--check",
        action="store_true",
        help="Definition of Done: exit 0 iff every face reflects its source and every conduit flows",
    )
    ap.add_argument("--refresh", action="store_true", help="recompute the contribution mix via `gh api graphql`")
    ap.add_argument("--apply", action="store_true", help="print the remediation plan (read-only; never writes repos)")
    ap.add_argument("--json", action="store_true", help="print the full assessment as JSON")
    args = ap.parse_args()

    a = assess(refresh=args.refresh)
    write_stamp(a)

    if args.json:
        printable = {k: v for k, v in a.items()}
        printable["pipes"] = [{k: v for k, v in p.items() if k != "doc"} for p in a.get("pipes", [])]
        print(json.dumps(printable, indent=2, default=str))
        return 0

    if args.apply:
        return _remediation(a)

    if args.check:
        fails = failures(a)
        adv = _source_stale(a)
        if not fails:
            note = f" ({len(adv)} source-stale advisory)" if adv else ""
            print(f"vvltvs --check: every measurable face reflects its source and every conduit flows ✓{note}")
            return 0
        print("vvltvs --check: the projection is not coherent — open items:")
        for f in fails:
            print(f"  ✗ {f}")
        if adv:
            print(f"  · advisory: {len(adv)} face metric(s) awaiting a stale source's conduit")
        if a.get("links", {}).get("status") == "missing":
            print("  · advisory: no canonical links home (see --apply)")
        return 1

    print(_oneliner(a))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
