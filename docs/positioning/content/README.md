# PSP-C08 proof-led content — private preflight

This directory is a **private staging package**, not a publishing queue. It prepares the reversible work for PSP-P09 without asserting that any report, derivative, metric, approval, send, or outcome exists in the world.

## What this package establishes

- A 90-day editorial calendar with one source, audience problem, door tag, signal, and stop rule per asset.
- A flagship report draft that uses only the wording admitted by the source register.
- Derivative drafts, a synthetic protocol walkthrough, and a correction-case-study shell that cannot be mistaken for a real incident.
- A measurement contract that keeps test events separate from observed outcomes.
- A release boundary for the two external-effect leaves: `PSP-P09-W02` and `PSP-P09-W08`.

## How to use it

1. Run `python3 scripts/check-psp-c08-preflight.py` and `python3 scripts/psp_c08_content.py --check` before an editorial review.
2. Keep every public-facing sentence within `claim-source-register.json`'s allowed wording, or mark it as a hypothesis or a withheld field.
3. Treat the report, channel copy, and case-study material as unpublished until the relevant source evidence and human gate are present.
4. Record actual measurement only in the receiving system after a human-approved release; never overwrite the synthetic fixture in `measurement-contract.json`.

## Authority boundary

`PSP-P09-W02` remains behind `HG-PUBLIC-IDENTITY`. `PSP-P09-W08` remains behind `HG-PUBLICATION-SEND`. This repository package neither grants those approvals nor attempts publication, distribution, capture activation, analytics changes, or a send.

The live program graph remains authoritative. This preflight is deliberately not a PSP-P09 receipt and does not satisfy a leaf or phase predicate.

Execution requirements are derived from that graph as capabilities plus reasoning, effect, and
effort. Provider selection happens from the live runtime catalog at dispatch; this package stores
no provider model slug and silently substitutes none.

## Deterministic staging controls

`content-control.json` maps every P09 work item to admitted or explicitly withheld source IDs, exact draft citations, a door tag, and a 30-day review date. `narrative-fixtures.json` provides architecture and correction drills with `[redacted]` private-data fields. `review-gates.json`, `campaign-analytics-schema.json`, and `dry-run-publication-package.json` keep review, analytics, and publication packaging in a no-effect state.

`python3 scripts/psp_c08_content.py --dry-run` renders the exact held package; it makes no network call, schedules nothing, and reports zero sends and publications.
