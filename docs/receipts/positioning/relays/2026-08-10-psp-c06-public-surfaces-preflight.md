# PSP-C06 public-surfaces preflight relay

Status: **PREPARED/PREFLIGHT**. This relay preserves a reversible downstream checkpoint. It does
not close PSP-P07, any P07 leaf, or a formal dependency.

## Exact inputs

- PSP-C00/P00 is closed through merged [PR #2300](https://github.com/organvm/limen/pull/2300).
  The former non-Codex/Agy identity condition is superseded; it is not a C06 blocker.
- C04 preflight: [PR #2313](https://github.com/organvm/limen/pull/2313), exact head
  `23712398c6586e005c303eff632604985cd0a25c`.
- P06 preflight: [portfolio PR #220](https://github.com/organvm-vii-kerygma/portfolio/pull/220),
  exact head `9bcc4606b68da83dc0878b060989d35c3b649d7f`.
- C03 [PR #2312](https://github.com/organvm/limen/pull/2312) is currently staged at
  `c7c932205faa405e291f8030235a73cedeaa219e`. Its W01-W06 acceptance tree is
  `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`; W06 is bound to the
  [marked receipt](https://github.com/organvm/limen/issues/2187#issuecomment-5271254820) with
  SHA-256 `260081dfbffc75d55824c0e6ed7d7718a7e397763afb689c94d2230963d79617`.
  W07/#2188 is the sole unresolved C03 dependency and requires five genuine independent
  target-like reader records. The tracked protocol/template at the current C03 head is intake
  machinery, not reader evidence.
- Canonical portfolio: `organvm-vii-kerygma/portfolio` (repository id `1155412125`), current
  public baseline `https://organvm-vii-kerygma.github.io/portfolio/` at main
  `85bfaa84287e4a3b90b49187caa4313c4edda1aa`.

## Downstream checkpoint

Portfolio [PR #221](https://github.com/organvm-vii-kerygma/portfolio/pull/221), branch
`codex/psp-c06-public-surfaces-preflight`, exact head
`6cb7f291ef758d26d136620398c6e9c09f74d0ea`, stages only:

- one W01–W09 source and release/rollback inventory;
- a disabled-by-default, allowlist-only analytics schema that differentiates client and
  recruiter/executive doors while rejecting personal, free-text, content, private-identifier, and
  cross-site fields;
- a machine-checked claim/disclosure contract that renders only verified or reviewed-derived
  claims, withholds private or unverified material, and exposes only the client and
  recruiter/executive public doors;
- canonical URL/domain truth, declared WCAG 2.2 AA and performance acceptance budgets, and a
  synthetic rollback dry-run contract that cannot contact deployment, DNS, routing, or analytics
  services;
- selection-gated visual and analytics implementation; and
- a public-safe link-health finding and a source-owned repair path.

The exact three review PNGs are now durable in the portfolio branch at:

- `docs/positioning/visual-directions/psp-c06/option-1-evidence-ledger.png`
- `docs/positioning/visual-directions/psp-c06/option-2-systems-field-guide.png`
- `docs/positioning/visual-directions/psp-c06/option-3-decision-brief.png`

Their public-safe manifest pins the source capture, direction names, SHA-256 digests,
`UNSELECTED` status, and the no-build boundary at
`docs/positioning/visual-directions/psp-c06/manifest.json`. The portfolio predicate verifies all
three digests before passing.

The portfolio predicate passed on that exact checkpoint:

```text
node scripts/validate-psp-p07-preflight.mjs
node --test scripts/__tests__/psp-p07-preflight.test.mjs
npm exec --package=@biomejs/biome@2.5.4 -- biome check src/data/psp-p07-public-surface-contract.json docs/positioning/PSP-C06-P07-PUBLIC-SURFACES-PREFLIGHT.md scripts/validate-psp-p07-preflight.mjs scripts/__tests__/psp-p07-preflight.test.mjs
```

All three passed before the checkpoint was committed. They validate the containment and schema,
not public-surface completion.

The refreshed contract distinguishes the accepted W01-W06 head from the current C03 preflight
head, pins the W06 receipt, and fails any inference that the W07 intake package satisfies the
five-reader gate. C05 remains a separate child of C03 and is not introduced as a C06 dependency.
It also makes post-selection prerequisites explicit: an operator selection receipt, C03 W07's
five-reader receipt, P05 W02 claim reconciliation, P06 W07 visual/comprehension QA, and
HG-PUBLIC-IDENTITY are required before any implementation effect. Selection alone cannot close a
P07 leaf or phase.

## Live finding and boundary

`python3 scripts/link-health.py --verify` observed 11 dead legacy
`organvm.github.io/portfolio` links across the tracked profile, portfolio, and resume surfaces.
The canonical `organvm-vii-kerygma.github.io/portfolio` counterparts resolve. The finding remains
failed until an owner-approved source repair and a new link-health receipt prove otherwise.

Exactly three grounded visual directions were prepared from captured current public surfaces and
the P06 design brief. Human selection, rejected-direction rationale, identity/proof fit,
accessibility/performance risk, and rollback must be recorded before any visual implementation,
route, server, analytics instrumentation, deployment, DNS, or public-surface mutation.

No private evidence, external send, DNS/TLS change, deployment, selection simulation, or claim
promotion occurred. Rollback is closing the portfolio draft and this relay draft and retaining the
current public release.
