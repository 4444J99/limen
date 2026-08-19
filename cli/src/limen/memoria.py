"""MEMORIA — the single-writer record-keeper for the memory dir (MEMORY.md + its atoms).

The disease this dissolves is the board's disease one domain over. `tasks.yaml` had ~32
uncoordinated writers; the memory dir has every session — each one appending its own atom file and
hand-editing `MEMORY.md`'s curated index, racing the same read-modify-write on a shared blob. The
cure is identical: sessions stop writing memory directly and instead APPEND one immutable *memory
ticket* to a lock-free inbox; exactly **one** keeper (TABVLARIVS, the same record-keeper that drains
the board) folds the tickets in on its beat, under a lock, and is the only process that ever writes
the memory dir. This module is `limen.tabularius`'s pattern — inbox → drain → quarantine → apply →
archive → receipt — but over the memory dir, not the board; it deliberately does **not** reuse the
board-bound engine (a memory atom is a markdown file + an index line, not a `Task` on `tasks.yaml`).

Out-of-repo BY DESIGN: a memory ticket's body is memory *content* (PII-class prose about the operator
and his life) and must never touch git. The inbox, archive, rejected, and receipts all live under the
memory dir — the absolute host path is identical from every worktree, so a ticket submitted from an
isolated worktree drains into the same real memory the live session reads. Only slugs and content
hashes are ever recorded in the receipts; body text stays local.

Ticket lifecycle (all under `<memdir>/`)::

    .covenant-inbox/<id>.json  --drain-->  applied  → .covenant-archive/   (the event log)
                                           rejected → .covenant-rejected/  (+ <id>.reason.txt)
                                           receipt  → .covenant-receipts.jsonl  (slug + hash only)

Design invariants, each carried over from a shipped safety precedent:
  * **A session never touches the memory dir.** It calls `submit_memory_ticket`, an exclusive atomic
    `os.link` create into the inbox — no read, no lock. (The board's `submit_ticket` invariant.)
  * **One bad ticket never rejects the batch.** Each ticket is parsed + applied individually; a bad
    one is quarantined to `.covenant-rejected/` with a `.reason.txt` and the rest still land.
  * **The curated order of MEMORY.md is meaning — never re-sort it.** An update REPLACES the atom's
    index line IN PLACE; a new atom APPENDS one. The keeper never reorders the surrounding lines.
  * **Never dead-stop the beat.** If the lock is held, the drain defers to the next beat.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

KEEPER = "tabularius"  # the record-keeper that owns the write; MEMORIA is its second lane
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")  # safe kebab filename stem — no path separators

# Break-glass escape hatch for the covenant write guard (armed in PR 6). Declared here now, ahead of
# arming, so the parameter is a real reader and not an orphan declaration. Consulted as a no-op guard
# bypass constant: the MEMORIA lane has no write guard yet, so this only records the operator's intent
# for the future hook to honor. Never gates a drain in this PR.
ALLOW_COVENANT_WRITE_ENV = "LIMEN_ALLOW_COVENANT_WRITE"


def covenant_write_allowed() -> bool:
    """Read the break-glass escape hatch (`LIMEN_ALLOW_COVENANT_WRITE`).

    A no-op guard-bypass constant in this PR: the MEMORIA drain has no write guard to bypass yet, so
    this value is not consulted to gate anything. It exists so the parameter has a live reader before
    PR 6 arms the write guard that will actually honor it.
    """
    return os.environ.get(ALLOW_COVENANT_WRITE_ENV, "0") == "1"


class MemoryTicket(BaseModel):
    """One immutable unit of memory work a session hands the record-keeper.

    A session builds a MemoryTicket describing an atom it wants remembered and drops it into the inbox
    via `submit_memory_ticket`. The keeper folds it into the memory dir on its next beat: creating or
    updating `<slug>.md` and its `MEMORY.md` index line. `body` is the verbatim atom content when the
    session authored it; when absent the keeper synthesizes the standard frontmatter + `desc` body.
    """

    ticket_id: str
    timestamp: datetime
    agent: str
    session_id: str = "unknown"
    slug: str  # safe kebab filename stem (validated) — becomes <slug>.md
    title: str
    desc: str
    body: str | None = None
    star: bool = False
    links: list[str] = []
    type: str = "project"
    op: str = "upsert"

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, value: str) -> str:
        if not _SLUG_RE.match(value):
            raise ValueError(
                f"invalid memory slug {value!r}: must be lowercase kebab-case ([a-z0-9] words joined "
                "by single hyphens), no path separators or dots"
            )
        return value

    @field_validator("desc")
    @classmethod
    def _validate_desc(cls, value: str) -> str:
        """Strip embedded newlines from desc so it never corrupts the single-line MEMORY.md index.

        The index format is `- [<title>](<slug>.md) — <desc>` — a single line. An embedded `\n` or
        `\r\n` would split that line verbatim into MEMORY.md, corrupting the index in a way that
        persists across re-drains (the marker still matches the broken line). Replace any run of
        newline characters with a single space so the line remains intact. Matches the safety intent
        of the slug validator, but strips rather than rejects so programmatic callers with accidental
        newlines don't lose the ticket entirely.
        """
        return re.sub(r"[\r\n]+", " ", value).strip()


def new_ticket_id(session_id: str = "unknown", now: datetime | None = None) -> str:
    """A sortable, collision-free ticket id: `<utc-timestamp>-<session>-<rand>` — the same shape as
    the board keeper's, so a plain filename sort is chronological and two same-microsecond tickets
    never collide."""
    import uuid

    now = now or datetime.now(timezone.utc)
    safe_session = "".join(c if c.isalnum() or c in "._-" else "_" for c in session_id)[:40]
    return f"{now.strftime('%Y%m%dT%H%M%S_%f')}Z-{safe_session}-{uuid.uuid4().hex[:8]}"


# --- memory-dir geometry -------------------------------------------------------------------------
def resolve_memdir(memdir: Path | str | None = None) -> Path:
    """Resolve the memory dir the same way scripts/evocator.py does — never pin.

    `LIMEN_MEMORY_DIR` overrides everything (tests point this at a temp dir). Otherwise it is derived
    from the workspace: `~/.claude/projects/<workspace-slug>/memory`, where the slug is the workspace
    path with '/' → '-'. `scripts/covenant.py` will own this derivation in PR 6; until it exists we
    inline the identical semantics.
    """
    if memdir is not None:
        return Path(memdir).expanduser()
    env = os.environ.get("LIMEN_MEMORY_DIR")
    if env:
        return Path(env).expanduser()
    workdir = Path(os.environ.get("LIMEN_WORKDIR", Path.home() / "Workspace" / "limen")).expanduser()
    slug = str(workdir).replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug / "memory"


def _inbox(memdir: Path) -> Path:
    return memdir / ".covenant-inbox"


def _archive(memdir: Path) -> Path:
    return memdir / ".covenant-archive"


def _rejected(memdir: Path) -> Path:
    return memdir / ".covenant-rejected"


def _receipts(memdir: Path) -> Path:
    return memdir / ".covenant-receipts.jsonl"


def _lockfile(memdir: Path) -> Path:
    return memdir / ".covenant.lock"


def _index(memdir: Path) -> Path:
    return memdir / "MEMORY.md"


def submit_memory_ticket(ticket: MemoryTicket, memdir: Path | str | None = None) -> Path:
    """Append a memory ticket to the inbox — a session's *only* memory-write surface.

    Exclusive + atomic: write a temp file, fsync, then `os.link` it into place. `os.link` fails if the
    destination exists, so a duplicate `ticket_id` raises instead of clobbering and a reader can never
    observe a half-written ticket. No lock, no memdir reads — many sessions submit concurrently without
    contending. Dirs are created 0700 (the memory dir holds PII-class content).
    """
    inbox = _inbox(resolve_memdir(memdir))
    inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = inbox / f"{ticket.ticket_id}.json"
    fd, tmp = tempfile.mkstemp(dir=inbox, prefix=f".{ticket.ticket_id}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(ticket.model_dump_json())
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, dest)  # atomic exclusive create — raises FileExistsError on a duplicate id
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return dest


@dataclass
class MemoryDrainResult:
    """The outcome of one memory drain pass — counts only, safe to log (no body text)."""

    pending: int = 0
    applied: int = 0
    rejected: int = 0
    wrote: bool = False
    deferred: bool = False
    note: str = ""
    applied_slugs: list[str] = field(default_factory=list)
    rejected_ids: list[str] = field(default_factory=list)


def pending_count(memdir: Path | str | None = None) -> int:
    inbox = _inbox(resolve_memdir(memdir))
    return len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0


def _synthesize_atom(ticket: MemoryTicket) -> str:
    """Build the standard memory-file content when the session did not author a verbatim body:
    the `--- name/description/metadata.type ---` frontmatter followed by the `desc` as the body."""
    lines = [
        "---",
        f"name: {ticket.slug}",
        f"description: {json.dumps(ticket.desc, ensure_ascii=False)}",
        "metadata:",
        "  node_type: memory",
        f"  type: {ticket.type}",
        "---",
        "",
        ticket.desc,
        "",
    ]
    return "\n".join(lines)


def _index_line(ticket: MemoryTicket) -> str:
    """The MEMORY.md index line: `- [<title>](<slug>.md) — <desc>`, star flag prefixing the title."""
    title = f"★{ticket.title}" if ticket.star else ticket.title
    return f"- [{title}]({ticket.slug}.md) — {ticket.desc}"


def _atomic_write(path: Path, text: str, *, mode: int = 0o600) -> None:
    """Crash-/race-safe write via temp file + os.replace, chmod to `mode`. Mirrors io.atomic_write_text
    but chmods the result (memory atoms are 0600 — PII-class local content)."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _replace_or_append_index_line(index_text: str, ticket: MemoryTicket) -> tuple[str, bool]:
    """Return (new_index_text, created). REPLACE the atom's line IN PLACE if `(<slug>.md)` already
    appears — preserving the curated order of every surrounding line byte-for-byte — else APPEND the
    new line. Never re-sorts."""
    new_line = _index_line(ticket)
    marker = f"({ticket.slug}.md)"
    lines = index_text.splitlines(keepends=True)
    trailing_newline = index_text.endswith("\n") or index_text == ""
    for i, line in enumerate(lines):
        if marker in line:
            suffix = "\n" if line.endswith("\n") else ""
            lines[i] = new_line + suffix
            return "".join(lines), False
    # append — keep the file's newline discipline; ensure a separating newline before the new line
    body = index_text
    if body and not body.endswith("\n"):
        body += "\n"
    body += new_line + ("\n" if trailing_newline or not index_text else "")
    return body, True


