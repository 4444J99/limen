---
name: agent-runtime-audit
description: Audit AI-agent runtime layout, configuration ownership, cleanup candidates, and drift between legacy settings and a shared runtime. Use for an agent-environment audit or a configuration-convergence plan, with evidence-based cleanup review and bounded implementation when requested.
---

# Agent runtime audit

Produce a current, source-owned audit and a reviewable convergence plan. Preserve
the distinction between reported cleanup, staged work, applied configuration,
verified behavior, and remote publication.

## Scope and authority

Resolve the requested mode: audit, cleanup review, convergence planning, or
authorized implementation. Honor plan-only instructions. A request to review
cleanup does not authorize deletion, disabling capabilities, or live deployment.

Read the applicable instructions, ownership manifests, and existing plan first.
Discover actual runtime roots, configuration paths, environment variables, source
repositories, worktrees, remotes, and active processes. Resolve paths from the
current environment; old screenshots and historical paths are leads.

On a chezmoi-managed host, edit the owning source and use its supported rendering
and application path. Do not patch a generated config merely because it is the
file the agent currently reads. Preserve unrelated dirty work and human sessions.

## Build the evidence inventory

For each relevant provider or agent surface, record:

- Installed launcher/version and effective runtime/configuration locations.
- Source owner, rendered destination, dynamic path variables, and precedence.
- MCP/plugin/skill configuration and whether each capability is configured,
  installed, authenticated, reachable, or exercised.
- State types: source configuration, generated config, sessions, databases,
  logs, caches, downloads, memories, and custody material.
- Current diagnostics, active users/processes, and repository local/remote state.

Use direct read-only evidence before broad scans or intrusive diagnostics.
A configuration entry is not a working integration. Unknown or authentication-
needed capabilities remain visible; do not remove them to make an audit green.
Do not equate an unused-skill report with proof that the skill is obsolete.

Record provenance and time per finding. Keep observations from different agents,
checkouts, sessions, and versions separate. If one session says cleanup is complete
and another says it is staged or guard-blocked, inspect the owning files and
receipts before reconciling them.

Use [audit-and-handoff.md](references/audit-and-handoff.md) for compact tables and
work packets. Read [recorded-workflow.md](references/recorded-workflow.md) only when
historical rationale or evidence boundaries matter.

## Review cleanup candidates

Classify each candidate by owner, value, regeneration method, active use, and
recoverability. Distinguish reclaimable downloaded/cache content from native
sessions, SQLite/WAL files, memory, dirty worktrees, protected data, and custody
partials. Runtime quota accounting and physical free disk are different measures;
report both when diagnosing storage pressure.

Prefer retention or reversible quarantine for unresolved candidates. Check live
local/remote parity and independent custody/restoration evidence before any
retirement that requires them. A clean tree, pushed commit, Git ignore rule, old
timestamp, or existing archive alone does not establish deletion eligibility.
Never delete conversations or state simply to clear an admission limit.

For oversized instructions, propose an isolated source edit that removes proven
duplication and links to its canonical owner. Preserve operative constraints and
capabilities. Measure the result and check routing/coverage before claiming a trim
is safe. Keep review and execution as separate statuses.

## Plan configuration convergence

For this user's shared-runtime convergence work, integrate legacy configuration as
real source-owned configuration; a symlink is not the requested end state. This
preference does not authorize removing existing links or legacy state during an
audit.

1. Map legacy sources, generated destinations, runtime consumers, and ownership.
   Separate durable config from mutable vendor state.
2. Compare keys and effective semantics, including precedence, dynamic variables,
   defaults, provider-specific features, credentials, and unknown fields. Preserve
   intentional differences and identify competing writers.
3. Render the proposed source in a private, isolated destination using the owning
   tool. Keep secrets out of terminal output, diffs, commits, and reports.
4. Compare rendered output with the legacy and current effective configurations.
   A failed render/comparison is an unresolved validation result; capture its
   actual error and cause when established. Do not infer a successful merge from
   a proposed command or plan.
5. Define the smallest source change, apply order, rollback artifact, and behavior
   checks. Stage cutover so all intended capabilities remain represented.
6. If only planning was requested, stop at the evidence-backed plan and handoff.
   If implementation is authorized, apply only its bounded scope, validate effective
   paths and provider behavior, and read back the source and deployed state.

Keep reasoning/planning and implementation packets distinct when requested. Respect
current model/provider constraints; do not hardcode historic model names or launch
another agent/chat merely because an old plan suggested it.

## Verify diagnostics and implementation

A command named check or dry-run may still write state. Inspect or exercise
uncertain diagnostics against isolated fixtures before treating them as harmless.
Observe outer logs/stamps as well as the component store, and use the predicate's
own exit code. Compare reported results with actual side effects.

Use the changed component's scoped checks, a finite deadline, and current resource
admission. A stale census, missing authority, or repeated unchanged hard stop
requires a changed predicate before retrying; never suppress a failing capability.
Do not restart live agents or schedule ongoing work merely to finish an audit.

For authorized changes, capture before/after evidence, installed behavior,
rollback readiness, and the exact commit/remote receipt when publication is in
scope. Keep source validation, deployment, and application acceptance separate.
Summarize verified findings and remaining uncertainty, with a named owner and
next check for unfinished work. Do not describe a plan or queued change as applied.
