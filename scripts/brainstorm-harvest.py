#!/usr/bin/env python3
"""
brainstorm-harvest — every conversation becomes an addressable extract, no reduction.

Generalizes the brainstorm-20260423 precedent (24 conversations → 934 atoms from ONE
export date) to the whole declared corpus estate. The multiverse contract, verbatim from
the operator: every session is a different experiment; preserve each in its own state and
let the convergence machinery (corpus-converge.py's DIVERGE → CONVERGE → ONE loop) derive
the ideal form downstream. This tool is the DIVERGE side: it reduces nothing.

Two passes, split by cost:

  mechanical (this tool, deterministic, free)
      One extract per thread — frontmatter (uid, provider, title, keywords, themes,
      entities), verbatim pair text, plus the corpus's own coarse action ledger as
      *candidate* atoms. CCE already normalized every
      provider into one contract (threads-index.json + pairs-index.json), so a single
      parser covers ChatGPT, Claude and Perplexity alike — no provider-native parsing.

  semantic (per-thread, model-driven, resumable)
      The eight brainstorm atom kinds (projects-to-start, decisions, tasks, vacuums,
      questions-unresolved, client-offerings, schema-proposals, functionality-to-repeat).
      Extracts are minted with `semantic_atoms: pending`; `--queue` lists what remains.
      Each thread's semantic pass rewrites only its own extract, so the sweep is
      checkpointed by construction and any session (or the beat) can drain it.

Stream assignment is deliberately part of the SEMANTIC pass, not this one — both
mechanical routes were tried and measured first (the shipped echo-clusterer fuses the
densely-vocabularied threads into one blob at every floor; CCE's per-pair "themes" are
frequency tokens, not topics). Extracts carry `stream: pending` as frontmatter so files
keep stable addresses when streams arrive.

Output lands in the PRIVATE store (never the public limen tree), declared in
institutio/governance/corpora.yaml as the `brainstorm-extracts` row:

    <store>/brainstorm-extracts/<corpus-id>/threads/NNN-<slug>.md
    <store>/brainstorm-extracts/<corpus-id>/atoms/candidate-actions.yaml
    <store>/brainstorm-extracts/<corpus-id>/index.yaml

Re-running the mechanical pass is drain-preserving: an extract whose frontmatter says
`semantic_atoms: done` is NEVER rewritten or deleted (the semantic pass owns it — even if
its source thread has vanished from the corpus, preservation beats parity and the index
marks it `source_present: false`). Only pending extracts are re-rendered, and new threads
are appended with fresh numbers so existing files keep stable addresses.

The index is a projection of extract frontmatter. The semantic pass rewrites only its own
extract file; `--sync-index` re-derives every index.yaml row (stream, semantic_atoms) from
the files, which is what shrinks `--queue`.

Usage:
  scripts/brainstorm-harvest.py --corpus chatgpt-local-session-memory
  scripts/brainstorm-harvest.py --all               # every harvestable session-memory corpus
  scripts/brainstorm-harvest.py --all --queue       # what still awaits the semantic pass
  scripts/brainstorm-harvest.py --sync-index        # index rows ← extract frontmatter
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus_resolve

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPORA_REGISTRY = REPO_ROOT / "institutio" / "governance" / "corpora.yaml"
ATOM_HOMING_REGISTRY = REPO_ROOT / "institutio" / "governance" / "atom-homing.yaml"
ATOM_CENSUS = REPO_ROOT / "institutio" / "governance" / "atom-census.yaml"

EXTRACTS_DIRNAME = "brainstorm-extracts"


def _atom_kinds() -> list[str]:
    """The eight-kind schema, DERIVED from atom-homing.yaml — never a second literal copy.

    The homing registry is the authority on which kinds exist, because it is the file that
    must declare a home for each one. A literal list here too is precisely how a ninth kind
    gets harvested into a store with nowhere to land. check-atom-homing.py check F holds
    this derivation in place.
    """
    doc = yaml.safe_load(ATOM_HOMING_REGISTRY.read_text(encoding="utf-8")) or {}
    kinds = list((doc.get("kinds") or {}).keys())
    if not kinds:
        raise SystemExit(f"no atom kinds declared in {ATOM_HOMING_REGISTRY}")
    return kinds


ATOM_KINDS = _atom_kinds()


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return re.sub(r"-{2,}", "-", value).strip("-") or "thread"


_HARVESTABLE_KINDS = {"session-memory", "atom-stream"}


def _registry() -> dict:
    return yaml.safe_load(CORPORA_REGISTRY.read_text(encoding="utf-8")) or {}


def _harvestable_corpora(doc: dict | None = None) -> dict[str, dict]:
    doc = doc if doc is not None else _registry()
    out = {}
    for cid, row in (doc.get("corpora") or {}).items():
        if row.get("harvestable") and row.get("kind") in _HARVESTABLE_KINDS:
            out[cid] = row
    return out


def _store_path(doc: dict, row: dict) -> Path:
    """Resolve a corpus row's on-disk location from its declared store + path.

    Roots come from the registry's stores table, never a literal — the
    check-corpora D-check bans a second copy of any store root."""
    store = (doc.get("stores") or {}).get(row.get("store") or "") or {}
    root = Path(str(store.get("root", ""))).expanduser()
    return root / str(row.get("path", ""))


def _load_corpus(corpus_dir: Path) -> tuple[list[dict], dict[str, list[dict]], list[dict]]:
    """threads, pairs grouped by thread_uid, and the coarse action ledger."""
    base = corpus_dir / "corpus"
    threads = json.loads((base / "threads-index.json").read_text(encoding="utf-8"))
    pairs = json.loads((base / "pairs-index.json").read_text(encoding="utf-8"))
    try:
        actions = json.loads((base / "action-ledger.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        actions = []
    by_thread: dict[str, list[dict]] = {}
    for p in pairs:
        by_thread.setdefault(p.get("thread_uid", ""), []).append(p)
    for rows in by_thread.values():
        rows.sort(key=lambda p: p.get("pair_id", ""))
    return threads, by_thread, actions


def _load_atom_stream(src: Path, sources: list[str]) -> tuple[list[dict], dict[str, list[dict]], list[dict]]:
    """Adapt a session-meta atom stream (one JSONL record per conversation turn) to the
    same (threads, by_thread, actions) shape the CCE corpora produce.

    Only sessions whose `source` is in the registry-declared harvest_sources allowlist
    are admitted — the stream also carries thousands of agent rollouts that are work
    logs, not brainstorms. Streaming parse: the file is ~1.36 GB but the allowlist
    keeps only a handful of sessions in memory. thread_uid = session-<session_id>
    (source-native id when the provider had one, so stable across re-atomization);
    adjacent user→assistant turns re-pair into the pair shape downstream expects."""
    if not src.is_file():
        raise SystemExit(f"ERROR: atom stream not found: {src}")
    allow = set(sources)
    sessions: dict[str, dict] = {}
    with src.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if r.get("source") not in allow:
                continue
            sid = str(r.get("session_id") or "").strip()
            if not sid:
                continue
            entry = sessions.setdefault(sid, {"source": r.get("source"), "atoms": []})
            entry["atoms"].append(r)
    threads: list[dict] = []
    by_thread: dict[str, list[dict]] = {}
    for sid, entry in sessions.items():
        atoms = sorted(entry["atoms"], key=lambda a: (a.get("ordinal") or 0))
        uid = f"session-{sid}"
        pairs: list[dict] = []
        current: dict | None = None
        for a in atoms:
            text = str(a.get("text") or "").strip()
            if not text:
                continue
            if a.get("role") == "user" or current is None:
                current = {"user": text if a.get("role") == "user" else "", "rest": []}
                if a.get("role") != "user":
                    current["rest"].append(text)
                pairs.append(current)
            else:
                current["rest"].append(text)
        pair_rows = []
        for i, p in enumerate(pairs, start=1):
            body = "\n\n".join(x for x in [p["user"], *p["rest"]] if x)
            first = (p["user"] or (p["rest"][0] if p["rest"] else "")).splitlines()[0][:120]
            pair_rows.append(
                {
                    "thread_uid": uid,
                    "pair_id": f"{uid}-pair-{i:03d}",
                    "title": first,
                    "search_text": body,
                }
            )
        if not pair_rows:
            continue
        title = pair_rows[0]["title"][:80]
        threads.append(
            {
                "thread_uid": uid,
                "title_raw": title,
                "title_normalized": title.lower(),
                "keywords": [],
                "provider": entry["source"],
            }
        )
        by_thread[uid] = pair_rows
    return threads, by_thread, []


# Render-time redaction: extracts are verbatim transcripts, and past sessions pasted
# real credentials into chats. The private store's pre-commit secret scan (global hook,
# ~/.config/git/hooks/pre-commit) blocks token-shaped values — so the renderer masks
# them at the base instead of anyone hand-editing generated files. Patterns mirror the
# hook's, and only the credential VALUE is replaced (marked in place, so the semantic
# pass still sees that a token existed); the raw text remains in the CCE source corpus.
# Redaction is not reduction: no thinking is dropped, only secret material.
_REDACT_PATTERNS = [
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws_secret_access_key", re.compile(r"(?i)(aws_secret_access_key\s*[:=]\s*['\"]?)[A-Za-z0-9/+=]{40}(['\"]?)")),
    ("github_token", re.compile(r"\bgh[opusr]_[A-Za-z0-9]{36,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|PGP|PRIVATE) KEY-----")),
    ("jwt", re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b")),
]
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b((?:api[_-]?key|secret|token|password|passphrase|auth[_-]?token)\b\s*[:=]\s*)([\"']?)([^\"'\s]+)\2"
)
_SKIP_VALUE_RE = re.compile(r"(?i)\b(changeme|example|placeholder|your[_-]?(key|token|secret|password)|todo)\b")


# The marker deliberately contains the word "placeholder": the hook's SKIP_VALUE_RE
# whitelists it, so a redacted assignment is never re-flagged as a fresh secret.
def _redact(text: str) -> str:
    for name, rx in _REDACT_PATTERNS:
        if rx.groups:
            text = rx.sub(rf"\g<1>[REDACTED-placeholder:{name}]\g<2>", text)
        else:
            text = rx.sub(f"[REDACTED-placeholder:{name}]", text)

    def _mask_assignment(m: re.Match) -> str:
        value = m.group(3)
        if value.startswith(("$", "${", "op://", "[REDACTED")) or _SKIP_VALUE_RE.search(value):
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}[REDACTED-placeholder:assignment]{m.group(2)}"

    return _ASSIGNMENT_RE.sub(_mask_assignment, text)


# Stream assignment is a SEMANTIC judgment, deliberately absent here. Two mechanical
# routes were tried and measured before deciding this: the shipped echo-clusterer
# (IDF + 2-core) fuses 397 densely-vocabularied threads into one blob at every floor,
# and CCE's per-pair "themes" turn out to be frequency tokens ("const", "classname",
# "add"), not topics. The brainstorm-20260423 precedent's three streams were
# model-authored too. So extracts land flat under threads/ with `stream: pending`,
# and the semantic pass assigns streams alongside the eight atom kinds — metadata,
# not directory structure, so files keep stable addresses when streams arrive.

def _render_extract(thread: dict, pairs: list[dict], stream: str, provider: str) -> str:
    uid = thread.get("thread_uid", "")
    title = thread.get("title_normalized") or thread.get("title_raw") or uid
    themes = sorted({th for p in pairs for th in (p.get("themes") or [])})
    entities = sorted({e for p in pairs for e in (p.get("entities") or []) if isinstance(e, str)})

    front = {
        "thread_uid": uid,
        "provider": provider,
        "title": title,
        "stream": stream,
        "pair_count": len(pairs),
        "keywords": thread.get("keywords") or [],
        "themes": themes,
        "entities": entities[:40],
        "semantic_atoms": "pending",
        "atom_kinds": ATOM_KINDS,
    }
    lines = ["---", yaml.safe_dump(front, sort_keys=False, allow_unicode=True).strip(), "---", "", f"# {title}", ""]
    lines.append("## PAIRS — verbatim, no reduction")
    lines.append("")
    for i, p in enumerate(pairs, 1):
        lines.append(f"### Pair {i} — {p.get('title', '').strip()}")
        lines.append("")
        text = (p.get("search_text") or p.get("summary") or "").strip()
        for ln in text.splitlines() or [""]:
            lines.append(f"> {ln}" if ln else ">")
        lines.append("")
    lines.append("## SEMANTIC ATOMS — pending")
    lines.append("")
    lines.append(
        "_The eight-kind atom pass has not run for this thread. When it does, it replaces "
        "this section and flips `semantic_atoms` to `done` — nothing above this line changes._"
    )
    lines.append("")
    # redact the WHOLE document — frontmatter keywords/themes/entities carry pasted
    # tokens just as body text does (a bare ghp_ token was found in a keywords list)
    return _redact("\n".join(lines))


def _read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    try:
        return yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}


def _existing_extracts(tdir: Path) -> dict[str, tuple[Path, dict]]:
    """thread_uid → (path, frontmatter) for every extract already on disk."""
    found: dict[str, tuple[Path, dict]] = {}
    if not tdir.is_dir():
        return found
    for p in sorted(tdir.glob("*.md")):
        front = _read_frontmatter(p)
        uid = front.get("thread_uid")
        if uid:
            found[uid] = (p, front)
    return found


def harvest_corpus(cid: str, provider: str, out_root: Path, row: dict | None = None, doc: dict | None = None) -> dict:
    row = row or {}
    if row.get("kind") == "atom-stream":
        src = _store_path(doc or _registry(), row)
        threads, by_thread, actions = _load_atom_stream(src, list(row.get("harvest_sources") or []))
    else:
        home = corpus_resolve.corpus_home()
        corpus_dir = home / cid
        if not corpus_dir.is_dir():
            raise SystemExit(f"ERROR: corpus {cid!r} not found under {home}")
        threads, by_thread, actions = _load_corpus(corpus_dir)

    out = out_root / cid
    tdir = out / "threads"
    tdir.mkdir(parents=True, exist_ok=True)

    # Drain-preserving merge, never a wipe: extracts the semantic pass has completed
    # (`semantic_atoms: done`) are accumulators of model-authored work, not derived
    # artifacts — this tool no longer owns them and must not rewrite or delete them.
    existing = _existing_extracts(tdir)
    numbers = [int(m.group(1)) for p in tdir.glob("*.md") if (m := re.match(r"(\d{3,})-", p.name))]
    next_no = max(numbers, default=0) + 1

    ordered = sorted(threads, key=lambda t: (t.get("title_normalized") or "", t.get("thread_uid") or ""))
    source_uids = {t.get("thread_uid", "") for t in ordered}
    index_rows = []
    preserved = 0
    for t in ordered:
        uid = t.get("thread_uid", "")
        title = t.get("title_normalized") or t.get("title_raw") or uid
        prior = existing.get(uid)
        if prior and prior[1].get("semantic_atoms") == "done":
            path, front = prior
            index_rows.append(
                {
                    "thread_uid": uid,
                    "stream": front.get("stream", "pending"),
                    "file": str(path.relative_to(out)),
                    "semantic_atoms": "done",
                }
            )
            preserved += 1
            continue
        if prior:
            path = prior[0]  # pending extract: re-render in place, address stays stable
        else:
            path = tdir / f"{next_no:03d}-{slugify(title)[:60]}.md"
            next_no += 1
        path.write_text(
            _render_extract(t, by_thread.get(uid, []), "pending", t.get("provider") or provider), encoding="utf-8"
        )
        index_rows.append(
            {"thread_uid": uid, "stream": "pending", "file": str(path.relative_to(out)), "semantic_atoms": "pending"}
        )

    # Extracts whose source thread vanished: drained ones stay (preservation beats
    # parity — the corpus dropping a thread must not destroy its harvested atoms);
    # pending ones are mechanical residue and are dropped with the source.
    for uid in sorted(existing):
        if uid in source_uids:
            continue
        path, front = existing[uid]
        if front.get("semantic_atoms") == "done":
            index_rows.append(
                {
                    "thread_uid": uid,
                    "stream": front.get("stream", "pending"),
                    "file": str(path.relative_to(out)),
                    "semantic_atoms": "done",
                    "source_present": False,
                }
            )
            preserved += 1
        else:
            path.unlink()

    # the corpus's own coarse actions, preserved as candidate atoms
    atoms_dir = out / "atoms"
    atoms_dir.mkdir(exist_ok=True)
    candidate = [
        {
            "id": a.get("action_key"),
            "kind": "candidate-action",
            "statement": a.get("canonical_action"),
            "status": a.get("status"),
            "thread_uids": a.get("thread_uids") or [],
            "confidence": "coarse — CCE action ledger, not the eight-kind semantic pass",
        }
        for a in sorted(actions, key=lambda a: a.get("action_key") or "")
    ]
    (atoms_dir / "candidate-actions.yaml").write_text(
        yaml.safe_dump({"count": len(candidate), "atoms": candidate}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    assigned = sorted({r.get("stream") for r in index_rows if r.get("stream") not in (None, "pending")})
    (out / "index.yaml").write_text(
        yaml.safe_dump(
            {
                "corpus": cid,
                "provider": provider,
                "threads": len(threads),
                "streams": assigned or "pending — assigned by the semantic pass",
                "candidate_actions": len(candidate),
                "extracts": index_rows,
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return {"corpus": cid, "threads": len(threads), "actions": len(candidate), "preserved": preserved}


def sync_index(out_root: Path) -> int:
    """Re-derive every index.yaml row (stream, semantic_atoms) from extract frontmatter.

    The semantic pass rewrites only its own extract file — this projection step is what
    makes `--queue` shrink. Idempotent: a second run changes nothing and writes nothing.
    """
    changed = 0
    for idx in sorted(out_root.glob("*/index.yaml")):
        out = idx.parent
        doc = yaml.safe_load(idx.read_text(encoding="utf-8")) or {}
        rows = doc.get("extracts") or []
        touched = False
        for row in rows:
            f = out / (row.get("file") or "")
            if not f.is_file():
                continue
            front = _read_frontmatter(f)
            new_state = front.get("semantic_atoms", row.get("semantic_atoms"))
            new_stream = front.get("stream", row.get("stream"))
            if (new_state, new_stream) != (row.get("semantic_atoms"), row.get("stream")):
                row["semantic_atoms"] = new_state
                row["stream"] = new_stream
                changed += 1
                touched = True
        if touched:
            assigned = sorted({r.get("stream") for r in rows if r.get("stream") not in (None, "pending")})
            doc["streams"] = assigned or "pending — assigned by the semantic pass"
            idx.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return changed


def semantic_queue(out_root: Path) -> list[str]:
    pending = []
    for idx in sorted(out_root.glob("*/index.yaml")):
        doc = yaml.safe_load(idx.read_text(encoding="utf-8")) or {}
        for row in doc.get("extracts") or []:
            if row.get("semantic_atoms") == "pending":
                pending.append(f"{doc.get('corpus')}/{row['file']}")
    return pending


# The one extract parser lives in the constellation streams organ; this mirrors only the
# atom-block shape, which is fixed by _render_extract above (this module writes it).
_ATOM_BLOCK_RE = re.compile(r"## SEMANTIC ATOMS\s*\n+```yaml\n(.*?)```", re.DOTALL)


def census(out_root: Path) -> dict:
    """Statement-free projection of the drain: counts, kinds, and ids — never statements.

    This is the artifact that lets the drain's outcome survive its own store. The corpus
    is declared `remote: none`, so it can never be published and CI can never read it;
    without a committed projection the entire 4,099-atom result is invisible to git and
    dies with the volume it sits on.

    Deliberately CLOCK-FREE so re-running is byte-idempotent: the git commit is the
    timestamp. Emitting `generated_at` here would make every run a diff.
    """
    by_kind: dict[str, int] = {k: 0 for k in ATOM_KINDS}
    streams: set[str] = set()
    seen_ids: set[str] = set()
    duplicates = 0
    extracts = extracts_with_atoms = atoms = 0
    explicit = implied = 0
    unknown_kinds: dict[str, int] = {}

    for path in sorted(out_root.glob("*/threads/*.md")):
        extracts += 1
        text = path.read_text(encoding="utf-8")
        front = _read_frontmatter(path)
        stream = str(front.get("stream") or "").strip()
        if stream and stream != "pending":
            streams.add(stream)
        m = _ATOM_BLOCK_RE.search(text)
        if not m:
            continue
        try:
            block = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        rows = block.get("atoms") or []
        if not rows:
            continue
        extracts_with_atoms += 1
        for atom in rows:
            if not isinstance(atom, dict):
                continue
            atoms += 1
            kind = str(atom.get("kind") or "").strip()
            if kind in by_kind:
                by_kind[kind] += 1
            elif kind:
                unknown_kinds[kind] = unknown_kinds.get(kind, 0) + 1
            aid = str(atom.get("id") or "").strip()
            if aid:
                if aid in seen_ids:
                    duplicates += 1
                seen_ids.add(aid)
            conf = str(atom.get("confidence") or "").strip()
            if conf == "explicit":
                explicit += 1
            elif conf == "implied":
                implied += 1

    doc: dict = {
        "schema_version": 0.1,
        "generated_by": "scripts/brainstorm-harvest.py --census",
        "source": {
            "store": "conversations-private",
            "corpus": EXTRACTS_DIRNAME,
            "corpus_state": "present",
        },
        "totals": {
            "extracts": extracts,
            "extracts_with_atoms": extracts_with_atoms,
            "streams": len(streams),
            "atoms": atoms,
            "duplicate_atom_ids": duplicates,
            "confidence_explicit_pct": round(explicit * 100.0 / atoms, 1) if atoms else 0.0,
            "confidence_implied_pct": round(implied * 100.0 / atoms, 1) if atoms else 0.0,
        },
        # Sorted by count then name: a stable order is what makes reruns byte-identical.
        "by_kind": dict(sorted(by_kind.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
    if unknown_kinds:
        # An undeclared kind is a schema change that must surface, never be dropped.
        doc["undeclared_kinds"] = dict(sorted(unknown_kinds.items()))

    homing = out_root / "homing.yaml"
    if homing.is_file():
        hdoc = yaml.safe_load(homing.read_text(encoding="utf-8")) or {}
        recorded = {k: len(v or {}) for k, v in hdoc.items() if isinstance(v, dict)}
        if recorded:
            doc["homed"] = {
                key.replace("_", "-"): {"unit": "stream", "count": count}
                for key, count in sorted(recorded.items())
            }
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", help="one corpus id from corpora.yaml")
    ap.add_argument("--all", action="store_true", help="every harvestable session-memory corpus")
    ap.add_argument("--queue", action="store_true", help="list extracts awaiting the semantic pass")
    ap.add_argument("--sync-index", action="store_true", help="re-derive index.yaml rows from extract frontmatter")
    ap.add_argument(
        "--census",
        action="store_true",
        help="write the statement-free atom census to institutio/governance/atom-census.yaml",
    )
    args = ap.parse_args()

    corpora = _harvestable_corpora()
    out_root = corpus_resolve.corpus_home() / EXTRACTS_DIRNAME

    if args.census:
        if not out_root.is_dir():
            # Refuse to write an empty census over a real one: an absent store is a host
            # fact (the corpus is cold-archived), not evidence that the drain produced
            # nothing. Silently emitting zeros would erase the only committed record.
            print(f"census: extracts root not present: {out_root}", file=sys.stderr)
            print(
                "The conversations-private store is `remote: none` and may be archived off "
                "this host. Restore it, then re-run --census. The committed census at "
                f"{ATOM_CENSUS.relative_to(REPO_ROOT)} carries the restore path.",
                file=sys.stderr,
            )
            return 1
        doc = census(out_root)
        body = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        previous = ATOM_CENSUS.read_text(encoding="utf-8") if ATOM_CENSUS.is_file() else ""
        header = previous.split("\nschema_version:", 1)[0] if previous.startswith("#") else ""
        text = (header.rstrip("\n") + "\n\n" + body) if header else body
        changed = text != previous
        if changed:
            ATOM_CENSUS.write_text(text, encoding="utf-8")
        t = doc["totals"]
        print(
            f"census: {t['atoms']} atoms across {len(doc['by_kind'])} kinds, "
            f"{t['extracts']} extracts, {t['streams']} streams, "
            f"{t['duplicate_atom_ids']} duplicate id(s) — "
            f"{'updated' if changed else 'unchanged'} {ATOM_CENSUS.relative_to(REPO_ROOT)}"
        )
        return 0

    if args.sync_index:
        changed = sync_index(out_root)
        pending = len(semantic_queue(out_root))
        print(f"sync-index: {changed} row(s) updated; {pending} extract(s) still pending")
        return 0

    if args.queue:
        pending = semantic_queue(out_root)
        print(f"{len(pending)} extract(s) awaiting the semantic atom pass")
        for p in pending[:20]:
            print(f"  {p}")
        if len(pending) > 20:
            print(f"  … +{len(pending) - 20} more")
        return 0

    targets = list(corpora) if args.all else ([args.corpus] if args.corpus else [])
    if not targets:
        ap.error("--corpus <id> or --all required")
    unknown = [t for t in targets if t not in corpora]
    if unknown:
        ap.error(f"not harvestable corpora: {unknown} (declared: {sorted(corpora)})")

    doc = _registry()
    for cid in targets:
        stats = harvest_corpus(cid, corpora[cid].get("provider", "unknown"), out_root, row=corpora[cid], doc=doc)
        print(
            f"harvested {stats['corpus']}: {stats['threads']} threads "
            f"({stats['preserved']} drained extract(s) preserved), {stats['actions']} candidate actions"
        )
    print(f"\nextracts under {out_root}  (private store — never the public tree)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
