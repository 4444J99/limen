# Antigravity Scratch Bridge

Generated: `2026-07-08T05:50:21+00:00`
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
- Total scratch size: `22.1 GiB`.
- Safe-reap candidate size: `8.5 MiB`.
- Dispositions: `bridge_required` 34, `container_review_required` 3, `keep_active` 11, `non_git_review_required` 3, `preserve_required` 2, `safe_reap_candidate` 2.

## Reap History

- Recorded reap events: `2`.
- Cumulative reaped roots: `24`.
- Cumulative reclaimed size: `6.9 GiB`.
- `2026-07-06T02:08:09+00:00`: `1` roots, `4.7 GiB` (`session-meta`).
- `2026-07-06T01:27:51+00:00`: `23` roots, `2.2 GiB` (`growth-auditor`, `the-invisible-ledger`, `organvm-corpvs-testamentvm`, `organvm_domus_genoma`, `persona-fleet`, `a-i--skills`, `prompt-registry-archive`, `portfolio`, ... +15).

## Preservation History

- Preservation receipts: `48`.
- External archives verified: `47`.
- Verified external archive source size: `37.4 GiB`.
- Event source size total: `42.1 GiB` (includes retries).
- `2026-07-08T04:56:45Z` `brainstorm-20260423`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260708T045645Z-brainstorm-20260423/receipt.json`.
- `2026-07-08T04:56:45Z` `session-meta-4`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260708T045645Z-session-meta-4/receipt.json`.
- `2026-07-07T22:33:13Z` `session-meta-2`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260707T223313Z-session-meta-2/receipt.json`.
- `2026-07-07T22:32:23Z` `session-meta-no-prompt`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260707T223223Z-session-meta-no-prompt/receipt.json`.
- `2026-07-07T22:31:34Z` `organvm-session-meta`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260707T223134Z-organvm-session-meta/receipt.json`.
- `2026-07-06T04:03:42Z` `hello_workspace`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T040342Z-hello_workspace/receipt.json`.
- `2026-07-06T04:02:18Z` `hello_project`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T040218Z-hello_project/receipt.json`.
- `2026-07-06T04:01:13Z` `my-project`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T040113Z-my-project/receipt.json`.
- `2026-07-06T04:00:23Z` `organvm-vi-koinonia`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T040023Z-organvm-vi-koinonia/receipt.json`.
- `2026-07-06T03:59:38Z` `organvm-i-theoria`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035938Z-organvm-i-theoria/receipt.json`.

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
| `a-i-council--coliseum` | `2.3 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/a-i-council--coliseum@fcacc4a1b202` |
| `peer-audited--behavioral-blockchain` | `1.8 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/peer-audited--behavioral-blockchain@18e881f0a29f` |
| `organvm` | `632.4 MiB` | `container` | `container_review_required` | `nested-git-roots` | `bridge_required:3, safe_reap_candidate:3` |
| `sovereign-systems--elevate-align` | `584.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-iii-ergon/sovereign-systems--elevate-align@3ac45f92ba16` |
| `limen` | `497.4 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/limen@7aff62eb8ba1` |
| `organvm-i-theoria-github` | `412.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/.github@af9232b68d53` |
| `dot-github--theoria` | `369.0 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/dot-github--theoria@a96c76a24b52` |
| `universal-mail--automation` | `330.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/universal-mail--automation@dd402c34450f` |
| `organvm-i-theoria` | `295.4 MiB` | `container` | `container_review_required` | `nested-git-roots` | `preserve_required:2` |
| `domus-genoma` | `229.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/domus-genoma@c483b81daaef` |
| `my-domus-genoma` | `168.7 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/domus-genoma@f8cfcbb46f80` |
| `rules-system-bound` | `130.6 MiB` | `git` | `keep_active` | `idle-window-not-met` | `organvm-i-theoria/rules-system-bound@4482ba84cc56` |
| `schema-definitions` | `90.6 MiB` | `git` | `keep_active` | `idle-window-not-met` | `organvm/schema-definitions@f11d1a5361d0` |
| `public-record-data-scrapper` | `87.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/public-record-data-scrapper@60f4c68a033f` |
| `4444J99` | `81.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/_agent@acbca74f95ec` |
| `anon-hookup-now` | `69.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/anon-hookup-now@92fd88681fde` |
| `hokage-chess` | `60.2 MiB` | `git` | `keep_active` | `idle-window-not-met` | `4444J99/hokage-chess@bf52a0eb33ec` |
| `public-process` | `54.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/public-process@9065f56fe2b3` |
| `organvm-rules-system-bound` | `51.3 MiB` | `git` | `keep_active` | `idle-window-not-met` | `organvm/rules-system-bound@160cc18784cc` |
| `session-meta-4` | `44.3 MiB` | `git` | `preserve_required` | `clean-but-head-not-proven-on-remote` | `organvm/session-meta` |
| `atomic-substrata` | `40.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/atomic-substrata@5b71447bbcef` |
| `organvm-engine` | `33.2 MiB` | `git` | `keep_active` | `idle-window-not-met` | `a-organvm/organvm-engine@26872c12d8d3` |
| `adaptive-personal-syllabus` | `31.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/adaptive-personal-syllabus@cf0abef19af6` |
| `studium-generale` | `28.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/studium-generale@6ca4f9a12527` |
| `recursive-engine--generative-entity` | `28.5 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/recursive-engine--generative-entity@77786fd5c1c6` |
| `browser-state` | `8.2 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/browser-state@e515a8541d4b` |
| `the-invisible-ledger` | `5.9 MiB` | `git` | `keep_active` | `idle-window-not-met` | `organvm/the-invisible-ledger@2bd0d2ef29e0` |
| `a-i-chat--exporter` | `5.5 MiB` | `git` | `keep_active` | `idle-window-not-met` | `a-organvm/a-i-chat--exporter@c2861dfad7bf` |
| `growth-auditor` | `5.2 MiB` | `git` | `keep_active` | `idle-window-not-met` | `organvm/growth-auditor@93cad2b4974d` |
| `brainstorm-20260423` | `5.1 MiB` | `git` | `preserve_required` | `clean-but-head-not-proven-on-remote` | `organvm/brainstorm-20260423@d7393d8a9197` |
| `conversation-corpus-engine` | `5.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/conversation-corpus-engine@9d7b3cff6e1f` |
| `mirror-mirror` | `4.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/mirror-mirror@cd59f5e6fd7f` |
| `mirror-mirror-healing` | `4.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/mirror-mirror@6491c27c636c` |
| `system-system--system--monad` | `2.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/system-system--system--monad@134b01e01c41` |
| `organvm-i-theoria-mesh` | `2.5 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/mesh@b4f0ed18fedf` |
| `organvm-ontologia` | `2.4 MiB` | `git` | `keep_active` | `idle-window-not-met` | `a-organvm/organvm-ontologia@511a5582911c` |
| `vigiles-aeternae--corpus-mythicum` | `2.2 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/vigiles-aeternae--corpus-mythicum@0098cd7d46a4` |

## Operating Rule

- `safe_reap_candidate`: local deletion is allowed only through `--apply-safe-reap --write`, which reclassifies the root before removal, then requires a matching verified archive receipt and human redaction acceptance with `accepted_at`, `archive_proof`, and `redaction_proof` before writing a deletion receipt.
- `bridge_required`: preserve/carry the uncommitted delta first.
- `preserve_required`: push, archive, or receipt the local commit before deletion.
- `container_review_required`: inspect nested repos; do not delete the parent as one blob.
- `non_git_review_required`: classify the directory owner before deleting it.
