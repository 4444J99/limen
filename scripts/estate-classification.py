#!/usr/bin/env python3
"""Verify PSP-P02-W02 estate classification from live GitHub metadata.

The public policy is ``institutio/github/estate.yaml``.  It names taxonomy and
rule precedence but does not become a second public inventory.  This verifier
retrieves the current owner/org repository denominator, classifies every record
in memory, emits only aggregate counts, and guards the reviewed diff against
newly added private repository names.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
ESTATE = ROOT / "institutio/github/estate.yaml"
ACCESS = ROOT / "institutio/github/access.yaml"
TAXONOMY = {
    "infrastructure",
    "proof",
    "experiments",
    "products",
    "archives",
    "private_operations",
    "partner_work",
}
MATURITY = {"active", "maintained", "dormant", "archived", "unvalidated"}
DISPOSITIONS = {"public_evidence", "public_partner", "private_internal", "private_partner"}


class ClassificationError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ClassificationError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ClassificationError(f"{path} must be a mapping")
    return value


def load_gitvs() -> Any:
    path = ROOT / "scripts/gitvs.py"
    spec = importlib.util.spec_from_file_location("estate_classification_gitvs", path)
    if spec is None or spec.loader is None:
        raise ClassificationError("cannot load scripts/gitvs.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def command_json(args: list[str]) -> Any:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False, timeout=60)
    if result.returncode != 0:
        raise ClassificationError((result.stderr or result.stdout or "GitHub query failed").strip())
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ClassificationError("GitHub query returned invalid JSON") from exc


def paginated_repositories(endpoint: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["gh", "api", "--paginate", endpoint], cwd=ROOT, text=True, capture_output=True, check=False, timeout=180
    )
    if result.returncode != 0:
        raise ClassificationError((result.stderr or result.stdout or "GitHub repository query failed").strip())
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            page = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ClassificationError("GitHub repository page returned invalid JSON") from exc
        if not isinstance(page, list):
            raise ClassificationError("GitHub repository page was not a list")
        rows.extend(row for row in page if isinstance(row, dict))
    return rows


def collect_live_repositories() -> list[dict[str, Any]]:
    orgs = command_json(["gh", "api", "--paginate", "/user/orgs?per_page=100"])
    if not isinstance(orgs, list):
        raise ClassificationError("GitHub organization query was not a list")
    pages = [paginated_repositories("/user/repos?affiliation=owner&per_page=100")]
    for org in orgs:
        login = str((org or {}).get("login") or "").strip()
        if login:
            pages.append(paginated_repositories(f"/orgs/{login}/repos?type=all&per_page=100"))
    repositories: dict[str, dict[str, Any]] = {}
    for page in pages:
        for row in page:
            name = str(row.get("full_name") or "").strip()
            if not name:
                raise ClassificationError("repository without full_name")
            if name in repositories:
                raise ClassificationError(f"duplicate repository returned by census: {name}")
            repositories[name] = row
    return [repositories[key] for key in sorted(repositories)]


def audience_for(repo: str, private: bool, access: dict[str, Any]) -> str:
    grants = access.get("grants") or {}
    if not private:
        return "collab" if repo in grants else "world"
    return "collab" if repo in grants else "self"


def parse_timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def maturity_for(row: dict[str, Any], policy: dict[str, Any], now: dt.datetime) -> str:
    if bool(row.get("archived")):
        return "archived"
    pushed = parse_timestamp(row.get("pushed_at"))
    if pushed is None:
        return "unvalidated"
    age = (now - pushed.astimezone(dt.UTC)).days
    maturity = policy["maturity"]
    if age <= int(maturity["active_within_days"]):
        return "active"
    if age <= int(maturity["maintained_within_days"]):
        return "maintained"
    return "dormant"


def selector_matches(
    selector: dict[str, Any], *, governance_class: str, audience: str, product: bool, row: dict[str, Any]
) -> bool:
    if selector.get("fallback") is True:
        return True
    if "audience" in selector and selector["audience"] != audience:
        return False
    if "archived" in selector and bool(selector["archived"]) != bool(row.get("archived")):
        return False
    if "visibility" in selector:
        observed = "private" if bool(row.get("private")) else "public"
        if selector["visibility"] != observed:
            return False
    if "product_ledger" in selector and bool(selector["product_ledger"]) != product:
        return False
    if "governance_classes" in selector and governance_class not in set(selector["governance_classes"] or []):
        return False
    return bool(selector)


def classify(rows: list[dict[str, Any]], estate: dict[str, Any], access: dict[str, Any], now: dt.datetime) -> list[dict[str, str]]:
    policy = estate.get("positioning_estate_classification") or {}
    product_names = {str(name) for name in ((estate.get("product_ledger") or {}).get("repos") or [])}
    gitvs = load_gitvs()
    result: list[dict[str, str]] = []
    for row in rows:
        repo = str(row["full_name"])
        governance_class = gitvs.classify_repo(repo, estate, facts={
            "private": bool(row.get("private")), "archived": bool(row.get("archived")), "fork": bool(row.get("fork"))
        })
        if not governance_class:
            raise ClassificationError(f"no governance class for {repo}")
        audience = audience_for(repo, bool(row.get("private")), access)
        matches = [
            str(rule.get("class"))
            for rule in policy.get("primary_order") or []
            if isinstance(rule, dict)
            and isinstance(rule.get("when"), dict)
            and selector_matches(
                rule["when"], governance_class=governance_class, audience=audience,
                product=repo.rsplit("/", 1)[-1] in product_names, row=row
            )
        ]
        # The taxonomy deliberately has overlaps (a partner product can also be
        # private, a portal product can also be in the product ledger).  The
        # registry's ordered policy resolves those overlaps; this output stores
        # only its first matching class, therefore exactly one primary class.
        if not matches:
            raise ClassificationError(f"{repo}: no primary-class rule matched")
        primary = matches[0]
        if primary not in TAXONOMY:
            raise ClassificationError(f"{repo}: invalid primary class {primary}")
        private = bool(row.get("private"))
        if private:
            disposition = "private_partner" if audience == "collab" else "private_internal"
        else:
            disposition = "public_partner" if audience == "collab" else "public_evidence"
        maturity = maturity_for(row, policy, now)
        relevance = str((policy.get("public_relevance") or {}).get(primary) or "")
        if disposition not in DISPOSITIONS or maturity not in MATURITY or not relevance:
            raise ClassificationError(f"{repo}: incomplete classification dimensions")
        uncertainty: list[str] = []
        if primary == "experiments":
            uncertainty.append("role")
        if maturity == "unvalidated":
            uncertainty.append("maturity")
        if disposition == "public_partner":
            uncertainty.append("public_relevance")
        result.append({
            "primary_class": primary,
            "maturity": maturity,
            "visibility_disposition": disposition,
            "public_relevance": relevance,
            "governance_class": governance_class,
            "uncertainty": uncertainty,
        })
    return result


def verify_policy(estate: dict[str, Any]) -> list[str]:
    policy = estate.get("positioning_estate_classification")
    if not isinstance(policy, dict):
        return ["missing positioning_estate_classification policy"]
    errors: list[str] = []
    if set(policy.get("primary_classes") or []) != TAXONOMY:
        errors.append("primary_classes must contain the seven PSP-P02-W02 classes exactly")
    rules = policy.get("primary_order") or []
    if not isinstance(rules, list) or len(rules) != len(TAXONOMY):
        errors.append("primary_order must contain one rule per primary class")
    elif {str(rule.get("class")) for rule in rules if isinstance(rule, dict)} != TAXONOMY:
        errors.append("primary_order must name each primary class exactly once")
    if set((policy.get("maturity") or {}).get("values") or []) != MATURITY:
        errors.append("maturity.values must contain the allowed maturity values exactly")
    if set(policy.get("visibility_dispositions") or []) != DISPOSITIONS:
        errors.append("visibility_dispositions must contain the allowed dispositions exactly")
    if set((policy.get("public_relevance") or {})) != TAXONOMY:
        errors.append("public_relevance must map each primary class")
    return errors


def private_leaks_added(base: str, private_names: set[str]) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--unified=0", f"{base}...HEAD"],
        cwd=ROOT, text=True, capture_output=True, check=False, timeout=60,
    )
    if result.returncode != 0:
        raise ClassificationError(f"cannot inspect reviewed diff against {base}")
    added = [line[1:] for line in result.stdout.splitlines() if line.startswith("+") and not line.startswith("+++")]
    return sorted(name for name in private_names if any(name in line for line in added))


def summary(rows: list[dict[str, Any]], classifications: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "repository_count": len(rows),
        "visibility": dict(sorted(collections.Counter("private" if bool(row.get("private")) else "public" for row in rows).items())),
        "primary_classes": dict(sorted(collections.Counter(row["primary_class"] for row in classifications).items())),
        "maturity": dict(sorted(collections.Counter(row["maturity"] for row in classifications).items())),
        "visibility_dispositions": dict(sorted(collections.Counter(row["visibility_disposition"] for row in classifications).items())),
        "public_relevance": dict(sorted(collections.Counter(row["public_relevance"] for row in classifications).items())),
        "uncertainty_queue": dict(
            sorted(collections.Counter(kind for row in classifications for kind in row["uncertainty"]).items())
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="fail unless policy, live coverage, and private-diff guard pass")
    parser.add_argument("--json", action="store_true", help="print public-safe aggregate counts")
    parser.add_argument("--base", default="HEAD", help="review base used by the new-private-name diff guard")
    args = parser.parse_args()
    try:
        estate = load_yaml(ESTATE)
        access = load_yaml(ACCESS)
        errors = verify_policy(estate)
        if errors:
            raise ClassificationError("; ".join(errors))
        rows = collect_live_repositories()
        classifications = classify(rows, estate, access, dt.datetime.now(dt.UTC))
        expected = (estate["positioning_estate_classification"].get("expected_denominator") or {})
        counts = summary(rows, classifications)
        if counts["repository_count"] != expected.get("repositories"):
            raise ClassificationError(f"census denominator mismatch: {counts['repository_count']} != {expected.get('repositories')}")
        if counts["visibility"] != {"private": expected.get("private"), "public": expected.get("public")}:
            raise ClassificationError("census visibility counts do not match the W01 receipt")
        leaks = private_leaks_added(args.base, {str(row["full_name"]) for row in rows if bool(row.get("private"))})
        if leaks:
            raise ClassificationError(f"new private repository name(s) in public diff: {len(leaks)}")
        if args.json:
            print(json.dumps(counts, indent=2, sort_keys=True))
        else:
            print(f"estate-classification: {counts['repository_count']} repositories, exactly one primary class each")
            print(f"estate-classification: uncertainty queue={sum(counts['uncertainty_queue'].values())}")
        return 0
    except ClassificationError as exc:
        print(f"estate-classification: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
