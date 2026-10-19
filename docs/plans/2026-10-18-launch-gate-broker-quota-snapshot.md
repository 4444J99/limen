# Launch gate: honour the last-good broker claim snapshot while the write quota is spent

Issue: #3119
PR: (pending)

## Context

Every agent CLI on this host (codex, claude, opencode, gemini) launches through
`domus-agent-runtime`, whose `launch_admission()` asks the installed limen runtime's
`scripts/runtime-pool.py observe --json` for one shared disk-growth verdict and refuses to launch
unless it answers `allowed=true`. That verdict needs the broker's storage-claim census
(`storage_claim_census.broker_storage_claims()` → conduct `GET capabilities`), and the broker is
a Cloudflare Worker + Durable Object on the free tier: 100,000 rows written per day, reset 00:00
UTC, and once exceeded its reads fail too. When it answers
`500 Exceeded allowed rows written in Durable Objects free tier`, `conduct.client` raises
`BrokerQuotaExhausted`, `selected_claims()` raises `PoolUnavailable("broker_quota_exhausted")`
(#3103), and **every agent launch on the machine is refused until the daily reset**. That has
happened three times in two months. The write amplifier itself is owner issue #2054 and is being
fixed in #3117; this plan does not touch it.

The operator's question that prompted this: *"why does cloudflare have any business with
launching local agents"*. The answer this plan implements: it should not be able to block them.

## Resolved design decisions

- **D1 — Remember the last successful read; use it only while the write quota is spent.** After
  every successful `broker_storage_claims()` read, persist the claims plus this host's
  `observed_at` and the broker's `observed_at` to a mode-0600 JSON snapshot beside the pool file
  (`RuntimePool.root / broker-claims-snapshot.json`; same private root, same lock — no new root).
  Atomic write (temp file + `os.replace`). Best effort: a failed snapshot write never turns a
  successful live read into a denial.
- **D2 — Why memory is exact here and nowhere else.** While the broker reports a spent WRITE quota,
  nothing can register, heartbeat, release or expire a claim on it, so the set of broker claims
  cannot change; the snapshot taken at the last successful read is the ledger for the whole outage.
  Honouring each claim to its own `rollback_until` can only over-reserve (an early release cannot
  happen while writes are refused; an expired claim is dropped exactly as the broker's census drops
  it). Therefore **no max-age cutoff** beyond the claims' own `rollback_until`. Every other broker
  failure (network, auth, incomplete / stale / duplicate census, conflicting claims) still fails
  closed with its existing reason, byte-for-byte.
- **D3 — The verdict says which ledger it stands on.** `selected_claims()` returns a
  `ClaimSelection(claims, broker_ledger)`; the pool copies the marker onto every decision:
  `{"broker_ledger": "live"}` after a broker read, or
  `{"broker_ledger": "frozen", "frozen_at": <snapshot observed_at>, "reason": "broker_quota_exhausted"}`
  during an outage. `scripts/runtime-pool.py --json` passes it through unchanged so the launcher can
  print it. `BrokerQuotaExhausted` with **no** snapshot keeps today's behaviour:
  `denial_reasons == ["broker_quota_exhausted"]`.
- **D4 — A damaged snapshot is an absent snapshot.** Read with `O_NOFOLLOW`, regular file, owned
  by this uid, mode `& 0o077 == 0`, one link, bounded size, schema match, offset-aware timestamps,
  validating claims, no duplicate ids. Anything else → `None` → fail closed as today.
- **D5 — The launcher change is a follow-up in the dotfiles repo, not this PR.** domus-genoma is
  not touched here; the exact two-line change is in the PR body and filed as an issue on
  `4444J99/domus-genoma-private`.

## Steps

1. `cli/src/limen/storage_claim_census.py`: `ClaimSnapshot`, `write_claim_snapshot`,
   `read_claim_snapshot`; `broker_storage_claims(snapshot_path=None)` writes after a successful read.
2. `cli/src/limen/runtime_pool.py`: `ClaimSelection`, `_broker_claims` (the fallback and its
   reasoning), `selected_claims(snapshot_path, now=)`, `RuntimePool.snapshot_path`, marker on
   every decision from `observe`/`reserve`.
3. `scripts/runtime-pool.py`: pass-through documented.
4. Tests in `cli/tests/test_runtime_pool.py` and `cli/tests/test_storage_claim_census.py`, each new
   test A/B'd against the parent commit (must fail there).
5. `bash scripts/verify-scoped.sh` bare; PR; `scripts/merge-policy.sh <PR#>`; merge only on exit 0.
6. Follow-up issue on `4444J99/domus-genoma-private` for the launcher message.

## Premortem

- **What most plausibly makes this wrong or unwelcome?** A claim registered between the last
  successful read and the quota wall is invisible to the snapshot, so the pool could under-reserve
  by that one claim's bytes for the outage. Bounded by the read cadence (every launch reads) and by
  the pool still measuring free disk live. The alternative — refusing every launch for the rest of
  the UTC day — is strictly worse, and the operator has said so.
- A snapshot that lingers after the quota resets is never consulted: the live read succeeds and
  overwrites it.

## Verification

- `bash scripts/verify-scoped.sh` (bare; read its own exit code)
- New tests fail on the parent commit and pass on the branch.
