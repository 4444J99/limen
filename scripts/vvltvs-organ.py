#!/usr/bin/env python3
"""vvltvs-organ.py — VVLTVS, THE COUNTENANCE (the face turned to the world).

Sibling of CVSTOS. Where CVSTOS (custos = keeper) faces the MACHINE and owns the local-artifact
lifecycle's terminal stage — EVICTION — VVLTVS (vultus = countenance/face) faces the WORLD and owns
the *public-identity* lifecycle's terminal stage — **verify-the-projection**:

    enumerate → compute → stamp → PROJECT-onto-a-face → ❓VERIFY-face-matches-source → true face

Nothing today fires that last step. That is precisely why the public numbers drifted: the GitHub
profile is a PROJECTION of a source of truth (like the board is a fold of the event log), and there
are FOUR independent projection endpoints with ZERO reconciliation between them —

  live SSOT (organvm-corpvs-testamentvm/system-metrics.json)   171 repos / 107 CI / 988K words
  profile bio README (4444J99/data/ecosystem.yml)              148 repos / "6K+" words
  portfolio build-time copy (portfolio/src/data/*.json)        116 repos / 104 CI / 2,980 code files
  the hand-set account bio + résumés + ticker                   91 repos / 3,586 files / 736 tests / 58 CI

VVLTVS does NOT become a fifth stamper (that is the disease). It READS the already-live SSOT and each
downstream face and reports the drift — the verify stage the pipeline never had. Prior sessions
hand-fixed specific drifts (a one-off); VVLTVS makes drift self-surfacing (the process), so the face
can never silently rot again.

Two departments, each fail-open, none blocking another, all READ-ONLY on his repos (they compare;
they never write his public face — that stays his):

  SPECVLVM — the mirror. For each downstream DATA face (profile ecosystem.yml, portfolio SSOT copy,
             portfolio vitals), read its metric and compare against the live SSOT. A face that
             disagrees with a real source is DRIFT (a measured leak ⇒ --check fails). A face that
             advertises a metric the SSOT computes NO source for (code_files / test_files /
             automated_tests are `repos × 20` fabrications) is UNBACKED (advisory — the fix is a
             bigger deferred build: wire manifestatio-code-audit.py into the SSOT). Narrative prose
             (résumés, ticker) is a snapshot allowed to lag — surfaced as an advisory count, never a
             hard fail (forcing prose exact-or-red is precision theatre that blocks deploys).

  NVMERVS  — the number/shape: the contribution activity mix (the radar). A clean greenfield gap —
             nothing computed it before. The tell for the Applied-AI / FDE lane is not the 25k
             volume, it is the REVIEW fraction: a profile that is ~0.6% code-review reads as a
             high-volume solo operator who does not review others' code — the opposite of a
             collaborative Forward-Deployed Engineer. VVLTVS SURFACES this (lead-with-system); it
             never inflates volume to game the graph. Below the review floor ⇒ a flagged liability.

DATA / SAFETY:
  - READ-ONLY on his public repos. VVLTVS never mutates a face. --apply prints the remediation PLAN
    (which existing stamper to re-run, current→target per drifted metric) — the reroute that surfaces
    the irreducible action without touching his identity. His bio prose + account bio stay his paste.
  - The BEAT is OFFLINE by default: it reads the SSOT + face files + a cached contribution-mix; it
    does NOT call `gh api` per beat (LIMEN_VVLTVS_REFRESH=0). --refresh recomputes the mix via one
    bounded `gh api graphql` call and caches it. A stale/absent cache is an advisory note, never a
    crash and never a blocked beat.
  - Writes a COUNTS-ONLY, PII-free liveness stamp to logs/vvltvs-organ-state.json (counts +
    percentages + face labels; never a login, never file contents) so organ-health.py sees it fired.
  - Fail-open everywhere + lockless: an absent repo (e.g. on a CI runner with no workspace) → that
    face is "unmeasurable" and is SKIPPED, never a failure. Only a measured drift fails the predicate.

  --check : the executable Definition of Done (exit 0 ⟺ every measurable data face agrees with the
            live SSOT). exit 1 names each drifted surface. Unbacked/fabricated + stale-mix are
            advisories that print but do not fail.
  --refresh : recompute the contribution mix from `gh api graphql` and cache it (bounded, one call).
  --apply : print the remediation plan (which stamper re-run reconciles each drifted face). Read-only;
            never writes his repos. The actual re-stamp of his public face stays his gated lever.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
HOME = Path.home()
WORKSPACE = Path(os.environ.get("LIMEN_WORKSPACE_ROOT", str(HOME / "Workspace")))

REVIEW_FLOOR = float(os.environ.get("LIMEN_VVLTVS_REVIEW_FLOOR", "10"))  # review % below this ⇒ FDE-lane liability
REFRESH_ON_BEAT = os.environ.get("LIMEN_VVLTVS_REFRESH", "0") == "1"  # may the beat hit gh api when the mix is stale
MIX_STALE_DAYS = float(os.environ.get("LIMEN_VVLTVS_MIX_STALE_DAYS", "7"))  # cached mix older than this ⇒ stale

MIX_CACHE = LOGS / "vvltvs-contribution-mix.json"

# The live source of truth — the ONE enumeration everything else must reflect. Its repo count derives
# live from `gh api` at generate-time (repo_count_basis: live-public-gh-api); VVLTVS reads it, never
# recomputes it (adding a parallel enumerator IS the four-stampers disease).
SSOT_REL = "organvm-corpvs-testamentvm/system-metrics.json"

# The downstream DATA faces that must reflect the SSOT. Each check: (label, path-into-face, ssot-key,
# kind). ssot-key None + kind "fabricated" ⇒ the metric has no live source at all. Paths are the repo
# LAYOUT (structural, fail-open if moved), not tunable knobs. Prose faces (résumés/ticker) are NOT
# here — they are a snapshot allowed to lag, surfaced separately as an advisory grep.
FACES = [
    (
        "profile-bio",
        "organvm/4444J99/data/ecosystem.yml",
        "yaml",
        [
            ("repos", "total_repos", "total_repos", "metric"),
            ("organs", "total_organs", "total_organs", "metric"),
            ("words", "total_words_short", "total_words_numeric", "wordshort"),
        ],
    ),
    (
        "portfolio-ssot-copy",
        "organvm/portfolio/src/data/system-metrics.json",
        "json",
        [
            ("repos", "computed.total_repos", "total_repos", "metric"),
            ("ci_workflows", "computed.ci_workflows", "ci_workflows", "metric"),
            ("organs", "computed.total_organs", "total_organs", "metric"),
        ],
    ),
    (
        "portfolio-vitals",
        "organvm/portfolio/src/data/vitals.json",
        "json",
        [
            ("code_files", "substance.code_files", None, "fabricated"),
            ("test_files", "substance.test_files", None, "fabricated"),
            ("automated_tests", "substance.automated_tests", None, "fabricated"),
        ],
    ),
]

# The stamper that owns re-stamping each face from the SSOT — surfaced by --apply, never auto-run.
FACE_STAMPER = {
    "profile-bio": "hand-edited wire: organvm/4444J99/data/ecosystem.yml → README via scripts/sync-readme.py "
    "(the bio wire is separate from metrics-targets.yaml — edit the numbers, then `sync-readme.py --check`)",
    "portfolio-ssot-copy": "corpus propagator: organvm-corpvs-testamentvm/metrics-targets.yaml "
    "(re-run propagate-metrics.py to refresh the portfolio json copies from the live SSOT)",
    "portfolio-vitals": "NO live source — wire organvm-corpvs-testamentvm/scripts/manifestatio-code-audit.py "
    "(code-substance-report.json) into system-metrics.json so code_files/test_files derive (memory residue)",
}

# Prose surfaces that still carry the stale hand-set literals — advisory only (snapshots may lag).
_STALE_PROSE_MARKERS = ("3,586", "736 test", "58 CI", "58 passing CI", "91 repositories", "91 repos")
_PROSE_GLOBS = [
    "organvm/portfolio/resume",
    "organvm/portfolio/src/components/sketches",
]

GB = 1024**3


# ── shared readers (fail-open, stdlib-only so the beat's python3 needs no deps) ───────────────
def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _dig(obj: dict, dotted: str):
    """Walk a dotted path (a.b.c) into nested dicts. None if any hop is missing."""
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _yaml_scalar(path: Path, key: str):
    """Pull a top-level `key: value` scalar from a simple YAML file by regex (no pyyaml dependency —
    ecosystem.yml is flat key:value). Returns the raw string (quotes/comment stripped) or None."""
    try:
        text = path.read_text()
    except OSError:
        return None
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*(?:#.*)?$", text, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


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
def ssot() -> dict:
    """The live-derived metrics everything else must reflect. Reads the corpus artifact (whose repo
    count already derives from `gh api`); returns the `computed` block, PII-free. Never enumerates."""
    path = WORKSPACE / SSOT_REL
    doc = _load_json(path)
    if doc is None:
        return {"present": False, "path": str(path)}
    computed = doc.get("computed", doc)  # tolerate flat shape
    keys = ("total_repos", "active_repos", "ci_workflows", "total_organs", "total_words_numeric")
    out = {"present": True, "path": str(path), "basis": computed.get("repo_count_basis")}
    for k in keys:
        out[k] = computed.get(k)
    return out


# ── SPECVLVM — the mirror (SSOT ⇄ each downstream face) ───────────────────────────────────────
def _face_value(path: Path, fmt: str, locator: str):
    if fmt == "json":
        doc = _load_json(path)
        return _dig(doc, locator) if doc is not None else None
    return _yaml_scalar(path, locator)  # yaml


def mirror(src: dict) -> dict:
    rows = []
    for name, rel, fmt, checks in FACES:
        path = WORKSPACE / rel
        if not path.exists():
            rows.append({"face": name, "present": False, "checks": []})
            continue
        crows = []
        for label, locator, ssot_key, kind in checks:
            fv = _face_value(path, fmt, locator)
            if fv is None:
                crows.append({"metric": label, "state": "unmeasurable", "face": None, "ssot": None})
                continue
            if kind == "fabricated":
                crows.append({"metric": label, "state": "unbacked", "face": fv, "ssot": None})
                continue
            sv = src.get(ssot_key) if src.get("present") else None
            if sv is None:
                crows.append({"metric": label, "state": "unmeasurable", "face": fv, "ssot": None})
                continue
            if kind == "wordshort":
                fn = _short_to_num(fv)
                # drift if the short form is off by >15% from the live numeric word total
                state = "agree" if (fn is not None and abs(fn - int(sv)) <= 0.15 * int(sv)) else "drift"
                crows.append({"metric": label, "state": state, "face": fv, "ssot": _num_to_short(int(sv))})
            else:
                state = "agree" if str(fv) == str(sv) else "drift"
                crows.append({"metric": label, "state": state, "face": fv, "ssot": sv})
        rows.append({"face": name, "present": True, "checks": crows})
    return {"faces": rows}


def prose_lag() -> dict:
    """Advisory: count prose/résumé/ticker files still carrying the stale hand-set literals. A
    snapshot allowed to lag — surfaced, never a hard fail."""
    hits = 0
    files = 0
    for glob_rel in _PROSE_GLOBS:
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
            n = sum(1 for m in _STALE_PROSE_MARKERS if m in text)
            if n:
                files += 1
                hits += n
    return {"files": files, "markers": hits}


# ── NVMERVS — the contribution activity shape (the radar) ─────────────────────────────────────
_GQL = (
    "query{viewer{contributionsCollection{"
    "totalCommitContributions totalIssueContributions totalPullRequestContributions "
    "totalPullRequestReviewContributions restrictedContributionsCount}}}"
)


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
    doc = None
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


def _which(name: str) -> bool:
    from shutil import which

    return which(name) is not None


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


# ── assembly + the Definition of Done ─────────────────────────────────────────────────────────
def assess(refresh: bool = False) -> dict:
    src = ssot()
    return {"ssot": src, "mirror": mirror(src), "prose": prose_lag(), "mix": mix(refresh)}


def _drifts(a: dict) -> list[dict]:
    out = []
    for row in a["mirror"]["faces"]:
        for c in row.get("checks", []):
            if c["state"] == "drift":
                out.append({"face": row["face"], "metric": c["metric"], "face_value": c["face"], "ssot": c["ssot"]})
    return out


def _unbacked(a: dict) -> list[dict]:
    out = []
    for row in a["mirror"]["faces"]:
        for c in row.get("checks", []):
            if c["state"] == "unbacked":
                out.append({"face": row["face"], "metric": c["metric"], "face_value": c["face"]})
    return out


def failures(a: dict) -> list[str]:
    """The Definition of Done: exit 0 ⟺ every MEASURABLE data face agrees with the live SSOT.
    Unmeasurable faces (no workspace / absent repo) never fail — only a measured drift does.
    Unbacked-fabricated + stale-mix + prose-lag are advisories, not failures."""
    out = []
    if not a["ssot"].get("present"):
        return out  # no live source visible here (e.g. CI runner) ⇒ nothing to reconcile against
    for d in _drifts(a):
        fv, sv = d["face_value"], d["ssot"]
        out.append(f"{d['face']}.{d['metric']} = {fv} but live SSOT = {sv} (projection stale — re-stamp owed)")
    return out


# ── liveness stamp (counts + percentages only, PII-free) ─────────────────────────────────────
def write_stamp(a: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    src, mx = a["ssot"], a["mix"]
    drifts, unbacked = _drifts(a), _unbacked(a)
    faces = a["mirror"]["faces"]
    measurable = [f for f in faces if f["present"]]
    true_faces = [f for f in measurable if not any(c["state"] == "drift" for c in f["checks"])]
    rec = {
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ssot_present": src.get("present", False),
        "ssot_repos": src.get("total_repos"),
        "ssot_ci": src.get("ci_workflows"),
        "ssot_words": src.get("total_words_numeric"),
        "ssot_basis": src.get("basis"),
        "faces_measurable": len(measurable),
        "faces_true": len(true_faces),
        "drift_count": len(drifts),
        "drifts": [f"{d['face']}.{d['metric']}" for d in drifts],
        "unbacked_count": len(unbacked),
        "unbacked": [f"{u['face']}.{u['metric']}" for u in unbacked],
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
    true_faces = [f for f in measurable if not any(c["state"] == "drift" for c in f["checks"])]
    if not src.get("present"):
        head = "vvltvs: live SSOT not visible here (no workspace) — faces unmeasurable"
    else:
        head = (
            f"vvltvs: faces {len(true_faces)}/{len(measurable)} true · "
            f"SSOT {src.get('total_repos')} repos / {src.get('ci_workflows')} CI / "
            f"{_num_to_short(src['total_words_numeric']) if src.get('total_words_numeric') else '?'} words"
        )
    drifts = _drifts(a)
    if drifts:
        d = ", ".join(f"{x['face']}.{x['metric']} {x['face_value']}→{x['ssot']}" for x in drifts[:3])
        head += f" · drift: {d}"
    if "review_pct" in mx:
        tell = " ⚠" if mx["review_pct"] < REVIEW_FLOOR else ""
        stale = " (stale)" if mx.get("stale") else ""
        head += (
            f" · mix {mx['commit_pct']}% commit / {mx['review_pct']}% review{tell}"
            f" / {mx.get('hidden_pct', 0)}% hidden{stale}"
        )
    else:
        head += " · mix: not yet computed (--refresh)"
    ub = _unbacked(a)
    if ub:
        head += f" · {len(ub)} unbacked (fabricated: no live source)"
    return head


def _remediation(a: dict) -> int:
    """--apply: the plan, not the mutation. Print exactly which stamper reconciles each drifted face,
    current→target per metric. Read-only — his public face stays his gated lever."""
    drifts = _drifts(a)
    unbacked = _unbacked(a)
    if not drifts and not unbacked:
        print("vvltvs --apply: nothing to reconcile — every measurable face already reflects the live SSOT.")
        return 0
    print("vvltvs --apply — remediation plan (VVLTVS never writes your public face; run the owning stamper):\n")
    by_face: dict[str, list[str]] = {}
    for d in drifts:
        by_face.setdefault(d["face"], []).append(f"    {d['metric']}: {d['face_value']} → {d['ssot']}")
    for u in unbacked:
        by_face.setdefault(u["face"], []).append(f"    {u['metric']}: {u['face_value']} (UNBACKED — no live source)")
    for face, lines in by_face.items():
        print(f"  ▸ {face}")
        for ln in lines:
            print(ln)
        print(f"    ↳ owner: {FACE_STAMPER.get(face, 'unknown')}\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="VVLTVS — the countenance (verify the public face reflects the SSOT).")
    ap.add_argument("--check", action="store_true", help="Definition of Done: exit 0 iff every face reflects the SSOT")
    ap.add_argument("--refresh", action="store_true", help="recompute the contribution mix via `gh api graphql`")
    ap.add_argument("--apply", action="store_true", help="print the remediation plan (read-only; never writes repos)")
    ap.add_argument("--json", action="store_true", help="print the full assessment as JSON")
    args = ap.parse_args()

    a = assess(refresh=args.refresh)
    write_stamp(a)

    if args.json:
        print(json.dumps(a, indent=2, default=str))
        return 0

    if args.apply:
        return _remediation(a)

    if args.check:
        fails = failures(a)
        ub = _unbacked(a)
        if not fails:
            note = f" ({len(ub)} unbacked-fabricated advisory)" if ub else ""
            print(f"vvltvs --check: every measurable face reflects the live SSOT ✓{note}")
            return 0
        print("vvltvs --check: the public face has drifted from the live SSOT — open projections:")
        for f in fails:
            print(f"  ✗ {f}")
        if ub:
            print(f"  · advisory: {len(ub)} unbacked-fabricated metric(s) (no live source — deferred wire)")
        return 1

    print(_oneliner(a))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
