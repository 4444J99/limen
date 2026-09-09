"""Dependency review routing for the existing drain; never merge authority.

No candidate code runs here. The audited evidence consumer owns classification;
the only optional effect is requesting the configured independent bot reviewer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from _dependency_acceptance import PILOT_REPOSITORIES, inspect_candidate


def pilot(repo):
    return repo.casefold() in {name.casefold() for name in PILOT_REPOSITORIES} | {"4444j99/portfolio"}


def lifecycle_hold(pr):
    labels = {item.get("name", "").strip().casefold() for item in pr.get("labels", [])}
    return any(
        name in labels
        for name in ("lifecycle:active-human", "lifecycle:preservation", "lifecycle:blocked", "lifecycle:superseded")
    )


def inspect(repo, number, head, gh):
    if not pilot(repo):
        return {"route": "not-dependency"}
    try:
        policy = Path(__file__).resolve().parents[1] / "institutio/github/dependency-trust.json"
        return inspect_candidate(repo, number, head, gh, trust_policy_path=policy)
    except Exception:  # noqa: BLE001 - redact the credential/provider boundary
        # API bodies and subprocess diagnostics are untrusted/private material.
        return {"route": "exception", "reasons": ["evidence-unavailable"], "head_sha": head}


def request_review(repo, number, head, gh):
    """One review request after a fresh evidence read; never an approval or merge.

    GitHub's requested-reviewer state and completed exact-head reviews provide
    idempotency across process restarts. A failed/ambiguous request is returned
    as an exception; the next heartbeat reads state before making any request.
    """
    if not pilot(repo) or type(number) is not int or number <= 0:
        return "exception", ["invalid-review-scope"]
    if repo.casefold() == "4444j99/portfolio":
        repo = "organvm-vii-kerygma/portfolio"
    repo = next(name for name in PILOT_REPOSITORIES if name.casefold() == repo.casefold())
    prefix = f"repos/{repo}/pulls/{number}"

    def read(path):
        response = gh(["api", path], timeout=40)
        if response.returncode != 0:
            raise ValueError("review-read-unavailable")
        return json.loads(response.stdout)

    try:
        evidence = inspect(repo, number, head, gh)
        if evidence.get("route") != "delegated-review":
            return "exception", evidence.get("reasons", ["evidence-not-ready"])
        reviewer = evidence.get("reviewer") or {}
        login, identity = reviewer.get("login"), reviewer.get("id")
        if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9_-]+(?:\[bot\])?", login):
            return "exception", ["reviewer-unconfigured"]
        if type(identity) is not int or identity <= 0:
            return "exception", ["reviewer-unconfigured"]
        user = read(f"users/{login}")
        if (
            user.get("id") != identity
            or user.get("type") != "Bot"
            or user.get("login", "").casefold() != login.casefold()
        ):
            return "exception", ["reviewer-identity-mismatch"]
        pr = read(prefix)
        if lifecycle_hold(pr):
            return "exception", ["review-lifecycle-hold"]
        if (
            pr.get("state") != "open"
            or pr.get("draft") is not False
            or pr.get("head", {}).get("sha") != head
            or pr.get("user", {}).get("id") == identity
        ):
            return "exception", ["review-candidate-changed"]
        # Bounded pagination fails closed instead of silently missing a review.
        matching_reviews = []
        for page in range(1, 11):
            reviews = read(f"{prefix}/reviews?per_page=100&page={page}")
            if not isinstance(reviews, list):
                raise TypeError("invalid-review-readback")
            matching_reviews.extend(
                review
                for review in reviews
                if review.get("user", {}).get("id") == identity
                and review.get("commit_id") == head
                and review.get("state") in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}
            )
            if len(reviews) < 100:
                break
        else:
            return "exception", ["review-pagination-incomplete"]
        if matching_reviews:
            decisive = [review for review in matching_reviews if review["state"] in {"APPROVED", "CHANGES_REQUESTED"}]
            if decisive and decisive[-1]["state"] == "CHANGES_REQUESTED":
                return "exception", ["review-changes-requested"]
            return "reviewed", []
        if any(item.get("id") == identity for item in pr.get("requested_reviewers", [])):
            return "already-requested", []
        # A batch assessment cannot authorize a later request after a rerun,
        # policy promotion, head change or base movement.
        fresh = inspect(repo, number, head, gh)
        if fresh != evidence:
            return "exception", ["review-evidence-changed"]
        current = read(prefix)
        if (
            lifecycle_hold(current)
            or current.get("head", {}).get("sha") != head
            or current.get("state") != "open"
            or current.get("draft") is not False
        ):
            return "exception", ["review-candidate-changed"]
        result = gh(
            ["api", prefix + "/requested_reviewers", "--method", "POST", "-f", f"reviewers[]={login}"], timeout=40
        )
        if result.returncode != 0:
            return "exception", ["review-request-unconfirmed"]
        confirmed = read(prefix)
        if confirmed.get("head", {}).get("sha") != head or lifecycle_hold(confirmed):
            return "exception", ["review-candidate-changed"]
        if not any(item.get("id") == identity for item in confirmed.get("requested_reviewers", [])):
            return "exception", ["review-request-unconfirmed"]
        return "requested", []
    except Exception:  # noqa: BLE001 - redact the credential/provider boundary
        return "exception", ["review-transport-unavailable"]


def main():
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()

    def gh(arguments, timeout=60, binary=False):
        return subprocess.run(["gh", *arguments], capture_output=True, text=not binary, timeout=timeout, check=False)

    result = inspect(args.repo, args.pr, args.expected_head, gh)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("route") == "not-dependency" else 2


if __name__ == "__main__":
    raise SystemExit(main())
