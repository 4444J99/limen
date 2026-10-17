# AI context migration and Agent runtime audit skills

Requested outcome: two discoverable skills grounded in the supplied Computer
History summaries and their cited 2026-10-16 event segments.

Scope: author reusable instructions, supporting formats and redacted provenance;
validate their structure and decisions; publish their source and install exact
copies into the active Codex skills directory. Do not execute a migration, runtime
cleanup, configuration cutover, or history-settings change.

Source home: Limen .agents/skills in an isolated branch from current origin/main.
The active vendor skill directories are installed copies, not canonical sources.

Plan:
1. Inspect recorded events and distinguish user actions from displayed reports.
2. Author both skills with useful references and Codex discovery metadata.
3. Validate structure and independently exercise realistic scenarios.
4. Commit/push the scoped source, create an owned PR, and verify installed bytes.

Acceptance: both skills pass the bundled validator; metadata and reference links
resolve; behavioral scenarios preserve authorization and evidence boundaries;
source is remotely recoverable; installed copies match source hashes.

Checkout retention: retain the source worktree while its PR is open. No retirement
or unrelated worktree cleanup is included.

Validation completed on 2026-10-16: both bundled skill validators passed using
the installed Limen Python environment. UI metadata, automatic discovery defaults,
relative references, and portable paths were checked. The scoped repository gate
passed diff hygiene, changed-file syntax, and note links. An independent read-only
review exercised four synthetic scenarios: export/compare without import authority,
plan-only runtime audit, an authorized import with unknown outcome, and a local
dry-run adapter with hidden writes and lost errors. No actionable defects were found.

Installation completed: each skill has four regular files in the active Codex
skills directory, with every file hash matching its source. No symlinks were
created. This verifies installed files, not a hot reload in an existing chat.
