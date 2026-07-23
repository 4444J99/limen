#!/usr/bin/env python3
"""
Collaborator Constellation Register — Rules #1-7.

Rule #1 — Completeness: version `constellation.v1`, owner `consulting`, a
non-empty people list; every person carries slug, tier, projects; every
project carries name, stage, public_face_state within the declared enums.

Rule #2 — Name Discipline: the register is world-readable, so a slug is a
first name plus at most a single-letter initial (`rob`, `john-m`) — the
pattern mechanically forbids surnames in the public half.

Rule #3 — PII Lint: no phone-like digit runs, no email addresses, no
@handles anywhere in the file. Contact data lives in the relationship
pipeline's people.json (private), never here.

Rule #4 — Cross-Refs: a non-null engagement_ref / funnel_instance_ref /
dossier must point at a path that exists (run from the repo root).

Rule #5 — Single Org: every repo and related_repos entry lives under
`organvm/` — the estate registry's one canonical org.

Rule #6 — Overlay Parity (only when the private store is reachable): the
private overlay carries the same slug set, and every private row declares
pipeline_slug, protocol_state, and channel_state within their enums. In CI
(store absent) this rule is skipped, not failed.

Rule #7 — Access Cross-Check (only when institutio/github/access.yaml is
reachable): every grant's `person` names a registered slug, and every
granted repo appears in that person's project rows — a partner grant with
no project relationship is a partition violation. GitHub logins stay in
the access registry (gitvs-owned), never here; grant-shape validation
(roles, ceiling, never-grant) is gitvs parity's job, not this rule's.

Usage:
  python organs/consulting/constellation/validate-constellation.py
  python organs/consulting/constellation/validate-constellation.py --quiet
  echo $?   # 0 = pass, 1 = violations, 2 = unusable input
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

DEFAULT_REGISTRY = Path("organs/consulting/constellation/registry.yaml")
DEFAULT_OVERLAY = Path(
    os.environ.get(
        "LIMEN_CONSTELLATION_OVERLAY",
        str(Path.home() / "Workspace" / "_people-private" / "constellation" / "registry-private.yaml"),
    )
)
# One knob per fact: the access-registry path is owned by LIMEN_GITVS_ACCESS (gitvs is the
# registry's owner) — a second env name here would shadow it.
DEFAULT_ACCESS = Path(os.environ.get("LIMEN_GITVS_ACCESS", "institutio/github/access.yaml"))

TIERS = {"T1", "T2", "T3"}
STAGES = {"idea", "dossier", "building", "mvp", "live", "funnelized"}
FACES = {"none", "pending-split", "readme", "portal", "funnelized"}
PROTOCOL_STATES = {"MISSING", "DRAFT", "PROVEN"}
CHANNEL_STATES = {"active", "in-flight", "dormant"}

SLUG_RE = re.compile(r"^[a-z]+(-[a-z])?$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s.-]?){10,}(?!\d)")
HANDLE_RE = re.compile(r"(?<![\w/])@[A-Za-z0-9_]{3,}")


def _walk_strings(node: Any) -> list[str]:
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(_walk_strings(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_walk_strings(item))
    return out


def _validate_registry(path: Path) -> tuple[list[str], dict[str, Any] | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read registry: {exc}"], None
    try:
        doc: Any = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return [f"YAML parse error: {exc}"], None
    if not isinstance(doc, dict):
        return ["document is not a YAML mapping"], None

    v: list[str] = []

    # Rule #1 — Completeness
    if doc.get("version") != "constellation.v1":
        v.append("Rule #1 violation: version must be 'constellation.v1'")
    if doc.get("owner") != "consulting":
        v.append("Rule #1 violation: owner must be 'consulting'")
    people = doc.get("people")
    if not isinstance(people, list) or not people:
        v.append("Rule #1 violation: people must be a non-empty list")
        people = []
    for person in people:
        if not isinstance(person, dict):
            v.append("Rule #1 violation: person entry is not a mapping")
            continue
        slug = str(person.get("slug", ""))
        label = slug or "<missing slug>"
        if not slug:
            v.append("Rule #1 violation: person missing slug")
        if person.get("tier") not in TIERS:
            v.append(f"Rule #1 violation: {label} tier must be one of {sorted(TIERS)}")
        projects = person.get("projects")
        if not isinstance(projects, list) or not projects:
            v.append(f"Rule #1 violation: {label} projects must be a non-empty list")
            projects = []
        for project in projects:
            if not isinstance(project, dict):
                v.append(f"Rule #1 violation: {label} project entry is not a mapping")
                continue
            pname = str(project.get("name", "")) or "<unnamed>"
            if not project.get("name"):
                v.append(f"Rule #1 violation: {label} project missing name")
            if project.get("stage") not in STAGES:
                v.append(f"Rule #1 violation: {label}/{pname} stage must be one of {sorted(STAGES)}")
            if project.get("public_face_state") not in FACES:
                v.append(f"Rule #1 violation: {label}/{pname} public_face_state must be one of {sorted(FACES)}")
            keywords = project.get("keywords")
            if not isinstance(keywords, list) or not keywords:
                v.append(f"Rule #1 violation: {label}/{pname} keywords must be a non-empty list")

        # Rule #2 — Name Discipline
        if slug and not SLUG_RE.match(slug):
            v.append(
                f"Rule #2 violation: slug {slug!r} must be a first name plus at most a "
                "single-letter initial — surnames never appear in the public half"
            )

    # Rule #3 — PII Lint
    for text in _walk_strings(doc):
        if EMAIL_RE.search(text):
            v.append(f"Rule #3 violation: email address in {text[:50]!r}")
        if PHONE_RE.search(text):
            v.append(f"Rule #3 violation: phone-like digit run in {text[:50]!r}")
        if HANDLE_RE.search(text):
            v.append(f"Rule #3 violation: @handle in {text[:50]!r}")

    # Rule #4 — Cross-Refs
    for person in people:
        if not isinstance(person, dict):
            continue
        label = str(person.get("slug", "<missing slug>"))
        for key in ("engagement_ref", "funnel_instance_ref"):
            ref = person.get(key)
            if isinstance(ref, str) and ref.strip() and not Path(ref).exists():
                v.append(f"Rule #4 violation: {label} {key} {ref!r} does not exist")
        for project in person.get("projects") or []:
            if not isinstance(project, dict):
                continue
            dossier = project.get("dossier")
            if isinstance(dossier, str) and dossier.strip() and not Path(dossier).exists():
                v.append(f"Rule #4 violation: {label}/{project.get('name')} dossier {dossier!r} does not exist")

    # Rule #5 — Single Org
    for person in people:
        if not isinstance(person, dict):
            continue
        label = str(person.get("slug", "<missing slug>"))
        for project in person.get("projects") or []:
            if not isinstance(project, dict):
                continue
            repos = [project.get("repo")] + list(project.get("related_repos") or [])
            for repo in repos:
                if isinstance(repo, str) and repo and not repo.startswith("organvm/"):
                    v.append(
                        f"Rule #5 violation: {label}/{project.get('name')} repo {repo!r} "
                        "is outside the canonical org (estate.yaml owns placement)"
                    )

    return v, doc


def _validate_overlay(overlay_path: Path, registry: dict[str, Any]) -> list[str]:
    """Rule #6 — parity with the private overlay; skipped when the store is absent."""
    if not overlay_path.exists():
        return []
    v: list[str] = []
    try:
        overlay: Any = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return [f"Rule #6 violation: overlay unreadable: {exc}"]
    if not isinstance(overlay, dict):
        return ["Rule #6 violation: overlay is not a YAML mapping"]

    public_slugs = {
        str(p.get("slug")) for p in registry.get("people") or [] if isinstance(p, dict) and p.get("slug")
    }
    rows = overlay.get("people")
    if not isinstance(rows, list):
        return ["Rule #6 violation: overlay people must be a list"]
    private_slugs = set()
    for row in rows:
        if not isinstance(row, dict):
            v.append("Rule #6 violation: overlay person entry is not a mapping")
            continue
        slug = str(row.get("slug", ""))
        private_slugs.add(slug)
        label = slug or "<missing slug>"
        if not row.get("pipeline_slug"):
            v.append(f"Rule #6 violation: overlay {label} missing pipeline_slug")
        if row.get("protocol_state") not in PROTOCOL_STATES:
            v.append(f"Rule #6 violation: overlay {label} protocol_state must be one of {sorted(PROTOCOL_STATES)}")
        if row.get("channel_state") not in CHANNEL_STATES:
            v.append(f"Rule #6 violation: overlay {label} channel_state must be one of {sorted(CHANNEL_STATES)}")
    if public_slugs != private_slugs:
        v.append(
            f"Rule #6 violation: slug sets differ — public-only {sorted(public_slugs - private_slugs)}, "
            f"overlay-only {sorted(private_slugs - public_slugs)}"
        )
    return v


