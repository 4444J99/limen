# Census runtime adoption

Owner: Codex; IRF-SYS-257. Full gap-filling scope remains active.

PR #2640 merged as a60175462bee077d99544b2133d8f662f9b1c3f4. The existing Domus activation adapter reviewed the exact merged contract, installed the immutable runtime, archived prior heartbeat state, and performed one controlled fire. Before activation launchd reported not running and the single-flight lock was absent. The verified plan digest is recorded in the companion receipt.

Activation and a separate installed verification returned verified=true, matching runtime identity and digest, zero surviving processes, and the retired watchdog absent. The controlled fire returned finding, not blanket health. Only one new-runtime native receipt was available at this observation; the three-fire acceptance remains pending and must use scripts/check-heartbeat-rollout.py --require-active --expected-sha a60175462bee077d99544b2133d8f662f9b1c3f4 without lowering its default fire count.

The direct installed census returned in 15.060 seconds inside the 30-second outer budget. Its exit 1 retains undeclared-item findings; BTM remains unmeasured. This is bounded execution evidence, not complete background-item health. Follow-up owner IRF-SYS-257 must reconcile each undeclared item against its canonical Domus owner and obtain BTM evidence without extending the heartbeat wall limit. No item was disabled, deleted, or exempted.

Receipts: docs/receipts/census-runtime-adoption-20260916.json and docs/receipts/background-census-runtime-20260916.json. No provider launch, task transition, account change or external correspondence occurred.
