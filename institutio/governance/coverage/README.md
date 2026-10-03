# Institutional coverage and ownership

Version 1, 2026-10-01. **A generic responsibility registry and bounded source crosswalk, not a personal case file or certification of operational coverage.**

The person chooses the purposes. Institutional functions coordinate resources, expertise, protection and continuity. Support remains person-directed, consent-bound and practically accessible.

## Deliverables

- `registry.json`: 25 stable responsibilities, comprising 16 life domains, seven shared capabilities and two practices. Each records a proposed accountable function, outcome, boundary, handoffs, first acceptance requirement and source-qualified reuse decision. `legacy_term_crosswalk` retains the original nine terms.
- `instance.example.json`: a synthetic person-level assessment contract. All 25 responsibilities start with unknown applicability and unassessed service state. It is not an assessment of an actual person.
- `validate.py` and `test_validate.py`: offline declaration checks and synthetic regression tests. No network, credential access, writes or external actions.

## Architectural placement and authorities

Systemic domain, personal outcome, institutional responsibility, capability, workflow and implementation are linked axes, not one rigid ownership tree. A matter can involve several domains but retains one accountable coordination owner until a handoff is accepted. Handoff links express cooperation, not executable scheduling dependencies; cycles can be legitimate.

This folder owns responsibility identity and the coverage contract only. It does not absorb domain implementations into Limen, override the polyrepo default, require a repository per domain or create another repository inventory.

| Question | Existing authority |
|---|---|
| Declared institutional organs | `organ-ladder.json` |
| Repository custody and identities | `institutio/github/estate.yaml` |
| Working-session projection | `institutio/governance/session-streams.yaml` and its existing derivation |
| Task and lease state | TABVLARIVS; `tasks.yaml` is a read-only projection |
| Verification gate registration | `institutio/governance/gates.yaml` |
| Responsibility taxonomy | This directory's `registry.json` |

The original nine-item view is a working-session projection, not an exhaustive life-domain inventory. This change does not alter that roster, spawn sessions, add organ-ladder rows, activate generators, rename projects, schedule jobs or expand execution authority.

The observed repository name is a locator, not taxonomy identity or a branding decision. IDs survive name, product and repository changes. Never reuse an ID for a different responsibility. Record predecessor/successor mappings for genuine splits or merges rather than silently repurposing aliases.

## Interpreting reuse and gaps

Observations are pinned to `source_snapshot`. A census link proves only that a pillar and institutional home are declared. It does not prove files exist, tests pass, a service runs or a person receives support.

`partial_declared / extend` identifies reusable declared scope. `unmapped / discover` means this bounded review did not establish an adequate binding, not that the capability is absent estate-wide.

Initially, 18 responsibilities have declaration-level reuse links. Seven remain unmapped: habitat, provisioning, benefits, mobility, civil identity, knowledge stewardship and whole-life continuity. Recover existing siblings and decisions before selecting homes. An unmapped knowledge row is not permission to duplicate an existing knowledge suite.

Pillar selectors can match multiple census entries, especially governance and observation. They are not unique organ or repository IDs. Refine references against the existing source authority rather than copying its mutable inventory.

Education, finance, health and law remain life domains. Governance, correspondence and representation are shared capabilities, alongside operations, research, knowledge and continuity. Consulting and contributions are practices serving several domains. New outward contributions remain distinct from outstanding-work stewardship; outbound approval remains intact.

## Ownership and protected instances

`accountable_function` is a proposed role, not an accepted appointment. A real implementation binds it to an authorized owner who accepts responsibility. Delivery can involve a suitable institution, professional, support person, self-directed arrangement or technical service. Suitability must be established outside this catalog.

Real instances belong in appropriate access-controlled operational storage, not this public tree. Even evidence pointers can disclose sensitive information; only synthetic examples belong here. Public source contains no health, legal, financial, client or relationship records.

