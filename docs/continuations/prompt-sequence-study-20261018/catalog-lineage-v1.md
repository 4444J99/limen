# Lineage in the native comparison

Owner: [#3056](https://github.com/4444J99/limen/issues/3056); publication: [draft #3087](https://github.com/4444J99/limen/pull/3087).

The existing private native comparison now includes the 37-view
[fork-boundary census](native-prefix-census-v1.md). Its lineage panel displays declared parents,
local source lines, matching reader positions and the scope of the evidence. It retains the
eight shared-turn ambiguities and two prefix limits.

Seven of the thirteen declared parents already have captured file columns. Those columns now
show their fork aliases and can be found by searching a fork alias. Existing source aliases stay
intact; otherwise the derived parent alias labels the column. The six parents outside the file
columns are visibly identified. Fork-only payloads are not copied into the raw file columns.

The panel also shows the supported M24/R01 boundary of seven context inputs and 26 local inputs,
including the parent capture's two retained-body gaps. The full reader view and the local file
sequence remain distinct units.

The owning generator reads the public census plus existing private identity bindings and compiles
a small metadata overlay. The actual private artifact received that same overlay and the matching
render/search changes. The immutable embedded dataset stays unchanged: 382 file columns and
3,500 original prompt rows. V5's twenty-one proposed operations and the six managed-input labels
are unchanged.

## Verification

The augmented structural check first failed because the lineage display had no rows.
After the update it executed the actual embedded runtime in a bounded Node VM and verified:

- All 37 lineage rows, including 19 declared forks, eight attribution gaps and two prefix limits.
- Seven captured parent columns carrying the correct fork relations.
- Search by M15 finding and rendering the captured P06 parent.
- The M24/R01 segment note and the seven-of-thirteen parent-coverage statement.
- Original default selection and full selection, all 3,500 retained prompt texts, the V5 glossary,
  shared-turn indicators, derived frames and six managed-input labels.
- Unique required element IDs in the actual HTML, rather than only elements in the test harness.
- Exact equality of the displayed metadata module to the owning template plus evidence.
- Byte-for-byte dataset preservation by SHA-256 comparison; the fingerprint stays private.

A harness escaping error in the new markup-ID assertion was corrected before it passed.
The private artifact's dataset and all original sources were preserved throughout.

Reproduce the structural check with
`node check-native-catalog.cjs /absolute/path/to/private/native-catalog.html`
from this directory. This remains structural execution, not browser visual inspection.

A read-only Python AST check was attempted, then its rejected multiline command was normalized
to one command. Host admission rejected that command as shared-checkout-write. The check was
not executed through another interpreter or transport. Full generator execution, Python syntax
validation and the full scoped gate remain unverified under the existing source/cwd admission
hold. The source-owned process-contract bootstrap still requires an approved execution work key;
this checkout has no workstream registration supplying one. No second independent-review packet
was submitted.

The raw view's partial coverage, unresolved native histories, independent semantic review and
runtime substitution acceptance remain open. No installation, merge, deployment or session-release
success is claimed.
