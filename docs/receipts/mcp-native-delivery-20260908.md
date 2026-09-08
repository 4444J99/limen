# Native MCP and refreshed skill metadata delivery

Owner: MCP-ESTATE-20260908, Limen #2577 stacked on #2567. Protected child
`run-124ca9ac749952e525f9bc649223cb3e`, session
`codex-campaign-native-child-20260908`, branch
`feat/mcp-healing-delivery-20260908`. Source base
`5a752d1a414b0439cb8db288b6590fbade55a198`.

The operator's completion criteria remain implementation, landing, exact
deployment, and fresh live acceptance. A source increment or a filed admission
gate does not close either campaign. Continue independent work while a specific
native launch or integration batch is not admitted.

## Native observation producers

The Claude Code producer uses the native stream control protocol to initialize a
fresh owned session, read effective MCP configuration and handshake versions,
and collect the native context accounting used by `/context`. It accepts only
`initialize`, `mcp_status`, and `get_context_usage`; no user/model turn, login,
reconnect, configuration change, permission response, or skill filter is sent.
The session uses `dontAsk` and does not persist a transcript. Actual process and
child cleanup reuse the existing custody owner. Plugin names remain namespaced
until an owner route map proves equivalence; suffix resemblance is insufficient.

The installed CLI version was read as `2.1.232 (Claude Code)`. The protocol and
status/context shape were checked against the upstream
[Python SDK control implementation](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/query.py)
and [status types](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/types.py).
These are source contract checks, not a passing live canary.

Codex collection now has a process-local OTLP receiver for the native skill
rendering histograms present in installed `0.153.4`. It accepts only a private
loopback capability and discards unrelated metrics, resource attributes, and
private text. A complete fresh `thread_context` sample must bind the expected
native skill count, client version, counts, constant histogram values, and one
bounded export batch. Missing, stale, mixed, or ambiguous data remains unmeasured.
No absence-of-warning inference produces a pass. The source contract is
[render observability at the installed release](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/ext/skills/src/render_observability.rs).

The receiver changes telemetry only in the fresh observer process. The ephemeral
endpoint is excluded from the stable MCP dependency binding so observing an
unchanged failure cannot manufacture another healing episode. The full native
configuration snapshot remains separately fingerprinted. No deployed file or
active process was changed.

## Plugin refresh correction

Compaction previously skipped every path already present in its custody ledger,
including a plugin refresh that replaced that exact path and a tighter native
budget. The new generation retains the prior receipt and preserves the current
artifact's instructions, skill identity, and other metadata. Re-compacting an
unchanged artifact retains its original source description for conditional
rollback. An interrupted generation cannot replay, even if the file changes.
An incomplete or raced target cannot return a successful apply result.

## Verification and live constraints

- Final native, estate, effective-configuration and skill batch: 128 tests passed,
  exit 0, including private loopback transport, metrics freshness/ambiguity,
  protocol refusals, dependency races, cleanup and refreshed artifact custody.
- Scoped integration from the base above: all 10 cheap gates passed; required
  heavy admission returned exit 75 for `swap-fraction,disk-throughput`.
- Fresh inventory with the source-owned policy retained 123 service identities
  and 156 registrations. These are inventory denominators, not live acceptance.
- Codex has 18 active registrations; 13 still lack audited quiet startup
  declarations. The native producer refuses to start the full configured estate
  until the owner declares those bounds. Current Claude runtime configuration
  files both exist with zero MCP registrations/plugins; the policy still requires
  its adapter. OpenCode has one active quiet HTTP route.

Current running Serena launchers resolve to cached revision
`701e7c843f46c6a649203a488cece1bf19f1df90` from `oraios/serena`, as witnessed by
the existing process executable and its `direct_url.json`. Existing processes
were preserved. The earlier protocol receipt did not bind a commit, so this
revision still requires its fresh pinned protocol/native canary.

The full seven-defect and every-registration acceptance remains outstanding.
No native runtime, authentication durability, UI startup, integration, merge,
or deployment pass is inferred from these source tests.
