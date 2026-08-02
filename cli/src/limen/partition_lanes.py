"""PARTNER-LANE derivation — the one place that answers "is this someone else's work?"

A partner lane is a repo where a named third party is attached AND the estate classes it
private. Both halves are already registered, so this module DERIVES and owns no list:

    constellation register  organs/consulting/constellation/registry.yaml
                            -> which repos have a named person attached (the third-party half)
    estate                  institutio/github/estate.yaml
                            -> classify_repo() -> class -> visibility (the private half)

WHY BOTH HALVES. Neither alone is the boundary:

  * Third-party-attached alone is too wide. Seven of the register's nine repos are listed in
    ``value-repos.json`` — collaborations the funding registry explicitly buys. Quarantining
    those would starve work the operator decided to fund.
  * Private-class alone is too wide in the other direction. ``organvm/domus-genoma`` is
    ``operation_private`` and entirely his; it is not somebody else's engagement.

The intersection is exactly the set the estate already annotates as "partner build lane":
``4444J99/victoroff-os`` and ``4444J99/sovereign-systems--elevate-align``.

THE INVARIANT THIS EXISTS TO ENFORCE (operator directive 2026-08-02: "there shouldn't be ANY
possibility of overlap between my work and client work"):

    A heuristic may never promote work across a partner boundary.
    Only an explicit registry decision may.

Explicit funding (a ``value-repos.json`` row) and an explicit ``--task <id>`` are the operator
deciding, which is not overlap. A free-text match on the word "blocker" is the machine deciding,
which is precisely the overlap being ruled out. ``_dispatch_focus_bucket`` had no way to express
this because it was a pure inclusion function: five independent ways to return "dispatch me
first" and no way to say "never". :func:`heuristics_may_promote` is that missing axis.

SLUG DRIFT IS PART OF THE DEFECT, NOT AN EDGE CASE. ``4444J99/victoroff-os`` was transferred out
of ``organvm`` in 2026-07 (estate.yaml repo_overrides, and the GitHub redirect is live), but the
board still carries the pre-transfer ``organvm/victoroff-os``. The estate's protective override
is keyed on the NEW slug, so the OLD slug misses it and falls through to the ``organvm/**`` glob
-> ``governed_public``. The same repository therefore reads private under one name and public
under the other, which is why every shipped estate predicate was blind to it while the note at
estate.yaml:750 had already written the hazard down. :func:`canonical_slug` closes that door by
matching on the repo tail, so a lane cannot be laundered by renaming its owner.

Tail matching is deliberately a SAFETY-WIDENING heuristic: it can only ever classify more repos
as partner, never fewer. That is the correct direction to be wrong in for a confidentiality
boundary, and it is the reason this module never uses tail matching to grant anything.

FAILURE POSTURE. If a registry cannot be read, the environment is broken, and the two consumers
want different things from that:

  * the predicate (``scripts/check-board-partition.py``) hard-fails, because an unverifiable
    boundary is not a green one;
  * dispatch keeps running but stops trusting its heuristics -- :func:`heuristics_may_promote`
    returns False for every task, so explicit value-repo matches still dispatch and incidental
    keyword promotion does not.

Fail-safe without being fail-dead: explicit decisions survive, guesses stop.
"""

from __future__ import annotations

import fnmatch
import functools
import os
from pathlib import Path
from typing import Any

__all__ = [
    "PartitionRegistryError",
    "canonical_slug",
    "heuristics_may_promote",
    "is_funded",
    "is_partner_lane",
    "partner_keywords",
    "partner_lanes",
    "repo_tail",
]


class PartitionRegistryError(RuntimeError):
    """A registry this boundary derives from is missing or unreadable."""


# The registries are CHECKOUT artifacts, not runtime data, so the checkout is located from THIS
# FILE and LIMEN_ROOT is only honoured when it actually holds them. This is the resolver discipline
# mail-beat.sh states outright: "The resolver is located from THIS FILE, never from $LIMEN_ROOT.
# LIMEN_ROOT is the runtime data root and a caller may legitimately point it at a directory with no
# scripts/". Defaulting to ~/Workspace/limen instead would make the boundary depend on one machine's
# layout -- it would resolve on the operator host and raise everywhere else, and since an
# unreadable registry vetoes every heuristic, that failure would silently starve dispatch on a
# fresh clone and in CI while passing its own tests on the host that does not need them.
_REGISTRY_MARKERS = (
    Path("institutio") / "github" / "estate.yaml",
    Path("organs") / "consulting" / "constellation" / "registry.yaml",
    Path("value-repos.json"),
)


