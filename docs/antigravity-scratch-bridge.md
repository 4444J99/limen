# Antigravity Scratch Bridge

Generated: `2026-07-07T13:12:27+00:00`
Scratch root: `~/.gemini/antigravity-cli/scratch`

## Decision

Do not delete Antigravity scratch roots by size alone. A root is only a review candidate
when this bridge proves it is clean, idle, and preserved on a remote/default-equivalent ref.
Physical deletion additionally requires a verified archive preservation receipt plus a
human acceptance/redaction-review event in `docs/antigravity-scratch-reap-acceptance.jsonl`.
The required acceptance shape is documented in `docs/antigravity-scratch-reap-acceptance.md`.
Dirty roots are `bridge_required`: their per-root delta must be carried home or archived
before any deletion.

`staged_deleted_count` in this receipt means Git observed files already missing/staged
inside a scratch clone. It is a preservation blocker, not authorization to delete the root.

## Summary

- Roots scanned: `55`.
- Total scratch size: `29.1 GiB`.
- Safe-reap candidate size: `88.2 MiB`.
- Dispositions: `bridge_required` 34, `container_review_required` 3, `keep_active` 12, `non_git_review_required` 3, `preserve_required` 2, `safe_reap_candidate` 1.

## Reap History

- Recorded reap events: `2`.
- Cumulative reaped roots: `24`.
- Cumulative reclaimed size: `6.9 GiB`.
- `2026-07-06T02:08:09+00:00`: `1` roots, `4.7 GiB` (`session-meta`).
- `2026-07-06T01:27:51+00:00`: `23` roots, `2.2 GiB` (`growth-auditor`, `the-invisible-ledger`, `organvm-corpvs-testamentvm`, `organvm_domus_genoma`, `persona-fleet`, `a-i--skills`, `prompt-registry-archive`, `portfolio`, ... +15).

## Preservation History

- Preservation receipts: `43`.
- External archives verified: `42`.
- Verified external archive source size: `23.7 GiB`.
- Event source size total: `28.4 GiB` (includes retries).
- `2026-07-06T04:03:42Z` `hello_workspace`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T040342Z-hello_workspace/receipt.json`.
- `2026-07-06T04:02:18Z` `hello_project`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T040218Z-hello_project/receipt.json`.
- `2026-07-06T04:01:13Z` `my-project`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T040113Z-my-project/receipt.json`.
- `2026-07-06T04:00:23Z` `organvm-vi-koinonia`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T040023Z-organvm-vi-koinonia/receipt.json`.
- `2026-07-06T03:59:38Z` `organvm-i-theoria`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035938Z-organvm-i-theoria/receipt.json`.
- `2026-07-06T03:58:40Z` `organvm`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035840Z-organvm/receipt.json`.
- `2026-07-06T03:57:39Z` `writelens`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035739Z-writelens/receipt.json`.
- `2026-07-06T03:57:06Z` `.github`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035706Z-github/receipt.json`.
- `2026-07-06T03:56:31Z` `sovereign--ground`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035631Z-sovereign--ground/receipt.json`.
- `2026-07-06T03:55:47Z` `organvm-ontologia`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035547Z-organvm-ontologia/receipt.json`.

## Repeated Staged-Missing Fingerprints

These roots have the same set of files already missing/staged inside their scratch clone.
That is a preservation blocker and duplicate-state signal, not deletion permission.

| Count | Roots | Staged missing | Same path untracked | Absent from worktree | Top staged buckets |
|---:|---|---:|---:|---:|---|
| `3` | `organvm-session-meta`, `session-meta-no-prompt`, `session-meta-2` | `2741` | `1451-2323` | `418-1290` | `claude:1269, codex:692, escape-velocity:339, scheduler:151, .claude:147, gemini:31, opencode:23, analysis:21` |

## Repeated Dirty Fingerprints

These are duplicate-looking unsafe scratch states. They still require bridge/archive proof
before any local root can be removed.

| Count | Roots | Staged missing | Untracked | Top buckets |
|---:|---|---:|---:|---|
| `2` | `anon-hookup-now`, `system-system--system--monad` | `0` | `1` | `(root):1` |

## Largest Roots

