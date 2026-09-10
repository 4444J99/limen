# MCP estate implementation receipt — 2026-09-08

## Resumed source implementation

Protected session `mcp-estate-resume-20260908` holds scoped execution run
`run-3890a837deca93e3ca65ac4ef1bce340`, lease `lease-1034-3890a837deca93e3`, generation 1034.
The task claim itself returned `busy` because the deployed keeper adds repository-wide code
exclusion to board-only packets. The four exact conflicting peer leases were inspected and
preserved; the separate two-branch execution packet was accepted and claimed. Prerequisite #2569
now corrects only the strict existing board-only contract; malformed packets retain exclusion.
This separate execution record is not a canonical task-state transition.

This resumed implementation adds:

- Read-only native `mcp_estate_status` with CLI-identical inventory JSON and MCP read-only hints.
- Configured and cached Codex manifests plus hosted-app declarations; ambiguous and overridden
  copies retain sanitized provenance. Inactive project and cache scopes are never probed.
- Filtered checks always return 77. Client receipt bundles cannot attest themselves: independent
  receipt/dependency/version observations are required. The native observation producer is still
  missing, so those dimensions remain unavailable rather than accepting a forged passing bundle.
- Explicit HTTP credential-header references, cumulative response ceilings, malformed pagination
  refusal, and fresh configuration reload after the one owned repair attempt.
- Read-only reconciliation of ianva's existing upstream loader with materialized MCPHub settings;
  this does not introduce another gateway or certify route/capability equivalence.
- Skill candidate catalog accounting for names, paths, formatting and descriptions. Native omitted
  skills and stripped descriptions remain null when telemetry cannot distinguish them. Metadata
  edits stay within frontmatter, serialize through a private lock, record custody before mutation,
  retain interrupted episodes and refuse rollback if the whole installed artifact has changed.
  Missing/corrupt custody fails closed. A size proxy or old truncation log cannot return green.

Focused results: 54 tests passed across retained estate, skill custody and existing boot
compatibility suite; 38 companion Domus tests
passed. Domus ownership validation and commit hooks passed. These focused results do not replace
the required admitted scoped batches or fresh application canaries.

## Current live observations and required continuation

Expanded source denominator: **122 service identities, 155 registrations**. Inventory-only
measurement returned **77**, with seven separate defect counts: missing capabilities **11**,
ownership conflicts **6**, unintended launches **0**, protocol failures **0**, authentication
gaps **0**, unmeasured integrations **154**, abandoned processes **0**. Zeros here mean no defect
observed in that dimension by inventory-only measurement, not successful protocol/auth/UI probes.
Fourteen coverage gaps remain, including the 13 distinct required adapter canaries.

The existing ianva loader and materialized MCPHub file both contain only two upstreams, `limen`
and `playwright`. Both configuration entries are enabled; capability and client-route evidence
remain unmeasured. No upstream cutover or external exposure was performed.

The deployed credential owner's read-only status returned exit 1 and `not_logged_in` for the
enabled direct LaunchDarkly registration. Consent remains owned by existing
`L-LAUNCHDARKLY-OAUTH-CONSENT`; the direct route was preserved. This independent observation
is not included in inventory-only authentication counts and is not an authenticated exchange.

Skill census: 358 filesystem candidate skills, zero parsed-metadata failures, zero missing
descriptions; the native truncation telemetry reports 268 skills and a 5440-token budget from
an older process. That is a denominator mismatch and missing fresh loading witness, not success.

Required owner actions remain the supplied estate plan: finish effective app-environment and
adapter version witnesses; safe functional calls, client behavior and isolation canaries;
deployment of exact merged revisions; targeted Domus apply and conditional gateway cutover;
then a fresh full-estate measurement with all seven counts zero. #2569 owns publication recovery,
the admitted full verification boundary and two consecutive real post-deployment mutations.
Its updated Worker remote job passed; its full scoped/local admission is not inferred from that.
Neither implementation completion, deployment completion nor estate-ideal satisfaction is claimed.

