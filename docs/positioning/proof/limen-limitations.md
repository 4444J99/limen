# Limen — Limitations

- **Host Admission Overload:** In high-concurrency environments, rigorous execution constraints like `verify-whole.sh` can be throttled or rejected by host admission rules (e.g., memory swap-fraction limits).
- **Not Customer Adoption:** The ability to execute autonomous routines at scale proves technical orchestration capability, but does not equate to commercial adoption or active customer usage metrics.
- **State Complexity:** Tracking and merging concurrent worktrees requires strict adherence to `TABVLARIVS` projection. Any out-of-band edits can invalidate task state.
