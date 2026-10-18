# Native sequence study: source reconciliation and vocabulary v2

Owner: [#3056](https://github.com/4444J99/limen/issues/3056). Publication and source-repair receipt: [#3087](https://github.com/4444J99/limen/pull/3087).
This is progress toward the original study, not a completion claim or installed command pack.

The private catalog places one captured file sequence in each column. Search selects whole sequences;
it never removes intervening prompts. Compare selected sequences or all matching sequences. Original
prompt text is retained, with native line references, body-retention flags, and recorded assistant
replies. Replies remain historical claims. The opener is a candidate until lineage is established.

| Current observation | Evidence |
|---|---:|
| Native Codex files inventoried | 1,517 |
| Compressed archive files | 1,308 |
| Header-classified direct candidates | 509 files / 503 IDs |
| Header-classified delegated / fork files | 973 / 35 |
| Direct candidate files visited by streaming extraction | 509 |
| Captured multi-prompt files / prompt rows | 383 / 3,493 |
| Files with fewer than two candidate prompts | 100 |
| Files exceeding explicit source bounds | 26: three unit limits, 23 record limits |
| Catalog after study-session exclusions | 381 Codex file sequences / 3,486 prompts |
| Independently read Claude configuration example | one file / 11 prompts |
| Catalog total | 382 columns / 3,497 prompts |
| Contextual candidate annotations | 51 follow-ups across 11 file sequences |
| Catalog Codex files marking every retained body complete | 70 |

These are file-level observations, not 503 proven complete human sessions. The streaming recipe has
a 128 MiB decompressed unit limit, a 4 MiB record limit, a 200,000-record limit, a finite tranche
deadline, and source-change detection. The 26 failures remain failures, not passing empty sequences.
The earlier 8 MiB experiment is superseded for coverage by this streaming extraction; its original
snapshot remains available for the eight closely reviewed columns.

The current history file contains 415 session IDs and 2,247 entries. Its IDs overlap 383 native-header
candidate IDs; 32 history IDs have no corresponding rollout header. Of 383 captured multi-prompt
files compared by exact stripped text, 142 match the history sequence exactly and 252 match its first
captured prompt. The earlier exploratory 562-session / 3,863-entry figures are not current counts.
History is not promoted into proof of native order, authorship or original-opener retention.

A read-only, query-only inspection of the native history projection found user items for 21 of those
32 missing rollout IDs (100 projected user items). Eleven had none. Projection presence does not
prove completeness or recover a missing body. This additional source is not yet integrated into the
catalog. Native stores, WAL files and compressed archives were not changed.

## Converged vocabulary

[vocabulary-v2.json](vocabulary-v2.json) reconciles this session's 17 candidates with the 12 contracts
read directly from published PR #3067 at head 4656b15e. No sibling checkout was adopted or used for
verification.

The 18 proposed operations are: /continue, /plan, /status, /next, /explain, /review, /verify, /fix,
/correct, /approve, /choose, /ship, /apply, /closeout, /context, /handoff, /watch and /codify.

Modifiers preserve differences without multiplying bare verbs: a selected plan and a completion
stopping condition remain arguments to /continue; retry requires the original attempt plus changed
evidence; an archive question is a read-only verification target; an operator result remains
attributed context. Publication stages and applying a change retain separate contracts.

The independently read Claude example confirms why selection and publication cannot be flattened:
choosing an offered behavior, merging its PR, applying its configuration and observing the running
consumer are distinct. The same next-action question also produces different operator actions as
evidence changes. A shared intention does not imply an identical fixed outcome.

Every command contract preserves operation, target, payload, authority, constraints and completion
evidence. New domain content remains content. These are contextual reconstructions, not blind
held-out validation; candidate annotations on incomplete bodies remain provisional. Most follow-ups
are still uncoded. No whole-corpus equivalence or replacement percentage is claimed.

## Reproduction and evidence

Run the research recipes from this owned checkout. They require the retained private snapshots
and bindings; compressed reads use the host Python standard library's Zstandard support.
The original native inputs and the generated derivatives remain in their existing private owners.

- capture-native-review.py records the bounded eight-sequence archive tranche.
- capture-native-stream.py records the broader bounded Codex extraction from the private header index.
- render-native-review.py binds annotations to unchanged source bytes and renders the eight-column review.
- render-native-catalog.py renders the searchable private catalog and the 18 contracts.
- check-native-catalog.cjs checks the actual rendered data and selection logic without a browser.

The eight-column check preserved all 43 captured prompt bodies. Catalog checks preserved all 3,497
displayed prompt bodies and rendered all 382 selected columns. JavaScript syntax, scoped Python
lint/formatting and credential-wall checks passed. Browser visual inspection is unverified: local-file
navigation was denied and no alternate browser transport was used.

Private derivatives are retained in this session's owned worktree with #3056 as their work owner.
No copied transcript, raw prompt body, native path index or generated HTML is published to Git.
This is not independent custody proof or retirement authorization.

The original finish line remains: reconcile full native lineage and retained bodies, inspect remaining
source failures and projection-only sessions, code follow-ups in their full session context, and test
substitutions on held-out whole sessions. Installation also needs provider collision checks.
#3087's source repair, full repository gate, merge, live deployment and two successful release checks
remain separate unfinished requirements; the scoped gate was again denied by host swap admission.
