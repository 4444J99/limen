# Final rollout corrections

Limen #2851 merged and immutable revision `218b5ed1d5f50705b77adf16aca8712baf9cdbb3`
installed at 23:47:05Z. The normal activation smoke test correctly rejected the first
observer fire: launchd does not inherit the login shell's explicit migration root.
Reproduce with an empty environment; repair the owning observer contract to select
the reviewed root explicitly through both aliases. Keep Domus containment checks,
source hashes, bounds and kill switch unchanged. The repaired empty-environment live
observation passed at 23:51:55Z with no worker request and positive shared headroom.

Hosted CI became available and exposed real dependency-audit failures; the earlier
account gate is historical, not the current cause. Raise compatible patched floors
for Next, sharp and source-map-js, refresh both locks and run the unchanged audit gates.
No advisory exceptions or capability omissions are authorized. Both audits passed.

Focused regression suite: 58 passed. All twelve implicated cheap registry gates pass.
Keep the broad admission result explicit. Merge the exact correction head, install its
accepted revision, activate through the reviewed Domus lifecycle, then retain the
controlled and naturally scheduled heartbeat receipts plus independent readback.
Update #2848 to the actual remaining platform/evidence boundaries, preserving its
historical record. No additional storage recovery, native history mutation or unrelated
product implementation is included.
