# Antigravity Scratch Root Blockers

Generated: `2026-07-07T15:40:50Z`

This receipt records scratch roots that are unsafe to delete and too large or
duplicative for an unbounded worker packet. It supplements
`docs/antigravity-scratch-bridge.md`; the bridge remains the generated
inventory, while this file records owner/blocker decisions.

## session-meta duplicate group

Decision: `owner-blocked`.

Owner repo: `organvm/session-meta`.

Roots:

| Scratch root | Size | Head | Tracked dirty | Untracked | Deleted entries | Disposition |
|---|---:|---|---:|---:|---:|---|
| `organvm-session-meta` | `4.7G` | `2954214acb76` | `2741` | `13` | `2741` | `owner-blocked` |
| `session-meta-no-prompt` | `4.5G` | `2954214acb76` | `2741` | `14` | `2741` | `owner-blocked` |
| `session-meta-2` | `4.5G` | `2954214acb76` | `2741` | `13` | `2741` | `owner-blocked` |

Blocker: all three roots are the same large staged-missing fingerprint on the
same owner repo/head. Deleting them would destroy evidence. Archiving them would
copy roughly 13.7G of duplicate state and still require redaction acceptance.
The next safe action is an owner-repo `session-meta` decision: either prove this
staged deletion set is superseded by a remote/default-equivalent ref, or create
a narrow owner PR/receipt that carries the intended delta. Until then, keep the
roots in place.

Verification:

```bash
for name in organvm-session-meta session-meta-no-prompt session-meta-2; do
  p="$HOME/.gemini/antigravity-cli/scratch/$name"
  du -sh "$p"
  git -C "$p" remote get-url origin
  git -C "$p" rev-parse --short=12 HEAD
  git -C "$p" status --porcelain=v1
done
```
