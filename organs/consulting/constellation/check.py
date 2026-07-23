#!/usr/bin/env python3
"""
Constellation task predicates — one executable check per CONST- task shape.

Every board task the constellation seeder emits names one of these
subcommands as its executable predicate (exit 0 ⟺ the task's completion
condition holds). Checks that touch the private people store resolve the
public slug to its pipeline slug through the ARCA-sealed overlay, so no
surname ever appears on the public board.

Usage:
  organs/consulting/constellation/check.py registry
  organs/consulting/constellation/check.py corpus-refresh
  organs/consulting/constellation/check.py proto <slug>
  organs/consulting/constellation/check.py dossier <slug> <project>
  organs/consulting/constellation/check.py stage <slug> <project> <min-stage>
  organs/consulting/constellation/check.py face-state <slug> <project> <min-face>
  organs/consulting/constellation/check.py face-brand <owner/repo> <substring>
  organs/consulting/constellation/check.py face-clean <owner/repo> <substring>
  organs/consulting/constellation/check.py funnel <instance-yaml>
  organs/consulting/constellation/check.py decision-packet <slug> <name>
  organs/consulting/constellation/check.py casestudy <slug> <project>
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
REGISTRY = HERE / "registry.yaml"
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

STAGE_ORDER = ["idea", "dossier", "building", "mvp", "live", "funnelized"]
FACE_ORDER = ["none", "pending-split", "readme", "portal", "funnelized"]


def _fail(msg: str) -> int:
    print(f"FAIL  {msg}")
    return 1


def _ok(msg: str) -> int:
    print(f"OK    {msg}")
    return 0


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _registry_project(slug: str, project: str) -> dict | None:
    doc = _load_yaml(REGISTRY)
    for person in doc.get("people") or []:
        if person.get("slug") == slug:
            for row in person.get("projects") or []:
                if row.get("name") == project:
                    return row
    return None


def _pipeline_slug(slug: str) -> str | None:
    """Public slug -> private pipeline slug via the ARCA-sealed overlay."""
    if not OVERLAY.exists():
        return None
    for row in _load_yaml(OVERLAY).get("people") or []:
        if row.get("slug") == slug:
            return row.get("pipeline_slug")
    return None


def check_registry() -> int:
    proc = subprocess.run(
        [sys.executable, str(HERE / "validate-constellation.py"), "--quiet"],
        cwd=REPO_ROOT,
    )
    return _ok("registry valid") if proc.returncode == 0 else _fail("registry invalid")


def _live_root() -> Path:
    """The live checkout's root — worktrees share its untracked estate (CCE checkout, source-drop)."""
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout.strip()
    return Path(common).parent


def check_corpus_refresh() -> int:
    """Populated ⟺ at least one per-corpus dir (drop_root.parent/<corpus_id>) is non-empty."""
    root = REPO_ROOT if (REPO_ROOT / "conversation-corpus-check" / "src").is_dir() else _live_root()
    sys.path.insert(0, str(root / "conversation-corpus-check" / "src"))
    try:
        from conversation_corpus_engine.provider_catalog import PROVIDER_CONFIG  # type: ignore
    except Exception as exc:  # noqa: BLE001 — any import failure is the same finding
        return _fail(f"conversation-corpus-engine not importable: {exc}")
    env = os.environ.get("CCE_SOURCE_DROP_ROOT")
    drop = Path(env).expanduser() if env else root / "source-drop"
    home = drop.parent
    populated = []
    for cfg in PROVIDER_CONFIG.values():
        for key in ("default_corpus_id", "fallback_corpus_id"):
            cid = cfg.get(key) if isinstance(cfg, dict) else None
            if cid and (home / cid).is_dir() and any((home / cid).iterdir()):
                populated.append(cid)
    if populated:
        return _ok(f"corpus populated: {', '.join(sorted(set(populated)))}")
    return _fail(f"no populated corpus under {home}")


def check_proto(slug: str) -> int:
    pipeline = _pipeline_slug(slug)
    if not pipeline:
        return _fail(f"no pipeline_slug for {slug!r} in overlay (private store required)")
    person_dir = PEOPLE_STORE / pipeline
    if not (person_dir / "open-asks.yaml").exists():
        return _fail(f"{slug}: open-asks.yaml missing in people store")
    profiles = list(person_dir.glob("*entity-profile*"))
    personas = list(person_dir.glob("*dialogue-persona*"))
    if not profiles or not personas:
        return _fail(f"{slug}: entity-profile={len(profiles)} dialogue-persona={len(personas)} (need both)")
    return _ok(f"{slug}: protocol artifacts present ({len(profiles)} profile, {len(personas)} persona)")


