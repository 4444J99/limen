# Shared agent OS deployment acceptance

This report supersedes earlier deployment checkpoints. Historical failed receipts remain preserved; their outcomes are not rewritten by later repairs.

## Accepted implementation and deployment

Limen #2849, #2851, #2852, #2853 and #2856 implement the shared disk-aware pool, complete authenticated workload-claim census, corpus analysis, healing health routing and bounded native heartbeat. Domus #420–#423 implement shared-pool consumers, canonical Claude reconciliation, native history preservation, responsible-host routing and bounded installer startup. Limen PR #2856 merged tested head `64d0fb98ed356ca8a1c555f02b55a0c5eea1f04d` as `d1e15e2506f97147a20d7aaa3387bb2aa67473ff`; the merge adds only unrelated estate identity data. The immutable runtime is installed and activated at that exact accepted revision. Domus #423 accepted revision is `124bc2fd4d61a141e388baa8c7c5450b564ffcdd`.

The authenticated Worker deployment remains source `6100dac2c9630f3c6472f6fbf50a5bf3d9ec8f47`, version `d5f969cf-1780-4e89-bfdc-0b02ea1f578e`. Its complete census/readback and actual reserve/release were verified. No local graph was invented to substitute for missing broker evidence.

The pool admits managed growth atomically across providers. Per-provider consumption remains visible without vendor allocations. Shared growth is filesystem free bytes less the Limen resource envelope and outstanding growth reservations, counted once. Existing sessions remain protected; containment, stale/incomplete telemetry, owner identity and verified-expiry rules remain enforced. Ordinary application writes are monitored observationally.

## Verification and historical CI repair

The exact implementation head passed 8,581 CLI tests (58 existing skips; eight subtests), 52 API tests, 19 scoped cheap gates, 154 focused native/heartbeat/storage regressions and all 32 registered credential-wall atoms. Hosted CI independently passed Python, Worker, dashboard web build, witness contract, both dependency audits and Semgrep. Relevant immutable job links are retained in the acceptance JSON.

The PR gate subsequently exposed two test examples bound to historical commit objects unavailable in a fresh clone. The followup repairs the historical test fixtures and records deployment evidence: real temporary Git commits now prove bookkeeping cannot settle a stream and implementation code can. Eight implicated anchor/classification cases pass; the production settlement guard and registry acceptance remain unchanged. This source-export verification does not claim Git integration checks ran on a Git-free archive. An attempted local dashboard replay was denied `heavy-lease-held`; the successful exact-head hosted dashboard build supplies that shard's evidence.

## Shared capacity and reserve truth

The independent complete census at `2026-10-13T02:26:35.425141Z` scanned 112,663 files with no census errors, failures, warnings or migration diagnostics. Consumption was 21,851,558,021 bytes. Filesystem free space was 26,888,695,808 bytes; one live reservation held 67,108,864 bytes, and the broker reported zero active storage claims. Available shared growth was **26,821,586,944 bytes (24.98 GiB)**. Observed utilization was **44.8945%**, strictly below 70%, with zero target deficit.

The unchanged resource-envelope calculation reported zero current reserve components in that observation. Live swap use (1,628.31 MiB) was below available RAM (about 3.58 GiB), so the existing `max(0, swap_used - ram_available)` projection was zero. The updater, APFS churn and telemetry-error inputs had no environment overrides and retained their registered zero-default meanings. These are disclosed inputs, not newly relaxed thresholds, guaranteed constant capacity, or attributed physical recovery. Earlier observations with about 10.12 GB reserve remain valid historical measurements of different pressure. The full private census is retained with SHA-256 `4d388529a61f98e4ca73b4b121984062b39aa09b366b1bd05537ad5d8393d084`.

## Controlled and scheduled execution

Normal reviewed activation passed at `2026-10-13T02:24:48Z`: whole tick 33,324 ms, probe 33,195 ms, exit zero, zero surviving descendants and zero consecutive failures. Runtime digest is `99a4704b077c4a8fc1f007f6ef1a6a552fd7efdc0990ce7b57a904a1064e578c`; contract digest is `0727b36d6fdaabafb7cf66ba146db6be6b459bbc2a1bb9a51c165b2537145353`. The controlled receipt SHA-256 is `deea8a7d0d1a0e6d9f04899dd923ec1fb90df9e3e8888a71899b72480235363a`. Launchd baseline is one run, successful exit, and no surviving process. The actual naturally due maintenance acceptance is appended below after observation; a controlled activation is never substituted for it.

