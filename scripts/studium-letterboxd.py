#!/usr/bin/env python3
"""studium-letterboxd.py — ingest Anthony's Letterboxd watch history into the Studium (read-only).

His ask: "can you interact with letterboxd? my watch history?" There is no Letterboxd connector and their
API is approval-gated, so this is the keyless cascade ([[cascade-fallback-principle]], never a dead "no"):

  1. CSV EXPORT (ideal, complete) — Letterboxd → Settings → Import & Export → *Export Your Data* → a ZIP
     (watched.csv · diary.csv · ratings.csv · reviews.csv · watchlist.csv). Drop it in ~/Downloads; this
     auto-discovers the newest `letterboxd-*.zip` (or an unzipped dir) and ingests the whole history.
  2. PUBLIC RSS (live, partial) — `--user <name>` pulls letterboxd.com/<user>/rss/ (recent diary only).
  3. (manual) browser on his session — out of scope for this script; the daily face surfaces the path.

Output: logs/letterboxd-history.json = {source, user, generated_at, count, films:[{title, year, slug,
rating, watched_date, liked, uri}]}. studium.py + studium-objectlessons.py read it by `slug` to mark films
he has SEEN and to join his viewing onto his own object-lessons DB.

POSTURE: read-only on HIS OWN data; writes only logs/. NEVER posts/logs to Letterboxd (that is his gate).
Fail-OPEN: with no source it writes an empty history + the one hand-atom, and prints the GH-issue path; it
never errors, so the daily face always renders.

Usage:
  python3 scripts/studium-letterboxd.py                  # auto-discover the CSV export in ~/Downloads
  python3 scripts/studium-letterboxd.py --export <path>  # an explicit zip or unzipped export dir
  python3 scripts/studium-letterboxd.py --user <name>    # public RSS (recent diary), keyless
"""
import csv
import io
import json
import os
import re
import sys
import tempfile
import unicodedata
import urllib.request
import zipfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
DOWNLOADS = Path(os.path.expanduser(os.environ.get("LIMEN_DOWNLOADS", "~/Downloads")))
OUT = LOGS / "letterboxd-history.json"

