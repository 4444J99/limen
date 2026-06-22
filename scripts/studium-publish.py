#!/usr/bin/env python3
"""studium-publish.py — Wings-style multi-channel draft generator for the build-in-public pillar.

For each curated playlist (studium/music/<work>/book-NN.yaml) + its essay (studium/essays/...), emit
ready-to-post DRAFTS in four channels:
  - post.md      a blog / Substack post (the full essay + track table)
  - thread.md    an X / threads thread (hook + one post per track + close)
  - discord.md   a compact #playlists message
  - playlist.md  the ordered tracks + YouTube/Spotify search links (copy-paste to build the playlist)

Drafts land in studium/publish/_drafts/<work>-book-NN/. This SENDS NOTHING — posting / creating the
Discord / making playlists public is Anthony's gate ([[known-owned-pervasive-then-idgaf]]). Wired off
the adaptive-personal-syllabus "Wings" idea (one source → many channel artifacts), consolidated here.

Usage:
  python3 scripts/studium-publish.py                 # all works with curated music
  python3 scripts/studium-publish.py --work iliad     # one work
"""
import os
import sys
import urllib.parse
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
STUDIUM = ROOT / "studium"
DRAFTS = STUDIUM / "publish" / "_drafts"

try:
    import yaml
except ImportError:
    yaml = None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _load_yaml(path, default=None):
    if yaml is None:
        return default
    try:
        return yaml.safe_load(Path(path).read_text()) or default
    except Exception:
        return default


def _search(composer, work):
    q = urllib.parse.quote_plus(f"{composer} {work}")
    return (f"https://www.youtube.com/results?search_query={q}",
            f"https://open.spotify.com/search/{q}")


def _track_table(tracks):
    rows = ["| # | Scene | Track | Force |", "| -: | --- | --- | --- |"]
    for t in tracks:
        rows.append(f"| {t.get('n','')} | {t.get('scene','')} | **{t.get('composer','')}** — "
                    f"{t.get('work','')} | {t.get('force','')} |")
    return "\n".join(rows)


def make_post(m, essay):
    title = m.get("title", "")
    body = essay if essay else (
        f"_{m.get('principle','')}_\n\n{_track_table(m.get('tracks', []))}\n\n" +
        "\n\n".join(f"**{t.get('n')}. {t.get('composer')} — {t.get('work')}** ({t.get('force')}) — "
                    f"{t.get('why','')}" for t in m.get("tracks", [])))
    arc = " → ".join(m.get("force_arc", []))
    return f"# {title}\n\n{body}\n\n---\n_Dominant arc: {arc}. From the Studium — a transmission curriculum (reading · script · translation · music)._\n"


def make_thread(m):
    title = m.get("title", "")
    out = [f"🧵 {title}\n\nScoring this not as \"war\" but as its real emotional arc — "
           f"{' → '.join(m.get('force_arc', [])[:5])}. One piece per beat. 👇"]
    for t in m.get("tracks", []):
        line = f"{t.get('n')}/ {t.get('scene')}\n🎵 {t.get('composer')} — {t.get('work')}\n{t.get('why','')[:200]}"
        out.append(line)
    out.append("Read the book. Copy the original by hand. Translate a line. Then listen.\nThe music is a second commentary system.\n#GreatBooks #ClassicalMusic")
    return "\n\n— — —\n\n".join(out)


def make_discord(m):
    title = m.get("title", "")
    lines = [f"**🎵 {title}**", f"_dominant arc: {' → '.join(m.get('force_arc', []))}_", ""]
    for t in m.get("tracks", []):
        yt, sp = _search(t.get("composer", ""), t.get("work", ""))
        lines.append(f"`{t.get('n'):>2}` **{t.get('composer')}** — {t.get('work')}  ·  *{t.get('scene')}*  ·  [▶]({yt}) [♫]({sp})")
    lines += ["", "_react 🎼 if you'd keep it, 🔁 to suggest a replacement._"]
    return "\n".join(lines)


def make_playlist(m):
    title = m.get("title", "")
    lines = [f"# {title} — playlist", "", "Copy-paste into Spotify/Apple Music, or use the search links.", ""]
    for t in m.get("tracks", []):
        yt, sp = _search(t.get("composer", ""), t.get("work", ""))
        lines.append(f"{t.get('n')}. {t.get('composer')} — {t.get('work')}")
        lines.append(f"   YouTube: {yt}")
        lines.append(f"   Spotify: {sp}")
    return "\n".join(lines) + "\n"


def publish_one(work, music_path):
    m = _load_yaml(music_path)
    if not m or not m.get("tracks"):
        return None
    book = m.get("book")
    slug = f"{work}-book-{int(book):02d}" if book else f"{work}-{music_path.stem}"
    essay_path = STUDIUM / "essays" / work / f"book-{int(book):02d}.md" if book else None
    essay = essay_path.read_text() if (essay_path and essay_path.exists()) else None
    d = DRAFTS / slug
    _atomic_write(d / "post.md", make_post(m, essay))
    _atomic_write(d / "thread.md", make_thread(m))
    _atomic_write(d / "discord.md", make_discord(m))
    _atomic_write(d / "playlist.md", make_playlist(m))
    return slug


def main():
    only = None
    if "--work" in sys.argv:
        try:
            only = sys.argv[sys.argv.index("--work") + 1]
        except IndexError:
            pass
    music_root = STUDIUM / "music"
    made = []
    for work_dir in sorted(music_root.glob("*")) if music_root.exists() else []:
        if not work_dir.is_dir():
            continue
        work = work_dir.name
        if only and work != only:
            continue
        for mp in sorted(work_dir.glob("book-*.yaml")):
            slug = publish_one(work, mp)
            if slug:
                made.append(slug)
    print(f"studium-publish: {len(made)} draft sets in {DRAFTS} (SENT NOTHING) -> {', '.join(made[:6])}{'…' if len(made) > 6 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
