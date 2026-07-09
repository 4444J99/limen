# Antigravity Scratch Bridge

Generated: `2026-07-09T23:32:08+00:00`
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

- Roots scanned: `48`.
- Total scratch size: `4.2 GiB`.
- Safe-reap candidate size: `262.4 MiB`.
- Dispositions: `bridge_required` 29, `container_review_required` 3, `non_git_review_required` 3, `preserve_required` 1, `safe_reap_candidate` 12.

## Reap History

- Recorded reap events: `4`.
- Cumulative reaped roots: `24`.
- Cumulative reclaimed size: `6.9 GiB`.
- `2026-07-09T23:20:20+00:00`: `0` roots, `0 B`.
- `2026-07-09T23:18:32+00:00`: `0` roots, `0 B`.
- `2026-07-06T02:08:09+00:00`: `1` roots, `4.7 GiB` (`session-meta`).
- `2026-07-06T01:27:51+00:00`: `23` roots, `2.2 GiB` (`growth-auditor`, `the-invisible-ledger`, `organvm-corpvs-testamentvm`, `organvm_domus_genoma`, `persona-fleet`, `a-i--skills`, `prompt-registry-archive`, `portfolio`, ... +15).

## Preservation History

- Preservation receipts: `96`.
- External archives verified: `95`.
- Verified external archive source size: `41.6 GiB`.
- Event source size total: `46.3 GiB` (includes retries).
- `2026-07-09T23:33:58Z` `hello_workspace`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-hello_workspace/receipt.json`.
- `2026-07-09T23:33:58Z` `hello_project`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-hello_project/receipt.json`.
- `2026-07-09T23:33:58Z` `my-project`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-my-project/receipt.json`.
- `2026-07-09T23:33:58Z` `writelens`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-writelens/receipt.json`.
- `2026-07-09T23:33:58Z` `.github`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-github/receipt.json`.
- `2026-07-09T23:33:58Z` `edgarflash`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-edgarflash/receipt.json`.
- `2026-07-09T23:33:58Z` `bountyscope-test-coverage`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-bountyscope-test-coverage/receipt.json`.
- `2026-07-09T23:33:58Z` `organvm-vi-koinonia`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-organvm-vi-koinonia/receipt.json`.
- `2026-07-09T23:33:58Z` `vulnpulse`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-vulnpulse/receipt.json`.
- `2026-07-09T23:33:57Z` `sovereign--ground`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233357Z-sovereign--ground/receipt.json`.

## Preservation Results

- Requested roots: `36`.
- Source size receipted: `3.9 GiB`.
- Statuses: `external_archive_preserved` 36.
- Preserved `organvm` `632.4 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233220Z-organvm/receipt.json`.
- Preserved `sovereign-systems--elevate-align` `584.3 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233245Z-sovereign-systems--elevate-align/receipt.json`.
- Preserved `limen` `497.4 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233251Z-limen/receipt.json`.
- Preserved `organvm-i-theoria-github` `412.9 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233303Z-organvm-i-theoria-github/receipt.json`.
- Preserved `dot-github--theoria` `369.0 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233313Z-dot-github--theoria/receipt.json`.
- Preserved `universal-mail--automation` `330.3 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233322Z-universal-mail--automation/receipt.json`.
- Preserved `organvm-i-theoria` `295.4 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233330Z-organvm-i-theoria/receipt.json`.
- Preserved `domus-genoma` `229.3 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233337Z-domus-genoma/receipt.json`.
- Preserved `my-domus-genoma` `168.7 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233341Z-my-domus-genoma/receipt.json`.
- Preserved `public-record-data-scrapper` `87.8 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233344Z-public-record-data-scrapper/receipt.json`.
- Preserved `4444J99` `81.6 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233346Z-4444J99/receipt.json`.
- Preserved `anon-hookup-now` `69.6 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233347Z-anon-hookup-now/receipt.json`.
- Preserved `public-process` `54.1 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233348Z-public-process/receipt.json`.
- Preserved `session-meta-4` `44.3 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233350Z-session-meta-4/receipt.json`.
- Preserved `atomic-substrata` `40.1 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233351Z-atomic-substrata/receipt.json`.
- Preserved `adaptive-personal-syllabus` `31.9 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233352Z-adaptive-personal-syllabus/receipt.json`.
- Preserved `studium-generale` `28.6 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233353Z-studium-generale/receipt.json`.
- Preserved `recursive-engine--generative-entity` `28.5 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233354Z-recursive-engine--generative-entity/receipt.json`.
- Preserved `conversation-corpus-engine` `5.1 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233356Z-conversation-corpus-engine/receipt.json`.
- Preserved `mirror-mirror` `4.3 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233356Z-mirror-mirror/receipt.json`.
- Preserved `mirror-mirror-healing` `4.1 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233356Z-mirror-mirror-healing/receipt.json`.
- Preserved `system-system--system--monad` `2.8 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233357Z-system-system--system--monad/receipt.json`.
- Preserved `organvm-i-theoria-mesh` `2.5 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233357Z-organvm-i-theoria-mesh/receipt.json`.
- Preserved `vigiles-aeternae--corpus-mythicum` `2.2 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233357Z-vigiles-aeternae--corpus-mythicum/receipt.json`.
- Preserved `media-ark-33` `1.3 MiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233357Z-media-ark-33/receipt.json`.
- Preserved `bountyscope` `848.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233357Z-bountyscope/receipt.json`.
- Preserved `sovereign--ground` `732.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233357Z-sovereign--ground/receipt.json`.
- Preserved `vulnpulse` `572.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-vulnpulse/receipt.json`.
- Preserved `organvm-vi-koinonia` `508.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-organvm-vi-koinonia/receipt.json`.
- Preserved `bountyscope-test-coverage` `484.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-bountyscope-test-coverage/receipt.json`.
- Preserved `edgarflash` `440.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-edgarflash/receipt.json`.
- Preserved `.github` `312.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-github/receipt.json`.
- Preserved `writelens` `208.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-writelens/receipt.json`.
- Preserved `my-project` `8.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-my-project/receipt.json`.
- Preserved `hello_project` `4.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-hello_project/receipt.json`.
- Preserved `hello_workspace` `4.0 KiB` as `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260709T233358Z-hello_workspace/receipt.json`.

