#!/usr/bin/env python3
"""decorum-keeper.py — DECORVM, the professionalization keeper (the guard against egg-face).

In Roman rhetoric *decorum* is "the fitting/becoming" — the propriety that makes a public act land
as dignified rather than embarrassing. This organ is its analogue: a continuous keeper that answers
one question every beat — "is anything on my public surfaces currently embarrassing?" — and drives
each embarrassment class to structural closure so it never recurs (the "no egg-face EVER").

DECORVM owns no measurement machinery and no surface list. It FEDERATES the estate's existing
quality organs — each of which already measures one facet and enumerates its own surfaces — and
rolls their sub-verdicts into a single verdict (logs/decorum.json, schema limen.decorum.v1):

    experience  (scripts/experience-audit.py)      reachable / fast / light / no-console-errors
    visual      (experience-judge → judgments.yaml) layout / typography / coherence / trust
    seo         (scripts/seo-audit.py)             README/SEO 10-rung standard, scoped to value-repos
    countenance (scripts/vvltvs-organ.py)          public numbers not drifting from SSOT
    links       (scripts/link-health.py)           no dead links on the public front doors
    moat        (scripts/moat-audit.py)            no private value leaked onto a public repo

The department set, each department's artifact/command, and the severity floor that flips the
verdict red are DECLARED DATA in institutio/governance/decorum-surfaces.yaml (derive-never-pin).
Add a facet = add one department entry; there is no surface list to maintain.

FAIL-OPEN IS LAW. A missing, unreadable, or unmeasured department is a `skip`, never a `fail`:
a keeper that cries wolf because `requests` isn't installed, or because an artifact is stale, is
its own egg-face. Only a *measured* failure becomes a finding.

The polish lane (Phase 2/3 — spellcheck, bio-staleness, narrative accuracy, tiered LLM-judge) and
the effector loop (Phase 4 — findings → tasks + censor precedents + GitHub issues, armed by
LIMEN_DECORUM_APPLY=1, dry-run by default, never sends) attach to this same core.

Usage:
  python3 scripts/decorum-keeper.py --sweep     # federate every department → logs/decorum.json; exit 0 iff clean
  python3 scripts/decorum-keeper.py --doctor    # offline: validate the registry + schema, run no network
  python3 scripts/decorum-keeper.py --json      # emit the machine verdict to stdout
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
REGISTRY = Path(os.environ.get("LIMEN_DECORUM_SURFACES", ROOT / "institutio" / "governance" / "decorum-surfaces.yaml"))
OUT = ROOT / "logs" / "decorum.json"
FACE = ROOT / "logs" / "decorum.html"
VOICE = ROOT / "logs" / ".voice" / "decorum"
SCHEMA = "limen.decorum.v1"

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a hard dep of the beat
    yaml = None


# ── helpers ───────────────────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_yaml(path: Path):
    if yaml is None or not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return None


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _sev_index(order: list[str], sev: str) -> int:
    try:
        return order.index(sev)
    except ValueError:
        return 0


def _finding(dept: str, surface: str, severity: str, detail: str, source: str) -> dict:
    fid = f"{dept}:{surface}".lower().replace("/", "-").replace(" ", "-")
    return {"id": fid, "lane": dept, "surface": surface, "severity": severity, "detail": detail, "source": source}


def _value_repos(reg: dict) -> set[str]:
    """The egg-face-critical repo set — DERIVED from value-repos.json, matched by 'owner/name' and bare name."""
    src = ((reg.get("scope_sources") or {}).get("value_repos")) or "value-repos.json"
    data = _load_json(ROOT / src) or {}
    repos = data.get("repos") if isinstance(data, dict) else data
    out: set[str] = set()
    for r in repos or []:
        out.add(r.lower())
        out.add(r.split("/")[-1].lower())
    return out


# ── department extractors (each fail-open; returns (findings, measured?)) ───────
def dept_experience(art, dept, sev) -> tuple[list, bool]:
    if not isinstance(art, dict):
        return [], False
    surfaces = art.get("surfaces") or {}
    findings, measured = [], False
    for sid, s in surfaces.items() if isinstance(surfaces, dict) else []:
        # UNMEASURED → skip: env-blind probe, or every rung null.
        if s.get("probe_error"):
            continue
        rungs = s.get("rungs") or {}
        real = {k: v for k, v in rungs.items() if v is not None}
        if not real:
            continue
        measured = True
        if s.get("pass") is False:
            failed = sorted(k for k, v in real.items() if v is False)
            findings.append(_finding(dept, sid, sev, f"experience rungs failed: {', '.join(failed) or '?'} ({s.get('url','')})", "experience-audit.json"))
    return findings, measured


def dept_visual(art, dept, sev) -> tuple[list, bool]:
    if not isinstance(art, dict):
        return [], False
    judgments = art.get("judgments") or {}
    findings, measured = [], False
    for sid, rows in judgments.items() if isinstance(judgments, dict) else []:
        if not rows:
            continue
        measured = True
        last = rows[-1]
        if str(last.get("verdict")).lower() == "fail":
            defects = "; ".join(last.get("defects") or []) or "failed visual judgment"
            findings.append(_finding(dept, sid, sev, f"visual: {defects}", "experience-judgments.yaml"))
    return findings, measured


def dept_seo(art, dept, sev, value_set) -> tuple[list, bool]:
    if not isinstance(art, dict):
        return [], False
    repos = art.get("repos") or {}
    findings, measured = [], False
    for key, r in repos.items() if isinstance(repos, dict) else []:
        # scope to value/portal repos only — the estate's long tail is not an egg-face
        if value_set and key.lower() not in value_set and key.split("/")[-1].lower() not in value_set:
            continue
        measured = True
        if r.get("pass") is False:
            failed = sorted(k for k, v in (r.get("rungs") or {}).items() if v is False)
            findings.append(_finding(dept, key, sev, f"README/SEO ({r.get('standard','?')}) failed rungs: {', '.join(failed)}", "seo-audit.json"))
    return findings, measured


def dept_countenance(art, dept, sev) -> tuple[list, bool]:
    if not isinstance(art, dict):
        return [], False
    measured = "at_true" in art
    findings = []
    if art.get("at_true") is False:
        for d in art.get("open_drifts") or ["face drifted from SSOT"]:
            findings.append(_finding(dept, "countenance", sev, f"face-drift: {d}", "vvltvs-organ-state.json"))
    return findings, measured


def dept_links(art, dept, sev) -> tuple[list, bool]:
    if not isinstance(art, dict):
        return [], False
    measured = "ok" in art or "total_dead" in art
    findings = []
    if art.get("ok") is False or (art.get("total_dead") or 0) > 0:
        findings.append(_finding(dept, "public-links", sev, f"{art.get('total_dead', '?')} dead link(s) across public surfaces", "link-health/last.json"))
    return findings, measured


def dept_moat(out, dept, sev, lure_sev) -> tuple[list, bool]:
    """moat-audit emits JSON: {moat_leaks: N|[...], lure_gaps: N|[...]} (shape-tolerant)."""
    if not isinstance(out, dict):
        return [], False
    findings = []

    def _count(v):
        return len(v) if isinstance(v, list) else (int(v) if isinstance(v, (int, float)) else 0)

    leaks = out.get("moat_leaks", out.get("leaks"))
    gaps = out.get("lure_gaps", out.get("gaps"))
    if _count(leaks) > 0:
        findings.append(_finding(dept, "moat", sev, f"{_count(leaks)} MOAT LEAK(s): private value on a public repo", "moat-audit"))
    if _count(gaps) > 0:
        findings.append(_finding(dept, "lure", lure_sev, f"{_count(gaps)} lure gap(s): dark/unpositioned public repo", "moat-audit"))
    return findings, True


def _run_command(cmd: str, timeout: int):
    try:
        p = subprocess.run(cmd, shell=True, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
        return json.loads(p.stdout) if p.stdout.strip() else None
    except Exception:
        return None


# ── the polish lane (Phase 2 — deterministic, zero tokens) ─────────────────────
# A curated, HIGH-CONFIDENCE misspelling map. Deliberately small and unambiguous: every entry is a
# word that is essentially never intended, so false positives on public prose stay near zero. (codespell
# is used when present; this is the always-available fallback per the registry.)
_TYPO_MAP = {
    "recieve": "receive", "recieved": "received", "seperate": "separate", "seperated": "separated",
    "definately": "definitely", "occured": "occurred", "occurance": "occurrence", "untill": "until",
    "adress": "address", "calender": "calendar", "cateogry": "category", "commited": "committed",
    "wich": "which", "teh": "the", "thier": "their", "acheive": "achieve", "acheived": "achieved",
    "beleive": "believe", "publically": "publicly", "neccessary": "necessary", "accomodate": "accommodate",
    "occassion": "occasion", "existance": "existence", "maintainance": "maintenance", "priviledge": "privilege",
    "enviroment": "environment", "goverment": "government", "independant": "independent", "reccomend": "recommend",
    "refered": "referred", "succesful": "successful", "sucessful": "successful", "tommorow": "tomorrow",
    "untils": "until", "buisness": "business", "gaurantee": "guarantee", "hardward": "hardware",
    "developement": "development", "arguement": "argument", "compatability": "compatibility",
}
_FENCE_RX = None  # compiled lazily to keep import cheap


def _strip_code(text: str) -> str:
    """Drop fenced ``` code blocks and inline `code spans` — typos there are not public-prose egg-face."""
    import re
    out, in_fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out.append(re.sub(r"`[^`]*`", " ", line))
    return "\n".join(out)


def _spellcheck(text: str):
    """Return [(word, fix, lineno)] for vendored typos in prose (code stripped, word-boundary, case-insensitive)."""
    import re
    hits = []
    for lineno, line in enumerate(_strip_code(text).splitlines(), 1):
        for word in re.findall(r"[A-Za-z]+", line):
            fix = _TYPO_MAP.get(word.lower())
            if fix:
                hits.append((word, fix, lineno))
    return hits


def _git_mtime_days(relpath: str) -> float | None:
    """Age in days of a file's last git commit (authored freshness, not checkout mtime)."""
    try:
        p = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%ct", "--", relpath],
                           capture_output=True, text=True, timeout=15)
        epoch = int(p.stdout.strip())
        return (datetime.now(timezone.utc).timestamp() - epoch) / 86400.0
    except Exception:
        return None


