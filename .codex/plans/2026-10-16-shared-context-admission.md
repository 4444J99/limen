# Bounded shared-context deployment admission

Implement the missing lane-neutral admission capability for the existing Domus shared-context deployer. Keep the runtime as policy owner and Domus as file/template owner.

1. Recognize only the canonical installed executable, with secure owner/mode checks and an exact source-revision identity bound by the signed plan. Plan and verify remain zero-write operations.
2. Bootstrap only the deployer and its shared authorization module through a bounded source-owned path. Bind before-images, content hashes, source identity and deadline; reject arbitrary executable paths, lookalikes, destination overrides and unrestricted chezmoi application.
3. For apply, verify the existing exact-plan host-mutation authorization before admitting external destinations. Preserve the worktree writer and machine-wide heavy gates. Do not turn arbitrary shell commands into sanctioned controls.
4. Add focused adversarial tests for forged/expired/mismatched signatures, changed source or installed bytes, symlinks, extra arguments and destination expansion. Wire implicated gates through the existing scoped resolver.
5. Submit the verified head once through governed merge; install the exact merged immutable runtime through the existing Domus lifecycle. Prove installed capability before live deployment.
6. Run the existing Domus plan/apply/readback sequence, converge its configured source without touching unrelated edits, and verify every declared consumer and supported child route through private owner receipts.

This plan is an implementation contract, not a deployment or retrieval receipt. Preserve predecessor artifacts and original packet hashes. No source history is deleted. Account-memory and project retrieval remain separate acceptance surfaces. No new model worker or background schedule is launched.

The admitted attempt retains its original deadline and resource reservations. A later bounded attempt must use changed implementation evidence and the same outcome history; it must not silently reset cumulative usage.
