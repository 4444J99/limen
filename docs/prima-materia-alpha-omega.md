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
debt. Adapters bind a claim recipe rather than a long-lived sample claim; every
selected source instance emits its own bounded `ResourceClaimV1`.

## Reconciliation

Freeze the denominator, re-enumerate its source instances in a separate
producer, materialize the selected observation graph, and wrap the canonical
non-mutating reclaimer:

```bash
uv run --project cli python scripts/prima-materia-freeze-wave.py \
  --repository-root /path/to/limen \
  --repository-search-root /path/to/workspace \
  --storage-inventory docs/storage-evacuation-inventory-20260727.json \
  --frozen-wave-output /receipt-root/frozen-wave.json

uv run --project cli python scripts/prima-materia-source-inventory.py \
  --repository-root /path/to/limen \
  --repository-search-root /path/to/workspace \
  --storage-inventory docs/storage-evacuation-inventory-20260727.json \
  --frozen-wave /receipt-root/frozen-wave.json \
  --output /receipt-root/source-inventory.json

uv run --project cli python scripts/prima-materia-resource-task-graph.py \
  --frozen-wave /receipt-root/frozen-wave.json \
  --output /receipt-root/resource-task-graph.json

uv run --project cli python scripts/prima-materia-reclaim-census.py \
  --repository-root /path/to/limen \
  --frozen-wave /receipt-root/frozen-wave.json \
  --output /receipt-root/reclaim-census.json
```

Then run the redacted pair. Each audit receives its own deadline and uses at
most three local repository-probe threads:

```bash
uv run --project cli python scripts/alpha-omega-reconcile.py \
  --repository-root /path/to/limen \
  --repository-search-root /path/to/workspace \
  --storage-inventory docs/storage-evacuation-inventory-20260727.json \
  --frozen-wave /receipt-root/frozen-wave.json \
  --source-inventory /receipt-root/source-inventory.json \
  --reclaim-census /receipt-root/reclaim-census.json \
  --resource-task-graph /receipt-root/resource-task-graph.json \
  --max-seconds 300 \
  --max-threads 3 \
  --output /path/to/redacted-receipt.json
```

A timed-out or interrupted census emits an explicitly incomplete receipt with
`candidate_count: null` and no plan digest. It can never substitute zero or
admit reclamation.

The receipt binds:

- a complete frozen denominator of repositories, storage roots, source
  instances, device roles, protected exclusions, and registry digests;
- exact Git HEAD, tree, working-state, local-ref, live-remote-ref, and worktree
  registration digests;
- private-root identities without paths;
- physical-device identity digests;
- protected process-CWD counts without PIDs or paths;
- independently re-enumerated source-adapter coverage;
- the concrete task graph and live disk/RAM resource envelope;
- reviewed remote-main authority and the exact installed immutable runtime
  path/SHA;
- every λ predicate and the separate Ω admission verdict.

The two audit state digests exclude observation timestamps and raw telemetry
that does not change a predicate, but include all normalized predicate-bearing
state. Equal digests prove an unchanged predicate state; unequal digests are
visible non-convergence. An unavailable repository command, source, device,
process, registration, or control-plane probe makes its audit incomplete.

Ω can be true only when every λ predicate passes and the live protection
registry reports no owner-blocking root.