def _prose_files(pol: dict):
    import fnmatch
    globs = pol.get("prose_globs") or []
    excl = pol.get("exclude_globs") or []
    files = []
    for g in globs:
        for p in sorted(ROOT.glob(g)):
            rel = p.relative_to(ROOT).as_posix()
            if p.is_file() and not any(fnmatch.fnmatch(p.name, e) for e in excl):
                files.append((rel, p))
    return files


def polish_findings(reg: dict) -> tuple[list, bool]:
    pol = (reg.get("polish") or {})
    if not pol.get("enabled", True):
        return [], False
    sev = pol.get("severity", "medium")
    findings, measured = [], False

    # 1) spellcheck over public prose files
    if (pol.get("spellcheck") or {}).get("enabled", True):
        ssev = (pol.get("spellcheck") or {}).get("severity", sev)
        for rel, path in _prose_files(pol):
            measured = True
            try:
                hits = _spellcheck(path.read_text(errors="ignore"))
            except Exception:
                continue
            for word, fix, ln in hits[:10]:
                findings.append(_finding("polish", rel, ssev, f"misspelling '{word}' → '{fix}' ({rel}:{ln})", "spellcheck"))
        # also lint the public strings baked into repo descriptions / the front door
        seeds = pol.get("seeds_text")
        if seeds and (ROOT / seeds).exists():
            measured = True
            for word, fix, ln in _spellcheck((ROOT / seeds).read_text(errors="ignore"))[:10]:
                findings.append(_finding("polish", seeds, ssev, f"misspelling '{word}' → '{fix}' in {seeds}", "spellcheck"))

    # 2) staleness of bio/positioning prose (git authored age)
    max_days = pol.get("bio_staleness_days")
    import fnmatch
    if max_days:
        for g in pol.get("staleness_globs") or []:
            for p in sorted(ROOT.glob(g)):
                rel = p.relative_to(ROOT).as_posix()
                if not p.is_file() or any(fnmatch.fnmatch(p.name, e) for e in (pol.get("exclude_globs") or [])):
                    continue
                age = _git_mtime_days(rel)
                if age is None:
                    continue
                measured = True
                if age > max_days:
                    findings.append(_finding("polish", rel, sev, f"stale positioning prose: {int(age)}d since last edit (max {max_days})", "staleness"))

    # 2b) voice-judge change detection (Phase 3, hybrid: linters above + LLM-judge ON CHANGE here).
    # The beat cannot reliably call a model synchronously, so — like the experience-judge skill — the
    # SCORING is model-in-the-loop; the beat's job is to detect when a surface's prose changed and no
    # current voice-judgment covers the new content, and queue it. First sighting records a baseline
    # silently (no finding); only a real change with no matching judgment surfaces a review request.
    judge = pol.get("llm_judge") or {}
    if judge.get("enabled") and judge.get("on", "change") == "change":
        import hashlib
        state = _load_json(ROOT / ".limen-private" / "decorum" / "prose-hashes.json") or {}
        judgments = (_load_yaml(ROOT / "institutio" / "observatory" / "decorum-judgments.yaml") or {}).get("judgments") or {}
        new_state = {}
        for rel, path in _prose_files(pol):
            try:
                h = hashlib.sha256(path.read_bytes()).hexdigest()
            except Exception:
                continue
            new_state[rel] = h
            prior = state.get(rel)
            if prior is None or prior == h:
                continue  # baseline or unchanged → quiet
            measured = True
            rows = judgments.get(rel) or []
            if not (rows and rows[-1].get("content_sha256") == h and str(rows[-1].get("verdict")).lower() == "pass"):
                findings.append(_finding("polish", rel, judge.get("severity", "medium"),
                                         f"prose changed since last voice judgment — re-review tone/brand-voice (run the decorum voice-judge on {rel})", "voice-judge"))
        try:
            p = ROOT / ".limen-private" / "decorum" / "prose-hashes.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(new_state, indent=2))
        except Exception:
            pass

    # 3) narrative accuracy — profile claims vs contribution mix (fail-open when the mix is absent)
    nar = pol.get("narrative_accuracy") or {}
    if nar.get("enabled"):
        vv = _load_json(ROOT / "logs" / "vvltvs-organ-state.json") or {}
        if vv.get("mix_present") and vv.get("commit_pct") is not None:
            measured = True
            # a public identity that claims building/engineering while the contribution graph is
            # overwhelmingly commit-churn (little review/design) is a narrative mismatch — the exact
            # AW-PUBLIC-FACE-CONTRIBUTION-BALANCE risk the board already flagged.
            if (vv.get("commit_pct") or 0) >= 80 and (vv.get("review_pct") or 0) < (vv.get("review_floor") or 10):
                findings.append(_finding("polish", "profile", nar.get("severity", sev),
                                         f"narrative mismatch: {vv.get('commit_pct')}% commit-churn, {vv.get('review_pct')}% review (below {vv.get('review_floor')}% floor) — public activity reads as churn, not craft",
                                         "narrative-accuracy"))
    return findings, measured