def _validate_access(access_path: Path, registry: dict[str, Any]) -> list[str]:
    """Rule #7 — access-registry cross-check; skipped when the access registry is absent."""
    if not access_path.exists():
        return []
    try:
        access: Any = yaml.safe_load(access_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return [f"Rule #7 violation: access registry unreadable: {exc}"]
    if not isinstance(access, dict):
        return ["Rule #7 violation: access registry is not a YAML mapping"]

    person_repos: dict[str, set[str]] = {}
    for person in registry.get("people") or []:
        if not isinstance(person, dict) or not person.get("slug"):
            continue
        repos: set[str] = set()
        for project in person.get("projects") or []:
            if not isinstance(project, dict):
                continue
            for repo in [project.get("repo")] + list(project.get("related_repos") or []):
                if isinstance(repo, str) and repo:
                    repos.add(repo)
        person_repos[str(person["slug"])] = repos

    v: list[str] = []
    grants = access.get("grants")
    if not isinstance(grants, dict):
        return v  # grant-shape validation is gitvs parity's job; nothing to cross-check
    for repo, rows in grants.items():
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            slug = str(row.get("person", ""))
            label = slug or "<missing person>"
            if slug not in person_repos:
                v.append(f"Rule #7 violation: grant on {repo!r} names person {label!r} — not a registered slug")
            elif str(repo) not in person_repos[slug]:
                v.append(
                    f"Rule #7 violation: {label} is granted on {repo!r} but has no project row for it — "
                    "a grant with no project relationship is a partition violation"
                )
    return v


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the constellation register against Rules #1-7. Run from the repo root."
    )
    parser.add_argument("path", nargs="?", default=str(DEFAULT_REGISTRY), help="registry YAML path")
    parser.add_argument("--overlay", default=str(DEFAULT_OVERLAY), help="private overlay path (parity check)")
    parser.add_argument("--access", default=str(DEFAULT_ACCESS), help="access registry path (grant cross-check)")
    parser.add_argument("--quiet", action="store_true", help="suppress output; exit code only")
    args = parser.parse_args()

    registry_path = Path(args.path)
    violations, doc = _validate_registry(registry_path)
    overlay_checked = access_checked = False
    if doc is not None:
        overlay_path = Path(args.overlay)
        overlay_checked = overlay_path.exists()
        violations.extend(_validate_overlay(overlay_path, doc))
        access_path = Path(args.access)
        access_checked = access_path.exists()
        violations.extend(_validate_access(access_path, doc))

    if doc is None:
        if not args.quiet:
            for item in violations:
                print(f"ERROR  {item}")
        return 2

    if not args.quiet:
        if violations:
            print(f"FAIL  {registry_path}")
            for item in violations:
                print(f"      violation: {item}")
        else:
            skipped = []
            if not overlay_checked:
                skipped.append("Rule #6 (overlay absent)")
            if not access_checked:
                skipped.append("Rule #7 (access registry absent)")
            scope = "Rules #1-7" if not skipped else f"Rules #1-7 minus skipped: {', '.join(skipped)}"
            print(f"PASS  {registry_path}  |  {scope}")

    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
