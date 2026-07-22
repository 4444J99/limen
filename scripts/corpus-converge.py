#!/usr/bin/env python3
"""corpus-converge.py — point the CONVERGE engine at Anthony's WORDS (not code PRs).

`scripts/converge-organ.py` converges *code PR-variants* (the divergence half of dispatch). This
organ is the other arrow, aimed at the thing he actually keeps asking for: his **text/language/word
knowledge base** — the universal context of prompts + session-meta dialogue (+ the GitHub graph) —
distilled toward ONE. It closes the CONVERGE rung for his words ([[alchemical-convergence-method]],
[[distillation-not-reduction]], [[knowledge-corpus-converged]]).

THE LOOP (DIVERGE → CONVERGE → ONE):

  CLUSTERS  the 13 canonical faces in `knowledge-corpus/reduced/*.md` ARE the idea-clusters. Each
            face is the current ONE-version of its cluster.
  INGEST    scan NEW divergent shots not yet absorbed — recent session-meta dialogue, new prompts,
            and (with --graph) a bounded slice of the GitHub issues/PRs that are the universal
            context — and assign each to its nearest face (lexical).
  DISTILL   for each face with new material, run converge() over [the face itself + its new shots].
            Offline by default (no network, no write-back — the concat fallback would bloat, so it
            NEVER touches the corpus). --live uses the real AnthropicSynthesizer; only then is the
            distillate written back.
  WRITE     (live + --apply + promoted) the better version is written back to the face atomically,
            absorbed shots are marked, THE ONE is itself RE-CONVERGED from the updated faces
            (recursive distillation, never a mechanical clobber). Gap-finder next_shots become new
            bounded collection tasks (gaps become work → feeds the next cycle). Every write is
            git-backed (the corpus repo is committed + pushed by the capture organ) — nothing lost.

Gated OFF by default (LIMEN_CORPUS_CONVERGE=1). Bounded (LIMEN_CORPUS_CONVERGE_LIMIT faces/beat,
default 2). Fail-open — never crashes the heartbeat.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
sys.path.insert(0, str(ROOT / "cli" / "src"))

H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


# ─── locations (derive at runtime, never pin — [[derive-never-pin-hardcodes]]) ───

def _corpus_root() -> Path:
    return Path(os.environ.get("LIMEN_CORPUS_ROOT", Path.home() / "Workspace" / "knowledge-corpus"))


def _media_atoms_root() -> Path:
    # The media-atoms store produced by scripts/media-atomize.py (strand D). Kept in sync
    # with that script's default so his docs/photos remix with his words.
    return Path(os.environ.get("LIMEN_MEDIA_ATOMS", _corpus_root() / "02-media-atoms"))


def _session_meta_root() -> Path:
    return Path(os.environ.get("LIMEN_SESSION_META", Path.home() / "Workspace" / "session-meta"))


def _atoms_path() -> Path:
    # The unified, redacted, multi-provider atom corpus produced by session-meta's
    # ingest/refresh-atoms.sh (Claude, codex, opencode, …). Derived, never pinned.
    return Path(os.environ.get("LIMEN_EXPORT_ATOMS", _session_meta_root() / "ingest" / "atoms.jsonl"))


def _export_source_gate() -> set[str] | None:
    """THE EXPORT GATE (his policy: ALL providers flow INTO atoms.jsonl unfiltered; the gate is at
    EXPORT, not ingest). LIMEN_EXPORT_SOURCES is a comma-separated allowlist of atom `source`s
    eligible to distill into THE ONE. Empty/unset = ALL sources eligible — the default he chose.
    Returns None for 'all', else the allowed-source set. Destination is LOCAL only (knowledge-corpus,
    git-backed to the private corpus repo) — this gate never authorizes outward/public publish."""
    raw = os.environ.get("LIMEN_EXPORT_SOURCES", "").strip()
    if not raw:
        return None
    return {s.strip() for s in raw.split(",") if s.strip()}


def _collect_atoms(limit: int, absorbed: set[str]) -> list[dict]:
    """Newest substantive shots from the UNIFIED multi-provider atom corpus (atoms.jsonl), filtered
    by the export source-gate. Bounded + fail-open. This is the bridge that lets his words across
    EVERY agent — not just Claude dialogue — distill into THE ONE ([[pillars-platform-convergence]]).
    A trivial one-liner carries no idea, so a minimum length keeps faces substantive."""
    path = _atoms_path()
    if not path.is_file():
        return []                       # never-NO: no atom store yet just means no atom shots
    gate = _export_source_gate()
    rows: list[dict] = []
    try:
        with path.open(errors="replace") as f:
            for line in f:
                try:
                    a = json.loads(line)
                except Exception:
                    continue
                if gate is not None and a.get("source", "") not in gate:
                    continue
                if len((a.get("text") or "").strip()) < 80:
                    continue
                rows.append(a)
    except OSError:
        return []
    rows.sort(key=lambda a: a.get("ts") or "", reverse=True)   # newest-first; ts-less sink
    out: list[dict] = []
    for a in rows[: max(limit * 8, 40)]:
        iid = a.get("content_sha") or a.get("atom_id") or _hash(a.get("text", ""))
        if iid in absorbed:
            continue
        out.append({"id": iid, "text": a["text"][:20000], "source": f"atoms:{a.get('source', '?')}"})
    return out


def _state_path() -> Path:
    return Path(os.environ.get("LIMEN_CORPUS_STATE", ROOT / "logs" / "corpus-converge-state.json"))


def _log_path() -> Path:
    return Path(os.environ.get("LIMEN_CORPUS_LOG", ROOT / "logs" / "corpus-converge-log.jsonl"))


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _hash(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode("utf-8", "replace"))
    return h.hexdigest()[:16]


# ─── clusters = faces ────────────────────────────────────────────────

def load_faces(corpus_root: Path | None = None) -> list[dict]:
    """Each reduced/*.md face is one idea-cluster. Returns [{name, path, title, text}]."""
    corpus_root = corpus_root or _corpus_root()
    reduced = corpus_root / "reduced"
    out: list[dict] = []
    if not reduced.is_dir():
        return out
    for p in sorted(reduced.glob("*.md")):
        try:
            text = p.read_text()
        except Exception:
            continue
        m = H1_RE.search(text)
        title = m.group(1).strip() if m else p.stem.replace("-", " ").title()
        out.append({"name": p.stem, "path": p, "title": title, "text": text})
    return out


# ─── ingest: the new divergent shots not yet absorbed ────────────────

def _read_text(p: Path, cap: int = 20000) -> str:
    try:
        t = p.read_text(errors="replace")
    except Exception:
        return ""
    return t[:cap]


def gather_new_material(limit: int, *, with_graph: bool = False, absorbed: set[str] | None = None) -> list[dict]:
    """Collect candidate NEW shots (session-meta dialogue, new prompts, optional GitHub graph),
    newest-first, skipping anything already absorbed. Returns [{id, text, source}]."""
    absorbed = absorbed or set()
    items: list[dict] = []

    # session-meta dialogue — the most recent files by mtime (bounded).
    sm = _session_meta_root()
    if sm.is_dir():
        files = []
        for p in sm.rglob("*.md"):
            try:
                files.append((p.stat().st_mtime, p))
            except Exception:
                continue
        files.sort(reverse=True)
        for _, p in files[: max(limit * 8, 40)]:
            text = _read_text(p)
            if not text.strip():
                continue
            iid = _hash(str(p), str(p.stat().st_mtime))
            if iid in absorbed:
                continue
            items.append({"id": iid, "text": text, "source": f"session-meta:{p.name}"})

    # new prompts / collection manifests inside the corpus (bounded).
    coll = _corpus_root() / "01-collection"
    if coll.is_dir():
        for p in sorted(coll.glob("*.md")):
            text = _read_text(p)
            if not text.strip():
                continue
            iid = _hash(str(p), str(int(p.stat().st_mtime)))
            if iid in absorbed:
                continue
            items.append({"id": iid, "text": text, "source": f"collection:{p.name}"})

    # personal-media atoms (strand D): doc/photo Shots produced by media-atomize.py, read from
    # the canonical media-atoms store so his MEDIA remixes with his WORDS through the same engine.
    # Fail-open (missing store → no media shots this beat); bounded like the other sources.
    atoms_dir = _media_atoms_root()
    if atoms_dir.is_dir():
        atom_files = []
        for p in atoms_dir.glob("*.json"):
            try:
                atom_files.append((p.stat().st_mtime, p))
            except Exception:
                continue
        atom_files.sort(reverse=True)
        for _, p in atom_files[: max(limit * 8, 40)]:
            try:
                a = json.loads(p.read_text())
            except Exception:
                continue
            text = (a.get("text") or "").strip()
            iid = a.get("id") or _hash(str(p))
            if not text or iid in absorbed:
                continue
            items.append({"id": iid, "text": text[:20000], "source": a.get("source") or f"media:{p.name}"})

    # the UNIFIED multi-provider atom corpus (atoms.jsonl) — his words across EVERY agent
    # (Claude, codex, opencode, …), gated at EXPORT by LIMEN_EXPORT_SOURCES. Realizes
    # "all providers in, gate on export": ingest is unfiltered, this converge step is where the
    # source-gate decides what distills into THE ONE. Bounded + fail-open like the others.
    items.extend(_collect_atoms(limit, absorbed))

    # the universal context: a bounded slice of the GitHub graph (issues/PRs as shots).
    if with_graph:
        items.extend(_gather_graph_shots(limit, absorbed))

    return items


def _gather_graph_shots(limit: int, absorbed: set[str]) -> list[dict]:
    """Bounded, fail-open pull of recent issues/PRs across the owner as divergent shots."""
    import subprocess
    out: list[dict] = []
    owner = os.environ.get("LIMEN_GH_OWNER", "organvm")
    n = str(int(os.environ.get("LIMEN_CORPUS_GRAPH_N", "20")))
    try:
        proc = subprocess.run(
            ["gh", "search", "issues", "--owner", owner, "--limit", n,
             "--json", "title,body,url", "--sort", "updated"],
            capture_output=True, text=True, timeout=30,
        )
        rows = json.loads(proc.stdout or "[]")
    except Exception:
        return out  # never-NO: graph unavailable just means no graph shots this beat
    for r in rows:
        body = (r.get("title", "") + "\n" + (r.get("body") or ""))[:8000]
        if not body.strip():
            continue
        iid = _hash(r.get("url", ""), r.get("title", ""))
        if iid in absorbed:
            continue
        out.append({"id": iid, "text": body, "source": f"graph:{r.get('url','')}"})
    return out


def assign_to_faces(faces: list[dict], items: list[dict]) -> dict[str, list[dict]]:
    """Assign each new item to its nearest face by lexical overlap. Items matching nothing are
    dropped (they belong to no existing face — a future face-spawn concern, not this beat)."""
    from limen.converge import _tokens
    face_toks = {f["name"]: _tokens(f["title"] + " " + f["text"]) for f in faces}
    buckets: dict[str, list[dict]] = {f["name"]: [] for f in faces}
    for it in items:
        toks = _tokens(it["text"])
        best, best_name = 0, None
        for f in faces:
            ov = len(toks & face_toks[f["name"]])
            if ov > best:
                best, best_name = ov, f["name"]
        if best_name is not None:
            buckets[best_name].append(it)
    return buckets


# ─── distill + write-back ────────────────────────────────────────────

def _kit(live: bool, threshold: float | None = None):
    from limen.converge import _build_dry_run_kit
    if not live:
        return _build_dry_run_kit()
    try:
        from limen.converge import (AnthropicSynthesizer, ClaudeCliSynthesizer,
                                     DeterministicScorer, LadderSynthesizer,
                                     LexicalGapFinder, LexicalRanker, NoopPromoter,
                                     _api_tier_factory, _cli_tier_factory)
        # Synthesizer cascade ([[cascade-fallback-principle]] / never a silent no), now an
        # EARNED-TIER LADDER nested inside each reachable rung (haiku-first-with-cheap-verify,
        # escalate only on a failed check; LIMEN_CONVERGE_LADDER=0 reverts to single-tier):
        #   1. raw Anthropic API   — only when ANTHROPIC_API_KEY is present (spends API)
        #   2. claude CLI (keyless)— subscription-authed `claude -p`; the LIVE DAEMON path
        #      (its launchd env has NO key, so this is the rung that actually closes the
        #      capture→converge write-back instead of falling silently to offline preview)
        #   3. offline preview     — handled by the outer except (no synthesizer available)
        # The ladder eagerly builds its cheapest rung, so a missing mechanism still raises at
        # construction here and the cascade's fallbacks fire exactly as before.
        ladder_on = os.environ.get("LIMEN_CONVERGE_LADDER", "1") == "1"
        # The ladder accept-gate MUST equal the threshold converge() promotes on, else a ladder
        # -accepted rung gets surprise-rolled-back. main() passes args.threshold (which already
        # defaults from LIMEN_CORPUS_THRESHOLD) as the single source of truth; fall back to the
        # env only for callers that don't pass one.
        if threshold is None:
            threshold = float(os.environ.get("LIMEN_CORPUS_THRESHOLD", "0.7"))
        scorer = DeterministicScorer()
        synth = None
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                synth = (LadderSynthesizer(tier_factory=_api_tier_factory(), scorer=scorer, threshold=threshold)
                         if ladder_on else AnthropicSynthesizer())
            except Exception as exc:
                print(f"[corpus-converge] API synth unavailable ({exc}); trying claude CLI")
        if synth is None:
            synth = (LadderSynthesizer(tier_factory=_cli_tier_factory(), scorer=scorer, threshold=threshold)
                     if ladder_on else ClaudeCliSynthesizer())  # raises (→ outer except → offline) if no CLI
        return {"ranker": LexicalRanker(), "synthesizer": synth,
                "scorer": scorer, "promoter": NoopPromoter(),
                "gap_finder": LexicalGapFinder()}
    except Exception as exc:
        print(f"[corpus-converge] live kit unavailable ({exc}); using offline kit")
        return _build_dry_run_kit()


def _managed_text(title: str, better_version: str, *, absorbed_n: int, losers_n: int, kind: str) -> str:
    """Canonical written form: preserved H1 + a managed provenance line + the distillate body
    (any leading H1 the synthesizer emitted is stripped so the title never doubles)."""
    body = H1_RE.sub("", better_version, count=1).lstrip() if better_version.lstrip().startswith("#") else better_version.strip()
    stamp = _now().date().isoformat()
    prov = (f"> _Converged {stamp} by the corpus-converge organ — absorbed {absorbed_n} new "
            f"{kind}; {losers_n} cited as provenance. Prior version in git history. "
            f"([[distillation-not-reduction]])_")
    return f"# {title}\n\n{prov}\n\n{body}\n"


def converge_face(face: dict, items: list[dict], kit: dict, threshold: float):
    """Run one convergence cycle over [the face itself + its new shots]."""
    from limen.converge import Shot, converge
    shots = [Shot(id=f"{face['name']}:self", text=face["text"], source=str(face["path"]))]
    shots += [Shot(id=it["id"], text=it["text"], source=it["source"]) for it in items]
    return converge(face["title"], shots, threshold=threshold, **kit)


def write_face(face: dict, result, absorbed_n: int) -> None:
    from limen.io import atomic_write_text
    atomic_write_text(face["path"],
                      _managed_text(face["title"], result.better_version,
                                    absorbed_n=absorbed_n, losers_n=len(result.cited_losers),
                                    kind="shots"))


def reconverge_the_one(corpus_root: Path, faces: list[dict], kit: dict, threshold: float):
    """Recursive distillation: THE ONE is converge() over the (updated) faces as shots — exactly
    'reduction performed on the reductions themselves'. Never a mechanical clobber."""
    from limen.converge import Shot, converge
    shots = [Shot(id=f["name"], text=f["text"], source=str(f["path"])) for f in faces]
    idea = "THE ONE — the single coherent corpus in which all faces are one substance"
    r = converge(idea, shots, threshold=threshold, **kit)
    if r.promoted and r.better_version.strip():
        from limen.io import atomic_write_text
        atomic_write_text(corpus_root / "00-THE-ONE.md",
                          _managed_text("THE ONE", r.better_version,
                                        absorbed_n=len(faces), losers_n=len(r.cited_losers),
                                        kind="faces"))
    return r


# ─── gaps become work + state ────────────────────────────────────────

def emit_gaps(gap_texts: list[str], origin: str, apply: bool) -> int:
    """Gap-finder next_shots → bounded NEW collection tasks via Tabularius tickets.

    Idempotent: a gap's id derives from its text, so the same gap never duplicates, including when
    it is already waiting in the keeper inbox.
    """
    if not gap_texts:
        return 0
    from limen.io import load_limen_file
    from limen.intake import contract_fields, github_pr_contract
    from limen.tabularius import pending_task_ids, submit_task_upsert
    tasks_path = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
    try:
        lf = load_limen_file(tasks_path)
    except Exception as exc:
        print(f"[corpus-converge] could not load tasks ({exc}); skipping gap-emit")
        return 0
    have = {t.id for t in lf.tasks} | pending_task_ids(tasks_path)
    added = 0
    session_id = os.environ.get("LIMEN_SESSION_ID", "corpus-converge")
    for g in gap_texts:
        gid = "CORP-" + re.sub(r"[^a-z0-9]+", "-", g.lower())[:40].strip("-")
        if gid in have:
            continue
        task = dict(
            id=gid,
            title=g[:120],
            repo="organvm/limen",
            created=_now().date(),
            status="open",
            target_agent="any",
            priority="low",
            type="corpus-gap",
            origin="system_debt",
            horizon="past",
            value_case=f"Preserve and close the prompt-corpus gap surfaced from {origin}",
            context=f"corpus gap surfaced by convergence of {origin}",
            **contract_fields(github_pr_contract("organvm/limen", gid)),
        )
        if apply:
            submit_task_upsert(tasks_path, task, agent="corpus-converge", session_id=session_id)
        have.add(gid)
        added += 1
    return added


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except Exception:
        return {"absorbed": []}


def _save_state(state: dict) -> None:
    from limen.io import atomic_write_text
    atomic_write_text(_state_path(), json.dumps(state, indent=2))


# ─── main ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="corpus-converge — distill his WORDS toward ONE")
    ap.add_argument("--apply", action="store_true", help="write faces/gaps/state/log (else preview)")
    ap.add_argument("--live", action="store_true", default=os.environ.get("LIMEN_CORPUS_CONVERGE_LIVE") == "1",
                    help="real AnthropicSynthesizer + face write-back (else offline preview)")
    ap.add_argument("--graph", action="store_true", default=os.environ.get("LIMEN_CORPUS_GRAPH") == "1",
                    help="also pull a bounded GitHub issues/PRs slice as divergent shots")
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LIMEN_CORPUS_CONVERGE_LIMIT", "2")),
                    help="max faces converged per run (bounded)")
    ap.add_argument("--threshold", type=float, default=float(os.environ.get("LIMEN_CORPUS_THRESHOLD", "0.7")))
    args = ap.parse_args(argv)

    corpus_root = _corpus_root()
    faces = load_faces(corpus_root)
    if not faces:
        print(f"[corpus-converge] no faces under {corpus_root}/reduced — nothing to converge")
        return 0

    state = _load_state()
    absorbed = set(state.get("absorbed", []))
    items = gather_new_material(args.limit, with_graph=args.graph, absorbed=absorbed)
    buckets = assign_to_faces(faces, items)

    # faces with the most new material first; bounded.
    live_faces = sorted(((f, buckets[f["name"]]) for f in faces if buckets[f["name"]]),
                        key=lambda fb: len(fb[1]), reverse=True)[: args.limit]
    if not live_faces:
        print(f"[corpus-converge] {len(items)} new shots, none assigned to a face — nothing to distill")
        return 0

    kit = _kit(args.live, threshold=args.threshold)  # ladder gate == converge() promote gate
    can_write = args.live and args.apply  # write-back requires REAL synthesis (concat would bloat)
    log_path = _log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    changed_any = False
    total_gaps = 0

    for face, its in live_faces:
        try:
            r = converge_face(face, its, kit, args.threshold)
        except Exception as exc:  # never crash the heartbeat
            print(f"[corpus-converge] {face['name']}: cycle failed ({exc}); skipping")
            continue
        wrote = False
        if can_write and r.promoted and r.better_version.strip():
            write_face(face, r, len(its))
            face["text"] = face["path"].read_text()  # refresh for THE ONE re-converge
            absorbed.update(it["id"] for it in its)   # only absorb what we actually folded
            wrote = changed_any = True
        gaps = emit_gaps(r.next_shots, face["name"], args.apply) if args.apply else len(r.next_shots)
        total_gaps += gaps
        rec = {"ts": _now().isoformat(), "face": face["name"], "new_shots": len(its),
               "score": round(r.score, 3), "promoted": r.promoted, "wrote": wrote,
               "losers": len(r.cited_losers), "gaps": gaps}
        if args.apply:
            with log_path.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
        print(f"[corpus-converge] {face['name']}: +{len(its)} shots → score {r.score:.2f} "
              f"promoted={r.promoted} wrote={wrote} gaps={gaps}")

    # recursive distillation of THE ONE from the updated faces (live + apply only).
    if changed_any and can_write:
        try:
            ro = reconverge_the_one(corpus_root, faces, kit, args.threshold)
            print(f"[corpus-converge] THE ONE re-converged: score {ro.score:.2f} promoted={ro.promoted}")
        except Exception as exc:
            print(f"[corpus-converge] THE ONE re-converge failed ({exc}); faces still updated")

    if args.apply and changed_any:
        state["absorbed"] = sorted(absorbed)[-5000:]  # bounded memory of what's been folded
        _save_state(state)

    mode = "live" if args.live else "offline-preview"
    note = "" if can_write else "  (no face write-back: needs --live --apply)"
    print(f"[corpus-converge] {len(live_faces)} faces, {total_gaps} gaps "
          f"{'emitted' if args.apply else '(dry-run)'} [{mode}]{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
