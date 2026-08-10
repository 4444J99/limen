# Estate classification

This is the public-safe classification contract for PSP-P02-W02. It makes the
whole controlled GitHub estate legible without using repository volume as a
quality claim and without turning a public document into an inventory of
private work.

The denominator is the stable two-pass W01 census receipt:
10 controlled organizations and 314 accessible repositories (235 public, 79
private). The receipt records identical repository keys across both passes;
this classification is a reversible preflight over that denominator, not a
completion receipt for W02.

## Four dimensions

Every live census record receives these dimensions during verification.

| Dimension | Values | Evidence |
| --- | --- | --- |
| Primary role | infrastructure, proof, experiments, products, archives, private operations, partner work | Estate governance class, product ledger, archive fact, and access grant posture |
| Maturity | active, maintained, dormant, archived, unvalidated | GitHub `archived` and `pushed_at` facts; 90- and 365-day policy boundaries |
| Visibility disposition | public evidence, public partner, private internal, private partner | GitHub `private` fact plus the access-grant registry |
| Public relevance | technical diligence, front-door proof, public reference, product diligence, historical reference, private only, partner scoped | Primary role plus visibility disposition |

The ordered role policy lives in
[`institutio/github/estate.yaml`](../../institutio/github/estate.yaml). It is
intentionally first-match-wins: a partner product is partner work first, a
portal product is proof first, and a private product remains a product. This
prevents the same repository being counted in two primary classes.

## Current preflight coverage

The live verifier observed this public-safe aggregate on 2026-08-10:

| Primary role | Repositories |
| --- | ---: |
| Archives | 71 |
| Experiments | 118 |
| Infrastructure | 1 |
| Partner work | 4 |
| Private operations | 56 |
| Products | 49 |
| Proof | 15 |
| **Total** | **314** |

| Visibility disposition | Repositories |
| --- | ---: |
| Public evidence | 234 |
| Public partner | 1 |
| Private internal | 76 |
| Private partner | 3 |
| **Total** | **314** |

Maturity is 238 active, 5 maintained, and 71 archived; no live record lacked
a usable `pushed_at` fact. These values are evidence snapshots, not public
performance claims.

## W03 flagship candidate projection

The W03 preflight turns the W02 classes into a bounded public candidate set; it
does not create another estate inventory. The screen scores all 15 repositories
currently classed as `front_door_proof`, adds Limen because the PSP manifest
names it as the primary proof object, adds the three other repositories still
named as public profile or portfolio entry points, and adds the live MONETA
endpoint. That produces 20 public candidates.

The scored matrix and reviewer verdict live in
[`flagship-proof-set.yaml`](flagship-proof-set.yaml). It provisionally ratifies
three non-overlapping flagships:

| Story role | Flagship | Public evidence boundary |
| --- | --- | --- |
| Governed agent delivery | Limen | Public source, current exact-head CI, and public operating-status endpoint |
| Public-record decision pipeline | UCC Public-Records Intelligence Platform | Public source, current exact-head gate, and public deployment |
| Privacy-first data portability | AI Chat Exporter | Public source, current exact-head CI, and public install surface |

Universal Mail, Styx, a-i--skills, and MONETA remain named alternates with
specific promotion conditions. Every other screened candidate retains an
explicit exclusion reason. Selection is not a repository-count, stars,
activity-volume, or aesthetic ranking; hard evidence gates override the numeric
score.

This is a dependency-blocked preflight. It does not change a live profile
generator, close #2175, or assert the PSP work predicate. After #2174 closes,
W03 must refresh the matrix against the merged exact classification before its
formal receipt is posted.

## Public/private rule

The public registry stores the policy, the W01 aggregate receipt, and this
aggregate report. It does not add private repository names, descriptions,
topics, or timestamps. Verification may inspect those facts directly through
the authenticated GitHub API, keeps them in process, and checks the reviewed
diff against the live private-name set. Any newly added private repository name
in these public outputs is a hard failure.

Sensitive rationale remains in the existing arca-sealed
`institutio/github/estate.private.yaml` overlay, which can deepen a repository
judgment but cannot alter public class policy. A private repository becomes
public only through the existing visibility sweep and its release gate; this
classification never authorizes a visibility change.

W03 applies the same split: its public matrix names zero private repositories.
Private candidates are neither silently discarded nor copied into this repo;
they remain available for sanctioned diligence and any later encrypted W04
addendum. No selected public flagship may require that private addendum to make
its public claim intelligible or reproducible.

## Finite uncertainty queue

The queue is deliberately evidence-shaped rather than a name list. Private
record identities stay in sanctioned private custody; the verifier emits only
aggregate queue counts.

| Question | Current count | Evidence needed to resolve | Owner |
| --- | ---: | --- | --- |
| Is a fallback experiment a product, proof object, or durable experiment? | 118 | Repository purpose or explicit product-ledger / proof-selection decision | PSP-P02-W02 → PSP-P02-W03 where proof selection is involved |
| Does the one public partner surface need a distinct public-collaboration disposition? | 1 | Collaboration posture or private-twin decision in the access registry | Partner-access owner |
| Is ownership ambiguous? | 0 | A newer W01 two-pass census showing a changed owner/org/repository key | PSP-P02-W01 |
| Is maturity ambiguous? | 0 | A usable `pushed_at` fact or an explicit archive decision | Repository owner |

An unresolved item still has one safe primary class. The queue is a decision
backlog, not permission to guess, publish, or weaken the private default.

## Validation

Run the focused live predicate from the W02 branch:

```bash
python3 scripts/estate-classification.py --verify --json --base codex/psp-p02-w01-estate-census-preflight
```

It fails unless the policy taxonomy is complete, every live census record has
exactly one primary class and all four dimensions, the W01 denominator and
visibility counts still match, and the public diff contains no newly added
private repository name. The unit companion is:

```bash
python3 scripts/tests/estate-classification.test.py
```

Formal W02 completion remains dependency-gated on #2173 and requires its
normal conduct-backed receipt plus
`python3 scripts/positioning-program.py --verify-work PSP-P02-W02`.
