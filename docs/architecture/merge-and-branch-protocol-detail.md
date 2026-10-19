# Merge & Branch Protocol — Case History and Detail

`CLAUDE.md` → **Merge & Branch Protocol** is loaded into every Claude session and is capped by
`scripts/check-agent-docs.py` (see `CLAUDE_MD_CHAR_CAP`). The rule text stays there; the incident
history, the long-form rationale, and the mechanism detail relocated here so the charter stays under
the cap without losing the evidence behind each rule. Nothing below is new policy.

## Chunking — the jules-capfill park

A branch is **one concern, not one session.** When a session produces multiple concerns, cut a fresh
branch per concern off `origin/main` — finish → push → PR → next branch — never accumulate
heterogeneous commits on a single session branch. And the **live checkout rests on `main`**: parking
it on a work branch pins the running fleet to stale code and entangles every autonomic capture into
that branch (the 2026-06-29 jules-capfill park: 5 days, 65 behind, a feature slice + daemon receipts
fused onto one ref). `scripts/sync-release.sh` auto-unparks a fully-pushed, clean park each beat and
fails open loudly otherwise — do session work in a worktree, never in the live checkout.

## Settling a session stream

If a PR completes a domain declared in
[`institutio/governance/session-streams.yaml`](../../institutio/governance/session-streams.yaml), claim
it with an anchored trailer at **column 0** of the merge commit message — `Settles: <stream-id>`
(comma-separated for several). That claim is the *only* thing that marks a domain settled, and the
claiming commit must change something outside the registry and `docs/{plans,continuations}/`:
bookkeeping records an outcome, it cannot produce one. A passing mention no longer counts — the old
unanchored `git log --grep=<id>` rule settled `s10-axis-coverage` off a docs commit whose whole
subject was that s10 owns work a plan should *not* do. `scripts/check-session-streams.py` is the
predicate.

## No side doors — docs included

The branch cadence applies to *every* tracked change, including one-file docs appends (the
`docs: review … run` class, which was landing as direct `main` commits — 35 of 40 at its worst). Ship
those with **`scripts/ship-docs.sh <slug> "<msg>" <file…>`**: it stages only the named files onto a
fresh branch cut from `origin/main` in an isolated reclaim-tracked worktree (your checkout is never
touched), opens the PR, and self-merges the moment `merge-policy.sh` clears while retaining the
branch/root for later accepted cleanup — one command, so the PR path is never harder than the side
door. The system's own findings are githubbed the same way: **`scripts/sync-censor-issues.py`**
(beat-wired, dry-run until `LIMEN_CENSOR_ISSUES_APPLY=1` arms it) mirrors live censor residuals to
public `censor`-labelled issues and auto-closes them when the lineage clears — so insight→correction
work arrives as an issue and leaves as a PR that cites it. TABVLARIVS is the only logical
board-projection writer: the keeper commits accepted events with SHA compare-and-swap and publishes
only through the stable `tabularius/board-projection` branch, whose exact head enters the normal PR
rail. Agent sessions never push `tasks.yaml`, and the keeper never pushes `main`; the remote
no-bypass `pull_request` rule rejects every direct default-branch push, including automation and
admins.

## The website guardrail — path match AND rail armed

Classification is **path match AND rail armed**, because the question was never "does this glob
match" but "will merging change what is served". A rail whose every effect-bearing step is
conditioned on a secret that does not exist deploys nothing — it runs, prints a skip notice, and goes
green. The **api rail is dormant** on exactly those grounds (`GCP_SA_KEY` exists nowhere; the live API
is the Worker), so `web/api/**` and `cli/**` are non-deploy. Dormancy is declared in each trigger's
`arming` block and *proven* by check-gates **K** — offline from the workflow's own step gating, and
corroborated against the latest run's step conclusions, which is what catches the secret landing
while the registry still says dormant. Absent an `arming` block a trigger is armed: the default
over-protects.

## Waiting on a gate

Agent/provider sessions never wait on PR state: no hand-rolled loop, no sleep/recheck sequence, and
no synchronous waiter. **`scripts/await-pr.sh` is retired and fails closed.** The single-owner fast
lane merges its locally verified exact head immediately with `--match-head-commit`; remote CI and bot
review are advisory. Other repositories submit one exact head at most once through
`scripts/merge-drain.py --repo OWNER/NAME --pr NUMBER --expected-head SHA`; GitHub and the recurring
merge drain own every later observation. Queue mode never rewrites the PR head when `main` moves:
GitHub creates a synthetic latest-base merge group for that shared-writer rail. Before submitting or
merging, read `logs/AUTONOMY_PAUSED`: its `prohibitions:` bind interactive sessions too — a marker
that prohibits merges means no submission and no merge until the operator releases it.

## Revising against a gate — an automated reviewer is a generator, not a gate

The twin of the watcher ban above, and it costs more. A bot that re-reviews **each new head** has no
fixed point: handed a fresh diff it always emits something, and every fix *adds* lines, so the surface
the next round reviews is larger than the last. Chasing it diverges. (2026-08-12: PR #2122 ran 4 days,
~180 commits, +5,838/−204 across 29 files and 167 inline comments — 119 from one bot — while
`merge-policy.sh` had returned **CLEARED** the whole time; the degenerate tail is
`style(test): restore terminal newline` three commits in a row. Sibling PRs that week drew 0, 6, and 0
comments.) So: **the merge decision belongs to `scripts/merge-policy.sh` alone** — when it exits
`0 CLEARED`, merge, and residual reviewer findings become follow-up issues, never a pre-merge
obligation (this is the same rule as "an advisory check never holds a non-deploy merge", applied to
prose instead of checks). Bound any fix-on-review cycle at **two rounds**, then stop with a loud
verdict naming what you did not address; a third round is evidence the reviewer is generating rather
than converging. Precedent: `PREC-2026-08-12-advisory-review-loop-has-no-fixed-point`.

