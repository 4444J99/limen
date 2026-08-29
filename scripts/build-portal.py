#!/usr/bin/env python3
"""Build a fail-closed public portal from explicit policy and the redacted live census."""

import html
import json
import os
from pathlib import Path

import yaml


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)).resolve()
ESTATE_REGISTRY = ROOT / "institutio" / "github" / "estate.yaml"
IDENTITY_REGISTRY = ROOT / "institutio" / "github" / "repository-identity.json"
CENSUS_DOC = ROOT / "docs" / "github-estate-census.json"
PORTAL_DIR = ROOT / "public-portal"


def load_repository_aliases(path: Path = IDENTITY_REGISTRY) -> dict[str, str]:
    """Map canonical and historical owner/name coordinates to the canonical coordinate."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    repositories = payload.get("repositories")
    if not isinstance(repositories, list):
        raise ValueError("repository identity registry must contain a repositories list")

    aliases: dict[str, str] = {}
    for repository in repositories:
        if not isinstance(repository, dict):
            raise ValueError("repository identity entries must be objects")
        canonical = repository.get("canonical_coordinate")
        historical = repository.get("historical_aliases", [])
        if not isinstance(canonical, str) or canonical.count("/") != 1:
            raise ValueError("repository identity canonical_coordinate must be owner/name")
        if not isinstance(historical, list) or not all(isinstance(value, str) for value in historical):
            raise ValueError("repository identity historical_aliases must be strings")

        for coordinate in [canonical, *historical]:
            if coordinate.count("/") != 1:
                raise ValueError(f"repository identity coordinate must be owner/name: {coordinate}")
            previous = aliases.setdefault(coordinate, canonical)
            if previous != canonical:
                raise ValueError(f"repository identity alias maps to multiple repositories: {coordinate}")
    return aliases


def canonical_coordinate(coordinate: str, aliases: dict[str, str]) -> str:
    """Resolve stale census/policy coordinates through stable repository identity aliases."""

    return aliases.get(coordinate, coordinate)


def build_portal_data(estate: dict, census: dict, aliases: dict[str, str]) -> dict:
    """Join explicit public policy to an exhaustive redacted census; private rows never enter."""

    source_report = census.get("source_report")
    if not isinstance(source_report, dict):
        raise ValueError("GitHub estate census is missing source_report")
    if source_report.get("exhaustive") is not True or source_report.get("semantic_status") != "ready":
        raise ValueError("GitHub estate census is not exhaustive and ready")
    summary = census.get("summary")
    if not isinstance(summary, dict) or summary.get("failure_count") != 0 or summary.get("unaccounted") != 0:
        raise ValueError("GitHub estate census has failures or unaccounted repositories")

    classes = estate.get("classes")
    overrides = estate.get("repo_overrides")
    if not isinstance(classes, dict) or not isinstance(overrides, dict):
        raise ValueError("estate registry must contain classes and repo_overrides mappings")
    public_classes = {
        name
        for name, policy in classes.items()
        if isinstance(policy, dict) and policy.get("visibility") == "public"
    }

    explicit_public: dict[str, str] = {}
    for coordinate, override in overrides.items():
        if not isinstance(coordinate, str) or not isinstance(override, dict):
            raise ValueError("estate repo_overrides entries must be coordinate mappings")
        classification = override.get("class")
        if classification in public_classes:
            explicit_public[canonical_coordinate(coordinate, aliases)] = str(classification)

    control_plane = estate.get("control_plane")
    if not isinstance(control_plane, dict):
        raise ValueError("estate registry is missing control_plane")
    controller = control_plane.get("canonical_coordinate")
    if not isinstance(controller, str) or controller.count("/") != 1:
        raise ValueError("control_plane canonical_coordinate must be owner/name")
    if "conductor" not in public_classes:
        raise ValueError("control-plane conductor is not explicitly public")
    explicit_public[canonical_coordinate(controller, aliases)] = "conductor"

    repositories = census.get("repositories")
    if not isinstance(repositories, list):
        raise ValueError("GitHub estate census is missing repositories")
    live_public: set[str] = set()
    for repository in repositories:
        if not isinstance(repository, dict) or not isinstance(repository.get("private"), bool):
            raise ValueError("GitHub estate census repository rows must carry boolean privacy")
        if repository["private"]:
            if repository.get("name_with_owner"):
                raise ValueError("redacted census exposed a private repository coordinate")
            continue
        coordinate = repository.get("name_with_owner")
        if not isinstance(coordinate, str) or coordinate.count("/") != 1:
            raise ValueError("public census repository rows must carry owner/name")
        if not repository.get("archived", False):
            live_public.add(canonical_coordinate(coordinate, aliases))

    repos = [
        {"coordinate": coordinate, "classification": classification}
        for coordinate, classification in explicit_public.items()
        if coordinate in live_public
    ]
    repos.sort(key=lambda row: row["coordinate"].casefold())
    omitted = sorted(set(explicit_public) - live_public, key=str.casefold)
    return {
        "repos": repos,
        "repo_count": len(repos),
        "explicit_public_count": len(explicit_public),
        "omitted_not_live": omitted,
        "census_generated_at": source_report.get("generated_at"),
    }


def build_html(data: dict) -> str:
    """Render canonical public coordinates only—never local paths, branches, or remote hashes."""

    grouped: dict[str, list[dict]] = {}
    for repository in data.get("repos", []):
        grouped.setdefault(repository["classification"], []).append(repository)

    output = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "    <meta charset='UTF-8'>",
        "    <meta name='viewport' content='width=device-width, initial-scale=1'>",
        "    <title>VLTA / PORTUS - Public Repositories</title>",
        "    <style>",
        "        body { font-family: system-ui, sans-serif; line-height: 1.6; max-width: 960px; margin: 0 auto; padding: 2rem; background-color: #f9f9f9; color: #222; }",
        "        .repo-card { background: white; border: 1px solid #ddd; padding: 0.9rem 1rem; margin-bottom: 0.75rem; border-radius: 8px; }",
        "        .tag { display: inline-block; padding: 0.15rem 0.5rem; margin-left: 0.5rem; background: #e6f3ff; border-radius: 4px; color: #065b9e; font-size: 0.8rem; }",
        "        a { color: #065b9e; text-decoration: none; }",
        "        a:hover { text-decoration: underline; }",
        "    </style>",
        "</head>",
        "<body>",
        "    <h1>VLTA / PORTUS</h1>",
        "    <p>The public front door into the estate.</p>",
        f"    <p><em>{data.get('repo_count', 0)} live repositories admitted by explicit public policy.</em></p>",
    ]

    order = {"conductor": 0, "portal_public": 1, "governed_public": 2, "shelf_public": 3}
    for classification in sorted(grouped, key=lambda value: (order.get(value, 99), value)):
        safe_classification = html.escape(classification)
        output.append(f"    <h2>{safe_classification}</h2>")
        for repository in grouped[classification]:
            coordinate = repository["coordinate"]
            safe_coordinate = html.escape(coordinate)
            safe_url = html.escape(f"https://github.com/{coordinate}", quote=True)
            output.append("    <div class='repo-card'>")
            output.append(f"        <strong><a href='{safe_url}'>{safe_coordinate}</a></strong>")
            output.append(f"        <span class='tag'>{safe_classification}</span>")
            output.append("    </div>")

    output.extend(["</body>", "</html>"])
    return "\n".join(output)


def main() -> int:
    PORTAL_DIR.mkdir(exist_ok=True)
    estate = yaml.safe_load(ESTATE_REGISTRY.read_text(encoding="utf-8"))
    census = json.loads(CENSUS_DOC.read_text(encoding="utf-8"))
    aliases = load_repository_aliases()
    data = build_portal_data(estate, census, aliases)

    (PORTAL_DIR / "index.html").write_text(build_html(data), encoding="utf-8")
    (PORTAL_DIR / "README.md").write_text(
        f"# VLTA / PORTUS\n\nPublic portal for {data['repo_count']} live repositories admitted by explicit public policy.\n"
        "See `index.html` for the canonical public index.\n",
        encoding="utf-8",
    )
    print(
        f"Portal built at {PORTAL_DIR}: {data['repo_count']} public repositories; "
        f"{len(data['omitted_not_live'])} explicit-public coordinates omitted because they were not live public."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
