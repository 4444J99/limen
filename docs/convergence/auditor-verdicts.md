# Auditor Verdicts — the convention (owner of record: governance)

Six repos independently implement "score a thing against criteria, emit a verdict":
`growth-auditor`, `organvm-scrutator`, `laurea`, `vulnpulse`, `cve-watch`, `bountyscope`.
The shared shape is real. The open design decision recorded in
`institutio/governance/convergence.yaml` (`auditor-verdicts`, formerly `owner: null`) was
**library or convention** — resolved 2026-07-26 by the estate's own precedent cascade:

**Convention, not library.** Every prior convergence of this kind in the estate landed as
declared data plus per-consumer derivation, never a shared runtime dependency: GATES
(`gates.yaml` + `check-gates.py`), SENSORS (`sensors.yaml` + `beat-sensors.py`), PARAMETERS,
CORPORA (`corpora.yaml` + `check-corpora.py`). The measured baseline that motivated
IF-SHARED-SUBSTRATE — zero cross-repo runtime dependencies across 310 repos — is a property
to preserve where a shape can be carried by convention: six small auditors gaining a common
import would couple six release cycles to buy six struct definitions.

## The verdict shape

A conforming auditor emits, per audited subject, a record with these fields (JSON or YAML;
field names exact, extra fields free):

```yaml
subject: <what was audited — repo, package, document, CVE id, metric target>
criteria: <the ruleset/rubric identifier the subject was scored against>
scores: {<criterion>: <number|grade>, ...}   # per-criterion detail, optional but preferred
verdict: pass | fail | hold | <graded tier>   # the one-word outcome a consumer can gate on
evidence: [<pointers — file paths, URLs, ids — never bulk content>]
emitted_at: <ISO-8601 UTC>
```

Process conventions:

- **Exit code mirrors verdict** when the auditor runs as a gate: `0` ⟺ pass, non-zero
  otherwise — the executable-predicate rule (`0` ⟺ done) applied to judgment.
- **Verdicts are records, not logs**: append-mode artifacts with stable addresses, so a
  later run never silently rewrites an earlier judgment.
- **Criteria are declared data**: the ruleset an auditor applies lives in a versioned file
  the verdict names via `criteria:` — never only in code.

## Tenancy

The six implementations are **tenants of the convention**: each keeps its own code and
release cycle and conforms its emitted shape. Divergence from the shape is drift to fix in
the tenant, not grounds for a new schema. A shared library remains a *possible future
lift* if a seventh implementation appears with genuinely duplicated non-trivial logic
(weighting algebra, evidence collation) — that would reopen the row as `lifting` with the
duplicated code named. Until then the row stands `converged` on this document.

Note: `laurea` is clustered here (developer-portfolio metrics auditor), not in education —
see `docs/convergence/learning-engine.md` dispositions.
