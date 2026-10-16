# Gateway activation correction

Supersedes step 2's targeted administrative API handoff in the original plan. A single normal management login with the vendor bootstrap credential returned HTTP 401 before any source or settings mutation. No password, authorization rule or account was changed; there is no available management session token.

The user authorized local gateway activation. Use the existing launchd-managed IANVA gateway restart after changing its owning per-server source override. This is a restart of the authorized gateway service, not a restart of human agent applications or their sessions. Before restart, the exact gateway process tree contains only its Limen and Playwright MCP children, with no browser descendants. Preserve both configured upstreams, credentials, preimages and the previous source environment. The restart may briefly reconnect gateway clients; subsequent native Codex probes establish reuse.

All other original acceptance requirements remain: managed non-editable packages constrained by the merged lock; actual upstream version 1.30.0; real protocol/tools/read proof; sequential fresh terminal and desktop startup verification; published sanitized receipt; no protected primary changes or retirement.
