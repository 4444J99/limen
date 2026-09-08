# MCP estate implementation receipt — 2026-09-08

Owner: Codex direct human session; canonical owner task `MCP-ESTATE-20260908`.
Companion source: `organvm/domus-genoma`, branch `feat/mcp-estate-policy-20260908`.
Limen branch: `feat/mcp-estate-contract-20260908`.

## Evidence and scope

The new command boundary replaces liveness-only success with a desired/observed inventory and
independent configuration, ownership, transport, protocol, authentication, capability, UI,
isolation, cleanup and client-route dimensions. Inventory is read-only. Missing required evidence
returns 77. Seven defect counts remain separate from service and registration denominators.
Domus owns a source registry and a partial Serena policy; no live configuration has been deployed.
The broad cache-deletion/configuration-reinstall healer has been removed.

A controlled fresh Serena process using the **candidate rendered** Codex registration completed
MCP 2025-11-25 initialization and tool discovery, including `open_dashboard`, in 2411 ms.
Server reported `1.7.1.dev0`; probe transport, protocol, authentication, expected capability discovery,
and root-process cleanup passed. The existing client session was not restarted. This proves a
protocol canary, not ChatGPT/Codex application-route readiness or dashboard-opening behavior.

## Blocker and next owner action

The broker accepted task intake with run `run-b889f63094064498fde826185f2fd864` and a committed
private-canonical projection receipt. Execution-state updates did not land. Its configured
`tabularius/board-projection` branch was absent; restoration at the current remote default head
allowed intake once, but the same branch disappeared again before the next transition.
The broker returned HTTP 503 with `GitHub projection reconciliation failed (404): Base does not exist`.
No task projection was edited locally and the task must not be represented as in_progress or done.

Owner: TABVLARIVS projection publisher, `web/worker/src/conduct/projection.js`.
Acceptance: a missing publication branch is safely created by the keeper from the current default
head; two consecutive broker-owned task mutations publish successfully without manual branch recreation.
Next command: `python3 -m pytest cli/tests/test_conduct_client.py -q`, followed by the worker projection
regression tests and a keeper-owned lifecycle canary after the publisher correction is deployed.
Do not repeat branch restoration or submit an unleased native client/agent fanout.

## Remaining acceptance work (implementation is not complete)

- Add authoritative installed-client/plugin manifests for every adapter; currently ambiguous plugin
  caches and desktop/hosted client coverage remain explicitly unmeasured.
- Bind canary receipts to independently observed current client/server versions and dependency
  fingerprints. A supplied fresh receipt alone is not an independently witnessed application canary.
- Run fresh ChatGPT/Codex and each distinct client canary after broker admission is available.
  Observe startup UI events, explicit dashboard opening, project isolation, shutdown, process count
  and memory; wire those observations into the existing bounded monitor.
- Complete ianva upstream-to-client capability routing checks, safe owner-declared functional smoke
  operations, and regression coverage for all required project/plugin/application rewrite cases.
- Review and harden private repair episode custody and concurrent rollback before enabling the
  effector on live configuration. Preserve active sessions and unknown/personal settings.

These items remain owned by `MCP-ESTATE-20260908`; they are not waived by unit-test success.

## Reproduction

```sh
python3 -m pytest cli/tests/test_mcp_server_boot.py cli/tests/test_mcp_estate_contract.py -q
python3 scripts/check-ideal-forms.py
python3 scripts/mcp-server-boot.py --inventory-only --policy /path/to/domus/.chezmoidata/config-ownership.json
bash scripts/verify-mcp-estate.sh --strict --policy /path/to/domus/.chezmoidata/config-ownership.json
```

The registry snapshot contains names and ownership/verification declarations only; credentials,
launch environments, endpoint payloads and private project paths are not copied into the policy.

Documentation used: [Serena dashboard](https://oraios.github.io/serena/02-usage/060_dashboard.html),
[Serena isolation](https://oraios.github.io/serena/02-usage/020_running.html),
[MCP stateless protocol](https://blog.modelcontextprotocol.io/posts/2026-07-28/).

## Verification receipts

- MCP-focused tests: 28 passed.
- Domus ownership/modifier/repair tests: 50 passed; commit hooks passed.
- Scoped cheap gates passed except a paused-beat batch failure; both implicated paused-sensing
  and paused-coherence predicates then passed when rerun directly.
- API suite: 48 passed.
- Full CLI suite: not passed. It showed failures before the deliberately bounded output ceiling
  stopped the run at 4000 bytes. The attempt to rerun that failed shard with a larger bounded
  output allowance was denied by machine-wide host admission (`vitals-shed`, exit 77).
  Failure identities and full-suite disposition remain acceptance work, not a green receipt.
- Inventory-only: 39 known service identities, 43 registrations, 42 incompletely measured
  registrations and 24 unmeasured surfaces; exit 77. Two conflicting registrations are the
  Codex GitHub standalone/plugin routes. These counts are an incomplete observed denominator,
  not a claim that every hosted integration has already been enumerated.

Next verification owner action after host admission recovers: rerun only `pytest-cli` through
`scripts/verify.py` admission with adequate bounded output, inspect the failed cases, and retain
these unchanged green shard receipts. No additional scheduler or background watcher was added.
