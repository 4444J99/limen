# Audit outputs and bounded handoff

Scale the report to the requested surface; a targeted audit need not inventory the
whole machine. Keep private paths, raw process arguments, secrets, and session
contents in private evidence. Use safe aliases in shared reports.

## Inventory

| Surface | Source owner | Effective destination | Consumer | Evidence/time | Status |
|---|---|---|---|---|---|
| Agent settings | Owning template | Resolved runtime config | Native agent | Readback or scoped probe | Configured / verified / unknown |

For a cleanup candidate, add active-use evidence, bytes under the relevant
accounting method, regeneration path, parity/custody evidence, and disposition.
Do not collapse "quarantine proposed," "quarantined," and "retired."

## Findings

Each finding needs the smallest reproducible observation, implication, severity
appropriate to the user's request, owner, proposed correction, and acceptance
predicate. Label historical assistant/UI claims as reported. Label a concrete
live readback as observed; reserve verified for the predicate actually exercised.

Examples of useful distinctions:

- A plugin appears in a file, but its authentication state is unknown.
- A render check failed; no deployed change has been demonstrated.
- Files are staged in one checkout; an unrelated chat's completion claim does not
  prove those files were applied.
- Quota usage decreased, but physical free space did not change.

## Convergence plan

Include:

1. Source/destination/consumer map and intended runtime root.
2. Key-level comparison: identical, intentional difference, missing, conflicting,
   or unknown; note precedence and competing writers.
3. Proposed edits and apply sequence, including preserved capabilities.
4. Secret-safe rendering location and validation commands.
5. Before-state snapshot, rollback mechanism, and cutover/readback criteria.
6. Explicit limits: plan only or implementation authorized, protected paths,
   current resource allowance, deadline, and stopping condition.

## Handoff packet

- Objective and concrete completion predicate.
- Owning repository, branch/base, allowed paths, and protected state.
- Observed facts with evidence pointers; unresolved hypotheses separately.
- Small implementation steps and dependencies.
- Scoped validation, rollback, finite attempt budget, and receipt destination.
- Current authorization and any current provider/model constraints.

Use existing durable owners when available. Preparing this packet does not send
it to another chat, activate a schedule, or grant destructive cleanup authority.
