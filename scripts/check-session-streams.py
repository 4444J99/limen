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
                   (see `state_of`), never written. NOTE: this alone does NOT make the ready-set
                   untamperable — the docstring used to claim it did. A commit message is as
                   writable as a YAML field; F only stops the registry CONTRADICTING git. The
                   anchored `Settles:` claim plus check H are what make the git side hard to fake.
  G  tier authority — job_class must be a class the tier authority RECOGNISES, DERIVED by import
                   rather than re-encoded here. A reserved-FABLE class is refused outright (building
                   on Fable is prohibited, so it would recreate the defect s9 healed); an unknown
                   class is refused because it derives the cheapest default tier in silence. This
                   check was a literal NO-OP until 2026-07-29 — it computed the class set and never
                   compared it — during which three rows quietly derived the default.
  I  predicate argv — a declared predicate_command must be statically safe to run: argv[0] a runner,
                   no act-tokens, and a mutate-by-default effector must carry its neutraliser.
  J  predicate uniqueness — two rows may not share a predicate_command; a shared probe cannot say
                   WHICH domain is done.
  K  owner resolves — owner_of_record must exist. Nothing checked this, and s8 pointed at
                   institutio/governance/estate.yaml (never a real path) for the registry's life.
  L  fan-out parity — max_children must equal the bound its cartridge states in prose; the prose
                   copy is the one a cold session actually reads.
  H  settlement backfill — `settled_by: <sha>` exists only for streams that settled BEFORE the
                   `Settles:` convention. Each must be a real commit reachable from origin/main that
                   changed paths outside this registry, and at most MAX_SETTLED_BY rows may carry
                   one — a migration that can only shrink, never a second settlement path.

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
  settled  — a commit that did REAL WORK has landed on origin/main CLAIMING this stream, with an
             anchored trailer at column 0 of its message:

                 Settles: <stream-id>[, <stream-id>…]

             "Real work" = it changed at least one path outside this registry and docs/{plans,
             continuations}/ — bookkeeping records an outcome, it does not produce one. Local work
             cannot fake it, and neither can a passing mention: the previous rule was an UNANCHORED
             `git log --grep=<id>`, which settled `s10-axis-coverage` off a docs commit whose whole
             subject was that s10 owns work a plan should not do. Pre-convention settlements use the
             bounded `settled_by:` backfill (check H).
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
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _worktree_liveness  # noqa: E402 — the shared probe reclaim-worktrees.py also trusts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "institutio", "governance", "session-streams.yaml")
CONTINUATIONS = os.path.join(ROOT, "docs", "continuations")
WORKTREES = os.path.join(ROOT, ".worktrees")