# Other relocated charter detail

These four blocks were also moved out of `CLAUDE.md` for the size cap; they sit in other sections
there (Never Over-Claim Completion, Parallel Exploration & Fan-Out, Worktree Isolation & CI Gate Matrix,
Session Phase Entry).

## A/B a change against its own parent commit

**A/B a change against its own parent commit, never against a branch name.** Once the PR merges,
`origin/main` *contains* the change, so `git show origin/main:<file>` silently hands back the fixed
file as the "before" — and the A/B compares the fix to itself and passes. The three-dot
`git diff origin/main...HEAD` keeps showing a correct diff throughout (it resolves the merge base), so
nothing looks wrong. Extract the baseline from `<sha>^` and assert a marker is absent from it before
trusting any before/after. (2026-08-07: a post-merge runtime verification's first "pre-fix"
extraction was the fixed file.)

## Tier every fan-out agent by job

**Tier every fan-out agent by job — never let it inherit.** In-harness subagents (the Task tool *and*
Workflow `agent()`) default to **the session model**, so a fan-out of trivial workers silently rides
the session's Opus (the `verify-studio-launch` incident: six broken-link/typo checks on Opus 4.8).
Pick each agent's tier by its job: choose an `agentType` from `.claude/agents/` (`verify`/`scan` →
haiku, `synth` → opus) or pass an explicit `model` + `effort`. The frontmatter pin is a **floor, not a
cap** — a per-call `model` still escalates a genuinely hard job upward. The class→tier authority is
`cli/src/limen/model_selection.py` plus `dispatch._claude_tier_for` (do **not** restate the ladder
here); an untiered expensive-tier fan-out is surfaced every session by the
`scripts/claude-workflow-guard.py` audit wired into `SessionEnd`.

## The beat sensor estate is declared data too

The heartbeat's continuous-runtime sensors live in
[`institutio/governance/sensors.yaml`](../../institutio/governance/sensors.yaml) (the SENSORS registry,
VIGILIA's third axis beside GATES and PARAMETERS), and `scripts/metabolize.sh` **derives** its whole
sensor pass from it via one `scripts/beat-sensors.py --run --source metabolize` call (`--list` prints
the matrix; `LIMEN_BEAT_DERIVE=0` skips the pass — an escape hatch; the hand-wired `── 0x ──` blocks
are gone). `scripts/check-sensors.py` (wired into pr-gate) holds it in parity with the scripts, the
parameter panel, and the beat sources — its D-check accepts the derive-runner call in place of literal
gate strings. **Adding a beat sensor = adding one `sensors.yaml` entry** — never a hand-wired shell
block. Every consumer that reads a sensor fact derives it from the registry, not the shell:
`check-params.py`'s `registry_referenced_tokens`, `armed-valve-audit.py`'s `discover_sensor_valves`
(gate + `armed_valve_type`), and `omega.sh`, which derives its registry-declared fixed-point rungs
(`omega_eligible`) via `beat-sensors.py --list-omega`/`--run-omega`. Sensor capabilities
(`omega_eligible`, `armed_valve_type`, `args_when`, `cadence`/`timeout`) are read by capability, never
by sensor id — consumers work unchanged if an id is renamed. See `docs/IDEAL-FORMS-LEDGER.md` →
IF-SENSOR-REGISTRY.

## Session model cadence and the opening pin

**Session model cadence — open cheap, escalate deliberately.** Interactive sessions OPEN on
Sonnet (the `"model": "sonnet"` pin staged in `docs/keys/fable-guard-settings-snippet.json`,
human-armed via lever `L-FABLE-GUARD-ARM` — an agent never arms settings). The first message —
usually a chaotic brainstorm — is structured into the plan chain *in plan mode on Sonnet*;
`/model opus` is the deliberate escalation for ratifying a genuinely hard plan, and Fable is
never a session default — only an explicit `/model` escalation under a live
`docs/fable-allotment.md` acceptance receipt. After plan approval, drop back (`/model sonnet`)
and execute through the tiered fleet (`.claude/agents/` pins + the `model_selection.py` ladder —
do not restate it here). The harness routes models per *session*, never per message (verified
2026-08-07: hooks cannot switch models), so enforcement is the three real layers: the opening
pin (prevention), `scripts/fable-session-guard.py` at SessionStart (loud warning on Fable
over-cap/unaccepted), and the `claude-workflow-guard.py audit-transcript` beat audit (unaccepted
Fable burn is a violation).

**The opening pin is a default, not a lock — and `/model` overwrites it.** `/model` is manual,
but it is *not* session-scoped: it reports "saved as your default for new sessions" and persists
outside `settings.json` (absent from `~/.claude/settings.json`, `settings.local.json`, and every
plain key of `~/.claude.json` — the store is harness-internal, so no predicate can read it back).
Two consequences, and they run opposite ways. **Cheap:** setting the opening tier costs one
keystroke — `/model sonnet` arms the cadence's prevention layer with no settings paste at all;
the staged snippet's paste is then only needed for the SessionStart guard hook. **Leaky:** one
`/model opus` at any time silently re-arms an expensive default for *every* future session, and
it leaves no artifact a gate can inspect. So prevention is the weakest of the three layers by
construction — detection (SessionStart guard) and the after-the-fact beat audit are what actually
hold the line. Never describe the pin as an enforcement mechanism; it is a good default that a
single keystroke, made months earlier and long forgotten, can invert.
