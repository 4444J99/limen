# Catalog metadata update

Owner: [#3056](https://github.com/4444J99/limen/issues/3056); publication: [draft #3087](https://github.com/4444J99/limen/pull/3087).

The existing private comparison now displays the 19 V4 operator contracts, including their
targets, constraints and completion evidence. Its V2 glossary remains visibly historical.
Column U3 identifies the source of six managed recovery inputs; positions 5 through 10 are
labelled as excluded from operator-intent evidence, with their original text retained.

The generator reads the current vocabulary and existing private provenance bindings.
A small overlay applies the labels after the immutable embedded dataset is parsed.
The current private artifact received the same metadata update without invoking the renderer.
No new transcript copy or public transcript body was created.

## Verification on 2026-10-19

The augmented checker first failed on the missing current vocabulary. After the update it
executed the actual embedded catalog script in a bounded Node VM and passed:

- 382 columns and all 3,500 original prompt rows rendered structurally.
- The displayed current operation names exactly match all 19 V4 contracts.
- U3 has 10 retained rows and exactly six managed-input labels at positions 5 through 10.
- Default selection, full selection, shared-turn and derived-frame indicators remain checked.
- SHA-256 equality of the embedded dataset before and after confirms byte-for-byte preservation.
- Git whitespace checking passed.

Reproduce the structural check from this directory with
`node check-native-catalog.cjs /absolute/path/to/private/native-catalog.html`.
The private artifact and bindings stay in the existing private study location.
The renderer has not been executed and browser appearance has not been inspected.
The full scoped gate remains held by the previously filed host-admission/source-cwd condition;
the current status still reports vitals-shed. No full-gate, merge, deployment, installation,
independent substitution-validation or session-release success is claimed.

The source-recovery census and newer contextual review remain supplementary linked evidence.
Their shared-history/original-opener gaps are not converted into additional independent columns.
The original goal and its remaining acceptance requirements stay open under the owner above.
