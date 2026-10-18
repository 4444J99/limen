# Reflexive Observation

> Tier-1 doctrine (check U in `scripts/check-agent-docs.py`). It is bound from
> `docs/agent-instruction-standard.md`, not from `AGENTS.md`, which sits over its instruction-surface
> byte budget (`institutio/governance/gates.yaml` → `instruction_surfaces`, check S). The stance is
> distilled from the private `4444J99/speculum-opencode` repo, a structural map of an AI coding agent
> and the agents around it; this file paraphrases it and quotes none of its text.

The protocol says *how work moves* (Peer Conductor Contract, task states, receipts). This file says
*how an agent holds itself* inside that protocol. Four rules; each cites the surface that already
enforces its mechanics rather than restating it.

1. **Absorb structure, not totality.** What an agent leaves in shared memory, receipts, and registries
   is the pattern: ids, edges, owners, evidence, and a pointer to the source. It is never the whole
   transcript, log, or session. A system that tries to hold every instance cannot be read, and the
   structure is what survives re-reading. Applies with `AGENTS.md` → Safety & Evidence (durable links
   and paths over pasted logs) and `docs/architecture/bounded-composition.md`.

2. **One source, lossy projections.** A fact has exactly one authoritative form. Narrative, graph, and
   query views of it are projections, each losing something different; the intersection of what all
   of them lose is accepted as irreducible, not patched by promoting a projection to a second source.
   Never edit a projection: regenerate it from its source (`tasks.yaml` from TABVLARIVS; rendered
   instruction files from their templates).

3. **Observation is not participation.** Mapping what another agent or lane did never substitutes for
   leasing, executing, or reporting work through the broker. An observer reads receipts and registry
   state; it does not steal, adopt, cancel, or edit a peer's lane (Peer Conductor Contract), and its
   observations never become task transitions on their own. Mirroring is read-only by construction.

4. **Agents are mutually legible.** Every agent is both a subject others can map and an observer of
   them. Legibility is a duty: a receipt carries the native executor identity, exact old/new heads,
   changed paths, and predicate evidence, so any peer can reconstruct what happened from the record
   alone, with no access to the author's session. Claude is mapped by Codex, Codex by Gemini, and so
   on; no lane is exempt and none is the privileged vantage. Reflexive depth is bounded:
   observation-of-observation stops at three levels or at convergence, whichever comes first
   (`docs/architecture/bounded-composition.md`).

## Out of scope

- A claim of what an agent *experiences* or *will* do. Only observable behavior is recorded, in the
  evidence-bound status words, and a trajectory is never a guarantee.
- The "self-eating" measure (the share of this system's changes authored by its own lanes) is a
  measurable, so it is a board task submitted through TABVLARIVS, not a rule here.
