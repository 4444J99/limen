#!/usr/bin/env python3
"""Wake one finite institutional campaign epoch; never launch a provider directly."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from limen.conduct.campaign_wake import (
    WAKE_SCHEMA,
    CampaignWakeError,
    NoActiveCampaign,
    wake_campaign,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("LIMEN_ROOT", Path.cwd())))
    parser.add_argument("--workstream", default="institutional-omega")
    parser.add_argument("--timeout", type=int)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        timeout_seconds = (
            args.timeout
            if args.timeout is not None
            else int(os.environ.get("LIMEN_CAMPAIGN_WAKE_TIMEOUT", "300"))
        )
        payload = wake_campaign(
            args.root,
            workstream=args.workstream,
            timeout_seconds=timeout_seconds,
        )
    except NoActiveCampaign as exc:
        payload = {
            "schema": WAKE_SCHEMA,
            "boundary": "wait_relay",
            "invoked": False,
            "reason": str(exc),
            "successor_required": True,
            "workstream": args.workstream,
        }
        code = 0
    except (CampaignWakeError, ValueError) as exc:
        payload = {
            "schema": WAKE_SCHEMA,
            "boundary": "invalid",
            "invoked": False,
            "reason": str(exc)[:2000],
            "successor_required": False,
            "workstream": args.workstream,
        }
        code = 1
    else:
        code = 1 if payload["boundary"] == "invalid" else 0
    print(json.dumps(payload, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
