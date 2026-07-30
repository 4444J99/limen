# Docs belong with their subject — the limen docs/ export program

**Date:** 2026-07-30 · **Method:** 65-agent subject-ownership audit (32 classifiers over all 355
files in `docs/`, each paired with an independent skeptic told to refute it; 1 synthesis pass).
213 dispositions, **48 overturned in verification**. Registry: `institutio/governance/docs-exports.yaml`.

## The directive

> "most of those docs -- if not all -- do not belong in limen; they belong in their respective
> repositories wherever those might be"

The earlier pass (PR #1684) rehomed 59 files into better *subdirectories* and shipped the
`check-docs-manifest` gate. That was the wrong altitude: the sprawl axis is **repo-level**. A doc
filed in a beautiful limen subdir is still misfiled if its subject lives in another repository.

## What the audit found

| Disposition | Count | Meaning |
|---|---|---|
| STAY | 140 | limen's own subject: its CLI, gates, registries, protocols, organs, and the operating records its own machinery reads at an exact path |
| EXPORT | 69 | subject is owned by another repo -- the estate governance graph, a product repo, or the private personal estate |
| DELETE | 4 | superseded by a live machine surface; git history is the archive |

So the operator's "most if not all" is directionally right about the *loose* files, but a majority
of `docs/` is genuinely limen's -- overwhelmingly because a script, test, or registry pins it at an
exact path. **Bindings, not topic, are what keep a doc here.**

## Corrections the verification pass produced

Three claims were walked back on inspection, and they matter because each would have been an
overstated alarm:

1. **`docs/health-office/reference/` is not personal medical records.** Every file declares
   "general clinical reference - names no patient". The real (narrower) issue is that the topic
   *selection* is inferential about whoever the office serves.
2. **`docs/keys/anthony-padavano-gpg.asc` is a PUBLIC key block** -- zero private-key material.
   Publishing public keys is what public keys are for.
3. **The identity organ leaks no identifiers.** `institutio/governance/personal-facts.yaml` holds
   zero literal values (only `op://` pointers, which are addresses, not secrets) and the store
   `_life-private/` is not tracked in limen. What is disclosed is schema field names, plus
   `scripts/fill-phi-jewishboard.py` naming a specific healthcare-adjacent provider.

One finding went the other way and is real: **a partial card identifier (last four) plus the
issuing bank** appears in ~15 files including `START-HERE.md` and several registries. Last-4 is not
a usable credential, but it is personal-financial detail on a public front door. It is a shorthand
token, so the fix is to generalize it at the source rather than move any file.

## Two decisions that are the operator's, not the system's

1. **The personal tranches (T1/T2, ~17 files: health office, identity-organ design, the personal
   revenue/recovery gate, first-dollar runbook, student-email grounding, his-hand registry).**
   `organvm/domus` (private) is the recommended destination, but relocating health, identity, and
   personal-financial material is a judgment call. The rows are filed; no agent executes them.
2. **The `card-NNNN` token generalization** across `START-HERE.md`, `his-hand-levers.json`,
   `tasks.yaml`, `organ-ladder.json`, and the `organs/financial/` family. Several are protected
   registries and `tasks.yaml` is TABVLARIVS-owned, so this needs its owner, not a sweep.

## Caveat that applies to every export

Removing a file from HEAD does **not** purge it from limen's git history. These moves stop future
exposure; a history rewrite would need force-push and is a separate, human-gated decision.

---

## 1. Headline

**273 of 355 files in `docs/` (≈77%) genuinely belong to limen — 79 export to five destinations, 3 delete, and 13 of the exports (plus one file that stays) are active PII/confidential leaks sitting in a world-readable repo right now.**

---

## 2. Export program, by destination

### → `organvm/domus:docs/` (PRIVATE) — 24 files
Personal life, health, identity, personal-financial, teaching, and confidential pricing material. **This is the leak destination — ship it first.**

| Files | Rationale | Patch needed? |
|---|---|---|
| `docs/architecture/identity-organ.md` | Personal identity/PHI organ design (SSN/DOB/address + a named health-adjacent provider) | **No** (doc unbound) — but see escalation below |
| `docs/health-office/CHARTER.md` + `docs/health-office/reference/` (6 files) | Personal medical office + clinical reference set whose topic selection discloses conditions/medication | **Yes** — 7 citation strings in `scripts/health-organ.py`; `docs-manifest.yaml` already declares this exact target |
| `docs/architecture/his-hand-registry.md` | Cross-life punch list: named bank fraud hold, course/section identifiers | No |
| `docs/student-email-reply-grounding.md` | FERPA/student material, course identifiers, instructor reply template | **Yes** — `scripts/check-student-email-grounding.py` reads it as a predicate; wired via `check-agent-docs.py`; cited in CLAUDE.md |
| `docs/runbooks/first-dollar-runbook.md` | Personal payout/KYC/bank enrollment for a different product | No |
| `docs/reviews/deep-history-2022-2026.md` | Personal financial-crisis/health-adjacent narrative + named teaching engagement | Citations: `organs/artist/chambers/etceter4-revival.yaml`, `tasks.yaml` ×2 |
| `docs/inbound-magnet-system.md` | Confidential pricing anchors + negotiation posture the doc itself marks "never published" | **Yes** — `scripts/generate-positioning.py`, `positioning-seeds.json` |
| `docs/AUG1-10K-GATE.md` | Personal recovery-contingent revenue gate + personal ramp plan | Comment/footer strings in `scripts/aug1-gate.sh`, `aug1-view.py` |
| `docs/OFFSITE-DURABILITY-PROPOSAL-2026-06-19.md` | Personal drive/keychain/identity backup plan + card-fraud detail | One row in `vltima-prior-excavations.py` |
| `docs/plans/2026-07-29-custody-dual-estate-semver-lineage.md` | Estate custody doctrine that maps named individuals to private repos and money/seat economics (see conflicts) | `his-hand-levers.json`, `institutio/github/estate.yaml`, `validate-constellation.py` (prose citations) |
| `docs/estate-custody-primitives.md`, `docs/estate-custody-implementation-receipts.json` | Personal laptop/SSD/photo custody doctrine + receipts | **Yes** — `scripts/always-working.py` constants, `cli/tests/test_always_working.py`, `tasks.yaml` `receipt_target` |
| `docs/QUICKEN-RESIDUE.md` | Personal needs-human atoms (fitness, teaching go-live, personal logins) | **Yes, base not output** — `scripts/quicken.py` `RESIDUE_OUT` regenerates it into the public repo unless repointed |
| `docs/photos-universe-duplicate-proof-2026-06-29.json`, `docs/photos-universe-sorting-2026-06-30.md` | Personal Photos-library work; generated into a *different* worktree, stray copies here | No (fix a wrong `docs-manifest.yaml` annotation) |
| `docs/storage-creep-2026-07-05.md` | Personal-machine storage hygiene incl. Messages/Photos/Mail no-delete decisions | No (zero bindings) |
| `docs/life-office/CHARTER.md` | Personal digital-estate/accounts organ charter | One docstring in `scripts/life-organ.py`; `docs-manifest.yaml` already declares the target |
| `docs/keys/anthony-padavano-gpg.asc` | Operator's personal comms identity (public key, but personal) | No |

### → `organvm/portvs:governance/records/` — 40 files
Whole-GitHub-estate census/governance/fleet sweeps. Subject is ~300 repos, not limen.

- **Estate census/records (root, 10):** `estate-closeout-audit.md`, `github-pr-debt-ledger.json`, `github-actions-usage.json`, `github-contribution-balance.md`, `github-estate-runbook.md`, `repository-evacuation-inventory-20260727.json`, `agent-reconstruction-review.md`, `agent-session-full-stack-review.md`, `prompt-priority-map.md`, `prompt-packet-resolution-receipts.json`
- **Estate PR-labeling sweep receipts (8):** `docs/receipts/pr-lifecycle-estate-*.json` (7, schema `limen.pr_lifecycle_estate_receipt.v1`, 129/50-repo denominators) + `docs/receipts/seo-live-facts-receipt-20260725.json` (310-repo README/SEO audit; **no** code binding despite the earlier claim)
- **Fleet reviews (20):** `docs/reviews/EXCAVATION-MAP-2026-06-25.md`, `agent-agy-antigravity-review.md`, `agent-claude-review.md`, `agent-opencode-review.md`, `agent-session-audit-rollup.md`, `retro-2026-06-24--2026-07-08.md`, `session-lifecycle-drain-queue-2026-06-27.md`, `session-screenshot-intake-2026-06-27.md`, `storage-pulse-2026-07-06.md`, `worktree-lifecycle-2026-06-27.md`, `worktree-reduction-2026-06-30.md`, and `seven-agent-whole-estate-2026-07-19/` (9 files — move as one unit so `collect.py`/`reconcile.py`/`build_report.py` still run together)
- **Plans/consolidation (2):** `docs/plans/2026-07-30-portvs-astra-consolidation.md`, `docs/consolidation/SESSION-2026-06-28.md`

**Patches:** `github-actions-usage.json` needs `institutio/governance/sensors.yaml` repointed at a narrow limen billing canary (only one field of that file is limen-scoped). `github-contribution-balance.md` needs `organs/contributions/ESTATE.yaml` + a test assertion. `github-estate-runbook.md` has 4 pins (`his-hand-levers.json`, `institutio/github/estate.yaml`, `sensors.yaml`, `setup-rulesets.py`). `retro-…md` has 13 `tasks.yaml` context citations + `censor/precedents.jsonl` + `EVERY-ASK-LEDGER.md`. The four `vltima`-registered census docs need their `scripts/vltima-prior-excavations.py` rows updated — and their generator scripts are the honest co-migration candidates.

### → product repos — 15 files
`docs/positioning/` is not one owner; it splits.

| Destination | Files |
|---|---|
| `4444J99/4444J99` (profile surface) | `_frontdoor.md`, `_method.md`, `_conductor.md`, `_corpus.md`, `_governance.md`, `_life-os.md`, `_prompt-hand.md` — personal-brand/hiring pitches; `_method.md` and `_frontdoor.md` name this destination in their own text |
| `organvm/universal-mail--automation` | `docs/positioning/universal-mail--automation.md`; `docs/his-hand-registry-mail-a290329e.md` (`his-hand-levers.json` already asserts the mail organ owns this record) |
| `organvm/a-i-chat--exporter` | `docs/positioning/a-i-chat--exporter.md` |
| `4444J99/peer-audited--behavioral-blockchain` | `docs/positioning/peer-audited--behavioral-blockchain.md` (repo moved to the personal account 2026-07-30; links in the file are stale) |
| `organvm/portfolio` | `docs/positioning/portfolio.md` |
| `organvm/public-record-data-scrapper` | `docs/positioning/public-record-data-scrapper.md` |
| `4444J99/micro-tato:docs/lanes/` | `docs/lanes/rob-game.md` (Godot game lane, other repo's tooling) |
| `organvm/my-knowledge-base:docs/plans/` | `docs/PLAN-LONG-AND-WIDE.md` (self-marked SUPERSEDED; personal corpus program) |

**Patch:** positioning is *generated*. A `git mv` alone is wrong — `scripts/generate-positioning.py` + `positioning-seeds.json` must emit per-repo, and `his-hand-levers.json` (`L-POSITIONING-ACTIVATE`) + two `tasks.yaml` pins on `_frontdoor.md` need repointing. The `decorum-surfaces.yaml` `docs/positioning/*.md` glob degrades gracefully.

### DELETE — 3 files + 1 section
- `docs/repo-surface-ledger.md` — 300-repo census, machine-regenerable, **and leaking** (named private individual + a student/teaching topic slug). Copying it to public portvs would relocate the leak, not cure it. Delete; regenerate redacted if portvs ever wants a census. *Patch:* `always-working.py`, `vltima-prior-excavations.py`, `tasks.yaml`.
- `docs/needs-human-prep/NEEDS-HUMAN-CHECKLIST-2026-06-19.md` — headline claim (Cloudflare/wrangler blocking 16 of 19) was disproven 2026-07-01; remaining items live in `tasks.yaml`. Fully superseded.
- `docs/needs-human-prep/LIMEN-072-branch-protection-commands.sh` — dead dump from a `registry-v2.json` that no longer exists; superseded by `institutio/github/estate.yaml` + `scripts/setup-rulesets.py` + lever `L-BRANCH-PROTECTION`.
- `docs/runbooks/workstream-kickstart.md` lines ~94–130 — stale cross-repo session leads; strip in place, keep the protocol body and fold the one "Limen lifecycle" bullet into `## Pattern`. *(Both `needs-human-prep` deletes require removing the directory row from `docs-manifest.yaml`.)*

---

## 3. Leak triage (PUBLIC repo — priority section)

| # | File(s) | Category (not content) | Action |
|---|---|---|---|
| 1 | `docs/architecture/identity-organ.md` **+ `scripts/identity.py`, `scripts/fill-phi-jewishboard.py`, `scripts/identity.schema.json`, `institutio/governance/personal-facts.yaml`** | Personal identity data architecture (national-ID/DOB/address class) + a PHI records-request flow naming a real healthcare-adjacent provider | Export doc → domus **and escalate the four non-doc files**; moving the doc alone leaves the live implementation public |
| 2 | `docs/health-office/reference/` (6 files) | Medical/psychiatric — medication + symptom correlation stated explicitly, not merely inferable | → domus, urgent; a lever already warns the daemon will auto-publish this tree |
| 3 | `docs/student-email-reply-grounding.md` | Student/teaching PII (FERPA), course/section identifiers, quarantine path | → domus; predicate must be patched or retired in the same commit |
| 4 | `docs/runbooks/first-dollar-runbook.md` | Personal-financial: payout/KYC/bank/tax-id enrollment + personal email | → domus |
| 5 | `docs/architecture/his-hand-registry.md` | Financial-personal (named bank + card fraud hold) + teaching identifiers | → domus |
| 6 | `docs/reviews/deep-history-2022-2026.md` | Personal financial-crisis + health-adjacent narrative + named teaching engagement | → domus (**not** portvs — portvs is public) |
| 7 | `docs/inbound-magnet-system.md` | Confidential commercial: internal price anchors + negotiation posture, self-marked never-publish | → domus |
| 8 | `docs/repo-surface-ledger.md` | Named private individual + student/teaching topic in branch slugs | **DELETE** (regenerable; do not copy to a public repo) |
| 9 | `docs/plans/2026-07-29-custody-dual-estate-semver-lineage.md` | Named individuals mapped to private repos + money/seat economics | → domus (auditor said portvs; see conflicts) |
| 10 | `docs/github-estate-runbook.md` | Financial-personal (named bank + partial card identifier tied to a fraud hold) | **Redact in the same commit**, then → portvs |
| 11 | `docs/AUG1-10K-GATE.md` | Recovery/health contingency + personal financial targets | → domus |
| 12 | `docs/OFFSITE-DURABILITY-PROPOSAL-2026-06-19.md` | Personal identity/keychain records + card-fraud detail | → domus |
| 13 | **`docs/conductor-tranche.md` — STAYS but leaks** | A skip-list slug carries a private individual's first name on a personal matter, plus a student/teaching support slug | **Redact/generalize the slug list at the generator** (`scripts/conductor-tranche.py`); do not move the file |
| — | `docs/github-estate-ledger.json` (stays, lower severity) | Outside-collaborator GitHub logins for repos that are **private** | Hash/drop the collaborator list for private repos, same treatment already applied in `github-estate-census.json` |

---

## 4. What genuinely stays (273 files)

- **Protocol & architecture specs (≈45):** `docs/architecture/` (20), `agent-instruction-standard.md`, `concurrent-integration.md`, `host-work-admission.md`, `tabularius-record-keeper.md`, `deployment.md`, `never-hang-permission-spec.md`, `research-backend.md`, `repo-split-protocol.md`, `removal-acceptance-covenant.md` + the reap/acceptance protocol family, `docs/plans/` (6), `docs/convergence/` (2), `docs/runbooks/workstream-kickstart.md` (body).
- **Session/workstream lifecycle (≈100):** all of `docs/continuations/` (90, incl. the 32 derived person/domain cartridges — thin registry pointers with content deliberately excluded), `docs/current-session-fanout/` (10).
- **Machine-consumed operating records (≈80):** the `prompt-*`/`vltima-*`/`session-*`/`worktree-*`/`branch-*`/`clone-*` ledgers, `product-ledger.md`, `always-working.md`, `dispatch-health.md`, `live-root-gate.md`, `capacity-fill.md`, custody/storage-evacuation inventories, `ask-gate-*` migration manifests, `jules-*` registries — each read or written at an exact path by `scripts/`, `cli/`, `institutio/governance/*.yaml`, or a test.
- **Own-repo receipts & audits (≈35):** `docs/receipts/` (12, incl. the `pr-campaign/` kernel store), `docs/lane-checkups/` (10), `docs/consolidation/` (5, wired as a live conductor gate), `docs/research/` (3), `docs/reviews/` limen-scoped subset (15: `BACKLOG`, `CONTAINER-READINESS`, `ORGAN-REVIVE`, `VENDOR-LANE-AUDIT`, `codex-claude-session-review`, `deletion-surface-audit`, `session-2026-07-03-audit-trail`, `full-history-excavation`, `epoch-closeout` + its 6 modules), `docs/every-ask/`, `docs/moneta/` (moneta is a limen subsystem, not a separate repo).
- **Registry-paired prose (≈13):** `IDEAL-FORMS-LEDGER.md`, `CANON.md`, `fable-allotment.md`, `gatekeeper-boundary.md`, `storage-endgame.md`, `sovereign-inference-plan.md`, `github-app-architecture.md`, `credential-token-tombstone-audit.md`, `docs/keys/fable-guard-settings-snippet.json`, `docs/positioning/{_capture,_discoverability,_his-hand,limen}.md`, `docs/lanes/README.md`.

---

## 5. Execution order

**T1 — Leak stop, free moves (no consumer patch).** `architecture/identity-organ.md`, `architecture/his-hand-registry.md`, `runbooks/first-dollar-runbook.md`, `AUG1-10K-GATE.md` (comment strings only), `OFFSITE-DURABILITY-PROPOSAL`, `storage-creep`, `keys/*.asc` → domus. Same commit: open the escalation for `scripts/identity.py` / `fill-phi-jewishboard.py` / `identity.schema.json` / `personal-facts.yaml` — the doc move does not cure that one.

**T2 — Leak stop, one-line citation patches.** `health-office/` (7 strings in `health-organ.py`), `student-email-reply-grounding.md` (**predicate patch**, `check-student-email-grounding.py`), `inbound-magnet-system.md` (+ `positioning-seeds.json`), `deep-history-2022-2026.md`, `plans/2026-07-29-custody-dual-estate…`, `life-office/CHARTER.md`. Plus two **in-place redactions**: `conductor-tranche.py` skip-list, `github-estate-ledger.json` private-repo collaborator logins.

**T3 — Free portvs moves.** `docs/receipts/pr-lifecycle-estate-*` (7) + `seo-live-facts` (zero bindings), `docs/reviews/` fleet set (11 + the 9-file `seven-agent` unit), `consolidation/SESSION-2026-06-28.md`, `plans/2026-07-30-portvs-astra-consolidation.md`, `github-pr-debt-ledger.json` (one `tasks.yaml` string). Cheapest volume in the whole program.

**T4 — Product-repo moves.** `lanes/rob-game.md`, `PLAN-LONG-AND-WIDE.md`, `his-hand-registry-mail-*.md` (3 citations), then **`docs/positioning/` — refactor, not `git mv`**: teach `generate-positioning.py` to emit per-repo, repoint `L-POSITIONING-ACTIVATE` and the two `_frontdoor` `tasks.yaml` pins, then move the 12.

**T5 — Portvs moves needing real consumer patches.** `github-actions-usage.json` (narrow the `sensors.yaml` canary), `github-contribution-balance.md` (`organs/contributions/ESTATE.yaml` + test), `estate-closeout-audit.md` (**move the generator with it**), the four `vltima`-registered census docs (registry rows + generators), `repository-evacuation-inventory` (`custody.yaml`), `github-estate-runbook.md` (redact first, 4 pins).

**T6 — Domus moves needing predicate patches, then deletes.** `estate-custody-primitives.md` + `-receipts.json` (`always-working.py` + test + `tasks.yaml receipt_target`), `QUICKEN-RESIDUE.md` (**repoint `quicken.py` `RESIDUE_OUT`** or it regenerates into the public repo next beat), `photos-universe-*` ×2. Then the deletes: `repo-surface-ledger.md` (3 consumers), `needs-human-prep/` ×2 (manifest row), `workstream-kickstart.md` section strip.

---

## 6. Conflicts and open questions

1. **`plans/2026-07-29-custody-dual-estate-semver-lineage.md` → portvs or domus?** It carries named individuals tied to private repos and money/seat economics; portvs is PUBLIC, so that export relocates the leak. **Recommend domus**, or redact the migration-ledger names and then portvs.
2. **`github-estate-runbook.md` — same shape.** Operationally it is portvs's subject, but it names a bank and a partial card identifier. **Recommend: redact in the export commit, then portvs.** Do not move it unredacted.
3. **`estate-custody-primitives.md` / `-receipts.json`: is `scripts/always-working.py`'s estate-custody workstream itself misplaced?** Auditors split STAY (binding) vs EXPORT (consumer belongs elsewhere). **Recommend export the docs + repoint the constants now; treat the script's home as a separate decision.**
4. **`docs/convergence/` (2 files): estate-wide content, but pinned by `institutio/governance/convergence.yaml` and a CI gate's `paths:`.** Auditors disagreed. **Recommend STAY** — the brief names `institutio/governance/*.yaml` as limen's own subject. The real question is whether the whole CONVERGENCE axis relocates; that's a bigger move than a docs export.
5. **`github-estate-census.json` and `github-estate-ledger.json` stay only because shipped limen code (the progress TUI, the GITVS observatory) reads them.** So limen still owns the estate census substrate portvs is supposed to own. **Question: should GITVS/observatory move to portvs?** Recommend deferring, but it is the reason this program cannot fully clear estate material out of limen.
6. **`docs/reviews/`: the batch pass said export all 34; per-file verification reclassified 15 as limen-scoped** (`epoch-closeout` is limen's own PR/board cadence, not a 300-repo census; `codex-claude-session-review` audits limen's own Fable/Opus budget discipline). **Recommend the per-file split above**; if you'd rather keep `docs/reviews/` as one unit, the whole directory goes to portvs and limen loses 15 of its own records.
7. **`needs-human-prep/`: export (batch) vs delete (per-file).** Both files are provably superseded and one is factually wrong. **Recommend DELETE**; git history is the archive.
8. **`docs/positioning/` was audited as one organ, then split 4/12 per file.** The split is right on subject, but it is only shippable as a generator refactor. **Confirm you want per-repo emission** before T4.
9. **`MERGE-READY.md`, `always-working.md`, `conductor-tranche.md`, `product-ledger.md` are cross-repo outputs kept in limen** because they are limen's own dispatcher's product, not a census. **Recommend STAY** — but they're the boundary case; if you read them as estate records, they'd add ~4 more to portvs.