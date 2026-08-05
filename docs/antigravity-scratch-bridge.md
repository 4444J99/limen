# Antigravity Scratch Bridge

Generated: `2026-07-10T01:20:39+00:00`
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
- Safe-reap candidate size: `265.6 MiB`.
- Dispositions: `bridge_required` 29, `container_review_required` 3, `non_git_review_required` 3, `preserve_required` 1, `safe_reap_candidate` 12.
- Post-reap scratch size: `4.2 GiB` across `48` roots.

## Reap Results

- Applied at: `2026-07-10T01:20:58+00:00`.
- Reaped: `0` roots, `0 B`.
- Skipped: `12`; failed: `0`.
- Skipped `schema-definitions`: missing-human-reap-acceptance.
- Skipped `hokage-chess`: missing-human-reap-acceptance.
- Skipped `organvm-rules-system-bound`: missing-human-reap-acceptance.
- Skipped `organvm-engine`: missing-human-reap-acceptance.
- Skipped `a-i-chat--exporter`: missing-human-reap-acceptance.
- Skipped `brainstorm-20260423`: missing-human-reap-acceptance.
- Skipped `the-invisible-ledger`: missing-human-reap-acceptance.
- Skipped `growth-auditor`: missing-human-reap-acceptance.
- Skipped `organvm-ontologia`: missing-human-reap-acceptance.
- Skipped `my--father-mother`: missing-human-reap-acceptance.
- Skipped `system-governance-framework`: missing-human-reap-acceptance.
- Skipped `4444J99-clone`: missing-human-reap-acceptance.

## Reap History

- Recorded reap events: `6`.
- Cumulative reaped roots: `24`.
- Cumulative reclaimed size: `6.9 GiB`.
- `2026-07-10T01:20:58+00:00`: `0` roots, `0 B`.
- `2026-07-10T01:19:14+00:00`: `0` roots, `0 B`.
- `2026-07-09T23:20:20+00:00`: `0` roots, `0 B`.
- `2026-07-09T23:18:32+00:00`: `0` roots, `0 B`.
- `2026-07-06T02:08:09+00:00`: `1` roots, `4.7 GiB` (`session-meta`).
- `2026-07-06T01:27:51+00:00`: `23` roots, `2.2 GiB` (`growth-auditor`, `the-invisible-ledger`, `organvm-corpvs-testamentvm`, `organvm_domus_genoma`, `persona-fleet`, `a-i--skills`, `prompt-registry-archive`, `portfolio`, ... +15).

## Preservation History

- Preservation receipts: `106`.
- External archives verified: `105`.
- Verified external archive source size: `41.9 GiB`.
- Event source size total: `46.5 GiB` (includes retries).
- `2026-07-10T01:20:27Z` `system-governance-framework`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260710T012027Z-system-governance-framework/receipt.json`.
- `2026-07-10T01:20:26Z` `my--father-mother`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260710T012026Z-my--father-mother/receipt.json`.
- `2026-07-10T01:20:25Z` `organvm-ontologia`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260710T012025Z-organvm-ontologia/receipt.json`.
- `2026-07-10T01:20:25Z` `growth-auditor`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260710T012025Z-growth-auditor/receipt.json`.
- `2026-07-10T01:20:24Z` `brainstorm-20260423`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260710T012024Z-brainstorm-20260423/receipt.json`.
- `2026-07-10T01:20:23Z` `a-i-chat--exporter`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260710T012023Z-a-i-chat--exporter/receipt.json`.
- `2026-07-10T01:20:22Z` `organvm-engine`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260710T012022Z-organvm-engine/receipt.json`.
- `2026-07-10T01:20:20Z` `organvm-rules-system-bound`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260710T012020Z-organvm-rules-system-bound/receipt.json`.
- `2026-07-10T01:20:18Z` `hokage-chess`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260710T012018Z-hokage-chess/receipt.json`.
- `2026-07-10T01:20:15Z` `schema-definitions`: `external_archive_preserved`; archive `verified`; private receipt `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260710T012015Z-schema-definitions/receipt.json`.

## Repeated Dirty Fingerprints

These are duplicate-looking unsafe scratch states. They still require bridge/archive proof
before any local root can be removed.

| Count | Roots | Staged missing | Untracked | Top buckets |
|---:|---|---:|---:|---|
| `2` | `anon-hookup-now`, `system-system--system--monad` | `0` | `1` | `(root):1` |

## Largest Roots Before Reap

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
| `schema-definitions` | `90.7 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/schema-definitions@f11d1a5361d0` |
| `public-record-data-scrapper` | `87.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/public-record-data-scrapper@60f4c68a033f` |
| `4444J99` | `81.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/_agent@acbca74f95ec` |
| `anon-hookup-now` | `69.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/anon-hookup-now@92fd88681fde` |
| `hokage-chess` | `60.3 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `4444J99/hokage-chess@bf52a0eb33ec` |
| `public-process` | `54.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/public-process@9065f56fe2b3` |
| `organvm-rules-system-bound` | `51.4 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/rules-system-bound@160cc18784cc` |
| `session-meta-4` | `44.3 MiB` | `git` | `preserve_required` | `clean-but-head-not-proven-on-remote` | `organvm/session-meta` |
| `atomic-substrata` | `40.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/atomic-substrata@5b71447bbcef` |
| `organvm-engine` | `33.5 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `a-organvm/organvm-engine@26872c12d8d3` |
| `adaptive-personal-syllabus` | `31.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/adaptive-personal-syllabus@cf0abef19af6` |
| `studium-generale` | `28.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/studium-generale@6ca4f9a12527` |
| `recursive-engine--generative-entity` | `28.5 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/recursive-engine--generative-entity@77786fd5c1c6` |
| `a-i-chat--exporter` | `6.4 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `a-organvm/a-i-chat--exporter@c2861dfad7bf` |
| `brainstorm-20260423` | `6.2 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/brainstorm-20260423@d7393d8a9197` |
| `the-invisible-ledger` | `5.9 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/the-invisible-ledger@2bd0d2ef29e0` |
| `growth-auditor` | `5.2 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/growth-auditor@93cad2b4974d` |
| `conversation-corpus-engine` | `5.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/conversation-corpus-engine@9d7b3cff6e1f` |
| `mirror-mirror` | `4.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/mirror-mirror@cd59f5e6fd7f` |
| `mirror-mirror-healing` | `4.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/mirror-mirror@6491c27c636c` |
| `system-system--system--monad` | `2.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/system-system--system--monad@134b01e01c41` |
| `organvm-ontologia` | `2.6 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `a-organvm/organvm-ontologia@511a5582911c` |
| `organvm-i-theoria-mesh` | `2.5 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/mesh@b4f0ed18fedf` |
| `vigiles-aeternae--corpus-mythicum` | `2.2 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/vigiles-aeternae--corpus-mythicum@0098cd7d46a4` |
| `my--father-mother` | `1.8 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/my--father-mother@d38772a914ca` |
| `system-governance-framework` | `1.4 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/system-governance-framework@d187eb093637` |
| `media-ark-33` | `1.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/media-ark@e3f8dfb41bf7` |
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
