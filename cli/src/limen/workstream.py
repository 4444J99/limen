"""Workstream channels — the PURPOSE partition of the board.

Anthony's "channels": a durable, single-purpose lane a worker session draws from — the axis ABOVE
the vendor ``target_agent`` lane. The 10-20-mixed-PRs sprawl came from having NO such axis: the
backlog was one undifferentiated grab-bag, so a session reserved whatever was in front of it. A
``workstream`` field on each :class:`~limen.models.Task` plus the invariant "one worker session
draws OPEN tasks from ONE workstream only" (enforced by the scoped cell conductor,
``cell conduct <slug> --workstream <handle>``) dissolves it.

The roster is DERIVED, never a hand-kept menu (the standing "never need him to speak again"
directive): the DOMAIN channels ARE the institutional organs in ``organ-ladder.json`` — add an
organ, get a channel, free — and the OPERATIONAL channels are the cross-cutting process lanes
Anthony named (conductor / contributions / correspondence / prompt-parity). The literal word
"channel" is deliberately NOT the code token: it already means FLAME/CORPUS/MEMORY truth
propagation in ``scripts/evocator.py`` and product × distribution in ``scripts/launch-organ.py``.
The converged term is ``workstream`` — it already names the scaffolder (``limen workstream``), the
private packet (``.limen-workstream/``) and ``docs/lanes/`` — so this promotes that
already-declared-but-empty lane concept into a real, enforced field.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from limen.models import LimenFile, Task


@dataclass(frozen=True)
class Channel:
    """One durable purpose-lane. ``source`` is ``"organ"`` (derived from organ-ladder.json) or
    ``"meta"`` (a hand-listed operational lane — the only channels NOT auto-derived)."""

    handle: str
    title: str
    source: str
    detail: str = ""
    aliases: tuple[str, ...] = ()


# Operational (non-organ) channels — the cross-cutting PROCESS lanes Anthony named in the
# channel-decomposition session (2026-07-02). These are the ONLY hand-listed channels, because they
# are not institutional organs; every DOMAIN channel derives from organ-ladder.json below.
_META_CHANNELS: tuple[Channel, ...] = (
    Channel(
        "conductor",
        "Conductor",
        "meta",
        "Idea intake + Q&A + packetization. Never executes a raw prompt; derives bounded tasks and "
        "tags each with its workstream, then seeds the board or spins a scoped worker.",
        ("intake", "brainstorm"),
    ),
    Channel(
        "contributions",
        "Contributions",
        "meta",
        "The code/PR lane — one worker draining contribution tasks, never mixing in mail or prompts.",
        ("contrib", "contribution", "code", "prs", "pr"),
    ),
    Channel(
        "correspondence",
        "Correspondence",
        "meta",
        "The mail lane — drafts, replies, the obligations ledger. Maps to the C_MAIL beat.",
        ("mail", "email", "comms", "inbox"),
    ),
    Channel(
        "prompt-parity",
        "Prompt-parity",
        "meta",
        "The completeness lane — proves every prompt Anthony gave reached the parity it was meant to "
        "reach. Same shape as no-tasks-on-me.sh / the every-ask ledger.",
        ("prompts", "prompt", "parity"),
    ),
)

# Aliases folded onto derived ORGAN channels so Anthony's spoken vocabulary resolves to the canonical
# pillar handle (his word works at the surface; the code converges underneath).
_ORGAN_ALIASES: dict[str, tuple[str, ...]] = {
    "financial": ("revenue", "money", "cash", "finance"),
}

UNASSIGNED = "(unassigned)"


def normalize_handle(value: str | None) -> str | None:
    """Kebab-normalize a raw handle: lowercase, runs of non-alphanumerics → '-'. Empty → None."""
    if not value:
        return None
    handle = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
    return handle or None


def _organ_channels(root: Path) -> list[Channel]:
    """One channel per DISTINCT organ pillar in organ-ladder.json (deduped, first-seen order)."""
    ladder = Path(root) / "organ-ladder.json"
    if not ladder.is_file():
        return []
    try:
        data = json.loads(ladder.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    seen: dict[str, Channel] = {}
    for organ in data.get("organs", []):
        pillar = normalize_handle(organ.get("pillar"))
        if not pillar or pillar in seen:
            continue
        seen[pillar] = Channel(
            handle=pillar,
            title=str(organ.get("organ") or pillar.title()),
            source="organ",
            detail=str(organ.get("macro") or organ.get("note") or ""),
            aliases=_ORGAN_ALIASES.get(pillar, ()),
        )
    return list(seen.values())


def derived_channels(root: Path) -> list[Channel]:
    """The canonical roster: operational meta-lanes + one channel per institutional organ.

    Derived at READ time from organ-ladder.json so a new organ IS a new channel with no code edit
    (the "never need him to speak again" property). Meta-lanes win a handle collision with an organ.
    """
    channels: list[Channel] = list(_META_CHANNELS)
    have = {c.handle for c in channels}
    for c in _organ_channels(root):
        if c.handle not in have:
            channels.append(c)
            have.add(c.handle)
    return channels


def _alias_map(root: Path) -> dict[str, str]:
    """{normalized handle-or-alias → canonical handle} across the whole derived roster."""
    m: dict[str, str] = {}
    for c in derived_channels(root):
        m[c.handle] = c.handle
        for a in c.aliases:
            key = normalize_handle(a)
            if key:
                m[key] = c.handle
    return m


def canonical_handle(value: str | None, root: Path) -> str | None:
    """Normalize a raw handle and resolve an alias (e.g. ``revenue`` → ``financial``). An unknown
    handle is returned normalized-but-unresolved so ad-hoc channels still work (they just show up
    outside the derived roster in the projection)."""
    h = normalize_handle(value)
    if h is None:
        return None
    return _alias_map(root).get(h, h)


def channel_of(task: Task, root: Path) -> str:
    """The task's channel: explicit ``workstream`` field wins; else infer from a label that matches a
    known handle/alias (keeps pre-field tasks visible); else :data:`UNASSIGNED`."""
    explicit = canonical_handle(getattr(task, "workstream", None), root)
    if explicit:
        return explicit
    amap = _alias_map(root)
    for label in task.labels:
        h = normalize_handle(label)
        if h and h in amap:
            return amap[h]
    return UNASSIGNED


def group_by_channel(limen: LimenFile, root: Path) -> dict[str, list[Task]]:
    """{channel handle → tasks}, in roster order, with any inferred-only handles then UNASSIGNED
    last. Every derived channel appears even when empty, so the projection is a stable scoreboard."""
    order = [c.handle for c in derived_channels(root)]
    buckets: dict[str, list[Task]] = {h: [] for h in order}
    for task in limen.tasks:
        buckets.setdefault(channel_of(task, root), []).append(task)
    ordered: dict[str, list[Task]] = {h: buckets.get(h, []) for h in order}
    for h, tasks in buckets.items():
        if h not in ordered and h != UNASSIGNED:
            ordered[h] = tasks
    ordered[UNASSIGNED] = buckets.get(UNASSIGNED, [])
    return ordered


def filter_board(limen: LimenFile, handle: str, root: Path) -> LimenFile:
    """A board copy carrying ONLY the given channel's tasks — the substrate for the
    one-worker-one-workstream invariant. The scoped ``cell conduct --workstream`` conductor reads
    this as its tasks file, so it structurally cannot reach another channel's work."""
    target = canonical_handle(handle, root)
    kept = [t for t in limen.tasks if channel_of(t, root) == target]
    return limen.model_copy(update={"tasks": kept})


