# Current evidence and next checks

Re-read live main, push CI, installed runtime receipt and launchd state. Read heartbeat receipts;
do not fire extra probes merely to accelerate scheduled adoption.

## Immediate host defect — owner Limen #2664

The user captured an sfltool administrator dialog. The installed background-items census calls
`sfltool dumpbtm` automatically in build_report. Its historical claim that the command is
unprivileged is contradicted by the current host experience. No active sfltool PID was captured
in the read-only process census, so a specific prompt/process parent was not established.
Next: repair scheduled census to avoid interactive privileged collection, retain LaunchAgents
classification and explicitly report missing BTM measurement. Preserve a supported intentional
BTM inspection path. Test that the scheduled invocation cannot launch a modal auth command, then
verify the owning source/deployment/runtime receipts. Do not dismiss the defect as user consent.

## Integration owners

- Relay: https://github.com/4444J99/organvm-ci-relay/issues/3 and PR #30. Exact candidate
  8d270867578fb8696578c20167ea0abe4b865238; frozen .github/workflows change causes admission failure.
  Main unprotected and rulesets empty at last read. Never merge around that trust boundary.
- Credential/signing automation: https://github.com/organvm/domus-genoma/issues/385.
  PR #386 merged and op-unattended installed. Local signing and isolated governor binding are not proven.
- Shared template/dependency completion: organvm/.github PR #26 (draft).
- Schema prerequisite: organvm-iv-taxis/schema-definitions PR #19 (ready, open).
- Registry: organvm/organvm-corpvs-testamentvm PR #553 (draft); Editorial PR #12 (draft).
  Engine #175 merged; reader pilot Limen #2553 remains draft. No additional reader pilot.
- Laurea PR #10, alchemical-synthesizer PR #47, learning-resources PR #11, public HOSPES PR #1:
  published, open; exact-head receipts remain in each owning PR. Do not repeat old submissions.
- Private HOSPES portal hardening: source and full clean-worktree done predicate are recorded
  in its private owner PR. That owner retains the exact head and integration failure/readback;
  private code and evidence must stay there. Do not conflate private operations and public face.
- Preservation: Limen #2614 owns custody. Six local checksums are not whole-estate restore proof.

Routine inventory growth remains contained; 250-item ceiling and 900-second freshness are
unchanged. Broker state owns tasks, claims and receipts. Register direct sessions as protected.
