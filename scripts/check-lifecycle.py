#!/usr/bin/env python3
"""PR lifecycle registry drift predicate.

Offline checks hold the declaration/consumer boundary:

A  lifecycle.yaml dispositions exactly match estate.yaml's legacy vocabulary while that ratchet is open.
B  every declared consumer's lifecycle literals equal its shrink-only baseline, or reach zero once converted.
C  an armed consumer ratchet contains no disposition-id literal; it derives by capability.
E  every cohort has a declared default disposition or a resolving human lever.
G  the registry's predicate and ideal-form self-references resolve.

`--measure` additionally reports the unreachable PR count from the committed exhaustive census. It is
kept outside the offline gate because live GitHub reach is environment evidence, not a repo invariant.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "lifecycle.yaml"
ESTATE = ROOT / "institutio" / "github" / "estate.yaml"
IDEALS = ROOT / "institutio" / "governance" / "ideal-forms.yaml"
LEVERS = ROOT / "his-hand-levers.json"
PR_LEDGER = ROOT / "docs" / "github-pr-debt-ledger.json"
PR_DEBT_FACTS = ROOT / "logs" / "gitvs-pr-debt-facts.json"
ESTATE_CENSUS_FACTS = ROOT / "logs" / "github-estate-census-facts.json"
SELF_COMMAND = "python3 scripts/check-lifecycle.py --check"
TERMINAL_LEVER_STATES = frozenset({"discharged", "retired", "done", "closed"})
ADMISSION_CONTRACT = {
    "draft": False,
    "mergeable": True,
    "required_checks": "green",
    "conflicts": "none",
}
INITIAL_LITERAL_CEILING = {
    "scripts/merge-drain.py": 6,
    "scripts/pr-lifecycle-manifest.py": 5,
    "scripts/pr-lifecycle-estate-manifest.py": 6,
    "scripts/gitvs.py": 8,
}

failures: list[str] = []


def fail(check: str, message: str) -> None:
    failures.append(f"  ✗ [{check}] {message}")


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        fail("A", f"{path.relative_to(ROOT)} is unreadable: {exc}")
        return {}
    if not isinstance(payload, dict):
        fail("A", f"{path.relative_to(ROOT)} must contain a mapping")
        return {}
    return payload


def load_levers() -> dict[str, str]:
    try:
        payload = json.loads(LEVERS.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        fail("E", f"{LEVERS.relative_to(ROOT)} is unreadable: {exc}")
        return {}
    rows = payload.get("levers") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        fail("E", "his-hand-levers.json has no levers list")
        return {}
    return {
        str(row["id"]): str(row.get("status") or "")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }


def legacy_estate_policy() -> dict[str, Any]:
    estate = load_yaml(ESTATE)
    policy = estate.get("pr_debt_policy") if isinstance(estate, dict) else None
    if not isinstance(policy, dict):
        fail("A", "estate.yaml has no pr_debt_policy mapping")
        return {}
    return policy


def legacy_estate_labels(policy: dict[str, Any]) -> set[str]:
    labels = policy.get("lifecycle_labels")
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        fail("A", "estate.yaml pr_debt_policy.lifecycle_labels must be a string list")
        return set()
    return set(labels)


def validate_dispositions(registry: dict[str, Any]) -> set[str]:
    rows = registry.get("dispositions")
    if not isinstance(rows, dict) or not rows:
        fail("A", "registry has no dispositions mapping")
        return set()
    required = {
        "label_color",
        "description",
        "merge_eligible",
        "fail_closed",
        "human_owned",
        "terminal",
        "owner",
    }
    merge_eligible: list[str] = []
    for disposition, row in rows.items():
        if not isinstance(disposition, str) or not disposition.startswith("lifecycle:"):
            fail("A", f"{disposition!r}: disposition id must start with lifecycle:")
            continue
        if not isinstance(row, dict):
            fail("A", f"{disposition}: row must be a mapping")
            continue
        missing = sorted(required - set(row))
        if missing:
            fail("A", f"{disposition}: missing fields {missing}")
        if re.fullmatch(r"[0-9a-f]{6}", str(row.get("label_color") or "")) is None:
            fail("A", f"{disposition}: label_color must be a lowercase six-digit hex color")
        for capability in ("merge_eligible", "fail_closed", "human_owned", "terminal"):
            if not isinstance(row.get(capability), bool):
                fail("A", f"{disposition}: {capability} must be boolean")
        if row.get("merge_eligible") is True:
            merge_eligible.append(disposition)
    if len(merge_eligible) != 1:
        fail("A", f"exactly one disposition must be merge_eligible; found {merge_eligible}")
    elif rows[merge_eligible[0]].get("admits") != ADMISSION_CONTRACT:
        fail(
            "A",
            f"{merge_eligible[0]}: admits must equal the typed merge admission contract",
        )

    preservation = rows.get("lifecycle:preservation")
    derived_from = preservation.get("derived_from") if isinstance(preservation, dict) else None
    if not isinstance(derived_from, dict):
        fail("A", "lifecycle:preservation must declare a derived_from mapping")
    else:
        required_derivation = {"labels", "body_markers", "materialize"}
        missing_derivation = sorted(required_derivation - set(derived_from))
        if missing_derivation:
            fail(
                "A",
                "lifecycle:preservation.derived_from is missing fields "
                f"{missing_derivation}",
            )
        for field in ("labels", "body_markers"):
            value = derived_from.get(field)
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(item, str) and item for item in value)
            ):
                fail(
                    "A",
                    f"lifecycle:preservation.derived_from.{field} must be a non-empty string list",
                )
        if derived_from.get("materialize") is not True:
            fail("A", "lifecycle:preservation.derived_from.materialize must be true")
    return {str(key) for key in rows}


def previous_registry() -> dict[str, Any] | None:
    """Read the prior exact registry so monotonic migration state cannot regress."""
    relative = REGISTRY.relative_to(ROOT).as_posix()
    for revision in ("HEAD^1", "HEAD^"):
        result = subprocess.run(
            ["git", "show", f"{revision}:{relative}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            continue
        try:
            payload = yaml.safe_load(result.stdout) or {}
        except yaml.YAMLError:
            return None
        return payload if isinstance(payload, dict) else None
    return None


def validate_ratchet_monotonicity(
    ratchets: dict[str, Any],
    prior_registry: dict[str, Any] | None,
) -> None:
    """Reject every true-to-false or true-to-missing migration reversal."""
    prior_ratchets = prior_registry.get("ratchets") if isinstance(prior_registry, dict) else None
    if not isinstance(prior_ratchets, dict):
        return
    reversed_ratchets = sorted(
        str(name)
        for name, armed in prior_ratchets.items()
        if armed is True and ratchets.get(name) is not True
    )
    if reversed_ratchets:
        fail("C", f"armed ratchets cannot be reversed: {reversed_ratchets}")


def _source_markers(source: str) -> tuple[set[str], set[str]]:
    """Collect executable marker names and lifecycle ids, excluding comments/docstrings."""
    tree = ast.parse(source)
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_nodes.add(id(first.value))

    markers: set[str] = set()
    lifecycle_literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_nodes:
                continue
            markers.add(node.value)
            lifecycle_literals.update(
                re.findall(r"(?<![\w-])lifecycle:[A-Za-z0-9_-]+", node.value)
            )
        elif isinstance(node, ast.Name):
            markers.add(node.id)
        elif isinstance(node, ast.Attribute):
            markers.add(node.attr)
    return markers, lifecycle_literals


def validate_consumers(registry: dict[str, Any], labels: set[str]) -> None:
    consumers = registry.get("consumers")
    ratchets = registry.get("ratchets")
    baseline = registry.get("literal_baseline")
    if not isinstance(consumers, dict) or not consumers:
        fail("B", "registry has no consumers mapping")
        return
    if not isinstance(ratchets, dict):
        fail("B", "registry has no ratchets mapping")
        ratchets = {}
    if not isinstance(baseline, dict):
        fail("B", "registry has no literal_baseline mapping")
        baseline = {}

    consumer_paths: set[str] = set()
    for consumer, row in consumers.items():
        if not isinstance(row, dict):
            fail("B", f"{consumer}: consumer row must be a mapping")
            continue
        relative = str(row.get("path") or "")
        ratchet = str(row.get("ratchet") or "")
        derives = row.get("derives")
        loader_markers = row.get("loader_markers")
        if not relative or not (ROOT / relative).is_file():
            fail("B", f"{consumer}: consumer path does not resolve: {relative!r}")
            continue
        consumer_paths.add(relative)
        if not isinstance(derives, list) or not derives or not all(isinstance(item, str) for item in derives):
            fail("B", f"{consumer}: derives must be a non-empty string list")
        if (
            not isinstance(loader_markers, list)
            or not loader_markers
            or not all(isinstance(item, str) and item for item in loader_markers)
        ):
            fail("C", f"{consumer}: loader_markers must declare observable registry derivation")
            loader_markers = []
        if ratchet not in ratchets or not isinstance(ratchets.get(ratchet), bool):
            fail("B", f"{consumer}: ratchet {ratchet!r} is missing or non-boolean")
            continue
        try:
            expected = int(baseline[relative])
        except (KeyError, TypeError, ValueError):
            fail("B", f"{consumer}: literal baseline is missing for {relative}")
            continue
        try:
            text = (ROOT / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            fail("B", f"{consumer}: consumer source is unreadable: {exc}")
            continue
        try:
            structural_markers, lifecycle_literals = _source_markers(text)
        except SyntaxError as exc:
            fail("C", f"{consumer}: consumer source is not parseable for derivation checks: {exc}")
            continue
        undeclared_literals = sorted(lifecycle_literals - labels)
        if undeclared_literals:
            fail(
                "C",
                f"{consumer}: undeclared lifecycle literal(s): {undeclared_literals}",
            )
        actual = sum(text.count(label) for label in labels)
        armed = bool(ratchets[ratchet])
        if armed and any(marker not in structural_markers for marker in loader_markers):
            missing_markers = [
                marker for marker in loader_markers if marker not in structural_markers
            ]
            fail("C", f"{consumer}: armed derivation markers missing: {missing_markers}")
        if armed and actual:
            fail("C", f"{consumer}: conversion ratchet is armed but {actual} disposition literal(s) remain")
        elif armed and expected != 0:
            fail("B", f"{consumer}: converted consumer must lower its literal baseline to 0 (found {expected})")
        elif not armed and actual != expected:
            direction = "grew" if actual > expected else "shrunk"
            fail("B", f"{consumer}: literal debt {direction} from baseline {expected} to {actual}; update the conversion receipt")

    missing_consumers = set(INITIAL_LITERAL_CEILING) - consumer_paths
    if missing_consumers:
        fail("B", f"canonical lifecycle consumers are undeclared: {sorted(missing_consumers)}")

    extra_baselines = set(str(key) for key in baseline) - consumer_paths
    if extra_baselines:
        fail("B", f"literal baselines name undeclared consumers: {sorted(extra_baselines)}")

    prior_registry = previous_registry()
    previous_baseline = prior_registry.get("literal_baseline") if isinstance(prior_registry, dict) else None
    ceiling = previous_baseline if isinstance(previous_baseline, dict) else INITIAL_LITERAL_CEILING
    for relative, value in baseline.items():
        try:
            current = int(value)
        except (TypeError, ValueError):
            fail("B", f"{relative}: literal baseline is not an integer")
            continue
        if relative not in ceiling:
            if current != 0:
                fail(
                    "B",
                    f"{relative}: new consumer requires an explicit zero literal baseline",
                )
            continue
        try:
            maximum = int(ceiling[relative])
        except (TypeError, ValueError):
            fail("B", f"{relative}: prior literal ceiling is not an integer")
            continue
        if current > maximum:
            fail("B", f"{relative}: literal baseline regrew from {maximum} to {current}")
    validate_ratchet_monotonicity(ratchets, prior_registry)


def validate_cohorts(registry: dict[str, Any], labels: set[str]) -> None:
    cohorts = registry.get("cohorts")
    if not isinstance(cohorts, dict) or not cohorts:
        fail("E", "registry has no cohorts mapping")
        return
    levers = load_levers()
    precedence = registry.get("cohort_precedence")
    if not isinstance(precedence, list) or set(precedence) != set(cohorts):
        fail("E", "cohort_precedence must name every cohort exactly once")
        precedence = []
    elif precedence[0] != "draft" or precedence[-1] != "all":
        fail("E", "cohort_precedence must evaluate draft first and all last")
    elif precedence.index("archived-repo") > precedence.index("dependabot"):
        fail("E", "archived-repo must precede the actionable dependabot cohort")
    for cohort, row in cohorts.items():
        if not isinstance(row, dict):
            fail("E", f"{cohort}: cohort row must be a mapping")
            continue
        selector = row.get("selector")
        if not isinstance(selector, dict) or not selector:
            fail("E", f"{cohort}: selector must be a non-empty mapping")
            selector = {}
        supported_selector_keys = {
            "all",
            "classification",
            "draft",
            "owner",
            "private",
            "repository_archived",
        }
        unknown_selector_keys = set(selector) - supported_selector_keys
        if unknown_selector_keys:
            fail("E", f"{cohort}: selector has unsupported key(s) {sorted(unknown_selector_keys)}")
        for key in ("all", "draft", "private", "repository_archived"):
            if key in selector and not isinstance(selector[key], bool):
                fail("E", f"{cohort}: selector.{key} must be boolean")
        for key in ("owner", "classification"):
            if key in selector and not isinstance(selector[key], str):
                fail("E", f"{cohort}: selector.{key} must be a string")
        if cohort == "draft" and selector != {"draft": True}:
            fail("E", "draft cohort selector must be exactly {draft: true}")
        if cohort == "all" and selector != {"all": True}:
            fail("E", "all cohort selector must be exactly {all: true}")
        disposition = row.get("default_disposition")
        lever = row.get("owner_lever")
        armed_disposition = row.get("armed_disposition")
        if disposition is None and not lever:
            fail("E", f"{cohort}: requires default_disposition or owner_lever")
        if disposition is not None and disposition not in labels:
            fail("E", f"{cohort}: unknown default_disposition {disposition!r}")
        if lever and lever not in levers:
            fail("E", f"{cohort}: owner_lever {lever!r} does not resolve")
        if armed_disposition is not None and (not lever or armed_disposition not in labels):
            fail("E", f"{cohort}: armed_disposition requires a resolving lever and known disposition")
        if disposition is None and lever and levers.get(str(lever)) in TERMINAL_LEVER_STATES:
            fail(
                "E",
                f"{cohort}: terminal owner_lever {lever!r} cannot replace a default disposition",
            )


def validate_self_reference(registry: dict[str, Any]) -> None:
    if registry.get("predicate") != SELF_COMMAND:
        fail("G", f"predicate must be exactly {SELF_COMMAND!r}")
    if registry.get("ideal_form") != "IF-PR-LIFECYCLE":
        fail("G", "ideal_form must be IF-PR-LIFECYCLE")
    ideals = load_yaml(IDEALS).get("ideals") or {}
    ideal = ideals.get("IF-PR-LIFECYCLE") if isinstance(ideals, dict) else None
    if not isinstance(ideal, dict):
        fail("G", "IF-PR-LIFECYCLE does not resolve in ideal-forms.yaml")
    else:
        probe = ideal.get("probe")
        if not isinstance(probe, dict):
            fail("G", "IF-PR-LIFECYCLE must declare a measurement probe")
        else:
            expected_probe = {
                "command": "python3 scripts/check-lifecycle.py --measure",
                "environment": "network",
                "extract": "unreachable PRs: ([0-9]+)",
                "ideal_value": 0,
            }
            for field, expected in expected_probe.items():
                if probe.get(field) != expected:
                    fail(
                        "G",
                        f"IF-PR-LIFECYCLE probe.{field} must equal {expected!r}",
                    )
            if not isinstance(probe.get("derives"), str) or not probe["derives"].strip():
                fail("G", "IF-PR-LIFECYCLE probe.derives must be a non-empty string")
    if not Path(__file__).is_file():
        fail("G", "predicate script does not resolve")


def run_offline_checks() -> tuple[dict[str, Any], set[str]]:
    registry = load_yaml(REGISTRY)
    if registry.get("schema_version") != 0.1:
        fail("A", "schema_version must be 0.1")
    labels = validate_dispositions(registry)
    estate_policy = legacy_estate_policy()
    ratchets = registry.get("ratchets") or {}
    estate_derives = ratchets.get("estate_yaml_derives")
    if not isinstance(estate_derives, bool):
        fail("A", "ratchets.estate_yaml_derives must be boolean")
    elif not estate_derives:
        estate_labels = legacy_estate_labels(estate_policy)
        if labels != estate_labels:
            fail("A", f"registry/estate disposition mismatch: registry={sorted(labels)} estate={sorted(estate_labels)}")
    elif estate_derives:
        if "lifecycle_labels" in estate_policy:
            fail("A", "converted estate.yaml must not retain lifecycle_labels")
        if estate_policy.get("lifecycle_registry") != "../governance/lifecycle.yaml":
            fail("A", "converted estate.yaml must point to ../governance/lifecycle.yaml")
    validate_consumers(registry, labels)
    validate_cohorts(registry, labels)
    validate_self_reference(registry)
    return registry, labels


def live_label_metadata_drift(
    repositories: set[str],
    dispositions: dict[str, Any],
) -> int | None:
    """Read lifecycle label color/description from GitHub in bounded GraphQL batches."""

    valid_repositories = sorted(
        repository
        for repository in repositories
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
    )
    drift = 0
    for offset in range(0, len(valid_repositories), 40):
        batch = valid_repositories[offset : offset + 40]
        fields = []
        aliases: dict[str, str] = {}
        for index, repository in enumerate(batch):
            owner, name = repository.split("/", 1)
            alias = f"r{index}"
            aliases[alias] = repository
            fields.append(
                f"{alias}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) "
                '{ labels(first: 100, query: "lifecycle:") { nodes { name color description } } }'
            )
        query = "query { " + " ".join(fields) + " }"
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={query}"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            payload = json.loads(result.stdout) if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            fail("D", f"live lifecycle-label query failed: {type(exc).__name__}")
            return None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            fail("D", "live lifecycle-label query returned no data")
            return None
        for alias, repository in aliases.items():
            repo_payload = data.get(alias)
            if not isinstance(repo_payload, dict):
                fail("D", f"live lifecycle-label query could not resolve {repository}")
                return None
            labels_payload = repo_payload.get("labels")
            nodes = labels_payload.get("nodes") if isinstance(labels_payload, dict) else None
            if not isinstance(nodes, list):
                fail("D", f"live lifecycle-label query returned no labels for {repository}")
                return None
            actual = {
                row.get("name"): row
                for row in nodes
                if isinstance(row, dict) and isinstance(row.get("name"), str)
            }
            drift += len(set(actual) - set(dispositions))
            for label, expected in dispositions.items():
                row = actual.get(label)
                if not isinstance(row, dict):
                    drift += 1
                    continue
                if str(row.get("color") or "").lower() != str(expected.get("label_color") or "").lower():
                    drift += 1
                    continue
                if str(row.get("description") or "") != str(expected.get("description") or ""):
                    drift += 1
    return drift



def _census_identity(row: dict[str, Any]) -> str | None:
    key = row.get("pr_key")
    if isinstance(key, str) and key:
        return key
    repository = row.get("repository")
    number = row.get("number")
    if (
        not isinstance(repository, str)
        or not repository
        or isinstance(number, bool)
        or not isinstance(number, int)
    ):
        return None
    return hashlib.sha256(f"{repository}#{number}".encode()).hexdigest()


def _complete_census_rows(
    ledger: dict[str, Any],
    *,
    facts_path: Path = PR_DEBT_FACTS,
) -> list[dict[str, Any]] | None:
    """Resolve redacted private rows from the matching gitignored runtime facts."""
    rows = ledger.get("pull_requests")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        fail("D", "PR-debt ledger has no pull_requests census")
        return None
    redacted_private = [
        row
        for row in rows
        if row.get("private") is True
        and (
            not isinstance(row.get("repository"), str)
            or isinstance(row.get("number"), bool)
            or not isinstance(row.get("number"), int)
        )
    ]
    if not redacted_private:
        return rows
    try:
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        fail(
            "D",
            "private PR cohort is redacted and therefore unmeasurable without "
            f"the matching {facts_path.name} runtime census: {exc}",
        )
        return None
    facts_rows = facts.get("pull_requests") if isinstance(facts, dict) else None
    ledger_keys = {_census_identity(row) for row in rows}
    facts_keys = {_census_identity(row) for row in facts_rows if isinstance(row, dict)} if isinstance(facts_rows, list) else set()
    if (
        not isinstance(facts, dict)
        or not facts.get("exhaustive")
        or facts.get("generated_at") != ledger.get("generated_at")
        or facts.get("open_pr_count") != ledger.get("open_pr_count")
        or not isinstance(facts_rows, list)
        or not all(isinstance(row, dict) for row in facts_rows)
        or len(facts_rows) != len(rows)
        or None in ledger_keys
        or None in facts_keys
        or facts_keys != ledger_keys
    ):
        fail("D", "private PR runtime census does not match the tracked exhaustive ledger")
        return None
    unresolved = [
        row
        for row in facts_rows
        if not isinstance(row.get("repository"), str)
        or isinstance(row.get("number"), bool)
        or not isinstance(row.get("number"), int)
    ]
    if unresolved:
        fail("D", f"private PR runtime census retains {len(unresolved)} unresolved coordinate row(s)")
        return None
    return facts_rows


def _complete_estate_repositories(
    *,
    facts_path: Path = ESTATE_CENSUS_FACTS,
) -> set[str] | None:
    """Load the exhaustive per-repository census; never infer the estate from open PR rows."""
    try:
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        fail(
            "D",
            "complete estate repository census is unavailable; refusing a partial "
            f"label measurement: {exc}",
        )
        return None
    if not isinstance(facts, dict):
        fail("D", "complete estate repository census must contain a mapping")
        return None
    report = facts.get("source_report")
    summary = facts.get("summary")
    cursors = facts.get("cursors")
    if (
        not isinstance(report, dict)
        or report.get("exhaustive") is not True
        or not isinstance(summary, dict)
        or not isinstance(cursors, list)
    ):
        fail("D", "complete estate repository census is not exhaustive")
        return None
    expected = summary.get("repository_count")
    if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 0:
        fail("D", "complete estate repository census has no positive repository_count")
        return None
    expected_kinds = {"pull_requests", "issues", "branches", "checks"}
    identities: set[tuple[str, str]] = set()
    repositories: set[str] = set()
    for row in cursors:
        if not isinstance(row, dict):
            fail("D", "complete estate repository census contains a malformed cursor row")
            return None
        repository = row.get("repository")
        kind = row.get("kind")
        if (
            not isinstance(repository, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or kind not in expected_kinds
            or row.get("exhaustive") is not True
            or row.get("error") not in (None, "")
        ):
            fail("D", "complete estate repository census contains an incomplete cursor row")
            return None
        repositories.add(repository)
        identities.add((repository, kind))
    if len(repositories) != expected or len(identities) != expected * len(expected_kinds):
        fail(
            "D",
            "complete estate repository census repository/connection totals do not reconcile",
        )
        return None
    return repositories


def _admission_evidence_is_green(
    row: dict[str, Any],
    disposition: dict[str, Any],
) -> bool:
    """Require the typed admission proof before a delivery label counts as reachable."""
    if disposition.get("merge_eligible") is not True:
        return False
    admission = row.get("admission")
    if not isinstance(admission, dict):
        return False
    return (
        admission.get("draft") is False
        and admission.get("mergeable") is True
        and admission.get("required_checks") == "green"
        and admission.get("conflicts") == "none"
        and row.get("lifecycle_disposition_source") == "label"
        and row.get("lifecycle_label_matches") == [row.get("lifecycle_disposition")]
    )


def mechanically_unreachable_count(
    rows: list[dict[str, Any]],
    dispositions: dict[str, Any],
) -> int:
    """Count PRs whose current typed state cannot reach merge admission."""
    unreachable = 0
    for row in rows:
        disposition = dispositions.get(row.get("lifecycle_disposition"))
        if (
            not isinstance(disposition, dict)
            or row.get("lifecycle_disposition_source") != "label"
            or disposition.get("merge_eligible") is not True
        ):
            unreachable += 1
            continue
        if not _admission_evidence_is_green(row, disposition):
            unreachable += 1
    return unreachable


def measure_unreachable(
    registry: dict[str, Any],
    *,
    metadata_probe=live_label_metadata_drift,
    rows_probe=_complete_census_rows,
    repositories_probe=None,
) -> int | None:
    try:
        ledger = json.loads(PR_LEDGER.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        fail("D", f"{PR_LEDGER.relative_to(ROOT)} is unreadable: {exc}")
        return None
    if not isinstance(ledger, dict) or not ledger.get("exhaustive"):
        fail("D", "PR-debt ledger is not an exhaustive census")
        return None
    rows = rows_probe(ledger)
    if rows is None:
        return None
    open_pr_count = ledger.get("open_pr_count")
    if isinstance(open_pr_count, bool) or not isinstance(open_pr_count, int) or open_pr_count != len(rows):
        fail("D", "PR-debt census row count does not match open_pr_count")
        return None
    dispositions = registry.get("dispositions")
    if not isinstance(dispositions, dict):
        fail("D", "registry has no dispositions mapping")
        return None

    mechanically_unreachable = mechanically_unreachable_count(rows, dispositions)

    materialization_missing = sum(
        1
        for row in rows
        if row.get("lifecycle_disposition") in dispositions
        and row.get("lifecycle_disposition_source") != "label"
    )
    preservation_missing = sum(
        1
        for row in rows
        if row.get("lifecycle_disposition") == "lifecycle:preservation"
        and row.get("lifecycle_disposition_source") != "label"
    )
    live_baseline = registry.get("live_baseline")
    preservation_ceiling = (
        live_baseline.get("preservation_materialization_missing_labels")
        if isinstance(live_baseline, dict)
        else None
    )
    if isinstance(preservation_ceiling, bool) or not isinstance(preservation_ceiling, int):
        fail("D", "live_baseline has no preservation materialization ceiling")
        return None
    prior_registry = previous_registry()
    prior_live = prior_registry.get("live_baseline") if isinstance(prior_registry, dict) else None
    prior_ceiling = (
        prior_live.get("preservation_materialization_missing_labels")
        if isinstance(prior_live, dict)
        else INITIAL_LITERAL_CEILING.get("preservation_materialization_missing_labels", 124)
    )
    if isinstance(prior_ceiling, bool) or not isinstance(prior_ceiling, int):
        fail("D", "prior registry has no preservation materialization ceiling")
        return None
    if preservation_ceiling > prior_ceiling:
        fail(
            "D",
            "preservation materialization ceiling regrew "
            f"from prior {prior_ceiling} to {preservation_ceiling}",
        )
    if preservation_missing > preservation_ceiling:
        fail(
            "D",
            "preservation materialization debt regrew "
            f"from {preservation_ceiling} to {preservation_missing}",
        )
    repositories = (
        _complete_estate_repositories()
        if repositories_probe is None
        else repositories_probe(ledger, rows)
    )
    if repositories is None:
        return None
    metadata_drift = metadata_probe(repositories, dispositions)
    if metadata_drift is None:
        return None

    literal_baseline = registry.get("literal_baseline")
    if not isinstance(literal_baseline, dict):
        fail("D", "registry has no literal_baseline mapping")
        return None
    try:
        literal_debt = sum(int(value) for value in literal_baseline.values())
    except (TypeError, ValueError):
        fail("D", "registry literal_baseline contains a non-integer value")
        return None
    ratchets = registry.get("ratchets")
    if not isinstance(ratchets, dict):
        fail("D", "registry has no ratchets mapping")
        return None
    unarmed_ratchets = sum(value is False for value in ratchets.values())
    return mechanically_unreachable + literal_debt + unarmed_ratchets + metadata_drift
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run offline registry parity checks")
    parser.add_argument("--measure", action="store_true", help="also print committed-census lifecycle distance")
    args = parser.parse_args()
    if not (args.check or args.measure):
        parser.error("one of --check or --measure is required")
    registry, _labels = run_offline_checks()
    unreachable = measure_unreachable(registry) if args.measure else None

    if failures:
        print("PR LIFECYCLE DRIFT — registry does not match its owners:")
        print("\n".join(failures))
        return 1
    literal_total = sum(int(value) for value in (registry.get("literal_baseline") or {}).values())
    print(f"OK: check-lifecycle — 5 dispositions; 7 owned cohorts; literal debt={literal_total}")
    if unreachable is not None:
        print(f"unreachable PRs: {unreachable}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
