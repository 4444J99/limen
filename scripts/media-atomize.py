#!/usr/bin/env python3
"""media-atomize.py — strand D slice 1: his personal DOCS become first-class Shot atoms.

The system already has the atom abstraction (`limen.converge.Shot`) and the engine
(`converge()` → ONE); it just never fed personal media into them. This organ does the
cheapest, highest-signal slice: turn his documents into `Shot` atoms in the SAME store
the converge engine reads, so `corpus-converge` remixes his media with his words and
`capture.sh` pushes them off-disk into the universal context. (Design:
`docs/atomic-units-personal-media.md`; reuses `cli/src/limen/converge.py` — no new infra.)

THE PIPELINE (slice 1 = stages 1–3; remix/reclaim are later slices):

  INGEST   walk a docs source — DEFAULT the DURABLE Archive4T copy of CloudDocs
           (`/Volumes/Archive4T/personal-cloud-docs`), so we atomize from the offsite
           copy and NEVER re-download iCloud (the vicious re-materialize cycle strand C
           just fixed). text/md/txt now; PDF when `pdftotext` (poppler) is present.
  ATOMIZE  extract text, chunk into section-level shots:
           ``Shot(id=hash, text=section, source=path)`` — the bytes stay put, only text.
  STORE    (--apply) write each atom content-addressed under the media-atoms store the
           converge engine reads (dedup by id; idempotent via a per-source signature so
           re-runs only atomize new/changed docs).
  PROVE    (--converge IDEA) run converge() over the stored atoms with the OFFLINE kit to
           show his media flows through the SAME engine that distills his words.

SAFE (mirrors library-preserve): dry-run by DEFAULT (--apply to write); READ-ONLY on
sources (never move/delete/evict — reclaim is a later byproduct); fail-open per file and
never crashes the heartbeat; bounded per run (--limit). Reversible only.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
sys.path.insert(0, str(ROOT / "cli" / "src"))

# Section boundaries: markdown headings; falls back to paragraph blocks when there are none.
HEAD_RE = re.compile(r"^#{1,3}[ \t]+\S.*$", re.MULTILINE)
PARA_RE = re.compile(r"\n[ \t]*\n")
DOC_EXTS = {".md", ".markdown", ".txt", ".text", ".rst", ".org", ".pdf"}
MAX_CHARS = int(os.environ.get("LIMEN_MEDIA_MAX_CHARS", "4000"))
MIN_CHARS = int(os.environ.get("LIMEN_MEDIA_MIN_CHARS", "200"))
PDF_TIMEOUT = int(os.environ.get("LIMEN_MEDIA_PDF_TIMEOUT", "60"))


# ─── locations (derive at runtime, never pin — [[derive-never-pin-hardcodes]]) ───

def _corpus_root() -> Path:
    return Path(os.environ.get("LIMEN_CORPUS_ROOT", Path.home() / "Workspace" / "knowledge-corpus"))


def _src_root() -> Path:
    # Atomize from the DURABLE Archive4T copy (strand C already copied CloudDocs there),
    # so this never touches/redownloads the live iCloud cache.
    return Path(os.environ.get("LIMEN_MEDIA_SRC", "/Volumes/Archive4T/personal-cloud-docs"))


def _atoms_root() -> Path:
    # The canonical media-atoms store the converge engine reads (content-addressed).
    return Path(os.environ.get("LIMEN_MEDIA_ATOMS", _corpus_root() / "02-media-atoms"))


def _photos_library_root() -> Path:
    return Path(os.environ.get("LIMEN_PHOTOS_LIBRARY", Path.home() / "Pictures" / "Photos Library.photoslibrary"))


def _photos_db_path() -> Path:
    return Path(os.environ.get("LIMEN_PHOTOS_DB", _photos_library_root() / "database" / "Photos.sqlite"))


def _state_path() -> Path:
    return Path(os.environ.get("LIMEN_MEDIA_STATE", ROOT / "logs" / "media-atomize-state.json"))


def _log_path() -> Path:
    return Path(os.environ.get("LIMEN_MEDIA_LOG", ROOT / "logs" / "media-atomize-log.jsonl"))


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _hash(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def _sig(p: Path) -> str:
    """A cheap change signature so re-runs skip unchanged sources (idempotent)."""
    try:
        st = p.stat()
        return f"{int(st.st_mtime)}:{st.st_size}"
    except Exception:
        return ""


PHOTOS_EPOCH = datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)


def _photos_time(value) -> str | None:
    try:
        if value is None:
            return None
        return (PHOTOS_EPOCH + datetime.timedelta(seconds=float(value))).isoformat()
    except Exception:
        return None


def _int_or_zero(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _float_or_none(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _valid_location(lat, lon) -> tuple[float | None, float | None]:
    lat_f = _float_or_none(lat)
    lon_f = _float_or_none(lon)
    if lat_f is None or lon_f is None:
        return None, None
    if lat_f == -180.0 and lon_f == -180.0:
        return None, None
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return None, None
    return lat_f, lon_f


def _sqlite_ro(db: Path) -> sqlite3.Connection:
    uri = "file:" + quote(str(db), safe="/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    except Exception:
        return set()


def _col(columns: set[str], name: str, alias: str, default: str = "NULL") -> str:
    return f"a.{name} AS {alias}" if name in columns else f"{default} AS {alias}"


def _iter_photos_metadata(db: Path, limit: int):
    """Yield read-only metadata rows from Photos.sqlite.

    Photos schema changes across macOS releases. Keep this slice fail-open: if the
    DB, table, or minimum identity columns are missing, emit no rows instead of
    touching Photos internals or crashing the heartbeat.
    """
    if not db.is_file():
        print(f"[media-atomize] Photos DB {db} not present - nothing to ingest (fail-open)")
        return
    try:
        conn = _sqlite_ro(db)
    except Exception as exc:
        print(f"[media-atomize] Photos DB {db} not readable ({exc}); skipping (fail-open)")
        return
    try:
        asset_cols = _table_columns(conn, "ZASSET")
        if not {"Z_PK", "ZUUID"} <= asset_cols:
            print("[media-atomize] Photos DB missing ZASSET identity columns - skipping (fail-open)")
            return

        resource_cols = _table_columns(conn, "ZINTERNALRESOURCE")
        has_resources = {"Z_PK", "ZASSET"} <= resource_cols
        resource_join = "LEFT JOIN ZINTERNALRESOURCE r ON r.ZASSET = a.Z_PK" if has_resources else ""
        resource_count = "COUNT(r.Z_PK)" if has_resources else "0"
        resource_bytes = "COALESCE(SUM(COALESCE(r.ZDATALENGTH, 0)), 0)" if has_resources and "ZDATALENGTH" in resource_cols else "0"
        order_col = "a.ZDATECREATED" if "ZDATECREATED" in asset_cols else "a.Z_PK"
        selects = [
            "a.Z_PK AS pk",
            "a.ZUUID AS uuid",
            _col(asset_cols, "ZFILENAME", "filename"),
            _col(asset_cols, "ZDATECREATED", "date_created"),
            _col(asset_cols, "ZADDEDDATE", "date_added"),
            _col(asset_cols, "ZKIND", "asset_kind", "0"),
            _col(asset_cols, "ZUNIFORMTYPEIDENTIFIER", "uti"),
            _col(asset_cols, "ZWIDTH", "width", "0"),
            _col(asset_cols, "ZHEIGHT", "height", "0"),
            _col(asset_cols, "ZDURATION", "duration", "0"),
            _col(asset_cols, "ZLATITUDE", "latitude"),
            _col(asset_cols, "ZLONGITUDE", "longitude"),
            _col(asset_cols, "ZISDETECTEDSCREENSHOT", "is_screenshot", "0"),
            _col(asset_cols, "ZFAVORITE", "favorite", "0"),
            _col(asset_cols, "ZHIDDEN", "hidden", "0"),
            f"{resource_count} AS local_resource_count",
            f"{resource_bytes} AS local_resource_bytes",
        ]
        query = f"""
            SELECT {", ".join(selects)}
            FROM ZASSET a
            {resource_join}
            GROUP BY a.Z_PK
            ORDER BY {order_col} DESC, a.Z_PK DESC
            LIMIT ?
        """
        for row in conn.execute(query, (int(limit),)):
            yield row
    except Exception as exc:
        print(f"[media-atomize] Photos metadata query failed ({exc}); skipping (fail-open)")
        return
    finally:
        conn.close()


def _photo_media_kind(kind: int, uti: str | None) -> str:
    uti_l = (uti or "").lower()
    if kind == 1 or "movie" in uti_l or "video" in uti_l or uti_l.endswith(".mpeg-4"):
        return "video"
    return "image"


def atomize_photo_metadata(row, library_name: str) -> dict:
    uuid = str(row["uuid"] or row["pk"])
    filename = row["filename"] or f"{uuid}"
    created = _photos_time(row["date_created"])
    added = _photos_time(row["date_added"])
    width = _int_or_zero(row["width"])
    height = _int_or_zero(row["height"])
    local_resource_count = _int_or_zero(row["local_resource_count"])
    local_resource_bytes = _int_or_zero(row["local_resource_bytes"])
    is_screenshot = bool(_int_or_zero(row["is_screenshot"]))
    lat, lon = _valid_location(row["latitude"], row["longitude"])
    media_kind = _photo_media_kind(_int_or_zero(row["asset_kind"]), row["uti"])
    duration = _float_or_none(row["duration"])
    sig = "|".join(
        str(v or "")
        for v in [
            uuid,
            filename,
            created,
            added,
            media_kind,
            row["uti"],
            width,
            height,
            duration,
            is_screenshot,
            local_resource_count,
            local_resource_bytes,
            lat,
            lon,
        ]
    )
    bits = [
        f"Photos asset {filename}",
        f"kind: {media_kind}",
        f"screenshot: {'yes' if is_screenshot else 'no'}",
        f"resources: {local_resource_count}",
    ]
    if created:
        bits.append(f"created: {created}")
    if width and height:
        bits.append(f"dimensions: {width}x{height}")
    bits.append(f"location: {'present' if lat is not None and lon is not None else 'not recorded'}")
    if row["uti"]:
        bits.append(f"uti: {row['uti']}")
    atom = {
        "id": _hash("photo-metadata", sig),
        "text": ". ".join(bits) + ".",
        "source": f"photos://{library_name}/{uuid}",
        "kind": "photo_metadata",
        "photos_uuid": uuid,
        "filename": filename,
        "created_at": created,
        "added_at": added,
        "media_kind": media_kind,
        "uti": row["uti"],
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "is_screenshot": is_screenshot,
        "favorite": bool(_int_or_zero(row["favorite"])),
        "hidden": bool(_int_or_zero(row["hidden"])),
        "local_resource_count": local_resource_count,
        "local_resource_bytes": local_resource_bytes,
        "has_location": lat is not None and lon is not None,
        "latitude": lat,
        "longitude": lon,
        "library": library_name,
        "metadata_signature": _hash(sig),
    }
    return atom


def atomize_photos_metadata(db: Path, limit: int) -> list[dict]:
    library_name = db.parent.parent.name if db.parent.name == "database" else db.parent.name
    return [atomize_photo_metadata(row, library_name) for row in _iter_photos_metadata(db, limit)]


# ─── ingest + atomize ────────────────────────────────────────────────

def _iter_docs(src: Path, limit: int):
    """Yield up to ``limit`` document paths under ``src`` (bounded, deterministic, fail-open).

    Uses os.walk with sorted dirs/files and an early stop so a huge tree is never fully
    materialised; skips dotfiles/dot-dirs (system/cache cruft)."""
    if not src.is_dir():
        return
    n = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith("."):
                continue
            p = Path(root) / name
            if p.suffix.lower() not in DOC_EXTS:
                continue
            yield p
            n += 1
            if n >= limit:
                return


def _pdf_text(path: Path) -> str:
    """Extract PDF text via poppler's pdftotext if present; fail-open to '' otherwise.

    Slice 1 has no hard PDF dependency: if poppler isn't installed the PDF is simply
    skipped this slice (counted), never a crash. text/md/txt still atomize."""
    exe = shutil.which("pdftotext")
    if not exe:
        return ""
    try:
        proc = subprocess.run(
            [exe, "-q", "-enc", "UTF-8", str(path), "-"],
            capture_output=True, text=True, timeout=PDF_TIMEOUT, check=False,
        )
        return proc.stdout or ""
    except Exception:
        return ""


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf_text(path)
    try:
        return path.read_text(errors="replace")
    except Exception:
        return ""


def _chunk(text: str) -> list[str]:
    """Split text into section-level chunks: markdown headings first, else paragraph blocks;
    oversize sections are hard-wrapped and tiny adjacent ones coalesced toward MIN_CHARS."""
    text = text.strip()
    if not text:
        return []
    positions = [m.start() for m in HEAD_RE.finditer(text)]
    if positions:
        sections = []
        if positions[0] > 0:
            sections.append(text[: positions[0]])
        bounds = positions + [len(text)]
        for i in range(len(positions)):
            sections.append(text[positions[i]: bounds[i + 1]])
    else:
        sections = PARA_RE.split(text)

    sized: list[str] = []
    for s in sections:
        s = s.strip()
        if not s:
            continue
        if len(s) <= MAX_CHARS:
            sized.append(s)
            continue
        for para in PARA_RE.split(s):
            para = para.strip()
            while len(para) > MAX_CHARS:
                sized.append(para[:MAX_CHARS])
                para = para[MAX_CHARS:]
            if para:
                sized.append(para)

    merged: list[str] = []
    for s in sized:
        if merged and len(merged[-1]) < MIN_CHARS:
            merged[-1] = merged[-1] + "\n\n" + s
        else:
            merged.append(s)
    return merged


def atomize_doc(path: Path) -> list[dict]:
    """One document → its section-level atoms (dicts). Bytes never inlined beyond the text."""
    chunks = _chunk(_extract_text(path))
    atoms = []
    for i, c in enumerate(chunks):
        atoms.append({
            "id": _hash(str(path), str(i), c[:120]),
            "text": c,
            "source": str(path),
            "doc": path.name,
            "section": i,
            "kind": "doc",
        })
    return atoms


# ─── store (content-addressed, dedup, idempotent) ────────────────────

def _store_atom(atom: dict, apply: bool) -> bool:
    """Write ONE atom content-addressed; dedup by id. Returns True if it was new."""
    dst = _atoms_root() / f"{atom['id']}.json"
    if dst.exists():
        return False
    if apply:
        from limen.io import atomic_write_text
        _atoms_root().mkdir(parents=True, exist_ok=True)
        atomic_write_text(dst, json.dumps(atom, ensure_ascii=False, indent=2))
    return True


def _load_atoms(limit: int) -> list[dict]:
    """Load up to ``limit`` stored atoms (for the --converge proof). Fail-open."""
    root = _atoms_root()
    out: list[dict] = []
    if not root.is_dir():
        return out
    for p in sorted(root.glob("*.json"))[:limit]:
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            continue
    return out


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except Exception:
        return {"absorbed": {}}


def _save_state(state: dict) -> None:
    from limen.io import atomic_write_text
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(_state_path(), json.dumps(state, indent=2))


# ─── prove the engine reuse (offline) ────────────────────────────────

def _prove_converge(idea: str, limit: int = 50) -> None:
    """Distill the stored atoms at ``idea`` with the OFFLINE kit — proof the media atoms
    flow through the SAME engine that distills his words. No network, no write-back."""
    from limen.converge import Shot, _build_dry_run_kit, converge
    atoms = _load_atoms(limit)
    if not atoms:
        print("[media-atomize] no stored atoms yet — nothing to converge")
        return
    shots = [Shot(id=a["id"], text=a.get("text", ""), source=a.get("source", "")) for a in atoms]
    r = converge(idea, shots, **_build_dry_run_kit())
    head = r.better_version.strip().splitlines()[:6]
    print("── media converge (offline proof) ──")
    print(f"  idea: {idea}")
    print(f"  atoms: {len(shots)}  score: {r.score:.3f}  promoted: {r.promoted}  "
          f"cited: {len(r.cited_losers)}  next_shots: {len(r.next_shots)}")
    if head:
        print("  better_version (head): " + " ".join(head)[:300])


# ─── main ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="media-atomize — personal media → first-class Shot atoms")
    ap.add_argument("--apply", action="store_true", help="write atoms/state/log (else preview)")
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LIMEN_MEDIA_LIMIT", "50")),
                    help="max source items atomized per run (bounded)")
    ap.add_argument("--src", default=None, help="docs source dir (default: Archive4T CloudDocs copy)")
    ap.add_argument("--photos-metadata", action="store_true",
                    help="atomize read-only Photos.sqlite metadata instead of docs")
    ap.add_argument("--photos-db", default=None,
                    help="Photos.sqlite path (default: ~/Pictures/Photos Library.photoslibrary/database/Photos.sqlite)")
    ap.add_argument("--converge", metavar="IDEA", default=None,
                    help="after atomizing, distill the stored atoms at IDEA (offline proof)")
    args = ap.parse_args(argv)

    state = _load_state()
    mode = "apply" if args.apply else "preview"

    if args.photos_metadata:
        db = Path(args.photos_db).expanduser() if args.photos_db else _photos_db_path()
        absorbed: dict = state.get("photos_metadata_absorbed", {})
        assets = atoms_new = screenshots = 0
        done: list[tuple[str, str]] = []
        for atom in atomize_photos_metadata(db, args.limit):
            uuid = atom.get("photos_uuid") or atom["id"]
            sig = atom.get("metadata_signature") or atom["id"]
            if sig and absorbed.get(str(uuid)) == sig:
                continue
            wrote = _store_atom(atom, args.apply)
            assets += 1
            atoms_new += int(wrote)
            screenshots += int(bool(atom.get("is_screenshot")))
            done.append((str(uuid), str(sig)))
        if args.apply and done:
            for uuid, sig in done:
                absorbed[uuid] = sig
            state["photos_metadata_absorbed"] = absorbed
            _save_state(state)
            try:
                _log_path().parent.mkdir(parents=True, exist_ok=True)
                with _log_path().open("a") as fh:
                    fh.write(json.dumps({"ts": _now().isoformat(), "photos_assets": assets,
                                         "atoms_new": atoms_new, "screenshots": screenshots}) + "\n")
            except Exception:
                pass
        print(f"[media-atomize] {assets} Photos assets -> {atoms_new} new atoms, "
              f"{screenshots} screenshots [{mode}] store={_atoms_root()}")
    else:
        src = Path(args.src).expanduser() if args.src else _src_root()
        absorbed: dict = state.get("absorbed", {})

        docs = atoms_new = skipped_pdf = 0
        done: list[tuple[str, str]] = []
        if not src.is_dir():
            print(f"[media-atomize] source {src} not present - nothing to ingest (fail-open)")
        else:
            for p in _iter_docs(src, args.limit):
                sig = _sig(p)
                if sig and absorbed.get(str(p)) == sig:
                    continue  # unchanged since last absorb -> idempotent skip
                try:
                    shots = atomize_doc(p)
                except Exception as exc:  # never crash the heartbeat
                    print(f"[media-atomize] {p.name}: atomize failed ({exc}); skipping")
                    continue
                if not shots:
                    if p.suffix.lower() == ".pdf":
                        skipped_pdf += 1
                    continue
                wrote = sum(1 for a in shots if _store_atom(a, args.apply))
                docs += 1
                atoms_new += wrote
                done.append((str(p), sig))
                print(f"[media-atomize] {p.name}: {len(shots)} sections -> {wrote} new atoms"
                      f"{'' if args.apply else ' (preview)'}")

        if args.apply and done:
            for sp, sg in done:
                absorbed[sp] = sg
            state["absorbed"] = absorbed
            _save_state(state)
            try:
                _log_path().parent.mkdir(parents=True, exist_ok=True)
                with _log_path().open("a") as fh:
                    fh.write(json.dumps({"ts": _now().isoformat(), "docs": docs,
                                         "atoms_new": atoms_new, "skipped_pdf": skipped_pdf}) + "\n")
            except Exception:
                pass

        pdf_note = f", {skipped_pdf} pdf skipped (no pdftotext)" if skipped_pdf else ""
        print(f"[media-atomize] {docs} docs -> {atoms_new} new atoms{pdf_note} "
              f"[{mode}] store={_atoms_root()}")

    if args.converge:
        _prove_converge(args.converge)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
