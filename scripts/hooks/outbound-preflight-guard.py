#!/usr/bin/env python3
"""PreToolUse(Bash) hook: outbound-preflight-guard — deny an outward-facing action that has no
fresh, digest-bound PROOF that its ground-truth predicate was actually run against its target.

WHY (measured, not asserted): 33 recorded instances between 2026-03-24 and 2026-07-31 of one
class — acting on an artifact that DESCRIBES reality instead of querying reality. Ten prose rules
were written for it; all ten were followed by a recurrence. On 2026-07-31 it produced the first
completed outward escape: a redundant reply to a live recruiter whose thread the operator had
already answered. Full measurement + contract: institutio/governance/outbound-effectors.yaml.

WHY NOT ANOTHER CHECKLIST: ~/.claude/settings.json already carries a PreToolUse hook on
`gh pr comment` opening "AUDIT: Did you read the full PR thread ... BEFORE composing this
comment?" — it emits `additionalContext`, so the model answers itself "yes" and proceeds. A
sibling hook labelled "HARD BLOCK" blocks nothing. Proximity to the action was never the missing
variable; consequence was. This hook emits `permissionDecision: deny`, and the thing it checks is
os.stat() plus a SHA-256 comparison — not a question the model gets to answer about itself.

DENY CONTRACT (house pattern — worktree-commit-guard.sh:125): print ONE JSON object on stdout and
exit 0. The exit code is never the channel; silence means allow. This hook never emits "allow",
so it cannot widen the permission surface — Claude Code's deny-beats-allow precedence settles the
overlap with the blanket Bash(gh *) grant in .claude/settings.local.json.

POSTURE — fail-CLOSED inside the match, fail-OPEN outside it:
  · no `match` pattern hits                    -> silent pass (most commands)
  · a pattern hits, target unextractable       -> DENY (an unparseable recipient is not a reason
                                                  to send to a real human)
  · a pattern hits, receipt missing/stale/
    wrong-predicate/FAIL/SKIP                  -> DENY, naming the exact producing command
  · registry unreadable / limen not importable -> DENY for matched commands only
This inverts worktree-commit-guard.sh's fail-open posture on purpose: that guard protects a
reversible local commit; this one protects a message to a person.

Escape hatch: LIMEN_ALLOW_UNVERIFIED_OUTBOUND=1 (declared in institutio/governance/parameters.yaml).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[2])
REGISTRY = Path(
    os.environ.get("LIMEN_OUTBOUND_REGISTRY") or ROOT / "institutio" / "governance" / "outbound-effectors.yaml"
)

# Cheap O(1) prefilter tokens — almost every Bash call carries none of these, so we bail before
# any YAML parse or import (worktree-commit-guard.sh:35-38 pattern).
_PREFILTER = (
    "smtp",
    "mail-send",
    "mail_send",
    "send_drafts",
    "send_message",
    "gh pr comment",
    "gh issue comment",
    "osascript",
)


def _deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")


def _target_digest(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:16]


def _targets(command: str, target_spec: dict) -> list[str]:
    """EVERY target in the command, deduped, in order of appearance.

    Addresses are lower-cased so the receipt file (_target_digest already lower-cases) and the
    predicate string agree on one identity. Before this, `--to Someone@x.com` found the receipt
    minted for `someone@x.com` and then rejected it on predicate_digest mismatch — safe, but it
    forced a pointless re-run on a difference no mail system observes.
    """
    pattern = target_spec.get("pattern") or ""
    if not pattern:
        return []
    normalize = target_spec.get("kind") == "email"
    found: list[str] = []
    for match in re.finditer(pattern, command):
        value = (match.group(1) if match.groups() else match.group(0)).strip()
        if normalize:
            value = value.lower()
        if value and value not in found:
            found.append(value)
    return found


def main() -> int:
    # Consume stdin FIRST, unconditionally — an early exit leaving the payload writer on a closed
    # pipe becomes a BrokenPipeError upstream.
    try:
        raw = sys.stdin.read()
    except (OSError, UnicodeError):
        return 0

    if os.environ.get("LIMEN_ALLOW_UNVERIFIED_OUTBOUND") == "1":
        return 0

    lowered = raw.lower()
    if not any(token in lowered for token in _PREFILTER):
        return 0

    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return 0
    command = ((payload.get("tool_input") or {}).get("command")) or ""
    if not command:
        return 0

    try:
        import yaml  # noqa: PLC0415 — deliberately after the prefilter; never imported on the hot path
    except ImportError:
        return 0
    try:
        registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return 0

    effectors = registry.get("effectors") or {}
    receipts_dir = ROOT / (registry.get("receipts_dir") or "logs/preflight-receipts")

    for action_id, spec in effectors.items():
        patterns = spec.get("match") or []
        if not any(re.search(pattern, command, re.IGNORECASE) for pattern in patterns):
            continue

        target_spec = spec.get("target") or {}
        targets = _targets(command, target_spec)
        if not targets:
            _deny(
                f"outbound-preflight [{action_id}]: this command performs an outward-facing action "
                f"but its target could not be read from the command text, so no proof of "
                f"observation can be checked. An unparseable target is not a reason to proceed. "
                f"Rewrite the command so the target is literal, or run the ground-truth check by "
                f"hand: {spec.get('predicate', '')}"
            )
            return 0

        max_age = int(spec.get("max_age_seconds") or 900)

        sys.path.insert(0, str(ROOT / "cli" / "src"))
        try:
            from limen.omega_owner_receipt import (  # noqa: PLC0415
                OmegaOwnerReceiptError,
                load_owner_receipt,
            )
        except ImportError as exc:
            _deny(
                f"outbound-preflight [{action_id}]: the receipt verifier could not be imported "
                f"({exc}), so this outward action cannot be proven safe. Fail-closed by design."
            )
            return 0

        # EVERY target must be proven, not just the first one the regex found. A single-match gate
        # is walked around by `--to <proven> --cc <unproven>`: the command still reaches the second
        # human, and the first address alone opened the door. Verified as a live bypass on
        # 2026-07-31 before this loop existed.
        for target in targets:
            predicate = str(spec.get("predicate") or "").replace("{target}", target)
            rung_id = f"{action_id}.{_target_digest(target)}".lower()
            try:
                load_owner_receipt(
                    receipts_dir / f"{rung_id}.json",
                    rung_id=rung_id,
                    predicate=predicate,
                    max_age_seconds=max_age,
                    require_pass=True,
                )
            except OmegaOwnerReceiptError as exc:
                others = [other for other in targets if other != target]
                also = f"\n(this command also addresses: {', '.join(others)})\n" if others else ""
                _deny(
                    f"outbound-preflight [{action_id}] BLOCKED for target {target}.\n"
                    f"{str(spec.get('reason') or '').strip()}\n{also}\n"
                    f"Reason: {exc}\n\n"
                    f"Run this first — it queries the real state and mints the receipt:\n"
                    f"    python3 scripts/preflight-receipt.py --action {action_id} --target {target}\n\n"
                    f"If it reports a prior send you had not read, READ IT before deciding. The "
                    f"receipt is bound to this exact target and predicate and expires in "
                    f"{max_age}s, so it cannot be reused, forged, or self-certified. Every "
                    f"addressee needs its own receipt."
                )
                return 0
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — a guard that crashes must never break the session
        sys.stderr.write(f"outbound-preflight-guard: internal error: {exc}\n")
        sys.exit(0)
