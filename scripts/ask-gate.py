#!/usr/bin/env python3
"""ask-gate.py — intake decomposition: one done-predicate per task, or split it.

The gap this closes (retro 2026-06-24→07-08, gap model + evolution 3): 1,779
deduplicated operator asks were audited against outcomes, and the drift
predictors were *structural properties of the ask itself*:

  converges                          drifts
  ─────────────────────────────      ──────────────────────────────────────
  reducible to ONE done-predicate    multi-goal bundles
  single bounded objective           narrative success ("run all night",
  names a concrete repo/owner          "make it shareable", "world-class")
  survives the session/vendor seam   owner-less asks / armed-behavior
                                       deliverables with no artifact gate

The five most-escalated ask themes (creative 101, autonomy 84, life-routing 48,
buried-lead triage 28, permission prompts) are exactly the drifted ones. The cure
is structural — gate the ASK at intake — not exhortative.

What this organ does (mechanical checks, never vibes):
  PREDICATE   the task names an executable check (a `Predicate:` line, a
              done.sh / --check / pytest / curl invocation, or a script path).
  BOUNDED     not a multi-goal bundle (enumerated (1)…(n) sub-asks past the
              threshold, or many conjoined imperatives).
  OWNED       a concrete repo and a target agent.
  OUTCOME     no narrative-success vocabulary standing in for a check; an
              armed-behavior deliverable (deploy/publish/send/env-arm) must
              cite its artifact gate (ship-gate / armed-valve / a URL probe).

Verdict per task: PASS / SPLIT (fails PREDICATE or BOUNDED — decompose into
children, each with predicate+owner) / ADVISE (soft findings only).

Modes:
  --audit [--since N]   scan open board tasks created in the last N days
                        (default 7); --check exits 1 on any SPLIT verdict.
  --task-file F.json    gate ONE proposed task (a keeper-ticket `patch` shape);
                        --check exits 1 unless PASS/ADVISE. Generators and the
                        keeper call this BEFORE a ticket is filed.
  --explain ID          print the full finding set for one board task.

Observable-before-autonomous (the LIMEN_CENSOR_APPLY constitutional pattern):
the beat runs the audit advisory (report + stamp, fail-open); hard enforcement
at the keeper seam arrives only after the predicate proves itself in the log.
Stamps logs/ask-gate.json.
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))
sys.path.insert(0, str(SCRIPT_ROOT / "cli" / "src"))

from limen.intake import boundedness_finding, is_executable_predicate  # noqa: E402

PREDICATE_RE = re.compile(
    r"(?ix)\b(done\.sh | predicate\s*: | --check\b | exit\s+0 | pytest | \.test\.sh"
    r" | verify-whole\.sh | merge-policy\.sh | curl\s+-s | npm\s+(test|run\s+check)"
    r" | ship-gate | armed-valve-audit | done\s*=\s*"
    # the fleet's own outcome idioms — machine-emitted heal/packet tasks state their
    # check in prose; these are real predicates (verifiable by gh/CI state), and a
    # gate that flags 400 of them is noise, which is a dead organ
    r" | stop\s+condition\s*: | \bMERGEABLE\b"
    r" | confirm(s|ed)?\b[^.]{0,80}\bgreen | checks?\s+go(es)?\s+green"
    r" | green\s+CI | returns?\s+200 | exits?\s+non-?zero | exit\s+1\b)"
)
NARRATIVE_RE = re.compile(
    r"(?i)\b(all\s+night|overnight\s+and\s+beyond|make\s+it\s+(excellent|shareable|beautiful|world-class)"
    r"|world-class|rival(ing|s)?\s|keep\s+going\s+forever|as\s+long\s+as\s+possible"
    r"|everything\s+(works|done)|polish\s+it|make\s+us\s+proud)"
)
ARMED_BEHAVIOR_RE = re.compile(
    r"(?i)\b(deploy|publish|post\s+(it|the)|send\s|go-?live|arm(ed)?\s+the|env\s+flag|receive\s+address)"
)
ARTIFACT_GATE_RE = re.compile(
    r"(?i)(ship-gate|armed-valve|https?://|200-?url|posted\s+link|booked\s+.*\bid\b|artifact)"
)
PLACEHOLDER_REPOS = {"", "tbd", "unknown", "none"}


def _text(task: dict) -> str:
    return " ".join(str(task.get(k) or "") for k in ("title", "description", "context"))


# An ask already owned by a registry must be DERIVED from that owner, never re-asked
# (PREC-2026-07-08-ask-already-decided; [[decisions-owned-by-organ-not-chat]],
# [[never-need-him-to-speak-again]]). Detection is high-precision so a benign build task is never
# suppressed: explicit lever/precedent IDs match anywhere (membership-checked against the real
# registry); organ/pillar names match only when the ask is phrased as a decision-to-be-made.
_LEVER_ID_RE = re.compile(r"\bL-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")
_PREC_ID_RE = re.compile(r"\bPREC-\d{4}-\d{2}-\d{2}-[a-z0-9-]+\b", re.IGNORECASE)
DECISION_SHAPE_RE = re.compile(
    r"(?i)(\?|\b(should|which|whether|decide|choose|pick|either)\b|\bvs\.?\b|\b\w+\s+or\s+\w+\b)"
)
_REGISTRY_CACHE = None


def _registry_decisions():
    """(cached, fail-open) the tokens that mark an already-owned decision: lever ids
    (his-hand-levers.json), precedent ids (censor/precedents.jsonl), and organ/pillar names
    (organ-ladder.json). A missing/torn registry contributes nothing — never crashes the gate."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    ids: set[str] = set()
    names: set[str] = set()
    try:
        d = json.loads((ROOT / "his-hand-levers.json").read_text())
        for lev in (d.get("levers") or []) if isinstance(d, dict) else []:
            if isinstance(lev, dict) and lev.get("id"):
                ids.add(str(lev["id"]))
    except Exception:
        pass
    try:
        for line in (ROOT / "censor" / "precedents.jsonl").read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pid = json.loads(line).get("id")
            except Exception:
                pid = None
            if pid:
                ids.add(str(pid))
    except Exception:
        pass
    try:
        ol = json.loads((ROOT / "organ-ladder.json").read_text())
        organs = ol.get("organs") if isinstance(ol, dict) else ol
        for o in organs or []:
            if isinstance(o, dict):
                for key in ("pillar", "organ"):
                    v = str(o.get(key) or "").strip()
                    if len(v) >= 4:
                        names.add(v.lower())
    except Exception:
        pass
    _REGISTRY_CACHE = (ids, names)
    return _REGISTRY_CACHE