def _apply_ticket(ticket: MemoryTicket, memdir: Path) -> tuple[str, str]:
    """Fold one valid ticket into the memory dir. Returns (op, body_hash) where op is
    'created'|'updated' and body_hash is the sha256 of the final atom content (hashes + slugs only,
    never body text, are recorded). Writes the atom atomically 0600 and rewrites MEMORY.md in place
    only when the index actually changed."""
    atom_path = memdir / f"{ticket.slug}.md"
    atom_existed = atom_path.exists()

    if ticket.body is not None:
        atom_content = ticket.body
    elif atom_existed:
        # update with no new body: leave the existing atom content untouched
        atom_content = atom_path.read_text(encoding="utf-8")
    else:
        atom_content = _synthesize_atom(ticket)

    # write the atom only when its content changes (idempotent re-drain writes nothing)
    if not atom_existed or atom_content != atom_path.read_text(encoding="utf-8"):
        _atomic_write(atom_path, atom_content)
    else:
        os.chmod(atom_path, 0o600)

    body_hash = hashlib.sha256(atom_content.encode("utf-8")).hexdigest()

    index_path = _index(memdir)
    index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    new_index, _created_line = _replace_or_append_index_line(index_text, ticket)
    if new_index != index_text:
        _atomic_write(index_path, new_index)

    op = "created" if not atom_existed else "updated"
    return op, body_hash


