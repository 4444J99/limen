# Limen Board Progress and Source-Coverage Lens

`limen progress` is a partial terminal lens over two bounded surfaces:

1. normalized task-board rows from `tasks.yaml`; and
2. readiness contracts for named local source receipts.

It does not ingest the source-owned leaves behind prompt, GitHub-estate, lifecycle, mail, financial,
or contribution receipts. It must not be cited as proof that the whole work estate has been
enumerated. The JSON payload says `scope: partial` and retains the older
`limen.progress-universe.v1` schema identifier only so existing consumers remain compatible.

## Terminal use

```bash
# Board summary, source readiness, and the highest-priority 50 active board leaves
limen progress

# Select one board grouping and optional exact scope
limen progress --view origin
limen progress --view horizon --scope past
limen progress --view workstream --scope financial
limen progress --view source_lineage --scope prompt-lineage-7

# Print every matching active board leaf or return the bounded JSON projection
limen progress --all
limen progress --json-output
limen progress --report-file logs/board-progress-source-coverage.json
```

Macro bars show board statuses and metadata coverage. Micro bars show canonical lifecycle stage;
they are deliberately not percent-of-effort estimates. `--view`, `--scope`, and `--level` are
non-interactive filters, not a TUI. Terminal rows remain in JSON and macro counts but are omitted from
the active micro-debt list.

## Debt units

The lens keeps three non-interchangeable counts separate:

- `board_debt`: task-board rows not in `done` or `archived`;
- `coverage_debt`: required source contracts that are missing, stale, undated, unavailable, failed,
  capped, partial, or incomplete; and
- `verified_receipt_debt`: terminal board claims without explicit verified-receipt evidence.

Source readiness is stricter than timestamp freshness. When a source publishes semantic fields such
as `status`, `verdict`, `available`, `complete`, `exhaustive`, `capped`, or `truncated`, negative or
partial values remain coverage debt even when the timestamp is fresh. This command does not inspect
or guess the underlying source leaves.

## Board metadata and work-loan signals

Board producers can provide the following explicit fields or labels:

| Field | Meaning |
|---|---|
| `origin` / `origin:*` | `obligation`, `human_prompt`, `agent_recommendation`, or `system_debt` |
| `horizon` / `horizon:*` | `past`, `present`, or `future` |
| `workstream` | Purpose lane, distinct from the execution provider |
| `source_lineage` / `lineage:*` | Explicit source-owned cohort; absence remains `unknown` |
| `due_at` / `due:*` | Exact deadline when one exists |
| `repo` and `urls` | Durable owner surface and evidence |
| `predicate` | Executable definition of done |
| `receipt_target` | Durable terminal custody target |
| `value_case` | Forecast reason for spending capacity |
| `receipt_verified: true` | Explicit owner-produced verification evidence; never inferred by this lens |

The `WORK LOANS` bar reports metadata underwriting, not funding or approval. It requires an explicit
origin, horizon, value case, owner repo, run cost, predicate, and receipt target. Requested
`budget_cost` is exposed as `debit_requested_runs`; it is not actual token, money, time, host, or
provider spend. `credit_forecast` is text, not earned value. A terminal status with contract strings
is a board credit claim; only explicit receipt-verification evidence reduces
`verified_receipt_debt`.

`WorkLoanV1` provides one shared readiness contract across Python, API, JSON Schema, and Worker
surfaces. Historical rows and stored packets remain readable, but new rows, active task transitions,
dispatch, packet reservation, and lease claim now fail closed when underwriting is absent. The stable
denial is `task-not-underwritten:<comma-separated-fields>` in canonical field order. Intake never
invents a value case from title prose.

One exact compatibility packet is not a work loan: the broker-authenticated TABVLARIVS projection
shape with an exclusive task claim and a zero-run spend envelope. It mutates only the task-board
projection and therefore consumes no executor capacity. Any positive spend, different adapter,
different authority, or non-task intent loses that exemption and requires a positive `WorkLoanV1`.
The projected task row itself still requires underwriting before later claim or dispatch.

The owner QA endpoint may set `receipt_verified: true` only on a `done` transition carrying a zero
predicate exit code, the task's exact declared receipt target, a positive receipt-verification
attestation, and a 64-hex verification-context digest. Merely changing lifecycle status to `done`
does not create verified progress credit.

Raw discoveries remain in their source-owned feed or staging ledger until a producer can pass the
ask gate and WorkLoan predicate. The board projection rejects a new ununderwritten row without
mutating the input projection. For legacy repair, `--view source_lineage` and each group's
`underwriting_denial_counts` expose cohort-sized gaps without rewriting `tasks.yaml`. An absent
lineage remains `unknown` and must not be rendered as zero debt.

In `logs/handoff.json`, `ostensible_next` is the raw highest-priority open row.
`dispatchable_next`—and the compatibility alias `next_action`—is the highest-priority row that also
clears underwriting, dependencies, budget, provider health, human gates, and execution requirements.
`dispatch_admission.reason_counts` explains every gated open row.

## Content-addressed inputs

Each JSON snapshot includes:

- a SHA-256 of the normalized task board;
- both raw-byte and canonical parsed-JSON SHA-256 values for each readable source receipt; and
- one contract hash over the normalized board, canonical source hashes (or raw bytes for invalid
  input), read states, the surface schema, and `scope: partial`.

The generation timestamp is intentionally outside the content hash because freshness changes with
evaluation time. JSON whitespace and object-key order do not change the contract hash. Equal input
hashes prove equal semantic input content, not equal freshness verdicts.

## Work intentionally left to owner packets

Dynamic source discovery, exhaustive GitHub-estate enumeration, prompt-atom lineage, actual
debit/credit reconciliation, interactive terminal zoom, and historical priority selection are
separate products. Their absence remains visible coverage debt; this lens does not simulate them.
