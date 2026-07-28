# Prima Materia Alpha-to-Omega Reconciliation

This lane turns the Prima Materia contracts into executable custody and
fixed-point evidence. It does not treat a census, timeout, or encrypted copy as
permission to reclaim source data.

## Protected exclusions

`institutio/governance/reconciliation-protected-exclusions.json` is the
repository-owned protection registry. Entries are repo-relative. Runtime
consumers resolve them against the live repository and publish only SHA-256
path, branch, and registration identities.

`scripts/reclaim-worktrees.py` loads this registry before classifying any
candidate. A candidate is rejected when it:

- is the protected root, an ancestor, or a descendant;
- overlaps the protected Git registration;
- has the protected branch;
- would clean generated payload below a protected root.

The reclaimer has no global `git worktree prune` execution path. A missing or
invalid protection registry blocks the entire reclaim run.

## Encrypted source custody

`limen.prima_materia_store.EncryptedObjectStore` provides deterministic,
content-addressed AES-256-GCM custody:

- a keyed HMAC produces an opaque object ID;
- a per-object key and per-chunk nonce prevent cross-object nonce reuse;
- the system libcrypto EVP interface supplies AES-256-GCM without a Python
  wheel or a secret-bearing subprocess command line;
- only ciphertext chunks, an authenticated key capsule, and a private manifest
  touch disk;
- each write restores and authenticates immediately;
- existing objects are byte-idempotent;
- altered manifests or ciphertext fail closed.

The 256-bit key remains in a mode-private owner file and is never stored in a
manifest, receipt, commit, or command line.

`limen.prima_materia_store.SourceRegistry` loads arbitrary source adapters at
runtime. Registry order cannot affect its canonical digest. Every observed
source without an adapter remains visible in the public projection as coverage
debt.

## Reconciliation

Run a bounded, redacted pair of live audits:

```bash
uv run --project cli python scripts/alpha-omega-reconcile.py \
  --repository-root /path/to/limen \
  --base-sha <exact-merged-sha> \
  --repository-search-root /path/to/workspace \
  --storage-inventory docs/storage-evacuation-inventory-20260727.json \
  --source-registry institutio/governance/prima-materia-source-registry.json \
  --protected-registry institutio/governance/reconciliation-protected-exclusions.json \
  --max-seconds 300 \
  --output /path/to/redacted-receipt.json
```

Omit `--safe-reclaim-count` when the complete reclaim census timed out or was
interrupted. Omission records `null` and makes
`automatically_safe_reclaim_zero` false; it never substitutes zero.

The receipt binds:

- exact Git HEAD, tree, working-state, local-ref, live-remote-ref, and worktree
  registration digests;
- private-root identities without paths;
- physical-device identity digests;
- protected process-CWD counts without PIDs or paths;
- source-adapter coverage;
- the live resource envelope;
- every λ predicate and the separate Ω admission verdict.

The two audit state digests exclude observation timestamps but include all
predicate-bearing state. Equal digests prove an unchanged predicate state;
unequal digests are visible non-convergence.

Ω can be true only when every λ predicate passes and the live protection
registry reports no owner-blocking root.
