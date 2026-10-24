# Native source recovery and repeated control language

Owner: [#3056](https://github.com/4444J99/limen/issues/3056).
Publication: [#3087](https://github.com/4444J99/limen/pull/3087).

The supported native reader was queried for the 26 sources that exceeded rollout bounds and
the 32 history IDs missing from the earlier header inventory. The original limits were not
raised and the blocked SQLite capture was not rerouted. These are supplementary native reader
views; they do not repair or certify the original source bytes.

| Result | Source-limit targets | Header-missing targets | Total |
|---|---:|---:|---:|
| End of reader view reached | 21 | 23 | 44 |
| Readable prefix, then a single-turn size failure | 3 | 1 | 4 |
| Readable prefix at the 20-page tranche bound | 1 | 1 | 2 |
| No readable view | 1 | 7 | 8 |
| Requested | 26 | 32 | 58 |

Fifty requested views were returned. One contains no turns and three contain no visible user
items; these are distinct from available operator-prompt evidence. Of the eight unread views,
one exceeds the single-turn limit,
one has no readable match on the queried hosts, and six have undetermined availability because
the durable host failed. An unavailable host is not proof that a session never existed.
For size failures, the documented smaller-turn request was attempted once; a failure at one
turn was retained. Cursor failures were not skipped.

[The source census](native-source-recovery-v1.json) records every target under a redacted alias.
Private query bindings retain native identities, returned cursors and observed turn references.
Forty-four exhausted views are **not forty-four proven complete operator sessions**.

## Shared history changes the denominator

Across the material read in this tranche:

| Unit | Count |
|---|---:|
| Native turn appearances across views | 743 |
| Distinct observed native turn IDs | 662 |
| Turn appearances without a visible user item | 335 |
| Visible user-item appearances | 580 |
| Distinct observed native input bindings | 496 |
| Native turn IDs repeated across different views | 27 |
| Maximum views sharing one turn | 8 |
| Conflicting ordered user-content arrays for a shared ID | 0 |
| Duplicate turn IDs within a single paginated view | 0 |

Shared turns were compared using exact ordered user-content arrays, with only JSON object-key
order ignored. Text, content-part values and array order were preserved. The count of distinct
inputs keeps multiple user items in the same native turn separate. Different native turns are
never collapsed just because their words match.

This establishes repeated *appearances of the same native input*, not semantic equivalence
between independent prompts. Those copies remain useful context in each side-by-side column,
but frequency analysis must not count each appearance as a fresh operator request.
The 496 bindings are not a human-authorship count or a completed semantic-review numerator.
The earlier projection's own-item count and a reader's context-rich view are different units;
subtracting them does not establish how many prompts remain missing.

## A recovered 26-input control sequence

One header-missing target now exposes 33 ordered inputs. Seven context inputs precede the
26-input terminal segment whose opening text matches the thread preview and earlier projection.
This is an explicit candidate segment boundary, not a claim that the original logical opener
has been recovered. One earlier context input contains 400,209 characters and was not
semantically classified in full. All original context remains in its source.

[The contextual review](recovered-control-sequence-v1.json) assesses all 25 positions after that
candidate segment's first input against the unchanged 19-operation v4 vocabulary. It inspects
the intervening comments as well as final replies and native turn status.

| Recurring form | Positions | Preserved difference |
|---|---|---|
| Next-action request | 9, 11, 14, 18, 23, 25 | The next target changes with completed work, evidence and scope corrections. |
| Continuation | 10, 12, 22 | Each inherits a different concrete proposal; the voice case retains its proposal binding. |
| Explicit approval plus execution | 13, 15, 19, 20, 24, 26 | The approved plan and authority change; approval does not imply successful execution. |
| Selected-target continuation | 6, 8 | Same routing operation, different named source. |
| Merge plus new work | 7 | Publication stage and four new source targets remain separate. |
| Explanation | 2, 4, 5 | Cause, denominator and possible reduction are different questions. |
| Process correction | 3, 21 | Enforce the existing plan or change throughput; do not merely draft another remedy. |
| Interpretation or scope correction | 16, 17 | An attributed factual update differs from stopping an unwanted diagnostic lane. |

The nine continuation/approval interactions produce different historical stage reports:
some claim integration, two stop at publication with merge pending, and the pilot interaction
reports provisioning without native acceptance. This supports common intention families, not
identical fixed outcomes or successful substitutions. None of those old delivery claims was
independently reverified by this language study.

The voice envelopes contain both an input and a transcript delta. Repeated text inside that
one envelope is not another operator prompt. Assistant speech in the payload supplies context;
it cannot independently grant authority. The scope correction also constrains later generic
continuations instead of being forgotten when the words repeat.

## Acceptance retained

This pass adds source availability, shared-history evidence and 25 contextual dispositions.
It does not install commands, claim complete logical sessions, add a corpus compression
percentage or promote grouping into semantic review. The 19-operation proposal remains v4.
The private comparison catalog is still the earlier frozen rendering; these versioned reviews
form the current supplementary layer. Remaining source, lineage, full-context analysis,
independent substitution and original delivery predicates retain their existing owners.

## Bounded verification

Target aliases are unique and reconcile to all 58 requested identities in the private index.
The index independently reproduces 743 turn appearances, 580 user-item appearances and 662
distinct turn IDs. The 25 case positions cover the complete range 2 through 26 without gaps.
Written public JSON and private reference indices match the analyzed objects exactly; private
metadata excludes prompt previews. These checks establish this tranche's accounting and write
fidelity, not whole-session completeness or semantic substitution success.
