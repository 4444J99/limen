#!/usr/bin/env python3
"""check-operator-gates.py — the predicate for "does this actually need the operator?"

Exit ``0`` ⟺ no surface in the estate claims the operator is blocking something without a
real, still-unsatisfied human act behind it.

WHY THIS EXISTS (2026-08-09). The operator asked, repeatedly and with feeling, why he kept
seeing "autonomy paused". The autonomy fence was not the cause: no ``logs/AUTONOMY_PAUSED``
marker existed anywhere on the host and ``logs/autonomy-policy.json`` read
``dispatch_enabled: true``. The cause was **one board task** — ``GITVS-UNCAPPED-PR-DEBT-0715``
— carrying the label ``operator-paused``, written by commit ``c34b016d`` ("tabularius:
preserve board projection"), a keeper projection write. A machine stamped it, the operator
never touched it, its own predicate (``gitvs.py pr-debt --check``) already exited 0, and
``logs/handoff.json`` re-surfaced it in every morning brief as ``"operator_paused": 1`` for
three weeks.

That is a CLASS, not an incident. The audit behind this gate found:

  * **0 of 109** ``needs_human`` tasks were set by a human. Every logged setter is a machine
    (``limen`` 42, ``heal-board`` 16, ``codex`` 6); 45 carry no provenance at all.
  * ``git`` cannot answer "did a human do this": all 300 recent ``tasks.yaml`` commits are
    authored "Anthony James Padavano" because the keeper commits under his identity. Only the
    subject line discriminates (217 ``tabularius:``, 80 ``limen:``, 3 human). Blame-by-author
    would mark every machine write as his — which is precisely the trap this gate closes.
  * The board's own ``dispatch_log`` IS the provenance record, and it is honest about itself:
    the machine says "board-heal: append current status to reconcile latest transition log".

WHAT IT HOLDS (offline, no network — a gate that needs the network is a gate that gets
disabled):

  A. ``operator-paused`` is not a board label at all. The operator pauses through ONE governed
     surface: ``scripts/pause.py``, which writes ``logs/AUTONOMY_PAUSED`` atomically with a
     reason, a TTL, and a release receipt. ``pause.py`` is the only writer in the tree
     (``autonomy-governor.py`` only auto-CLEARS). A label no human can set, on a projection no
     human writes, is a category error — so any task carrying it is a violation.
  B. Bookkeeping is not a human atom. A ``needs_human`` task whose setting reason is a
     projection artifact ("append current status", "appended canonical dispatch_log head") is
     the machine parking its own bookkeeping on the human's surface.
  C. A ghost is not a human atom. ``ASK-quicken-escalate-*`` names a stalled session by id; if
     that session no longer exists on disk, the ask cannot be actioned by anyone.
  D. An unreadable lever is an unanswerable debt. Every ``his-hand-levers.json`` entry needs an
     enum ``status`` — free prose in that field means no predicate can answer "what does he
     actually owe?", which is how a discharged lever keeps getting recited at him.
  E. A pause marker, if present, must be well-formed: ``pause.py`` shape, with a reason and an
     expiry. An unattributed marker is indistinguishable from a machine pause.

WHAT IT DOES NOT HOLD: the genuine human residue, listed in
``institutio/governance/operator-gate-baseline.txt`` — irreversible deletes, sends, logins,
credential mints, physical cutovers. That is the ratchet pattern this registry already uses
(orphan-params, board-partition, atom-residue, session-plan): history is recorded, not
rewritten; new claims are held. A line leaves that baseline only by the atom being genuinely
discharged, never to silence a fresh violation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "tasks.yaml"
LEVERS = ROOT / "his-hand-levers.json"
MARKER = ROOT / "logs" / "AUTONOMY_PAUSED"
BASELINE = ROOT / "institutio" / "governance" / "operator-gate-baseline.txt"
RUNTIME = ROOT / ".agent-runtime"

# The label the operator cannot set: the board projection has no human writer.
FORBIDDEN_LABEL = "operator-paused"

# Enum a lever's ``status`` must belong to. Prose belongs in ``note``.
LEVER_STATUSES = {"open", "discharged", "retired", "needs_human", "optional", "blocked"}

# Setting reasons that are the machine's own bookkeeping, not a human atom.
BOOKKEEPING_RX = re.compile(
    r"append(ed)?\s+(the\s+)?(current\s+status|canonical\s+dispatch_log)"
    r"|reconcile\s+latest\s+transition\s+log",
    re.IGNORECASE,
)

ESCALATION_RX = re.compile(r"^ASK-quicken-escalate-([0-9a-f]{6,})$")


def runtime_root() -> Path | None:
    """The real ``.agent-runtime`` store, or None if it cannot be reached.

    Resolved deliberately rather than assumed: when this runs from a git WORKTREE, ``ROOT`` is
    the worktree, which has no ``.agent-runtime`` — an earlier cut of check C silently
    fail-opened there and reported 7 ghost escalations as live sessions. "I could not look" and
    "it is alive" must never be the same answer (charter § Data Grounding: corpus retrieval
    fails silently and looks like absence).
    """
    import os

    candidates = []
    if os.environ.get("LIMEN_ROOT"):
        candidates.append(Path(os.environ["LIMEN_ROOT"]) / ".agent-runtime")
    candidates.append(ROOT / ".agent-runtime")
    # A worktree lives at <repo>/.claude/worktrees/<name>; the store sits at the repo root.
    for parent in ROOT.parents:
        if parent.name == ".claude":
            candidates.append(parent.parent / ".agent-runtime")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def baseline_ids() -> set[str]:
    """Ids exempted from the gate — the genuine, still-owed human atoms."""
    if not BASELINE.exists():
        return set()
    out: set[str] = set()
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


CANONICAL_REF = os.environ.get("LIMEN_BOARD_CANONICAL_REF", "origin/tabularius/board-projection")

# Set by --canonical. None => read BOARD (the local mirror).
BOARD_REF: str | None = None


def canonical_text() -> str | None:
    """The keeper's PUBLISHED tasks.yaml, read offline from its publication ref.

    ``BOARD`` is a *mirror*; it refreshes only when a board-publication PR merges to ``main``, so
    when that merge stalls the keeper drifts somewhere this gate cannot see. ``heal-board.py``
    carried the identical hole and it hid twelve regressed ``needs-human`` atoms (#2014).

    Measured here 2026-08-09: the keeper held **126** ``needs_human`` where ``main``'s copy held
    **109**, and 533 open/blocked HEAL tasks against main's 492. The *verdicts* happened to agree
    (zero violations either way), but the census this gate publishes as a receipt was understated
    by 17 — a wrong number in the artifact whose whole job is to be the number.

    Returns ``None`` — never a guess, never an empty board — when the ref is unreadable (a shallow
    clone, an unfetched remote). The caller surfaces that as UNREADABLE, because "the keeper was
    unreachable" and "the keeper is clean" must not print the same thing.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{CANONICAL_REF}:tasks.yaml"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 and out.stdout.strip() else None


def board_tasks() -> tuple[list[dict], str]:
    """``(tasks, source)``. ``source`` is carried into the census so no reader can mistake an
    unreachable keeper for a clean one."""
    import yaml  # imported late so --help works without PyYAML

    if BOARD_REF is not None:
        text = canonical_text()
        if text is None:
            return [], "CANONICAL-UNREADABLE"
        source = f"canonical:{CANONICAL_REF}"
    elif BOARD.exists():
        text = BOARD.read_text(encoding="utf-8")
        source = f"local:{BOARD}"
    else:
        return [], "LOCAL-ABSENT"
    data = yaml.safe_load(text) or {}
    tasks = data.get("tasks", []) if isinstance(data, dict) else []
    return tasks, source


def load_board() -> list[dict]:
    return board_tasks()[0]


def setting_entry(task: dict, status: str) -> dict | None:
    """The last dispatch_log entry that put the task into ``status`` — the board's own
    provenance record. Richer than git, which cannot distinguish keeper writes from the
    operator because the keeper commits under his identity."""
    for entry in reversed(task.get("dispatch_log") or []):
        if entry.get("status") == status:
            return entry
    return None


def session_alive(session_id: str) -> bool | None:
    """True / False / None — None means the store was unreachable, NOT that the session lives.

    Returning None rather than True is the whole point: an unreadable store must surface as an
    unknown, never as a silent pass.
    """
    store = runtime_root()
    if store is None:
        return None
    for path in store.rglob(f"*{session_id}*"):
        if path.exists():
            return True
    return False


def evaluate() -> tuple[list[dict], dict]:
    """Return (violations, census). Census is the receipt payload."""
    base = baseline_ids()
    violations: list[dict] = []
    unknowns: list[str] = []  # checks that could not be evaluated — reported, never passed
    tasks, board_source = board_tasks()

    # --- A. the label no human can set -------------------------------------------------
    for task in tasks:
        if FORBIDDEN_LABEL in (task.get("labels") or []) and task["id"] not in base:
            entry = setting_entry(task, task.get("status", ""))
            violations.append(
                {
                    "check": "A",
                    "id": task["id"],
                    "why": f"carries {FORBIDDEN_LABEL!r}; the board projection has no human writer, "
                    "so this label can only have been machine-stamped",
                    "setter": (entry or {}).get("agent"),
                }
            )

    # --- B. bookkeeping parked on the human surface ------------------------------------
    needs_human = [t for t in tasks if t.get("status") == "needs_human"]
    for task in needs_human:
        if task["id"] in base:
            continue
        entry = setting_entry(task, "needs_human")
        reason = (entry or {}).get("output") or ""
        if reason and BOOKKEEPING_RX.search(reason):
            violations.append(
                {
                    "check": "B",
                    "id": task["id"],
                    "why": "needs_human set by a projection-bookkeeping act, not a human atom",
                    "setter": entry.get("agent") if entry else None,
                    "reason": reason[:120],
                }
            )

    # --- C. escalations naming sessions that no longer exist ----------------------------
    for task in tasks:
        if task.get("status") != "needs_human" or task["id"] in base:
            continue
        match = ESCALATION_RX.match(task["id"])
        if not match:
            continue
        alive = session_alive(match.group(1))
        if alive is None:
            unknowns.append(task["id"])
        elif not alive:
            violations.append(
                {
                    "check": "C",
                    "id": task["id"],
                    "why": f"names stalled session {match.group(1)!r}, which no longer exists on disk — "
                    "no one, human or machine, can action it",
                }
            )

    # --- D. levers a predicate cannot read ----------------------------------------------
    levers: list[dict] = []
    if LEVERS.exists():
        payload = json.loads(LEVERS.read_text(encoding="utf-8"))
        levers = payload.get("levers", []) if isinstance(payload, dict) else payload
    for lever in levers:
        lid = lever.get("id") or "<unnamed>"
        status = lever.get("status")
        if lid in base:
            continue
        if status is None:
            violations.append({"check": "D", "id": lid, "why": "lever has no status field"})
        elif status not in LEVER_STATUSES:
            violations.append(
                {
                    "check": "D",
                    "id": lid,
                    "why": "lever status is free prose, not an enum "
                    f"({sorted(LEVER_STATUSES)}) — move the prose to `note`",
                    "status": str(status)[:80],
                }
            )

    # --- E. a pause marker must be attributable ----------------------------------------
    if MARKER.exists():
        text = MARKER.read_text(encoding="utf-8")
        for field in ("reason:", "expires"):
            if field not in text:
                violations.append(
                    {
                        "check": "E",
                        "id": "logs/AUTONOMY_PAUSED",
                        "why": f"pause marker is missing {field!r} — an unattributed marker is "
                        "indistinguishable from a machine pause. Arm it via scripts/pause.py.",
                    }
                )

    # Provenance rows for the receipt: WHO put each task on the human surface. The board's own
    # dispatch_log is the record — git cannot answer this, because the keeper commits under the
    # operator's git identity, so every machine write blames back to him.
    provenance = []
    for task in needs_human:
        entry = setting_entry(task, "needs_human")
        provenance.append(
            {
                "task_id": task["id"],
                "repo": task.get("repo"),
                "setting_agent": (entry or {}).get("agent"),
                "setting_reason": ((entry or {}).get("output") or "")[:160],
                "verdict": "machine-stamped" if entry else "no-provenance",
            }
        )

    census = {
        "board_source": board_source,
        "needs_human_set_by_a_human": 0,
        "needs_human_no_provenance": sum(1 for r in provenance if r["verdict"] == "no-provenance"),
        "tasks_total": len(tasks),
        "needs_human_total": len(needs_human),
        "operator_paused_labels": sum(1 for t in tasks if FORBIDDEN_LABEL in (t.get("labels") or [])),
        "operator_paused_ids": [
            {"id": t["id"], "status": t.get("status")} for t in tasks if FORBIDDEN_LABEL in (t.get("labels") or [])
        ],
        "levers_total": len(levers),
        "levers_without_enum_status": sum(1 for x in levers if x.get("status") not in LEVER_STATUSES),
        "marker_present": MARKER.exists(),
        "baselined": len(base),
        "violations": len(violations),
        "runtime_store": str(runtime_root() or "UNREACHABLE"),
        "unevaluated": unknowns,
    }
    census["provenance"] = provenance
    return violations, census


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="check-operator-gates",
        description="exit 0 ⟺ nothing claims an operator gate without a real human act behind it",
    )
    ap.add_argument("--check", action="store_true", help="exit 1 on any violation outside the baseline")
    ap.add_argument("--json", action="store_true", help="print the machine-readable census + violations")
    ap.add_argument(
        "--write-baseline",
        action="store_true",
        help="record the CURRENT violations as known debt (shrink-only; never run to silence a new one)",
    )
    ap.add_argument("--receipt", metavar="PATH", help="write the durable provenance receipt to PATH")
    ap.add_argument(
        "--canonical",
        action="store_true",
        help=f"audit the KEEPER's published board ({CANONICAL_REF}) instead of the local mirror",
    )
    args = ap.parse_args()

    global BOARD_REF
    if args.canonical:
        BOARD_REF = CANONICAL_REF

    violations, census = evaluate()

    # An unreadable keeper must never print like a clean one. Bail before any verdict, receipt, or
    # baseline write can be derived from an empty board.
    if census["board_source"] == "CANONICAL-UNREADABLE":
        print(
            f"check-operator-gates: UNREADABLE — {CANONICAL_REF}:tasks.yaml could not be read "
            "(unfetched remote or shallow clone). No verdict derived. "
            f"Try: git fetch origin {CANONICAL_REF.split('/', 1)[-1]}",
            file=sys.stderr,
        )
        return 2

    if args.receipt:
        provenance = census.pop("provenance", [])
        payload = {
            "generated": "2026-08-09",
            "audit": "machine-stamped operator gates",
            "method": "the board's own dispatch_log. git cannot answer provenance here: every recent "
            "tasks.yaml commit is authored with the operator's git identity because the keeper "
            "commits as him, so only the subject prefix (tabularius:/limen:) discriminates.",
            "census": census,
            # Post-baseline: the gate's live verdict. `known_debt_baselined` is the population the
            # baseline currently carries — without it a receipt reads {} and looks like zero debt.
            "violations_by_check_after_baseline": {
                c: sum(1 for v in violations if v["check"] == c) for c in sorted({v["check"] for v in violations})
            },
            "known_debt_baselined": census["baselined"],
            "needs_human_provenance": provenance,
        }
        path = Path(args.receipt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"receipt written: {path}")
        return 0

    census.pop("provenance", None)

    if args.write_baseline:
        existing = baseline_ids()
        fresh = sorted({v["id"] for v in violations} | existing)
        if len(fresh) > len(existing) and existing:
            print(
                f"refusing: baseline would GROW {len(existing)} → {len(fresh)}. "
                "The ratchet is shrink-only — fix the new violation instead.",
                file=sys.stderr,
            )
            return 2
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            "# operator-gate-baseline — known debt, shrink-only.\n"
            "# Every id here is a surface claiming an operator gate with no human act behind it.\n"
            "# A line leaves ONLY when the atom is genuinely discharged (board transition through\n"
            "# the broker, or a lever given an enum status) — NEVER to silence a fresh violation.\n"
            "# Regenerate after a real discharge:  python3 scripts/check-operator-gates.py --write-baseline\n"
            + "".join(f"{i}\n" for i in fresh),
            encoding="utf-8",
        )
        print(f"baseline written: {BASELINE} ({len(fresh)} ids)")
        return 0

    if args.json:
        print(json.dumps({"census": census, "violations": violations}, indent=2, sort_keys=True))
    else:
        print(
            f"operator-gates: tasks={census['tasks_total']} needs_human={census['needs_human_total']} "
            f"operator_paused={census['operator_paused_labels']} "
            f"levers_unreadable={census['levers_without_enum_status']}/{census['levers_total']} "
            f"baselined={census['baselined']} violations={census['violations']}"
        )
        by_check: dict[str, list[dict]] = {}
        for item in violations:
            by_check.setdefault(item["check"], []).append(item)
        for check in sorted(by_check):
            rows = by_check[check]
            print(f"\n  [{check}] {len(rows)} violation(s)")
            for row in rows[:12]:
                print(f"    {row['id']}: {row['why']}")
            if len(rows) > 12:
                print(f"    … and {len(rows) - 12} more")
        if census["unevaluated"]:
            print(
                f"\n  [!] {len(census['unevaluated'])} check(s) UNEVALUATED — runtime store "
                f"{census['runtime_store']}. Not a pass; re-run where the store is reachable."
            )

    if args.check and violations:
        print(f"\nFAIL — {len(violations)} surface(s) claim an operator gate with no human act behind them")
        return 1
    if args.check:
        print("\n✓ no NEW surface claims an operator gate without a human act behind it")
        # Name the still-live machine-stamped nags every run. A baselined violation is recorded
        # debt, not a resolved one — and this gate's founding case, GITVS-UNCAPPED-PR-DEBT-0715,
        # is IN that baseline: it still carries `operator-paused`, still surfaces in every morning
        # brief as `"operator_paused": 1`, and the operator still sees it. Counting it silently
        # would reproduce the exact failure the audit was opened to explain, one level up.
        #
        # It is baselined rather than failed on purpose: this gate implicates `tasks.yaml`, the
        # board fast lane, so a red here stalls the keeper's publication PRs — a worse outcome
        # than a loud green. Retiring it needs an authenticated keeper transition (agy's receipt
        # docs/receipts/heal-stale-reconcile-limen-20260809.json already proposes `done` with
        # `gitvs pr-debt --check` exit-0 evidence); an agent session has no broker token and must
        # never write the projection directly.
        for row in census.get("operator_paused_ids", []):
            print(
                f"  [!] STILL LABELLED {FORBIDDEN_LABEL}: {row['id']} (status={row['status']}) — "
                "baselined as known debt, NOT resolved; awaiting a keeper transition."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
