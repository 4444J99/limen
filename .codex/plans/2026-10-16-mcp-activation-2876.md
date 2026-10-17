# Activate the merged MCP SDK in the local gateway

Owner: gitvs / issue #2876. Source: merged Limen commit 579ef53a56fb39624aadd4c420a86b75ce327af3. User authorizes local gateway activation and startup verification.

1. Build/install the merged first-party CLI and MCP packages as a non-editable managed UV tool, constrained by the merged MCP lock. This uses the existing UV tool lifecycle and produces a stable launcher independent of the dirty shared primary checkout. Keep the old environment for rollback.
2. Preserve private preimages of the IANVA upstream definition and materialized settings. Change only the Limen upstream through IANVA's existing per-server override, preserving other entries and credentials. Use the gateway's targeted Limen reconnect; do not restart the gateway, other upstreams or agent sessions.
3. Verify the new running child belongs to the gateway and launches the installed MCP 1.30.0 environment. Verify initialization, tools/list and a harmless read through the gateway. Compare installed dependencies with the merged lock.
4. Sequentially start fresh terminal and bundled desktop Codex clients, refetch plugins, reload MCP and verify all four originally affected providers. Confirm that the original warning set remains absent. Keep private account readbacks outside Git.
5. Publish a sanitized activation receipt and resolve #2876 only after active-process and client evidence passes. Retain the source checkout, old environment and configuration preimages; no custody retirement is part of this activation.