def _already_decided(task: dict):
    """(source, ref) if this ask is already owned by a registry → verdict DERIVE (derive from the
    owner, don't surface). Membership-checked so a stray 'L-…'-looking string can't false-fire."""
    text = _text(task)
    ids, names = _registry_decisions()
    for m in _LEVER_ID_RE.finditer(text):
        if m.group(0) in ids:
            return ("his-hand-lever", m.group(0))
    for m in _PREC_ID_RE.finditer(text):
        if m.group(0) in ids:
            return ("precedent", m.group(0))
    if DECISION_SHAPE_RE.search(text):
        low = text.lower()
        for nm in names:
            if re.search(rf"\b{re.escape(nm)}\b", low):
                return ("organ-ladder", nm)
    return None


def assess(task: dict) -> dict:
    """Mechanical drift-predictor findings for one task dict (keeper patch shape)."""
    decided = _already_decided(task)
    if decided:
        src, ref = decided
        return dict(id=task.get("id", "?"), verdict="DERIVE",
                    findings=[f"DERIVE: already owned by {src}:{ref} — derive from the registry, "
                              "don't re-ask (PREC-2026-07-08-ask-already-decided)"])
    text = _text(task)
    findings = []

    if not is_executable_predicate(task.get("predicate")) and not PREDICATE_RE.search(text):
        findings.append(("PREDICATE", "no executable done-check named — add a `Predicate:` line "
                                      "(a script/command whose exit 0 ⟺ done)"))

    bundle = boundedness_finding(task)
    if bundle:
        findings.append(("BOUNDED", f"{bundle} — split into children, one predicate each"))

    if str(task.get("repo", "")).strip().lower() in PLACEHOLDER_REPOS:
        findings.append(("OWNED", "no concrete repo owner"))
    if not str(task.get("target_agent", "")).strip():
        findings.append(("OWNED", "no target agent"))

    if NARRATIVE_RE.search(text):
        findings.append(("OUTCOME", f"narrative success criterion ({NARRATIVE_RE.search(text).group(0)!r}) "
                                    "standing in for a check"))
    if ARMED_BEHAVIOR_RE.search(text) and not ARTIFACT_GATE_RE.search(text):
        findings.append(("OUTCOME", "armed-behavior deliverable with no artifact gate cited "
                                    "(ship-gate / armed-valve / a URL the effect must serve)"))

    hard = {k for k, _ in findings} & {"PREDICATE", "BOUNDED"}
    verdict = "SPLIT" if hard else ("ADVISE" if findings else "PASS")
    return dict(id=task.get("id", "?"), verdict=verdict,
                findings=[f"{k}: {msg}" for k, msg in findings])


