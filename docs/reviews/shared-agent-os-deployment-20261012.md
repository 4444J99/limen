# Shared agent OS deployment acceptance

This receipt supersedes the early implementation checkpoint. Final followup installation
and naturally scheduled firing receipts are published on the PR that carries this file.

| Defect | Owner | Regression guard | Accepted live evidence |
|---|---|---|---|
| Fixed vendor slices and double accounting | Limen resource pool; Domus consumers | `test_runtime_pool.py`, Domus runtime accounting | #2849 and #420 merged/deployed; live reserve/readback/release leaves zero reservations |
| Missing workload claims | Limen authenticated broker | Complete/fresh census and missing-graph tests | Deployed Worker `6100dac2c9630f3c6472f6fbf50a5bf3d9ec8f47`, deployment `d5f969cf-1780-4e89-bfdc-0b02ea1f578e`; complete census, zero active runs and no invented local graph |
| Claude source/render recursion | Domus canonical chezmoi source | Claude source ownership, hook import exclusion | Reviewed source reconciled; files-only apply, empty diff and second no-change apply; runtime alias retained |
| Native history preservation and process attribution | Domus #421 and native-baseline followup | Native readers, truncation rejection, ownership and installer tests | Five native readers verified; ordinary guarded OpenCode 2.0.25 and Codex 0.162.1 exit successfully without attribution warnings |
| False host health failures | Limen health observer; Domus host route | Supported routing and immutable receipt fallback | Supported host check succeeds; real TextEdit capture retained in `native-visual-20261012.json`; target Codex restriction is external platform policy |
| Missing recurring maintenance observation | Existing Limen heartbeat; Domus activation | Full-day cadence simulation, all probes retained, source drift, incomplete census, worker rejection, contention, exit-78 kill switch | Source-bound record-only observer added at 900 seconds; final accepted install and natural firing must be linked on this PR |
| Incomplete six-month review | Limen corpus adapters | Native boundaries, compressed scope, deduplication, correction lineage, redaction and exact receipt linkage | 2,366,993 record observations; all fifteen providers inventoried; complete Codex rescan with zero deadline gaps; 264 of 265 remote candidates linked to exact identities |

The evidence window ends at October 13 midnight America/New_York, exclusive. April and
May contain no observed native records. The ledger preserves undated/non-message
artifacts and opaque/server-side provider boundaries explicitly. The unavailable
`4444J99/limen` PR #10 returned HTTP 404; it is not a landing receipt. Historical failure
occurrences retain their own dispositions and are not blanket-closed by these repairs.

## Measured shared headroom

At 2026-10-12T23:19:16.612101Z the complete census measured 22,084,754,632 consumption
bytes, 27,859,349,504 filesystem free bytes, 6,232,288,133 reserve bytes and zero growth
reservations. Available shared growth was **21,627,061,371 bytes (20.14 GiB)**;
utilization was 50.5235%, below the requested 70% target. The source-bound observation
at 23:27:53.910233Z remained healthy with 20,680,600,126 available growth bytes.
These are observations of a changing filesystem, not hard enforcement of ordinary
application writes or a promise of constant capacity.

The original maintenance episode closed after one worker attempt; the next observation
retained the same closed episode and attempt count with no additional worker. The
native compatibility and restoration predicates passed. Provider billing limits remain
provider-specific.

## Recovery attribution and verification limits

Native conversion reduced apparent accounting by 5,725,879,702 bytes and allocated
carrier bytes by 5,720,875,008. Its measured volume free-space delta was negative, so
no physical recovery is attributed to conversion. Separately, regenerable Homebrew
cache cleanup reduced allocated cache bytes by 2,731,327,488. The observed volume
free-space increase during that cleanup was 3,723,386,880 bytes and includes concurrent
filesystem effects. No native history, active uv cache or custody copy was deleted.

The focused followup suite passed 57 tests. Nineteen scoped cheap gates passed and the
corrected formatting shard passed. Broad local heavy verification was not run after
machine admission denied `swap-fraction`; the safeguard remains active. Hosted CI
cannot start because of the independently confirmed account billing/spending gate.
Existing issue #2848 owns external acceptance gates. A real native visual smoke test
succeeded in TextEdit; Codex-target access remains restricted by the platform harness.

Both dirty/divergent primary checkouts are preserved. The isolated implementation
worktrees are retained for source/custody provenance. Accepted source, runtime identity,
natural observer firing and final independent readback are linked through PR receipts;
an unavailable gate is never reported as a passing test.
