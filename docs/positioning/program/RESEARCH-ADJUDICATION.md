# PSP-P02-W08 research adjudication preflight

This is a public-safe preflight record, not a completion receipt. PSP-P02-W08 remains formally
blocked on the accepted outputs of PSP-P02-W01 and PSP-P02-W05. No issue closure, merge, profile
mutation, live issue projection, or claims-ledger edit is authorized by this record.

The machine-readable adjudication is
[`research-adjudication.json`](research-adjudication.json). Its dated live evidence is
[`psp-p02-w08-live-profile-preflight-20260810.json`](../../receipts/positioning/psp-p02-w08-live-profile-preflight-20260810.json).

## Exact public heads and observations

| Surface | Exact public head or identity | Adjudication use |
|---|---|---|
| GitHub profile | `f198b37e3161121e7c198e21bd18b87e29b6bc4f` | Rendered wording, manifest values, generator workflow |
| W01 census preflight | `2d591e630a3b3fbcdfeb7ac12500f374c607af30` | Public-safe estate totals |
| W03 proof-set preflight | `0de48d3f5dc15b9bae61cbf49eeba9a9eed59ba2` | Per-system public proof and constrained live probes |
| LAVREA | `02e360c9828336ac95ce8223c65d127ffea27661` | Methodology and percentile-baseline audit |
| Portfolio | GitHub repository ID `1155412125`; head `85bfaa84287e4a3b90b49187caa4313c4edda1aa` | Canonical-owner resolution independent of a mutable slug |

All values below are observations made on 2026-08-10. Moving values carry their own timestamp in
the receipt.

## Adjudicated corrections

1. **The portfolio link is broken, but the portfolio is not gone.** The profile metadata URL
   returned 404. Stable repository ID `1155412125` resolves to the transferred public repository,
   and its canonical Pages URL returned 200. The registry now resolves the immutable ID to the
   canonical owner instead of assuming the former slug. GitHub documents that Pages URLs are not
   redirected when a repository transfers.
2. **The repository counts are measurements, not unsupported self-report.** The generated manifest
   records 227 public organization repositories and 198 public non-forks. Fresh public API queries
   reproduced both values, and W01 independently reconciles 8 personal plus 227 organization
   repositories to 235 public repositories. These counts do not imply product count, quality,
   adoption, or impact.
3. **The contribution total is valid only as a dated moving-window observation.** The exact
   manifest records 33,130 at `2026-08-10T08:05:30Z`; a later live query returned 33,168 and its
   daily-count sum matched. Any public use must state the range, observation time, and viewer/token
   treatment.
4. **The profile is actively regenerated, not a one-time boast.** Eight distinct workflow run IDs,
   each recorded as a scheduled event on one of eight consecutive UTC days, succeeded from
   2026-08-03 through 2026-08-10. That bounded window does not establish an uptime SLO,
   perpetual availability, or zero manual intervention. The workflow also checks out a floating
   generator dependency and does not record that generator head in the manifest.
5. **The blanket production claim is too broad.** W03 found exact-head CI for both featured systems
   and a live public operating receipt for Limen, but another featured system's advertised public
   proof endpoint returned 404. Replace universal live-deploy wording with per-system evidence
   status.
6. **The bounded Limen operating claim survives.** Current public status and exact-head verification
   support named mechanisms operating in the owner's environment. They do not support the phrase
   “Zero manual upkeep — runs forever once seeded,” which remains withheld.
7. **LAVREA's raw measurements survive the baseline criticism.** Contribution, repository,
   pull-request, language, organization, stack-rule, and tenure inputs can be retained when dated
   and definition-labeled. The inspected primary population material does not establish LAVREA's
   percentile thresholds, so “top 0.1% engineering throughput” and “Top 1% Python full-stack
   engineer” remain withheld. Rejecting those inferences must not erase verified inputs.
8. **Singular accountability needs authorship disclosure.** “One creator” may describe the
   accountable architect and director, but must not imply that every line was manually written
   without machine assistance.

## Four independent dispositions

Every contested claim has four independently cited fields in the integration artifact:

| Layer | Question | Required treatment |
|---|---|---|
| Measurement | What was directly observed, counted, or reproduced? | Preserve verified, dated, public-safe facts even when later layers fail. |
| Inference | What conclusion follows from those premises and comparison rules? | Bound or withhold conclusions whose population, threshold, or causal rule is missing. |
| Implication | What might a reader wrongly take the claim to prove? | Explicitly reject unsupported quality, adoption, impact, reliability, or authorship implications. |
| Prominence | Where should the claim appear publicly? | Decide separately from truth; a valid measurement may remain supporting-only. |

The artifact covers 13 research-rebuked claims and audits all eight LAVREA axes. Private dossier
prose and private-only inventories are not copied or used as public evidence.

## W05 integration contract

PSP-P02-W05 consumes `research-adjudication.json`, preserves every claim's four layers and
citations, regenerates moving numeric rows, and imports only publishable wording into
`docs/positioning/claims-ledger.md`. It must not collapse a verified measurement into a rejected
inference. The ledger is deliberately unchanged in this lane.

Formal W08 completion remains forbidden until W01 and W05 have accepted receipts and this artifact
is reconciled to their exact heads.

## Registry-drift relay

The authoritative program manifest and its generated issue index now resolve the portfolio through
GitHub repository ID `1155412125` to `organvm-vii-kerygma/portfolio`. A focused live-identity check
fails if the ID resolves to a different slug, visibility, default branch, or archive state, or if
program work reintroduces the retired slug.

The following 18 live issue bodies still contain the retired projection and require an authorized
projector refresh; this preflight did not mutate them:

| Work IDs | Live issues |
|---|---|
| `PSP-P06-W01` through `PSP-P06-W07` | #2205–#2211 |
| `PSP-P07-W03`, `PSP-P07-W04`, `PSP-P07-W08` | #2215, #2216, #2220 |
| `PSP-P08-W02` | #2224 |
| `PSP-P09-W02` through `PSP-P09-W06` | #2232–#2236 |
| `PSP-P10-W04` | #2243 |
| `PSP-P12-W04` | #2261 |

The confirmed private collaboration target is unchanged. The next authorized projection action is
recorded in the machine-readable artifact; it was not executed here. A packet seed remains a
non-lease, but seeds for identity-managed repositories now fail closed unless a live lookup of the
immutable repository ID still resolves the canonical owner, visibility, default branch, and archive
state immediately before seed emission.
