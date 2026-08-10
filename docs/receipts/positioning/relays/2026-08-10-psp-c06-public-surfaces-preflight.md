# PSP-C06 public-surfaces preflight relay

Status: **PREPARED/PREFLIGHT**. This relay preserves a reversible downstream checkpoint. It does
not close PSP-P07, any P07 leaf, or a formal dependency.

## Exact inputs

- PSP-C00/P00 is closed through merged [PR #2300](https://github.com/organvm/limen/pull/2300).
  The former non-Codex/Agy identity condition is superseded; it is not a C06 blocker.
- C04 preflight: [PR #2313](https://github.com/organvm/limen/pull/2313), exact head
  `e9c2db2360acd5fd57a48d063e64990dc8f3a768`.
- P06 preflight: [portfolio PR #220](https://github.com/organvm-vii-kerygma/portfolio/pull/220),
  exact head `fa86b67a7283c15ab801302ffac655c30898b6a1`.
- Canonical portfolio: `organvm-vii-kerygma/portfolio` (repository id `1155412125`), current
  public baseline `https://organvm-vii-kerygma.github.io/portfolio/` at main
  `85bfaa84287e4a3b90b49187caa4313c4edda1aa`.

## Downstream checkpoint

Portfolio [PR #221](https://github.com/organvm-vii-kerygma/portfolio/pull/221), branch
`codex/psp-c06-public-surfaces-preflight`, exact head
`5cd79b4c0d7863842f40b3d46cdf99f1c6f99638`, stages only:

- one W01–W09 source and release/rollback inventory;
- a disabled-by-default, allowlist-only analytics schema that differentiates client and
  recruiter/executive doors while rejecting personal, free-text, content, private-identifier, and
  cross-site fields;
- selection-gated visual and analytics implementation; and
- a public-safe link-health finding and a source-owned repair path.

The portfolio predicate passed on that exact checkpoint:

```text
node scripts/validate-psp-p07-preflight.mjs
node --test scripts/__tests__/psp-p07-preflight.test.mjs
npm exec --package=@biomejs/biome@2.5.4 -- biome check src/data/psp-p07-public-surface-contract.json docs/positioning/PSP-C06-P07-PUBLIC-SURFACES-PREFLIGHT.md scripts/validate-psp-p07-preflight.mjs scripts/__tests__/psp-p07-preflight.test.mjs
```

All three passed before the checkpoint was committed. They validate the containment and schema,
not public-surface completion.

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
