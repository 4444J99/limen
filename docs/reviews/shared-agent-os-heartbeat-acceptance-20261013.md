# Shared operating system heartbeat acceptance — October 13, 2026

The shared-pool, configuration and native-verification repairs are merged and deployed. Limen PR #2861 adds the final bounded native TCC audit route and includes the shared admission-root repair from #2860. Domus private PR #426 remains accepted. This report supplements the original deployment record without replacing its failed or incomplete observations.

Tested source: `47fb2b23bc55ef3eac2731f8eccd40adcf075b35`. Deployed runtime: `dcb273386f48a5836256c9033664ed71d7f36b4f`. All 14 reviewed files match the installed source. The managed activation verified the contract, plist, complete source/installed CLI package and interpreter, with zero surviving processes. Changing TMPDIR now resolves to the same canonical shared admission store; no live lease store was cleared or migrated.

Validation passed: 8,639 CLI tests, 70 existing skips, eight subtests; 52 API tests; web build; all 14 cheap gates. The five changed typing/syntax/lint/format/hygiene shards and 18 strict native-job cases passed after the observer-induced RSS failure was corrected. One normal admitted heavy batch ran for 289.69 seconds after cleanup released its slot, then released its lease and flock.

LaunchServices routes the same signed native host whose grants already matched its signature. The native job binds requester/host/receiver birth identities, nonce, wall/CPU/RSS/output bounds and actual completion. Native active-job inspection avoids the transient protected ps child that caused EPERM during aggregate RSS measurement. Complete inventories remain private; scheduled receipts retain compact typed findings and explicit cleanup truth. No grants, signing requirements, thresholds, probe cadences or failure safeguards were relaxed.

Final-fingerprint natural execution acceptance: **passed**. These observations are separate from the controlled activation and earlier 3a3 proofs. The machine-readable record binds actual launchd parentage, exit observations, receipt hashes, typed findings and same-boot awake-clock cadence.

- dialogs-silenced: 2026-10-13T19:47:23Z; finding; 5785 ms whole tick; descendants 0; observed root and process identities exited.
- runtime-maintenance-observation: 2026-10-13T19:37:58Z; passed; 23867 ms whole tick; descendants 0; observed root and process identities exited.
- runtime-maintenance-observation: 2026-10-13T19:53:30Z; passed; 19123 ms whole tick; descendants 0; observed root and process identities exited.

Shared growth headroom was 34.73 GiB at 2026-10-13T19:53:46.711603+00:00. The complete census measured 20.47 GiB consumption. Filesystem free bytes, required reserve and outstanding reservations are reported separately; the protected foreign reservation remains counted once. Zero measured reserve components are disclosed as registered inputs, not a guarantee about future application writes. No physical recovery is attributed to this routing or quota-accounting change.

The six-month ledger covers April 12 through October 12 in America/New_York, using an exclusive October 13 boundary: 15 providers, 2,366,993 record observations and 264 linked authenticated remote candidates out of 265. April/May coverage gaps remain missing evidence; historical Limen PR 10 remains HTTP 404. Prompt correction lineage, redaction and exact receipt linkage remain preserved.

The original independent watch retains its October 13 03:02:10.931617Z anchor and October 14 end. Its early unretained window, 18 historical maintenance payload gaps and unknown old timeout cleanup remain incomplete. Earlier measured sleep explains two wall-clock gaps; it does not repair missing evidence. No replacement watch or scheduler was created.

Permission health remains incomplete under [Limen #1703](https://github.com/4444J99/limen/issues/1703): an actual native authentication sheet gates grant cleanup. Existing unrelated application-grant changes and historical path clients are preserved. The real TextEdit native visual smoke test passed; Codex-target visual capture remains blocked by the platform safeguard. Claude source/render parity and a second no-change apply remain proved in the original acceptance record.

The existing [shared OS owner #2848](https://github.com/4444J99/limen/issues/2848) retains the longer watch, evidence gaps and source-checkout custody. Dirty divergent primary checkouts, native histories, active database sidecars, custody partials and foreign sessions remain preserved. This report changes no runtime source and requires no further installation.

Exact fingerprints, verification receipts and natural acceptance: [machine-readable record](shared-agent-os-heartbeat-acceptance-20261013.json). Original delivery: [deployment record](shared-agent-os-deployment-20261012.md) and [original acceptance](shared-agent-os-final-acceptance-20261013.json).
