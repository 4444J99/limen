---
name: closeout
description: Drive a task to a true closeout — ZERO open or dangling items. Verify ground truth read-only across all owners, close every gap so each owner records its own residual work, reach an idempotent fixed point (re-run = no changes), commit all loose work, and produce a relay handoff. Use when asked to close out, finalize, wrap up, archive, or hand off.
---

# Closeout

A closeout means **ZERO open or dangling items AND ZERO human-gated items recited at Anthony.** No caveats, no "still open" list, no "but also this" tail. Canonical definition: `CLAUDE.md` → Closeout Definition.

Every owed atom already has a durable, git-tracked home: **his-hand atoms** → a lever in `his-hand-levers.json`; **credential/token/login/env atoms** → the credential organ (`scripts/creds-hydrate.py` `DEFAULT_MAP` + Wall #320) — *never* a lever, *never* chat; **code follow-ups** → an issue in the owning repo. A closeout's job is to **prove, via executable predicate, that nothing hangs outside those homes** — never to hand Anthony a list. If an atom is already homed, it is DONE; re-surfacing it is the failure.

## Steps

1. **Verify ground truth (read-only) across all owners.** Fan out parallel read-only explorers — one per repo / component / ledger — each returning a structured packet `{ found, not_found, confidence }`. Merge into one report and flag conflicts. Never guess a location or timeframe; verify each explicitly.
2. **Route every gap to its owner — never to a chat list.** For each open item, resolve it now or **file it in its own git-tracked owner** (lever / credential organ / repo issue, per the homes above). Nothing parked in your head, in recall-only memory (`~/.claude/…` is **not** a durable home), or in the relay prose. An already-filed atom needs no action. A genuinely human-gated gate gets **`BLOCKED: <atom>` stated once**, filed as its lever/issue, then left alone — never looped on or re-surfaced — while every other reversible lane keeps moving.
3. **Prove nothing hangs — run the predicates (the gate is executable, not prose).**
   - `scripts/no-tasks-on-me.sh` — exit `0` ⟺ every owed his-hand atom lives in the registry with a graph `issue` pointer; no stranded refs; PII-clean.
   - `scripts/credential-wall.py --check` — exit `0` ⟺ every secret in use has a registered home.
   - the work's own `done.sh` or `scripts/verify-whole.sh` — re-run until it produces **no changes** and exits `0`. **Daemon-owned live state (`tasks.yaml`, `tasks.yaml.lock` — the heartbeat rewrites it every beat) is NOT yours and is excluded from the fixed point** (`verify-whole.sh` already excludes it; `capture.sh:46 RUNTIME_GLOBS` is canonical). Re-polling for a "clean tree" that a daemon perpetually dirties is the endless-loop failure — do not chase it.
   A **red predicate is unfiled work**: return to step 2 and FILE the atom — do not report it. That filing, not a chat list, **is** the closeout.
4. **Commit loose work across all repos.** `git add <path>` explicitly (**never `-A`**); commit; confirm `git status` is clean everywhere you touched. Push staged branches — but leave merges/deploys to Anthony (except the standing merge grant; see `CLAUDE.md` → Merge & Branch Protocol).
5. **Relay — cite the registry, never the atoms.** A concise note: what changed, the **predicate verdicts** as proof, and a single pointer to where owed work lives (e.g. "N atoms homed in `his-hand-levers.json` / Wall #320 — predicates green"). **Do NOT enumerate human-gated items, append a "but also / also this" tail, or leave any action at Anthony's feet.** Anything needing his hand is already a lever with an issue — the predicate proves it, the registry holds it, and he reads it there on his own cadence. End with the terminal statement — **"CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items"** — and stop; nothing follows it.

## Gate

Do **not** declare closeout until: every owed atom is filed in its own git-tracked owner, **`scripts/no-tasks-on-me.sh` AND `scripts/credential-wall.py --check` both exit `0`**, the work predicate re-runs to a zero-change fixed point (**excluding daemon-owned `tasks.yaml`/`tasks.yaml.lock`**), and all loose work is committed. Closeout means ZERO open items **and** ZERO recited remainders. The relay's last line is the terminal statement — anything after it is a caveat tail and fails the closeout.
