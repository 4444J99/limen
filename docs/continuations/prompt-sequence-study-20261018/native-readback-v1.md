# Native readback: provenance correction

Research owner: [#3056](https://github.com/4444J99/limen/issues/3056).
Publication owner: [#3087](https://github.com/4444J99/limen/pull/3087).
This corrects the evidence behind [the longer-sequence review](long-sequence-review-v1.md).
It does not replace the frozen source snapshot or claim the whole study complete.

## What the native readback establishes

The supported chat reader returned all pages for U1, U2 and U3. U1 has five native turns
containing seven user-role items; one turn is interrupted and contains three inputs.
U2 has ten completed main-thread turns with ten inputs. U3 currently has fifteen turns:
thirteen completed and two interrupted. Its first ten inputs match the frozen snapshot and
five additional marker inputs have appeared. These are bounded current-view observations.

| Alias | Captured inputs | Current inputs | Captured prefix matches exactly | Captured turn bindings match | Current interrupted turns |
|---|---:|---:|---|---|---:|
| U1 | 7 | 7 | yes | yes | 1 |
| U2 | 10 | 10 | yes | yes | 0 |
| U3 | 10 | 15 | yes | yes | 2 |

All 27 captured prompt bodies and their native turn bindings match the current ordered prefix.
User-item identifiers differ between the rollout capture and supported reader for all 27 items.
The views therefore remain distinct identifier namespaces; item IDs alone are not a safe join.
The reader can render an interrupted turn's last commentary. That is not a completed result.

U3's old archived pathname is no longer present. The same session now has a native rollout
under its active date directory. The current native metadata declares VS Code/user origin
and paginated history. That thread-level origin does not establish who emitted every later item.
No thread was resumed, unarchived, messaged or otherwise changed by this study.

## Six inputs have managed recovery provenance

The source search found the exact marker generator in Domus's
`dot_local/libexec/domus-codex-history.py`, method `managed_probe` (lines 584-635 at the
inspected source revision). It calls the native turn-start API with the same literal-response
instruction, then saves each resulting native turn as a per-reader operation record.

The retained fixture names U3 as its target. One saved turn in the earlier managed attempt and
five saved turns in the subsequent attempt match all six captured U3 marker turns by exact
native turn ID and input text. Their ordering also matches the frozen capture. The source file
was clean at the inspected Domus revision; no Domus source or deployed file was edited.

This resolves the earlier authorship uncertainty for U3.5-U3.10 to managed recovery inputs.
They remain visible evidence. They are excluded from the operator-intent denominator and do
not justify adding an operator command. The five later current-view marker inputs have not
been individually bound to their own operation records in this pass; they remain separate
from the frozen six and are not silently counted as proven automation.

The source-level review still accounts for 102 post-first positions across 23 file sequences:
**six are now identified managed inputs; the other 96 remain candidate operator-context
positions**, including earlier incomplete-body and attribution limitations. This is not a
verified count of 96 manually authored prompts or successful substitutions.

[vocabulary-v4.json](vocabulary-v4.json) therefore contains **19 proposed operator operations**.
It retains recall and the plan/authority clarifications, and moves exact response out of the
primary set into an explicitly excluded technical example. V2 stays the frozen evaluation
baseline; V3 remains preserved as superseded research. No commands were installed.

## Side exchanges: secondary observation, not original native history

U2's native tool records show how the earlier assistant recovered the side questions: it read
Computer History events. One retained output contains an observed terminal question and its
Return event; another output contains progressively typed variants of the other question.
These are useful observations about text in the interface. They are not original native
side-turn objects or the complete side replies.

Current Computer History status is running. The specific historical segment referenced by
those tool records is now absent. The recorded tool-output copies remain in native history;
one large output is explicitly truncated. This study neither reconstructed the missing segment
nor treated a partial observation as the original complete side conversation.

The earlier statement that both exchanges were recovered must therefore be qualified by
source tier. Their themes and later influence on the main conversation are evidenced;
their full original native sequence, replies and fork lineage remain unresolved.
Recall must identify whether its evidence is original native content, an external observation
captured in native history, or a quoted reconstruction.

## Verification and remaining acceptance

The comparison of all 27 bodies and turn bindings was performed on the current reader output
against the retained snapshot. Six saved recovery-turn records were read and matched to native
turns. The fixture target was checked. Vocabulary checks require nineteen unique primary names,
absence of exact response from that primary set, and preservation of its exclusion record.

The old catalog remains a frozen 382-column / 3,500-prompt artifact; it has not been regenerated
under the denied execution surface. This note and the versioned vocabulary form the current
review layer. Native completeness, remaining corpus coding, independent substitution and the
original source-repair, full verification, merge/live and release predicates remain open.
