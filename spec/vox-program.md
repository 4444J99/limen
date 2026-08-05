# VOX Program — Meta Registration & Macro Verification

**Owner:** limen dispatch / `agy-conductor`
**Status:** open
**Concern:** register the program so each plan is verified against meta/macro,
then assigned to its owner.

## The program
A cross-repo initiative:
- `vox` — pure voice core (clone / synthesize / transcribe / reading styles).
- `in-my-head` — consumer: messages read back in your voice.
- `universal-mail--automation` — owns account-backed transports (Twilio/Gmail).
- limen credential organ (`creds-hydrate`) — owns the ElevenLabs secret.

## Process
1. Add a parent initiative `VOX` to `tasks.yaml` with child tasks `VOX-0…VOX-5`
   plus `VOX-META`, each with `target` = its plan file, `owner` = the repo/agent,
   `status: open`.
2. Verification gate (pre-assignment): an agent checks each plan file against:
   - AGENTS.md precedence + task lifecycle + his-hand (no account action as a chat task),
   - organ boundaries (vox core / sign-signal play / mail transports),
   - credential protocol (creds-hydrate.py — no secret in repo, env-injected),
   - NAMING.md (ideal-form derivation),
   - `vox/types` single-contract rule.
3. Only plans passing the gate are dispatched to their owner; failures return to
   the board with the specific unmet constraint.
4. Macro review in `meta-organvm/governance` confirms the program doesn't collide
   with sibling organs.

## Verify against meta/macro
This file *is* the meta check; it cites every canonical doc above.

## Dispatch
`VOX-META` → owner `limen dispatch`.

## Open by design
The initiative grows new child tasks (e.g. new consumers) as ideal forms emerge.