# ── the sweep ───────────────────────────────────────────────────────────────
def sweep(reg: dict, offline: bool) -> dict:
    depts = reg.get("departments") or {}
    order = ((reg.get("verdict") or {}).get("severity_order")) or ["low", "medium", "high", "critical"]
    floor = ((reg.get("verdict") or {}).get("floor")) or "high"
    value_set = _value_repos(reg)

    findings: list[dict] = []
    measured: dict[str, str] = {}   # dept -> "measured" | "skip"

    for name, cfg in depts.items():
        sev = cfg.get("severity", "medium")
        fs, ms = [], False
        if "command" in cfg:
            if offline and "--no-visibility" not in cfg["command"] and name != "moat":
                ms = False  # doctor mode: don't run network departments
            else:
                out = _run_command(cfg["command"], cfg.get("timeout", 60))
                if name == "moat":
                    fs, ms = dept_moat(out, name, sev, cfg.get("lure_severity", "low"))
        else:
            art = ROOT / cfg["artifact"]
            data = _load_yaml(art) if art.suffix in (".yaml", ".yml") else _load_json(art)
            if name == "experience":
                fs, ms = dept_experience(data, name, sev)
            elif name == "visual":
                fs, ms = dept_visual(data, name, sev)
            elif name == "seo":
                fs, ms = dept_seo(data, name, sev, value_set)
            elif name == "countenance":
                fs, ms = dept_countenance(data, name, sev)
            elif name == "links":
                fs, ms = dept_links(data, name, sev)
        findings.extend(fs)
        measured[name] = "measured" if ms else "skip"

    # the polish lane — the NEW capability: does the public prose read professionally?
    pfs, pms = polish_findings(reg)
    findings.extend(pfs)
    measured["polish"] = "measured" if pms else "skip"

    floor_i = _sev_index(order, floor)
    blocking = [f for f in findings if _sev_index(order, f["severity"]) >= floor_i]
    passed = len(blocking) == 0

    return {
        "schema": SCHEMA,
        "generated_at": _now(),
        "pass": passed,
        "verdict_floor": floor,
        "departments": measured,
        "counts": {
            "findings": len(findings),
            "blocking": len(blocking),
            "measured": sum(1 for v in measured.values() if v == "measured"),
            "skipped": sum(1 for v in measured.values() if v == "skip"),
        },
        "egg_face_findings": sorted(findings, key=lambda f: (-_sev_index(order, f["severity"]), f["lane"], f["surface"])),
    }


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _write_face(verdict: dict) -> None:
    """A minimal public-safe HTML face — the estate's professionalization mirror (siblings organ-health.html)."""
    c = verdict["counts"]
    status = "green — no egg-face" if verdict["pass"] else f"{c['blocking']} blocking finding(s)"
    color = "#137333" if verdict["pass"] else "#c5221f"
    rows = "".join(
        f"<tr><td><code>{_esc(f['severity'])}</code></td><td>{_esc(f['lane'])}</td>"
        f"<td>{_esc(f['surface'])}</td><td>{_esc(f['detail'])}</td></tr>"
        for f in verdict["egg_face_findings"]
    ) or "<tr><td colspan=4>— nothing to answer for —</td></tr>"
    depts = ", ".join(f"{k}:{v}" for k, v in verdict["departments"].items())
    html = f"""<!doctype html><meta charset=utf-8><title>DECORVM — professionalization keeper</title>
<style>body{{font:14px/1.5 -apple-system,system-ui,sans-serif;margin:2rem;color:#202124}}
h1{{font-size:1.3rem}} .badge{{color:{color};font-weight:600}}
table{{border-collapse:collapse;margin-top:1rem;width:100%}} td,th{{border:1px solid #dadce0;padding:.4rem .6rem;text-align:left;vertical-align:top}}
th{{background:#f1f3f4}} .meta{{color:#5f6368}}</style>
<h1>DECORVM — the professionalization keeper</h1>
<p class=badge>{_esc(status)}</p>
<p class=meta>{c['findings']} findings ({c['blocking']} at/above floor '{_esc(verdict['verdict_floor'])}') ·
{c['measured']} departments measured, {c['skipped']} skipped (fail-open) · generated {_esc(verdict['generated_at'])}</p>
<p class=meta>departments: {_esc(depts)}</p>
<table><tr><th>severity</th><th>lane</th><th>surface</th><th>detail</th></tr>{rows}</table>
"""
    try:
        FACE.write_text(html)
    except Exception:
        pass


