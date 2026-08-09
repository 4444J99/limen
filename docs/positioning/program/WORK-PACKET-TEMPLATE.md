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
so changing acceptance automatically invalidates stale proof.

## Return evidence

The exact proof that travels back to the phase and root: heads, checks, links, metrics, decisions,
objections, incidents, or external validation.

## Rollback

The recovery route if the change or external outcome is wrong. “Revert it” is insufficient unless
the issue names the owner and release or data boundary that makes reversion safe.

## Closeout

No issue closes on prose or a self-referential check. Close after the executable predicate passes
against the durable receipt.
