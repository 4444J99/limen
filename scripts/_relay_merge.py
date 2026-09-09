#!/usr/bin/env python3
"""Personal relay merge transaction; invoked only by the existing merge drain.

The dedicated governor credential belongs to the deployed keeper, never to a
candidate checkout or an Actions job. Workflow check rollups are not authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
import uuid
from pathlib import Path

REPOSITORY = "4444J99/organvm-ci-relay"
REPOSITORY_ID = 1350979676
CHECK = "Relay merge / governor"
ROOTS = (
    ".github/workflows",
    "scripts/verify-policy.mjs",
    "scripts/test-policy.mjs",
    "relay",
    "profiles",
    ".gitattributes",
    ".github/.gitattributes",
    "config/.gitattributes",
    "scripts/.gitattributes",
)
STEPS = (
    "Fetch the exact pull-request head and freeze executable policy",
    "Verify the candidate with the trusted base verifier",
    "Verify every registered operational SHA exists",
    "Regress the trusted base verifier",
)


class Hold(RuntimeError):
    """No authority to perform a merge."""


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value), "invalid SHA")
    return value


def app_id(value):
    require(type(value) is int and 0 < value < 2**53 and value != 15368, "dedicated App required")
    return value


def configuration(governor_app):
    app_id(governor_app)
    return {
        "branch_protection": {
            "required_status_checks": {
                "strict": True,
                "contexts": [],
                "checks": [{"context": CHECK, "app_id": governor_app}],
            },
            "enforce_admins": True,
            "required_pull_request_reviews": {
                "dismiss_stale_reviews": True,
                "require_code_owner_reviews": True,
                "required_approving_review_count": 1,
                "require_last_push_approval": True,
            },
            "restrictions": None,
            "required_conversation_resolution": True,
            "required_linear_history": True,
            "allow_force_pushes": False,
            "allow_deletions": False,
        },
        "update_ruleset": {
            "name": "Relay main updates through governor",
            "target": "branch",
            "enforcement": "active",
            "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
            "bypass_actors": [{"actor_id": governor_app, "actor_type": "Integration", "bypass_mode": "pull_request"}],
            "rules": [{"type": "update", "parameters": {"update_allows_fetch_and_merge": False}}],
        },
    }


class GitHub:
    def __init__(self, token):
        require(bool(token), "governor credential unavailable")
        self.token = token

    def __call__(self, path, method="GET", body=None):
        # Fixed origin; API-supplied URLs are never followed with the credential.
        require(path.startswith(f"/repos/{REPOSITORY}/"), "unexpected API scope")
        request = urllib.request.Request(
            "https://api.github.com" + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )

        # Repository transfers/redirects are a hold, not credential forwarding.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            data = response.read(4 * 1024 * 1024 + 1)
        require(len(data) <= 4 * 1024 * 1024, "API response too large")
        return json.loads(data)


def verify_controls(protection, ruleset, governor_app):
    """Two independent gates: no-bypass protection, PR-only exclusive updater."""
    app_id(governor_app)
    required = protection["required_status_checks"]
    require(required["strict"] is True, "strict checks required")
    require({"context": CHECK, "app_id": governor_app} in required["checks"], "governor check binding missing")
    require(
        not any(c.get("context") == CHECK and c.get("app_id") != governor_app for c in required["checks"]),
        "ambiguous check binding",
    )
    for field in ("enforce_admins", "required_conversation_resolution", "required_linear_history"):
        require(protection[field]["enabled"] is True, f"{field} required")
    for field in ("allow_force_pushes", "allow_deletions"):
        require(protection[field]["enabled"] is False, f"{field} forbidden")
    review = protection["required_pull_request_reviews"]
    require(
        type(review["required_approving_review_count"]) is int and review["required_approving_review_count"] >= 1,
        "independent approval required",
    )
    for field in ("dismiss_stale_reviews", "require_last_push_approval", "require_code_owner_reviews"):
        require(review[field] is True, f"{field} required")
    require(not any(review.get("bypass_pull_request_allowances", {}).values()), "review bypass forbidden")
    require(ruleset["enforcement"] == "active" and ruleset["target"] == "branch", "update gate inactive")
    require(
        ruleset["source_type"] == "Repository" and ruleset["source"].lower() == REPOSITORY.lower(),
        "update gate repository mismatch",
    )
    require(
        ruleset["conditions"] == {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "update gate scope mismatch",
    )
    require(
        ruleset["bypass_actors"]
        == [{"actor_id": governor_app, "actor_type": "Integration", "bypass_mode": "pull_request"}],
        "exclusive PR-only updater required",
    )
    require(
        ruleset["rules"] == [{"type": "update", "parameters": {"update_allows_fetch_and_merge": False}}],
        "updater exemption must not exempt checks/reviews",
    )


def snapshot(api, number, expected_head):
    prefix = f"/repos/{REPOSITORY}"
    pr = api(f"{prefix}/pulls/{number}")
    require(pr["number"] == number and pr["state"] == "open" and pr["draft"] is False, "PR not open and ready")
    require(pr["base"]["repo"]["id"] == REPOSITORY_ID and pr["base"]["ref"] == "main", "wrong base")
    require(pr["head"]["sha"] == sha(expected_head), "head changed")
    require(pr.get("auto_merge") is None, "auto-merge must be disabled")
    base = sha(api(f"{prefix}/git/ref/heads/main")["object"]["sha"])
    merge = sha(api(f"{prefix}/git/ref/pull/{number}/merge")["object"]["sha"])
    parents = api(f"{prefix}/git/commits/{merge}")["parents"]
    require([p["sha"] for p in parents] == [base, expected_head], "test merge is stale or malformed")
    require(merge != expected_head, "never authorize a candidate head")
    return {"base": base, "head": expected_head, "merge": merge, "head_repository": pr["head"]["repo"]["full_name"]}


def evaluate(candidate, policy_sha, read_token):
    """Replay only audited workflow bodies, with a read-only token and clean HOME.

    The pinned deployment commit supplies the allowed executable identities. The
    current base supplies data; candidate bytes are overlaid only by the trusted
    workflow's bounded regular-blob validation. No YAML from the candidate runs.
    """
    import yaml

    sha(policy_sha)
    require(bool(read_token), "separate read-only credential unavailable")
    with tempfile.TemporaryDirectory(prefix="limen-relay-") as temporary:
        root = Path(temporary)
        env = {
            "PATH": os.defpath + ":/usr/local/bin",
            "HOME": str(root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C.UTF-8",
        }

        def run(args, timeout=120, working_directory=None):
            result = subprocess.run(
                args,
                cwd=root if working_directory is None else working_directory,
                env=env,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            require(result.returncode == 0, "trusted evaluation failed")
            return result.stdout.decode()

        run(["git", "init", "trusted"])
        run(
            [
                "git",
                "-C",
                "trusted",
                "-c",
                "credential.helper=",
                "fetch",
                "--no-tags",
                "--depth=1",
                f"https://github.com/{REPOSITORY}.git",
                candidate["base"],
                policy_sha,
            ]
        )
        for path in ROOTS:
            pinned = run(["git", "-C", "trusted", "ls-tree", policy_sha, "--", path])
            current = run(["git", "-C", "trusted", "ls-tree", candidate["base"], "--", path])
            require(pinned == current, "base executable differs from audited deployment")
        run(["git", "-C", "trusted", "-c", "core.hooksPath=/dev/null", "checkout", "--detach", candidate["base"]])
        workflow = (root / "trusted/.github/workflows/relay-policy.yml").read_bytes()
        document = yaml.safe_load(workflow)
        steps = document["jobs"]["policy"]["steps"]
        selected = [s for s in steps if s.get("name") in STEPS]
        require(tuple(s["name"] for s in selected) == STEPS, "unexpected trusted workflow structure")
        env.update(
            {
                "BASE_REPOSITORY": REPOSITORY,
                "GITHUB_REPOSITORY": REPOSITORY,
                "BASE_REF": "main",
                "BASE_SHA": candidate["base"],
                "HEAD_SHA": candidate["head"],
                "HEAD_REPOSITORY": candidate["head_repository"],
                "GITHUB_API_URL": "https://api.github.com",
                "GITHUB_TOKEN": read_token,
                "CANDIDATE_ROOT": "candidate",
            }
        )
        for step in selected:
            require(
                step.get("shell") == "bash" and isinstance(step.get("run"), str) and "${{" not in step["run"],
                "unsupported trusted step",
            )
            run(
                ["bash", "--noprofile", "--norc", "-euo", "pipefail", "-c", step["run"]],
                timeout=600,
                working_directory=root / "trusted",
            )
        return hashlib.sha256(workflow).hexdigest()


def transact(api, number, head, governor_app, ruleset_id, evaluator):
    prefix = f"/repos/{REPOSITORY}"

    def controls():
        verify_controls(api(f"{prefix}/branches/main/protection"), api(f"{prefix}/rulesets/{ruleset_id}"), governor_app)

    controls()
    candidate = snapshot(api, number, head)
    receipt = "limen-relay-merge:" + str(uuid.uuid4())
    check = api(
        f"{prefix}/check-runs",
        "POST",
        {
            "name": CHECK,
            "head_sha": candidate["merge"],
            "status": "in_progress",
            "external_id": receipt,
            "output": {"title": "Governor evaluation in progress", "summary": json.dumps(candidate)},
        },
    )
    require(
        type(check["id"]) is int
        and check["id"] > 0
        and check["app"]["id"] == governor_app
        and check["head_sha"] == candidate["merge"]
        and check["name"] == CHECK,
        "unexpected check owner",
    )
    check_path = f"{prefix}/check-runs/{check['id']}"
    authorized = False
    try:
        digest = evaluator(candidate)
        require(bool(re.fullmatch(r"[0-9a-f]{64}", digest)), "missing evaluator receipt")
        controls()
        require(snapshot(api, number, head) == candidate, "candidate/base changed during evaluation")
        # Only this process's successful synchronous evaluation can reach merge.
        # A historical check or webhook delivery never enters this transition.
        authorized = True
        api(
            check_path,
            "PATCH",
            {
                "status": "completed",
                "conclusion": "success",
                "output": {
                    "title": "Governor evaluation passed",
                    "summary": json.dumps({**candidate, "workflow_sha256": digest, "transaction": receipt}),
                },
            },
        )
        result = api(f"{prefix}/pulls/{number}/merge", "PUT", {"sha": head, "merge_method": "squash"})
        require(result.get("merged") is True, "GitHub did not merge")
        landed = api(f"{prefix}/pulls/{number}")
        require(
            landed.get("merged") is True
            and landed["head"]["sha"] == head
            and landed.get("merge_commit_sha") == sha(result["sha"]),
            "landing not confirmed",
        )
        return {
            "repository": REPOSITORY,
            "pr": number,
            **candidate,
            "landed": result["sha"],
            "transaction": receipt,
            "check_id": check["id"],
        }
    finally:
        # Consume the authorization, including an ambiguous merge response. Never
        # retry a merge after a timeout; reconcile its receipt on the next session.
        try:
            api(
                check_path,
                "PATCH",
                {
                    "status": "completed",
                    "conclusion": "failure",
                    "output": {
                        "title": "Governor authorization consumed" if authorized else "Governor evaluation failed",
                        "summary": "One-shot authorization. A new attempt must evaluate again.",
                    },
                },
            )
        except Exception:  # noqa: BLE001 - cleanup cannot erase the merge/readback receipt
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int)
    parser.add_argument("--expected-head")
    parser.add_argument("--render-config", type=int, metavar="GOVERNOR_APP_ID")
    args = parser.parse_args()
    try:
        if args.render_config is not None:
            require(args.pr is None and args.expected_head is None, "render is read-only")
            print(json.dumps(configuration(args.render_config), indent=2))
            return 0
        require(args.pr is not None, "PR required")
        require(args.pr > 0, "invalid PR")
        governor_app = app_id(int(os.environ["LIMEN_RELAY_GOVERNOR_APP_ID"]))
        ruleset_id = int(os.environ["LIMEN_RELAY_UPDATE_RULESET_ID"])
        require(ruleset_id > 0, "invalid ruleset")
        token = os.environ["LIMEN_RELAY_GOVERNOR_TOKEN"]
        read_token = os.environ["LIMEN_RELAY_READ_TOKEN"]
        require(token != read_token, "evaluator must not receive the governor token")
        result = transact(
            GitHub(token),
            args.pr,
            sha(args.expected_head),
            governor_app,
            ruleset_id,
            lambda candidate: evaluate(candidate, os.environ["LIMEN_RELAY_POLICY_SHA"], read_token),
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:  # noqa: BLE001 - redact failures at the credential boundary
        # No provider response, environment value, or subprocess output can leak keys.
        print("HOLD: relay merge not confirmed; retain custody and reconcile before any retry.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
