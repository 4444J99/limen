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
        if evidence.get("route") == "pending":
            return "pending", []
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
        if fresh.get("route") == "pending":
            return "pending", []
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


def inspect_completion(repo, run_id, gh):
    """Resolve a completed-run hint through authenticated reads; no effects.

    Repeated hints deliberately re-read current evidence. This adapter issues no
    review request, lease or merge, so replay cannot duplicate an external effect.
    The existing trust consumer retains policy and artifact authority.
    """
    failure = {"route": "exception", "reasons": ["completion-evidence-unavailable"], "automatic_acceptance": False}
    if not isinstance(repo, str) or not pilot(repo) or type(run_id) is not int or run_id <= 0:
        return {**failure, "reasons": ["completion-scope-unconfigured"]}
    if repo.casefold() == "4444j99/portfolio":
        repo = "organvm-vii-kerygma/portfolio"
    repo = next(name for name in PILOT_REPOSITORIES if name.casefold() == repo.casefold())
    prefix = f"repos/{repo}"

    def read(path):
        response = gh(["api", path], timeout=20)
        if response.returncode or len(response.stdout) > 2_000_000:
            raise ValueError("completion-read-unavailable")
        value = json.loads(response.stdout)
        if not isinstance(value, dict):
            raise ValueError("completion-shape")
        return value

    try:
        repository = read(prefix)
        identity = repository.get("id")
        if type(identity) is not int or identity <= 0 or repository.get("full_name", "").casefold() != repo.casefold():
            return failure
        path = prefix + f"/actions/runs/{run_id}"
        run = read(path)
        refs = run.get("pull_requests")
        head = run.get("head_sha")
        if (
            run.get("id") != run_id
            or run.get("event") != "pull_request"
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("repository", {}).get("id") != identity
            or run.get("head_repository", {}).get("id") != identity
            or type(run.get("run_attempt")) is not int
            or run["run_attempt"] < 1
            or not isinstance(head, str)
            or not re.fullmatch(r"[0-9a-f]{40}", head)
            or not isinstance(refs, list)
            or len(refs) != 1
        ):
            return failure
        number = refs[0].get("number")
        if type(number) is not int or number <= 0 or refs[0].get("head", {}).get("sha") != head:
            return failure
        pr = read(prefix + f"/pulls/{number}")
        if (
            pr.get("number") != number
            or pr.get("state") != "open"
            or pr.get("draft") is not False
            or pr.get("head", {}).get("sha") != head
            or pr.get("base", {}).get("repo", {}).get("id") != identity
            or pr.get("base", {}).get("ref") != repository.get("default_branch")
            or pr.get("base", {}).get("sha") != refs[0].get("base", {}).get("sha")
        ):
            return failure
        evidence = inspect(repo, number, head, gh)
        # The ordinary consumer checks newest runs, trusted policy and artifacts.
        # A completion hint cannot override a newer attempt or a changed PR.
        after = read(path)
        current = read(prefix + f"/pulls/{number}")
        if any(
            after.get(key) != run.get(key) for key in ("id", "run_attempt", "head_sha", "status", "conclusion")
        ) or any(current.get(key) != pr.get(key) for key in ("number", "state", "draft", "head", "base")):
            return {**failure, "reasons": ["completion-generation-moved"]}
        return {
            **evidence,
            "completion_hint": {
                "repository_id": identity,
                "run_id": run_id,
                "run_attempt": run["run_attempt"],
                "pr": number,
                "head_sha": head,
            },
            "automatic_acceptance": False,
        }
    except Exception:  # noqa: BLE001 - redact provider and subprocess diagnostics
        return failure


def main():
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pr", type=int)
    mode.add_argument("--completed-run", type=int)
    parser.add_argument("--expected-head")
    args = parser.parse_args()

    def gh(arguments, timeout=60, binary=False):
        return subprocess.run(["gh", *arguments], capture_output=True, text=not binary, timeout=timeout, check=False)

    if args.completed_run is not None:
        if args.expected_head:
            parser.error("--completed-run derives its head from authenticated evidence")
        result = inspect_completion(args.repo, args.completed_run, gh)
    else:
        if not args.expected_head:
            parser.error("--pr requires --expected-head")
        result = inspect(args.repo, args.pr, args.expected_head, gh)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("route") == "not-dependency" else 2


if __name__ == "__main__":
    raise SystemExit(main())