def _task_id(lane: str, surface: str) -> str:
    """Stable, idempotent task id for a (lane, surface) group — NO date, so a re-run never re-files."""
    import re
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{lane}-{surface}").strip("-").lower()
    return f"DECORUM-{slug}"


def apply_effector(reg: dict, verdict: dict, armed: bool) -> dict:
    """The mentor: fold each open finding into ONE bounded, idempotent ticket per (lane, surface),
    submitted through the tabularius broker (never a direct tasks.yaml write). Dry-run by default;
    mutates only when armed (LIMEN_DECORUM_APPLY=1). Fail-open: if the limen intake stack can't be
    imported, report and skip — the keeper's read-only verdict is unaffected."""
    plan = {"armed": armed, "planned": [], "filed": [], "skipped_existing": 0, "note": None}
    findings = verdict.get("egg_face_findings") or []
    if not findings:
        return plan
    cap = int(os.environ.get("LIMEN_DECORUM_MAX", "8"))
    receipt_repo = (reg.get("effector") or {}).get("receipt_repo", "organvm/limen")
    prio_map = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}

    # group findings by (lane, surface) → one ticket, details listed in context
    groups: dict = {}
    for f in findings:
        groups.setdefault((f["lane"], f["surface"]), []).append(f)

    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "cli" / "src"))
        from limen.intake import contract_fields, github_pr_contract  # noqa: E402
        from limen.io import load_limen_file  # noqa: E402
        from limen.models import Task  # noqa: E402
        from limen.tabularius import submit_task_upsert, pending_task_ids  # noqa: E402
    except Exception as e:  # fail-open — verdict stands, effector just can't file
        plan["note"] = f"limen intake stack unavailable ({e}); tickets not filed"
        return plan

    board = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
    try:
        lf = load_limen_file(board)
        have = {t.id for t in lf.tasks} | set(pending_task_ids(board))
    except Exception as e:
        plan["note"] = f"board unreadable ({e}); tickets not filed"
        return plan

    stamp = datetime.now(timezone.utc).date().isoformat()
    order = ((reg.get("verdict") or {}).get("severity_order")) or ["low", "medium", "high", "critical"]
    for (lane, surface), fs in sorted(groups.items(), key=lambda kv: -max(_sev_index(order, f["severity"]) for f in kv[1])):
        tid = _task_id(lane, surface)
        if tid in have:
            plan["skipped_existing"] += 1
            continue
        if len(plan["planned"]) >= cap:
            break
        top = max(fs, key=lambda f: _sev_index(order, f["severity"]))
        # SEO findings name a real "owner/name" repo; everything else is homed in the keeper's repo.
        repo = surface if (lane == "seo" and "/" in surface) else receipt_repo
        details = " · ".join(f["detail"] for f in fs)
        # A voice-judge finding is not a "go fix the surface" chore — it is a bounded JUDGMENT the
        # fleet runs with the decorum-voice-judge skill. Tier it haiku (per model policy; the skill
        # scores tone/brand-voice and writes a SHA-pinned row to decorum-judgments.yaml, clearing it).
        is_voice = any(f.get("source") == "voice-judge" for f in fs)
        if is_voice:
            title = f"Voice-judge changed prose on {surface}"
            context = (f"DECORVM queued a voice review: {details}. Run the `decorum-voice-judge` skill on {surface} "
                       f"(Haiku-tiered), append a content_sha256-pinned verdict row to "
                       f"institutio/observatory/decorum-judgments.yaml; done ⟺ this finding clears. [decorum {stamp}]")
        else:
            title = f"Fix public egg-face on {surface} ({lane})"
            context = (f"DECORVM found: {details}. Fix at the surface's source and re-run scripts/decorum-keeper.py "
                       f"--sweep; done ⟺ this finding no longer appears in logs/decorum.json. [decorum {stamp}]")
        plan["planned"].append({"id": tid, "repo": repo, "priority": prio_map.get(top["severity"], "medium"), "lane": lane, "surface": surface, "tier": "haiku" if is_voice else None})
        if not armed:
            continue
        try:
            task = Task(
                id=tid,
                title=title,
                repo=repo,
                type="code",
                target_agent="any",
                priority=prio_map.get(top["severity"], "medium"),
                budget_cost=1,
                status="open",
                origin="system_debt",
                horizon="present",
                value_case=f"Remove a professionalization defect a visitor can see on {surface}",
                labels=["decorum", "professionalization", lane, "generated"],
                urls=[],
                context=context,
                claude_tier=("haiku" if is_voice else None),
                **contract_fields(github_pr_contract(repo, tid)),
                depends_on=[],
                created=stamp,
                dispatch_log=[],
            )
            submit_task_upsert(board, task, agent="decorum-keeper", session_id=os.environ.get("LIMEN_SESSION_ID", "decorum-keeper"))
            plan["filed"].append(tid)
        except Exception as e:
            plan.setdefault("errors", []).append(f"{tid}: {e}")
    return plan


