# Source of Truth and Local Cache

> Relocated verbatim from `AGENTS.md` (2026-08-06) under the instruction-surface byte budget
> (`institutio/governance/gates.yaml` → `instruction_surfaces`, check S). The binding stub in
> `AGENTS.md` points here; this file is the full doctrine.

For GitHub, profile, repo inventory, credential, and public proof surfaces, the remote owner is the
source of truth. A local checkout is a disposable cache or staging area; it is not the golden state.

- Read remote state first through the GitHub API, live deployed endpoint, pinned issue, or owner repo
  receipt before trusting a local clone.
- If local work is required, create it in an isolated worktree or scratch lane, push/open the remote
  receipt, then reap the local cache once lifecycle custody is proven.
- Reap a local worktree once it is clean, inactive, and its exact HEAD is reachable from a remote
  ref. A pushed branch or open PR is durable custody for the disposable checkout; the unresolved
  delivery lifecycle remains owned by that remote receipt until it merges or closes.
- Do not fall back to local files when the canonical object is remote and queryable.
- Do not let local clone presence, local profile copies, or stale generated artifacts define public
  truth. If a remote cannot be updated, record the owner repo, missing gate, and next command.
- Do not generalize one failed GitHub surface into "GitHub is blocked." A zero-step hosted Actions
  job, including a runner-allocation or billing annotation, describes that exact execution surface;
  it does not make repository/API/PR custody unavailable and is not by itself an external stop
  condition. Verify live permissions and current receipts, continue every available local or remote
  predicate, and name the narrow failing surface without stalling unrelated closeout work.
