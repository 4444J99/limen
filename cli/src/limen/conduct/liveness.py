"""Foreign-occupant probe for worktree succession.

Registration may name a dead predecessor to supersede (ConductorSessionV1.supersedes), but the
broker cannot verify process liveness across hosts — the claimant must, and it runs INSIDE the
worktree it is claiming, so the plain is-anything-alive-here probe would always answer "yes, me."
This probe therefore excludes the calling process's own ancestor lineage (the boot shell, the
workstream launcher, the tmux pane) and reports only FOREIGN occupants.

Sibling of scripts/_worktree_liveness.py, which serves repo scripts that run without the limen
package installed and needs no self-exclusion (the stream launcher probes before it spawns into
the worktree). Both fail CLOSED: when the probe itself is unavailable, the answer is "occupied"
(pid -1), so a broken probe can only refuse succession, never steal a live session's worktree.
`live_checkout_occupant` below is the one deliberate inversion — it fails OPEN, because its
consumer does not destroy anything and its failure mode is a sync organ that never converges.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _ancestor_pids() -> set[int]:
    """The calling process and its ancestor chain, walked via `ps` (portable to macOS)."""
    lineage = {os.getpid()}
    pid = os.getpid()
    for _ in range(64):
        try:
            raw = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                cwd="/",
            ).stdout.strip()
            parent = int(raw)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            break
        if parent <= 1 or parent in lineage:
            break
        lineage.add(parent)
        pid = parent
    return lineage


def _process_cwds() -> dict[Path, set[int]]:
    """Observable process cwds; an unavailable probe fails closed (pid -1 owns everything).

    A directory maps to EVERY pid observed there, never one. Keying a single pid per directory is
    lossy in exactly the case both consumers below live in: they filter the pid they retrieve, so
    dropping the one that would have survived the filter does not mis-name the occupant, it
    ERASES it — the probe answers "free" while a live session holds the tree.

    That is not hypothetical. `sync-release.sh` does `cd "$ROOT"` before it asks, so the probe
    process sits in the very directory it is asking about; with one slot per cwd the probe's own
    pid evicted the session's, `live_checkout_occupant` then recognised the survivor as its own
    lineage, and the guard reported the live checkout free while a session worked in it. Observed
    end-to-end 2026-08-06 by driving sync-release.sh against a real occupant: it unparked HEAD and
    pushed. The escape valve was luck — lsof emits in ascending pid order, so the LAST writer wins
    the slot, and the operator host had only escaped because its pid counter had wrapped and the
    session's pid outranked every fresh spawn.

    The sibling probes (`scripts/_worktree_liveness.py`, `scripts/reap-clones.py`) key the same
    way and are deliberately NOT changed: their consumers return whatever pid is at the cwd with
    no filtering, so a collision there costs a wrong pid in a log line, never a wrong decision.
    """
    observed: dict[Path, set[int]] = {}
    proc = Path("/proc")
    if proc.is_dir():
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                observed.setdefault((entry / "cwd").resolve(strict=True), set()).add(int(entry.name))
            except (OSError, ValueError):
                continue
        return observed
    try:
        # cwd="/" is load-bearing: the scanner subprocess otherwise inherits the CALLER's cwd,
        # and the claimant registers from inside the worktree it probes — so lsof would list
        # ITSELF as a live occupant of that worktree, a descendant the ancestor lineage cannot
        # exclude, and succession would be refused deterministically (the 2026-07-30 reopen
        # incident). Launching the observer from / keeps it out of every observed region.
        result = subprocess.run(
            ["lsof", "-n", "-a", "-d", "cwd", "-Fpn"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            cwd="/",
        )
    except (OSError, subprocess.TimeoutExpired):
        return {Path("/"): {-1}}
    pid: int | None = None
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            try:
                pid = int(line[1:])
            except ValueError:
                pid = None
        elif line.startswith("n/") and pid is not None:
            try:
                observed.setdefault(Path(line[1:]).resolve(), set()).add(pid)
            except OSError:
                continue
    return observed


def foreign_worktree_occupant(worktree: Path) -> int | None:
    """pid of a live process OUTSIDE this process's own lineage with cwd at or under
    `worktree`; -1 when the probe was unavailable (fail closed: caller must not supersede);
    None when no foreign process occupies the worktree."""
    try:
        root = worktree.resolve()
    except OSError:
        return -1
    lineage = _ancestor_pids()
    for cwd, pids in _process_cwds().items():
        if -1 in pids:
            return -1
        if cwd != root and root not in cwd.parents:
            continue
        # EVERY pid at this cwd is a candidate, not just one: the caller runs inside the worktree
        # it probes, so it routinely shares the cwd with the occupant it is looking for. `sorted`
        # only makes the choice among several foreign occupants deterministic.
        foreign = sorted(pids - lineage)
        if foreign:
            return foreign[0]
    return None


def linked_worktree_roots(root: Path) -> set[Path]:
    """Every LINKED worktree of `root` — the ones that nest *inside* it are what matter.

    `git worktree list --porcelain` emits `worktree <abspath>` records, the first of which is the
    main checkout itself. That first record is excluded: it is `root`, not a region to skip.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            cwd="/",
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    found: set[Path] = set()
    for line in out.splitlines():
        if not line.startswith("worktree "):
            continue
        try:
            path = Path(line[len("worktree ") :]).resolve()
        except OSError:
            continue
        if path != root:
            found.add(path)
    return found