The estate scoped batch used exact ancestor `26b82ebc65bc2057b39dcef1499edc78308c0489`.
Nineteen of 20 cheap gates passed, including mypy, lint, formatting, paused-beat, ownership and
ideal-form checks. `agent-docs` failed with `FileNotFoundError` for `apps/danse/AGENTS.md`:
`git ls-tree HEAD apps/danse` contains only its README, while the unchanged instruction verifier
still includes the removed component instruction file in `REFERENCE_DOCS`. This is an existing
relocation/reference defect, not a passing or waived gate. Its durable disposition is this PR's
verification blocker, owned by the shared instruction-surface verifier. Next owner action:
reconcile the relocated component's canonical references, then run `python3 scripts/check-agent-docs.py`.
The batch did not reach the heavy tier. Unchanged green shard receipts remain historical evidence;
focused tests and lint cover subsequent protocol refinements, not a new whole-batch pass.

Functional smoke calls now require an explicit bounded read-only owner declaration and validate
their result envelopes. Raw functional response content is excluded from reports. Invalid launch
specifications remain counted and never launch; combined OpenCode argv is normalized without
dropping arguments. Cleanup refuses to signal a group whose original leader has exited and whose
remaining membership cannot be proven; that case remains unmeasured rather than claiming cleanup.

## Recovered full CLI failure identities

Remote prerequisite run `34260120907`, exact head `f8c6ca2c237de591c3ee60837abf8d10a37236aa`,
finished with **6839 passed, 3 failed, 4 skipped**. The failures are:

- `cli/tests/test_diurnal_shipping.py::test_the_pr_number_is_recorded_so_the_next_run_can_reap_it`
- `cli/tests/test_diurnal_shipping.py::test_no_pr_is_recorded_when_ship_docs_already_merged`
- `cli/tests/test_private_vault.py::test_real_gpg_round_trip_with_scratch_key`

The two diurnal cases reproduce on untouched primary-checkout head
`26b82ebc65bc2057b39dcef1499edc78308c0489` with the same missing receipt keys. Owner:
`scripts/diurnal.py` and its receipt fixture. The GPG failure is the canonical public-key armor
comparison in `scripts/private-vault.py`; owner: private-vault's portable scratch-GPG fixture.
All four implicated source/test files are byte-identical between the prerequisite base and its
tested head. They are evidence-backed unrelated-suite dispositions under the user's scope,
not waived failures or reasons to take on the diurnal/vault tasks. The full suite remains failed.
The next owner probes are the two named diurnal test nodes and the named private-vault node;
no full-suite retry or credential/key modification was performed here.

The last skill refinement validates YAML metadata round-trip, correctly escapes control characters,
and preserves every non-description key and instruction body; its 14-test shard passed.

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

## Completion continuation — 2026-09-08, current Codex execution

The user requires three independent outcomes: implementation verified, exact changes deployed, and the estate ideal satisfied. Every required registration must have fresh passing evidence; both denominators and all seven defect counts must be explicit, with every defect count zero. Partial receipts, drafts, queued merges and filed blockers remain intermediate states. None of the three whole-estate outcomes is claimed by this receipt.

Protected session `mcp-estate-complete-20260908` acquired Limen run `run-d41cd64aaf7052a1ac3de532d52f897a`, lease generation 1036, and Domus run `run-4595a4de901a376edce92627c0f9ee28`, lease generation 1037. Existing branch work was preserved. The broker rejected cancellation of the unstarted protected Domus reservation; it was subsequently claimed for the authorized work, rather than abandoned. No peer session was signalled or displaced.

### Implemented and verified in this continuation

- Retained malformed undeclared registrations in the denominator; duplicate JSON keys and malformed launch fields fail closed. Invalid plugin/project containers no longer hide the remaining registrations. Per-client environment inputs resolve relocated configuration roots independently.
- Installed-plugin registry selection distinguishes user/project scope and exact installed version from older cache candidates. Overridden cache manifests remain sanitized provenance. Claude enabled-plugin settings are read separately from its MCP configuration. This remains partial effective configuration coverage, not proof of every client loader.
- Added `mcp_native_observer.py`: a bounded Codex app-server observation producer, using the installed CLI schema inspected in this session (0.153.4). It requires an active, fresh Codex broker execution lease and host admission; it checks binary/configuration stability, independent native version identity, pagination, native catalog shapes and owned cleanup. It requests no model turn, login, config write or refresh. MCP status is requested only when the active inventory has explicit quiet-launch evidence.
- Canary acceptance now binds broker run, native connection identity, collection timestamp, dependency fingerprint and observed versions. A supplied receipt bundle has no observation authority. A native route observation cannot satisfy missing startup UI, dashboard or isolation evidence.
- Extended skill accounting to compare an in-process native catalog with filesystem candidates, distinguishing native-only/candidate-only entries and changed descriptions. Rendered token-budget evidence, model-context omissions and description stripping remain unknown. Listing skills is not a fresh model-rendering witness.
- Domus adds exact-target, policy- and source-version-bound conditional rollback with private write-ahead custody, original mode restoration and late-write/interruption preservation. Source: companion #379, commit `6e54474d`.
- Reused the exact diurnal/GPG fixture corrections from prerequisite `256cc3f5c`; no production key-validation logic changed. The already-landed Danse instruction-reference repair was integrated from main without recreating the retired app tree.

