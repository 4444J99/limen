# Objective and routing

Move the system from the July 9-14 closeout receipt to the next truthful, durable state. The live
environment chooses the work; this module defines what a candidate must prove before it may borrow
resources.

## Work-loan admission

Require one bounded objective with:

- an owner and owner repo;
- an executable predicate and durable receipt target;
- expected value and cost-of-delay evidence;
- a cost/usage ceiling and required reserve;
- dependencies, runtime requirements, and preservation risk;
- explicit lane-switch and session-boundary conditions.

Reject or owner-route work that cannot underwrite itself. Do not turn an easy nearby diff into
priority authority. Keep money, correspondence, contribution, substrate, past/present/future review,
and control-plane work visible as separate purpose lanes.

## Dynamic provider and lane selection

Derive provider-neutral requirements from the admitted task, then discover live capabilities,
availability, cost, rate limits, host pressure, and remote capacity. Use strong reasoning only where
the task earns it; use cheaper/faster workers for bounded implementation and verification. Do not
encode model names or a fixed fallback ladder. Local concurrency limits do not cap remote lanes.

If the laptop is under pressure or below the live reserve gate, switch to remote or receipt-only work.
If one provider is at capacity, select another eligible provider or `wait_relay`; do not busy-loop or
manufacture a capacity claim.
