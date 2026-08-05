# S8 — Mint by demand: close the demand half of the genesis gate

## Precondition

**`s5-commercial-offerings` merged** — its distillations, plus the 165 `IRF-BRC` rows in the private
`organvm-corpvs-testamentvm`, are the demand evidence this domain consumes. **Verify they exist
before minting anything.**

## Correction to prior planning — read this first

An earlier plan asserted that this domain must *build* `scripts/repo-genesis.py` with gates
`G1 evidence / G2 necessity / G3 non-duplication / G4 amalgamation`. **That was wrong, and was caught
by `scripts/check-session-streams.py` check C on 2026-07-29.**

Ground truth: **`scripts/repo-genesis.py` already exists and is on `origin/main`** (landed in
PR #1535). Its four shipped gates are:

| gate | function | what it actually checks |
|---|---|---|
| G1 evidence | `gate_evidence` | non-empty demand-evidence ref — an extract path, dossier path, or `CONST-`/`IRF` id |
| G2 name | `gate_name` | `scripts/nomenclator.py --check <name>` clears the naming canon |
| G3 class | `gate_class` | the name resolves to a declared `estate.yaml` class by glob (never class J) |
| G4 seed | `gate_seed` | at least one brainstorm extract or seed doc — an empty repo is a vacuum, not a genesis |

**Re-read the file before doing anything.** Do not trust this table either; it is a measurement with
a date on it.

## The doctrine that shapes this domain

**A repo is not the unit of a brainstorm.** The estate measured **149 repos minted from a single
export date** against ~550 threads in CCE, and IF-AMALGAMATION records the result: duplicates
accreting faster than they merge — a direct regression against a declared ideal.

The unit of a brainstorm is an **atom in the extract registry** (IF-LEARNING-ENGINE's
subject/cartridge contract, generalized). A repo is minted **only** when an atom needs what only a
repo provides: its own deploy surface, its own collaborator grant, or its own visibility boundary.

## Objective — close the demand half

The shipped gates check that a mint is **well-formed** (named right, classed right, seeded, with
*some* evidence attached). **None of them checks that the repo is warranted.** That is the gap 149
repos walked through. Add the three missing predicates, in the tool's existing `gate_*` idiom:

1. **necessity** — the request must name **which** repo-only affordance is required (deploy surface /
   collaborator grant / visibility boundary), from a closed enum. Absent one, the correct output is
   an atom, not a repo, and the gate says so.
2. **non-duplication** — query `institutio/governance/convergence.yaml`: if a converged owner already
   covers this capability, refuse. A mint that duplicates a converged owner **is** the 7th engine.
3. **amalgamation** — IF-AMALGAMATION as an executable predicate: mints must not outpace lifts. Read
   the ledger; if the fleet is amalgamating slower than it spawns, **refuse regardless of every other
   gate**. This is the one that would have stopped the 149.

Keep the existing four intact and their numbering stable — renumbering shipped gates breaks every
receipt that cites them. Add the new ones as named checks alongside.

**Visibility is not a judgment call and must not be asked:** `estate.yaml` glob classes assign every
`organvm/**` repo a class automatically (that is exactly what `gate_class` already enforces). A
genuine exception is a `repo_override` row, not a decision made in chat.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible work: authoring the new gates, their tests,
  and their registry rows.
- Retained gates: destructive, credential, paid-spend, **public-send**, runtime/host mutation.
- **Estate rows land by PR.** Mass repo creation stays a human-gated lever — this domain hardens the
  **gate**, and mints only what the gate clears, one at a time.
- `repo-genesis.py` mints for real without `--dry-run`. **Use `--dry-run` for every evaluation in
  this domain** unless a specific mint has cleared all gates and you intend it.

## Fan-out

At most **2** children, only via `limen conduct split <parent_run> --packet`. Never nest a git
worktree inside this one — the reclaim organ sweeps roots, so a nested worktree leaks. Tier every
child explicitly; no worker inherits this session's model.

## Constraints

Fresh branch `feat/repo-genesis-demand-gates` off updated `origin/main`, one concern.
`scripts/verify-scoped.sh`; `merge-policy.sh` → `await-pr.sh --merge`. **Claim the settlement with an anchored trailer in the merge commit message** — a line at
column 0 reading `Settles: s8-mint-by-demand`. The STREAMS registry derives this domain's settled
state from that claim, and *only* from it: an unanchored mention no longer counts (it once
settled `s10-axis-coverage` off a docs commit that merely named it). The claiming commit must
also change something outside the registry and `docs/{plans,continuations}/` — bookkeeping
records an outcome, it cannot produce one.

## Done

The three new gates exist as **executable predicates** wired into `repo-genesis.py`; the tool
**refuses** a synthetic request that is well-formed but unwarranted — **prove the refusal path, not
just the mint path**; every repo minted under it carries an `estate.yaml` row landed by PR;
IF-AMALGAMATION still holds after the domain closes.
