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

EXTRACTS_DIRNAME = "brainstorm-extracts"

ATOM_KINDS = [
    "projects-to-start",
    "decisions",
    "tasks",
    "vacuums",
    "questions-unresolved",
    "client-offerings",
    "schema-proposals",
    "functionality-to-repeat",
]


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return re.sub(r"-{2,}", "-", value).strip("-") or "thread"


def _harvestable_corpora() -> dict[str, dict]:
    doc = yaml.safe_load(CORPORA_REGISTRY.read_text(encoding="utf-8")) or {}
    out = {}
    for cid, row in (doc.get("corpora") or {}).items():
        if row.get("harvestable") and row.get("kind") == "session-memory":
            out[cid] = row
    return out


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
    return "\n".join(lines)


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


def harvest_corpus(cid: str, provider: str, out_root: Path) -> dict:
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
        path.write_text(_render_extract(t, by_thread.get(uid, []), "pending", provider), encoding="utf-8")
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

    (out / "index.yaml").write_text(
        yaml.safe_dump(
            {
                "corpus": cid,
                "provider": provider,
                "threads": len(threads),
                "streams": "pending — assigned by the semantic pass",
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", help="one corpus id from corpora.yaml")
    ap.add_argument("--all", action="store_true", help="every harvestable session-memory corpus")
    ap.add_argument("--queue", action="store_true", help="list extracts awaiting the semantic pass")
    ap.add_argument("--sync-index", action="store_true", help="re-derive index.yaml rows from extract frontmatter")
    args = ap.parse_args()

    corpora = _harvestable_corpora()
    out_root = corpus_resolve.corpus_home() / EXTRACTS_DIRNAME

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
        ap.error(f"not harvestable session-memory corpora: {unknown} (declared: {sorted(corpora)})")

    for cid in targets:
        stats = harvest_corpus(cid, corpora[cid].get("provider", "unknown"), out_root)
        print(
            f"harvested {stats['corpus']}: {stats['threads']} threads "
            f"({stats['preserved']} drained extract(s) preserved), {stats['actions']} candidate actions"
        )
    print(f"\nextracts under {out_root}  (private store — never the public tree)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
