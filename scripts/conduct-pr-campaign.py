#!/usr/bin/env python3
"""Exact, resumable GitHub census and zero-growth predicate for peer-conduct campaigns."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.conduct.campaign import build_census, compare_censuses, read_census, write_census  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    census = sub.add_parser("census")
    census.add_argument("--owner", default="organvm")
    census.add_argument("--output", type=Path, required=True)
    census.add_argument("--max-pages", type=int, default=10000)
    verify = sub.add_parser("verify")
    verify.add_argument("--previous", type=Path, required=True)
    verify.add_argument("--current", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--current", type=Path, required=True)
    validate.add_argument("--digest", required=True)
    validate.add_argument("--repo")
    args = parser.parse_args()

    if args.command == "census":
        receipt = build_census(args.owner, max_pages=args.max_pages)
        write_census(args.output, receipt)
        print(
            json.dumps(
                {
                    "complete": receipt.complete,
                    "repository_total": receipt.repository_total,
                    "repositories_with_open_prs": receipt.repositories_with_open_prs,
                    "advertised_open_prs": receipt.advertised_open_prs,
                    "observed_open_prs": receipt.observed_open_prs,
                    "snapshot_digest": receipt.snapshot_digest,
                    "errors": receipt.errors,
                    "output": str(args.output),
                },
                indent=2,
            )
        )
        return 0 if receipt.complete else 1

    if args.command == "verify":
        comparison = compare_censuses(read_census(args.previous), read_census(args.current))
        print(json.dumps(comparison, indent=2))
        return 0 if comparison["zero_growth"] else 1

    current = read_census(args.current)
    repositories = {repo.name_with_owner: repo for repo in current.repositories}
    valid = (
        current.complete
        and current.snapshot_digest == args.digest
        and (args.repo is None or (args.repo in repositories and repositories[args.repo].complete))
    )
    print(
        json.dumps(
            {
                "complete": current.complete,
                "digest_matches": current.snapshot_digest == args.digest,
                "repo": args.repo,
                "repo_complete": args.repo is None or (
                    args.repo in repositories and repositories[args.repo].complete
                ),
                "valid": valid,
            },
            indent=2,
        )
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