| Root | Size | Kind | Disposition | Reason | Remote / nested proof |
|---|---:|---|---|---|---|
| `organvm-session-meta` | `4.7 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/session-meta@2954214acb76` |
| `session-meta-no-prompt` | `4.5 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/session-meta@2954214acb76` |
| `session-meta-2` | `4.5 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/session-meta@2954214acb76` |
| `peer-audited--behavioral-blockchain` | `2.5 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/peer-audited--behavioral-blockchain@18e881f0a29f` |
| `a-i-council--coliseum` | `2.3 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/a-i-council--coliseum@fcacc4a1b202` |
| `sovereign-systems--elevate-align` | `1.2 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-iii-ergon/sovereign-systems--elevate-align@3ac45f92ba16` |
| `public-record-data-scrapper` | `1.0 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/public-record-data-scrapper@60f4c68a033f` |
| `growth-auditor` | `896.1 MiB` | `git` | `keep_active` | `idle-window-not-met` | `organvm/growth-auditor@93cad2b4974d` |
| `dot-github--theoria` | `650.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/dot-github--theoria@a96c76a24b52` |
| `organvm` | `632.4 MiB` | `container` | `container_review_required` | `nested-git-roots` | `bridge_required:3, keep_active:1, safe_reap_candidate:2` |
| `limen` | `559.2 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/limen@7aff62eb8ba1` |
| `the-invisible-ledger` | `468.1 MiB` | `git` | `keep_active` | `idle-window-not-met` | `organvm/the-invisible-ledger@2bd0d2ef29e0` |
| `mirror-mirror-healing` | `455.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/mirror-mirror@6491c27c636c` |
| `mirror-mirror` | `451.7 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/mirror-mirror@cd59f5e6fd7f` |
| `organvm-i-theoria-github` | `413.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/.github@af9232b68d53` |
| `a-i-chat--exporter` | `410.1 MiB` | `git` | `keep_active` | `idle-window-not-met` | `a-organvm/a-i-chat--exporter@c2861dfad7bf` |
| `hokage-chess` | `352.2 MiB` | `git` | `keep_active` | `idle-window-not-met` | `4444J99/hokage-chess@bf52a0eb33ec` |
| `universal-mail--automation` | `330.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/universal-mail--automation@dd402c34450f` |
| `organvm-i-theoria` | `295.4 MiB` | `container` | `container_review_required` | `nested-git-roots` | `preserve_required:2` |
| `bountyscope` | `235.5 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/bountyscope@ecf83bcee32a` |
| `bountyscope-test-coverage` | `234.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/bountyscope@e100c8b0dc4a` |
| `edgarflash` | `234.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/edgarflash@1e74592c935b` |
| `domus-genoma` | `229.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/domus-genoma@c483b81daaef` |
| `vulnpulse` | `223.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/vulnpulse@e0b94ed724b9` |
| `organvm-engine` | `197.8 MiB` | `git` | `keep_active` | `idle-window-not-met` | `a-organvm/organvm-engine@26872c12d8d3` |
| `my-domus-genoma` | `168.7 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/domus-genoma@f8cfcbb46f80` |
| `organvm-i-theoria-mesh` | `148.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/mesh@b4f0ed18fedf` |
| `rules-system-bound` | `133.5 MiB` | `git` | `keep_active` | `idle-window-not-met` | `organvm-i-theoria/rules-system-bound@4482ba84cc56` |
| `conversation-corpus-engine` | `120.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/conversation-corpus-engine@9d7b3cff6e1f` |
| `schema-definitions` | `90.7 MiB` | `git` | `keep_active` | `idle-window-not-met` | `organvm/schema-definitions@f11d1a5361d0` |
| `organvm-ontologia` | `88.2 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `a-organvm/organvm-ontologia@511a5582911c` |
| `4444J99` | `81.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/_agent@acbca74f95ec` |
| `anon-hookup-now` | `69.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/anon-hookup-now@92fd88681fde` |
| `studium-generale` | `58.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/studium-generale@6ca4f9a12527` |
| `public-process` | `54.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/public-process@9065f56fe2b3` |
| `organvm-rules-system-bound` | `51.3 MiB` | `git` | `keep_active` | `idle-window-not-met` | `organvm/rules-system-bound@160cc18784cc` |
| `recursive-engine--generative-entity` | `45.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/recursive-engine--generative-entity@77786fd5c1c6` |
| `session-meta-4` | `44.3 MiB` | `git` | `preserve_required` | `clean-but-head-not-proven-on-remote` | `organvm/session-meta` |
| `atomic-substrata` | `40.2 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/atomic-substrata@5b71447bbcef` |
| `adaptive-personal-syllabus` | `31.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/adaptive-personal-syllabus@cf0abef19af6` |

## Operating Rule

- `safe_reap_candidate`: local deletion is allowed only through `--apply-safe-reap --write`, which reclassifies the root before removal, then requires a matching verified archive receipt and human redaction acceptance with `accepted_at`, `archive_proof`, and `redaction_proof` before writing a deletion receipt.
- `bridge_required`: preserve/carry the uncommitted delta first.
- `preserve_required`: push, archive, or receipt the local commit before deletion.
- `container_review_required`: inspect nested repos; do not delete the parent as one blob.
- `non_git_review_required`: classify the directory owner before deleting it.
