# Chat/GitHub implementation continuation

Owner: PR #2679, direct human request to proceed through engineering, verification,
governed merge and deployment. This revision preserves the original plan rather
than overwriting it. Workflow-scope authorization was completed by the operator.
Current architecture and activation contract:
`docs/architecture/chat-github-execution.md` (rehomed from the candidate's loose
docs root after the curated-surface gate rejected that placement).

Correction carried forward: a published draft is preservation, not a stopping
point. Finish reversible engineering and source/deployment work without another
operator confirmation. Only actual account/consent or runtime safety gates pause
their own lane; they do not defer unrelated source work.

## Execution batch

- Persist the exact admission packet before canonical submit; recover ambiguous
  admission by the same canonical work identity.
- Preserve one-shot dispatch, bind native provider attempt identity, and reconcile
  interruption, expired/fenced leases, workflow failures and queued merges within
  the original deadline. Never re-submit a merge from reconciliation.
- Bind trusted verification attestations to immutable GitHub artifact metadata,
  exact controller/head/profile/run/attempt identities and actual verifier steps.
- Fence base history and the immutable test oracle; keep source and credentials
  outside public output. The initial canary profile remains deliberately narrow.
- Run focused fault regressions, then one implicated scoped verification batch.
- Update PR #2679 with exact evidence, land through the governed PR rail if green,
  deploy the landed main SHA, and independently read back deployment identity.

## Independent acceptance

OAuth issuer/native client linking and dedicated execution credentials still
belong to credential wall #320. No tenant signup, consent, secret widening or
paid upgrade is inferred from GitHub workflow-scope authorization. Desktop and
scheduled Chat canaries require their own actual tool/run receipts. A deployed
disabled adapter is not an activated connection and never counts as either canary.

## Finite runway

This changed-input corrective batch began 2026-09-17 at approximately 15:56 UTC.
Limit: 30 minutes, including at most 10 minutes of verification, within the
120-minute cumulative outcome limit. Prior candidate remains in PR #2679.
No model-provider fanout or additional autonomous implementation child is used.
Retain this checkout until its final exact source and owner receipts are durable.