def split_skeleton(task: dict, row: dict) -> list[dict]:
    """A decomposition template for a SPLIT verdict — children the filer edits, not prose."""
    base = str(task.get("id", "ASK"))
    return [
        dict(id=f"{base}-C{i}",
             title=f"(child {i} of {base} — one bounded objective)",
             description="One objective. Predicate: <script/command; exit 0 ⟺ done>.",
             repo=task.get("repo") or "<owner/repo>",
             target_agent=task.get("target_agent") or "any",
             context=f"split by ask-gate from {base}: {'; '.join(row['findings'])}")
        for i in (1, 2)
    ]


def audit_board(tasks, since_days: int):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=since_days)
    rows = []
    for t in tasks:
        if t.status != "open":
            continue
        try:
            created = datetime.datetime.fromisoformat(str(t.created).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=datetime.timezone.utc)
            if created < cutoff:
                continue
        except (ValueError, TypeError):
            continue  # undated tasks belong to the historical board, not the intake window
        rows.append(assess(t.model_dump(mode="json")))
    return rows


def stamp(rows, path):
    payload = dict(
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        split=[r["id"] for r in rows if r["verdict"] == "SPLIT"],
        advise=[r["id"] for r in rows if r["verdict"] == "ADVISE"],
        derive=[r["id"] for r in rows if r["verdict"] == "DERIVE"],
        passed=sum(1 for r in rows if r["verdict"] == "PASS"),
        rows=rows,
    )
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=1) + "\n")
    except OSError as exc:
        print(f"  (stamp skipped: {exc})", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Intake gate: one done-predicate per task, or split it.")
    ap.add_argument("--check", action="store_true", help="exit 1 on SPLIT verdicts")
    ap.add_argument("--audit", action="store_true", help="scan open board tasks in the intake window")
    ap.add_argument("--since", type=int, default=7, help="intake window in days (with --audit)")
    ap.add_argument("--task-file", help="gate ONE proposed task (JSON, keeper-ticket patch shape)")
    ap.add_argument("--explain", metavar="ID", help="full finding set for one board task")
    ap.add_argument("--top", type=int, default=0, help="print at most N non-PASS rows (0 = all); full detail always lands in the stamp")
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    ap.add_argument("--stamp", default=str(ROOT / "logs" / "ask-gate.json"))
    args = ap.parse_args(argv)

    if args.task_file:
        task = json.loads(Path(args.task_file).read_text())
        row = assess(task)
        print(json.dumps(dict(row, children=split_skeleton(task, row) if row["verdict"] == "SPLIT" else []),
                         indent=1))
        return 1 if (args.check and row["verdict"] == "SPLIT") else 0

    from limen.io import load_limen_file  # noqa: PLC0415 — board modes only

    lf = load_limen_file(Path(args.tasks))

    if args.explain:
        t = next((t for t in lf.tasks if t.id == args.explain), None)
        if t is None:
            print(f"no such task: {args.explain}", file=sys.stderr)
            return 2
        print(json.dumps(assess(t.model_dump(mode="json")), indent=1))
        return 0

    rows = audit_board(lf.tasks, args.since)
    stamp(rows, args.stamp)
    shown = 0
    for r in rows:
        if r["verdict"] != "PASS":
            if args.top and shown >= args.top:
                print(f"  … (+{sum(1 for x in rows if x['verdict'] != 'PASS') - shown} more in the stamp)")
                break
            print(f"  {r['verdict']:<7} {r['id']}: " + "; ".join(r["findings"]))
            shown += 1
    split = [r for r in rows if r["verdict"] == "SPLIT"]
    print(f"ask-gate: {len(rows)} intake-window tasks — {len(rows) - len(split)} pass/advise, {len(split)} need a split")
    if args.check and split:
        print("ask-gate: RED — an ask entered the board without a done-predicate or bounded scope; "
              "split it into predicate-shaped children", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
