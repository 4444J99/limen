# Custody: the Dual-Estate Doctrine — semver'd lineage and v1.0.0 encoding

**Date:** 2026-07-29 · **Status:** v1.0.0 encoded (this PR) · **Registry owners:**
`institutio/github/estate.yaml` (custody), `institutio/github/access.yaml` (access),
`organs/consulting/constellation/registry.yaml` (products), `his-hand-levers.json` (migration).

This document is the excavated lineage of every custody/topology decision on record, versioned,
plus the v1.0.0 doctrine the operator directed on 2026-07-29. It is a *record*; the registries
above own the live answers. Nothing here restates a path list or a class table.

## Part I — topology lineage (excavated 2026-07-29, three-explorer sweep)

| Version | Date | Artifact | Decision | Status |
|---|---|---|---|---|
| v0.1.0 | 2026-06-01 | `.claude/plans/2026-06-01-limen-system-state.md` | Scattered estate: repos across the personal account + 7 per-aspect org shells | superseded |
| v0.1.1 | 2026-06-20 | `docs/consolidation/SCOPE-AND-APP.md` | Personal-account *identity coupling* diagnosed as a hazard (a personal billing lock killed CI); fleet identity moves to an org-owned GitHub App | live (identity only) |
| v0.2.0 | 2026-06-28 | `docs/consolidation/EXECUTION-MANIFEST.md` | Consolidation: all code into the single `organvm` org; personal account carved out as a non-code-host | superseded by v1.0.0 (amended, not reversed) |
| v0.2.1 | 2026-07-10 | `institutio/github/estate.yaml` (PR #900) | GITVS: custody becomes declared registry data (classes, overrides, orgs block); `4444J99/**` classed portal-only | live, amended |
| v0.2.2 | 2026-07-17 | estate.yaml orgs block (#1185) | Inverted-custody settlement: 9 empty shell orgs → $0 name reservations; Enterprise emptied by machine | live |
| v0.3.0-rc | 2026-07-22 | branch `work/victoroff-external-custody-20260722` (unmerged) | Proposed an external client-org (`victoroffgroup`) custody exception for one collaboration repo | **road not taken** — never landed |
| v0.3.0 | 2026-07-23 | `institutio/github/access.yaml` (PR #1407) | Partner partitioning: **grants, not transfers** — per-partner scoped `push` grants, ceiling-bounded, engine repos ungrantable | live (governs ACCESS in both estates) |
| v0.3.1 | 2026-07 (out of band) | GitHub ground truth (verified 2026-07-29 via `gh`) | `victoroff-os` physically transferred `organvm` → the personal account; redirect live; **no registry row followed it** | drift — healed by this PR |
| **v1.0.0** | **2026-07-29** | operator directive + this PR | **Dual-estate custody** (Part II) | **encoded** |

## Part II — the v1.0.0 doctrine

**The org is the SYSTEM; a collaboration-born product is a personally-owned asset.**

- `organvm` holds the system-of-organs: engine, organs, governance, moat, corpora. Custody: org.
- Products born from constellation collaborations live on the **personal account**. Custody:
  personal. Membership **derives from the constellation register's project repos** — no second
  list is maintained anywhere.
- Three load-bearing reasons, in order:
  1. **Ownership boundary** — the engine and the moat are the estate; a product built *with* a
     partner is a separable personal asset. Custody states the boundary structurally.
  2. **Seat economics** — personal-account private repos carry unlimited free collaborators,
     permanently. The org's planned Team upgrade (`L-ORG-TEAM-UPGRADE`, wanted for private-repo
     rulesets) would meter outside collaborators on private *org* repos as paid seats. Dual
     estate means the upgrade never taxes a partner lane.
  3. **Blast radius** — partner access structurally never touches the org that holds the moat;
     defense-in-depth above `access.yaml` partitioning.
- **v0.3.0 is subsumed, not reversed:** partitioning governs *access* (scoped grants, `push`
  ceiling, in both estates); dual-estate governs *custody* (which account owns the repo).
- Identity stays v0.1.1: CI/fleet identity remains the org-owned App/token cascade — moving a
  repo's custody must never re-couple automation to personal billing.

**Encoded this PR:** the `repo_custody` envisioned resource type + the amended `orgs.canonical`
note + the `4444J99/victoroff-os` override row (estate.yaml); the `david` grant row
(access.yaml); the register re-path (constellation registry.yaml); the migration lever
(`L-CONST-CUSTODY-MIGRATION`).

## Part III — ground-truth reconciliation (2026-07-29)

Verified live via `gh` (never from local remotes — the local checkout's remote URL still pointed
at the pre-transfer path and disagreed with GitHub):

- `victoroff-os`: owner `4444J99`, private, redirect from `organvm/victoroff-os` live; partner
  role `write` — exactly the access ceiling. Healed: without an override row, the `4444J99/**`
  portal glob classed it **desired-public** (a latent flip hazard behind the publish gates);
  without a grant row, its partner access sat in the undeclared-removal direction of
  `collab-sync.py`. Both rows land in this PR.
- `organvm-corpvs-testamentvm`: estate row (`vault_private`, on main since the classification
  wave) already declares it desired-private; observed public (CC-BY-SA, 0 forks). This is
  **already-decided demote-direction drift** — the standing leak-posture auto-guard direction of
  `scripts/apply-visibility.py`, not an open exposure question.
- 9 shell orgs: empty, $0 — matches v0.2.2. Personal account: 2 repos (profile + victoroff-os).

## Part IV — migration ledger (candidates derive from the constellation register)

Live-repo candidates at excavation time — the register is the source; this table is a receipt:

| Product | Partner | Current repo | Note before transfer |
|---|---|---|---|
| spiral | maddie | `organvm/sovereign-systems--elevate-align` | grant row re-path; check org Actions vars |
| styx | jessica | `organvm/peer-audited--behavioral-blockchain` (+2 cluster repos) | public/portal class — transfer moves stars; re-path grant + estate rows |
| hokage-chess | rob | `organvm/hokage-chess` (+ `hokage-chess--4444j99`) | reconcile the name-twin first |
| micro-tato | rob | `organvm/micro-tato` (+ play repo) | — |
| mirror-mirror | charles | `organvm/mirror-mirror` | publish-candidate row travels with it |
| your-fit-tailored | charles | `organvm/your-fit-tailored` | — |
| content-cannibalizer | scott | `organvm/content-engine--asset-amplifier` | grant row re-path |
| podcast-suite | ari | `organvm/hospes` | **excluded** until the declared vault split (`split: into arca`) lands — transcripts are vault-class |

Per-repo checklist (each transfer, same day): fire via the lever → accept invitation → verify
redirect → land one row re-path PR (estate override, access grant key, constellation `repo:`,
any moat-guard/positioning references) → `gitvs.py doctor` green.

**Owed items, each with its owner (none parked here):**
- `L-CONST-CUSTODY-MIGRATION` — his-hand registry (staged; machine never fires a transfer).
- `repo_custody` activation (observe + effector) — estate.yaml wiring-integrity law.
- `derek`: engagement file exists (`organs/consulting/engagements/derek.yaml`) with no register
  row — owner: constellation register (add the person row or re-home the engagement).
- The seven registry-decided demotes (corpvs + 6 siblings, observed public 2026-07-29) —
  owner: `L-GITVS-DEMOTE-ARM` (the reconcile valve is unarmed; arming is classifier-gated to
  agents, so the paste/one-shot is his). Executor: `apply-visibility.py` auto-guard lane.

## Part V — secret-sauce lineage (recorded for the same excavation; registries own the rest)

| Version | Date | Artifact | Decision |
|---|---|---|---|
| v0.1.0 | 2026-07-10 | estate.yaml classes | Publish-the-form split: `operation_private` — "a public FORM twin may exist; the operation itself stays the moat" |
| v0.2.0 | 2026-07-17 | `docs/repo-split-protocol.md` (PR #1159) | The hard law: never fork/branch-copy a private repo — git history leaks; fresh-init twins, history-disjoint verified (`check-split-hygiene.py` P1–P5) |
| v0.2.1 | 2026-07-17 | `moat-guard.json` + `scripts/moat-audit.py` (PR #1183) | Crown jewels as machine-checkable literal-value leak patterns; interfaces stay public (the lure), values stay private |
| v0.2.2 | 2026-07-22 | `CONST-VICTOROFF-FACE` | Every unreviewed private repo gets an *owned exposure decision*; a public face is a split, never a flip |
| v1.0.0 | 2026-07-29 | this excavation | Posture confirmed; the enforcement gap is **coverage**, not doctrine: moat-guard guards 1 public repo; expansion is per-repo curation work owed to `moat-guard.json`; corpvs demote is decided drift (Part III) |

Platform fact the doctrine already respects: GitHub cannot disable forking of a *public* repo —
`allow_forking` binds private repos only. The only real fork-protection levers are visibility
(the private core) and what the split protocol lets out (the form twin). License posture governs
reuse rights, not the fork button.
