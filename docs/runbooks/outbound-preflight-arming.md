# Arming the outbound preflight gate

The gate ships **built and tested but not armed**. `.claude/settings.json` is a self-modification
boundary (CLAUDE.md § Standing Autonomy & Compliant Gate Reroute), so this is the one required
copy-paste. Everything around it — branch, tests, registries, PR, merge — is already done.

## The one edit

In `.claude/settings.json`, add a **third** entry to the existing `hooks.PreToolUse[0].hooks`
array (the `"matcher": "Bash"` block that already holds `worktree-commit-guard.sh` and
`pytest-scope-guard.sh`):

```json
{
  "type": "command",
  "command": "PROJECT_ROOT=\"${CLAUDE_PROJECT_DIR:-$PWD}\"; [ -x \"$PROJECT_ROOT/scripts/hooks/outbound-preflight-guard.py\" ] && LIMEN_ROOT=\"$PROJECT_ROOT\" python3 \"$PROJECT_ROOT/scripts/hooks/outbound-preflight-guard.py\" || true"
}
```

Byte-identical in shape to the two guards already there.

## Verify it took

```bash
bash scripts/tests/outbound-preflight-guard.test.sh    # 13/13, hermetic, no network

# and live — this must print a deny decision:
printf '%s' '{"tool_name":"Bash","tool_input":{"command":"scripts/mail-send --to someone@example.com"}}' \
  | python3 scripts/hooks/outbound-preflight-guard.py
```

## What it does when it fires

Denies the command and hands back the exact producing command:

```
python3 scripts/preflight-receipt.py --action mail.send --target <recipient>
```

That runs the real IMAP query against `[Gmail]/Sent Mail`. If anything already went out to that
recipient it **prints the prior message and fails**, so the next decision is made holding it. Only
an explicit `--acknowledge` of that specific Message-ID — a value only the server can supply —
lets a PASS receipt be minted.

## Why it is a deny and not a reminder

`~/.claude/settings.json` already carries a `PreToolUse` hook on `gh pr comment` that fires at the
exact moment of the action and opens with *"AUDIT: Did you read the full PR thread … BEFORE
composing this comment?"* — it emits `additionalContext`. A sibling hook is labelled
`"HARD BLOCK — LaunchAgent Creation"` and blocks nothing.

Proximity to the action was never the missing variable. Between 2026-03-24 and 2026-07-31 the
estate recorded **33 instances** of acting on an artifact that describes reality instead of
querying reality. **Ten prose rules were written for that class; all ten were followed by a
recurrence** — including `CLAUDE.md § Data Grounding`, written for this exact failure on
2026-07-24 and violated five times in the next six days.

On 2026-07-31 it produced the first completed outward escape: a redundant reply to a live
recruiter three hours after the operator had already answered the thread himself. The inbox was
read; Sent was not.

This gate checks `os.stat()` on a receipt plus a SHA-256 comparison. It is not a question the
model gets to answer about itself.

## Related, not yet armed

- `scripts/check-live-checkout.py` exists and is wired to no runner. A stale executing tree
  silently disarms every fix in it — that is how the 2026-07-29 finding recurred on 2026-07-31.
- `scripts/check-plan-decisions.py` is on `origin/main` and **absent** from the live checkout.