Applicability is `unknown`, `active`, `contingent`, `not_applicable` or `declined`. Every responsibility needs an explicit disposition. Exclusion requires a reason, authority and current applicability evidence. Declining involvement is not a personal failure.

Service state is `not_assessed`, `planned`, `available`, `operating`, `verified` or `blocked`. These are coverage declarations, not TABVLARIVS task states. Available, operating and verified assertions require owner, provider and authority references. Blocked requires `blocker_ref` into the protected owning record. Only an active need can assert a delivered outcome.

A verified assertion requires eight current evidence references:

| Key | The authorized reviewer must substantiate |
|---|---|
| `purpose` | Person-approved outcome and applicability |
| `consent` | Scope, access, revocation and permission |
| `owner_acceptance` | An accountable owner accepted responsibility |
| `provider_access` | A suitable delivery path is actually usable |
| `resources` | Necessary money, time, equipment, documentation and accessibility |
| `workflow` | Actions, deadlines, handoffs and follow-up |
| `outcome` | Actual receipt of the intended support or result |
| `fallback` | Viable, appropriately tested escalation and recovery |

Each reference carries `ref`, `observed_at` and `valid_until`, with timezone-aware timestamps satisfying `observed_at <= as_of < valid_until`. The responsible reviewer sets expiry according to evidence and risk; there is no invented universal review interval. State can regress as arrangements fail or evidence expires.

The checker never fetches evidence payloads, authenticates attestations, judges professional qualifications, establishes eligibility, provides regulated advice or enforces live access controls. A structurally valid assertion can be factually wrong. Output always includes `service_delivery_certified: false` and `evidence_payloads_verified: false`.

## Verification

From the repository root:

```sh
python3 institutio/governance/coverage/validate.py
python3 institutio/governance/coverage/validate.py --instance institutio/governance/coverage/instance.example.json
python3 institutio/governance/coverage/test_validate.py
```

Optional `--as-of` accepts a timezone-aware ISO timestamp for reproducible tests. Real assessments should use current UTC, the default, not a historical test date. Exit codes: 0 validates declarations; 1 reports failed checks; 2 reports unreadable or malformed inputs. Error output omits supplied values and private paths. This is not a comprehensive personal-data or secret scanner.

Tests cover stable identity, duplicates and dangling references, source/disposition agreement, prohibited catalog-level coverage claims, complete instance disposition, readiness ownership, explicit exclusions, evidence expiry, future observations and required outcome evidence.

## Integration scope and remaining owner work

This is a bounded, tested registry deliverable. **The checker is not yet registered in the canonical gate matrix, no runtime consumes real instances, and no actual support has been activated.** This PR is not full institutional coverage.

Further integration stays with the same governance owner and PR lineage. Add one entry in `institutio/governance/gates.yaml`, following its existing schema, for the test command and paths covering this directory. Do not create another workflow or task board. Run the implicated scoped checks on a complete exact-ref checkout before integration.

Recover and bind implementation homes through the existing estate registry, source manifests and product-family decisions. Reuse direct matches; extend partial scope; build only after a documented gap and justified function boundary. Preserve existing VNIVERSE, SPIRA, knowledge, education, communications and other product boundaries rather than replacing them with this catalog.

Use the existing operational review cadence when consumer wiring is accepted; this change installs no schedule. Review bindings when sources, roles, authority, providers or repository locations change. Assess actual needs only through a consented private workflow. Prioritize consequential unmet needs and deadlines, not whichever category produces easy code.

Before claiming coverage, exercise a multi-domain transition, provider absence, lost digital access, expiring evidence, a declined responsibility and a blocked essential need. Measure accepted ownership, usable delivery and observed outcomes separately. Unknown applicability, a zero denominator and catalog completeness must never produce a blanket success score.

## Provenance

The source base and paths are recorded in `registry.json`; observation types distinguish census declarations from documentation reads. Conceptual scope follows the October 1 institutional-coverage request. The implementation crosswalk is intentionally narrower than an estate-wide audit. No private source-record contents are reproduced.
