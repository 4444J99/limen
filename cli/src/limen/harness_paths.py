"""Resolve the Claude Code harness runtime root — the one place that knows where it lives.

The harness keeps its per-session state (transcripts, plan files, background-job scratch)
outside the workspace.  It historically lived at ``~/.claude``; it now lives at a repo-local
``<repo>/.agent-runtime/claude`` tree.  Both layouts occur in the wild, sometimes on the same
host, and the harness may move again.

Before this module the location was hard-coded in ten places, so when it moved every consumer
went quietly blind at once: ``action_admission`` stopped recognising plan-file writes as harness
state (breaking plan mode), CONTINUITY globbed an empty directory while still reporting ``ok``,
and the untiered-fan-out audit silently found no sessions.  An undeclared dependency on another
product's internal layout cannot be fixed one instance at a time — declare it once, resolve it
here, and let :mod:`scripts.harness-root-probe` fail loudly the next time it moves.

Stdlib-only on purpose: the admission hook and standalone scripts import this on paths where the
parameter layer is not available.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Operator override.  Declared in ``institutio/governance/parameters.yaml`` as CLAUDE_HARNESS_ROOT.
HARNESS_ROOT_ENV = "LIMEN_CLAUDE_HARNESS_ROOT"

#: Repo-relative harness tree, current layout.
REPO_RUNTIME_PARTS = (".agent-runtime", "claude")

#: Session-metadata children the harness writes into, whichever root is live.
SESSION_DIR_NAMES = ("projects", "plans", "jobs")


def _repo_root(repo_root: Path | None = None) -> Path:
    """Best-effort workspace root: explicit argument, then ``LIMEN_ROOT``, then cwd."""

    if repo_root is not None:
        return Path(repo_root).expanduser()
    return Path(os.environ.get("LIMEN_ROOT", ".")).expanduser()


def _shared_checkout(repo_root: Path) -> Path | None:
    """The main checkout backing ``repo_root`` when it is a ``.claude/worktrees/<name>`` worktree.

    Sessions routinely run isolated in a worktree while the harness keeps writing transcripts to
    the shared checkout's tree.  Without this, a reader running from a worktree resolves to its own
    empty ``.agent-runtime`` and reports "no transcripts" while the real corpus sits one level up —
    the same silent-blindness failure this module exists to prevent, one directory over.
    """

    parts = repo_root.parts
    for index in range(len(parts) - 1, 0, -1):
        if parts[index] == "worktrees" and parts[index - 1] == ".claude":
            return Path(*parts[: index - 1])
    return None


def _is_live(root: Path) -> bool:
    """True when ``root`` actually holds transcripts.

    Existence is not liveness: the old ``~/.claude/projects`` directory survives a relocation as
    an empty shell, which is exactly how the move went undetected.  Presence of at least one
    transcript is the honest predicate.
    """

    projects = root / "projects"
    if not projects.is_dir():
        return False
    try:
        return next(projects.glob("*/*.jsonl"), None) is not None
    except OSError:
        return False


def candidate_roots(home: Path | None = None, repo_root: Path | None = None) -> tuple[Path, ...]:
    """Every harness root worth considering, most-current first.

    Order is deliberate: the repo-local tree is the current layout, so it wins ties.  The env
    override, when set, precedes both and is trusted without a liveness check — an operator
    pointing at a fresh root must not be second-guessed.
    """

    roots: list[Path] = []
    override = os.environ.get(HARNESS_ROOT_ENV, "").strip()
    if override:
        roots.append(Path(override).expanduser())
    workspace = _repo_root(repo_root).resolve(strict=False)
    roots.append(workspace / Path(*REPO_RUNTIME_PARTS))
    shared = _shared_checkout(workspace)
    if shared is not None:
        roots.append(shared / Path(*REPO_RUNTIME_PARTS))
    roots.append((home or Path.home()).expanduser() / ".claude")

    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return tuple(unique)


def harness_roots(home: Path | None = None, repo_root: Path | None = None) -> tuple[Path, ...]:
    """Every candidate root that exists on disk, most-current first.

    Callers that must accept writes (admission) use this rather than :func:`harness_root`: a
    session may legitimately write to either layout, and denying the live one is the whole bug
    this module exists to prevent.
    """

    return tuple(root for root in candidate_roots(home, repo_root) if root.is_dir())


def harness_root(home: Path | None = None, repo_root: Path | None = None) -> Path:
    """The single root to read from — first live candidate, else first existing, else the newest layout.

    Readers (transcript scanners, usage accounting) want one answer.  Falling back to the
    most-current layout when nothing is live keeps the return type total, and the liveness probe
    is what turns "nothing is live" into a visible failure instead of a silent empty scan.
    """

    candidates = candidate_roots(home, repo_root)
    for root in candidates:
        if _is_live(root):
            return root
    for root in candidates:
        if root.is_dir():
            return root
    return candidates[0]


def harness_dir(name: str, home: Path | None = None, repo_root: Path | None = None) -> Path:
    """A named session-metadata child (``projects`` / ``plans`` / ``jobs``) of the live root."""

    return harness_root(home, repo_root) / name


def session_dirs(home: Path | None = None, repo_root: Path | None = None) -> tuple[Path, ...]:
    """Session-metadata directories across *every candidate* root, existing or not.

    The admission carve-out consumes this: harness-directed writes are not workspace mutations,
    and that holds for whichever layout the running harness happens to use.

    Deliberately built from :func:`candidate_roots` rather than :func:`harness_roots` — the very
    first plan-file write *creates* the directory, so gating the carve-out on the directory
    already existing would deny exactly the write that establishes it.
    """

    return tuple(root / name for root in candidate_roots(home, repo_root) for name in SESSION_DIR_NAMES)


def is_session_path(path: Path) -> bool:
    """True when ``path`` sits under a harness session directory *by shape*, at any root.

    Complements the absolute-root check in :func:`session_dirs`, which can only be as good as the
    resolved repo root — and the admission hook may run with an arbitrary cwd and no ``LIMEN_ROOT``.
    Matching the layout instead keeps the carve-out correct wherever the harness put its tree.

    The match is anchored on *consecutive* segments (``.agent-runtime/claude/plans`` or
    ``.claude/plans``), never a bare ``plans`` component, so an ordinary workspace directory that
    merely happens to be called ``plans`` or ``jobs`` is not mistaken for harness state.
    """

    parts = path.parts
    for index, part in enumerate(parts):
        if part == ".claude" and index + 1 < len(parts) and parts[index + 1] in SESSION_DIR_NAMES:
            return True
        if (
            part == REPO_RUNTIME_PARTS[0]
            and index + 2 < len(parts)
            and parts[index + 1] == REPO_RUNTIME_PARTS[1]
            and parts[index + 2] in SESSION_DIR_NAMES
        ):
            return True
    return False


def transcript_glob(home: Path | None = None, repo_root: Path | None = None) -> str:
    """Glob matching one session transcript per project scope, under the live root."""

    return str(harness_dir("projects", home, repo_root) / "*" / "*.jsonl")


def liveness(home: Path | None = None, repo_root: Path | None = None) -> dict:
    """Describe which roots exist and which hold transcripts.

    The probe script renders this; keeping the shape here means the sensor and any future
    consumer agree on what "the harness moved" looks like without re-deriving it.
    """

    rows = []
    for root in candidate_roots(home, repo_root):
        projects = root / "projects"
        try:
            count = sum(1 for _ in projects.glob("*/*.jsonl")) if projects.is_dir() else 0
        except OSError:
            count = 0
        rows.append({"root": str(root), "exists": root.is_dir(), "transcripts": count})
    resolved = harness_root(home, repo_root)
    return {
        "resolved": str(resolved),
        "resolved_live": _is_live(resolved),
        "candidates": rows,
        "override_env": HARNESS_ROOT_ENV,
        "override_set": bool(os.environ.get(HARNESS_ROOT_ENV, "").strip()),
    }


__all__ = [
    "HARNESS_ROOT_ENV",
    "REPO_RUNTIME_PARTS",
    "SESSION_DIR_NAMES",
    "candidate_roots",
    "harness_dir",
    "harness_root",
    "harness_roots",
    "is_session_path",
    "liveness",
    "session_dirs",
    "transcript_glob",
]
