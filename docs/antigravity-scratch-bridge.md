# Antigravity Scratch Bridge

Generated: `2026-07-06T01:21:57+00:00`
Scratch root: `~/.gemini/antigravity-cli/scratch`

## Decision

Do not delete Antigravity scratch roots by size alone. A root is only a reclaim candidate
when this bridge proves it is clean, idle, and preserved on a remote/default-equivalent ref.
Dirty roots are `bridge_required`: their per-root delta must be carried home or archived
before any deletion.

## Summary

- Roots scanned: `66`.
- Total scratch size: `30.6 GiB`.
- Safe-reap candidate size: `2.2 GiB`.
- Dispositions: `bridge_required` 34, `container_review_required` 3, `non_git_review_required` 3, `preserve_required` 3, `safe_reap_candidate` 23.

## Largest Roots

| Root | Size | Kind | Disposition | Reason | Remote / nested proof |
|---|---:|---|---|---|---|
| `session-meta` | `4.7 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/session-meta@b70038efc431` |
| `organvm-session-meta` | `4.7 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/session-meta@2954214acb76` |
| `session-meta-no-prompt` | `4.5 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/session-meta@2954214acb76` |
| `session-meta-2` | `4.5 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/session-meta@2954214acb76` |
| `peer-audited--behavioral-blockchain` | `2.2 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/peer-audited--behavioral-blockchain@2dcc48181e08` |
| `sovereign-systems--elevate-align` | `1.2 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-iii-ergon/sovereign-systems--elevate-align@3ac45f92ba16` |
| `public-record-data-scrapper` | `1.0 GiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/public-record-data-scrapper@60f4c68a033f` |
| `growth-auditor` | `972.0 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm-i-theoria/growth-auditor@3ecf369a7dea` |
| `dot-github--theoria` | `650.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/dot-github--theoria@a96c76a24b52` |
| `organvm` | `632.0 MiB` | `container` | `container_review_required` | `nested-git-roots` | `bridge_required:4, safe_reap_candidate:2` |
| `limen` | `557.0 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/limen@7aff62eb8ba1` |
| `the-invisible-ledger` | `463.5 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `a-organvm/the-invisible-ledger@bf9aa21ccea4` |
| `mirror-mirror` | `450.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/mirror-mirror@cd59f5e6fd7f` |
| `organvm-i-theoria-github` | `413.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/.github@af9232b68d53` |
| `a-i-chat--exporter` | `409.2 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/a-i-chat--exporter@c3088cd2646a` |
| `universal-mail--automation` | `327.5 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/universal-mail--automation@4facf681a126` |
| `organvm-i-theoria` | `295.4 MiB` | `container` | `container_review_required` | `nested-git-roots` | `preserve_required:2` |
| `organvm-corpvs-testamentvm` | `266.9 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/organvm-corpvs-testamentvm@5668a653c7e2` |
| `bountyscope-test-coverage` | `234.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/bountyscope@e100c8b0dc4a` |
| `edgarflash` | `234.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/edgarflash@1e74592c935b` |
| `bountyscope` | `234.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/bountyscope@e100c8b0dc4a` |
| `vulnpulse` | `223.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/vulnpulse@e0b94ed724b9` |
| `organvm_domus_genoma` | `167.8 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/domus-genoma@8ea995bb587a` |
| `domus-genoma` | `166.0 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `4444J99/domus-genoma@57d176ccb52d` |
| `organvm-i-theoria-mesh` | `148.1 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/mesh@b4f0ed18fedf` |
| `rules-system-bound` | `133.2 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/rules-system-bound@2d8061dd02c1` |
| `organvm-engine` | `122.7 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `a-organvm/organvm-engine@d6cc4a10f65f` |
| `persona-fleet` | `122.5 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/persona-fleet@fd4fac20af13` |
| `conversation-corpus-engine` | `120.3 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/conversation-corpus-engine@9d7b3cff6e1f` |
| `a-i--skills` | `96.2 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/a-i--skills@c022ef82c30a` |
| `prompt-registry-archive` | `83.3 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/prompt-registry-archive@bd736d12a69a` |
| `4444J99` | `81.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/_agent@acbca74f95ec` |
| `anon-hookup-now` | `69.6 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/anon-hookup-now@92fd88681fde` |
| `hokage-chess` | `59.4 MiB` | `git` | `preserve_required` | `clean-but-head-not-proven-on-remote` | `4444J99/hokage-chess@dd9cb425b9ef` |
| `studium-generale` | `58.8 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm-i-theoria/studium-generale@6ca4f9a12527` |
| `session-meta-4` | `44.3 MiB` | `git` | `preserve_required` | `clean-but-head-not-proven-on-remote` | `organvm/session-meta@HEAD` |
| `atomic-substrata` | `40.2 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/atomic-substrata@5b71447bbcef` |
| `portfolio` | `34.6 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm/portfolio@dca52ecb1500` |
| `adaptive-personal-syllabus` | `31.9 MiB` | `git` | `bridge_required` | `dirty-or-untracked` | `organvm/adaptive-personal-syllabus@cf0abef19af6` |
| `pr-454-workspace` | `21.5 MiB` | `git` | `safe_reap_candidate` | `clean-idle-remote-preserved` | `organvm-i-theoria/.github@3fb7cc7506ad` |

## Operating Rule

- `safe_reap_candidate`: local deletion can be considered by a separate reaper, not this script.
- `bridge_required`: preserve/carry the uncommitted delta first.
- `preserve_required`: push, archive, or receipt the local commit before deletion.
- `container_review_required`: inspect nested repos; do not delete the parent as one blob.
- `non_git_review_required`: classify the directory owner before deleting it.
