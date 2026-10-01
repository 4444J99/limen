# Encrypted custody for retained repository archives

Owner: [ARCA/HORREVM #2742](https://github.com/4444J99/limen/issues/2742), with
repository routing in [#2741](https://github.com/4444J99/limen/issues/2741).
This path accepts the existing exact repository-group JSON allowlist. It does
not depend on the generated `estate-audit-*` naming convention.

Preview with `limen repos custody --allowlist /absolute/path/group.json`.
Capture with the same command and `--apply`; `--candidate` selects an opaque
candidate ID printed by preview. `--max-seconds` bounds an invocation, defaults
to 600 and permits at most 900. These commands never remove source copies.
After a successful capture, `limen repos custody --verify /absolute/path/receipt.json`
performs another restoration from each device. Local receipts are under
`$XDG_DATA_HOME/limen/repository-archives/<allowlist-sha256>/<candidate>.json`.

Capture and verification require the existing heavy-work host admission gate,
both physically distinct registered drives, the frozen inventory digest, private
FileVault scratch, native metadata inspection and the existing `limen-arca-vault`
Keychain key. No new key, storage registration or admission bypass is created.
The drives may contain only ARCA-encrypted payloads and encrypted private
manifests; public locators contain digests and opaque IDs. Plaintext archive
creation and restoration occur on FileVault scratch, removed after each probe.
ACLs, binary xattrs, modes, symlinks, ignored/untracked files and Git object stores
are compared after actual extraction from each drive. A stable recapture reuses
the locator and verifies both copies again. Failures retain the sources.

Valid standalone Git repositories require matching restored HEAD, refs, object
inventory, index and full fsck results, including unreachable objects. Broken
worktree pointers receive filesystem-only coverage: preserving the pointer and
its payload does not reconstruct an absent Git store. An unlisted nested Git
root or mismatched pointer is rejected. Private failed-command argv, exit and
bounded stderr are recorded only on FileVault, never printed in a public receipt.

The retirement runner can select `custody.mode: arca-envelope` for preservation,
while its existing remote, runtime-owner, dependency, keeper and reviewer gates
remain in force. Acceptance/removal is explicitly blocked with
`archive-independent-key-recovery-proof-required`: a successful decryption with
the local Keychain does not prove recovery of the key after loss of this host.
Independent key recovery must be demonstrated through ARCA/HORREVM before that
gate can be implemented and opened. Every archive CLI result reports
`retirement_authorized: false`.

## Group 05 observation, 2026-10-01

The exact allowlist digest is
`0eaa094925c08fe451ca054582503223100de5a2f80560e5ceff90cf9b11a655`.
Preview inspected all 11 candidates: seven standalone Git repositories and four
broken-pointer filesystem copies. The unrelated generated estate-audit directory
was not repaired or used as evidence.

The live canary was denied before archive-state creation by host admission
(`swap-fraction`, observed swap usage about 49.4%). No drive archive was created,
no live restore proof exists and all 11 copies remain retained. Reclaimed space
is zero. Run a bounded capture only after host admission changes; continue exact
remote reconciliation, pointer/store recovery and independent acceptance under
the existing owners before any removal.