def _gh(args: list[str], timeout: int = 45):
    """Shell to gh, returning stdout (str) or None on any failure — fail-open, never raises."""
    try:
        p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else None
    except Exception:
        return None


_ISSUE_MARKER = "decorum"  # body carries <!-- decorum:<finding-id> --> ; identity is the marker, not the title


def mirror_issues(reg: dict, verdict: dict, armed: bool) -> dict:
    """The self-closing sink (github-native process organ): mirror each open finding at/above the
    issue-floor to a `decorum`-labelled GitHub issue, and AUTO-CLOSE any decorum issue whose finding
    has cleared. A human who closes an issue while the finding still stands is a VETO — never reopened.
    This is what makes arming safe: tracking closes itself, so no dangling item accrues. Dry-run by
    default; mutates GitHub only when LIMEN_DECORUM_ISSUES_APPLY=1 arms it. Never sends, never deletes."""
    import re
    eff = reg.get("effector") or {}
    plan = {"armed": armed, "repo": None, "created": [], "closed": [], "kept": 0, "vetoed": [], "note": None}
    repo = eff.get("receipt_repo", "organvm/limen")
    plan["repo"] = repo
    order = ((reg.get("verdict") or {}).get("severity_order")) or ["low", "medium", "high", "critical"]
    floor = eff.get("issue_floor", "medium")
    floor_i = _sev_index(order, floor)
    findings = [f for f in (verdict.get("egg_face_findings") or []) if _sev_index(order, f["severity"]) >= floor_i]
    live = {f["id"]: f for f in findings}

    # read existing decorum issues via REST (search index lags; REST is idempotent right after create)
    raw = _gh(["api", "--paginate", f"repos/{repo}/issues?labels={_ISSUE_MARKER}&state=all&per_page=100"])
    if raw is None:
        plan["note"] = "gh unavailable or repo unreadable; issue mirror skipped (fail-open)"
        return plan
    try:
        rows = json.loads(raw) if raw.strip().startswith("[") else [json.loads(x) for x in raw.splitlines() if x.strip()]
        # --paginate concatenates arrays; normalise
        if raw.count("[") > 1:
            rows = []
            for chunk in re.findall(r"\[.*?\]", raw, re.S):
                try:
                    rows.extend(json.loads(chunk))
                except Exception:
                    pass
    except Exception as e:
        plan["note"] = f"could not parse existing issues ({e}); mirror skipped"
        return plan
    mrx = re.compile(rf"<!--\s*{_ISSUE_MARKER}:([^\s>]+)\s*-->")
    existing: dict[str, dict] = {}
    for it in rows:
        if "pull_request" in it:  # issues API returns PRs too
            continue
        m = mrx.search(it.get("body") or "")
        if m:
            existing[m.group(1)] = {"number": it["number"], "state": it["state"].upper()}

    cap = int(os.environ.get("LIMEN_DECORUM_MAX", "8"))
    # CREATE — a live finding with no issue
    for fid, f in sorted(live.items(), key=lambda kv: -_sev_index(order, kv[1]["severity"])):
        if fid in existing:
            plan["kept"] += 1
            continue
        if len(plan["created"]) >= cap:
            break
        plan["created"].append(fid)
        if not armed:
            continue
        body = (f"**DECORVM — professionalization keeper**\n\n"
                f"- **surface:** `{f['surface']}`\n- **lane:** {f['lane']}\n- **severity:** {f['severity']}\n\n"
                f"{f['detail']}\n\n"
                f"Fix at the surface's source, then re-run `scripts/decorum-keeper.py --sweep`. "
                f"This issue **auto-closes** when the finding clears from `logs/decorum.json`. "
                f"Closing it by hand while the finding still stands is a veto (it will not reopen).\n\n"
                f"<!-- {_ISSUE_MARKER}:{fid} -->")
        _mk_body = ROOT / ".limen-private" / "decorum" / f"issue-{re.sub(r'[^A-Za-z0-9]+','-',fid)}.md"
        try:
            _mk_body.parent.mkdir(parents=True, exist_ok=True)
            _mk_body.write_text(body)
            _gh(["issue", "create", "--repo", repo, "--label", _ISSUE_MARKER,
                 "--title", f"decorum: {f['lane']} egg-face on {f['surface']}", "--body-file", str(_mk_body)])
        except Exception as e:
            plan.setdefault("errors", []).append(f"create {fid}: {e}")

    # CLOSE-ON-CLEAR — an OPEN decorum issue whose finding is gone; VETO — CLOSED while finding stands
    for fid, meta in existing.items():
        if fid in live:
            if meta["state"] == "CLOSED":
                plan["vetoed"].append(fid)  # human closed it though it still stands — respect, never reopen
            continue
        if meta["state"] == "OPEN":
            plan["closed"].append(fid)
            if armed:
                _gh(["issue", "close", str(meta["number"]), "--repo", repo, "--comment",
                     f"Finding `{fid}` has cleared from `logs/decorum.json` — the surface no longer carries this "
                     "egg-face. Auto-closed by scripts/decorum-keeper.py."])
    return plan


