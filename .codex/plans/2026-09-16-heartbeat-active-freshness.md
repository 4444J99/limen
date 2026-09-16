# Fresh active-runtime proof

Owner: Codex; heartbeat adoption acceptance.

The rollout checker validated SHA/status/descendants and minimum spacing but never receipt age. A stopped runtime could therefore retain active proof indefinitely. Validate finite positive numeric timestamps before sorting; reject future and malformed values without traceback. Require the latest receipt within the registered 300-second interval plus 120-second maximum tick duration. Derive both bounds from the existing scheduled contract; no runtime or timing configuration changes.

Tests use an injected observation clock; historical fixture dates no longer depend on wall time. Boundary tests cover exactly 420 seconds, stale 421 seconds, missing/string/boolean/nonfinite/oversized/negative and future timestamps. Prior live adoption evidence remains valid for its recorded observation time; it is not perpetual proof.

Verification at ec9ac52ba: all 10 cheap gates, 7,746 CLI tests (2 skipped), and 52 API tests passed. The live predicate returned FAIL because native receipt 4ddb85f25a254e06ac32fd5cc10ef926 at 2026-09-16T04:10:36Z recorded background-items-census timeout, status failed, and descendant count unknown. This is a retained runtime failure, not a test failure or proof of surviving processes. A subsequent notification-registry-parity fire passed; it does not erase the failed fire from the required consecutive window.

Follow-up owner: background-items-census under IRF-SYS-257 / heartbeat acceptance. Its sfltool subprocess has a 30-second deadline equal to the outer 30-second probe deadline, leaving no cleanup margin. Next engineering action: reproduce with an isolated timeout fixture, derive a nested execution budget that fits the existing outer limit, preserve unavailable BTM evidence visibly, then verify bounded cleanup before runtime adoption. No active process was signaled or runtime configuration changed.