#: Interactive agent runtimes. The ideal's subject is "an INTERACTIVE SESSION's cwd", and that
#: precision is what keeps this guard from firing constantly: measured live on the operator host,
#: 5 processes sat in tracked parts of the live checkout, but only ONE was a session — the others
#: were a long-running MCP server and a static file server, which are not what the fleet is being
#: asked to stop rewriting under. Counting them would make "occupied" the modal state and the sync
#: organ would never converge again, which is the failure IF-LIVE-TREE-COHERENCE already records.
SESSION_RUNTIMES = ("claude", "codex", "gemini", "opencode")


def _is_session(pid: int) -> bool:
    """Whether `pid` is an interactive agent runtime rather than a service or a build."""
    try:
        comm = subprocess.run(
            ["ps", "-o", "comm=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd="/",
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False  # fail OPEN, consistent with this consumer's direction
    name = Path(comm.split()[0]).name if comm else ""
    return any(name == runtime or name.startswith(f"{runtime}-") for runtime in SESSION_RUNTIMES)


def _is_ignored(root: Path, cwd: Path) -> bool:
    """Whether git itself considers `cwd` ignored — asked, never guessed from a skip-list.

    Load-bearing because `reset --hard` / `stash push` / `switch` only rewrite TRACKED content —
    sync-release.sh says so in its own comment ("reset --hard leaves UNTRACKED runtime untouched").
    A process parked in a gitignored runtime directory therefore cannot be disrupted by any of
    them and is not an occupant in the sense this ideal means. Measured live: this dropped two
    codex plugin-cache processes under .agent-runtime/ that would otherwise have blocked sync.
    """
    try:
        rel = cwd.relative_to(root)
    except ValueError:
        return False
    if rel == Path("."):
        return False
    try:
        return (
            subprocess.run(
                ["git", "-C", str(root), "check-ignore", "-q", str(rel)],
                capture_output=True,
                timeout=10,
                check=False,
                cwd="/",
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def live_checkout_occupancy(root: Path) -> tuple[int | None, bool]:
    """`(occupant_pid, probe_available)` — the same answer as `live_checkout_occupant`, plus
    whether the probe could actually see anything.

    THE SECOND VALUE EXISTS BECAUSE FAILING OPEN IS SILENT. Both of this function's unavailability
    paths — an unresolvable root, and the `-1` sentinel `_process_cwds` returns when it cannot run
    at all — collapse into `None`, which is the same answer it gives for a genuinely free tree.
    Failing open is right (see below); failing open INDISTINGUISHABLY is not, because it means a
    host where the probe is broken reports the ideal upheld in exactly the words it uses when the
    ideal is upheld. Observed 2026-08-06 by driving the organ with the package unimportable: the
    probe printed `free`, the guard disarmed, and nothing anywhere said so.

    `live_checkout_occupant` remains the answer-only form for callers that do not care.

    Several things make this different from `foreign_worktree_occupant`, and all are load-bearing:

    LINKED WORKTREES ARE NOT THE CHECKOUT. The containment rule above ("cwd is at or under root")
    is correct for a leaf worktree and catastrophic for `$LIMEN_ROOT`, because ~16 of this host's
    worktrees nest *underneath* it at `.claude/worktrees/*`, `.worktrees/*`, `.codex/worktrees/*`.
    Any one of them holding a live session would report the checkout occupied, which is close to
    the modal state — so the guard would never let the sync organ run again. A true occupant is
    under `root` and under NO linked worktree.

    IT FAILS OPEN, inverting this module's sibling. `foreign_worktree_occupant` fails closed
    because its consumer *deletes*; a broken probe there can only refuse to destroy. This
    consumer's failure mode is the opposite: the sync organ silently never converging, which this
    fleet has already paid for once (the live checkout sat 120 commits behind, six days stale, and
    nothing read the log). `sync-release.sh` states its own contract in capitals — "It FAILS OPEN,
    always" — and this guard honours it. An unavailable probe means "proceed", never "skip".
    """
    try:
        root = root.resolve()
    except OSError:
        return None, False  # fail OPEN, and say the probe could not tell — see docstring
    linked = linked_worktree_roots(root)
    lineage = _ancestor_pids()
    for cwd, pids in _process_cwds().items():
        if -1 in pids:
            return None, False  # fail OPEN — the probe was unavailable, so it accuses no one
        if cwd != root and root not in cwd.parents:
            continue
        if any(cwd == w or w in cwd.parents for w in linked):
            continue  # a session in a nested worktree is isolated BY DESIGN, not contending
        if _is_ignored(root, cwd):
            continue  # untracked ground: a rewrite cannot reach it
        # Every pid here, not just one. The per-cwd exclusions above are properties of the
        # DIRECTORY and are settled once; lineage and session-ness are properties of the PROCESS,
        # so they must be asked of each occupant separately. Collapsing the two — testing one
        # arbitrary pid per directory — is what let the caller's own pid stand in for the session
        # it was meant to find and report the live checkout free. `sorted` for determinism.
        for pid in sorted(pids - lineage):
            if _is_session(pid):
                return pid, True
    return None, True


def live_checkout_occupant(root: Path) -> int | None:
    """pid of a foreign interactive session working in the LIVE CHECKOUT itself; None when free.

    The answer-only form of `live_checkout_occupancy`, which see for every reason this differs
    from `foreign_worktree_occupant`. Callers that must distinguish "free" from "could not tell"
    — anything that REPORTS, rather than merely proceeds — want the two-value form instead.
    """
    return live_checkout_occupancy(root)[0]
