# Engagement Register

Every paid engagement, logged on day one. The standard is
[`docs/engagement-intake-standard.md`](../docs/engagement-intake-standard.md); the predicate is
`scripts/engagement-guard.py`.

**A row is added before the first commit, not after the first dispute.**

```bash
scripts/engagement-guard.py --all      # status of every engagement below
```

| Engagement | Counterparty | Started | Instrument | Guard | Notes |
|---|---|---|---|---|---|
| [`victoroff`](victoroff.yaml) | pre-revenue LLC | 2026‑07‑21 | not mutually executed | **BLOCKED** (6 FAIL) | Retroactive. This is the guard's regression test — it must never pass. |
| [`examples/healthy`](examples/healthy.yaml) | — | — | — | CLEAR | Template. Copy this to start a new engagement. |

---

## Adding an engagement

```bash
cp engagements/examples/healthy.yaml engagements/<name>.yaml
$EDITOR engagements/<name>.yaml
scripts/engagement-guard.py --config engagements/<name>.yaml
```

Then add a row above. Fill the config in **honestly** — a config written to pass the guard is
worse than no config, because it converts a real warning into a false reassurance.

## Reading the Guard column

| Verdict | Meaning |
|---|---|
| **CLEAR** | Every condition holds. Safe to work. |
| **PROCEED WITH CAUTION** | Warnings only — usually counsel asymmetry, or an unexecuted transfer request. Readable risk. |
| **BLOCKED** | One or more conditions failed. **Stop performing new billable work** until cleared; every additional unpaid day worsens the position. |

## Privacy

These configs are committed to a **public** repository. They record the *shape* of an engagement
— dates, whether an instrument was countersigned, whether payment landed — and must contain **no
message content, no personal detail, and no third-party names**. Counterparties are described by
character ("pre-revenue LLC"), not identity where identity is not already public.

Confidential engagement records belong in a private repository. `victoroff.yaml` is the worked
example of the line: it records that promises were made only in conversation, and quotes the
three fragments necessary to make the failure legible, but carries none of the surrounding
record.
