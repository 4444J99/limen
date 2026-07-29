# Session Stream Cartridges — the iceberg arc, post-Ω

**Authored** 2026-07-29. **Instantiates** the α→ω roadmap approved 2026-07-26
(`.agent-runtime/claude/plans/virtual-greeting-umbrella.md`, worktree `constellation-atlas`), whose
execution stopped on a monthly spend limit at 2026-07-26T13:44Z with **zero phases landed**.

A *cartridge* is a packet injection: a self-contained block pasted into a **cold** session that
carries its own measured ground truth, its own branch, its own boundary, and its own executable
done-predicate. No cartridge assumes the reader saw any prior session, this document, or each other.

> **Status — this document is PROVENANCE, not the operative surface.** It records the measurement
> and the reasoning that produced the stream set, and `institutio/governance/session-streams.yaml`
> cites it for exactly that. It is landed so that citation resolves; a registry whose provenance
> exists only on an unmerged branch cites nothing.
>
> Two successors outrank it, both on `main`:
>
> * the **dependency graph and ready-set** are declared data in `session-streams.yaml` and DERIVED
>   by `scripts/check-session-streams.py --ready` — this document's §"Dependency graph" is the
>   prose it replaced, kept for its measurement, not to be re-read as current;
> * each domain's operative cartridge is `docs/continuations/<id>/intent.md`.
>
> Where a per-stream section here and its `intent.md` differ, **the intent wins** — that is not
> hypothetical: §S8 below asserted a predicate was unbuilt when it had already shipped, and check C
> of that registry caught it. Read the intents; read this for how the set was arrived at.

---

## What measurement says before any stream opens

Verified 2026-07-29 against disk and `origin/main` — not recalled:

