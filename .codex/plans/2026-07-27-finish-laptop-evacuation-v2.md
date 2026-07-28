# Prima Materia evacuation and programmable-matter convergence

Status: active superseding execution plan
Frozen inventory: `docs/storage-evacuation-inventory-20260727.json`
Frozen inventory SHA-256: `5034e1ca795fd1900f05f34068edb028da569bebc28d020e211a35f7abfa5be6`
Delivery owner: PR #1604, branch `work/finish-laptop-evacuation-20260727`
Source-owned Domus receipt: merged PR #354, reviewed head
`b45828490a03113d7249bf6b50d504435b514f81`, squash merge
`45760db8334ced1e99b112e45dabadb7d3f7df23`

This plan supersedes the implementation and completion authority in
`2026-07-27-finish-laptop-evacuation.md`. It does not rewrite that plan, the
frozen inventory, or any historical 200/220 GiB receipt. Those are immutable
evidence of the earlier rail, not present acceptance criteria.

## Objective

Evacuate the laptop to a programmable-matter fixed point while preserving the
process as a renderable artifact. Every repository and private root must reach
remote or encrypted independent custody with restoration proof. The selected
task graph alone may materialize locally, and its working set must be
dematerialized after its receipt lands.

Limen coordinates and indexes this work. Source systems keep ownership and
publish compatible encrypted events, recipes, action receipts, custody
receipts, and composition manifests.

## Governing contracts

The portable schemas under `spec/contracts/prima-materia/` are authoritative:

- `PrimaMateriaEventV1` records opaque event/source IDs, adapter and source
  schema digests, observed/effective time, registry-owned domain tags,
  actor/authority and intent/causal lineage, encrypted payload references,
  input/output digests, privacy/consent policy, and replay class.
- `SourceAdapterV1` registers source-native acquisition, owner, cursor schema,
  completeness predicate, privacy transform, resource claim, recipe version,
  custody targets, and restoration predicate. `SourceCoverageV1` renders every
  discovered source without a registration as adapter debt.
- `TransformRecipeV1` binds exact inputs, code/tool/config/environment
  identities, parameters, randomness/time declarations, outputs, and replay
  level.
- `ActionReceiptV1` binds effect authority, idempotency, preconditions,
  provider-native object/version evidence, postconditions, reversibility, and
  undo evidence.
- `CustodyReceiptV1` binds encryption, chunks, independent devices, remote
  refs, and restoration proofs.
- `CompositionManifestV1` selects, orders, omits, redacts, transforms, and
  renders process events.
- `StandingAuthorityV1` migrates the existing signed File Provider authority
  into a revocation-only parent and derives exact-plan child capabilities
  locally. It has neither expiry nor attempt count. Credentials remain
  references.

Replay is exact, semantic, or observable-only. Exact work reproduces identical
bytes. Semantic work preserves original output plus its invocation envelope
and verifies declared equivalence. Observable-only actions simulate or
reconstruct an external effect; they never repeat it without fresh effect
authority.

## Dynamic resource envelope

No fixed GiB threshold is execution authority. The live evaluator implements:

```text
required_free(t, graph) =
    observed_system_reserve(t, graph.horizon)
  + peak_concurrent_sum(graph.task_claims)
  + custody_and_rollback_staging(graph)
  + telemetry_error(t)
```

Each claim binds hydrated inputs, workspace, temporary expansion, outputs,
encryption/chunking, and rollback lifetime. The system reserve derives from
live RAM/swap headroom, updater claims, APFS churn, and telemetry error.
Admission fails closed when telemetry is unknown. Reclaim continues toward a
reference fixed point; crossing a number is never completion.

## Execution waves

### 1. Land the safe evacuation rail

- Keep all changes in PR #1604. Do not mutate the dirty primary checkout,
  create another Limen control-plane PR, resume Omega, rewrite historical
  receipts, or rewrite PRs #1599-#1601.
