# Ethics & Boundary Log — [Client Name]
*Append-only record of every boundary pass/fail check. Continuous per-workflow output.*
*No artifact leaves the HR organ without a pass record and practitioner direction.*

| # | Date | Workflow | Artifact | Check | Result | Detail |
|---|---|---|---|---|---|---|
| 1 | [date] | [W2/W3/W4/W5/W6/W7] | [filename] | UPL boundary | PASS | No legal advice detected |
| 1 | [date] | [W2/W3/W4/W5/W6/W7] | [filename] | Scope boundary | PASS | Within engagement scope |
| 1 | [date] | [W2/W3/W4/W5/W6/W7] | [filename] | Privacy boundary | PASS | No PII exposed |
| 1 | [date] | [W2/W3/W4/W5/W6/W7] | [filename] | Styx consent | PASS | Opt-in confirmed or N/A |
| 2 | ... | ... | ... | ... | ... | ... |

## Boundary Rules (enforced by sentinel)

- **UPL:** No employment counsel, no legal advice, no personnel-action recommendation
- **Scope:** No intake scope creep without practitioner approval
- **Privacy:** No PII in artifacts without explicit consent
- **Styx:** Behavioral tooling is opt-in only; no covert monitoring
- **Practitioner gate:** Every output is a draft; practitioner reviews, corrects, and delivers
