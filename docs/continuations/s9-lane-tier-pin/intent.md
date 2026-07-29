# S9 — Lane tier pin: stop launched lanes inheriting a prohibited tier

## Objective

A workstream lane launched on the **claude** lane silently inherits the operator's *interactive*
model default, and today that default is a tier the estate prohibits for build work.

Measured 2026-07-29:

- `~/.claude/settings.json` sets `"model": "claude-fable-5[1m]"`.
- `scripts/lib/workstream-capsule.sh` — the generic (non-Codex) autonomous branch execs
  `"$binary" "$capsule_prompt"` with **no `--model`**, and the bare interactive branch execs
  `"$binary"` alone.
- `scripts/start-worktree-session.sh` rejects `--model` unless all three of
  `--model`/`--reasoning-effort`/`--sandbox` are supplied, and then hard-errors unless the lane is
  Codex (*"explicit model launch profiles require the Codex native lane"*).
- The PATH shim cannot save it: `model_selection.model_for_argv` returns `None` for any
  non-`-p`/`--print` invocation, and the shim is only on PATH when `heartbeat-loop.sh` prepends it —
  a hand-run launcher never sees it.
- `docs/fable-allotment.md`: *"Fable is **PLAN-ONLY** … **Building on Fable is prohibited** — no
  coding grind, no coverage sweeps, no PR babysitting."*

So every Claude umbrella opened by `limen workstream` starts on Fable and does build work there.

> **RE-MEASURED 2026-07-29 — and this domain is now SETTLED.** Two corrections:
>
> * The headroom sentence cited `logs/fable-allotment.json` reading `spent_pct: 7.52` against
>   `hard_cap: 50`. **That file does not exist** (`ls logs/fable-allotment.json` → no such file),
>   so the figure is uncheckable and must not be repeated. The argument never needed it: headroom
>   was explicitly *not* the defence — the prohibition is.
> * The defect itself is **repaired**. `heal/lane-tier-pin` merged as
>   [#1619](https://github.com/organvm/limen/pull/1619) (`7ba07525`), and this domain reads
>   `settled` from `scripts/check-session-streams.py --ready`.
>
> Retained as provenance. Do not re-open this domain to fix what #1619 already fixed; if a lane is
> still observed inheriting a prohibited tier, that is a **new** measurement and deserves its own
> row, not a re-run of this one.

**Re-measure all of the above before changing a line.** These are dated observations, not truths.

## Mission

Let a lane declare its tier, without weakening the Codex launch profile.

1. **Thread a lane tier pin** from `--model` (alone) through the capsule to the launched process, so
   the generic branch execs `"$binary" --model <tier> "$capsule_prompt"`. Scope it to lanes whose
   `--model` flag form is verified — do **not** silently swallow a pin on a lane that would ignore it;
   refuse instead.
2. **The contract is the hard part, and the reason this is its own domain.**
   `cli/src/limen/workstream_contract.py::_primary_launch` models a launch profile as *strictly
   Codex* — it raises on a non-Codex agent, and demands both a model and a reasoning effort; and
   `_authorization_for_sandbox` rejects an empty sandbox. The contract is **SHA-bound over its nine
   modules** and validated on both build and re-entry. Either route a bare lane pin *around*
   `primary_launch` entirely, or extend the contract with an explicit lane-pin variant and update
   **both** the build and verify sides plus the JSON schema. Do not half-change it: a contract that
   builds but fails re-entry validation bricks every capsule that carries it.
3. Keep the Codex triple's validation (`validate-codex-launch` against the live local catalog)
   **exactly as it is**.
4. Update the stale help text in `scripts/start-worktree-session.sh`'s usage block and the
   `--model` option help in `cli/src/limen/cli.py`, both of which currently say "Codex" only.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible work.
- Retained gates: destructive, credential, paid-spend, public-send, runtime/host mutation.
- **Do not weaken the Codex profile validation**, and do not relax the capsule identity/receipt
  hashing to make a change fit.
- Do not edit `~/.claude/settings.json` to work around this — that is the operator's interactive
  surface, and changing it would fix one symptom while leaving the launcher wrong.
- `scripts/fable-session-guard.py` exists but is **not armed**, and
  `docs/keys/fable-guard-settings-snippet.json` stages a settings hook. Arming it is a
  self-modification boundary: stage the exact file and hand over the one copy-paste, never apply it
  yourself. `his-hand-levers.json` already tracks this as an open lever — do not file a second one.

## Fan-out

At most **2** children, only via `limen conduct split <parent_run> --packet`. Never nest a git
worktree inside this one — the reclaim organ sweeps roots, so a nested worktree leaks.

## Constraints

Fresh branch `heal/lane-tier-pin` off updated `origin/main`, one concern.
`scripts/verify-scoped.sh`; `merge-policy.sh` → `await-pr.sh --merge`. **Claim the settlement with an anchored trailer in the merge commit message** — a line at
column 0 reading `Settles: s9-lane-tier-pin`. The STREAMS registry derives this domain's settled
state from that claim, and *only* from it: an unanchored mention no longer counts (it once
settled `s10-axis-coverage` off a docs commit that merely named it). The claiming commit must
also change something outside the registry and `docs/{plans,continuations}/` — bookkeeping
records an outcome, it cannot produce one.

## Done

`cli/tests/test_workstream_contract.py` passes, extended with cases proving: a bare lane pin reaches
the exec'd argv; a capsule carrying a lane pin **re-validates on re-entry** (build *and* verify); the
Codex triple still rejects a partial profile; and a pin on a lane that cannot honour it is **refused,
not ignored** — prove the refusal, not just the happy path. `python -m pytest cli/tests -q` green.