def recurrence_precedents(reg: dict, verdict: dict, armed: bool) -> dict:
    """The literal 'ever' ratchet: a finding CLASS that recurs after being cleared (fixed, then broke
    again) — or persists across many sweeps — is not a one-off. It earns a `recurring_friction`
    precedent in censor/precedents.jsonl so the correction escalates from 'fix it again' to 'prevent
    the class structurally' (a generator fix, a gate). State lives in .limen-private (per-machine);
    the precedent is the durable, committed record. Writes only when armed."""
    eff = reg.get("effector") or {}
    thresh = int(eff.get("recurrence_sweeps", 4))
    plan = {"armed": armed, "escalated": [], "note": None}
    state_path = ROOT / ".limen-private" / "decorum" / "recurrence.json"
    state = _load_json(state_path) or {}
    prec_path = ROOT / "censor" / "precedents.jsonl"
    existing_prec = set()
    try:
        for line in prec_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    existing_prec.add(json.loads(line).get("id"))
                except Exception:
                    pass
    except Exception:
        pass

    live_ids = {f["id"] for f in (verdict.get("egg_face_findings") or [])}
    detail_by_id = {f["id"]: f for f in (verdict.get("egg_face_findings") or [])}
    stamp = datetime.now(timezone.utc).date().isoformat()
    new_state = dict(state)
    to_escalate = []

    # every id ever seen: update sweeps/cleared bookkeeping
    for fid in set(state) | live_ids:
        rec = dict(new_state.get(fid) or {"first_seen": stamp, "sweeps": 0, "cleared": 0, "recurred": False})
        if fid in live_ids:
            if rec.get("was_clear"):          # present now, was clear last sweep → recurrence
                rec["recurred"] = True
                rec["cleared"] = rec.get("cleared", 0) + 1
            rec["sweeps"] = rec.get("sweeps", 0) + 1
            rec["was_clear"] = False
        else:
            rec["was_clear"] = True
        new_state[fid] = rec
        # escalation predicate: recurred-after-clear OR persisted past the sweep threshold
        if (rec.get("recurred") or rec.get("sweeps", 0) >= thresh):
            pid = f"PREC-{stamp}-decorum-{fid}".replace(":", "-").replace("/", "-").lower()
            if pid not in existing_prec:
                to_escalate.append((pid, fid, rec))

    for pid, fid, rec in to_escalate:
        f = detail_by_id.get(fid, {})
        plan["escalated"].append(pid)
        if not armed:
            continue
        prec = {
            "id": pid,
            "ts": stamp,
            "type": "recurring_friction",
            "subject": f"recurring public egg-face: {fid}",
            "outcome": "open",
            "reversible": "reversible",
            "action": (f"DECORVM finding {fid} recurred/persisted (sweeps={rec.get('sweeps')}, "
                       f"recurred={rec.get('recurred')}): {f.get('detail','')}. Escalate from one-off fix to STRUCTURAL "
                       f"prevention — a generator fix or a check-decorum gate rung so the class cannot return."),
            "authorised_by": "scripts/decorum-keeper.py recurrence ratchet (decorum-surfaces.yaml effector.recurrence_sweeps)",
            "review": "empirical close = the finding ages out of logs/decorum.json AND a structural guard exists (gate/generator).",
        }
        try:
            prec_path.parent.mkdir(parents=True, exist_ok=True)
            with open(prec_path, "a") as fh:
                fh.write(json.dumps(prec) + "\n")
        except Exception as e:
            plan.setdefault("errors", []).append(f"{pid}: {e}")

    if armed:
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(new_state, indent=2))
        except Exception:
            pass
    return plan