REQUIRED_FIELDS = (
    "family",
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
# Which registry a row is a projection of. `domain` rows are DERIVED from the workstream channel
# roster (cli/src/limen/workstream.py meta lanes + organ-ladder.json pillars) — the operator's
# LIFE/WORK DOMAINS (2026-07-30 correction: email/comms=correspondence, finance=financial, job
# applications=representation), the streams he actually opens. `constellation` rows are DERIVED
# from organs/consulting/constellation/registry.yaml — the collaborator person-streams, which are
# the consulting DOMAIN's interior. `governance` rows are hand-authored estate work. The
# operator-facing views list domain first — his life/work domains are the answer to "what streams
# do I open?"; the collaborator interior and the plumbing follow, never lead.
VALID_FAMILIES = {"domain", "constellation", "governance"}
FAMILY_RANK = {"domain": 0, "constellation": 1, "governance": 2}
# The generators whose output checks M and N hold this registry to. Each one's --check re-derives
# its own family's rows and cartridges and exits 1 on any byte of drift — so a hand-edit to a
# derived row is a red pr-gate, same pattern as check-gates.py holds workflows.
DERIVE_STREAMS = os.path.join("organs", "consulting", "constellation", "derive-streams.py")
DERIVE_DOMAINS = os.path.join("institutio", "governance", "derive-domain-streams.py")
VALID_PREDICATE_STATUS = {"existing", "to_be_built"}
# Fields whose presence would let a human hand-write state the graph is supposed to derive.
FORBIDDEN_STATE_FIELDS = ("status", "state", "settled", "ready", "done", "complete")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RUNWAY_RE = re.compile(r"^([1-9][0-9]*)([mhd])$")

# ── predicate_command: the argv actually RUN to prove a stream done ─────────────────
#
# Distinct from `predicate` (the FILE whose existence check C validates). A file existing proves
# nothing about the work; this is what gets executed.
#
# THE GUARD IS THE POINT. `predicate` fields already name executables that MUTATE THE WORLD —
# scripts/repo-genesis.py without --dry-run creates a real GitHub repo and pushes seed material
# (repo-genesis.py:28). Running predicates naively would make settlement an irreversible, outward
# -facing action. So the argv is constrained STATICALLY and a violation is REFUSED BY THE CHECKER,
# never executed: there is no path from this registry to a live mint.
PREDICATE_ARGV0 = {"python3", "bash", "scripts/run-pytest-hermetic.sh"}
# Tokens that mean "actually do it". Refused anywhere in the argv, not just position 1.
PREDICATE_FORBIDDEN_TOKENS = ("--apply", "--no-dry-run", "--write", "--live", "--force", "--execute")
# Scripts that MUTATE BY DEFAULT, mapped to the flag that neutralises them. Blocking "act" flags is
# backwards for these: repo-genesis.py mints a real GitHub repo and pushes seed material unless
# --dry-run is passed (repo-genesis.py:28,100-107) — `--dry-run` is opt-IN, so an argv carrying no
# forbidden token at all is still an effector. A predicate naming one of these MUST carry its
# neutralising flag. This is the difference between a guard that looks right and one that is.
PREDICATE_EFFECTORS = {"scripts/repo-genesis.py": "--dry-run"}
PREDICATE_TIMEOUT_S = 180

failures = []


def fail(check, msg):
    failures.append(f"  ✗ [{check}] {msg}")


def _tier_classes(attr):
    """DERIVE a reserved class set from the tier authority by name; never keep a second copy.

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
    classes = getattr(mod, attr, None)
    return set(classes) if classes else None


def _opus_classes():
    """The reserved-Opus set."""
    return _tier_classes("_CLAUDE_OPUS_CLASSES_DEFAULT")


def _fable_classes():
    """The reserved-Fable set — building on Fable is prohibited, so a row may not declare one."""
    return _tier_classes("_CLAUDE_FABLE_CLASSES_DEFAULT")


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


# A settling commit must CLAIM the settlement on its own line, at column 0, in its own message.
# Anchored deliberately: the previous rule was `git log --grep=<id> --fixed-strings`, which matched
# an id ANYWHERE in a message and so could not tell "this commit settles s10" from "this commit
# mentions s10". That is not hypothetical — it fired within a day of the registry shipping:
#
#   0a17877b  docs(plans): the omega rung belongs to s10-axis-coverage, not to this plan (#1624)
#
# a docs commit whose entire point was that s10 owns work THIS plan should not do, which marked s10
# SETTLED and removed it from the ready set with none of its work built. `s1-homing-spine` settled
# the same way, off the registry's own bookkeeping commit.
#
# Read from %B (the raw body), NOT via `%(trailers:…)`. GitHub's squash-merge appends its own
# `Co-authored-by:` paragraph, which demotes an author-written trailer out of the final paragraph —
# git's trailer parser then returns EMPTY for it. Measured: 9 of 9 commits carrying a
# `Claude-Session:` line return nothing from `%(trailers:key=Claude-Session,valueonly)`. A regex over
# the whole body is what survives the squash.
SETTLES_RE = re.compile(r"^Settles:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)

# The registry may not settle itself. A commit that only edits the registry (or only docs about it)
# is bookkeeping: it records an outcome, it does not produce one. Requiring at least one changed
# path outside these is what stops a row from being talked into `settled`.
SELF_REFERENTIAL_PATHS = (
    "institutio/governance/session-streams.yaml",
    "docs/continuations/",
    "docs/plans/",
)

# `settled_by: <sha>` is the ONE migration affordance: streams that genuinely settled before the
# `Settles:` convention existed, and whose real-work commit therefore cannot be amended (it is on
# main). Bounded at exactly the number legitimately needed today, so a third is a deliberate,
# reviewed registry edit and never a quiet escape hatch. Check H proves each SHA is real, reachable
# on origin/main, and did work outside the registry — the same bar a live `Settles:` claim must meet.
MAX_SETTLED_BY = 2


def predicate_argv_violation(cmd):
    """Why this argv may not be run, or None if it is safe. Pure — no execution, no filesystem."""
    if not isinstance(cmd, str) or not cmd.strip():
        return "must be a non-empty string"
    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        return f"is not parseable as a shell command ({exc})"
    if not argv:
        return "is empty after parsing"
    if argv[0] not in PREDICATE_ARGV0:
        return f"argv[0] {argv[0]!r} is not one of {sorted(PREDICATE_ARGV0)} — a predicate must be a runner, not an effector"
    for token in argv:
        if token in PREDICATE_FORBIDDEN_TOKENS:
            return f"carries {token!r} — a settlement probe must be side-effect-free"
    for effector, neutraliser in PREDICATE_EFFECTORS.items():
        if any(tok == effector or tok.endswith("/" + effector.rsplit("/", 1)[-1]) for tok in argv):
            if neutraliser not in argv:
                return (
                    f"names {effector}, which MUTATES BY DEFAULT, without {neutraliser}. "
                    "It creates a real GitHub repo and pushes seed material unless told otherwise, so "
                    "an argv carrying no forbidden flag at all is still an effector"
                )
    return None


def _predicate_proven(sid, stream):
    """Run this stream's predicate_command. True only on a clean exit 0.

    Every other outcome — absent command, guard violation, nonzero, timeout, missing binary —
    resolves identically to NOT PROVEN. Failing toward unproven is what keeps a broken environment
    from inventing settlement.
    """
    cmd = (stream or {}).get("predicate_command")
    if not cmd or predicate_argv_violation(cmd):
        return False
    try:
        out = subprocess.run(
            shlex.split(cmd),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=PREDICATE_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


def _settled_by_backfill():
    """{sid: sha} from the registry's `settled_by` rows. Loaded once, validated by check H."""
    return {sid: s["settled_by"] for sid, s in load().items() if isinstance(s, dict) and s.get("settled_by")}


def _settling_commits(sid):
    """SHAs on origin/main whose message carries an anchored `Settles: <sid>` claim.

    `--grep` still does the cheap prefilter (git-side, no full log walk); the regex is what decides.
    """
    raw = _git("log", "origin/main", "--grep", f"Settles: {sid}", "--fixed-strings", "--format=%H%x00%B%x01")
    out = []
    for record in raw.split("\x01"):
        if "\x00" not in record:
            continue
        sha, body = record.split("\x00", 1)
        sha = sha.strip()
        for claim in SETTLES_RE.findall(body):
            # One trailer may settle several ids: `Settles: s2-foo, s3-bar`.
            if sid in [part.strip() for part in claim.split(",")]:
                out.append(sha)
                break
    return out


def _does_real_work(sha):
    """True iff this commit changed at least one path outside the registry's own bookkeeping."""
    files = _git("show", "--name-only", "--format=", sha).splitlines()
    return any(f.strip() and not f.startswith(SELF_REFERENTIAL_PATHS) for f in files)


def _settled(sid, stream=None):
    """settled ⟺ (anchored claim on real work AND its predicate exits 0) OR bounded backfill.

    Two paths, and the asymmetry is deliberate:

      * A NEW settlement must clear BOTH halves. The claim says "this is done"; the predicate
        PROVES it. Either alone is an assertion — the trailer is as writable as a YAML field, and a
        green predicate shared with another stream cannot tell which one it settled.
      * The `settled_by:` backfill is exempt from the predicate half, because it exists precisely
        for rows that settled BEFORE any of this existed and whose real-work commit is already on
        main and cannot be amended. It is not unproven: check H verifies the SHA is a real commit
        reachable from origin/main that changed paths outside this registry, and MAX_SETTLED_BY
        bounds it at exactly today's legitimate count. Requiring a second, independent proof of a
        grandfathered row would un-settle it for a reason unrelated to whether it is done, which is
        what makes a migration useless.

    Fails toward NOT-settled: if git or the remote ref is unavailable we report unsettled, so a
    broken environment can only under-report readiness, never invent it.

    Constellation and domain rows NEVER settle here: both are recurring work the operator
    reopens, and their lifecycle belongs to the registry each derives from — a constellation lane
    leaves the ready set when the operator re-tiers or removes the person in the register, and a
    domain leaves it when the channel roster changes (an organ pillar removed, or the projection
    policy deliberately edited); derivation then deletes the row. Not when one increment lands a
    trailer: without this guard a single `Settles: styx` (or `Settles: correspondence`) commit
    would remove a recurring lane from the launcher forever while its registry still declares it.
    """
    if stream is None:
        stream = load().get(sid) or {}
    if stream.get("family") in ("constellation", "domain"):
        return False
    if sid in _settled_by_backfill():
        return True
    if not any(_does_real_work(sha) for sha in _settling_commits(sid)):
        return False
    return _predicate_proven(sid, stream)


# Presence classification per lane, memoized so every view agrees within one run and the pid a
# view prints is the pid the decision was made on.
_PRESENCE: dict[str, tuple[str, int | None]] = {}


def _lane_presence(sid):
    """(state, pid) for a lane's on-disk worktree, or (None, None) when there is none.

    This split is what makes the round trip ROUND. The old rule — "a directory exists at
    .worktrees/<sid>" ⇒ `running` — conflated two states that need opposite handling: an agent
    actually attached (never double-open) and an exited session whose worktree remains (the
    whole point of reopening). Under it, a stream opened once could never re-enter the ready
    set until settled: the one-command reopen the registry promises worked exactly once per
    stream, then jammed shut, while `--ready` printed `running` about nothing.

      live     a process has its cwd at/under the worktree — or the probe was unavailable
               (pid -1, fail-closed: a broken probe must under-open, never double-open). The
               same probe, same direction, keeps reclaim-worktrees.py from deleting these.
      dormant  a valid worktree, nothing attached. OPENABLE — the launcher labels it REOPEN;
               start-worktree-session.sh re-enters it (`created="reused"`) with the capsule
               identity digest still binding the branch.
      stale    the path exists but is not a valid git worktree. start-worktree-session.sh
               hard-errors on these (:529-531), so offering one as reopenable would open a
               tmux window containing an error. Reported; the SPRAWL-RECLAIM organ owns it.
    """
    if sid in _PRESENCE:
        return _PRESENCE[sid]
    wt = os.path.join(WORKTREES, sid)
    if not os.path.isdir(wt):
        state = (None, None)
    else:
        probe = subprocess.run(
            ["git", "-C", wt, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            state = ("stale", None)
        else:
            pid = _worktree_liveness.process_owner(Path(wt))
            state = ("live", pid) if pid is not None else ("dormant", None)
    _PRESENCE[sid] = state
    return state


def state_of(sid, stream, settled_cache):
    if settled_cache[sid]:
        return "settled"
    presence, _pid = _lane_presence(sid)
    if presence is not None:
        return presence
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
    fable_classes = _fable_classes()
    if fable_classes is None:
        fail("G", "could not import model_selection._CLAUDE_FABLE_CLASSES_DEFAULT (tier authority)")
        fable_classes = set()

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
        if s.get("family") not in VALID_FAMILIES:
            fail("A", f"{sid}: family {s.get('family')!r} not in {sorted(VALID_FAMILIES)}")
        # register_tier orders the ready set (T1 opens before T2 under the launcher's bound). It is
        # the register's word, so only derived rows may carry it — a governance row declaring one
        # would be hand-written queue-jumping.
        rt = s.get("register_tier")
        if rt is not None:
            if s.get("family") != "constellation":
                fail("A", f"{sid}: register_tier is register-derived; only constellation rows carry it")
            elif not re.fullmatch(r"T[0-9]", str(rt)):
                fail("A", f"{sid}: register_tier {rt!r} is not T<digit>")
        # open_rank is the domain family's ordering word (the launcher's RAM bound opens the first
        # N rows, so order IS priority) — roster-derived, so only domain rows may carry it; any
        # other family declaring one would be hand-written queue-jumping, same rule as
        # register_tier above.
        orank = s.get("open_rank")
        if orank is not None:
            if s.get("family") != "domain":
                fail("A", f"{sid}: open_rank is roster-derived; only domain rows carry it")
            elif not isinstance(orank, int) or isinstance(orank, bool) or orank < 1:
                fail("A", f"{sid}: open_rank {orank!r} must be a positive int")
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

        # F — no hand-written state. This does NOT make state untamperable on its own, and the
        # docstring used to claim it did ("there is no field to lie in"). The lie simply moved into
        # a commit message, which is equally writable — see the s10 false-settlement in SETTLES_RE.
        # What F actually buys is that the registry cannot contradict git; the anchored trailer plus
        # check H are what make the git side hard to fake.
        for forbidden in FORBIDDEN_STATE_FIELDS:
            if forbidden in s:
                fail(
                    "F",
                    f"{sid}: carries `{forbidden}` — state is DERIVED from git, never declared",
                )

        # L — max_children is stated TWICE: here, and in prose in the cartridge ("At most **N**
        # children"). The registry value is not inert — FanoutBoundsV1 enforces it when a child is
        # reserved via `conduct split` — but the cartridge copy is what a cold session actually
        # READS before deciding how many children to open. Two copies of a bound is the same
        # second-source defect the rest of this file exists to prevent, and the prose copy is the
        # one nothing would ever check. Hold them equal.
        intent_path = os.path.join(ROOT, s["intent"]) if isinstance(s.get("intent"), str) else None
        if intent_path and os.path.exists(intent_path) and isinstance(s.get("max_children"), int):
            with open(intent_path) as fh:
                stated = re.search(r"[Aa]t most \*\*(\d+)\*\* children", fh.read())
            if stated and int(stated.group(1)) != s["max_children"]:
                fail(
                    "L",
                    f"{sid}: max_children {s['max_children']} but its cartridge says "
                    f"{stated.group(1)} — the prose copy is what a cold session reads",
                )

        # K — owner_of_record must RESOLVE. The field names the git-tracked surface that owns this
        # domain's result, and nothing ever checked it existed: s8 pointed at
        # institutio/governance/estate.yaml for the registry's whole life, while the real file is
        # institutio/github/estate.yaml — s8's OWN predicate reads the github/ one. A registry whose
        # job is naming owners cannot have an owner that is not there.
        owner = s.get("owner_of_record")
        if isinstance(owner, str) and owner and not os.path.exists(os.path.join(ROOT, owner)):
            fail("K", f"{sid}: owner_of_record {owner!r} does not exist")

        # I — predicate_command, if declared, must be statically safe to RUN. Validated for every
        # row whether or not it will ever execute, so an unsafe argv is caught the moment it is
        # written rather than the day that stream settles.
        if "predicate_command" in s and s.get("predicate_command") is not None:
            violation = predicate_argv_violation(s["predicate_command"])
            if violation:
                fail("I", f"{sid}: predicate_command {violation}")

        # H — the pre-convention backfill is bounded and every entry is real
        sb = s.get("settled_by")
        if sb is not None:
            if not isinstance(sb, str) or not re.fullmatch(r"[0-9a-f]{7,40}", sb):
                fail("H", f"{sid}: settled_by must be a hex commit SHA, got {sb!r}")
            elif _git("cat-file", "-t", sb) != "commit":
                fail("H", f"{sid}: settled_by {sb} is not a commit in this repo")
            # `rev-list <sha> ^origin/main` lists commits reachable from the SHA but NOT from main.
            # Empty ⇒ the SHA is an ancestor of main, i.e. the work really landed. A SHA on some
            # unmerged branch would list itself here and is rejected.
            elif _git("rev-list", "--max-count=1", sb, "^origin/main") != "":
                fail("H", f"{sid}: settled_by {sb} is not reachable from origin/main")
            elif not _does_real_work(sb):
                fail(
                    "H",
                    f"{sid}: settled_by {sb} changed only registry/docs paths — bookkeeping "
                    "cannot settle a stream, the same bar a live `Settles:` claim must clear",
                )

        # G — job_class is validated against the tier authority, not a local copy.
        #
        # This was a LITERAL NO-OP: `opus_classes` was computed above and never compared, and the
        # body only asserted a non-empty string. So the one field that decides which model a
        # launched lane runs on was unvalidated, and three rows declaring `governance` — a class the
        # authority has never heard of — derived the DEFAULT haiku in silence.
        jc = s.get("job_class")
        if not isinstance(jc, str) or not jc:
            fail("G", f"{sid}: job_class must be a non-empty string")
        elif jc in fable_classes:
            # docs/fable-allotment.md: Fable is PLAN-ONLY and building on it is PROHIBITED. A row
            # declaring one of these derives a Fable pin for a lane whose whole purpose is build
            # work — recreating the exact defect s9 was opened to heal.
            fail(
                "G",
                f"{sid}: job_class {jc!r} is RESERVED-FABLE — it would derive a Fable pin, and "
                "docs/fable-allotment.md prohibits building on Fable. Use a reserved-Opus class.",
            )
        elif jc not in opus_classes:
            # Unknown to the authority ⇒ tier_for_classes returns the cheapest default. Silently.
            # A work DOMAIN running on the default tier is almost never intended, and nothing would
            # have surfaced it — the row looks declarative and derives nothing.
            fail(
                "G",
                f"{sid}: job_class {jc!r} is unknown to the tier authority, so it derives the "
                f"cheapest default tier silently. Use one of {sorted(opus_classes)}, or add it to "
                "model_selection._CLAUDE_OPUS_CLASSES_DEFAULT — never widen the authority just to "
                "green a row, since that changes tier derivation for every fleet task estate-wide.",
            )

    # J — a shared predicate_command cannot decide either stream it serves. This is not
    # hypothetical: check-convergence.py is the `predicate` of s3/s6/s7, check-atom-homing.py of
    # s1/s2, no-tasks-on-me.sh of s4/s5 — 7 of 11 rows. Green on a shared, argument-less command
    # says "some axis is healthy", never "THIS domain is done", so it may not settle anything.
    by_cmd = {}
    for sid, s in streams.items():
        if isinstance(s, dict) and s.get("predicate_command"):
            by_cmd.setdefault(" ".join(shlex.split(str(s["predicate_command"]))), []).append(sid)
    for cmd, sids in sorted(by_cmd.items()):
        if len(sids) > 1:
            fail(
                "J",
                f"{', '.join(sorted(sids))} share predicate_command {cmd!r} — a shared probe cannot "
                "prove which domain is done; narrow it per stream or leave it null (null = not provable yet)",
            )

    # H — the backfill is a migration, not a mechanism: bound the whole-registry count so it can
    # only shrink as those streams' work is re-proven, never grow into a parallel settlement path.
    backfilled = sorted(sid for sid, s in streams.items() if isinstance(s, dict) and s.get("settled_by"))
    if len(backfilled) > MAX_SETTLED_BY:
        fail(
            "H",
            f"{len(backfilled)} rows carry settled_by (max {MAX_SETTLED_BY}): {', '.join(backfilled)} — "
            "this field exists only for streams that settled BEFORE the `Settles:` convention; a new "
            "stream settles by claiming it in its own commit",
        )

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
                # The receipt is written ON THE STREAM'S BRANCH, inside the worktree — it reaches
                # this checkout's docs tree only when that branch merges. An open stream whose
                # receipt still lives in its own worktree is compliant, not drifted (first live
                # launch, 2026-07-29: every opened lane instantly turned --status into a red D).
                receipt = os.path.join(CONTINUATIONS, slug, "workstream.json")
                wt_receipt = os.path.join(wt, "docs", "continuations", slug, "workstream.json")
                if os.path.isdir(capsule) and not (os.path.exists(receipt) or os.path.exists(wt_receipt)):
                    fail("D", f"{slug}: worktree has a capsule but no docs/continuations/{slug}/workstream.json")
            elif os.path.isdir(capsule) and re.match(r"^s[0-9]+-", slug):
                fail("E", f"{slug}: stream-shaped lane exists on disk but is not declared in the registry")

    # M — constellation rows and cartridges are PROJECTIONS of the constellation register, held in
    # parity by the generator's own --check (one derivation rule, one home — this checker never
    # re-implements it). The defect this closes: the operator's actual workstreams (people ×
    # project lanes, tiers operator-accepted 2026-07-22) lived one registry over, and this file was
    # authored fresh without them — so "what streams do I open?" answered with governance plumbing
    # while spiral/styx/hokage-chess were unopenable. Drift in EITHER direction (register edited
    # without rerunning --write, or a derived row/cartridge hand-edited) is a red pr-gate.
    generator = os.path.join(ROOT, DERIVE_STREAMS)
    if not os.path.exists(generator):
        fail("M", f"{DERIVE_STREAMS} is missing — constellation rows have no derivation authority")
    else:
        try:
            probe = subprocess.run(
                [sys.executable, generator, "--check"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=ROOT,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            fail("M", f"could not run {DERIVE_STREAMS} --check: {exc}")
        else:
            if probe.returncode != 0:
                detail = (probe.stdout + probe.stderr).strip().splitlines()
                fail(
                    "M",
                    "constellation rows/cartridges have drifted from the register — "
                    + "; ".join(detail[:4])
                    + f" — fix the register, then `python3 {DERIVE_STREAMS} --write`",
                )

    # N — domain rows and cartridges are PROJECTIONS of the workstream channel roster
    # (workstream.py meta lanes + organ-ladder.json pillars), held in parity by the domain
    # generator's own --check — the same one-derivation-rule-one-home shape as check M. The defect
    # this closes: the operator's actual streams are his LIFE/WORK DOMAINS (2026-07-30 —
    # email/comms=correspondence, finance=financial, job applications=representation), canonical
    # in code since 2026-07-02, and this registry twice shipped without a family for them.
    domain_generator = os.path.join(ROOT, DERIVE_DOMAINS)
    if not os.path.exists(domain_generator):
        fail("N", f"{DERIVE_DOMAINS} is missing — domain rows have no derivation authority")
    else:
        try:
            probe = subprocess.run(
                [sys.executable, domain_generator, "--check"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=ROOT,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            fail("N", f"could not run {DERIVE_DOMAINS} --check: {exc}")
        else:
            if probe.returncode != 0:
                detail = (probe.stdout + probe.stderr).strip().splitlines()
                fail(
                    "N",
                    "domain rows/cartridges have drifted from the channel roster — "
                    + "; ".join(detail[:4])
                    + f" — fix the roster/policy, then `python3 {DERIVE_DOMAINS} --write`",
                )


def print_all(streams):
    """Every unsettled domain's launch command, in dependency order.

    `blocked` is ADVISORY, not enforced: `limen workstream` never reads this registry, so a blocked
    domain launches exactly like a ready one. The operator decides — the registry only reports what
    each is waiting on. Ordering ready-first, then blocked, is the only opinion expressed here.
    """
    settled_cache = {sid: _settled(sid, s) for sid, s in streams.items()}
    states = {sid: state_of(sid, s, settled_cache) for sid, s in streams.items()}
    # dormant ranks WITH ready (it is openable — that is the round trip), live/stale never launch.
    rank = {"ready": 0, "dormant": 0, "live": 1, "blocked": 2, "stale": 3}
    openable = sorted(
        ((sid, s) for sid, s in streams.items() if states[sid] != "settled"),
        key=lambda kv: (FAMILY_RANK.get(kv[1].get("family"), len(FAMILY_RANK)), rank[states[kv[0]]], kv[0]),
    )

    print(
        f"session streams: {len(openable)} openable ({sum(1 for k in states.values() if k == 'ready')} with every precondition met)\n"
    )
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


def _within_family_key(s):
    """The ordering word INSIDE a family, as a string so families never cross-compare types:
    domain rows order by zero-padded open_rank ("001" < "002"), constellation by register_tier
    ("T1" < "T2"), governance by nothing ("~" sorts after both)."""
    if s.get("family") == "domain":
        try:
            return f"{int(s.get('open_rank', 999)):03d}"
        except (TypeError, ValueError):
            return "999"
    return str(s.get("register_tier", "~"))  # "~" sorts after any TN, so untiered rows follow


def _family_order(rows):
    """Domain rows first (by open_rank — the launcher's RAM bound opens the first N rows, so
    order IS priority), then constellation (T1 before T2 — the consulting domain's interior),
    then governance, alphabetical within each rank. The operator's life/work domains are the
    answer to "what streams do I open?" — the interior and the plumbing follow, never lead."""
    return sorted(
        rows,
        key=lambda kv: (
            FAMILY_RANK.get(kv[1].get("family"), len(FAMILY_RANK)),
            _within_family_key(kv[1]),
            kv[0],
        ),
    )


def _bucket(streams):
    """The ONE state derivation. Both the human view and the machine view read this, so a launcher
    can never open a set the operator was not shown (and vice versa)."""
    settled_cache = {sid: _settled(sid, s) for sid, s in streams.items()}
    buckets = {"ready": [], "live": [], "dormant": [], "stale": [], "blocked": [], "settled": []}
    for sid, s in streams.items():
        buckets[state_of(sid, s, settled_cache)].append((sid, s))
    return buckets, settled_cache


def _openable(buckets):
    """ready ∪ dormant — everything the launcher may open. Dormant IS openable: an exited session
    whose worktree remains is the reopen case, not an occupied slot."""
    return _family_order(buckets["ready"] + buckets["dormant"])


def print_ready_json(streams):
    """Machine-readable openable set — what `scripts/open-streams.sh` consumes.

    Exists because --ready was a PRINTER: its formatted text was for human eyes, so the only way to
    act on the derived set was to read it and retype it. That is the hand-loop this registry exists
    to abolish, displaced one level up. Emitting the resolved argv (not a shell string) keeps the
    launcher from re-deriving — or quietly disagreeing with — the registry's own command.

    Rows carry `reopen`: false = a fresh open, true = re-entry into an existing dormant worktree
    (the launcher labels it REOPEN so the operator can tell resumption from a first open).
    """
    buckets, _ = _bucket(streams)
    dormant = {sid for sid, _ in buckets["dormant"]}
    print(
        json.dumps(
            [
                {
                    "id": sid,
                    "family": s["family"],
                    "title": s["title"],
                    "job_class": s["job_class"],
                    "runway": s["runway"],
                    "intent": s["intent"],
                    "owner_of_record": s["owner_of_record"],
                    "max_children": s["max_children"],
                    "reopen": sid in dormant,
                    # The same builder the text view renders — never a second copy.
                    "argv": launch_argv(sid, s),
                }
                for sid, s in _openable(buckets)
            ],
            indent=2,
        )
    )
    return 0


def _print_unopenable(buckets, settled_cache, indent="   "):
    for sid, s in sorted(buckets["live"]):
        _, pid = _lane_presence(sid)
        print(f"{indent}live     {sid} — a session is attached (pid {pid}); never double-opened")
    for sid, s in sorted(buckets["blocked"]):
        unmet = [r for r in s.get("requires", []) if not settled_cache.get(r)]
        print(f"{indent}blocked  {sid} — waiting on {', '.join(unmet)}")
    for sid, _ in sorted(buckets["stale"]):
        print(
            f"{indent}stale    {sid} — .worktrees/{sid} is not a valid git worktree; "
            "owner: the SPRAWL-RECLAIM organ (scripts/reclaim-worktrees.py)"
        )
    for sid, _ in sorted(buckets["settled"]):
        print(f"{indent}settled  {sid}")


def print_ready(streams):
    buckets, settled_cache = _bucket(streams)
    openable = _openable(buckets)
    dormant = {sid for sid, _ in buckets["dormant"]}

    if not openable:
        print("session streams: NONE OPENABLE")
        _print_unopenable(buckets, settled_cache, indent="  ")
        return 0

    reopen_n = len(buckets["dormant"])
    suffix = f" ({reopen_n} of them REOPEN — exited sessions whose worktree remains)" if reopen_n else ""
    print(f"session streams: {len(openable)} OPENABLE{suffix}\n")
    for sid, s in openable:
        mark = "REOPEN" if sid in dormant else ""
        print(f"── {sid} — {s['title']}{('   [' + mark + ']') if mark else ''}")
        print(
            f"   family: {s['family']}   owner: {s['owner_of_record']}   class: {s['job_class']}   children ≤ {s['max_children']}"
        )
        print()
        for line in launch_command(sid, s).splitlines():
            print(f"   {line}")
        print()

    _print_unopenable(buckets, settled_cache)
    return 0


def print_status(streams):
    """One line per stream, every state named — the round trip made visible.

    The reopen cycle was invisible: nothing showed 'you exited styx; it is reopenable', so the
    operator could not see WHY the one-command open did or did not include a lane. This is the
    glance view: open → work → exit → `--status` says dormant → open again → it says live.
    """
    buckets, settled_cache = _bucket(streams)
    dorm = {sid for sid, _ in buckets["dormant"]}
    states = {}
    for state, rows in buckets.items():
        for sid, _s in rows:
            states[sid] = state
    label = {
        "live": "live     — session attached (pid {pid})",
        "dormant": "dormant  — exited; REOPENS on next open-streams run",
        "ready": "ready    — never opened; opens on next open-streams run",
        "blocked": "blocked  — waiting on {waits}",
        "stale": "stale    — invalid worktree; owner: SPRAWL-RECLAIM",
        "settled": "settled",
    }
    for family in sorted({s.get("family") for s in streams.values()}, key=lambda f: FAMILY_RANK.get(f, 9)):
        rows = _family_order([(sid, s) for sid, s in streams.items() if s.get("family") == family])
        print(f"{family}:")
        for sid, s in rows:
            st = states[sid]
            _, pid = _lane_presence(sid) if st in ("live",) else (None, None)
            waits = ", ".join(r for r in s.get("requires", []) if not settled_cache.get(r))
            print(f"  {sid:24s} {label[st].format(pid=pid, waits=waits)}")
    openable = len(buckets["ready"]) + len(dorm)
    print(f"\n{openable} openable ({len(dorm)} reopen) · attach: tmux attach -t limen-streams")
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
    ap.add_argument(
        "--status",
        action="store_true",
        help="one line per stream with its derived state (live/dormant/ready/blocked/stale/settled)"
        " — the glance view of the open → exit → reopen cycle; touches nothing",
    )
    args = ap.parse_args()

    if args.json and not args.ready:
        ap.error("--json applies to --ready")

    streams = load()

    if args.ready or args.all or args.status:
        # A launch command is only meaningful over a coherent registry. This guard is what makes it
        # safe for open-streams.sh to run the emitted argv unread: drift is exit 1 with no rows, so
        # a launcher can never open a set derived from an incoherent graph.
        run_checks(streams)
        if failures:
            print("session-streams registry: DRIFT — refusing to derive launch commands")
            print("\n".join(failures))
            sys.exit(1)
        if args.status:
            sys.exit(print_status(streams))
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
