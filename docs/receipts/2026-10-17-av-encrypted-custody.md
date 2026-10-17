# AV encrypted two-device custody and budget ledger readback (2026-10-17)

Plan: `docs/plans/2026-10-17-tmb-acceptance-gaps.md`. Issue: #2909.
Machine-readable companion: `docs/receipts/2026-10-17-av-encrypted-custody.json`.

## Encrypted custody

Six private media blobs were sealed with `scripts/sealed-custody.py` (run `av-media-custody-20261017`):

- four current derivatives (generation-01 and generation-02, video and audio-only), each verified against the preservation manifest sha256 before sealing;
- two superseded blobs from commit ed5a09f (old generation-01.mp4 and generation-02.mp4), each verified by `git hash-object` equal to its blob OID (2/2 MATCH).

The bundle also carries the preservation manifest, so each replica has 7 members (6 media + manifest).

Two physical devices hold independent replicas: the internal disk and an external USB SSD. Each replica is a separate seal with a fresh salt, so ciphertext hashes differ by design (both 1,544,224 bytes).

| Step | Internal replica | External replica |
|------|------------------|------------------|
| seal | exit 0 | exit 0 |
| key-less verify (ciphertext vs manifest) | exit 0, ok | exit 0, ok |
| escrow restore (`--key-source op`) | members 7, mismatched 0, verified true | members 7, mismatched 0, verified true |

Key source for restore was the escrow item (`op`), not the local Keychain vault key. Escrow: PROVEN (both replicas decrypted and every member verified with the escrow key).

Plaintext retained: the internal staging source directory and the pre-existing external plaintext copy from 2026-10-17 remain in place. Their retirement is gated by lever L-TMB-HISTORY-REMOVAL.

## History purge declined 2026-10-17

Rewriting the TMB history to purge the superseded blobs was declined: the repository is private, owner-only, fork-free, and has no Pages site, so exposure is bounded. The purge recipe is held by lever L-TMB-HISTORY-REMOVAL until the owner chooses to pull it.

## Budget ledger readback

Read-only readback of the conduct graph for the run's root node:

| Field | Value |
|-------|-------|
| status | expired |
| lease state | expired |
| spend envelope | unit agent-minutes, limit 6, reserve 6 |
| deadline | 2026-10-10T17:01:58Z |
| receipts | 3 |
| children | 0 |
| packet task_id | absent (null) |

Interpretation: `expired` is not `cancelled`, so no refund applies. The envelope is never debited by children (there are none). With no task_id on the packet, no debit event exists; the envelope is declared only, and the reserve of 6 agent-minutes is a ceiling, not recorded spend. `limen conduct harvest` exists but was not run, since it may mutate state.