The estate focused MCP/native/skill batch passed 67 tests; four additional collector race/pagination/version tests passed. A native refusal fixture had a leader-exit cleanup race; keeping its synthetic leader alive until owned cleanup corrected it, and the sole failed test passed. All 20 scoped cheap gates passed; subsequent source changes invalidate only their syntax/lint/format and focused-test shards, which are rerun separately. Heavy admission returned 75 on swap pressure. Domus has 58 focused tests passing, ownership validation passing and commit hooks passing. These are scoped receipts, not a full estate implementation pass.

### Prerequisite and live evidence

Prerequisite #2569 exact head `256cc3f5c29a135326ce6f2bbfd65568c958ea2f` passed both remote CI and PR Gate. The previously failing full CLI suite now reports **6842 passed, 4 skipped**, and API reports **48 passed**. Receipts: https://github.com/4444J99/limen/actions/runs/34264919650 and https://github.com/4444J99/limen/actions/runs/34264919678 . The declared local build/deploy admission remains unavailable and is not replaced by advisory CI. No merge or Worker deployment occurred.

The direct native catalog attempt was denied before app-server startup (`swap-fraction,vitals-shed`, exit 77). No fresh native-client canary or rendered skill-budget witness was produced. The remaining twelve adapter producers, per-client effective environment/configuration witnesses, complete gateway route/capability equivalence, broader owner modifiers, and UI/isolation/process measurements remain implementation and acceptance work. They cannot be certified from direct server probes or synthetic tests.

Read-only LaunchDarkly status again returned exit 1 and `not_logged_in`. The direct route is preserved; consent and the authenticated exchange remain owned by `L-LAUNCHDARKLY-OAUTH-CONSENT`. No health check initiated login.

Unfiltered **inventory-only** measurement against current live files and the candidate Domus policy returned **77**: **123 service identities, 156 registrations**, 14 coverage gaps. Defects: missing capabilities **12**, ownership conflicts **6**, unintended launches **0**, protocol failures **0**, authentication gaps **0**, unmeasured integrations **155**, abandoned processes **0**. Inventory zeros do not establish protocol/authentication/UI/cleanup success; the separate LaunchDarkly observation remains an authentication gap. Neither source branch nor policy is deployed.

### Canonical task-update exclusion receipt

The completion requirement is durable in the execution packet and this continuation. Its canonical task-context update returned the complete sanitized busy response below. The exact conflicting graph was inspected: this is the sessions own active scoped Limen lease, not a peer. The deployed keeper still adds repository-wide exclusion to the strict board-only packet. The task remains `open`; no local projection edit or task completion occurred. Owner: #2569 publisher/claim isolation. Next command after its local admission and exact deployment: resubmit the broker-owned context update, then a second real task mutation, verifying both publication receipts without manual ref restoration.

```json
{
  "schema_version": "limen.conduct_submit_result.v1",
  "status": "busy",
  "busy_receipt_id": "busy-f105af734d2c474a03d05529",
  "work_id": "mcp-estate-completion-requirement-20260908",
  "conflicts": [
    {
      "lease_id": "lease-1036-d41cd64aaf7052a1",
      "run_id": "run-d41cd64aaf7052a1ac3de532d52f897a",
      "keys": [
        [
          "repo/4444j99/limen/write",
          "branch/4444j99/limen/feat/mcp-estate-contract-20260908"
        ],
        [
          "repo/4444j99/limen/write",
          "branch/4444j99/limen/fix/keeper-publication-recovery-20260908"
        ],
        [
          "repo/4444j99/limen/write",
          "path/4444j99/limen/main/AGENTS.md"
        ],
        [
          "repo/4444j99/limen/write",
          "path/4444j99/limen/main/cli"
        ],
        [
          "repo/4444j99/limen/write",
          "path/4444j99/limen/main/docs/agent-instruction-standard.md"
        ],
        [
          "repo/4444j99/limen/write",
          "path/4444j99/limen/main/docs/receipts"
        ],
        [
          "repo/4444j99/limen/write",
          "path/4444j99/limen/main/mcp"
        ],
        [
          "repo/4444j99/limen/write",
          "path/4444j99/limen/main/scripts"
        ],
        [
          "repo/4444j99/limen/write",
          "path/4444j99/limen/main/web/worker"
        ]
      ]
    }
  ]
}
```

