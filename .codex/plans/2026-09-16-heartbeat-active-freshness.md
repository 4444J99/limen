# Fresh active-runtime proof

Owner: Codex; heartbeat adoption acceptance.

The rollout checker validated SHA/status/descendants and minimum spacing but never receipt age. A stopped runtime could therefore retain active proof indefinitely. Validate finite positive numeric timestamps before sorting; reject future and malformed values without traceback. Require the latest receipt within the registered 300-second interval plus 120-second maximum tick duration. Derive both bounds from the existing scheduled contract; no runtime or timing configuration changes.

Tests use an injected observation clock; historical fixture dates no longer depend on wall time. Boundary tests cover exactly 420 seconds, stale 421 seconds, missing/string/boolean/nonfinite/oversized/negative and future timestamps. Prior live adoption evidence remains valid for its recorded observation time; it is not perpetual proof.
