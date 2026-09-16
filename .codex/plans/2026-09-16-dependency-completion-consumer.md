# Dependency completion consumer

Owner: Codex; dependency-delivery integration / shared policy PR #26.

Extend the existing read-only upkeep CLI with --completed-run RUN_ID. Treat that integer as a hint, resolve current repository/run/PR identity through authenticated GETs, require a completed successful same-repository pull-request run, then invoke the existing evidence consumer. Re-read run attempt and PR generation afterwards. Five bounded identity GETs supplement the existing bounded consumer; no candidate code, review request, lease, provider launch or merge runs. Replays repeat reads and cannot duplicate an effect.

Unconfigured repositories fail closed rather than falling through as non-dependencies. The current shared repository remains unconfigured; no pilot/trust authority was expanded. This is the consumer portion only. Authenticated completion-event delivery, a reviewed shared Actions policy, isolated credentials and protected transaction acceptance remain implementation obligations under L-DEPENDABOT-DELIVERY-ARM / shared PR #26. Do not claim those review findings resolved from these fixtures.

Launch: python3 scripts/_dependency_upkeep.py --repo REGISTERED_PILOT --completed-run RUN_ID. The existing --pr/--expected-head interface remains available. Supplying a head with completion mode is rejected because current evidence owns it.

Focused validation: 24 dependency upkeep tests passed. Existing policy/artifact freshness and trust checks remain authoritative; this adapter adds identity binding rather than replacing them. The scoped resolver must pass before integration.
