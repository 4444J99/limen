# Blinded target-reader protocol

This is the collection instrument for `PSP-P03-W07`. It does not contain reader
results and does not satisfy the work packet by itself. Use one qualified,
independent reader for each of the five archetypes below. Do not coach a reader,
explain the intended answer, or count an author, implementation agent, or model
response.

## Copy-ready reader block

Copy only the block between `READER BLOCK START` and `READER BLOCK END`.

<!-- READER BLOCK START -->

I build production systems that solve expensive problems.

For a direct client, I help a named sponsor make a bounded decision about an
active AI or software initiative whose decision rights, verification, cost
boundaries, or handoff are unclear. For a recruiter or hiring executive, I
bring evidence-backed senior systems judgment to a named architecture or
engineering mandate.

The expensive problem is delivery that cannot say who decides, what verified
done means, how cost is bounded, or who owns the system after handoff.

Limen is an inspectable governed-delivery system with operating, failure, and
verification evidence in its owner environment.

The work is not to replace the buyer's team, take control of the organization,
or create permanent dependency. A written mandate defines authority; current
owners remain visible; the work concludes with evidence, rollback information,
and handoff.

If you are a client, discuss a fixed-scope Agentic Delivery Audit. If you are a
recruiter or hiring executive, discuss a senior systems architecture or
engineering role with a named mandate.

Read the passage once. Answer without searching the project. If something is
unclear, say so instead of guessing.

1. What role or identity do you think this person is presenting?
2. Who do you think the primary buyer or decision-maker is?
3. What expensive problem do you think they solve?
4. What is the strongest proof or evidence you noticed?
5. What should the next action be after reading this?

<!-- READER BLOCK END -->

## Facilitator-only collection rules

Use exactly these five slots, with one person per slot:

1. `client` — CTO, VP Engineering, or Head of Platform.
2. `internal_evaluator` — engineering director or platform lead.
3. `recruiter` — technical or executive recruiter.
4. `executive_sponsor` — founder, COO, or general manager.
5. `product_partner` — domain operator or product-operating partner candidate.

Record responses in
`docs/positioning/program/w07_blinded_reader_response_template.json`. Keep only
anonymous IDs `R1` through `R5`; do not record names, companies, email
addresses, phone numbers, handles, or private project details. Score only what
the reader independently identified. If the facilitator explains an answer,
the reader searches the project, or prompt leakage occurs, discard that
response and collect a fresh one.

The deterministic validator requires five valid records, at least 20 of 25
identified elements, at least four role identifications, at least four buyer
identifications, at least four CTA identifications, no unresolved
authority/takeover objection, and no objection repeated by three readers.

## Accepted stimulus provenance

The stimulus is pinned to
`organvm/limen@c94bc3748fcf2d1dc802a4bae972df23d9a9fbec` and is assembled from
the accepted W01-W06 public-facing copy in:

- `docs/positioning/narrative-ladder.md`
- `docs/positioning/client-narrative-and-problem-map.md`
- `docs/positioning/recruiter-narrative-and-role-map.md`
- `docs/positioning/authority-and-trust-language.md`

The durable protocol-of-record is also preserved in issue #2188 comment
`5271321054`. The issue remains open until five genuine responses, a decision
memo, and the registered non-circular receipt predicate all pass.