Remaining acceptance and deployment ownership stays with MCP-ESTATE-20260908, Limen #2567/#2569 and Domus #379. No implementation-complete, deployed, estate-ideal or terminal closeout claim is made.

### Completion correction and continued execution

The operator rejected stopping at the preceding partial handoff. That correction binds this task: keep the full implementation, deployment and zero-defect acceptance scope active across turns; a pressure-denied native or build lane does not stop independent source implementation. Releasing an execution lease or pushing a draft is not a task boundary. Continue admissible work until the full predicate passes or no meaningful independent action remains behind a precisely owned external gate.

The next native Codex execution is broker run `run-838daff04c181b2d3d933b9d4bbcc455`, lease `lease-1041-838daff04c181b2d`, preserving the existing branches and unchanged receipts. Its packet carries this correction and the original completion requirement.

This continuation adds gateway declaration/materialization comparison (including launch arguments, headers, environment, disabled/missing/extra upstreams), strict source-container validation, explicit capability/schema mapping comparison, and gateway gaps that control the estate exit. It also adds PID-reuse-resistant child custody, bounded group-absence verification, and sampled process-count/RSS evidence to the protocol and native collectors. The OpenCode adapter uses the actual native HTTP runtime, validates its live API and version, creates an owned native session, reads effective configuration and MCP status, then removes that session and its owned process. No model turn, login, configuration edit or existing-session mutation is performed.

Adapter source: [OpenCode server contract](https://opencode.ai/docs/server/), inspected alongside installed `opencode --version` = `1.18.20`. MCP status does not expose an independently bound server version in this adapter; that field stays missing and cannot mint a passing registration receipt. This is a native observation producer, not evidence of a live canary passing.

Focused receipts: `python3 -m pytest cli/tests/test_mcp_gateway_evidence.py -q` **16 passed**; affected process/protocol/Codex tests **60 passed**; `python3 -m pytest cli/tests/test_mcp_opencode_observer.py -q` **12 passed**. Changed Python files pass Ruff after formatting. The run remains active for the remaining implementations and acceptance work; these receipts do not replace the full completion predicate.

The continuation's scoped cheap wave passed **11/11 gates** with finite 180-second per-gate deadlines. At `2026-09-08T19:52:33Z`, admission still reported `swap-fraction,vitals-shed`, swap fraction `0.3924`, and no live host lease. No denied heavy gate was bypassed or claimed green. Independent implementation continues under the active broker lease.

The next batch binds each native registration receipt to the client-loaded effective launch fingerprint. Native configuration absence, disabled entries, malformed entries and changed environment values cannot produce a receipt from a matching server name. OpenCode's `environment` mapping and Claude's default settings/plugin root are resolved explicitly; malformed registration containers remain coverage gaps. Effective maps expose only launch fingerprints and state.

The installed Codex `0.153.4` generated protocol schema declares `thread/start` with `ephemeral`, and `mcpServer/tool/call` with `threadId`, `server`, `tool` and `arguments`. The collector now creates that real native thread for MCP observations and executes bounded, owner-declared read-only tool calls through it. It validates the whole batch against native configuration and catalogs, rechecks dependencies before calls, counts per-server functional outcomes, and never emits response content. No model turn or login is sent. Missing UI, isolation, version or other evidence remains missing.

Verification: the initial configuration/collector regression batch passed **82 tests**. After adding native-thread functional calls, the changed native/configuration shard passed **33 tests**, including dependency-race refusal before any functional call, wrong-route refusal, malformed contracts and private-response exclusion. Previous unaffected receipts remain evidence. The full implementation/deployment/estate predicate is still active.

This batch's scoped cheap wave passed **11/11 gates**; the changed production scripts also passed explicit Ruff lint. Required heavy and native-runtime receipts have not been replaced by these local synthetic predicates.
