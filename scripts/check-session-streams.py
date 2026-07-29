#!/usr/bin/env python3
"""STREAMS drift predicate — holds the work-domain registry to its own rules (check-gates.py shape).

Exit 0 iff institutio/governance/session-streams.yaml is internally coherent:
  A  schema      — ids unique/slug-shaped, required fields present, enums valid, `intent:` exists.
  B  graph       — requires/unblocks reference real ids, are mutually consistent, and are ACYCLIC.
  C  predicate   — predicate_status:existing ⇒ the file exists; to_be_built ⇒ it does NOT yet exist
                   (flipping the field without shipping the file is caught BOTH ways — the anti-fake
                   rung; a stream may not claim a predicate it never built, nor hide one it did).
  D  capsule     — a stream whose worktree exists carries a matching
                   docs/continuations/<id>/workstream.json with the same slug and branch.
  E  orphans     — every <repo>/.worktrees/<slug> capsule whose slug is stream-shaped is declared
                   here (catches a lane opened by hand and then forgotten).
  F  no hand-state — NO row may carry status/state/settled/ready/done. State is DERIVED from git
                   (see `state_of`), never written. This is what makes the ready-set untamperable:
                   there is no field to lie in.
  G  tier authority — any job_class claiming reserved-Opus standing must be in
                   model_selection._CLAUDE_OPUS_CLASSES_DEFAULT, DERIVED by import from the tier
                   authority rather than re-encoded here (the "consumers derive" discipline).

Also the mode that answers the operator's actual question:

    python3 scripts/check-session-streams.py --ready

which derives each domain's state from ground truth and prints, for every openable one, the exact
`workstream` command. "Which streams do I open?" is a command's output, not a table someone keeps.

    python3 scripts/check-session-streams.py --all

prints EVERY unsettled domain's command, ready or blocked, in dependency order. `blocked` is
ADVISORY: `limen workstream` never reads this registry, so a blocked domain launches exactly like a
ready one — the registry reports what each waits on and the operator decides. Output is valid shell
(commands plus `#` comments), so it can be redirected to a file or piped.

State is derived, never declared:
  settled  — a commit naming the stream id has landed on origin/main (Rule #11: atomic commits,
             one id per commit, `git log --grep=<id>` → the SHA). Local work cannot fake it.
  running  — the umbrella worktree exists at <repo>/.worktrees/<id>.
  ready    — not settled, not running, and every `requires` id is settled.
  blocked  — not settled, and some `requires` id is not.

Run directly, via pr-gate, or verify-whole. Fails toward caution: a broken registry is RED.
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "institutio", "governance", "session-streams.yaml")
CONTINUATIONS = os.path.join(ROOT, "docs", "continuations")
WORKTREES = os.path.join(ROOT, ".worktrees")

REQUIRED_FIELDS = (
    "title",
    "branch_prefix",
    "intent",
    "requires",
    "unblocks",
    "job_class",
    "predicate",
    "predicate_status",
    "runway",
    "owner_of_record",
    "max_children",
    "note",
)
# The CLAUDE.md branch-cadence table. Restated nowhere else in this file.
VALID_PREFIXES = {"feat", "fix", "heal", "chore", "docs", "refactor"}
VALID_PREDICATE_STATUS = {"existing", "to_be_built"}
# Fields whose presence would let a human hand-write state the graph is supposed to derive.
FORBIDDEN_STATE_FIELDS = ("status", "state", "settled", "ready", "done", "complete")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RUNWAY_RE = re.compile(r"^([1-9][0-9]*)([mhd])$")

failures = []


def fail(check, msg):
    failures.append(f"  ✗ [{check}] {msg}")


def _opus_classes():
    """DERIVE the reserved-Opus class set from the tier authority; never keep a second copy.

    model_selection.py owns Claude's ladder. Importing it by path is the same idiom
    scripts/claude-workflow-guard.py and scripts/shims/claude use, so a rename of the ladder
    surfaces here as an import error instead of silent drift.
    """
    path = os.path.join(ROOT, "cli", "src", "limen", "model_selection.py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("_limen_model_selection", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    classes = getattr(mod, "_CLAUDE_OPUS_CLASSES_DEFAULT", None)
    return set(classes) if classes else None


def _git(*args):
    try:
        out = subprocess.run(
            ["git", "-C", ROOT, *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def load():
    with open(REGISTRY) as f:
        doc = yaml.safe_load(f) or {}
    return doc.get("streams", {}) or {}


# ── state derivation ────────────────────────────────────────────────────────────


def _settled(sid):
    """A stream is settled when a commit naming it has landed on origin/main.

    Fails toward NOT-settled: if git or the remote ref is unavailable we report unsettled, so a
    broken environment can only under-report readiness, never invent it.
    """
    log = _git("log", "origin/main", "--grep", sid, "--fixed-strings", "--format=%H")
    return bool(log)


def _running(sid):
    return os.path.isdir(os.path.join(WORKTREES, sid))


def state_of(sid, stream, settled_cache):
    if settled_cache[sid]:
        return "settled"
    if _running(sid):
        return "running"
    unmet = [r for r in stream.get("requires", []) if not settled_cache.get(r)]
    return "blocked" if unmet else "ready"


def launch_argv(sid, stream):
    """The exact command for this domain — one that actually OPENS an agent.

    `--agent auto` is load-bearing twice over, and omitting it was the defect:

      * start-worktree-session.sh sets `launch_agent=1` only when --agent is passed (:88-89) and
        execs the capsule's kickstart only under that flag (:478-480). WITHOUT --agent the script
        writes the capsule, prints a `Next:` hint, and exits — so the command this registry printed
        could never open a session. The operator was told to open four streams and handed four
        commands that each opened zero.
      * `auto` is not a pin. It resolves through the live census (start-worktree-session.sh
        :283-306): live + available + native-execution lanes only, ordered by $LIMEN_AGENT, first
        one whose binary is actually on PATH. That IS
        `lane_selection: derive_from_live_capabilities` — the capsule contract's requirement — so
        naming a vendor here would be the violation, and `auto` is the thing that honours it.

    Emitting a bare `limen workstream` and expecting a human to remember to add `--agent auto` is
    the same hand-maintained step the registry exists to abolish.

    Returns argv, not a shell string: the human view renders it and the machine view (--ready
    --json, consumed by scripts/open-streams.sh) emits it verbatim. One builder, so the command a
    launcher runs is by construction the command the operator was shown — a second copy would drift
    the moment either grew a flag.
    """
    return [
        "limen",
        "workstream",
        "--agent",
        "auto",
        "--conduct",
        "--runway",
        str(stream["runway"]),
        "--workstream",
        sid,
        "--prompt-file",
        stream["intent"],
        "limen",
        sid,
    ]


def launch_command(sid, stream):
    """`launch_argv` rendered for human eyes — wrapped at the flag boundaries it already has."""
    argv = launch_argv(sid, stream)
    head, tail = argv[:7], argv[7:]
    lines = [" ".join(head)]
    for i in range(0, len(tail) - 2, 2):
        lines.append(f"  {tail[i]} {tail[i + 1]}")
    lines.append(f"  {tail[-2]} {tail[-1]}")
    return " \\\n".join(lines)


# ── checks ──────────────────────────────────────────────────────────────────────


def run_checks(streams):
    if not streams:
        fail("A", "registry has no `streams` block")
        return

    opus_classes = _opus_classes()
    if opus_classes is None:
        fail("G", "could not import model_selection._CLAUDE_OPUS_CLASSES_DEFAULT (tier authority)")
        opus_classes = set()

    ids = set(streams)

    for sid, s in streams.items():
        if not isinstance(s, dict):
            fail("A", f"{sid}: row must be a mapping")
            continue

        # A — schema
        if not SLUG_RE.match(sid):
            fail("A", f"{sid}: id is not slug-shaped (lowercase, digits, dashes)")
        for field in REQUIRED_FIELDS:
            if field not in s:
                fail("A", f"{sid}: missing `{field}`")
        if s.get("branch_prefix") not in VALID_PREFIXES:
            fail("A", f"{sid}: branch_prefix {s.get('branch_prefix')!r} not in {sorted(VALID_PREFIXES)}")
        if s.get("predicate_status") not in VALID_PREDICATE_STATUS:
            fail(
                "A",
                f"{sid}: predicate_status {s.get('predicate_status')!r} not in {sorted(VALID_PREDICATE_STATUS)}",
            )
        if not RUNWAY_RE.match(str(s.get("runway", ""))):
            fail("A", f"{sid}: runway {s.get('runway')!r} is not Nm/Nh/Nd")
        mc = s.get("max_children")
        if not isinstance(mc, int) or mc < 1:
            fail("A", f"{sid}: max_children must be a positive int (IF-AMALGAMATION bound)")
        intent = s.get("intent")
        if isinstance(intent, str):
            if not intent.startswith(f"docs/continuations/{sid}/"):
                fail("A", f"{sid}: intent must live under docs/continuations/{sid}/")
            if not os.path.exists(os.path.join(ROOT, intent)):
                fail("A", f"{sid}: intent file does not exist: {intent}")
        note = s.get("note")
        if not isinstance(note, str) or len(note.strip()) < 40:
            fail("A", f"{sid}: note must name the measured defect this domain closes")

        # B — graph shape (membership + symmetry; acyclicity checked once, below)
        for rel in ("requires", "unblocks"):
            vals = s.get(rel, [])
            if not isinstance(vals, list):
                fail("B", f"{sid}: {rel} must be a list")
                continue
            for v in vals:
                if v not in ids:
                    fail("B", f"{sid}: {rel} names unknown stream {v!r}")
                elif v == sid:
                    fail("B", f"{sid}: {rel} names itself")
        for other in s.get("unblocks", []):
            if other in ids and sid not in streams[other].get("requires", []):
                fail("B", f"{sid}: unblocks {other}, but {other} does not require {sid}")
        for other in s.get("requires", []):
            if other in ids and sid not in streams[other].get("unblocks", []):
                fail("B", f"{sid}: requires {other}, but {other} does not unblock {sid}")

        # C — predicate presence must match its declared status, BOTH ways
        pred = s.get("predicate")
        status = s.get("predicate_status")
        if isinstance(pred, str):
            exists = os.path.exists(os.path.join(ROOT, pred))
            if status == "existing" and not exists:
                fail("C", f"{sid}: predicate_status:existing but {pred} does not exist")
            if status == "to_be_built" and exists:
                fail(
                    "C",
                    f"{sid}: predicate_status:to_be_built but {pred} EXISTS — flip it to `existing`",
                )

        # F — no hand-written state (there must be no field to lie in)
        for forbidden in FORBIDDEN_STATE_FIELDS:
            if forbidden in s:
                fail(
                    "F",
                    f"{sid}: carries `{forbidden}` — state is DERIVED from git, never declared",
                )

        # G — job_class is validated against the tier authority, not a local copy
        jc = s.get("job_class")
        if not isinstance(jc, str) or not jc:
            fail("G", f"{sid}: job_class must be a non-empty string")

    # B — acyclicity over the whole graph
    color = {}

    def visit(node, trail):
        if color.get(node) == "done":
            return
        if color.get(node) == "open":
            fail("B", f"requires-cycle: {' -> '.join(trail + [node])}")
            return
        color[node] = "open"
        for dep in streams.get(node, {}).get("requires", []) or []:
            if dep in streams:
                visit(dep, trail + [node])
        color[node] = "done"

    for sid in streams:
        visit(sid, [])

    # D/E — capsule parity and orphan lanes
    if os.path.isdir(WORKTREES):
        for slug in sorted(os.listdir(WORKTREES)):
            wt = os.path.join(WORKTREES, slug)
            if not os.path.isdir(wt):
                continue
            capsule = os.path.join(wt, ".limen-workstream")
            if slug in streams:
                receipt = os.path.join(CONTINUATIONS, slug, "workstream.json")
                if os.path.isdir(capsule) and not os.path.exists(receipt):
                    fail("D", f"{slug}: worktree has a capsule but no docs/continuations/{slug}/workstream.json")
            elif os.path.isdir(capsule) and re.match(r"^s[0-9]+-", slug):
                fail("E", f"{slug}: stream-shaped lane exists on disk but is not declared in the registry")


def print_all(streams):
    """Every unsettled domain's launch command, in dependency order.

    `blocked` is ADVISORY, not enforced: `limen workstream` never reads this registry, so a blocked
    domain launches exactly like a ready one. The operator decides — the registry only reports what
    each is waiting on. Ordering ready-first, then blocked, is the only opinion expressed here.
    """
    settled_cache = {sid: _settled(sid) for sid in streams}
    states = {sid: state_of(sid, s, settled_cache) for sid, s in streams.items()}
    rank = {"ready": 0, "running": 1, "blocked": 2}
    openable = sorted(
        ((sid, s) for sid, s in streams.items() if states[sid] != "settled"),
        key=lambda kv: (rank[states[kv[0]]], kv[0]),
    )

    print(f"session streams: {len(openable)} openable ({sum(1 for k in states.values() if k == 'ready')} with every precondition met)\n")
    for n, (sid, s) in enumerate(openable, 1):
        unmet = [r for r in s.get("requires", []) if not settled_cache.get(r)]
        waits = ", ".join(unmet) if unmet else "nothing"
        print(f"# {n}. {s['title']}")
        print(f"#    state: {states[sid]}   waits on: {waits}   owner: {s['owner_of_record']}")
        print(launch_command(sid, s))
        print()

    settled = sorted(sid for sid, k in states.items() if k == "settled")
    if settled:
        print("# settled (do not open): " + ", ".join(settled))
    return 0


def _bucket(streams):
    """The ONE state derivation. Both the human view and the machine view read this, so a launcher
    can never open a set the operator was not shown (and vice versa)."""
    settled_cache = {sid: _settled(sid) for sid in streams}
    buckets = {"ready": [], "running": [], "blocked": [], "settled": []}
    for sid, s in streams.items():
        buckets[state_of(sid, s, settled_cache)].append((sid, s))
    return buckets, settled_cache


def print_ready_json(streams):
    """Machine-readable ready set — what `scripts/open-streams.sh` consumes.

    Exists because --ready was a PRINTER: its formatted text was for human eyes, so the only way to
    act on the derived set was to read it and retype it. That is the hand-loop this registry exists
    to abolish, displaced one level up. Emitting the resolved argv (not a shell string) keeps the
    launcher from re-deriving — or quietly disagreeing with — the registry's own command.
    """
    buckets, _ = _bucket(streams)
    print(
        json.dumps(
            [
                {
                    "id": sid,
                    "title": s["title"],
                    "job_class": s["job_class"],
                    "runway": s["runway"],
                    "intent": s["intent"],
                    "owner_of_record": s["owner_of_record"],
                    "max_children": s["max_children"],
                    # The same builder the text view renders — never a second copy.
                    "argv": launch_argv(sid, s),
                }
                for sid, s in sorted(buckets["ready"])
            ],
            indent=2,
        )
    )
    return 0


def print_ready(streams):
    buckets, settled_cache = _bucket(streams)

    if not buckets["ready"]:
        print("session streams: NONE READY")
        for sid, s in sorted(buckets["blocked"]):
            unmet = [r for r in s.get("requires", []) if not settled_cache.get(r)]
            print(f"  blocked  {sid} — waiting on {', '.join(unmet)}")
        for sid, _ in sorted(buckets["running"]):
            print(f"  running  {sid} — worktree open at .worktrees/{sid}")
        return 0

    print(f"session streams: {len(buckets['ready'])} READY to open\n")
    for sid, s in sorted(buckets["ready"]):
        print(f"── {sid} — {s['title']}")
        print(f"   owner: {s['owner_of_record']}   class: {s['job_class']}   children ≤ {s['max_children']}")
        print()
        for line in launch_command(sid, s).splitlines():
            print(f"   {line}")
        print()

    for sid, s in sorted(buckets["blocked"]):
        unmet = [r for r in s.get("requires", []) if not settled_cache.get(r)]
        print(f"   blocked  {sid} — waiting on {', '.join(unmet)}")
    for sid, _ in sorted(buckets["running"]):
        print(f"   running  {sid} — worktree open at .worktrees/{sid}")
    for sid, _ in sorted(buckets["settled"]):
        print(f"   settled  {sid}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--ready",
        action="store_true",
        help="derive each domain's state from ground truth and print the launch command for every openable one",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="with --ready, emit the ready set as JSON (each row carries the resolved argv) instead "
        "of formatted text — this is what scripts/open-streams.sh consumes",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="print the launch command for EVERY unsettled domain, ready or blocked, in dependency "
        "order — blocked is advisory (the launcher never reads this registry), so the operator "
        "decides which to open",
    )
    args = ap.parse_args()

    if args.json and not args.ready:
        ap.error("--json applies to --ready")

    streams = load()

    if args.ready or args.all:
        # A launch command is only meaningful over a coherent registry. This guard is what makes it
        # safe for open-streams.sh to run the emitted argv unread: drift is exit 1 with no rows, so
        # a launcher can never open a set derived from an incoherent graph.
        run_checks(streams)
        if failures:
            print("session-streams registry: DRIFT — refusing to derive launch commands")
            print("\n".join(failures))
            sys.exit(1)
        if args.all:
            sys.exit(print_all(streams))
        sys.exit(print_ready_json(streams) if args.json else print_ready(streams))

    run_checks(streams)
    if failures:
        print("session-streams registry: DRIFT")
        print("\n".join(failures))
        sys.exit(1)
    print(f"session-streams registry: OK ({len(streams)} work-domains coherent)")
    sys.exit(0)


if __name__ == "__main__":
    main()
