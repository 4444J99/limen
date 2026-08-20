# Prima Materia universe S3 relay

Recorded: `2026-07-28T21:05:34Z`
Workstream deadline: `2026-07-29T04:43:09Z`

## Durable custody

- The admitted finite-runway receipt is remote commit
  `adc44b9415ba3dd23ccbf5534870483a3926dac2`.
- The bounded universe-contract packet is remote commit
  `f9b00076b46945d0a67a8a7e8d7f8edf1b13f234`.
- GitHub blob identities for all five packet paths equal the tested local blob
  identities.
- PR #1606 remains the alpha delivery owner at immutable head
  `f002f973d7f2d46cb218fe49edebfa43d43cc523`; its unchanged required CI
  receipts were reused.

## Packet

The packet added fail-closed `ProjectUniverseManifestV1` and
`CollaboratorUniverseManifestV1` Pydantic contracts and generated JSON
Schemas. The contracts bind source, project, and collaborator denominators;
keep projects and child tasks distinct; support zero- and multi-repository
projects; require artifacts and receipts before a build can pass; keep
Project and repository access separate; reject role over-grants; and keep
reference-only identities outside the collaborator universe.

Changed paths:

- `cli/src/limen/prima_materia.py`
- `cli/tests/test_prima_materia.py`
- `scripts/generate-prima-materia-schemas.py`
- `spec/contracts/prima-materia/project-universe-manifest-v1.schema.json`
- `spec/contracts/prima-materia/collaborator-universe-manifest-v1.schema.json`

## Predicate receipts

- `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_prima_materia.py -q`
  passed: `13 passed`.
- Focused `ruff format --check` and `ruff check` passed for the three touched
  Python files.
- Both generated schemas passed their explicit JSON-schema assertions.
- A second schema-generation pass was byte-identical.
- `git diff --check` passed.
- `bash scripts/verify-scoped.sh` reached `ruff-lint` and failed on 1,299
  inherited whole-estate findings outside this packet. The gate owner is
  `verify` in `institutio/governance/gates.yaml`; the next clearing command in
  a normally hydrated checkout is the unchanged
  `bash scripts/verify-scoped.sh` after that owner reconciles the estate-wide
  Ruff baseline. Do not rerun it on this unchanged state.

## Boundary

The authenticated conduct registration was admitted before provider launch,
but the broker became unreachable inside the network-restricted provider
sandbox, so no child packet or hidden fan-out was created.

The managed filesystem permits source-file writes but makes the linked
worktree's shared Git metadata read-only. `git add` failed at the worktree
`index.lock` with `Operation not permitted`. Remote GitHub custody therefore
owns the two commits above, while the local working bytes remain an
uncommitted exact mirror.

Successor creation is owner-blocked on that same Git-metadata surface because
the canonical launcher must create a new linked `-s4` worktree and preserve
the already-admitted deadline. From a write-capable Limen shell, the first
clearing command is:

```bash
git -C /Users/4jp/Workspace/limen fetch origin \
  work/prima-materia-alpha-omega-universe-20260728-s3
```

Then create the unique S4 capsule from the fetched exact head while copying,
not resetting, the admitted S3 timing contract before launch. Until that
owner operation is available, this S3 capsule remains the launch surface:

```bash
bash "/Users/4jp/Workspace/limen/.worktrees/prima-materia-alpha-omega-universe-20260728-s3/.limen-workstream/kickstart.sh"
```
