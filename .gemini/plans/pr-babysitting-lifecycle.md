# Task Worktree & PR Babysitting Lifecycle
**Date:** 2026-06-01

## 1. Worktree Isolation
Instead of cloning or checking out branches in the main repository checkout, the Conductor Swarm will spawn tasks in isolated git worktrees.
- Command: `git worktree add ../<task-id> -b <task-id>`
- Ensures parallel tasks do not conflict in the working directory.

## 2. PR Babysitting Loop
The agent responsible for a task will not just push and exit. It must:
1. **Open PR:** Use the GitHub tool to `create_pull_request`.
2. **Watch Status:** Poll `pull_request_read` (method: `get_status` and `get_check_runs`) to monitor CI checks.
3. **Address Comments:** Poll `pull_request_read` (method: `get_review_comments`). If comments appear, apply fixes to the worktree, commit, and push.
4. **Merge:** Once CI passes and comments are resolved, use `merge_pull_request`.
5. **Report:** Use a notification tool (or generate a local report file) to document the successful merge and notify the owner.

## 3. UI Dashboard Updates
- The dashboard at `web/app/app/page.tsx` has been updated to hyper-link all IDs, titles, repos, branches, and CI statuses directly to their GitHub counterparts, providing complete traceability for the babysitting process.