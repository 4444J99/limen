# Estate classification

This is the public-safe classification contract for PSP-P02-W02. It makes the
whole controlled GitHub estate legible without using repository volume as a
quality claim and without turning a public document into an inventory of
private work.

The denominator is the stable two-pass W01 census receipt:
10 controlled organizations and 314 accessible repositories (235 public, 79
private). The receipt records identical repository keys across both passes;
the verifier recomputes that repository identity/visibility digest and also
matches the authenticated owner and organization roster. This classification
is a reversible preflight over that denominator, not a completion receipt for
W02.

## Four dimensions

Every live census record receives these dimensions during verification.

| Dimension | Values | Evidence |
| --- | --- | --- |
| Primary role | infrastructure, proof, experiments, products, archives, private operations, partner work | Estate governance class, product ledger, archive fact, and access grant posture |
| Maturity | active, maintained, dormant, archived, unvalidated | GitHub `archived` and `pushed_at` facts; exact elapsed-time comparisons at the inclusive 90- and 365-day policy boundaries |
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

## Public/private rule

The public registry stores the policy, the W01 aggregate receipt, and this
aggregate report. It does not add private repository names, descriptions,
topics, or timestamps. Verification may inspect those facts directly through
the authenticated GitHub API, keeps them in process, and checks the reviewed
diff against the live private-name set. Any newly added private repository name
in public content, a newly added path, or a rename destination is a hard
failure. Failure messages remain aggregate and never echo the private identity.

Sensitive rationale remains in the existing arca-sealed
`institutio/github/estate.private.yaml` overlay, which can deepen a repository
judgment but cannot alter public class policy. A private repository becomes
public only through the existing visibility sweep and its release gate; this
classification never authorizes a visibility change.

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
exactly one primary class and all four dimensions, every selector key and value
is recognized, the live owner/organization roster and repository
identity/visibility digest still match W01, the denominator counts still
match, and the public diff contains no newly added private repository name in
content or path metadata. The unit companion is:

```bash
python3 scripts/tests/estate-classification.test.py
```

Formal W02 completion remains dependency-gated on #2173 and requires its
normal conduct-backed receipt plus
`python3 scripts/positioning-program.py --verify-work PSP-P02-W02`.
