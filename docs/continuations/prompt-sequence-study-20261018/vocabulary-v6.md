# Vocabulary V6: content authoring as an explicit operation

Owner: [#3056](https://github.com/4444J99/limen/issues/3056). Current research proposal: [vocabulary-v6.json](vocabulary-v6.json).

V6 retains all 21 V5 contracts and proposes **`/compose`**, giving 22 operation names. It addresses a real partial fit: a follow-up can request a new content artifact whose brief was not supplied by the opener. The command name carries the operation; the new brief remains irreducible payload.

The intent and constraints are already supplied by the study request: reduce recurring follow-up control language while retaining intended work, output, authority and evidence. This is a bounded research revision, not installed command behavior or a product implementation.

## Proposed contract

| Part | Required binding |
|---|---|
| Operation | Author a requested content artifact from a bound brief. |
| Target and payload | Actual brief or immutable reference; audience; source material; format; requested maturity; destination; quantity/structure; style reference; factual limits. |
| Authority | Only the authorized content work. Sending, submitting, signing, public publication, account actions, instruction activation and runtime installation retain their own authority. |
| Constraints | Preserve originals and explicit no-overwrite conditions. Carry final/draft/exploratory maturity exactly. A production plan does not satisfy an artifact request. |
| Completion evidence | The requested artifact, source/claim checks, required quantity/structure, and requested readback/render/style checks; report each actual acceptance state. |

Illustrative notation, not an installed parser:

```text
/compose --brief N07.2 --form naming-matrix --maturity exploratory
/open --target <that-artifact> --application <requested-viewer>
/compose --brief A06.3 --form editorial-options --days 30 --minimum-options 5
```

Each brief reference must resolve to its complete authorized payload. These examples do not authorize executing historical tasks.

## Evidence and alternatives

| Candidate | Assessment |
|---|---|
| Broaden `/continue` | It could carry the full new brief, but would conceal the distinction between advancing selected work and requesting a new content deliverable. |
| `/draft` | Useful for review-stage output, but can narrow a specifically requested final artifact. |
| `/compose` | Names content authoring while preserving the requested maturity and output form. Proposed here. |

The two post-first supporting positions are **N07.2** (the previously reviewed naming matrix) and **A06.3** (a new editorial options brief). Three PDF tasks are explicitly separated as initial-task controls. Handoff, audit, planning, codification and display contrasts preserve their existing operations. See [the complete retained contexts](authoring-boundary-review-v1.md).

The recorded outcomes differ: one reply reports a created matrix and display; the editorial reply supplies a plan rather than the full options artifact. Shared intent is not successful delivery, and neither source is a runtime command-substitution test.

## Operation index

| Name | Operation |
|---|---|
| /continue | Advance the current authorized work |
| /plan | Produce a durable execution plan |
| /status | Report current evidence |
| /next | Derive the next useful action |
| /explain | Clarify a term, behavior or result |
| /review | Evaluate an artifact or claim |
| /verify | Test whether a claim is true |
| /fix | Resolve a named defect |
| /correct | Change the working interpretation |
| /approve | Grant bounded authority |
| /choose | Select an offered alternative |
| /ship | Advance publication |
| /apply | Apply a selected change |
| /closeout | Resolve session obligations and prove release |
| /context | Supply evidence or a report |
| /handoff | Prepare or send a bounded continuation |
| /watch | Observe an assigned native session |
| /codify | Make an accepted lesson persistent |
| /recall | Retrieve earlier exchanges with original source references |
| /open | Display an existing artifact in the requested application |
| /goal | Create or update a persistent execution objective |
| /compose | Author a requested content artifact from a bound brief |

## Version and validation

V2 evaluation and V5 contracts remain unchanged. The existing private HTML catalog embeds V5; V6 is reviewed through this note, its JSON contract and the source comparison until admitted regeneration occurs. It is not an installed command pack.

Checks bind the new operation to its two post-first source positions and keep all original contracts, valid aliases, payload/stage distinctions, local links and source namespaces intact. Independent substitution, broader source/emitter reconciliation, original pre-retention and logical-session completeness, remaining corpus coding and the owned capture repairs remain unproved. The full goal is active.
