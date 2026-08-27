#!/usr/bin/env python3
"""Mint and post PSP-P03 and PSP-P04 phase receipts as GitHub issue comments.

Usage: python3 scripts/mint_phase_receipts.py [--dry-run]

This script:
1. Runs --phase-proof for PSP-P03 and PSP-P04 to verify predicates pass
2. Computes the output_sha256 of each predicate output
3. Builds the schema-valid phase receipt JSON
4. Posts it as a GitHub issue comment with the positioning-phase-receipt marker
5. Runs --verify-phase to confirm the posted receipt validates
"""

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import urllib.parse


GITHUB_API = "https://api.github.com"
REPO = "4444J99/limen"

# Issue numbers for PSP-P03 and PSP-P04 phase issues
PHASE_ISSUES = {
    "PSP-P03": 2181,
    "PSP-P04": 2189,
}

# Evidence URLs (the phase-level issue)
PHASE_EVIDENCE = {
    "PSP-P03": "https://github.com/4444J99/limen/issues/2181",
    "PSP-P04": "https://github.com/4444J99/limen/issues/2189",
}


def run(args, **kwargs):
    r = subprocess.run(args, capture_output=True, text=True, **kwargs)
    return r


def gh_post_comment(issue_number: int, body: str, token: str, dry_run: bool) -> str:  # allow-secret
    """Post a comment to a GitHub issue. Returns the comment URL."""
    url = f"{GITHUB_API}/repos/{REPO}/issues/{issue_number}/comments"
    payload = json.dumps({"body": body}).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if dry_run:
        print(f"[DRY RUN] Would POST to {url}")
        print(f"[DRY RUN] Body (first 200 chars): {body[:200]}")
        return "https://github.com/4444J99/limen/issues/DRY_RUN"

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
        return str(data.get("html_url", ""))


def mint_receipt(phase_id: str, dry_run: bool, token: str) -> dict:  # allow-secret
    print(f"\n=== Minting {phase_id} phase receipt ===")

    # Run the phase-proof predicate
    r = run(["python3", "scripts/positioning-program.py", "--phase-proof", phase_id])
    if r.returncode != 0:
        print(f"ERROR: --phase-proof {phase_id} failed (rc={r.returncode}):")
        print(r.stdout)
        print(r.stderr)
        sys.exit(1)

    output_text = r.stdout.strip()
    output_sha256 = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
    print(f"  predicate output sha256: {output_sha256}")

    # Parse the binding values from the output
    try:
        bindings = json.loads(output_text)
    except json.JSONDecodeError as e:
        print(f"ERROR: --phase-proof {phase_id} output is not valid JSON: {e}")
        sys.exit(1)

    if bindings.get("status") != "pass":
        print(f"ERROR: --phase-proof {phase_id} status is not pass: {bindings.get('status')}")
        sys.exit(1)

    # Get the current main head
    main_head_r = run(["git", "rev-parse", "origin/main"])
    main_head = main_head_r.stdout.strip()
    if not main_head or len(main_head) != 40:
        print(f"ERROR: Could not get origin/main head: {main_head!r}")
        sys.exit(1)
    print(f"  origin/main head: {main_head}")

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    receipt = {
        "schema_version": "limen.positioning_phase_receipt.v1",
        "phase_id": phase_id,
        "status": "pass",
        "predicate": {
            "command": f"python3 scripts/positioning-program.py --phase-proof {phase_id}",
            "exit_code": 0,
            "observed_at": now,
            "output_sha256": output_sha256,
        },
        "observed_heads": {"4444J99/limen": main_head},
        "child_receipts_sha256": bindings["child_receipts_sha256"],
        "exit_gate_sha256": bindings["exit_gate_sha256"],
        "parity_sha256": bindings["parity_sha256"],
        "remote_state_sha256": bindings["remote_state_sha256"],
        "evidence_urls": [PHASE_EVIDENCE[phase_id]],
    }

    receipt_json = json.dumps(receipt, indent=2)
    print(f"  receipt JSON built ({len(receipt_json)} bytes)")

    # Build the comment body with the required marker
    comment_body = f"""<!-- positioning-phase-receipt:{phase_id} -->

Phase receipt: `{phase_id}` — predicate passed at `{now}`.

```json
{receipt_json}
```

Predicate: `python3 scripts/positioning-program.py --phase-proof {phase_id}`
Exit code: 0
Output SHA-256: `{output_sha256}`
Observed `4444J99/limen` head: `{main_head}`
"""

    issue_number = PHASE_ISSUES[phase_id]
    print(f"  posting to issue #{issue_number}...")
    comment_url = gh_post_comment(issue_number, comment_body, token, dry_run)
    print(f"  comment posted: {comment_url}")

    return {
        "phase_id": phase_id,
        "receipt": receipt,
        "comment_url": comment_url,
        "output_sha256": output_sha256,
        "main_head": main_head,
        "observed_at": now,
    }


def verify_phase(phase_id: str) -> bool:
    """Run --verify-phase and return True if it passes."""
    r = run(["python3", "scripts/positioning-program.py", "--verify-phase", phase_id])
    if r.returncode == 0:
        print(f"  --verify-phase {phase_id}: PASS")
        print(f"  {r.stdout.strip()[:200]}")
        return True
    else:
        print(f"  --verify-phase {phase_id}: BLOCKED")
        print(f"  {r.stdout.strip()}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Mint PSP-P03 and PSP-P04 phase receipts")
    parser.add_argument("--dry-run", action="store_true", help="Do not post to GitHub")
    parser.add_argument("--phase", choices=["PSP-P03", "PSP-P04", "both"], default="both")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")  # allow-secret
    if not token and not args.dry_run:
        print("ERROR: GITHUB_TOKEN or GH_TOKEN environment variable required")
        sys.exit(1)

    phases = ["PSP-P03", "PSP-P04"] if args.phase == "both" else [args.phase]
    results = {}

    for phase_id in phases:
        results[phase_id] = mint_receipt(phase_id, args.dry_run, token or "")

    print("\n=== Verifying posted receipts ===")
    if not args.dry_run:
        for phase_id in phases:
            verify_phase(phase_id)
    else:
        print("[DRY RUN] Skipping --verify-phase")

    print("\n=== Summary ===")
    for phase_id, result in results.items():
        print(f"  {phase_id}: {result['comment_url']}")
        print(f"    output_sha256: {result['output_sha256']}")
        print(f"    head: {result['main_head']}")
        print(f"    observed_at: {result['observed_at']}")


if __name__ == "__main__":
    main()
