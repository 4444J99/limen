# Native prefix and fork-boundary census

Owner: [#3056](https://github.com/4444J99/limen/issues/3056); publication: [draft #3087](https://github.com/4444J99/limen/pull/3087).

The [machine-readable census](native-prefix-census-v1.json) binds 37 additional recovered views
to current native-file metadata. Nineteen explicitly declare forks with thirteen distinct
parents. This supplies lineage evidence for shared history; the views must not be treated as
independent original sessions.

| Check | Result |
|---|---:|
| Current metadata fingerprints match the retained index | 37 / 37 |
| First local candidate prompt read within the prefix bound | 35 / 37 |
| Candidate turn matches the reader's first user turn | 18 |
| Candidate turn matches a later position in the reader view | 17 |
| Candidate remains unread at the compressed-prefix bound | 2 |
| Explicit fork declarations | 19 |
| Distinct declared parents | 13 |
| Fork cutoff mirrors agree where both are present | 17 / 17 |
| Older fork records lack one or both cutoff fields | 2 |
| Multiple reader inputs share the candidate's turn | 8 |

The two older metadata shapes are missing information, not conflicting cutoffs. One names
only its parent; another declares its history-base cutoff without a duplicate fork-ordinal
field. All seventeen records with both cutoff fields agree. The parent labels in the public
receipt are redacted references, not native IDs.

The original reader census had 44 exhausted views. This tranche excludes L08 and L22, whose
[opener bodies were already matched](native-prefix-lineage-v1.md), and prospective independent
holdout L05. Four other views lack a bound source header or a visible input and remain explicitly
outside this prefix join. These exclusions account for all 44 views.

## What this changes

For seventeen fork views, the first retained local candidate's turn maps later in the full
reader view. Whole-view pagination and the fork's own prompt sequence therefore describe
different units. Keep the inherited context and local segment linked while counting them
separately. Two declared forks already start at the reader's first user turn; that observation
does not prove that their parent histories were fully returned.

Turn identity alone does not identify a user item inside a shared turn. The eight affected rows
retain every matching reader position. This tranche does not promote those matches into exact
prompt-body equality or collapse shared inputs.

The previously reviewed control source M24, labelled R01 in its semantic review, now has stronger
boundary evidence. Its first local candidate is source line 7, and its complete 329-character
body and native turn match reader input 8. The seven preceding input turns exactly match the
existing parent capture's turn order. Every captured parent prompt ordinal lies before the
declared exclusive cutoff 607. The local visible segment contains 26 inputs.

This establishes the retained parent/local segmentation used by the earlier R01 review. It does
not establish complete original text: the parent capture marks its first two input bodies as
incomplete, and this tranche did not independently verify every byte of the declared parent
prefix. Those gaps stay visible.

## Bounds and verification

Reads were sequential and in place. Each was bounded by a five-second deadline, a 2 MiB decoded
prefix, 256 records, and the unchanged 4 MiB original record ceiling. Source inode, size and
modification time were checked before and after. No transcript or instruction body was copied.

An actual bound defect was detected before publication: the first L13 and L15 attempts consumed
one extra 16 KiB compressed-input chunk before their threshold check stopped them. Their failed
attempts remain in the receipt. One corrective read per source changed the stream itself to
end at byte 1,048,575. Both then stopped at exactly 1 MiB and still could not supply a complete
candidate prompt. The correction proves the hard input bound, not successful source recovery.
Neither original bulk-capture limits nor the unresolved source dispositions were relaxed.

Counts, unique aliases, source/turn joins, fork-field agreement, shared-turn ambiguity and the
R01 parent/local boundary were checked against the retained private bindings. The public rows
contain no private paths, native identifiers, raw prompt bodies or full source fingerprints.
No semantic dispositions or vocabulary contracts changed in this tranche. Independent review
remains blocked at the [recorded broker admission](independent-review-admission-v1.md).
