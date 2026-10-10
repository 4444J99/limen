# Recovery admission implementation checkpoint

Owner: this Limen change and 4444J99/ops#6; quota source owner: 4444J99/domus-genoma.

The exact prior rejected ops work key is `ops6-coordinate-20261009`. Owner-held
policy source was located at the previous successful policy installation; the local
empty observe-only projection was not used or changed. Authenticated live GET of
`/api/conduct/execution/policy` returned HTTP 404. See policy-admission.json.
This proves the readback capability is unavailable, not that administrator
credentials are unavailable. No policy replacement, capacity reservation, native
subagent, deployment custody or production apply occurred in this attempt.

The added readback returns only a canonical policy fingerprint and deployed runtime
identity to authenticated conductors. The additive reconciler refuses a mismatched
owner source and preserves unrelated priorities and every existing limit. After
the readback is deployed, the next owner operation is the reconciler with the
existing source, exact work key and `--install`, followed by bounded broker admission.
No installation is safe before matching that generation. The installation rechecks
generation immediately before the existing headless Wrangler secret route; provider
secret installation has no CAS, so deployment custody must exclude concurrent writers.

`scripts/ops6-recovery-graph.py` produces a canonical fanout manifest for serial,
read-only preparations with an explicit original deadline. It reserves and launches
nothing. Deployment is separately gated through accepted ops source
08d493caf5cf6fe7a64cbb67f6ed7e6b07ea119e and pinned runtime
62469ec5b402460a5610145e67901fcdd0ca00b9. C records unavailable window evidence
without sleeping or renewing a deadline. Hosted ALREADY_DEPLOYED and full incident
acceptance remain independently unproven.

Storage now separates capacity pools and shares APFS container restrictions. Missing
mounts fail explicitly. The internal legacy latch remains authoritative. The additive
repair command requires keeper-installed recovery authority, reserves durably,
checks estimated and actual allocated bytes, and preserves ambiguous failures.
Ordinary thresholds remain 50/200 GiB. Retained state is not an automatic release.

Live Domus observation at approximately 00:08 UTC found Codex at 12,896,141,528 bytes
against 12,884,901,888 bytes; all runtime vendors totaled 18,635,649,844 bytes against
25,769,803,776 bytes. These sizes are apparent quota bytes, not physical recovery.
No inactive downloaded release directory exists in the observed Codex runtime.
History restoration/replica acceptance was not established, so history, databases,
sidecars and partials were retained. Quota reduction: zero; physical recovery:
zero claimed. Native history retirement remains with the existing custody owner.

Two small isolated source checkouts were created under the implementation instruction,
using existing Git stores, sparse paths and no clone. They are retained as PR-owned
implementation checkouts; no prior checkout or peer process was altered. The initial
isolation was manual under this instruction, not attributed to the new repair adapter
or a broker lease. Allocation measurements and verification are recorded alongside
the PR publication. Broader code deployment and ops acceptance remain open.

Final verification and delivery measurements are in [verification.json](verification.json).
All 14 scoped cheap gates passed with the pinned toolchain. The scoped heavy wave
returned exit 75 on `swap-fraction,disk-throughput`; no override was attempted.
Limen owner: https://github.com/4444J99/limen/pull/2840 (draft).
Domus owner: https://github.com/4444J99/domus-genoma/pull/415; the targeted managed
runtime file is applied with empty post-apply diff. Its exact-head merge submission
returned `DEFERRED — LIFECYCLE-UNKNOWN`; it was submitted once, without polling.