def _quarantine(rejected: list[tuple[Path, str]], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for p, reason in rejected:
        try:
            (dest_dir / f"{p.name}.reason.txt").write_text(reason)
            p.rename(dest_dir / p.name)
        except OSError:
            pass


def _move(paths: list[Path], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for p in paths:
        try:
            p.rename(dest_dir / p.name)
        except OSError:
            pass


def _parse_pending(inbox: Path) -> tuple[list[tuple[Path, MemoryTicket]], list[tuple[Path, str]]]:
    """Load every inbox ticket, splitting parseable from garbage, then order the good ones by
    (timestamp, ticket_id) so concurrent submissions replay in a single deterministic total order."""
    good: list[tuple[Path, MemoryTicket]] = []
    bad: list[tuple[Path, str]] = []
    for p in sorted(inbox.glob("*.json")):
        try:
            good.append((p, MemoryTicket.model_validate_json(p.read_text(encoding="utf-8"))))
        except Exception as exc:  # a torn/invalid ticket is quarantined, never fatal
            bad.append((p, f"unparseable/invalid memory ticket: {exc}"))
    good.sort(key=lambda pt: (pt[1].timestamp, pt[1].ticket_id))
    return good, bad


def drain_memory_once(memdir: Path | str | None = None, *, dry_run: bool = False) -> MemoryDrainResult:
    """Drain the memory inbox once: fold every pending ticket into the memory dir, append receipts,
    archive the applied tickets. An empty inbox is an instant no-op (no lock, no memory I/O) — safe to
    run every beat while no sessions submit yet.

    The whole parse→apply→archive runs under an exclusive flock on `<memdir>/.covenant.lock`, and the
    keeper is the only drainer, so there is no read-modify-write race with a concurrent drain. A held
    lock defers to the next beat rather than blocking.
    """
    memdir = resolve_memdir(memdir)
    inbox = _inbox(memdir)
    if not inbox.is_dir():
        return MemoryDrainResult(note="inbox empty")

    pending_hint = len(list(inbox.glob("*.json")))
    if pending_hint == 0:
        return MemoryDrainResult(note="inbox empty")

    if dry_run:
        good, bad = _parse_pending(inbox)
        return MemoryDrainResult(
            pending=len(good) + len(bad),
            applied=len(good),
            rejected=len(bad),
            note=f"dry-run: {len(good)} applicable, {len(bad)} unparseable",
        )

    lockfile = _lockfile(memdir)
    lockfile.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(lockfile, "w") as lf:
        try:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return MemoryDrainResult(
                pending=pending_hint, deferred=True, note="memory lock held; deferred to next beat"
            )

        good, bad = _parse_pending(inbox)
        pending = len(good) + len(bad)
        if pending == 0:
            return MemoryDrainResult(note="inbox empty")

        applied: list[Path] = []
        rejected: list[tuple[Path, str]] = list(bad)
        receipts: list[dict[str, Any]] = []
        wrote = False
        for p, ticket in good:
            try:
                op, body_hash = _apply_ticket(ticket, memdir)
            except Exception as exc:  # one bad ticket never rejects the batch
                rejected.append((p, f"apply failed: {exc}"))
                continue
            applied.append(p)
            wrote = True
            receipts.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "slug": ticket.slug,
                    "op": op,
                    "ticket_id": ticket.ticket_id,
                    "body_hash": body_hash,
                    "keeper": KEEPER,
                }
            )

        if receipts:
            with open(_receipts(memdir), "a", encoding="utf-8") as rf:
                for r in receipts:
                    rf.write(json.dumps(r, ensure_ascii=False) + "\n")

        _move(applied, _archive(memdir))
        _quarantine(rejected, _rejected(memdir))

    return MemoryDrainResult(
        pending=pending,
        applied=len(applied),
        rejected=len(rejected),
        wrote=wrote,
        note=("folded" if wrote else "no memory change"),
        applied_slugs=[r["slug"] for r in receipts],
        rejected_ids=[p.stem for p, _ in rejected],
    )
