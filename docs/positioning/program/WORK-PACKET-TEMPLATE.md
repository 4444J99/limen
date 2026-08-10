# Work packet template

This is the human-readable shape rendered into every leaf issue. The canonical values live in
`institutio/positioning/program.yaml`.

## Identity

- Stable work ID
- Parent phase
- Target repository and path scope
- GitHub issue and milestone

## Outcome

One observable end state, written without implementation assumptions.

## Deliverables

A finite list of durable artifacts or external receipts.

## Dependencies

Program work IDs, upstream pull requests or issues, and human levers. Dependencies are explicit;
calendar order is not a dependency.

## Execution contract

- Required capabilities
- Reasoning class (`routine`, `deep`, or `frontier_review`)
- Assigned model slug and reasoning effort
- Assignment basis, catalog observation time, and fail-blocked unavailability rule
- Effect (`read`, `write`, or `external`)
- Authority boundary
- Finite retry and output expectations supplied by the live conductor

## Acceptance condition

One unambiguous end-state test. If the outcome is partly qualitative, the condition names the
review artifact, reviewers, and pass rubric.

## Executable completion predicate

Every leaf renders `python3 scripts/positioning-program.py --verify-work <WORK-ID>`. Before running
it, the executor runs a non-circular task-specific check and posts a structured, marked GitHub
receipt containing its command, true exit code, output digest, authority, exact heads, durable
evidence URLs, and rollback state. The verifier binds that receipt to the current acceptance text,
so changing acceptance automatically invalidates stale proof. The task-specific check may not call
`--verify-work` directly or indirectly: the underlying predicate proves the work, and
`--verify-work` proves that the receipt accurately records it.

For a single-repository packet, `observed_heads` contains exactly the declared target repository and
its predicate-tested head. For a `multi-repository:<selector>` packet, the receipt includes a
nonempty `resolved_repositories` list of concrete `owner/repository` names, and the
`observed_heads` keys equal that resolved set exactly. Unrelated, additional, or omitted repository
heads cannot stand in for packet targets.

For a phase, child closure and leaf receipts are necessary but not sufficient. Execute the
manifest-owned phase `exit_gate`, then generate its read-only skeleton with
`python3 scripts/positioning-program.py --phase-receipt-template <PHASE-ID>`. Post the completed
`limen.positioning_phase_receipt.v1` JSON receipt after
`<!-- positioning-phase-receipt:<PHASE-ID> -->`. It contains `phase_id`, `"status": "pass"`, the
current `exit_gate_sha256`, exactly the program repository head in `observed_heads`,
`child_receipts_sha256`, phase-local `remote_state_sha256`, `parity_sha256`, the manifest-derived
non-circular `predicate.command`, zero `predicate.exit_code`, `predicate.output_sha256`, RFC3339
`predicate.observed_at`, and nonempty HTTPS `evidence_urls`. Validate it with
`python3 scripts/positioning-program.py --verify-phase <PHASE-ID>` before closing the phase; the
underlying predicate may not call this receipt verifier. Closure-integrity and ready-work checks
reject a closed phase without a valid current phase receipt.

The phase-local stable digest binds child states and receipts plus stable phase identity, while
excluding the phase issue’s own open/closed state. It therefore survives that issue’s open-to-closed
transition, and unrelated future phases do not invalidate it. Direct phase verification and normal
closure recompute the current child-receipt, remote-state, and parity bindings and reject drift.

For a terminal Omega packet, each observation fetches remote state once and derives parity, closure
integrity, and the state digest from that same snapshot. Invoke `--omega --omega-pass 1` and
`--omega --omega-pass 2` separately and save each emitted `limen.positioning_omega_pass.v1` record
to its corresponding pass file. Each has `"status": "pass"`, its integer `pass`, `state_digest`,
and RFC3339 `observed_at`. The two files use their respective pass numbers and different observation
times while attesting the same digest; `--omega --require-two-pass` consumes both. Duplicating one
pass file is not an independent observation. Only the manifest-derived terminal Omega leaf, its
phase, and root may remain open during proof generation, then close in dependency order.

## Return evidence

The exact proof that travels back to the phase and root: target-bound head or resolved head set,
underlying checks, phase exit-gate evidence, links, metrics, decisions, objections, incidents, or
external validation.

## Rollback

The recovery route if the change or external outcome is wrong. “Revert it” is insufficient unless
the issue names the owner and release or data boundary that makes reversion safe.

## Closeout

No issue closes on prose or a self-referential check. Close after the executable predicate passes
against the durable receipt.
