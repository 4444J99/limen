# Bounded Composition

> Relocated verbatim from `AGENTS.md` (2026-08-06) under the instruction-surface byte budget
> (`institutio/governance/gates.yaml` → `instruction_surfaces`, check S). The binding stub in
> `AGENTS.md` points here; this file is the full doctrine.

A long-running campaign or whole-repo gate may exist only as a thin orchestrator over independently
owned, bounded units. Every unit declares its inputs, owner, predicate, execution profile, finite
retry policy, bounded-output policy, and durable receipt. The aggregate preserves completed receipts,
resumes from them, and reports counts plus links; it never reruns successful children or emits their
full logs.

Apply the same rule to artifacts: README files are indexes over cohesive modules, not concatenated
prompts, reports, transcripts, or append-only scrawl. Split on semantic ownership and independently
testable interfaces, not an arbitrary line count. A file repeatedly changed for unrelated reasons has
already exposed a missing module boundary.

CI must shard module predicates and run eligible shards in parallel. The final integration gate checks
the shard receipts plus only genuine cross-module seams. Each shard has an execution-profile timeout,
finite transient retry policy, output cap, and stable receipt; no unbounded wait, retry, or log stream
is a valid verification strategy.