# the CSV members the Letterboxd export ships (we read whichever exist; later files enrich earlier ones)
CSV_MEMBERS = ["watched.csv", "diary.csv", "ratings.csv", "reviews.csv"]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def slugify(name, year=None):
    """Approximate Letterboxd's film slug from Name (+Year). Imperfect for disambiguated titles — the
    crosswalk also matches on (title, year), so a near-miss slug still joins."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or (str(year) if year else "")


def _slug_from_uri(uri):
    m = re.search(r"/film/([^/]+)/?", str(uri or ""))
    return m.group(1) if m else ""


# ── source 1: the CSV export (zip or dir) ─────────────────────────────────────────
def _discover_export():
    """Newest letterboxd export in ~/Downloads: a `letterboxd-*.zip`, or a dir/zip holding watched.csv."""
    cands = []
    if DOWNLOADS.is_dir():
        for p in DOWNLOADS.glob("letterboxd-*.zip"):
            cands.append(p)
        for p in DOWNLOADS.glob("letterboxd*"):
            if p.is_dir() and (p / "watched.csv").exists():
                cands.append(p)
        # a loose unzipped export (watched.csv sitting directly in Downloads)
        if (DOWNLOADS / "watched.csv").exists():
            cands.append(DOWNLOADS)
    cands = sorted(set(cands), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return cands[0] if cands else None


def _read_member(src: Path, member: str):
    """Return the text of `member` from a zip or a dir, or None."""
    try:
        if src.is_dir():
            p = src / member
            return p.read_text(errors="replace") if p.exists() else None
        if zipfile.is_zipfile(src):
            with zipfile.ZipFile(src) as z:
                names = {n.split("/")[-1]: n for n in z.namelist()}
                if member in names:
                    return z.read(names[member]).decode("utf-8", "replace")
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def _merge_row(films, row):
    name = (row.get("Name") or "").strip()
    if not name:
        return
    year = (row.get("Year") or "").strip()
    slug = _slug_from_uri(row.get("Letterboxd URI")) or slugify(name, year)
    rec = films.setdefault(slug, {"title": name, "year": year, "slug": slug,
                                  "rating": None, "watched_date": None, "liked": False, "uri": row.get("Letterboxd URI", "")})
    if row.get("Rating"):
        rec["rating"] = (row.get("Rating") or "").strip()
    wd = (row.get("Watched Date") or row.get("Date") or "").strip()
    if wd and not rec["watched_date"]:
        rec["watched_date"] = wd


def ingest_export(src: Path):
    films = {}
    used = []
    for member in CSV_MEMBERS:
        text = _read_member(src, member)
        if not text:
            continue
        used.append(member)
        for row in csv.DictReader(io.StringIO(text)):
            _merge_row(films, row)
    return list(films.values()), used


# ── source 2: public RSS (recent diary) ───────────────────────────────────────────
def ingest_rss(user):
    url = f"https://letterboxd.com/{user}/rss/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "studium/1.0 (+limen)"})
        with urllib.request.urlopen(req, timeout=12) as r:  # noqa: S310 (his own public feed, https)
            xml = r.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — network/sandbox/private profile → fail open
        return None
    films = {}
    for item in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL):
        title = re.search(r"<letterboxd:filmTitle>(.*?)</letterboxd:filmTitle>", item, re.DOTALL)
        yr = re.search(r"<letterboxd:filmYear>(.*?)</letterboxd:filmYear>", item, re.DOTALL)
        rating = re.search(r"<letterboxd:memberRating>(.*?)</letterboxd:memberRating>", item, re.DOTALL)
        wd = re.search(r"<letterboxd:watchedDate>(.*?)</letterboxd:watchedDate>", item, re.DOTALL)
        link = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
        name = (title.group(1).strip() if title else "")
        if not name:
            continue
        year = (yr.group(1).strip() if yr else "")
        slug = slugify(name, year)
        films[slug] = {"title": name, "year": year, "slug": slug,
                       "rating": (rating.group(1).strip() if rating else None),
                       "watched_date": (wd.group(1).strip() if wd else None),
                       "liked": False, "uri": (link.group(1).strip() if link else "")}
    return list(films.values())


def main():
    args = sys.argv[1:]
    user = None
    export = None
    if "--user" in args:
        i = args.index("--user")
        user = args[i + 1] if i + 1 < len(args) else None
    if "--export" in args:
        i = args.index("--export")
        export = Path(os.path.expanduser(args[i + 1])) if i + 1 < len(args) else None

    films, source, used = [], None, []

    # 1) explicit or discovered CSV export (the complete, keyless source)
    src = export or _discover_export()
    if src and src.exists():
        films, used = ingest_export(src)
        if films:
            source = f"csv-export:{src.name}"

    # 2) public RSS (partial, live)
    if not films and user:
        rss = ingest_rss(user)
        if rss:
            films, source = rss, f"rss:{user}"

    LOGS.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "user": user,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": str(date.today()),
        "count": len(films),
        "films": sorted(films, key=lambda f: (f.get("watched_date") or "", f.get("title") or ""), reverse=True),
    }
    if not films:
        payload["needs"] = (
            "No Letterboxd source found. Drop your export ZIP (Settings → Import & Export → Export Your Data) "
            "in ~/Downloads, or run with --user <your-letterboxd-name> for the public RSS. "
            "Tracked as a GitHub issue on the object-lessons repo."
        )
    _atomic_write(OUT, json.dumps(payload, indent=2))

    if films:
        print(f"studium-letterboxd: {len(films)} films from {source} ({', '.join(used) or 'rss'}) -> {OUT}")
    else:
        print(f"studium-letterboxd: no source yet (fail-open empty history) -> {OUT}\n  {payload['needs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
