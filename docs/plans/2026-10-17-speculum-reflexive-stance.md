# Codify the Speculum reflexive stance as cross-agent doctrine

Issue: #2989
PR: (pending)

## Context

The operator pointed at the private `4444J99/speculum-opencode` README intro as the posture every
agent should hold inside this system. Limen owns the *protocol* (Peer Conductor Contract, task
states, evidence-bound status words) but not the *stance*. Clause-by-clause, most of the intro already
lives here under other names (observable behavior = evidence-bound status words; no prediction oracle
= Never Over-Claim). Genuinely new: absorb structure not totality; one source with lossy projections;
observation never substitutes for the lease+receipt path; agents mutually legible; reflexive depth
capped at three (from the Speculum's own Key Decisions).

## Resolved design decisions

- **D1 — Tier-1 doc plus a pointer in the uncapped standard, not `AGENTS.md`.** `AGENTS.md` sits over
  its 32,768 B budget with an open `debt:` line (check S); the standard's rule 14 admits a rule to the
  capped file only if needed every turn and not hook-enforced. A posture is neither.
- **D2 — Paraphrase, never quote.** The source repo is `vault_private` in the estate registry.
- **D3 — A predicate, not prose.** Check U in `scripts/check-agent-docs.py` holds the doc, its four
  binding phrases, the portal link, and the depth cap in `bounded-composition.md`.
- **D4 — Self-eating metric is a measurable, so it is a board ticket, not doctrine.**

## Steps

1. Write `docs/architecture/reflexive-observation.md` (four rules, out-of-scope note).
2. Bind it as item 15 and letter check U in `docs/agent-instruction-standard.md`.
3. Add the depth-cap paragraph to `docs/architecture/bounded-composition.md`.
4. Add check U to `scripts/check-agent-docs.py`; negative-test it by breaking one phrase.
5. Follow-ups (filed, not done here): stale `organvm/speculum-opencode` key at
   `institutio/github/estate.yaml:939`; self-eating metric as a TABVLARIVS ticket; if promoted to a
   Session Discipline rule, check M needs a matching `AGENTS.md.tmpl` summary in domus-genoma.

## Premortem

- **Most plausible wrong turn:** the operator wanted the Speculum *built into* the system (an observer
  organ that maps lanes), not a doctrine file. This plan lands the stance and defers the organ; the
  rules are written so an organ can implement rule 4 without changing them.
- **Check U is phrase-presence only**, so it proves the doctrine exists, not that lanes obey it.
  Obedience is the receipts' job (rule 4); a receipt-legibility predicate is the natural next owner.

## Verification

- `python3 scripts/check-agent-docs.py` exits 0; negative test (broken phrase) exits 1 naming `(U)`.
- `bash scripts/verify-scoped.sh`
