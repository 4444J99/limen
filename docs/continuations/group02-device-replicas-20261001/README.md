# Group 02 independent physical-device replicas

The independent custody verifier now accepts `--replica Archive4T` or
`--replica T7Recovery` for any of the eleven pinned views. It reuses native
custody physical-device identities and requires both mounted drives to be
distinct from each other and the internal device. It stores only exact encrypted
release assets on the two pinned physical-device identities; a replacement device
with the same volume name is refused pending owner profile reconciliation. It stores
only exact encrypted
release assets under each drive's `limen-private/group02-custody-20261001/`.
The new leaf directory is mode 0700; ciphertext files are exclusive-created,
mode 0600, synced, and hash-read back. Existing files must be private, singly
linked regular files with the pinned hash; they are never overwritten. Owned
non-writable ancestor directories may be mode 0755; neither their permissions
nor existing stores are changed. Symlinked or writable parents are rejected.

Normal replica mode decrypts directly from the device's ciphertext using escrow
and executes the full manifest/Git restore verifier. `--preserve-only` copies and
checks ciphertext without requesting a key. That mode deliberately returns exit
1 and `accepted: false`, `ciphertext-preserved-restore-unproven`; encrypted
replication is not accepted recovery. Native heavy-work admission precedes large
downloads and copies in both modes. An `op` subprocess failure stops the cohort
instead of repeatedly requesting credential authentication.

Current evidence:

- G02-02 and G02-03 exist on both physical drives, with pinned ciphertext sizes
  3,142,688 and 1,574,944 bytes and SHA-256 values from the merged diagnostics
  receipt. Four encrypted files total 9,435,264 logical bytes. Their device IDs
  are `device_7b1949b90546f414a63811ef0a5caeea` and
  `device_6d45f17db43abb97bf79bc1d4dfdbe06`.
- Repeat preserve-only runs report `replica_created: false`, confirming the
  existing copies are reused without overwrite and still match pinned hashes.
- Fresh Archive4T decrypt/restore attempts returned `CalledProcessError`.
  A separate stable-host credential-authentication observation returned exit 1.
  These device restores are unaccepted; prior independent restores from remote
  ciphertext remain separate evidence. No source retirement follows this result.
- Other nine views are not yet replicated or independently restored from these
  devices. Larger work remains subject to native host admission.

Five archive/schema/replica safety tests and focused Ruff pass. The continuation
owner is Domus #397; E1/E5 custody predicates remain separately owned in Limen.
Native protected clients, existing vaults, private originals and installed runtime
are retained. No key is exported, rotated, printed or stored in this work.
