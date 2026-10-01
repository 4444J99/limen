# Independent Group 02 custody restoration

Run `python3 scripts/check-group02-independent-custody.py` for the entire pinned
eleven-view cohort, or repeat `--id G02-NN` to investigate named views. The
verifier reads canonical credential-organ escrow without consulting Mac Keychain.
It checks authenticated ciphertext, manifest coverage, snapshot hash, all restored
entry contents/modes/link targets, and standalone Git integrity where captured.
Detailed manifests and plaintext stay in temporary native scratch, removed on
exit. Public results contain cohort IDs, counts, hashes, and failure classes.

Larger archives require the existing heavy-work admission before download. A
denial stops the cohort and returns failure; a partial pass is never full custody.
Archive traversal and hardlinks are rejected. Symlinks are installed only after
regular extraction and mode restoration, and no archive member may descend
through a symlink. Snapshot coverage deliberately excludes foreign nested roots
where the original receipt declares exclusions.

Live observations on 2026-10-01:

- G02-03: independently restored all 426 captured entries, snapshot hash
  `612182a71771bbc405806389478f7bca5f91be38da6c4bd8a63980a7839afa50`,
  restored `git fsck --full` exit 0, temporary plaintext removed.
- G02-02: failed strict restoration with `FileNotFoundError` during the restore
  lifecycle. This cohort is not accepted. Reconcile archive membership with the
  encrypted manifest before claiming independent restore or retiring its source.
- G02-01: native heavy-work admission denied for swap fraction and disk
  throughput. No large cohort download or restore began.
- Remaining eight cohorts: not verified by this independent verifier yet.

Two negative archive boundary tests pass; focused Ruff passes. This work does not
activate launchd jobs, move active agent state, or establish full stream closeout.
The existing owner is Domus #397, with the current observation receipt at
https://github.com/4444J99/domus-genoma/issues/397#issuecomment-5940018058.
