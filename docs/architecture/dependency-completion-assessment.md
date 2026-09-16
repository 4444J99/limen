# Dependency completion assessment handoff

Owner: Codex, Limen PR #2651. Production policy remains disabled until its
activation prerequisites have current evidence.

## Authority and registration

The existing conduct session protocol owns registration. The deployment owner
registers the assessor from its own executor-authenticated environment, with its
real agent, surface, native session identity, `dependency-assessment` capability,
and concurrency of one. Use the existing `limen conduct register --session`
interface or `AssessmentHttpClient.register(ConductorSessionV1)`.

A dedicated service uses its actual service origin. Direct human sessions remain
`human_protected: true`; the keeper refuses to select another protected session
for this work. Never change an existing session's protection to make it eligible.
The credential principal must have executor authority, and read access needed to
inspect its assigned graph. Readback must show the expected identity, capability,
healthy heartbeat, accepting-work state and available slot before submission.

Registration does not authorize new capacity while the #269/#1995 admission gate
is unresolved. The dedicated read and executor credentials, source commit and
digest, deployment identity and invocation contract must have their own approved
owners. The callback rejects generic GitHub, conductor and relay credential
references and requires distinct explicit values.

## Finite handoff

1. The dedicated completion observer publishes the four-field hint to the keeper.
   The hint authorizes no launch, reservation or merge.
2. The conductor reads the authenticated hint and compiles an immutable packet
   using `limen conduct compile-dependency-assessment`. The reviewed contract
   binds the executor session, source commit/digest, predicate, receipt owner,
   underwriting and deadline. Persist that exact packet in its approved owner.
3. `limen conduct consume-dependency-completion` submits at most once. A pending
   assessment returns exit 77 with the keeper run ID. An ambiguous submission
   requires keeper reconciliation; it never authorizes a blind new packet.
4. The approved native wake route delivers that run ID to the selected executor's
   configured `limen conduct execute-dependency-assessment` entrypoint. The route
   must use deployment-owned command/configuration and isolated credentials.
   Commands, source paths, credentials and authority cannot come from the hint.
5. The callback re-reads the graph, reconstructs and compares the packet, claims
   the selected lease generation and atomically admits one attempt. Only then
   does it execute the pinned source. Concurrent callbacks cannot launch twice.
6. The conductor reconciles once through the keeper. An accepted assessment
   receipt remains `automatic_acceptance: false`; merge admission is separate.
   Restarting the consumer preserves the binding and does not reserve a new run.

The production native wake route still needs deployment integration and evidence.
This document describes the tested protocol boundary, not an installed service.
No retired daemon is required by this handoff.

## Bounded execution and recovery

The assessor has a 95-second process budget. Every broker exchange has a
20-second process wall limit, 15-second socket timeout, bounded input/output,
redirect refusal and no ambient proxy inheritance. The packet and admitted lease
must retain more than 150 seconds for assessment and terminal reporting.

Lost admission responses never launch source. Lost report responses may leave an
accepted keeper receipt; read that evidence instead of executing again. Unknown
or incomplete graph metadata, changed source/authority, stale leases, malformed
responses and missing credentials remain unmeasured. No retry or polling loop is
part of the callback.

## Verification and current service evidence

`cli/tests/test_dependency_completion_integration.py` composes the actual
JavaScript Worker hint store and reconciler with real Python keeper registration,
reservation, attempt admission, isolated child execution and accepted receipts.
It verifies a terminal receipt survives a new consumer and duplicate hint, while
another human-protected executor is refused before launch. Its dedicated scoped
gate includes both Worker and Python paths and the completion policy.

The authenticated capability read at **2026-09-16T09:58:52.196Z** observed **zero
registered dependency assessors and zero healthy unprotected assessors**. It
changed no sessions, leases or credentials. Owner PR #2651 retains the deployment
work; existing admission owners #269/#1995 remain prerequisites. The next deployment
step, after those prerequisites and isolated credentials are evidenced, is the
reviewed executor registration followed by capability readback and one protected
canary. Local integration tests do not satisfy that deployment predicate.
