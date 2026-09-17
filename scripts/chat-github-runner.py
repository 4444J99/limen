#!/usr/bin/env python3
"""Trusted, bounded Actions phases for Chat-authored changes; no model invocation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}\Z")
IMAGE = re.compile(r"(?:python|node)@sha256:[0-9a-f]{64}\Z")


def canonical(value: object) -> bytes:
    # Profiles contain only ASCII strings, arrays, objects and integral bounds.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def validate_context(context: dict) -> dict:
    if not SHA.fullmatch(context.get("head", "")) or not SHA.fullmatch(context.get("control_sha", "")):
        raise ValueError("invalid exact commit")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", context.get("repository", "")):
        raise ValueError("invalid repository")
    if context["control_repository"] != os.environ.get("GITHUB_REPOSITORY"):
        raise ValueError("wrong controller repository")
    if context["control_sha"] != os.environ.get("GITHUB_SHA"):
        raise ValueError("wrong defining commit")
    if time.time() >= __import__("datetime").datetime.fromisoformat(context["deadline"].replace("Z", "+00:00")).timestamp():
        raise ValueError("original deadline exhausted")
    profile = json.loads((ROOT / "institutio/governance/chat-github-profiles.json").read_text())["profiles"][context["profile"]]
    if profile["repository"] != context["repository"] or hashlib.sha256(canonical(profile)).hexdigest() != context["profile_digest"]:
        raise ValueError("profile identity mismatch")
    if not IMAGE.fullmatch(profile["image"]) or not 1 <= profile["timeout_seconds"] <= 600:
        raise ValueError("unbounded verification profile")
    return profile


def api(path: str, data: dict) -> dict:
    origin = os.environ["LIMEN_CONDUCT_URL"].rstrip("/")
    if origin != "https://limen-runtime.ivixivi.workers.dev":
        raise ValueError("unapproved broker origin")
    request = urllib.request.Request(origin + path, data=json.dumps(data).encode(), headers={
        "Authorization": "Bearer " + os.environ["LIMEN_CHAT_EXECUTOR_TOKEN"], "Content-Type": "application/json",
    }, method="POST")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError("oversized broker reply")
        return json.loads(body)


def checked(argv: list[str], *, cwd: Path | None = None, timeout: int = 60) -> str:
    result = subprocess.run(argv, cwd=cwd, check=False, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} failed (exit {result.returncode}); output withheld")
    return result.stdout


def verify(context: dict, target: Path) -> dict:
    profile = validate_context(context)
    if checked(["git", "rev-parse", "HEAD"], cwd=target).strip() != context["head"]:
        raise ValueError("wrong checkout")
    if checked(["git", "status", "--porcelain"], cwd=target).strip():
        raise ValueError("dirty candidate checkout")
    for oracle in profile["oracle_paths"]:
        if checked(["git", "show", f"{context['head']}:{oracle}"], cwd=target) != (ROOT / oracle).read_text():
            raise ValueError("candidate changed trusted test oracle")
    checked(["docker", "pull", profile["image"]], timeout=90)
    # Read-only target, no checkout credentials, no Docker socket or controller mount.
    container_name = "limen-chat-" + context["head"][:16]
    command = ["docker", "run", "--name", container_name, "--rm", "--network=none", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--read-only", "--user=65534:65534", "--cpus=2", "--memory=2g", "--pids-limit=256",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=512m", "--mount", f"type=bind,source={target.resolve()},target=/target,readonly",
        "--workdir=/target", "--env=PYTHONDONTWRITEBYTECODE=1", "--env=HOME=/tmp", profile["image"], *profile["argv"]]
    # Output is private to the job's temp file, not emitted into public Actions logs.
    with tempfile.TemporaryFile() as output:
        start = time.monotonic()
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            while process.poll() is None:
                if time.monotonic() - start > profile["timeout_seconds"] or os.fstat(output.fileno()).st_size > 1024 * 1024:
                    timed_out = True
                    os.killpg(process.pid, __import__("signal").SIGKILL)
                    break
                time.sleep(0.2)
            code = process.wait(timeout=10)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, __import__("signal").SIGKILL)
                process.wait(timeout=10)
            subprocess.run(["docker", "rm", "--force", container_name], capture_output=True, timeout=10, check=False)
        output.seek(0)
        payload = output.read(1024 * 1024)
    result = {"schema_version": "limen.chat_verification.v1", "run_id": context["run_id"],
        "head": context["head"], "profile_digest": context["profile_digest"], "control_sha": context["control_sha"],
        "workflow_run_id": int(os.environ["GITHUB_RUN_ID"]), "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "exit_code": 124 if timed_out else code, "output_sha256": hashlib.sha256(payload).hexdigest(),
        "inference_provider_runs": 0, "sandbox_image": profile["image"]}
    # This file is outside the read-only candidate mount. Only trusted host code
    # can create the attestation or Actions output; candidate output stays hashed.
    Path("chat-verification.json").write_bytes(canonical(result))
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write("verification=" + canonical(result).decode() + "\n")
        output.write("artifact_name=chat-verification-" + hashlib.sha256(canonical(result)).hexdigest() + "\n")
    if result["exit_code"] != 0:
        raise RuntimeError(f"isolated predicate failed (exit {result['exit_code']}, output sha256 {result['output_sha256']})")
    return result


def publish(context: dict) -> dict:
    validate_context(context)
    repository, head = context["repository"], context["head"]
    branch = context["branch"]
    if not re.fullmatch(r"chat/[0-9a-f]{24}", branch):
        raise ValueError("invalid owned branch")
    current = json.loads(checked(["gh", "api", f"repos/{repository}/git/ref/heads/{branch}"]))
    if current["object"]["sha"] != head:
        raise ValueError("topic head moved")
    pulls = json.loads(checked(["gh", "api", "--method", "GET", f"repos/{repository}/pulls",
        "-f", f"head={repository.split('/')[0]}:{branch}", "-f", "state=all", "-f", "per_page=100"]))
    if len(pulls) > 1:
        raise ValueError("ambiguous PR identity")
    # Even an existing PR must pass the authenticated artifact fence before merge.
    pr = api(f"/api/conduct/github/runs/{context['run_id']}/publish", {
        "workflow_run_id": int(os.environ["GITHUB_RUN_ID"]), "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "verification": json.loads(os.environ["LIMEN_CHAT_VERIFICATION"])})
    if pr["head"]["sha"] != head or pr["head"]["repo"]["full_name"] != repository:
        raise ValueError("PR head differs")
    if context["landing"] == "merge" and not pr.get("merged_at"):
        sys.path.insert(0, str(ROOT / "cli/src"))
        from limen.fanout import PullRequestReceiptAdapter
        PullRequestReceiptAdapter().land({}, {"checks": [{"name": "pull-request", "url": pr["html_url"], "head": head}]}, merge=True)
    return {"pull_request": pr["number"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["context", "verify", "publish", "failed"])
    parser.add_argument("--profile")
    parser.add_argument("--target", type=Path, default=Path("target"))
    args = parser.parse_args()
    identity = {"workflow_run_id": int(os.environ["GITHUB_RUN_ID"]), "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"])}
    run_id = os.environ["LIMEN_CHAT_RUN_ID"]
    if not re.fullmatch(r"run-[0-9a-f]{32}", run_id):
        raise ValueError("invalid broker run")
    route = f"/api/conduct/github/runs/{run_id}"
    if args.phase == "failed":
        print(json.dumps(api(route + "/failed", identity)))
        return 0
    if args.phase == "context":
        context = api(route + "/context", identity)
        validate_context(context)
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write("context=" + json.dumps(context, separators=(",", ":")) + "\n")
        return 0
    context = json.loads(os.environ["LIMEN_CHAT_CONTEXT"])
    if context["run_id"] != run_id:
        raise ValueError("wrong request context")
    if args.phase == "verify":
        print(json.dumps(verify(context, args.target)))
    else:
        # Reauthenticate and fence the lease before any publication mutation.
        current = api(route + "/context", identity)
        if current != context:
            # Lease heartbeat times can differ; immutable execution identity cannot.
            for field in ("head", "base_sha", "digest", "profile_digest", "control_sha", "landing"):
                if current[field] != context[field]:
                    raise ValueError("execution context changed")
        result = publish(context)
        print(json.dumps(api(route + "/complete", {**identity, **result,"verification":json.loads(os.environ["LIMEN_CHAT_VERIFICATION"])})))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # No tokens, source, response bodies, or full exception repr in public job logs.
        print(f"chat-github-runner: {type(error).__name__}; execution incomplete", file=sys.stderr)
        raise SystemExit(1)