- The exact-plan reclaimer rejects path escapes, source-contained public
  receipts, same-device custody, stale identities, missing all-local-ref
  proofs, unavailable registered siblings, active roots, working-content
  drift, metadata-loss restores, and noncanonical plan copies.
- Copy and restore operations are bounded. A paired private receipt survives
  and reconciles a one-device write failure after purge.
- Read-only Codex admission precedes ancestry. Mutations without a durable
  session identity fail closed. Generated reclaim defaults off until a recipe
  classifies the projection/cache.
- Source-owned Domus runtime materialization remains in Domus. Generated or
  deployed-home outputs are never edited as source. Domus PR #354 owns the
  standing-authority materializer change; Limen PR #1604 owns the compatible
  contract and consumer.

### 2. Reconcile and retire every repository

- Freeze a new private SHA-bound census of every `.git` directory/file,
  registration, local ref, dirty/untracked/ignored path, active process, and
  provider-native remote ref.
- Coherent work lands on an owner branch/PR. Every local ref, not merely HEAD,
  must be remotely recoverable.
- Ambiguous or unpublished state becomes an encrypted content-addressed Git
  bundle plus working-tree overlay and manifest, stored in its private remote
  owner and two independent custody targets.
- Restore the exact repository and working state in an isolated probe before
  exact-plan removal.
- Completion is zero local repository roots and zero stale registrations, with
  release tooling installable without a checkout.

### 3. Reconcile and retire non-Git/private material

- File Provider work uses the migrated standing authority and bounded
  exact-plan children without another signing prompt.
- Browser, session, filesystem/cloud, media, messages, mail, calendar,
  contact, and other source-native material enters encrypted private custody.
- Unique personal material requires two independent physical-device copies and
  restoration proof. A volume on the same physical device is not another copy.
- Every batch rehashes immediately before deletion. Drift, active ownership,
  stale plans, incomplete receipts, and lost metadata fail closed.

### 4. Expand source-native coverage

- Converge existing Git/conduct, prompt/session, browser, filesystem/File
  Provider, and media sources first.
- Freeze the source registry digest for each bounded wave. Discoveries become
  explicit next-wave adapter debt rather than silently widening in-flight
  work.
- Add messages, mail, calendar, contacts, social, cloud drive, notifications,
  and external-device adapters through their owners. Mutations emit
  `ActionReceiptV1`; transcripts are not effect proof.

### 5. Prove the programmable-matter fixed point

On empty scratch, install release tooling without a repository checkout,
hydrate one selected graph, restore its encrypted inputs, reproduce it at its
declared replay level, render its composition, publish receipts, and remove the
checkout.

## Current nonterminal reconciliation

The 2026-07-28 live dirty-primary census remains part of the denominator:

- local `main` HEAD `681f0294` is remotely preserved by three `preserve/*`
  refs;
- the checkout has 4,207 status entries: seven tracked projections
  (`+3,666/-500`) and 4,200 untracked files;
- 4,191 untracked files are in the recipe-owned `.agent-runtime` root
  (1.1 GiB aggregate); and
- active peer and service CWDs still reference the checkout and runtime.

This root is active and therefore not automatically safe. It was neither
purged nor hidden. A later SHA-bound reconciliation must classify its generated
recipes and reach terminal custody after every protected owner exits.

## Terminal predicate

This phase is complete only when all of the following are simultaneously true
on live state:

1. every root in the frozen evacuation denominator has a terminal custody or
   remote receipt;
2. every discovered source in the frozen source-registry wave has an adapter
   and passing completeness/restoration predicate;
3. selected private material restores from both independent custody targets;
4. every removed repository reconstructs from remote/private custody,
   including all refs and working overlays;
5. local repository census and stale registration census are both zero;
6. a second exact-plan reclaim check reports zero automatically safe roots;
7. the resource envelope remains nonnegative for its telemetry-backed
   validation horizon; and
8. Omega successor admission remains stopped until the preceding predicates
   pass.

Motion, scans, bytes reclaimed, commits, and prose are supporting evidence.
Only these predicates plus durable receipts close the phase.