| Fact | State |
|---|---|
| Extracts / atoms | 541 extracts · **4,099 atoms** · 8 kinds · 100% `semantic_atoms: done` · 273 streams |
| Declared store root `~/Workspace/_conversations-private` | **does not resolve on disk** |
| Actual corpus location | `/Volumes/T7Recovery/laptop-evacuation/20260727/objects/repo_conversations-private/35ab2f20…/` — intact: `brainstorm-extracts/` (541 `.md`), `homing.yaml`, `convergence-candidates.yaml`, three `*-local-session-memory/`, `federation/`, `state/`, `reports/` |
| Why it moved | the **laptop-evacuation custody lane** (PR #1604, `cli/src/limen/personal_custody.py`, `docs/storage-evacuation-custody-receipts-20260727.jsonl`) — deliberate, receipted, **not drift** |
| Homed atoms | **165** (`IRF-BRC` rows, private `organvm-corpvs-testamentvm` — verified present) |
| Un-homed atoms | **3,658 across 7 kinds** — no declared owner |
| `convergence.yaml` | 12 capabilities · 7 converged · **5 lifting** · 0 unresolved |
| `atom-homing.yaml` / `check-atom-homing.py` / `mirrors.yaml` | **absent from `origin/main`** — Phase α never shipped |
| `docs/plans/2026-07-26-atom-homing-and-lift-correction.md` | **never committed** — Rule #5 still open |
| `his-hand-levers.json` | 62 levers · 11 unresolved (6 `open` + 5 `needs_human`) |

**Atom counts by kind:** decisions 877 · tasks 751 · schema-proposals 676 ·
functionality-to-repeat 518 · vacuums 466 · projects-to-start 441 · questions-unresolved 316 ·
client-offerings 54.

### The correction that reorders the arc

The roadmap's Phase α assumed the corpus sat at its declared root. It does not. The evacuation lane
that moved it was **designed correctly** — `repository-evacuation-inventory-20260727.json` declares
`projection_privacy.contains_private_paths: false`, so private roots are deliberately absent from
the public projection and live in a private inventory required for reclaim.

But `institutio/governance/corpora.yaml` is a **public registry that names that root directly**, and
it was never taught about custody. So the estate now holds the exact defect the roadmap condemned
one domain over: **declared data that misdescribes ground truth**, green because
`check-corpora.py` never asserted a root *resolves*.

**S0 is therefore a new stream and a hard blocker on S1–S5.** It is not "put the files back" — the
evacuation is correct. It is "teach the registry about custody, and make an unresolvable root RED."

### The standing constraint, binding in every stream

Atom **statement text may never enter the public `organvm/limen` tree**
(`redacted: false ⇒ never leaves its store`). Homing is **distillation** — counts, ids,
generalizations — never transfer.

---

## Dependency graph — what opens when

```
        ┌──────────────────────────────────────────────┐
NOW ───►│ S0  corpus-custody        (blocks S1–S5)     │
        │ S6  registry-correction   (independent)      │──► S7  lifts
        └──────────────────────────────────────────────┘
                      │
                      ▼
              S1  homing-spine  (blocks S2–S5)
                      │
        ┌─────────────┼─────────────┬─────────────┐
        ▼             ▼             ▼             ▼
   S2 public     S3 governance  S4 operator   S5 commercial
   distillation   case-law       routing       offerings
                                                    │
                                                    ▼
                                              S8  mint-by-demand
```

**Open in parallel today: S0 and S6.** They share no paths and no registry rows. S1 opens the moment
S0 merges. S2–S5 fan out in parallel once S1 merges — one branch per stream, never one branch per
session. S7 waits on S6 (lifting the wrong seam is worse than not lifting). S8 waits on S5 (it needs
the G1 demand evidence offerings produce).

---

## S0 — corpus custody: teach the registry where the store actually lives

**Branch** `heal/corpora-custody-aware` · **Blocks** S1–S5 · **Open now**

```text
You are running the S0 corpus-custody stream in organvm/limen. Read
docs/plans/2026-07-29-session-stream-cartridges.md §S0 for the full packet; this block is the
injection. Verify every claim below before acting on it — this cartridge is a hypothesis until
you re-measure.

GROUND TRUTH (measured 2026-07-29):
- institutio/governance/corpora.yaml declares store `conversations-private` at
  root "~/Workspace/_conversations-private", remote: none. THAT PATH DOES NOT RESOLVE.
- The store was evacuated 2026-07-27 by the laptop-evacuation custody lane (PR #1604,
  cli/src/limen/personal_custody.py, docs/storage-evacuation-custody-receipts-20260727.jsonl) to:
  /Volumes/T7Recovery/laptop-evacuation/20260727/objects/repo_conversations-private/
  35ab2f20762e212fe846280cb4f85b271a52af03f2f0c4895c9eb1d2ae03fb5a/
  Contents verified intact: brainstorm-extracts/ (541 .md, 4,099 atoms), homing.yaml,
  convergence-candidates.yaml, chatgpt|claude|perplexity-local-session-memory/, federation/,
  state/, reports/.
- THE EVACUATION IS CORRECT. docs/repository-evacuation-inventory-20260727.json declares
  projection_privacy.contains_private_paths: false — private roots are deliberately absent from
  the public projection and live in a private inventory required for reclaim. Do not fight this
  design and do not copy private paths into a public projection that excludes them by contract.
- THE DEFECT is that corpora.yaml is a PUBLIC registry naming that root directly, and it was never
  taught about custody. scripts/check-corpora.py passes checks A-E today because it never asserted
  a root RESOLVES. A registry that green-lights a store nobody can open is the bug.

MISSION: make the store addressable through declared data, and make an unresolvable root RED.
1. Teach corpora.yaml about custody: a store gains a custody state (resident | evacuated) and,
   when evacuated, the declared handle the custody lane already owns — inventory id and object
   digest, NOT a hand-copied volume path if that would contradict the public projection's
   privacy contract. Read personal_custody.py and the receipts JSONL first and reuse ITS
   vocabulary; do not invent a second custody schema (Rule: route through the canonical surface,
   never fork parallel substrate).
2. Add a NEW lettered check F to scripts/check-corpora.py: every store either RESOLVES at its root
   or carries a valid custody record that a reclaim command can act on. It must run STORE-FREE in
   CI (no external volume there) and degrade to declared data — never to a filesystem probe that
   is vacuously true on a runner.
3. Give it a reclaim path a cold session can execute: one command that takes the custody record and
   makes the store resident again, so S1-S5 are unblocked by a documented verb rather than by
   somebody remembering which drive.

BOUNDARY: do not touch atom content. Do not move, rewrite, re-harvest, or re-atomize a single
extract. This stream makes the store FINDABLE; it homes nothing. Do not restore the store into the
public tree.

CONSTRAINTS: fresh branch heal/corpora-custody-aware off updated origin/main; one concern; gate with
scripts/verify-scoped.sh; merge via scripts/merge-policy.sh -> scripts/await-pr.sh <PR#> --merge.
Atom statement text must never enter the public tree. corpora.yaml publishes — keep it PII-clean.

DONE: scripts/check-corpora.py exits 0 with check F present and passing; a store whose root neither
resolves nor carries a valid custody record makes it exit NONZERO — prove this by actually testing
the failure mode, not by reading the code; scripts/check-gates.py green; re-running mutates nothing.
```

---

## S1 — the homing spine: declared data before any homing

**Branch** `feat/atom-homing-registry` · **Blocks** S2–S5 · **Opens when** S0 merges

```text
You are running the S1 homing-spine stream in organvm/limen. Read
docs/plans/2026-07-29-session-stream-cartridges.md §S1; this block is the injection. Re-measure
before trusting any number below.

GROUND TRUTH (measured 2026-07-29): 4,099 atoms in 8 kinds. Exactly ONE kind is homed —
projects-to-start, as 165 IRF-BRC rows in the private organvm-corpvs-testamentvm (verified
present). 3,658 atoms across 7 kinds have NO DECLARED OWNER and rest in a store whose corpora.yaml
entry is remote: none, redacted: false — by declared design it can never be published. Rule #1: a
vacuum is never a resting state. institutio/governance/atom-homing.yaml and
scripts/check-atom-homing.py DO NOT EXIST on origin/main.

PRECONDITION: S0 (heal/corpora-custody-aware) merged, and the store is resident via its reclaim
verb. Without it check C has no census to read.

MISSION: author the homing spine. No atom is homed in this stream — this stream makes homing
DECLARED and PREDICATED so S2-S5 execute against a real contract instead of a convention.

1. institutio/governance/atom-homing.yaml — one row per kind:
   {kind, home, home_class: public|private|broker, unit: cluster|stream|atom,
    admits (the gate an atom must clear to land), verify, consumers, residue_baseline,
    owner_of_record, note}
2. scripts/check-atom-homing.py — lettered checks, modelled on the SHAPE of
   scripts/check-personal-facts.py (123 lines, fail(check,msg)). Read that file first; its own
   rationale is the exact analogue — filling a form needed facts with no store, so the ASK became
   the defect and the registry made an un-homed fact a RED build.
   A schema     — all 8 kinds present, enums valid, no kind without a home
   B resolution — home resolves: in-repo path, declared private-repo path, or a real broker verb
   C completeness — per kind, homed + dispositioned == total, derived from the COMMITTED census
                    (must run store-free in CI, where the private store does not exist)
   D leak       — no atom statement shingle appears anywhere in the public tree. This is the
                  executable form of "redacted: false => never leaves its store"
   E ratchet    — residue counts only shrink, via a baseline file
                  (pattern: institutio/governance/corpus-root-literals-baseline.txt)
   F consumers  — scripts/brainstorm-harvest.py's ATOM_KINDS list READS the registry; a second
                  copy anywhere is a red check
   G anti-fake  — a kind whose population is wholly deferred is RED; each disposition class is
                  bounded and must cite its owner
3. Extend scripts/brainstorm-harvest.py with --census: a STATEMENT-FREE git-tracked artifact
   (counts per kind and per stream, homing ids, disposition tallies). NOT under logs/** — that path
   is gitignored (logs/.gitignore is `*`), which is exactly why the drain's entire product is
   local-only today, a standing Rule #2 breach.
4. Gate row: check-atom-homing in institutio/governance/gates.yaml, ci_job "pr-gate.yml:pr-gate",
   with a note: naming the measured defect (3,658 atoms, no declared owner, remote: none store).
   Adding a gate = ONE registry entry; check-gates.py enforces parity.
5. Rule #5 repair, same branch: commit the α→ω roadmap as
   docs/plans/2026-07-26-atom-homing-and-lift-correction.md. It has been local-only in the
   constellation-atlas worktree since 07-26.

BOUNDARY: zero atoms move. If you find yourself distilling content, you are in the wrong stream —
that is S2-S5.

CONSTRAINTS: fresh branch feat/atom-homing-registry off updated origin/main; scripts/verify-scoped.sh;
merge-policy.sh -> await-pr.sh --merge.

DONE: check-atom-homing.py exits 0 (every kind homed or bounded-dispositioned, leak clean, baseline
monotonic); check-gates.py green; harvest --census re-run mutates nothing.
```

---

## S2 — public distillation: 1,194 atoms into ideal forms and schemas

**Branch** `feat/home-functionality-and-schemas` · **Opens when** S1 merges · **Parallel with** S3–S5

```text
You are running the S2 public-distillation stream in organvm/limen. Read
docs/plans/2026-07-29-session-stream-cartridges.md §S2; this block is the injection.

GROUND TRUTH (measured 2026-07-29): functionality-to-repeat = 518 atoms, schema-proposals = 676
atoms. Both un-homed.

PRECONDITION: S1 merged. institutio/governance/atom-homing.yaml declares both kinds' contracts —
READ THE REGISTRY FIRST and obey it; do not re-derive the home from this prompt. The registry owns
the answer.

MISSION: home both kinds by DISTILLATION.
- functionality-to-repeat 518 -> docs/IDEAL-FORMS-LEDGER.md IF-* entries. An IF entry is a
  GENERALIZATION, never an atom. 518 atoms cluster to a HANDFUL of entries. The ledger currently
  has no validator — author one in this stream: an IF entry must carry its ideal form, a MEASURED
  distance (with the date and method of measurement), and a named predicate.
- schema-proposals 676 -> the registries and specs each one amends; genuine portable contracts to
  spec/. MOST land as PRIVATE candidates in organvm-corpvs-testamentvm, not as public schemas.
  A schema no consumer reads is not a schema; it is a wish with a filename.

THE VOLUME DISCIPLINE IS THE POINT. If your output is proportional to your input, you have
TRANSFERRED rather than distilled — the failure mode this entire arc exists to prevent.
check-atom-homing.py's G-check catches a wholly-deferred kind but NOT a padded ledger. You are the
only guard against padding. A 518-entry ideal-forms ledger is a worse outcome than no homing at all,
because it looks done.

HARD CONSTRAINT: atom statement text may never enter the public organvm/limen tree. Every IF entry
is YOUR generalization in your own words. check-atom-homing.py's D-check (leak: no statement shingle
in the public tree) fails the PR if you paste.

FAN-OUT: partition -> EXPLICITLY TIERED workers -> audit script -> commit. No worker inherits the
session tier (scripts/claude-workflow-guard.py audits this at SessionEnd). Reserve every child via
`limen conduct split` before launching subagents; hidden fanout is rejected.

CONSTRAINTS: fresh branch feat/home-functionality-and-schemas off updated origin/main;
verify-scoped.sh; merge-policy.sh -> await-pr.sh --merge.

DONE: both kinds show homed + dispositioned == total in check-atom-homing.py check C; the residue
baseline SHRANK; leak check clean; the new IDEAL-FORMS-LEDGER validator exits 0 and is gate-wired.
```

---

## S3 — governance case law: 1,343 atoms into precedents and counted vacuums

**Branch** `feat/home-decisions-and-vacuums` · **Opens when** S1 merges · **Parallel with** S2, S4, S5

```text
You are running the S3 governance-case-law stream in organvm/limen. Read
docs/plans/2026-07-29-session-stream-cartridges.md §S3; this block is the injection.

GROUND TRUTH (measured 2026-07-29): decisions = 877 atoms, vacuums = 466 atoms. Both un-homed.
institutio/governance/convergence.yaml today: 12 capabilities, 7 converged, 5 lifting, ZERO
unresolved rows.

PRECONDITION: S1 merged. atom-homing.yaml declares both contracts — read the registry first.

MISSION: home both kinds.
- decisions 877 -> governance case law in censor/precedents.jsonl for the ones that BIND FUTURE
  BEHAVIOR; stream-local design decisions -> private IRF in organvm-corpvs-testamentvm.
  PRECEDENTS STAY CURATED. 877 rows destroys the file's function: a precedent is consulted, and a
  corpus nobody can read is consulted by nobody. Expect single digits to low double digits to reach
  precedent status. The rest are IRF, or they are nothing — and "nothing, with a reason" is a valid
  bounded disposition under the G-check.
- vacuums 466 -> capability-shaped ones become convergence.yaml `unresolved` rows (owner: null,
  counted LOUDLY per Rule #1); the rest become private IRF-VAC rows.
  A registry asserting "0 unresolved" while 466 vacuum atoms sit un-homed is declared data
  contradicting measurement — the exact defect class S6 is correcting one file over. Do not
  reproduce it here.

COUNTED VACUUMS, NOT PROSE. An unresolved row NAMES a capability with no chosen owner; it is not a
paragraph of description. scripts/check-convergence.py must stay green with the new rows, and its
B-check rejects prose owners — do not add one.

HARD CONSTRAINT: atom statement text may never enter the public organvm/limen tree.
censor/precedents.jsonl PUBLISHES: a precedent is YOUR restatement of the binding rule, never the
atom. The D-check fails the PR on a pasted shingle.

FAN-OUT: partition -> explicitly tiered workers -> audit script -> commit. Reserve children via
`limen conduct split`. Never let a worker inherit the session tier.

CONSTRAINTS: fresh branch feat/home-decisions-and-vacuums off updated origin/main; verify-scoped.sh;
merge-policy.sh -> await-pr.sh --merge.

DONE: check-atom-homing.py check C shows both kinds fully homed or bounded-dispositioned;
check-convergence.py green WITH the new unresolved rows present; residue baseline shrank; leak
clean. State the precedent count you added and justify it — a large number is a defect to explain,
not an achievement to report.
```

---

## S4 — operator routing: 1,067 atoms without handing him a list

**Branch** `feat/home-questions-and-tasks` · **Opens when** S1 merges · **Parallel with** S2, S3, S5

```text
You are running the S4 operator-routing stream in organvm/limen. Read
docs/plans/2026-07-29-session-stream-cartridges.md §S4; this block is the injection.

GROUND TRUTH (measured 2026-07-29): questions-unresolved = 316 atoms, tasks = 751 atoms. Both
un-homed. his-hand-levers.json currently holds 62 levers, 11 of them unresolved (6 `open`,
5 `needs_human`).

PRECONDITION: S1 merged. atom-homing.yaml declares both contracts — read the registry first.

MISSION: home both kinds WITHOUT enlarging the operator's burden. This stream's success metric is
INVERTED from every other stream: routing 1,067 atoms at the human is the failure mode, not the
deliverable.
- questions-unresolved 316 -> ONLY the genuinely human-gated ones become levers in
  his-hand-levers.json (each with an int `issue`). Everything else is design work -> private IRF.
  The charter is explicit: a closeout that hands him a list HAS FAILED even when every item is
  technically homed. If this stream triples the lever registry, it has failed. Most of these 316
  are questions the SYSTEM can answer by querying a registry it already owns.
- tasks 751 -> demand-gated `limen conduct submit --packet`. NEVER bulk-submit. The board's signal
  IS the asset; 751 synthetic tasks destroy it. A task is submitted when something demands it now,
  not because it was found in a corpus.

THE TEST for every atom in this stream: can the system resolve this by reading a registry it
already owns — his-hand-levers.json, organ-ladder.json, pillars.yaml, tasks.yaml,
censor/precedents.jsonl, convergence.yaml, gates.yaml? If yes, it is NOT a lever and NOT a task.
It is ANSWERED, and the answer is the homing. (Precedent: the "8 vs 10 organs" question was asked
at the operator while organ-ladder.json held the count.)

HARD CONSTRAINT: his-hand-levers.json PUBLISHES and must stay PII-clean —
scripts/no-tasks-on-me.sh enforces it. Atom statement text may never enter the public tree.
CREDENTIAL/SECRET/TOKEN/LOGIN/ENV atoms DO NOT GO HERE: they go to the credential organ
(scripts/creds-hydrate.py DEFAULT_MAP) and the Wall, organvm/limen#320. Never recite a credential
in chat or encode one in a lever.

CONSTRAINTS: fresh branch feat/home-questions-and-tasks off updated origin/main; verify-scoped.sh;
merge-policy.sh -> await-pr.sh --merge.

DONE: check-atom-homing.py check C shows both kinds fully homed or bounded-dispositioned;
scripts/no-tasks-on-me.sh exits 0; scripts/credential-wall.py --check exits 0; and you report the
unresolved-lever count before and after (11 -> N) with a one-line justification per addition.
```

---

## S5 — commercial offerings: 54 atoms into the funnel

**Branch** `feat/home-client-offerings` · **Opens when** S1 merges · **Feeds** S8 · **Parallel with** S2–S4

```text
You are running the S5 commercial-offerings stream in organvm/limen. Read
docs/plans/2026-07-29-session-stream-cartridges.md §S5; this block is the injection.

GROUND TRUTH (measured 2026-07-29): client-offerings = 54 atoms — the smallest kind and the only
one with direct revenue consequence. Un-homed. The constellation program already exists at
organs/consulting/constellation/; constellation-streams.py::find_echoes is a CONVERGED owner in
institutio/governance/convergence.yaml. DO NOT BUILD A SECOND ONE — a new engine where an owner
exists is a regression ("never build the 7th").

PRECONDITION: S1 merged. atom-homing.yaml declares the contract — read the registry first.

MISSION: home all 54 into the organs/consulting/ funnel and the constellation register, and emit the
demand evidence S8 consumes.
1. Each offering distills to a funnel entry with a real stage on the ladder
   idea -> dossier -> building -> mvp -> live -> funnelized, and a tier (T1/T2/T3).
2. The constellation public register is FIRST-NAME SLUGS ONLY — surnames are mechanically banned by
   the program's Rule #2, and the private overlay is ARCA-sealed. Verify the ban is enforced by a
   PREDICATE, not by your carefulness. If no predicate exists, that absence is the first thing you
   ship in this stream.
3. Emit the G1 demand-evidence reference S8's repo-genesis gate requires: an extract path, dossier
   path, or CONST-/IRF id per offering. "I want it" is not evidence.
4. review-before-rails holds: an offering earns a rail by REVIEWED DEMAND, never by enthusiasm.

WHY 54 ATOMS GET THEIR OWN STREAM: it is the only kind whose homing produces revenue surface, and
it is the sole input to S8's mint gate. Bundled into a bulk homing pass it gets buried under 877
decisions and never resurfaces.

HARD CONSTRAINT: atom statement text may never enter the public organvm/limen tree. Surname-free,
PII-free — organs/consulting/ and the constellation register both publish. scripts/no-tasks-on-me.sh
enforces PII-cleanliness.

CONSTRAINTS: fresh branch feat/home-client-offerings off updated origin/main; verify-scoped.sh;
merge-policy.sh -> await-pr.sh --merge.

DONE: check-atom-homing.py check C shows client-offerings fully homed; the surname ban has a
PASSING predicate you can point at; every offering carries a G1-admissible demand-evidence
reference; scripts/no-tasks-on-me.sh exits 0.
```

---

## S6 — registry correction: make convergence.yaml describe the code it names

**Branch** `heal/convergence-rows-match-ground-truth` · **Blocks** S7 · **Open now, parallel with S0**

```text
You are running the S6 registry-correction stream in organvm/limen. Read
docs/plans/2026-07-29-session-stream-cartridges.md §S6; this block is the injection.

GROUND TRUTH: institutio/governance/convergence.yaml on origin/main holds 12 capabilities —
7 converged, 5 lifting, 0 unresolved. FOUR of its claims were measured FALSE on 2026-07-26.
Declared data that misdescribes ground truth is WORSE than a vacuum: it routes work at the wrong
target. RE-VERIFY each finding against the code before rewriting a row — this cartridge is a
hypothesis, and a correction made from a stale hypothesis is the same defect wearing a new hat.

THE FOUR CORRECTIONS:
1. worker-toolkit — the row names no shared substrate, but organvm/payrail ALREADY EXISTS as a
   deployed shared money-rail Worker, and 4 of 6 tenants call it through a BYTE-IDENTICAL
   copy-pasted payrailFetch() + hmacHex() block. The lift is not "extract a toolkit"; it is "turn
   an existing copy-paste into an import." trendpulse is the true outlier (Lemon Squeezy, no
   payrail). All six are KV-only, no D1. Add payrail as the real seam.
2. data-export — the row claims "near-identical copies". FALSE: real diffs are 130-189 lines with
   ZERO shared function names; each generates different domain artifacts. Only two helpers are
   genuinely duplicated (write_json_artifact, load_seed_json), plus a SEED_DIR path-depth
   divergence that is a LIVE REGRESSION RISK. Rewrite the row to exactly that, and record the
   regression risk where a predicate can see it.
3. text-quality-scoring — essay-pipeline/validator.py is a FRONTMATTER SCHEMA VALIDATOR, not a
   quality scorer. The four "encodings" are structurally disjoint: this is a translation layer, not
   code reuse. Its editorial-standards dependency HAS NO LOCAL CLONE. The row must say so.
4. docs/convergence/learning-engine.md claims mirror drift "is currently caught only by a manual
   verify.sh". FALSE: the actual verify.sh is a FERPA/secrets guardrail. NOTHING checks mirror
   drift. That is a VACUUM, not a manual process — and a doc that describes a nonexistent control
   is how a vacuum hides.

ALSO RESOLVE: check-convergence.py's B-check emits advisories for prose owners
("agon (plugin only)", "~/Workspace/daily-engine"); owner organvm/adaptive-personal-syllabus has no
local clone — it exists only as an edu-organism mirror. Turn each into a verifiable reference.

ENCODE THE MIRROR VACUUM AS DECLARED DATA: institutio/governance/mirrors.yaml +
scripts/check-mirrors.py, rows shaped {path, origin_repo, direction, last_synced_sha} — the same
shape that converged corpus-resolution. Register it as ONE row in gates.yaml.

BOUNDARY: this stream corrects DESCRIPTIONS and adds the mirror predicate. It lifts NO code — that
is S7, and S7 is blocked on this landing.

CONSTRAINTS: fresh branch heal/convergence-rows-match-ground-truth off updated origin/main;
verify-scoped.sh; merge-policy.sh -> await-pr.sh --merge.

DONE: check-convergence.py green with ZERO prose-owner advisories; check-mirrors.py exists, is
gate-registered, and exits 0; check-gates.py green; and every rewritten row cites a measurement a
reader can reproduce from the command you name in the row's note.
```

---

## S7 — the smallest real lifts

**Branch** one per lift, sequential · **Opens when** S6 merges

```text
You are running the S7 lifts stream in organvm/limen. Read
docs/plans/2026-07-29-session-stream-cartridges.md §S7; this block is the injection.

PRECONDITION: S6 (heal/convergence-rows-match-ground-truth) MUST be merged. Lifting against the
uncorrected rows lifts the wrong seam — specifically, it would "extract a toolkit" that
organvm/payrail already is, and unify an export_all() that shares no function names. Verify
convergence.yaml carries the corrected worker-toolkit and data-export rows before writing a line.

THE DE-RISKING FACT (measured 2026-07-26 — re-verify): NONE of the Worker repos deploys on merge;
there is no `wrangler deploy` in any of their CI. A merged lift is therefore a REVIEWABLE CODE
CHANGE and the deploy stays a human action. That is what makes these safe to land.

EXECUTE, ONE BRANCH EACH, IN THIS ORDER:
1. data-export — extract ONLY the two genuinely duplicated helpers (write_json_artifact,
   load_seed_json) and fix the SEED_DIR path-depth divergence. Convert reading-group-curriculum
   first as the proof. DO NOT unify export_all() — the diffs are 130-189 lines with zero shared
   function names; unifying it is a FALSE LIFT, the precise error the corrected row exists to stop.
2. worker-toolkit — a shared payrailFetch()/hmacHex() module against organvm/payrail; convert ONE
   tenant. Its existing vitest suite is the predicate: RUN it, do not assert it.
3. voice-infrastructure — point one sign-signal synth call at vox's POST /tts.
4. text-quality-scoring — DEFER with a RATCHETED row. editorial-standards is unavailable locally and
   the four encodings share no data shape. A deferral WITH a shrinking baseline is a homed item; a
   deferral without one is a vacuum wearing a disposition.

IF-AMALGAMATION HOLDS THROUGHOUT: the fleet must amalgamate faster than it spawns. This stream is
the amalgamation side of that ledger, and S8's minting is gated by it.

BOUNDARY: one lift per branch, one concern per branch — never batch two lifts into one PR. No
wrangler deploy from this session; deploy stays a human action.

CONSTRAINTS: each branch off updated origin/main; verify-scoped.sh per branch; merge-policy.sh ->
await-pr.sh --merge. web/worker merges do not auto-deploy, but any website-sensitive diff requires
the FULL green rollup first — merging that is the deploy.

DONE per lift: the converted consumer's own test suite passes; check-convergence.py green; the
capability's row moved lifting -> converged, or its ratchet shrank. All four dispositioned, none
left silently in `lifting`.
```

---

## S8 — mint by demand

**Branch** `feat/repo-genesis-by-demand` · **Opens when** S5 merges

```text
You are running the S8 mint-by-demand stream in organvm/limen. Read
docs/plans/2026-07-29-session-stream-cartridges.md §S8; this block is the injection.

PRECONDITION: S5 (feat/home-client-offerings) merged — its distillations, plus the 165 IRF-BRC rows
in private organvm-corpvs-testamentvm, are the demand evidence this stream consumes. Verify they
exist before minting anything.

THE DOCTRINE THAT SHAPES THIS STREAM: a repo is NOT the unit of a brainstorm. The estate measured
149 repos minted from a SINGLE export date against ~550 threads in CCE, and IF-AMALGAMATION records
the result — duplicates accreting faster than they merge, a direct regression against a declared
ideal. The unit of a brainstorm is an ATOM in the extract registry (IF-LEARNING-ENGINE's
subject/cartridge contract, generalized). A repo is minted ONLY when an atom needs what only a repo
provides: its own deploy surface, its own collaborator grant, or its own visibility boundary.

CORRECTION — this block asserted the gate did not exist, and that was WRONG. It was caught by
scripts/check-session-streams.py check C on 2026-07-29 (the anti-fake rung: a stream may not claim
to build a predicate that is already on main). Ground truth: scripts/repo-genesis.py EXISTS on
origin/main, landed in PR #1535, with four shipped gates — and they are NOT the four this block
named:
  G1 evidence  gate_evidence  non-empty demand-evidence ref (extract path, dossier path, CONST-/IRF id)
  G2 name      gate_name      scripts/nomenclator.py --check <name> clears the naming canon
  G3 class     gate_class     the name resolves to a declared estate.yaml class by glob (never class J)
  G4 seed      gate_seed      at least one brainstorm extract or seed doc — an empty repo is a vacuum

MISSION: close the DEMAND half. The shipped four check that a mint is well-FORMED (named right,
classed right, seeded, with *some* evidence attached). None checks that the repo is WARRANTED — that
is the gap 149 repos walked through. Add three predicates in the tool's existing gate_* idiom:
  necessity        — names WHICH repo-only affordance is required (deploy surface / collaborator
                     grant / visibility boundary), from a closed enum. Absent one, the correct
                     output is an atom, not a repo, and the gate says so.
  non-duplication  — query convergence.yaml; if a converged owner already covers the capability,
                     refuse. A mint that duplicates a converged owner IS the 7th engine.
  amalgamation     — IF-AMALGAMATION: mints must not outpace lifts. Read the ledger; if the fleet
                     amalgamates slower than it spawns, REFUSE regardless of every other gate. This
                     is the one that would have stopped the 149.

Keep the shipped four intact and their NUMBERING STABLE — renumbering gates that already shipped
breaks every receipt citing them. Add the new checks alongside, named, not renumbered.

The operative, corrected cartridge for this domain is docs/continuations/s8-mint-by-demand/intent.md
on main; where it and this section differ, the intent wins.

Visibility is NOT a judgment call and must not be asked: institutio/governance/estate.yaml glob
classes assign every organvm/** repo a class automatically. A genuine exception is a repo_override
row, not a decision made in chat.

BOUNDARY: estate rows land BY PR. Mass repo creation stays a human-gated lever — this stream ships
the GATE and mints only what the gate clears, one at a time.

CONSTRAINTS: fresh branch feat/repo-genesis-by-demand off updated origin/main; verify-scoped.sh;
merge-policy.sh -> await-pr.sh --merge.

DONE: repo-genesis.py exists with G1-G4 as executable predicates; it REFUSES a synthetic
insufficient-evidence request in a test — prove the refusal path, not just the mint path; every repo
it minted carries an estate.yaml row landed by PR; IF-AMALGAMATION still holds after the stream.
```

---

## Ω — the fixed point across all nine streams

The arc is done when these are simultaneously true, executably — not when the streams are closed:

1. `scripts/check-atom-homing.py` exits 0 — every kind homed or bounded-dispositioned, leak check
   clean, residue baseline monotonic.
2. `check-corpora.py` (with S0's F-check), `check-convergence.py`, `check-mirrors.py`, and
   `check-gates.py` all green — and **no registry row contradicts a reproducible measurement**.
3. Every branch merged through `merge-policy.sh` CLEARED; `verify-scoped.sh` green per branch.
4. Re-running `brainstorm-harvest.py --census` plus the homing pass **mutates nothing**.
5. `scripts/no-tasks-on-me.sh` and `scripts/credential-wall.py --check` both exit 0.

Then **one** `scripts/verify-whole.sh` at the end of the arc — not once per stream.

**Standing doctrine, unchanged:** *harvest everything, preserve every variant, converge downstream.*
