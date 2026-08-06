# Dynamic Provider Selection

> Relocated verbatim from `AGENTS.md` (2026-08-06) under the instruction-surface byte budget
> (`institutio/governance/gates.yaml` → `instruction_surfaces`, check S). The binding stub in
> `AGENTS.md` points here; this file is the full doctrine.

Provider catalogs are live external state, not repository constants. Do not encode model IDs,
catalog snapshots, name-based capability guesses, or fixed fallback tables in dispatch logic,
instructions, tasks, or receipts.

- Derive provider-neutral requirements from the current task and discover reachable capabilities at
  execution time. Treat `tier:*` text as opaque context. Express numeric constraints only through the
  owning execution-profile schema, such as `profile:<field>:<value>`.
- When the provider exposes sufficient live metadata, filter and rank that catalog by capability,
  availability, cost, and task pressure. When it does not, leave model selection to provider Auto.
- A human-configured model override is an escape hatch, not a default. Validate it against the live
  catalog when possible; otherwise fail blocked instead of inventing or silently substituting a name.
- Tests use arbitrary and renamed fixture IDs and must prove that catalog add/remove/reorder changes
  are handled without a code change. Receipts may record the actual selected model when exposed, but
  never promise a future model name, price class, subscription outcome, or fixed tier mapping.