## Repeated Dirty Fingerprints

These are duplicate-looking unsafe scratch states. They still require bridge/archive proof
before any local root can be removed.

| Count | Roots | Staged missing | Untracked | Top buckets |
|---:|---|---:|---:|---|
| `2` | `anon-hookup-now`, `system-system--system--monad` | `0` | `1` | `(root):1` |

## Largest Roots

| Root | Size | Kind | Disposition | Reason | Remote / nested proof |
|---|---:|---|---|---|---|
| `organvm` | `632.4 MiB` | `container` | `container_review_required` | `nested-git-roots` | `bridge_required:3, safe_reap_candidate:3` |
| `sovereign-systems--elevate-align` | `584.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-iii-ergon/sovereign-systems--elevate-align@3ac45f92ba16` |
| `limen` | `497.4 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/limen@7aff62eb8ba1` |
| `organvm-i-theoria-github` | `412.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/.github@af9232b68d53` |
| `dot-github--theoria` | `369.0 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/dot-github--theoria@a96c76a24b52` |
| `universal-mail--automation` | `330.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/universal-mail--automation@dd402c34450f` |
| `organvm-i-theoria` | `295.4 MiB` | `container` | `container_review_required` | `nested-git-roots` | `preserve_required:2` |
| `domus-genoma` | `229.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/domus-genoma@c483b81daaef` |
| `my-domus-genoma` | `168.7 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/domus-genoma@f8cfcbb46f80` |
| `schema-definitions` | `90.6 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/schema-definitions@f11d1a5361d0` |
| `public-record-data-scrapper` | `87.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/public-record-data-scrapper@60f4c68a033f` |
| `4444J99` | `81.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/_agent@acbca74f95ec` |
| `anon-hookup-now` | `69.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/anon-hookup-now@92fd88681fde` |
| `hokage-chess` | `60.2 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `4444J99/hokage-chess@bf52a0eb33ec` |
| `public-process` | `54.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/public-process@9065f56fe2b3` |
| `organvm-rules-system-bound` | `51.3 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/rules-system-bound@160cc18784cc` |
| `session-meta-4` | `44.3 MiB` | `git` | `preserve_required` | `clean-but-head-not-proven-on-remote` | `organvm/session-meta` |
| `atomic-substrata` | `40.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/atomic-substrata@5b71447bbcef` |
| `organvm-engine` | `33.2 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `a-organvm/organvm-engine@26872c12d8d3` |
| `adaptive-personal-syllabus` | `31.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/adaptive-personal-syllabus@cf0abef19af6` |
| `studium-generale` | `28.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/studium-generale@6ca4f9a12527` |
| `recursive-engine--generative-entity` | `28.5 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/recursive-engine--generative-entity@77786fd5c1c6` |
| `the-invisible-ledger` | `5.9 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/the-invisible-ledger@2bd0d2ef29e0` |
| `a-i-chat--exporter` | `5.5 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `a-organvm/a-i-chat--exporter@c2861dfad7bf` |
| `growth-auditor` | `5.2 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/growth-auditor@93cad2b4974d` |
| `brainstorm-20260423` | `5.1 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/brainstorm-20260423@d7393d8a9197` |
| `conversation-corpus-engine` | `5.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/conversation-corpus-engine@9d7b3cff6e1f` |
| `mirror-mirror` | `4.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/mirror-mirror@cd59f5e6fd7f` |
| `mirror-mirror-healing` | `4.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/mirror-mirror@6491c27c636c` |
| `system-system--system--monad` | `2.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/system-system--system--monad@134b01e01c41` |
| `organvm-i-theoria-mesh` | `2.5 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/mesh@b4f0ed18fedf` |
| `organvm-ontologia` | `2.4 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `a-organvm/organvm-ontologia@511a5582911c` |
| `vigiles-aeternae--corpus-mythicum` | `2.2 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/vigiles-aeternae--corpus-mythicum@0098cd7d46a4` |
| `my--father-mother` | `1.4 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/my--father-mother@d38772a914ca` |
| `media-ark-33` | `1.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/media-ark@e3f8dfb41bf7` |
| `system-governance-framework` | `1.3 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/system-governance-framework@d187eb093637` |
| `bountyscope` | `848.0 KiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/bountyscope@ecf83bcee32a` |
| `sovereign--ground` | `732.0 KiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/sovereign--ground@80e7617d1122` |
| `vulnpulse` | `572.0 KiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/vulnpulse@e0b94ed724b9` |
| `organvm-vi-koinonia` | `508.0 KiB` | `container` | `container_review_required` | `nested-git-roots` | `safe_reap_candidate:1` |

## Operating Rule

- `safe_reap_candidate`: local deletion is allowed only through `--apply-safe-reap --write`, which reclassifies the root before removal, then requires a matching verified archive receipt and human redaction acceptance with `accepted_at`, `archive_proof`, and `redaction_proof` before writing a deletion receipt.
- `bridge_required`: preserve/carry the uncommitted delta first.
- `preserve_required`: push, archive, or receipt the local commit before deletion.
- `container_review_required`: inspect nested repos; do not delete the parent as one blob.
- `non_git_review_required`: classify the directory owner before deleting it.
