# Dynamic provider routing

Limen routes from a task's current needs, not from a model-name table. Provider catalogs change;
their names, versions, availability, prices, and account reachability are runtime outputs.

## Contract

Each dispatch derives an extensible execution profile from live task evidence:

- reasoning depth and verification strength;
- minimum context and output room;
- tool and attachment requirements;
- cost and latency pressure;
- planning-only versus build permission; and
- optional generic numeric constraints such as `profile:min-context:131072`; and
- an opaque free-form hint from an existing `tier:*` label.

The profile is not a closed tier enum. A `tier:*` value is carried into the receipt and prompt but is
never interpreted by Limen, so `tier:economy`, `tier:plan`, and a future arbitrary value produce the
same routing profile for the same task evidence. Numeric `profile:<field>:<value>` labels are typed
from the execution-profile schema instead of a label-name table. Provider adapters filter their
current reachable catalog by hard capabilities, rank the survivors from metadata and current
pressure, and record the profile, catalog hash, selection source, and selected model when exposed.

OpenCode is selected from `opencode models --verbose`. Empty, malformed, stale, or capability-poor
results produce `failed_blocked`; there is no built-in model fallback and no name heuristic such as
`free`, `code`, or a vendor family name.

Warp/Oz normally receives the execution profile with the Action's `model` input blank. Warp Auto owns
the changing underlying catalog because Oz exposes model IDs but not enough capability/cost metadata
for Limen to rank them honestly. `LIMEN_WARP_MODEL_OVERRIDE` is an escape hatch only: dispatch first
proves the value exists in the current `oz model list --output-format json` result.

## Safety and planning

Credentials, secrets, personal data, irreversible deletion, paid overages, public-identity claims,
and `needs-human` work are rejected before a prompt reaches Warp/Oz. A planning-only profile uses the
explicit `mode:plan-only` task label and requires the existing current Fable acceptance/cap receipt;
without it, the request becomes maximally verified executable work. An accepted planning run returns
a build packet and may not build.

## Regression predicate

Provider-routing tests must use arbitrary/renamed fixture IDs and reorder/add/remove candidates. A
test that depends on a real model name is itself a regression. The implementation must prove:

1. catalog order and renames do not change capability semantics;
2. inaccessible models are never synthesized;
3. hard capability gaps block instead of silently downgrading;
4. explicit overrides are live-validated;
5. Warp defaults to provider Auto with no model ID; and
6. arbitrary `tier:*` text cannot change routing behavior; and
7. selection receipts contain no credential values.
