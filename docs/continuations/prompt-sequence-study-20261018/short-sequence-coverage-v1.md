# Short sequences and native-source coverage

Owner: [#3056](https://github.com/4444J99/limen/issues/3056).
Publication: [draft #3087](https://github.com/4444J99/limen/pull/3087).

This adds contextual dispositions for **16 two-prompt file sequences**:
32 retained positions and 16 follow-ups. Each opener and paired reply was read
with its follow-up. See [the ordered cases](short-sequence-review-v1.json).
The [source census](native-coverage-v1.json) keeps unknown retention metadata,
explicitly incomplete bodies, source segments and logical-session coverage distinct.
No new command is added; v5 remains a research proposal.

## What can and cannot be compressed

| Sequence / source key | Opener | Follow-up candidate | Required binding | Historical reply |
|---|---|---|---|---|
| E01 / b760bfd40198 | Review three peer records, plan repairs and implement | /fix + /continue | Resolve storage/access causes without deletion or safeguard bypass, then execute the existing plan through its existing owners. | The reply reports restored existing-worktree access, one merged healthcheck fix and two published Limen updates; heavy verification, deployment and full recovery remain incomplete. |
| E02 / 9484ade1e6aa | Close out a review whose checkout disappeared | /next | Derive the minimum actual human action from current access/ownership evidence; investigation and repair remain agent work. | The reply says there is no terminal command to run yet and describes a concrete policy request that still needs preparation. |
| E03 / 286d6e09fd72 | Inventory agent directories and plan provider-neutral containment | /review | Adversarially evaluate the entire preceding session against its original multi-part request, source claims, coverage and durable deliverables. | The reply identifies incomplete census/plan delivery and unsafe recovery assumptions while preserving successful reconnaissance as partial evidence. |
| E04 / e5486e84c834 | Repair strict YAML lint while preserving configuration values | /verify | Check archival eligibility of the work conversation, without deleting the chat or authorizing checkout retirement. | The reply permits chat archival but says formal session closeout and a terminal receipt remain unverified. |
| E05 / d72e4ff8bf64 | Finish incomplete local-CI fixes and integration | /verify | Check chat archival eligibility against published work and remaining owned state. | The reply permits chat archival while requiring worktree retention because an uncommitted child edit has unknown ownership. |
| E06 / 372f808b1d01 | Harden the native Doctor adapter and prove its deployed behavior | /verify | Check archival eligibility as a durable handoff while preserving the unmerged delivery owner and private evidence. | The reply permits archival, reports a matching installed helper and published clean checkout, and explicitly retains the worktree with its PR still open. |
| E07 / 6838400d1152 | Finish live skills consolidation, use, capture and rollback | /next + /plan | Derive the complete remaining rollout sequence with all consumer, capture, review, recovery and retirement gates preserved. | The reply gives a controlled five-consumer rollout and distinguishes engineering from eligible-review/account authority. |
| E08 / cffcc86b2fdf | Give evidence-grounded feedback on day-to-day operation | /continue | Finish the already requested activity analysis using its bounded evidence sample. | The reply provides the assessment and recommendations with explicit sample coverage rather than a complete time-use audit. |
| E09 / 325388a4989e | Recover production and deployment automation under exact-source constraints | /next + /plan + /handoff | Derive next work, assess serialized multi-agent preparation/execution, and draft a separate bounded relay for each role. | The reply supplies three role handoffs with temporal, authority, custody, accounting and full-day acceptance dependencies. |
| E10 / a01b845e1fe4 | Recover a storage-quota-blocked launcher safely | /correct + /plan | Correct one-off cleanup into durable recurrence prevention, retaining the existing archive/restoration owner and original data. | The reply supplies a preventive maintenance plan and corrects the supplied claim that an archive process was running. |
| E11 / 3addcf764b75 | Diagnose quota and two MCP startup failures | /fix + /verify | Execute only the specifically selected technical repair: negotiation compatibility and a prepared fixed-version launcher. | The reply reports tool discovery for both integrations but leaves full installer completion and independent monthly quota exhaustion open. |
| E12 / a92ca768e5a3 | Proceed with the named C0 reconciliation stage | /continue | Repeat the same C0-stage request while retaining its source prerequisites, accepted policy boundaries and existing allowance. | The first reply cannot locate B0; the second reports C0 staged on B0 with tests and HOLD for acceptance/review. |
| E13 / d9a614769649 | Build a purpose-specific governed repository factory | /closeout | Resolve this session's obligations and prove its release without substituting project completion or merge acceptance. | The reply reports two unchanged passing release runs while explicitly leaving task completion, estate completion, retirement and merge unclaimed. |
| E14 / fc79f3672823 | Diagnose local/remote editor dictation failures | /context + /verify | Supply the new local-run error as evidence that tests the earlier Codespaces-specific hypothesis. | The reply identifies the same transcription challenge locally and gives a redacted escalation route rather than a microphone/reinstall fix. |
| E15 / 704e82f73833 | Complete the assigned miscellaneous-repository workstream | /closeout | Attempt the complete original session-release contract, preserving its task owners and custody requirements. | The reply reports exit 2/unmeasured after bootstrap and a read-back handoff; release remains unverified. |
| E16 / e29f61b15f28 | Plan healing of an allegedly missing closeout protocol | /closeout | Prove release for this healing session while retaining the prior plan and original session obligations separately. | The reply reports exit 0 and a published durable handoff after the earlier reply identified a partly stale blocker. |

Repeated archival questions E04-E06 share a verification operation, but their
answers do not authorize checkout deletion or establish all task predicates.
E13 and E15 share closeout intent while their reported predicate results differ.
E09 asks for a plan and relay drafts, not launched agents. E12 repeats a named
stage without proving its previously missing prerequisite appeared.
E08's continue finishes analysis; it does not implement the resulting advice.

These are contextual candidates, not successful runtime substitutions. New
payload, authority, expected evidence and source gaps remain explicit in JSON.
Opener attachments in E01 and the error attachment in E14 were not fully read
in this tranche. Historical external assertions were not reverified as current.

## Missing metadata is not declared truncation

| Captured scope | Explicit complete | Explicit incomplete | No completeness value | Total positions |
|---|---:|---:|---:|---:|
| 381 decoded native Codex file columns | 757 | 100 | 2,632 | 3,489 |
| One separate Claude example | 0 | 0 | 11 | 11 |
| Entire existing comparison | 757 | 100 | 2,643 | 3,500 |

A complete native projection is not proof that the original prompt survived
retention or that its logical session is complete. Conversely, a missing
retention flag does not declare truncation. The decoder joins represented
input-text blocks without slicing their text and records content/attribution
limits. Source-level capture bounds fail an attempted capture; they do not
turn unknown original provenance into complete retention.

Two direct native-record comparisons passed: one explicitly incomplete body
and one body without retention metadata both exactly match the captured text.
The first source had moved from active to archived storage; its captured text
still matched. These two samples do not establish completeness of all 2,743
non-true positions. They establish why false and absent flags must stay distinct.

Seventy file columns, containing 395 positions, have all captured retention
flags true. Their current review owners reconcile as follows:

| Owner | File columns |
|---|---:|
| Earlier inline annotations | 5 |
| Earlier native readback/review | 3 |
| Four-sequence contextual review | 4 |
| Expanded 218-position review | 36 |
| This two-prompt review | 16 |
| Duplicate-header families requiring branch reconstruction | 6 |
| Total | 70 |

This is coverage of captured file columns, not 70 complete original sessions,
independent intentions, or validated substitutions. All original study gaps
remain visible under their existing owners.

## Exact source-prefix evidence

[Ordered storage-view references](native-storage-views-v1.json) now preserve seven
cutoff-aware prompt/context views and their bounded reply references. This is
reference reconstruction; native identity and whole-view semantic acceptance remain open.

Seven files across three duplicate-header families were read within their
recorded byte bounds. Every full decoded hash matched the captured source
snapshot. All record ordinals were consecutive in each file.

Four declared history-base byte offsets land exactly at newlines. Their final
prefix ordinals equal the declared exclusive endpoints minus one. Each matching
parent snapshot was independently hash-bound again to the exact prefix evidence.

| Child column | Candidate parent column | Prefix exclusive ordinal | Excluded parent-tail prompt positions | Header identity agrees with reference |
|---|---|---:|---|---|
| a6ec9e820613 | 0479e9657ab3 | 6700 | 5 | No; unique filename token matches, native identity still unresolved |
| 0479e9657ab3 | e9a469256c79 | 5402 | 11 | Yes |
| 129fc0393717 | 66de6ccc61e4 | 513 | 3 | Yes |
| 2b3c94584076 | c0924a69626b | 397 | 6 | Yes |

The referenced prefixes omit later parent prompts in every case. Concatenating
complete parent files with continuation files would therefore insert prompts
outside the declared histories. The next reconstruction must keep the parent
tail as a separate branch and use only the referenced prefix.

One reference token differs from its candidate parent's header ID. Its unique
filename token and exact byte/ordinal boundary match, but that is not a complete
native identity binding. The app readback for one historical continuation
returned `list_turns is not supported yet`; no UI identity proof is claimed.
The files are not silently merged or counted as independent sessions.

## Selection concern checked before changing code

I used the systematic-debugging workflow to test the hypothesis that duplicate
native IDs cause the picker to select the wrong column. The code already uses
numeric file indices. The actual embedded runtime and existing catalog checks
passed in a bounded VM, then all **nine columns across four duplicate-ID groups**
were individually selected. Each displayed its own prompt count and text.

The hypothesis was disproved. No picker, capture, renderer or vocabulary code
changed. This is structural runtime evidence; browser appearance remains
uninspected, and the blocked full renderer was not run.

## Verification boundaries

Source bindings, case positions, operation names and coverage sums are checked
against the existing private dataset. All raw transcripts and attachments stay
at their existing locations. Public evidence contains redacted source keys and
descriptions, not private source text, account IDs or full hashes.

This work does not validate all original native bodies, complete logical
lineage, independent substitutions, installed commands, deployment or session
release. The goal remains active.