The original episode `af529e574f2b4f2e9c95a14837b3fdd4` remains closed after one worker attempt. The observer is record-only and does not invent another maintenance worker. Older `482e97d...` RSS-census failures, their disabled state and the timed-out npm-cache verification remain preserved. No success or physical recovery is attributed to that npm attempt.

## Configuration, history, visual capability and corpus

Claude canonical source reconciles templates, ownership and hooks without overwriting application-owned state. Reviewed files-only apply, empty diff and a second no-change apply were proved. Fresh source/render parity at `2026-10-13T01:58:29.708681Z` retained SHA-256 `4aa08ae41e0b4f5804ffbc2b9bf0c4a2787aa8ed46dbeabbf68bdbfc21a43c0e` for the instruction file and `1f8c7b3ec350c61ff0f30f8ea6bc7e2eb4ea99b68c833e4e0919abf20bfe09f3` for the owned hook.

All five native history readers, attribution and restoration predicates passed. Fresh guarded interactive launches against d1e15e25 at `2026-10-13T02:30:44.855391Z` returned OpenCode 2.0.25 and Codex 0.162.1, both exit zero with no quota or attribution warnings; launch receipt SHA-256 is `531bef2ecc42ca6a2f29e5d7ebe6553d51495d2a9758c1562ab8846d5c33c1b7`. Native conversion reduced apparent accounting by 5,725,879,702 bytes and allocated carrier bytes by 5,720,875,008, but measured filesystem free-space delta was negative; no physical recovery is attributed to conversion. Verified regenerable Homebrew cleanup reduced allocated cache bytes by 2,731,327,488; the observed 3,723,386,880-byte free-space increase includes concurrent effects. Native history, active uv caches, custody partials and foreign worktrees were preserved. New validation dependencies are transient build growth and confer no historical recovery credit.

Supported DomusAgentHost routing and a real native TextEdit visual smoke check passed; actual visual evidence is linked in `native-visual-20261012.json`. Codex-target capture remains denied by the external platform safeguard, so target-specific acceptance is false. No blanket policy bypass is used.

The six-month ledger `operating-system-2026-04-12-2026-10-13.{json,md}` inventories all 15 providers and 2,366,993 record observations. The boundary is April 12 through October 13 midnight America/New_York, exclusive. Complete Codex rescan has zero deadline gaps. April/May zero observed records is not absence of failures. Undated/non-message, opaque and server-export boundaries remain explicit; deduplication preserves correction lineage and redaction. 264 of 265 remote candidates link to exact identities; historical Limen PR #10 returned HTTP 404 and is not landing proof. Original occurrences keep their own live dispositions.

## Retention and external gates

Dirty/divergent primary checkouts and the recovery task's retained worktree remain preserved. The exact source export, source manifest, attempted build receipt and test fixtures are retained under private custody staging; no new source worktree bypassed storage admission. Raw evidence remains private; this report carries only redacted identities and measurements.

Issue #2848 remains the human-owned acceptance registry. The existing read-only 24-hour watch remains ACTIVE and must anchor at the first verified natural maintenance pass; no elapsed-day completion is claimed early. Extending that existing watch requires its supported app automation updater, currently unavailable to this terminal harness. No raw automation configuration edits or duplicate scheduler are used. Codex-target native capture remains externally policy-blocked. Provider billing limits remain provider-specific.

## Background-item ownership correction

The natural background-items census exposed one undeclared service, `sh.brew.lighttpd`. Its installed plist resolves to the actual Homebrew `lighttpd` binary (1.4.85_1). The existing third-party registry now declares this specific service without exempting unrelated `sh.brew` labels. The unchanged live census passes with seven estate, nine third-party, two tombstones and zero undeclared items; all 14 background-census regressions pass. Launch behavior, policy safeguards and misbehavior checks remain unchanged. Because the registry is immutable runtime data, the successor accepted merge must be installed and activated normally; earlier d1e execution proof remains specific to d1e and is not promoted to that successor. Final successor deployment receipts are appended to the owning PR.

Actual natural maintenance for d1e15e25 passed at `2026-10-13T02:40:27Z`: whole tick 22,878 ms, probe 22,792 ms, exit zero, zero surviving descendants and failures. Receipt SHA-256 `eea7e0e045e87af01abd1c0ec6d06770e4631941bb05ab108c28fd0e7e047d75`. The observation began 939.232 seconds after the controlled maintenance attempt, beyond the 900-second cadence. This is exact d1e evidence; the registry successor still requires its own activation and natural acceptance.