def check_dossier(slug: str, project: str) -> int:
    row = _registry_project(slug, project)
    if row is None:
        return _fail(f"{slug}/{project} not in registry")
    if not row.get("dossier"):
        return _fail(f"{slug}/{project} registry dossier field is null")
    pipeline = _pipeline_slug(slug)
    if not pipeline:
        return _fail(f"no pipeline_slug for {slug!r} in overlay")
    private = PEOPLE_STORE / pipeline / "projects" / f"{project}-dossier.md"
    if not private.exists():
        return _fail(f"{slug}/{project}: private dossier missing at {private}")
    return _ok(f"{slug}/{project}: dossier halves present")


def _rank_check(slug: str, project: str, field: str, minimum: str, order: list[str]) -> int:
    row = _registry_project(slug, project)
    if row is None:
        return _fail(f"{slug}/{project} not in registry")
    current = str(row.get(field))
    if current not in order or minimum not in order:
        return _fail(f"{slug}/{project}: {field}={current!r} vs floor {minimum!r} not in enum")
    if order.index(current) >= order.index(minimum):
        return _ok(f"{slug}/{project}: {field}={current} >= {minimum}")
    return _fail(f"{slug}/{project}: {field}={current} < {minimum}")


def _readme_text(repo: str) -> str | None:
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/readme"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        return base64.b64decode(json.loads(proc.stdout)["content"]).decode("utf-8", "replace")
    except (KeyError, ValueError):
        return None


def check_face_brand(repo: str, needle: str) -> int:
    text = _readme_text(repo)
    if text is None:
        return _fail(f"{repo}: README unreadable via gh api")
    if needle.lower() in text.lower():
        return _ok(f"{repo}: README carries {needle!r}")
    return _fail(f"{repo}: README missing {needle!r}")


def check_face_clean(repo: str, needle: str) -> int:
    text = _readme_text(repo)
    if text is None:
        return _fail(f"{repo}: README unreadable via gh api")
    if needle.lower() in text.lower():
        return _fail(f"{repo}: README still contains {needle!r}")
    return _ok(f"{repo}: README clean of {needle!r}")


def check_funnel(instance: str) -> int:
    path = REPO_ROOT / instance
    if not path.exists():
        return _fail(f"funnel instance {instance} does not exist yet")
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "organs/consulting/funnel/validate-funnel.py"), str(path), "--quiet"],
        cwd=REPO_ROOT,
    )
    return _ok(f"{instance} passes Engine Rules") if proc.returncode == 0 else _fail(f"{instance} violations")


def check_casestudy(slug: str, project: str) -> int:
    """The register row owns the case-study pointer; the artifact must be live where it points."""
    row = _registry_project(slug, project)
    if row is None:
        return _fail(f"{slug}/{project} not in registry")
    pointer = str(row.get("case_study") or "")
    if not pointer:
        return _fail(f"{slug}/{project}: registry case_study field is null")
    parts = pointer.split(":", 2)
    if len(parts) != 3 or parts[0] != "git" or parts[1].count("/") != 1 or not parts[2]:
        return _fail(f"{slug}/{project}: case_study must be git:<owner>/<repo>:<path>, got {pointer!r}")
    repo, path = parts[1], parts[2]
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/contents/{path}"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return _fail(f"{slug}/{project}: case_study target {pointer} unreadable via gh api")
    return _ok(f"{slug}/{project}: case study live at {pointer}")


def check_decision_packet(slug: str, name: str) -> int:
    pipeline = _pipeline_slug(slug)
    if not pipeline:
        return _fail(f"no pipeline_slug for {slug!r} in overlay")
    packet = PEOPLE_STORE / pipeline / "decisions" / f"{name}.md"
    if packet.exists():
        return _ok(f"{slug}: decision packet {name} present")
    return _fail(f"{slug}: decision packet missing at {packet}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "registry" and not args:
            return check_registry()
        if cmd == "corpus-refresh" and not args:
            return check_corpus_refresh()
        if cmd == "proto" and len(args) == 1:
            return check_proto(args[0])
        if cmd == "dossier" and len(args) == 2:
            return check_dossier(*args)
        if cmd == "stage" and len(args) == 3:
            return _rank_check(args[0], args[1], "stage", args[2], STAGE_ORDER)
        if cmd == "face-state" and len(args) == 3:
            return _rank_check(args[0], args[1], "public_face_state", args[2], FACE_ORDER)
        if cmd == "face-brand" and len(args) == 2:
            return check_face_brand(*args)
        if cmd == "face-clean" and len(args) == 2:
            return check_face_clean(*args)
        if cmd == "funnel" and len(args) == 1:
            return check_funnel(args[0])
        if cmd == "decision-packet" and len(args) == 2:
            return check_decision_packet(*args)
        if cmd == "casestudy" and len(args) == 2:
            return check_casestudy(*args)
    except (OSError, yaml.YAMLError) as exc:
        return _fail(f"{cmd}: {exc}")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