def _stamp_voice() -> None:
    try:
        VOICE.parent.mkdir(parents=True, exist_ok=True)
        VOICE.write_text(_now() + "\n")
    except Exception:
        pass


def doctor(reg: dict) -> int:
    """Offline validation: registry present, well-formed, every department addressable."""
    problems = []
    if not isinstance(reg, dict) or reg.get("schema_version") != 1:
        problems.append("registry missing or schema_version != 1")
    depts = reg.get("departments") or {}
    if not depts:
        problems.append("no departments declared")
    for name, cfg in depts.items():
        if "artifact" not in cfg and "command" not in cfg:
            problems.append(f"department '{name}' has neither artifact nor command")
        if "severity" not in cfg:
            problems.append(f"department '{name}' missing severity")
    order = ((reg.get("verdict") or {}).get("severity_order")) or []
    floor = ((reg.get("verdict") or {}).get("floor"))
    if floor not in order:
        problems.append(f"verdict.floor '{floor}' not in severity_order")
    if problems:
        print("DECORVM doctor: FAIL")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print(f"DECORVM doctor: OK — {len(depts)} departments, floor={floor}")
    return 0


def _print_summary(verdict: dict) -> None:
    c = verdict["counts"]
    mark = "✓ green — no egg-face" if verdict["pass"] else f"✗ {c['blocking']} blocking finding(s)"
    print(f"DECORVM — professionalization keeper: {mark}")
    print(f"  departments: {c['measured']} measured, {c['skipped']} skipped (fail-open)")
    print(f"  findings: {c['findings']} total, {c['blocking']} at/above floor '{verdict['verdict_floor']}'")
    for f in verdict["egg_face_findings"][:20]:
        print(f"    [{f['severity']:<8}] {f['lane']}/{f['surface']}: {f['detail']}")
    extra = len(verdict["egg_face_findings"]) - 20
    if extra > 0:
        print(f"    … +{extra} more (see {OUT})")
    plan = verdict.get("effector") or {}
    if plan.get("note"):
        print(f"  effector: {plan['note']}")
    elif plan.get("planned"):
        if plan.get("armed"):
            print(f"  effector: filed {len(plan.get('filed', []))} ticket(s), {plan['skipped_existing']} already on board")
        else:
            print(f"  effector: DRY-RUN — would file {len(plan['planned'])} ticket(s) ({plan['skipped_existing']} already on board); arm with LIMEN_DECORUM_APPLY=1 --apply")
        for p in plan["planned"][:8]:
            tier = f" ({p['tier']})" if p.get("tier") else ""
            print(f"      → {p['id']} [{p['priority']}] {p['repo']}{tier}")
    iss = verdict.get("issues") or {}
    if iss.get("note"):
        print(f"  issues: {iss['note']}")
    elif iss.get("created") or iss.get("closed"):
        verb = "mirrored" if iss.get("armed") else "DRY-RUN would mirror"
        print(f"  issues: {verb} → {len(iss.get('created', []))} new, {len(iss.get('closed', []))} auto-closed, "
              f"{iss.get('kept', 0)} kept, {len(iss.get('vetoed', []))} vetoed (repo {iss.get('repo')}); "
              f"arm with LIMEN_DECORUM_ISSUES_APPLY=1")
    rec = verdict.get("recurrence") or {}
    if rec.get("escalated"):
        verb = "filed" if rec.get("armed") else "DRY-RUN would file"
        print(f"  recurrence: {verb} {len(rec['escalated'])} recurring_friction precedent(s) — a class recurred/persisted (the 'ever' ratchet)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sweep", action="store_true", help="federate every department → logs/decorum.json (default)")
    ap.add_argument("--doctor", action="store_true", help="offline: validate the registry + schema, run no network")
    ap.add_argument("--json", action="store_true", help="emit the machine verdict to stdout instead of a summary")
    ap.add_argument("--apply", action="store_true", help="file a ticket per finding (armed only when LIMEN_DECORUM_APPLY=1; dry-run otherwise)")
    args = ap.parse_args()

    reg = _load_yaml(REGISTRY)
    if reg is None:
        print(f"DECORVM: registry unreadable at {REGISTRY}", file=sys.stderr)
        return 1

    if args.doctor:
        return doctor(reg)

    verdict = sweep(reg, offline=False)

    # the effector (mentor) — dry-run plan by default; mutates only when the valve is armed.
    # THREE sinks, each its own valve: board tasks (dispatchable work), GitHub issues (self-closing
    # tracked-to-closure findings — the primary durable sink), and recurrence precedents (the 'ever' ratchet).
    armed = args.apply and os.environ.get("LIMEN_DECORUM_APPLY") == "1"
    plan = apply_effector(reg, verdict, armed)
    verdict["effector"] = plan
    issues_armed = args.apply and os.environ.get("LIMEN_DECORUM_ISSUES_APPLY") == "1"
    verdict["issues"] = mirror_issues(reg, verdict, issues_armed)
    verdict["recurrence"] = recurrence_precedents(reg, verdict, armed)
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(verdict, indent=2) + "\n")
    except Exception as e:
        print(f"DECORVM: could not write {OUT}: {e}", file=sys.stderr)
    _write_face(verdict)
    _stamp_voice()

    if args.json:
        print(json.dumps(verdict, indent=2))
    else:
        _print_summary(verdict)

    return 0 if verdict["pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
