# HR Organ — Template Library

The macro platform's jurisdiction-aware template library. Each skeleton is tagged
by jurisdiction and mandatory/elective status. The policy drafter (W2) loads the
appropriate skeleton and populates client-specific fields.

## Structure

```
templates/
  handbooks/              # Handbook skeletons by primary jurisdiction
    federal.md
  policies/               # Individual policy skeletons by policy type
    at-will-employment/   # Jurisdiction variants
    anti-harassment/      # Jurisdiction variants
    leave-of-absence/     # Jurisdiction variants
  compliance/             # Jurisdiction rule annotation files
    states/               # Per-state rule annotations
    federal.yaml          # Federal rule annotations
  comp-benchmarks/        # Industry benchmark skeletons
  rubrics/                # Performance rubric skeletons
```

## Usage

1. Identify the client's jurisdiction(s) from the posture record.
2. Load the handbook skeleton and policy skeletons for those jurisdictions.
3. Populate mandatory policies first, then elective policies the client selects.
4. Run the ethics sentinel (W8) before any draft leaves the organ.

*All templates are drafts for practitioner review. Nothing is binding until the
practitioner reviews and the client signs off.*
