#!/usr/bin/env python3
"""Read-only dependency evidence admission for the existing governor.

Native CI observations route an exact candidate to delegated review. They never
create merge authority: asynchronous results cannot close the merge-time race.
All source and archives are parsed as bounded data in the credentialed process.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path

PILOT_REPOSITORIES = frozenset(
    {
        "organvm-vii-kerygma/portfolio",
        "4444J99/portfolio",
        "organvm-iii-ergon/public-record-data-scrapper",
    }
)
SCHEMA = "organvm.dependency-evidence.v1"
TRUST_SCHEMA = "organvm.dependency-trust.v1"
MAX_ARCHIVE = 2 * 1024 * 1024
MAX_JSON = 1024 * 1024
MAX_BLOB = 8 * 1024 * 1024


class Hold(ValueError):
    """Evidence cannot authorize even delegated review."""


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value), "invalid-sha")
    return value


def positive(value):
    return type(value) is int and 0 < value < 2**53


def strict_json(raw, maximum=MAX_JSON):
    require(isinstance(raw, (str, bytes)) and len(raw) <= maximum, "json-size")

    def pairs(items):
        output = {}
        for key, value in items:
            require(key not in output, "duplicate-json-key")
            output[key] = value
        return output

    return json.loads(raw, object_pairs_hook=pairs)


def read_evidence_archive(raw):
    require(isinstance(raw, bytes) and len(raw) <= MAX_ARCHIVE, "archive-size-or-type")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        require(
            1 <= len(entries) <= 20 and sum(item.file_size for item in entries) <= MAX_BLOB,
            "archive-member-count-or-size",
        )
        names = [item.filename for item in entries]
        require(len(names) == len(set(names)) and names.count("dependency-evidence.json") == 1, "archive-member-count")
        for item in entries:
            require(
                item.filename == "dependency-evidence.json"
                or re.fullmatch(r"audit-(?:base|head)-[A-Za-z0-9_.-]+", item.filename),
                "archive-member-path",
            )
            require(not item.flag_bits & 1 and not item.is_dir(), "archive-member-type")
            mode = item.external_attr >> 16
            require((mode & 0o170000) in (0, 0o100000), "archive-member-type")
            require(0 < item.file_size <= MAX_JSON, "archive-member-size")
        return strict_json(archive.read("dependency-evidence.json"))


def pages(api, path, field=None, maximum=1000):
    rows = []
    separator = "&" if "?" in path else "?"
    for page in range(1, maximum // 100 + 1):
        value = api(f"{path}{separator}per_page=100&page={page}")
        part = value[field] if field else value
        require(isinstance(part, list), "incomplete-api-list")
        rows.extend(part)
        if field and "total_count" in value:
            total = value["total_count"]
            require(type(total) is int and len(rows) <= total <= maximum, "incomplete-api-list")
            if len(rows) == total:
                return rows
        elif len(part) < 100:
            return rows
        require(bool(part), "incomplete-api-list")
    raise Hold("api-list-bound")


def snapshot(api, repository, number, expected_head, policy):
    prefix = f"/repos/{repository}"
    pr = api(f"{prefix}/pulls/{number}")
    require(pr["number"] == number and pr["state"] == "open" and pr["draft"] is False, "pr-not-ready")
    require(pr["base"]["repo"]["id"] == policy["repository_id"], "repository-id")
    require(pr["base"]["repo"]["full_name"] == repository, "repository-name")
    require(pr["base"]["ref"] == policy["base_ref"], "base-ref")
    require(pr["head"]["sha"] == sha(expected_head), "head-changed")
    require(pr["head"]["repo"]["id"] == policy["repository_id"], "fork-candidate")
    require(pr.get("auto_merge") is None, "auto-merge-already-enabled")
    actor = pr["user"]
    require(
        actor["id"] == policy["dependabot_actor_id"] and actor["login"] == "dependabot[bot]" and actor["type"] == "Bot",
        "candidate-not-dependabot",
    )
    base = sha(api(f"{prefix}/git/ref/heads/{policy['base_ref']}")["object"]["sha"])
    merge = sha(api(f"{prefix}/git/ref/pull/{number}/merge")["object"]["sha"])
    parents = api(f"{prefix}/git/commits/{merge}")["parents"]
    require([p["sha"] for p in parents] == [base, expected_head], "stale-test-merge")
    require(merge != expected_head, "head-is-not-test-merge")
    return {"base_sha": base, "head_sha": expected_head, "tested_sha": merge, "author_id": actor["id"]}


def content(api, repository, path, revision):
    require(
        isinstance(path, str)
        and re.fullmatch(r"[A-Za-z0-9_./-]+", path)
        and not path.startswith("/")
        and ".." not in path.split("/"),
        "policy-file-path",
    )
    item = api(f"/repos/{repository}/contents/{path}?ref={sha(revision)}")
    require(item["type"] == "file" and item["path"] == path, "nonregular-policy-file")
    sha(item["sha"])
    return item


def blob_bytes(api, repository, item):
    blob = api(f"/repos/{repository}/git/blobs/{item['sha']}")
    require(
        blob["encoding"] == "base64" and type(blob["size"]) is int and 0 < blob["size"] <= MAX_BLOB, "lockfile-blob"
    )
    data = base64.b64decode(blob["content"].replace("\n", ""), validate=True)
    require(
        len(data) == blob["size"] and hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() == item["sha"],
        "lockfile-blob-identity",
    )
    return data


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def graph_delta(before, after, lockfile):
    for lock in (before, after):
        require(
            lock.get("lockfileVersion") == 3
            and isinstance(lock.get("packages"), dict)
            and "" in lock["packages"]
            and all(isinstance(item, dict) for item in lock["packages"].values()),
            "invalid-lockfile-graph",
        )
    result = {"added": [], "removed": [], "changed": []}
    for path in sorted(before["packages"].keys() | after["packages"].keys()):
        old, new = before["packages"].get(path), after["packages"].get(path)
        entry = new if new is not None else old
        name = path.rsplit("node_modules/", 1)[-1] if "node_modules/" in path else entry.get("name", path)
        common = {"lockfile": lockfile, "path": path, "name": name}
        if old is None:
            result["added"].append({**common, "entry": new})
        elif new is None:
            result["removed"].append({**common, "entry": old})
        elif canonical(old) != canonical(new):
            fields = sorted(
                key
                for key in old.keys() | new.keys()
                if (key in old) != (key in new) or canonical(old.get(key)) != canonical(new.get(key))
            )
            result["changed"].append({**common, "before": old, "after": new, "fields": fields})
    return result


def verify_pins(api, repository, state, policy):
    pins = policy["trusted_files"]
    require(
        isinstance(pins, dict) and policy["workflow_path"] in pins and "scripts/dependency-evidence.mjs" in pins,
        "trusted-files-incomplete",
    )
    for workflow in policy["required_workflows"]:
        require(workflow["path"] in pins, "workflow-pin-missing")
    for path, digest in pins.items():
        sha(digest)
        for revision in (state["base_sha"], state["head_sha"], state["tested_sha"]):
            require(content(api, repository, path, revision)["sha"] == digest, "executable-pin-drift")


def current_run(api, repository, workflow, state, policy):
    prefix = f"/repos/{repository}"
    runs = pages(api, f"{prefix}/actions/runs?event=pull_request&head_sha={state['head_sha']}", "workflow_runs")
    matches = [run for run in runs if run.get("path") == workflow["path"]]
    require(bool(matches), "trusted-workflow-run-missing")
    for run in matches:
        require(positive(run.get("id")) and positive(run.get("run_number")), "workflow-run-identity")
    selected = max(matches, key=lambda run: (run["run_number"], run["id"]))
    run = api(f"{prefix}/actions/runs/{selected['id']}")
    require(
        run["id"] == selected["id"] and run["path"] == workflow["path"] and run["event"] == "pull_request",
        "workflow-run-identity",
    )
    require(
        run["repository"]["id"] == policy["repository_id"]
        and run["repository"]["full_name"] == repository
        and run["head_repository"]["id"] == policy["repository_id"],
        "workflow-repository",
    )
    require(run["head_sha"] == state["head_sha"] and positive(run["run_attempt"]), "workflow-revision")
    require(not run.get("referenced_workflows"), "unreviewed-reusable-workflow")
    require(run["status"] == "completed" and run["conclusion"] == "success", "workflow-not-successful")
    return run


def verify_checkout_log(raw, tested_sha):
    require(isinstance(raw, (str, bytes)) and len(raw) <= 4 * 1024 * 1024, "checkout-log-size")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="strict")
    lines = [re.sub(r"^\d{4}-\d\d-\d\dT[^ ]+ ", "", line) for line in raw.splitlines()]
    found = []
    for index, line in enumerate(lines[:-1]):
        if re.fullmatch(r"(?:\[command\])?(?:/[^ ]+/)?git log -1 --format=%H", line):
            found.append(lines[index + 1].strip("'\""))
    require(found == [tested_sha], "checkout-revision-unproven")


def verify_jobs(api, log_reader, repository, run, workflow, state):
    jobs = pages(api, f"/repos/{repository}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs", "jobs")
    wanted = workflow["jobs"]
    require(isinstance(wanted, dict) and bool(wanted), "required-jobs-unconfigured")
    checkout_jobs = workflow["checkout_jobs"]
    require(
        isinstance(checkout_jobs, list) and bool(checkout_jobs) and set(checkout_jobs) <= set(wanted),
        "checkout-jobs-unconfigured",
    )
    for name, required_steps in wanted.items():
        selected = [job for job in jobs if job.get("name") == name]
        require(len(selected) == 1, "missing-or-duplicate-job")
        job = selected[0]
        require(
            job["run_id"] == run["id"]
            and job["run_attempt"] == run["run_attempt"]
            and job["head_sha"] == run["head_sha"],
            "job-attempt-identity",
        )
        require(job["status"] == "completed" and job["conclusion"] == "success", "job-not-successful")
        if name in checkout_jobs:
            require(positive(job["id"]), "job-identity")
            verify_checkout_log(log_reader(repository, job["id"]), state["tested_sha"])
        require(isinstance(required_steps, list) and bool(required_steps), "required-steps-unconfigured")
        for step_name in required_steps:
            steps = [step for step in job["steps"] if step.get("name") == step_name]
            require(
                len(steps) == 1 and steps[0]["status"] == "completed" and steps[0]["conclusion"] == "success",
                "required-step-not-successful",
            )


def fingerprint(run):
    return tuple(run[key] for key in ("id", "run_attempt", "head_sha", "path", "status", "conclusion", "updated_at"))


def evaluate(api, archive_reader, repository, number, expected_head, policy, log_reader=None):
    """Return review routing only; every API callback here is a GET."""
    require(positive(policy.get("repository_id")) and positive(policy.get("dependabot_actor_id")), "policy-identity")
    require(policy.get("base_ref") == "main" and policy.get("package_manager") == "npm", "policy-runtime")
    reviewer = policy.get("reviewer")
    require(
        isinstance(reviewer, dict)
        and positive(reviewer.get("id"))
        and isinstance(reviewer.get("login"), str)
        and bool(reviewer["login"]),
        "reviewer-unconfigured",
    )
    require(callable(log_reader), "checkout-log-reader-unavailable")
    state = snapshot(api, repository, number, expected_head, policy)
    require(reviewer["id"] != state["author_id"], "reviewer-is-author")
    verify_pins(api, repository, state, policy)
    workflows = policy["required_workflows"]
    require(
        isinstance(workflows, list) and bool(workflows) and len({w["path"] for w in workflows}) == len(workflows),
        "required-workflows-unconfigured",
    )
    runs = {}
    for workflow in workflows:
        run = current_run(api, repository, workflow, state, policy)
        verify_jobs(api, log_reader, repository, run, workflow, state)
        runs[workflow["path"]] = run
    primary = runs[policy["workflow_path"]]
    artifacts = pages(api, f"/repos/{repository}/actions/runs/{primary['id']}/artifacts", "artifacts")
    name = f"dependency-evidence-{primary['id']}-{primary['run_attempt']}"
    matches = [item for item in artifacts if item.get("name") == name]
    require(len(matches) == 1, "missing-or-duplicate-artifact")
    artifact = matches[0]
    require(
        positive(artifact["id"])
        and artifact["expired"] is False
        and type(artifact["size_in_bytes"]) is int
        and 0 < artifact["size_in_bytes"] <= MAX_ARCHIVE,
        "artifact-unavailable",
    )
    artifact_run = artifact["workflow_run"]
    require(
        artifact_run["id"] == primary["id"]
        and artifact_run["head_sha"] == state["head_sha"]
        and artifact_run["repository_id"] == policy["repository_id"]
        and artifact_run["head_repository_id"] == policy["repository_id"],
        "artifact-provenance",
    )
    raw = archive_reader(repository, artifact["id"])
    require(isinstance(raw, bytes) and len(raw) <= MAX_ARCHIVE, "archive-size-or-type")
    require(artifact.get("digest") == "sha256:" + hashlib.sha256(raw).hexdigest(), "artifact-digest")
    receipt = read_evidence_archive(raw)
    require(receipt["schema"] == SCHEMA and receipt["repository"] == repository, "receipt-schema-or-repository")
    for field in ("base_sha", "head_sha", "tested_sha"):
        require(receipt[field] == state[field], "receipt-revision")
    require(
        receipt["workflow_sha"] == state["tested_sha"] and receipt["workflow_path"] == policy["workflow_path"],
        "receipt-workflow",
    )
    require(
        str(primary["id"]) == receipt["run_id"] and str(primary["run_attempt"]) == receipt["run_attempt"],
        "receipt-attempt",
    )
    lockfiles = policy["lockfiles"]
    require(
        isinstance(lockfiles, list) and bool(lockfiles) and set(receipt["lockfile_sha256"]) == set(lockfiles),
        "lockfiles-incomplete",
    )
    actual_graph = {"added": [], "removed": [], "changed": []}
    for path in lockfiles:
        item = content(api, repository, path, state["tested_sha"])
        data = blob_bytes(api, repository, item)
        require(hashlib.sha256(data).hexdigest() == receipt["lockfile_sha256"][path], "lockfile-digest")
        before = strict_json(blob_bytes(api, repository, content(api, repository, path, state["base_sha"])), MAX_BLOB)
        after = strict_json(data, MAX_BLOB)
        observed = graph_delta(before, after, path)
        for field in actual_graph:
            actual_graph[field].extend(observed[field])
    require(
        receipt["route"] in ("delegated-review", "exception")
        and isinstance(receipt["exceptions"], list)
        and all(isinstance(reason, str) for reason in receipt["exceptions"]),
        "receipt-route",
    )
    graph = receipt["graph"]
    require(canonical(graph) == canonical(actual_graph), "dependency-graph-differs-from-source")
    require(all(isinstance(graph[field], list) for field in ("added", "removed", "changed")), "graph-incomplete")
    advisory = receipt["advisories"]
    require(
        all(
            isinstance(advisory[field], list)
            for field in ("base", "head", "introduced", "resolved", "remaining", "errors")
        ),
        "advisories-incomplete",
    )
    require(advisory["status"] == "complete" and not advisory["errors"], "advisory-closure-unverified")
    require(not advisory["introduced"], "advisory-introduced")
    require(
        all(
            isinstance(entry, dict) and entry.get("severity") in ("info", "low", "moderate", "high", "critical")
            for entry in advisory["head"]
        ),
        "advisory-severity-unavailable",
    )
    require(
        not any(entry["severity"] in ("high", "critical") for entry in advisory["head"]),
        "high-or-critical-advisories-remain",
    )
    require(not graph["added"] and not graph["removed"], "dependency-graph-additions-or-removals")
    require(bool(graph["changed"]), "dependency-graph-unchanged")
    require(receipt["route"] == "delegated-review" and not receipt["exceptions"], "dependency-policy-exception")
    # A changed base/head, rerun, or newer run during artifact retrieval invalidates
    # routing. This last read is not claimed as an atomic merge-time guarantee.
    require(snapshot(api, repository, number, expected_head, policy) == state, "candidate-changed-during-inspection")
    for workflow in workflows:
        require(
            fingerprint(current_run(api, repository, workflow, state, policy)) == fingerprint(runs[workflow["path"]]),
            "workflow-changed-during-inspection",
        )
    return {
        "route": "delegated-review",
        "reasons": [],
        **state,
        "reviewer": reviewer,
        "evidence": {
            "run_id": primary["id"],
            "run_attempt": primary["run_attempt"],
            "artifact_id": artifact["id"],
            "artifact_digest": artifact["digest"],
        },
        "automatic_acceptance": False,
    }


def inspect_candidate(repo, number, expected_head, gh_callable, trust_policy_path=None):
    """CLI adapter. Missing policy, denied reads, and malformed evidence HOLD.

    `gh_callable(args, timeout=60, binary=False)` returns CompletedProcess. The
    caller owns credentials. No secrets are accepted in policy or subprocess args.
    """
    canonical = {name.casefold(): name for name in PILOT_REPOSITORIES}
    canonical["4444j99/portfolio"] = "organvm-vii-kerygma/portfolio"
    if not isinstance(repo, str) or repo.casefold() not in canonical:
        return {"route": "not-dependency", "reasons": []}
    repo = canonical[repo.casefold()]
    result = {"route": "exception", "reasons": [], "head_sha": expected_head, "automatic_acceptance": False}
    prefix = f"/repos/{repo}"

    def api(path):
        require(path.startswith(prefix + "/"), "api-scope")
        response = gh_callable(["api", path], timeout=60)
        require(response.returncode == 0, "github-read-unavailable")
        return strict_json(response.stdout, 12 * 1024 * 1024)

    def archive_reader(repository, artifact_id):
        require(repository == repo and positive(artifact_id), "archive-api-scope")
        response = gh_callable(["api", f"{prefix}/actions/artifacts/{artifact_id}/zip"], timeout=60, binary=True)
        require(response.returncode == 0, "artifact-download-unavailable")
        return response.stdout

    def log_reader(repository, job_id):
        require(repository == repo and positive(job_id), "log-api-scope")
        response = gh_callable(["api", f"{prefix}/actions/jobs/{job_id}/logs"], timeout=60)
        require(response.returncode == 0, "job-log-unavailable")
        return response.stdout

    try:
        sha(expected_head)
        pr = api(f"{prefix}/pulls/{number}")
        require(pr["head"]["sha"] == expected_head, "head-changed")
        files = pages(api, f"{prefix}/pulls/{number}/files")
        require(len(files) == pr["changed_files"], "changed-files-incomplete")
        names = {item["filename"] for item in files}
        dependencies = {
            name
            for name in names
            if name.rsplit("/", 1)[-1]
            in ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "npm-shrinkwrap.json")
        }
        dependabot = pr.get("user", {}).get("login") == "dependabot[bot]"
        if not dependencies and not dependabot:
            return {"route": "not-dependency", "reasons": []}
        require(bool(dependencies) and names == dependencies, "unusual-dependency-files")
        require(
            all(item.get("status") == "modified" and not item.get("previous_filename") for item in files),
            "dependency-file-addition-removal-or-rename",
        )
        require(trust_policy_path is not None, "trust-policy-unconfigured")
        path = Path(trust_policy_path)
        require(path.is_file() and not path.is_symlink(), "trust-policy-unavailable")
        document = strict_json(path.read_bytes())
        require(document["schema"] == TRUST_SCHEMA and document.get("installed") is True, "trust-policy-not-installed")
        policy = document["repositories"].get(repo)
        require(isinstance(policy, dict), "repository-policy-unconfigured")
        allowed = set(policy["lockfiles"]) | {
            p.removesuffix("package-lock.json") + "package.json" for p in policy["lockfiles"]
        }
        require(names <= allowed, "unusual-dependency-files")
        return evaluate(api, archive_reader, repo, number, expected_head, policy, log_reader)
    except Hold as error:
        result["reasons"] = [str(error)]
    except (KeyError, TypeError, ValueError, OSError, zipfile.BadZipFile, RuntimeError, subprocess.SubprocessError):
        result["reasons"] = ["dependency-evidence-unavailable-or-malformed"]
    return result
