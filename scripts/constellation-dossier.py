#!/usr/bin/env python3
"""
constellation-dossier — per-project brainstorm dossiers from the conversation corpus.

For one constellation project (or --all), reads the register's keyword list,
sweeps every populated conversation corpus under the CCE corpus home, and
assembles two dossier halves:

  private  ~/Workspace/_people-private/people/<pipeline_slug>/projects/<project>-dossier.md
           (full excerpts; ARCA-sealed store)
  public   …/projects/<project>-dossier.public.md
           (same skeleton, passed through publication-policy redaction —
           the CONST-*-DOSSIER task lands it in the project repo by PR and
           records the repo path in the register's `dossier` field)

The corpus is the sanctioned source (CONST-CORPUS-REFRESH populates it via
`cce provider import` / live-session pulls); an empty corpus is a loud exit,
never a silent empty dossier.

Usage:
  scripts/constellation-dossier.py --slug jessica --project styx          # dry-run
  scripts/constellation-dossier.py --slug jessica --project styx --write
  scripts/constellation-dossier.py --all --write
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "organs" / "consulting" / "constellation" / "registry.yaml"
OVERLAY = Path(
    os.environ.get(
        "LIMEN_CONSTELLATION_OVERLAY",
        str(Path.home() / "Workspace" / "_people-private" / "constellation" / "registry-private.yaml"),
    )
)
PEOPLE_STORE = Path(
    os.environ.get(
        "LIMEN_PEOPLE_STORE",
        str(Path.home() / "Workspace" / "_people-private" / "people"),
    )
)
CORPUS_EXTS = {".jsonl", ".json", ".md", ".txt"}
EXCERPT_RADIUS = 240
MAX_HITS_PER_KEYWORD = 40


def _live_root() -> Path:
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout.strip()
    return Path(common).parent


def _corpus_home() -> Path:
    """Parent dir under which per-corpus dirs live (drop_root.parent by CCE convention)."""
    env = os.environ.get("CCE_SOURCE_DROP_ROOT")
    drop = Path(env).expanduser() if env else _live_root() / "source-drop"
    return drop.parent


def _corpus_ids() -> list[str]:
    sys.path.insert(0, str(_live_root() / "conversation-corpus-check" / "src"))
    try:
        from conversation_corpus_engine.provider_catalog import PROVIDER_CONFIG  # type: ignore
    except Exception as exc:  # noqa: BLE001 — any import failure is the same finding
        print(f"ERROR: conversation-corpus-engine not importable: {exc}", file=sys.stderr)
        return []
    ids: list[str] = []
    for cfg in PROVIDER_CONFIG.values():
        for key in ("default_corpus_id", "fallback_corpus_id"):
            value = cfg.get(key) if isinstance(cfg, dict) else None
            if value and value not in ids:
                ids.append(value)
    return ids


def _populated_corpora() -> list[Path]:
    home = _corpus_home()
    dirs = []
    for cid in _corpus_ids():
        candidate = home / cid
        if candidate.is_dir() and any(candidate.iterdir()):
            dirs.append(candidate)
    return dirs


def _pipeline_slug(slug: str) -> str | None:
    if not OVERLAY.exists():
        return None
    for row in yaml.safe_load(OVERLAY.read_text(encoding="utf-8")).get("people") or []:
        if row.get("slug") == slug:
            return row.get("pipeline_slug")
    return None


def _projects(slug_filter: str | None, project_filter: str | None) -> list[tuple[str, dict]]:
    doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    out = []
    for person in doc.get("people") or []:
        slug = person.get("slug")
        if slug_filter and slug != slug_filter:
            continue
        for row in person.get("projects") or []:
            if project_filter and row.get("name") != project_filter:
                continue
            out.append((slug, row))
    return out


def _sweep(corpora: list[Path], keywords: list[str]) -> dict[str, list[tuple[str, str]]]:
    """keyword -> [(source locator, excerpt)] across every populated corpus."""
    patterns = {kw: re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords}
    hits: dict[str, list[tuple[str, str]]] = {kw: [] for kw in keywords}
    for corpus in corpora:
        for path in sorted(corpus.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in CORPUS_EXTS:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            locator = f"{corpus.name}/{path.relative_to(corpus)}"
            for kw, pattern in patterns.items():
                if len(hits[kw]) >= MAX_HITS_PER_KEYWORD:
                    continue
                for match in pattern.finditer(text):
                    start = max(0, match.start() - EXCERPT_RADIUS)
                    end = min(len(text), match.end() + EXCERPT_RADIUS)
                    excerpt = " ".join(text[start:end].split())
                    hits[kw].append((locator, excerpt))
                    if len(hits[kw]) >= MAX_HITS_PER_KEYWORD:
                        break
    return hits


def _render(slug: str, project: dict, corpora: list[Path], hits: dict[str, list[tuple[str, str]]]) -> str:
    lines = [
        f"# {project['name']} — brainstorm dossier",
        "",
        f"Generated {date.today().isoformat()} by scripts/constellation-dossier.py for `{slug}`.",
        f"Corpora swept: {', '.join(c.name for c in corpora)}.",
        "Source of truth for the person→project map: organs/consulting/constellation/registry.yaml.",
        "",
    ]
    total = sum(len(v) for v in hits.values())
    lines.append(f"**{total} excerpt(s)** across {sum(1 for v in hits.values() if v)} matched keyword(s).")
    lines.append("")
    for kw, rows in hits.items():
        if not rows:
            continue
        lines.append(f"## {kw}")
        lines.append("")
        for locator, excerpt in rows:
            lines.append(f"- `{locator}` — {excerpt}")
        lines.append("")
    if total == 0:
        lines.append("_No corpus matches yet — re-run after the next corpus refresh._")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble per-project brainstorm dossiers from the corpus.")
    parser.add_argument("--slug", help="constellation person slug")
    parser.add_argument("--project", help="project name within the slug")
    parser.add_argument("--all", action="store_true", help="every project in the register")
    parser.add_argument("--write", action="store_true", help="write dossier files (default: dry-run report)")
    args = parser.parse_args()

    if not args.all and not (args.slug and args.project):
        parser.error("--slug and --project (or --all) required")

    corpora = _populated_corpora()
    if not corpora:
        print(
            f"ERROR: no populated corpus under {_corpus_home()} — run the corpus refresh "
            "(CONST-CORPUS-REFRESH) before assembling dossiers",
            file=sys.stderr,
        )
        return 1

    targets = _projects(None if args.all else args.slug, None if args.all else args.project)
    if not targets:
        print("ERROR: no matching register projects", file=sys.stderr)
        return 1

    failures = 0
    for slug, project in targets:
        pipeline = _pipeline_slug(slug)
        if not pipeline:
            print(f"SKIP  {slug}/{project['name']}: no pipeline_slug in overlay", file=sys.stderr)
            failures += 1
            continue
        hits = _sweep(corpora, [str(k) for k in project.get("keywords") or []])
        body = _render(slug, project, corpora, hits)
        out_dir = PEOPLE_STORE / pipeline / "projects"
        private = out_dir / f"{project['name']}-dossier.md"
        public = out_dir / f"{project['name']}-dossier.public.md"
        total = sum(len(v) for v in hits.values())
        if not args.write:
            print(f"DRY   {slug}/{project['name']}: {total} excerpt(s) -> {private}")
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        private.write_text(body, encoding="utf-8")
        public.write_text(body, encoding="utf-8")
        redact = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "publication-policy.py"), "redact", str(public), "--apply"],
            capture_output=True,
            text=True,
        )
        if redact.returncode != 0:
            print(f"FAIL  {slug}/{project['name']}: redaction failed — public half removed", file=sys.stderr)
            public.unlink(missing_ok=True)
            failures += 1
            continue
        print(f"WROTE {slug}/{project['name']}: {total} excerpt(s)")
        print(f"      private: {private}")
        print(f"      public (redacted, land by PR): {public}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
