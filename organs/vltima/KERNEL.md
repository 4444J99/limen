# VLTIMA Kernel

The VLTIMA kernel is the universal civilizational substrate underneath the
organs. The existing five institutional primitives stay intact; this document
names the lower layer they project from and the value layer they must eventually
support.

The executable registry is [`kernel.yaml`](kernel.yaml). `scripts/validate-vltima-kernel.py`
loads that registry, verifies the canonical primitive set, and checks every organ
projection against it. `scripts/validate-vltima-kernel.py --json-output` emits the
derived machine-readable substrate, and `--write-projection` persists the canonical
projection at [`projection.json`](projection.json). Its portable contract lives at
[`spec/contracts/vltima-kernel-projection.schema.json`](../../spec/contracts/vltima-kernel-projection.schema.json)
and is checked by `scripts/validate-contract-schemas.mjs`. `--check-projection`
is wired into `scripts/verify-whole.sh` so the checked-in substrate cannot drift
from `kernel.yaml` or `organ-ladder.json`: primitive graph nodes and source
edges, layers, projection groups, each organ's kernel mapping, and a typed
`graph` object that connects layers, primitives, projections, and organs. The
contract is named `vltima.kernel-projection` with `schema_version: 1`.
Each organ also carries a structured `kernel_map` in `organ-ladder.json`, so
Member/Mandate/Standing/Standard/Governance mappings are executable data instead
of prose embedded in a `domain_map` sentence.

For direct inspection, the Limen CLI exposes projection selectors over the same
derived payload:

```bash
PYTHONPATH=cli/src python3 -m limen.cli vltima-kernel --primitive record
PYTHONPATH=cli/src python3 -m limen.cli vltima-kernel --layer lower
PYTHONPATH=cli/src python3 -m limen.cli vltima-kernel --organ education
PYTHONPATH=cli/src python3 -m limen.cli vltima-kernel --projection organ_kernel
```

## Lower Layer

| Primitive | Meaning |
|---|---|
| **Object** | Anything the institution can point at: artifact, account, document, work, rule, claim, file, or product. |
| **Subject** | A bearer of interest, consent, harm, benefit, identity, or standing. |
| **Agent** | A system or person capable of producing an event under a known authority boundary. |
| **Actor** | An agent acting in a role at a specific moment. |
| **System** | The bounded machine, office, institution, or process that receives events and maintains records. |
| **Event** | A dated assertion that something happened, was proposed, was decided, or changed state. |
| **Record** | A durable event or projection that can be re-read, audited, and cited. |
| **Covenant** | A binding rule or promise that governs future events and record interpretation. |

## Institutional Projection

Every organ projects the lower layer into the five existing primitives:

| Institutional primitive | Universal source |
|---|---|
| **Member** | Subject or object with recognized standing inside the system. |
| **Mandate** | Covenant-backed purpose, claim, role, matter, goal, or obligation. |
| **Standing** | Current record-derived posture: who may act, what is true enough to rely on, and what remains blocked. |
| **Standard** | The covenant, law, rubric, benchmark, or test that decides whether standing can change. |
| **Governance** | The rule-bound authority map for actors, agents, records, and external acts. |

## Value Projection

Money is not separate from the kernel. It is a value-bearing projection:

| Value primitive | Meaning |
|---|---|
| **Exchange** | A recordable transfer of value or promise of value. |
| **Entitlement** | Standing granted by a valid record, such as a MONETA license. |
| **Obligation** | A covenant-backed duty to pay, deliver, maintain, review, or refrain. |

## Operating Law

Events become records. Records establish standing. Standing authorizes action.
Action produces value. Value funds the institution.

TABVLARIVS is the record proof: ticket event -> board projection -> sealed
record -> task standing. MONETA is the value proof: buyer -> payment/order event
-> license record -> entitlement standing. The organs are institutional proofs:
member -> mandate -> standing -> standard -> governance.
