# Complete delivery workflow verification and merge

Supersedes the incomplete validation receipt in the original plan. Owner: gitvs / PR #2873.

The operator explicitly authorized hosted verification after native local host admission denied the retry for swap pressure. The host guard remains unchanged. The hosted run on bd7d082140437a50969b428d91467b52567c61da completed the CLI suite with 8,686 passed, 67 skipped, and one failure: the audit deadline fixture assumed a real macOS LaunchServices executable existed on the Linux runner. API verification had not started when that gate stopped.

1. Make the audit fixture provide the macOS executable-presence boundary, while retaining the real deadline logic. Assert that the first command receives the remaining two-second budget and the next command is never spawned after exhaustion.
2. Run the focused regression, publish the correction, and complete the normal hosted scoped gate on the final head. Earlier unchanged green shard receipts remain evidence; the existing PR workflow provides the remaining API proof and the corrected CLI result.
3. Disclose the separate MCP lock dependency-audit finding in issue #2874; do not suppress it or bundle an unrelated dependency update into this workflow fix.
4. Mark the PR ready only after the outstanding tests pass. Exercise the guarded delivery classification on this exact PR head, read the label back, and merge through the registered single-owner fast lane with the exact-head condition. Record positive remote merge proof.

Retain /Volumes/Archive4T/limen-pr-delivery-20261016 and its topic branch. The protected shared primary checkout remains untouched. No cleanup or custody retirement is authorized by this verification retry.
