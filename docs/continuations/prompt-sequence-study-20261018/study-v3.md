# Native sequence study v3: reply attribution and source holdout

Owner: [#3056](https://github.com/4444J99/limen/issues/3056). Source/publication lane: [#3087](https://github.com/4444J99/limen/pull/3087).
This revision corrects the research reader and tests the frozen 18-operation draft. It does not claim
whole-corpus equivalence, command installation, successful session release or runtime deployment.

## A source defect changed the outcome evidence

The v2 reader grouped all assistant replies until the next retained human prompt. That incorrectly
absorbed replies to intervening automatic goal frames. In H2, one human opener acquired six replies;
five actually belonged to separate automatic continuations. Two later human reports shared one native
turn, so assigning the reply to only the later report was also wrong.

The reader now binds replies using native message turn IDs. It preserves derived frames separately,
marks multiple human inputs sharing a turn, and labels missing native bindings as adjacent-unbound.
No source limits were increased: 128 MiB per decompressed unit, 4 MiB per record, 200,000 records and
a finite tranche deadline remain enforced. Transport echoes are counted separately, not promoted.

Replay visited all 509 direct-session candidate files again. It captured 383 multi-prompt file
sequences and 3,496 prompt rows. The same 26 source limits remain: three unit bounds and 23 record bounds.
382 captured source files have identical bytes to v2; one active source grew by three prompts.
On unchanged sources, 607 prompt/reply associations changed. No captured prompt text changed in that
comparison. Across the replay there are 641 shared-turn prompt records and 1,211 adjacent-unbound
records; these remain visible limitations, not independent outcome confirmations.

The private catalog now contains 382 displayed file sequences and 3,500 prompts: 381 Codex files
after excluding the captured study sessions, plus the independently read 11-prompt Claude example.
The original snapshot and source selection remain retained privately.

## Frozen source holdout: nine whole retained-input sequences

The vocabulary file was frozen before selection. A fixed seed selected three sequences each from
home, Limen and other directories. Previously previewed or contextually coded examples were excluded.
Eligibility required 2-6 retained prompts, explicit complete-body flags, no media, one metadata record,
and the first retained input within the first 32 source lines.

There were 30 eligible files; nine were selected. All 36 prompt bodies were read in session order,
including the 27 follow-ups, preceding proposals and recorded responses. The replay verified unchanged
source bytes and unchanged human prompt text for all nine selected files.

This is a single-coder contextual reconstruction on held-out source files. It is not a blind,
independent-reader test or a runtime replay. File-level retention evidence still does not prove that
every logical session and original opener has survived.

[substitution-review-v1.json](substitution-review-v1.json) records every follow-up:

| Required representation | Follow-ups |
|---|---:|
| Control with an unambiguous inherited target | 15 |
| Operation plus retained evidence/domain payload | 6 |
| Multiple operations and publication/acceptance stages | 2 |
| Explicit authority or allowance binding | 4 |
| Total | 27 |

These categories are not a replacement-rate estimate for the corpus. Even the first category retains
the existing objective, authority, constraints and stopping condition. The 18 operations remain
provisional; no contracts were edited during the frozen evaluation.

Important counterexamples:

- H2.2/H2.3 are peer reports, not new approval. Their payloads and provenance must survive, and
  their one shared reply cannot prove two independent per-prompt outcomes.
- H3's diagnostic reports must retain the earlier finalization conditions. A green summary is not
  by itself new blanket authority or an independent witness of every prerequisite.
- H4.3 and H5.4 request a policy exception. Generic continuation or ordinary approval would lose
  the exception target, duration and preserved gates.
- H5.2 supplies a new allowance value in answer to a question; it must not reset prior accounting
  or silently become approval for unrelated scope.
- H5.5 names three merges plus continued engineering and a restricted operator handoff. One generic
  publication verb would omit part of that operation list.
- H9.5 changes an allowlist. The actual delta and its scope must remain explicit.

A slash vocabulary can shorten repeated control language. It cannot erase substantive new content,
unresolved authority or the difference between intended action and recorded result.

## Projection adapter: tested, live capture denied

A target-bound native SQLite adapter now has a cheap registry gate. Nine isolated fixture tests
first failed before implementation, then passed. Three native-rollout attribution tests were added,
failed before the decoder existed, and passed after implementation: 12 tests pass in total.

The tests cover exact text/structured references, late replies, shared turns, retained source gaps,
derived frames, unknown schemas, ambiguous order, target-only read-only SQLite access, UTF-8 byte
bounds, transport echoes and unbound native attribution.

The live projection capture was denied by the host hook as write-target-outside-worktree: its
external database input was treated as a write target. This denial was not bypassed. The adapter
has not recovered the 26 limited files or the 21 projection-only session sources. The earlier
presence probes remain presence evidence, not completeness or recovery receipts.

## Verification and outstanding acceptance

The gate registry validates with its existing unjustified API deploy-trigger note. Scoped fixture
tests, Python lint/formatting and catalog render-logic checks are the bounded local evidence.
Catalog checks preserve all displayed prompt text and explicitly expose attribution states and
derived frames. Browser visual inspection remains unverified after the earlier local-file denial.

The original task remains open: inspect unresolved native sources, establish logical session lineage,
code the remaining follow-ups in context, and obtain independent substitution review. The four
authority-sensitive cases need binding/contract work before executable substitution. Installation
still requires provider collision checks.

The process-ownership repair and #3087's full scoped gate, exact-head merge, live installation and
two successful native-anchor closeouts remain separate requirements. The owning policy bootstrap
was investigated further: two retained owner-policy candidates fail the authenticated live
fingerprint check. Neither was installed or treated as current authority.

All raw sources, derived frames, selection manifests, payload bindings and generated HTML stay private.
This worktree remains retained under the existing owner; no retirement or independent custody claim
is added.