def _holds_registries(candidate: Path) -> bool:
    return all((candidate / marker).exists() for marker in _REGISTRY_MARKERS)


def _root() -> Path:
    configured = os.environ.get("LIMEN_ROOT", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if _holds_registries(candidate):
            return candidate
    # cli/src/limen/partition_lanes.py -> limen -> src -> cli -> <checkout>
    checkout = Path(__file__).resolve().parents[3]
    if _holds_registries(checkout):
        return checkout
    # Neither resolved: hand back the configured root (or the checkout) so the caller raises a
    # PartitionRegistryError naming a real path instead of guessing a second location.
    return Path(configured).expanduser() if configured else checkout


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - PyYAML is a hard dependency of the CLI
        raise PartitionRegistryError(f"PyYAML unavailable: {exc}") from exc
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, ValueError) as exc:
        raise PartitionRegistryError(f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PartitionRegistryError(f"{path}: expected a mapping at the top level")
    return data


def repo_tail(repo: object) -> str:
    """The owner-independent name of a repo (``organvm/foo`` and ``4444J99/foo`` share a tail).

    Owner is exactly the part that a transfer changes, so the tail is what survives one.
    """
    value = str(repo or "").strip().lower()
    for prefix in ("git@github.com:", "https://github.com/", "http://github.com/", "github.com/"):
        if value.startswith(prefix):
            value = value.removeprefix(prefix)
            break
    if value.endswith(".git"):
        value = value[:-4]
    value = value.strip("/")
    return value.rsplit("/", 1)[-1] if value else ""


def _class_visibility(estate: dict[str, Any]) -> dict[str, str]:
    classes = estate.get("classes")
    if not isinstance(classes, dict):
        raise PartitionRegistryError("estate.yaml: classes block missing or malformed")
    out: dict[str, str] = {}
    for name, body in classes.items():
        if isinstance(body, dict):
            out[str(name)] = str(body.get("visibility") or "")
    return out


def _classify(repo: str, estate: dict[str, Any]) -> str | None:
    """Resolve a repo to its estate class the same way ``gitvs.classify_repo`` does.

    Reimplemented rather than imported because ``scripts/gitvs.py`` is not importable from the
    installed CLI package. The precedence is copied deliberately and is covered by a parity test
    (``test_partition_lanes.py``) that fails if gitvs and this drift apart: override row first
    (a durable per-repo human judgment), then the class globs.
    """
    # Case-insensitively, because the registries disagree on capitalisation: the constellation
    # register writes `4444J99/victoroff-os` and the board writes it lowercased, while
    # estate.yaml keys the protective override on the mixed-case spelling. A case-sensitive
    # lookup here silently returns a plausible, non-empty, WRONG lane set -- it drops exactly the
    # override rows that make a lane private, which is the failure this boundary cannot have.
    overrides = {str(key).strip().lower(): value for key, value in (estate.get("repo_overrides") or {}).items()}
    row = overrides.get(repo.strip().lower())
    if isinstance(row, dict) and row.get("class"):
        return str(row["class"])
    if isinstance(row, str) and row:
        return row
    best: tuple[int, str] | None = None
    for name, body in (estate.get("classes") or {}).items():
        if not isinstance(body, dict):
            continue
        for glob in body.get("match") or []:
            if fnmatch.fnmatch(repo.strip().lower(), str(glob).strip().lower()):
                # Most-specific (longest) glob wins, matching gitvs' ordering.
                score = len(str(glob))
                if best is None or score > best[0]:
                    best = (score, str(name))
    return best[1] if best else None


def _constellation(root: Path) -> tuple[tuple[str, frozenset[str]], ...]:
    """One (repo slug, keywords) pair per project that has a named third party attached."""
    path = root / "organs" / "consulting" / "constellation" / "registry.yaml"
    data = _load_yaml(path)
    people = data.get("people")
    if not isinstance(people, list):
        raise PartitionRegistryError(f"{path}: people block missing or malformed")
    projects: list[tuple[str, frozenset[str]]] = []
    for person in people:
        if not isinstance(person, dict):
            continue
        for project in person.get("projects") or []:
            if not isinstance(project, dict):
                continue
            repo = str(project.get("repo") or "").strip().lower()
            if not repo:
                # A project with no repo cannot be a lane; it has no artifact to partition.
                continue
            keywords = {
                text for keyword in project.get("keywords") or [] if (text := str(keyword or "").strip().lower())
            }
            projects.append((repo, frozenset(keywords)))
    return tuple(projects)


@functools.lru_cache(maxsize=8)
def _lanes(root_str: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    root = Path(root_str)
    estate = _load_yaml(root / "institutio" / "github" / "estate.yaml")
    visibility = _class_visibility(estate)
    projects = _constellation(root)

    lanes: set[str] = set()
    lane_keywords: set[str] = set()
    for repo, keywords in projects:
        cls = _classify(repo, estate)
        if cls and visibility.get(cls) == "private":
            lanes.add(repo)
            # Keywords count only for lanes that are actually partitioned. "chess" and "hokage"
            # belong to a funded collaboration, so treating them as leak markers would flag every
            # task that merely mentions chess.
            lane_keywords |= keywords

    tails = {repo_tail(repo) for repo in lanes} - {""}
    return frozenset(lanes), frozenset(tails), frozenset(lane_keywords)


def partner_lanes(root: Path | None = None) -> frozenset[str]:
    """Canonical slugs of every partner-private lane. Raises on an unreadable registry."""
    return _lanes(str(root or _root()))[0]


def partner_keywords(root: Path | None = None) -> frozenset[str]:
    """Keywords declared for partner-private lanes only (never for funded collaborations)."""
    return _lanes(str(root or _root()))[2]


def canonical_slug(repo: object, root: Path | None = None) -> str | None:
    """The partner lane this slug denotes, following a transfer, or None.

    ``organvm/victoroff-os`` and ``4444J99/victoroff-os`` both resolve to the lane, which is the
    whole point: the estate's protective override is keyed on the post-transfer slug and the
    board still carries the pre-transfer one.
    """
    tail = repo_tail(repo)
    if not tail:
        return None
    lanes, tails, _ = _lanes(str(root or _root()))
    if tail not in tails:
        return None
    slug = str(repo or "").strip().lower().strip("/")
    if slug in lanes:
        return slug
    for lane in sorted(lanes):
        if repo_tail(lane) == tail:
            return lane
    return None


def is_partner_lane(repo: object, root: Path | None = None) -> bool:
    """True when this repo is somebody else's engagement, under any owner it has ever had."""
    return canonical_slug(repo, root) is not None


@functools.lru_cache(maxsize=8)
def _funded_tails(root_str: str) -> frozenset[str]:
    """Repo tails the operator explicitly funds in ``value-repos.json``.

    Tail-keyed for the same reason :func:`canonical_slug` is: the board writes
    ``organvm/mirror-mirror`` while the funding registry writes ``4444J99/mirror-mirror``, and an
    exact-slug comparison would read a funded repo as unfunded.
    """
    import json

    path = Path(root_str) / "value-repos.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise PartitionRegistryError(f"{path}: {exc}") from exc
    tails: set[str] = set()
    for item in data.get("repos") or []:
        slug = item if isinstance(item, str) else (item or {}).get("repo")
        tail = repo_tail(slug)
        if tail:
            tails.add(tail)
    return frozenset(tails)


def is_funded(repo: object, root: Path | None = None) -> bool:
    """True when ``value-repos.json`` explicitly buys work on this repo."""
    tail = repo_tail(repo)
    return bool(tail) and tail in _funded_tails(str(root or _root()))


def heuristics_may_promote(repo: object, root: Path | None = None) -> bool:
    """May a heuristic (label, lifecycle term, id prefix, free text) promote this task?

    The missing axis in ``_dispatch_focus_bucket``, which is a pure inclusion function: five
    independent ways to say "dispatch me first" and no way to say "never".

    False for an UNFUNDED partner lane. Funding is the operator writing the repo down in
    ``value-repos.json``, which is an explicit decision and therefore not the accidental overlap
    this boundary exists to prevent -- four of the six partner lanes are funded products with a
    collaborator attached, and vetoing those would starve work the funding registry deliberately
    buys. Withholding only the HEURISTIC paths is what makes the invariant precise:

        a heuristic may never cross a partner boundary; an explicit registry decision may.

    False for everything when a registry cannot be read: a guess is exactly what must stop when
    the boundary is unverifiable, and explicit ``value-repos.json`` repo matches in
    ``_dispatch_focus_bucket`` still promote, so dispatch degrades rather than dying.
    """
    try:
        if not is_partner_lane(repo, root):
            return True
        return is_funded(repo, root)
    except PartitionRegistryError:
        return False
