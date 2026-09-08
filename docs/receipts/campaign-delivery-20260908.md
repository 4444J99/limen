# MCP and recovery campaign delivery

Owner: the direct human request of 2026-09-08, MCP-ESTATE-20260908, recovery
PR #2573 and their existing implementation successors. Root execution is
`run-adef573d91cdf2124cf6299d9ad391a1`, protected native Codex session
`codex-campaign-delivery-resume-20260908`.

The operator explicitly rejected stopping after source fixes were pushed. An
intermediate PR, passing shard, deferred merge or filed blocker cannot close
either campaign. Continue all independent authorized work while a specific
gate holds its dependent lane. Preserve the full original completion criteria:
landed source, exact deployment receipts, fresh native MCP acceptance, semantic
source reconciliation, review dispositions, integration and archive restoration.

Repeated login prompts are an engineering defect to resolve through credential
ownership, durable native storage and refresh. Reuse must survive client
restart and plugin refresh. A generic `not_logged_in` observation does not
authorize another automatic login. Human consent remains human-controlled.
Domus #380 records the observed legacy LaunchDarkly issuer-binding failure and
the distinction between stored credentials and usable native refresh.

Broker-reserved independent children:

- Recovery reconciliation: `run-af751df86db9df5d77a21cca7fd00a49`, PR #2576.
- Native MCP implementation: `run-124ca9ac749952e525f9bc649223cb3e`, PR #2577.
- Publication recovery: `run-7fa59b5b6a26f51504ab085060466a25`, PR #2569.

The root owns dependency and managed-configuration delivery through each
repository's existing rail. Source checkouts are isolated. No prior peer
checkout, archive, stash, active process or credential was removed.

This is a continuing execution receipt, not a completion claim.

## Landed and deployed MCP configuration

Domus #380 merged into #379 at `4909af7e031236c95c31d95eb44e5f8667d5a387`;
the merge tree is byte-identical to the tested source. #379 landed on main at
`2f51073cbebe3ab3c9a4cfc40d20694d9e91296c`. Targeted policy, repair and
authentication support files were applied from that exact revision with private
preimages. Authentication status remains failing; no login was attempted.

An active-profile preview exposed unrelated model retuning by the normal owner
reconciler. Domus #381 adds the narrow `reconcile-mcp` path; 66 affected tests
and one added active-profile regression passed. It landed at
`5a3b88f0ddab140bc5a93531e38346ec71a5db2d`, and both runtime support files
were deployed from that revision. The active reconciliation changed exactly
`mcp_servers.serena.args` and `mcp_servers.serena.startup_timeout_sec`.

Live configuration assertions passed: exactly one enabled Serena route, launcher
revision `701e7c843f46c6a649203a488cece1bf19f1df90`, startup bound 60 seconds,
dashboard enabled and automatic opening disabled. The YAML owner repair returned
`verified`, episode `9925240d35e1160c716d3e51`, retaining private conditional
rollback custody. Config before/after digests are
`3dcc09f40f788bb256edf7f47ea17b1fd6d2b9b7b27cfc696641d9f57eb09852`
and `673cd36b788e3dd49aa1c3339583bec79558bf1fea0aa1ab2b4c1f5f6ecc1922`.
Native startup is still pending admission; configuration assertions do not
substitute for protocol, UI or process-cleanup evidence.

## Recovery dependency corrections

Engine #175 now has head `5cf2949e7597b85c285b2d39976a16a14f9d5fc7`.
It rejects unsupported SOP phases before output changes and brings an installed
audit candidate into conditional rollback custody immediately after linking.
An initial observation failure restores/removes the candidate; a concurrent
replacement is preserved with original preimages retained. Validation: 437
affected tests passed, two skipped; seven targeted cases passed; Ruff clean.
The source and updated exact-head review dispositions are pushed to the existing
owner. Required admitted integration and independent review remain separate.