def _counts(tasks: list[Task]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in tasks:
        counts[t.status] = counts.get(t.status, 0) + 1
    return counts


def roster_summary(limen: LimenFile, root: Path) -> dict:
    """JSON-able projection of the board by channel (for ``limen channels --json-output``)."""
    groups = group_by_channel(limen, root)
    meta = {c.handle: c for c in derived_channels(root)}
    channels = []
    for handle, tasks in groups.items():
        c = meta.get(handle)
        channels.append(
            {
                "handle": handle,
                "source": c.source if c else ("infer" if handle != UNASSIGNED else "none"),
                "title": c.title if c else handle,
                "counts": _counts(tasks),
                "total": len(tasks),
            }
        )
    return {"generated_from": "organ-ladder.json organs + operational meta-lanes", "channels": channels}


def print_channels(limen: LimenFile, root: Path, scope: str | None = None) -> None:
    """Human projection of the board by channel — the conductor's live scoreboard."""
    groups = group_by_channel(limen, root)
    meta = {c.handle: c for c in derived_channels(root)}
    scope_h = canonical_handle(scope, root) if scope else None
    print("Workstream channels — purpose partition (derived from organ-ladder.json + operational lanes)")
    print(f"{'CHANNEL':<16} {'SRC':<6} {'OPEN':>4} {'IP':>3} {'DONE':>5} {'TOTAL':>6}  TITLE")
    print("-" * 78)
    for handle, tasks in groups.items():
        if scope_h and handle != scope_h:
            continue
        c = meta.get(handle)
        src = c.source if c else ("infer" if handle != UNASSIGNED else "-")
        title = c.title if c else handle
        counts = _counts(tasks)
        done = counts.get("done", 0) + counts.get("archived", 0)
        print(
            f"{handle:<16} {src:<6} {counts.get('open', 0):>4} {counts.get('in_progress', 0):>3} "
            f"{done:>5} {len(tasks):>6}  {title}"
        )
    if scope_h:
        print()
        for t in groups.get(scope_h, []):
            title = (t.title[:50] + "…") if len(t.title) > 51 else t.title
            print(f"  {t.id:<12} {t.status:<12} {t.target_agent:<8} {title}")
