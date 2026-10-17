# Plan: close every remaining audiovisual (time-moment-brief) acceptance gap

Issue: #2909
PR: (pending)

Status: READY — owner decisions taken 2026-10-17:
- **History purge: DECLINED.** G1 closes as "exposure bounded (private, owner-only, fork-free,
  no Pages), purge declined". Lane E reduces to filing `L-TMB-HISTORY-REMOVAL` as `deferred`
  with the six OIDs and the prepared-mirror recipe recorded in its steps. No v2 validator, no
  filter-repo run, no force-push, no SHA re-pin churn.
- **Allowance now: limen lanes A, B, C, L only** (~4 capsules). TMB lanes D–K are fully
  specified below but wait for a second explicit authorization; they are homed by the plan doc +
  issue created in Lane B step 0.

Facts below are verified from live state on 2026-10-17.

## Context

The AV engineering landed on 2026-10-10 (time-moment-brief PR #3 `e5900ef`, PR #4 `44d815c`;
simvltanea PR #28 `fc78b41`). Limen PR #2904 (`0a8b91ce`) recorded reservation expiry and a
second-device custody copy. What remains is a short list of gaps that the receipts mark
FAILED/UNVERIFIED. Some are engineering; some need physical inputs only the human can supply.
This plan sorts them, closes every engineering-closable one, and files each physical one as a
lever with its exact resume command — so "all gaps filled" means: every gap is either closed with
a predicate receipt or homed in its registry owner with a named next action.

## Gap inventory (verified 2026-10-17)

| # | Gap | Current evidence | Class (pending exploration) |
|---|-----|------------------|-----------------------------|
| G1 | Private media blobs remain in remote git history (untracked at HEAD) | `git ls-tree 893efbcb` shows 4 blobs; absent at `7fa9181`/`44d815c` | engineering (history purge under containment receipt) |
| G2 | Second-device custody is unencrypted | Archive4T APFS, `Encrypted: No` | engineering (encrypted bundle) |
| G3 | Budget ledger 5+25 min not confirmed | graph node has no spend fields | engineering (keeper ledger readback) |
| G4 | `merge-policy.sh` BLOCKED ×2 "cannot read PR" while `gh` read it | PR #2904 | engineering (limen defect) |
| G5 | Live limen checkout behind origin/main | `main...origin/main [behind 1]` before #2904 | engineering (sync-release beat) |
| G6 | Browser FOA/binaural audio rendering UNVERIFIED | receipt row | pending |
| G7 | N-generation resource maxima / moving-source timing | receipt row | pending |
| G8 | Four physical cameras (three sensors) | Danse #69 | human / new capture (pending) |
| G9 | `Ingress` source volume absent → lineage unverified | PRESERVATION_REPAIR_RECEIPT | human-physical |
| G10 | Safari sustained playback / WebCodecs lifecycle | DEVICE_ACCEPTANCE_RESULTS limits | pending |
| G11 | Phone, WebXR headset, comfort/thermal, lip-sync capture | DEVICE-CHECK.md | human-physical |
| G12 | Worktree `av-second-device-custody-20261017` retained, unreaped | `git worktree list` | engineering (receipt-backed reap) |

### Already filed (registry scan 2026-10-17 — do not duplicate)

- `tasks.yaml`: nothing for TMB/AV.
- `his-hand-levers.json` (canonical: `/Users/4jp/Workspace/limen/his-hand-levers.json`): only
  `L-DANSE-ARTISTIC-APPROVAL` (blocked, artistic cut/rights) — no lever for Ingress, cameras,
  headset, phone, lip-sync, or the custody disk.
- screendance issues: #69 (GoPro MAX + FOA matched pair — owns G8), #21 (two-checksum custody +
  clean restore — owns G2's acceptance predicate), #11/#14 (spatial sound, installation).
- time-moment-brief has NO issues, and three OPEN PRs that are unaccounted hanging work:
  #1 "Make WebCodecs decode and present real sources", #2 "Immersive VR … (device acceptance
  unverified)", #5 "Declare functional playback boundaries without changing pinned runtime".
  → new gap **G13**: disposition of TMB PRs #1/#2/#5 (superseded by #3/#4? or still pending?).

### Doctrine and tooling located (limen, 2026-10-17)

- **G1 history purge** — no local rewrite / force-push path exists or is permitted (AGENTS.md
  rule 5; CLAUDE.md reroute). Sanctioned path = lever pattern `L-GITHUB-PR2532-HISTORY-REMOVAL`:
  private packet `limen.sensitive_history_removal_packet.v1` (validated by
  `scripts/check-sensitive-history-removal.py:77-172`; needs ≥2 custody copies with distinct
  `device_id`, `restore_verified_at`, sha256 AND exact git blob OID), `preflight --packet`, one
  GitHub sensitive-data-removal request, then `postflight --packet … --apply --receipt
  docs/receipts/privacy/<name>.json` (create-only, immutable), merged via PR, linked to owner issue.
  Pre-rewrite containment predicate: `scripts/check-prerewrite-containment.py` (A ledger / B
  blob-hash in private clone / C no push-capable upstream on old branches; quarantine form
  `branch.<b>.remote="."`).
- **G2 encrypted custody** — sanctioned form is arca-sealed ciphertext (AES-256-CBC
  `openssl enc -pbkdf2 -iter 200000` tar; key at `op://Private/limen-arca-vault/password`, never
  recited). Tool: `scripts/check-group02-independent-custody.py` (preserve + key-less verify of
  `ciphertext_sha256`/`ciphertext_bytes`). Receipt schema `limen.custody_receipt.v2`
  (`docs/estate-custody-primitives.md:52-62`); physical-device receipts are v1. Nearest lever:
  `L-UNIVERSE-RECOVERY-CUSTODY-VOLUMES` (needs_human; Archive4T + T7Recovery identity/restore).
  Archive4T role: `institutio/governance/storage-roles.yaml:168-178` (optional local archive).
- **G4 merge-policy** — `scripts/merge-policy.sh:101-122`: `lookup_failure` greps `$err` for
  rate-limit/transport patterns, else exit 3 and DISCARDS `$err`. The same `gh pr view --json …`
  succeeds now. Fix: print a bounded, scrubbed tail of `$err` on the exit-3 path. Test harness:
  `scripts/tests/merge-policy.test.sh` (`check`/`check_output` helpers at 94/108; transport/auth
  cases at 230-302).
- **Levers** — `/Users/4jp/Workspace/limen/his-hand-levers.json` (107 levers; keys `id, label,
  status, owner, issue, gate, cost, unlocks, note, steps, added …`). Added by direct edit in a
  worktree + PR; a bare `L-*` id in prose must exist (`no-tasks-on-me.sh` §8).

### TMB predicates classified (origin/main 44d815c, 2026-10-17)

| Gap | Exact predicate | Closable by |
|-----|-----------------|-------------|
| G6 FOA audio | `pytest tests/e2e/test_foa_browser_audio.py` = 4 pass (OfflineAudioContext, procedural ACN/SN3D). UNVERIFIED part = live `AudioContext` on a real output device + matched archival pair + acoustic output | engineering (loopback capture via virtual audio device) + human (matched pair = Danse #69) |
| G7 N-gen maxima | `test_n_generation_playback.py` (19; `t7_17` real-media skips without derivatives). Open: live frame/bitmap/decoder/worker/texture/audio counts on target hardware + wall-clock soak; loops need marker video + independent audio, frame gap ≤1, A/V ≤50 ms. No soak/maxima in `DEVICE_ACCEPTANCE_RESULTS.json` | engineering on M5 Mac (after derivatives hydrate); phone numbers human |
| G8 four cameras | `source-manifest.json` sensors=3 views=4; cam3 = rectilinear crop of gopro-360. Census lists `100GOPRO` (real GoPro HERO, NOT in manifest) — candidate fourth view, unchecked, needs Ingress | human/new-capture; engineering after Ingress |
| G9 Ingress | expected `/Volumes/Ingress/backwards-up-hill/{2022FEB-360GOPRO,100GOPRO,PANASONIC,DJI,F6/220218_012.WAV}`; `tools/build_role_derivatives.py` → 16 derivatives. NO sha256 of originals exists anywhere (census = size/duration only) → first mount must produce the hash chain | human (mount) then engineering |
| G10 Safari lifecycle | no predicate exists; `native_browser_probe.py` covers parity only. Needs a new probe page on the same byte-range server + a feature check for `VideoDecoder` in Safari workers | engineering only |
| G11 headset/phone | `webcodecs-spike/DEVICE-CHECK.md` gates A–E; receipt `DEVICE-CHECK-<model>-<date>.md`; phone unnamed in any receipt | human-physical |
| parity headline | CLOSED (9/9 on ANGLE Metal, SwiftShader, Safari). Stale wording remains in `AGENT8_ACCEPTANCE_REPORT.md:94`, `TEST_INFRA.md:74`, `evidence/acceptance-status.json` (96.7–99.5%) | engineering (docs correction) |

Skips: all conditional on `conftest.py` fixtures (`ingress_root`, `derivatives_present`) — nothing
hard-skipped. Unreconciled totals: "84 distinct, zero skips" vs AGENT4 "213 passed, 23 skipped".

### Design-phase corrections (TMB, 2026-10-17)

- The 16 derivatives + 4 clips ARE on disk (`.wt-agent7-integration/…/media/derivatives/` and the
  main checkout), byte counts match `source-manifest.json`. Ingress is needed only for the
  original hash chain and the 100GOPRO check — G7/G10 real-media runs can start now.
- `n-generation-player.js:449` calls `scheduler.getLoopContinuityReport()`; it does not exist on
  main. The implementation is UNCOMMITTED in the main checkout (branch `agent5-loop-continuity`
  `da10bd9`, +267 scheduler / +28 worker, untracked `AGENT5_RECEIPT.md`, Oct 9). Preserve first.
- `webcodecs-spike/` has no `AudioContext` → A/V ≤50 ms is measurable only on
  `panoramic-generation-proof.html`; spike loop continuity uses `frameSeq` (gap ≤1).
- `refs/pull/1/head`, `refs/pull/2/head`, `agent2-real-webcodecs`, `agent6-webxr` still contain
  `evidence/agent2-sidebar-*.png` → G1 packet must list them; never `--delete-branch` on close.
- 100GOPRO by metadata: ends ~16:18:51Z, passage starts ~16:43:44Z → likely no coverage, but
  camera clocks are untrusted; F6 audio onset match (`verify_alignment.find_offset`) is the test.
- No 2-ch loopback audio device installed (only Teams mono) → BlackHole install is a human step.
- Worker `MAX_QUEUE = 256` vs declared `maxQueuedFramesPerView: 8` — a real cap mismatch to fix.

### Design-phase corrections (limen, 2026-10-17 — verified by me)

- **Six blobs, not four.** `ed5a09f` added mp4 blobs `2b29542d…`/`05b73e81…`; `cbce79d` replaced
  them with `0b85513b…`/`8a68159d…`; `62c0c3e` added `b7c423db…`/`1bda5463…`; `e5900ef` deleted.
  The two superseded mp4 blobs have NO custody copy anywhere. PRs #3/#4 were squash-merged, so the
  blobs sit directly on `main` history; every branch/PR ref descends from `ed5a09f` → no ref
  deletion removes them; removal = full history rewrite + GitHub Support purge.
- `check-sensitive-history-removal.py` v1 cannot validate this (requires CLOSED-unmerged PR,
  Pages URLs, unauthenticated 200 on a private repo, single blob) → a v2 schema is needed.
- `check-prerewrite-containment.py` is hardcoded to limen's 2026-10-10 rewrite; only its
  quarantine form (`branch.<b>.remote="."`, `pushRemote="."`) carries over.
- `check-group02-independent-custody.py` is hardcoded to G02 ids/domus release → new
  `scripts/sealed-custody.py` reusing `scripts/arca.sh seal|unseal`, `_device_identity`, and
  the escrow key pattern (`env -u OP_SERVICE_ACCOUNT_TOKEN op read op://Private/limen-arca-vault/password`,
  64-hex check, key over `-pass fd:N`; never in an env var or transcript).
- G3: `conduct graph` DOES return `packet.spend` (I saw `limit: 6, reserve: 6` — the envelope
  Codex set wrongly). Cancel is the only refund path (`keeper.js:1731-1745`); status `expired`
  ≠ cancelled → envelope intact. The "5+25 minutes" was wall-clock allowance, not an envelope
  field; if `packet.task_id` is null there is no debit event — the receipt must say so.
- Limen remote is `4444J99/limen` (not organvm) — merge with `--repo 4444J99/limen`.

## Approach

Ordered lanes. Each limen lane: worktree off `origin/main` under `~/Workspace/.limen-worktrees/`,
one `scripts/verify-scoped.sh` on the final tree, one push, `gh pr merge N --repo 4444J99/limen
--squash --match-head-commit SHA`. Each TMB lane: worktree off `44d815c` (never the main checkout
— it holds uncommitted Agent 5 work — nor `~/Workspace/time-moment-brief`), copy the 16
derivatives + 4 clips into the ignored `media/` dir, browser batches one-at-a-time under
`scripts/host-work-admission.py`, exact-head merge with `--match-head-commit`. Actions never
evidence. One bare command per call; read each predicate's own exit code.

### Lane A — limen: merge-policy diagnostic (G4)
Branch `fix/merge-policy-lookup-diagnostic-20261017`. `scripts/merge-policy.sh` `lookup_failure`
before the exit-3 echo (~line 113): print `tail -c 300 "$err"` to stderr, scrubbed
(`gh[pousr]_…`, `github_pat_…`, `Bearer|Token|Authorization` values → `[REDACTED]`), control
chars stripped. HOLD paths untouched. Test: `scripts/tests/merge-policy.test.sh` after line 312,
`check_output "blocked: diagnostic surfaces" 3 "HTTP 404 Not Found" "ghp_abcdef"` with
`GH_PR_VIEW_ERROR` set via the existing stub. Note for later: transport regex `could not resolve`
also matches GraphQL "Could not resolve to a PullRequest" — the diagnostic will reveal which
class hid #2904's BLOCKED. Gates: merge-policy-test, dependency-acceptance-test,
merge-queue-contract-test, check-gates.

### Lane B — limen: levers (homes every human gate; must land before any `L-TMB-*` is cited)
Branch `docs/tmb-levers-20261017`. Step 0: `scripts/session-plan.py open tmb-acceptance-gaps
--title "TMB/AV acceptance gaps"` → run the printed `gh issue create` → issue N; move THIS plan's
content into the `docs/plans/2026-10-17-tmb-acceptance-gaps.md` it creates (with `Issue: #N`,
`PR: (pending)` headers — `check-session-phase.py` gates it). Approval here becomes the committed
plan; this scratch file is not a durable home. Then append to
`/Users/4jp/Workspace/limen/his-hand-levers.json` (Read-before-write, targeted append, key set
matching `L-GITHUB-PR2532-HISTORY-REMOVAL`, `sovereignty.reason` from `SOVEREIGN_REASONS`,
`diagnosed_at: null`, `implementation` block with `acceptance.status: "not_currently_verified"`):
- `L-TMB-INGRESS-SOURCE-MOUNT` (needs_human, physical_act) — unlocks first-mount sha256 chain +
  `tools/build_role_derivatives.py`.
- `L-TMB-FOURTH-CAMERA` (needs_human; depends on Ingress; owner Danse #69) — unlocks the
  100GOPRO F6-onset check via `ingress_resume.py`.
- `L-TMB-DEVICE-ACCEPTANCE` (needs_human) — phone + headset + capture hardware;
  `webcodecs-spike/DEVICE-CHECK.md` gates A–E → `DEVICE-CHECK-<model>-<date>.md`.
- `L-TMB-LOOPBACK-AUDIO-DEVICE` (needs_human) — install BlackHole 2ch (admin password +
  coreaudiod restart); unlocks `tests/e2e/foa_loopback_probe.py`.
- `L-TMB-HISTORY-REMOVAL` (**deferred**, sovereignty identity) — records the six blob OIDs
  (`2b29542d…`, `05b73e81…`, `0b85513b…`, `8a68159d…`, `b7c423db…`, `1bda5463…`), introducing
  commits `ed5a09f`/`cbce79d`/`62c0c3e`, the exposure assessment, and the full recipe from Lane E
  (mirror + `filter-repo --strip-blobs-with-ids`, force-push exception, Support request,
  commit-map + three re-pin PRs, plaintext retirement) so it can be executed later without
  re-derivation. `unlocks`: "owner reverses the 2026-10-17 decline".
Predicates: `python3 scripts/check-his-hand.py --check`, `python3 scripts/lever-classify.py
--check`. Gates: his-hand-registry-test, operator-gates, check-lifecycle, pytest-cli (heavy).

### Lane C — limen: sealed custody tool + execution (G2) and ledger readback (G3)
C1 branch `feat/sealed-custody-20261017`: new `scripts/sealed-custody.py` with verbs
`seal --source DIR --replica {staging,Archive4T} --run RUN` (calls `arca.sh seal` with `TMPDIR`
= 0700 per-run dir under `$LIMEN_CUSTODY_STAGING_ROOT`; ciphertext `O_EXCL` 0600; read-back
sha256), `verify --key-less` (ciphertext sha256/bytes vs manifest + tracked receipt),
`restore --replica …` (`ARCA_KEY_SOURCE=op` → proves escrow independent of the Mac Keychain;
`shasum -c` per member; scratch plaintext deleted), `receipt` (private `CustodyReceiptV1` via
`model_validate`, ≥2 `independent_device_ids` from `_device_identity`; redacted tracked copy).
Also: `scripts/arca.sh vault_key()` gains `ARCA_KEY_SOURCE=op` (Keychain stays default);
`cli/src/limen/agent_state/crypto.py` gains source kind `"arca-sealed-tar"`; hermetic test with
`op` stubbed; new `gates.yaml` entry `sealed-custody-test`.
C2 branch `docs/av-encrypted-custody-20261017`: bundle = `manifest.json` + 4 media + the two
historical blobs extracted via `git cat-file blob 2b29542d… / 05b73e81…` into 0700 staging
(stored under OID names; sha256 + OID in the private manifest) → replicas on internal staging
AND `/Volumes/Archive4T/limen-private/av-media-custody-20261017/` — ciphertext ONLY on
Archive4T (no new plaintext there; the existing verified `av-media-20261017-171406` dir is left
untouched until retirement). Plaintext of all six blobs lives only in the internal 0700 staging.
Lane C's `restore` verb proves each sealed replica reproduces the blob OIDs, so the only
plaintext to retire later is the internal staging dir plus the pre-existing
`av-media-20261017-171406` plaintext on Archive4T (both recorded in the receipt as
`plaintext_retained: true`; retirement stays a human-gated step on the deferred lever). Run seal×2, verify, restore×2, receipt. The `restore` step uses `op read`
without `OP_SERVICE_ACCOUNT_TOKEN` → Touch-ID prompt: run only with the operator present, never
from a background job. Tracked
receipt `docs/receipts/2026-10-17-av-encrypted-custody.json` (schema, run id, ciphertext
sha256/bytes, 6 blobs covered, `independent_device_count: 2`, restore booleans,
`key_source: "canonical-credential-organ"`, `plaintext_retained: true`, retirement lever id; NO
device ids/paths/member digests). Plaintext on Archive4T is RETAINED (deletion = human-gated,
last step of `L-TMB-HISTORY-REMOVAL`).
G3 in the same receipt: `limen conduct graph` + `limen conduct harvest` on
`run-12a1b2390e4ca37140f00d546c1cab26` (via the env-sourcing script pattern already used in
`$CLAUDE_JOB_DIR/tmp/graph-readonly.sh`): record `status: expired` (≠ cancelled → no refund),
`packet.spend {limit 6, reserve 6}`, `receipts: []`, harvest `unharvested: []`, and
`packet.task_id` (null → "no debit event exists; envelope declared, never refunded").

### Lane D — TMB: PR disposition (G13) — no branch
- #1 (`60722c2`) and #2 (`51b57cb`): ancestors of `7fa9181`; `e5900ef` tree-identical → close
  with metadata comment citing the landed SHA and `AGENT7_INTEGRATION_RECEIPT.md:204-205`.
  NEVER `--delete-branch` (heads carry private PNGs → Lane E packet).
- #5 (`2b9206f`, draft, CLEAN, base = current main): `git fetch origin pull/5/head`, worktree,
  `node --expose-gc --test shared-engine/tests/*.test.mjs`, `pytest tests/e2e/test_tier6_doc_freshness.py -q`,
  `gh pr ready 5`, `gh pr merge 5 --repo 4444J99/time-moment-brief --squash --match-head-commit 2b9206f441a0fd42d575bdc778a54e5665eb43b0`.
  Do this BEFORE Lane F (both touch README.md).

### Lane E — history removal (G1) — DECLINED 2026-10-17; retained as the deferred recipe
Not executed. The lever in Lane B carries this section's content as steps. Kept verbatim so a
later reversal needs no re-derivation:
Branch `feat/sensitive-history-removal-v2-20261017`: add
`limen.sensitive_history_removal_packet.v2` / `receipt.v2` to
`scripts/check-sensitive-history-removal.py` (v1 byte-for-byte unchanged) + tests in
`cli/tests/test_sensitive_history_removal.py`. v2 packet: `repository`, `visibility: private`,
`artifacts[]` {blob_oid, path, introduced_in, custody_copies[] ≥2 distinct device_id with
restore_verified_at + sha256 reproducing the OID}, `reachability_scan` {observed_at, refs} from
full `ls-remote` + `for-each-ref --contains` for ed5a09f/cbce79d/62c0c3e, `rewrite` {old_refs,
expected_new_refs from the prepared mirror, tip_tree_equal per branch — all tips post-date
`e5900ef` so trees must be unchanged}, and the local-carrier list for containment (Workspace TMB
clone, audiovisual-composition-system TMB worktree, custody-staging baseline clone). Preflight
(authenticated): `gh api repos/4444J99/time-moment-brief/git/blobs/<oid>` 200 ×6; mirror
`cat-file -e` fails ×6; tip trees equal; custody verified. Postflight: blob API 404/422 ×6;
fresh `--mirror` clone fails `cat-file -e` ×6; `commits/62c0c3e` 404/422; no `refs/pull/*`
resolves to old lineage. Receipt create-only at
`docs/receipts/privacy/tmb-history-removal-20261017.json`.
Prepared rewrite (private, reversible): `git clone --mirror … <staging>/tmb-mirror.git`;
`git -C <mirror> filter-repo --strip-blobs-with-ids <staging>/tmb-oids.txt` (6 OIDs;
`/opt/homebrew/bin/git-filter-repo`). Human steps in `L-TMB-HISTORY-REMOVAL`: (3) force-push
`refs/heads/*:refs/heads/*` from the mirror (not `--mirror`; GitHub rejects `refs/pull`);
(4) one GitHub Support "remove sensitive data" request naming repo, 6 OIDs, old SHAs, asking for
`refs/pull/{1..5}` dereference + GC — no content, no paths; (6) authorize plaintext retirement.
Agent then: postflight, receipt PR, quarantine every local carrier, re-clone.
**Cost of the purge (why G1 is a decision, not a chore).** `filter-repo` rewrites every commit
from `ed5a09f` forward, so `e5900ef`, `7fa9181`, `44d815c` cease to exist on origin. Everything
that pins them goes stale: simvltanea PR #28's six-file engine graph (pins the landed TMB commit
on `main`), `DEVICE_ACCEPTANCE_RESULTS.json` merge SHAs, every TMB receipt, limen receipt #2904.
If executed, Lane E must also: keep filter-repo's `commit-map`; open follow-on PRs — simvltanea
`PROVENANCE` re-pin, a limen receipt mapping old→new SHAs, TMB receipt SHA updates. Doctrine
conflict stated plainly: CLAUDE.md says never ask the human to force-push; the purge requires
exactly that, so it can only proceed as an explicit owner-authorized exception recorded in the
lever. Repo is private, owner-only, fork-free, no Pages — exposure is bounded to the owner and
GitHub. Two honest dispositions, owner's call: (a) execute — lever `open`, force-push as
recorded exception; (b) decline — seal custody (Lane C), lever `deferred` with the prepared
mirror retained, G1 closed as "exposure bounded, purge declined".

### Lane F — TMB: docs correction + e2e totals receipt
Branch `docs/parity-wording-and-test-totals` (after Lane D #5 merge). `TEST_INFRA.md:74` and
`README.md:112`: replace the lone 96.7–99.5% headline with the split statement (static poses
96.7–99.5% exact / MAE ≤0.85 SwiftShader; crossfade 34.0244% exact / MAE 0.647315 under its
<1/255 criterion; 9 parity cases on ANGLE Metal + SwiftShader; Safari 27.2 native probe 7
synthetic + 5 real-frame by bigPct<5/meanAbs<1, exact 88.8–92.7%). Never write "9/9 on three
backends" (Safari ran the probe, not the 9 pytest cases). `AGENT8_ACCEPTANCE_REPORT.md:93-94`:
keep history, append dated "CLOSED → BROWSER_REPAIR_RECEIPT.md:13, DEVICE_ACCEPTANCE_RESULTS.json".
`evidence/acceptance-status.json`: edit only `renderer_parity` (112) and limitations (125, 127);
leave `software_checks`/`acceptance_criteria` (tier6 `headline()` derives from them). Totals:
84 = browser batch (`ACCEPTANCE_BROWSER_RESULTS.json`); 213/23 = full e2e at Agent 4's head —
different denominators. Add `E2E_TOTALS_RECEIPT.md` from one `pytest tests/e2e -q -rs` (+
`--collect-only -q`) under a heavy lease, skips grouped by reason (only `ingress_root` consumers
should skip), head SHA, the 1-in-3 `TargetClosedError` cascade recorded honestly with a `--lf`
rerun of the failed shard. Predicate: tier6 passes.

### Lane G — TMB: land loop-continuity report (G7a; unblocks G7/G10 rows)
Branch `fix/loop-continuity-report`. First preserve: read `git diff` from the main checkout
(no mutation), save diff + `AGENT5_RECEIPT.md` to `$LIMEN_CUSTODY_STAGING_ROOT/<run>/`, apply in
a fresh worktree off `da10bd9`, commit, push `preserve/agent5-loop-continuity-20261009`. Then
port onto `44d815c`: scheduler `LOOP_CONTINUITY` (50 ms, max gap 1), `_recordFramePresentation`,
`getLoopContinuityReport`, distribution helpers; `worker.js` `frameSeq`. Keep keys
`avContinuity`, `frameSequence.gaps/repeats` (DEVICE-CHECK.md reads them); add
`avContinuity.basis: "transport-phase vs presented frame; no audio path in webcodecs-spike"`,
`audioMeasured: false`. Tests: `test_public_player_lifecycle.py` shape test (stubbed media);
real-media t7 case frame gaps ≤1 across two wraps. Also fix the declared cap:
`maxQueuedFramesPerView: 8` → 256 with comment (worker enforces `MAX_QUEUE = 256`).

### Lane H — TMB: Safari WebCodecs feature + sustained probe (G10)
Branch `feat/safari-webcodecs-lifecycle-probe`. New `tests/e2e/native_lifecycle_probe.py`
(sibling; `native_browser_probe.py` is digest-pinned `d03b89…` — do not edit). Args `--mode
feature|sustained --duration N --tier --source derivatives|fixture --output <private>`; timeout
= duration + 90 s; POST cap 2 MB or 5 s downsample; serves
`/webcodecs-spike/__lifecycle_probe.html` (index.html + injected driver, same dir for module
paths); `open -a Safari <url>`; keep tab frontmost (rAF throttling). Feature mode: page + Blob
worker existence of `VideoDecoder/VideoFrame/EncodedVideoChunk/OffscreenCanvas.transferToImageBitmap/createImageBitmap/importScripts`,
`isConfigSupported(avc1.640028)` at 768×384/1536×768/512×288/1024×576, `requestVideoFrameCallback`,
WebGL2, `AudioContext.prototype.setSinkId`; then run production `worker.js` on tracked
`synthetic-probe-fixture.mp4` and one derivative → `stream_ready` codec, ≥1 bitmap,
`released{decoderClosed, closedFrames}`. Sustained mode: 1 Hz samples of transport time,
`resourceReport()` (derived), measured workers/bitmaps/textures/stallCount/errors/framesDelivered,
`getLoopContinuityReport()`, `transportReset`, `frame_gap` events; `player.dispose()` →
`synchronizer_stopped`. Predicate: feature → worker-realm `VideoDecoder`, fixture decodes,
`decoderClosed`; sustained 600 s/tier → errors 0, no transportReset, transport ≥0.95× wall,
peaks within budget, post-dispose workers 0 / decodersClosed ≥4 / closedFrames >0. Receipt: new
keys `safari_webcodecs_feature`, `safari_webcodecs_sustained`, `native_lifecycle_probe_sha256`
in `DEVICE_ACCEPTANCE_RESULTS.json`; rewrite `limits[0]`. The 4 private clips cannot drive the
spike (single-tier 768×528; `SourceSelection` rejects) — derivatives only.

### Lane I — TMB: resource maxima + soak + loop continuity (G7b; after Lane G)
Branch `feat/n-generation-soak-harness`. `worker.js` frame messages gain `queueDepth`,
`decoder.decodeQueueSize`; new `NGenerationPlayer.measuredResources()` (workers, open decoders,
bitmaps held, max queue depth, textures, audio sources = 0 by construction) beside
`scheduler.observedMaxima`. New CLI `tests/e2e/soak_n_generation.py`: Playwright Chromium
`--use-gl=angle --use-angle=metal`, 1800 s wall-clock, 1 s in-page / 10 s harvest, `ps -o rss=`
over the browser process tree; Safari via Lane H `--mode sustained --duration 1800`. Loop
continuity: spike uses `frameSeq` (gap ≤1); A/V on `panoramic-generation-proof.html` with a new
`synchronized-generation-calibration/tools/build_marker_clip.py` (ffmpeg lavfi: two 8 s 24 fps
768×528 clips, burned frame number, white flash each 1 s, m4a click on flash) written to ignored
`media/marker/`, served at the clip URLs the page expects (page and private media untouched);
flash via `requestVideoFrameCallback` luma readback, click onset via AudioWorklet +
`getOutputTimestamp()`. Predicates: peaks within caps; no post-warm-up growth trend (memory slope
reported, ceiling set from first run); spike gap ≤1; proof page A/V ≤50 ms at every wrap.
Receipt: new `N_GENERATION_SOAK_RESULTS.json` {chromium_angle_metal, safari_27_2}; flip the
"not measured" row in `AGENT7_INTEGRATION_RECEIPT.md`; AudioBufferSourceNodes stay "no audio path".

### Lane J — TMB: live FOA output (G6)
Branch `feat/foa-live-output-harness`. Now: `tests/e2e/test_foa_live_context.py` — realtime
`AudioContext` (`--autoplay-policy=no-user-gesture-required`) → FOA decoder →
`MediaStreamAudioDestination` → AudioWorklet capture, offline reference rendered in-page;
predicate L RMS >5× R at yaw 0 mirrored at π, gain ratio 0.5 ±2%, live/offline RMS within 5%;
labelled "live graph, not device output". Gated on `L-TMB-LOOPBACK-AUDIO-DEVICE`:
`tests/e2e/foa_loopback_probe.py` — headed Chromium `--use-fake-ui-for-media-stream`,
`enumerateDevices` → "BlackHole 2ch", `ctx.setSinkId`, `getUserMedia` (EC/NS/AGC off, 2 ch);
predicate lateral >5×, gain 0.5 ±5%, channels not swapped, latency recorded. Safari only if Lane
H finds `setSinkId`. Receipt `FOA_LIVE_OUTPUT_RESULTS.json`. Matched archival pair stays Danse #69.

### Lane K — TMB: Ingress-resume tool (G9/G8 scaffold; runs the moment Ingress mounts)
Branch `feat/ingress-resume-tool`. New
`synchronized-generation-calibration/tools/ingress_resume.py` (`--dry-run`): (1) verify tree
(`SENSOR_ARCHIVE_ID` from `build_role_derivatives.py` + `2022FEB-F6/220218_012.WAV`,
`2022FEB-100GOPRO/GH010043.MP4`, `GH010044.MP4`) by size/duration vs tracked
`evidence/real-source-census.json` using `audit_ingress.probe_file` IMPORTED (the script
overwrites the census); never write to the volume; warn if writable. (2) hash chain via
`probe_sources.hashes()` → private ignored `media/ingress-hash-manifest.json` (full) + tracked
`evidence/ingress-hash-census.json` (collection, basename, size, duration, 16-hex sha256 prefix,
root hash over sorted `basename:size:sha256`); hash the 16 derivatives the same way. (3) run
`build_role_derivatives.py` (skips complete), then `git diff --exit-code
webcodecs-spike/source-manifest.json`; on byte drift stop and compare frame count/codec params
via ffprobe. (4) 100GOPRO coverage: print metadata verdict (ends ~16:18:51Z vs passage
~16:43:44Z) then the authority — `verify_alignment.decode_audio/onset_function/find_offset`
imported, `ADOPTED_CURRENT['offset']` set, decode to ignored `evidence/alignment-audio/`;
positive only if peak lands in F6 [510, 526] with margin → tracked
`evidence/hundred-gopro-coverage.json`. (5) print next commands (`pytest tests/e2e -q -rs`,
`verify_alignment.py --audio-dir … --decode`, `align_audio.py` with private `--output`/
`--evidence-output`). Test `tests/e2e/test_ingress_resume.py` on a `tmp_path` fake tree
(verification + deterministic root hash). First real run flips the "lineage unverified" row in
`PRESERVATION_REPAIR_RECEIPT.md`; `sensors=3` stays unless the onset match is positive.

### Lane L — limen: reap + currency (G12, G5) — last
G12: `python3 scripts/reclaim-worktrees.py --check --json`; if verdict is a standing grant
(`receipt-remote-merged+clean+idle` / `clean+merged+idle`) → `--apply --force`, no ledger row;
if `unpushed-commits` → `scripts/worktree-abandonment.py release --superproject
/Users/4jp/Workspace/limen --target …/av-second-device-custody-20261017 --expected-head
27b20b605b723893bb30446f429f62a1735313bd --remote-ref refs/pull/2904/head --apply` + a row in
`docs/worktree-reclaim-acceptance.jsonl` (keys root, path, action, reason, accepted,
accepted_at, acceptance_authority, archive_status, archive_proof, redaction_review,
redaction_proof) on a `docs/` branch. Then `python3 scripts/reap-branches.py --apply`
(`landed-pr-merged` = standing grant). G5: `bash scripts/sync-release.sh` (FF-only organ; never a
hand `pull`); if the organ changed in this batch, run the `origin/main` copy against
`$LIMEN_ROOT` per its bootstrap note (lines 30-47). Predicates: `sync-release.sh --check` 0;
`python3 scripts/check-live-checkout.py` → `drift=0`.

### Execution order and parallelism
**Authorized now:** A → B → C1 → C2 → L.
**Second authorization (TMB):** D → F → G → H ∥ J(live-context half) → I → K.
Limen lanes and TMB lanes are different repos and may interleave; the memory constraint caps
browser batches at one heavy lease at a time. Builds on sonnet, verification by a separate
`verifier` agent (haiku) per lane; this session plans and checks receipts.

**Finite-work and broker bounds (the prior session died here).** AGENTS.md: at most two
autonomous implementation tasks + one heavy workload at a time; 30-min attempt (≤10 min
verification); 120 cumulative agent-minutes per approved outcome; one corrective retry only
after inputs change. Peer Conductor Contract: reserve a child before any mutating subagent.
Rules for packets: one root packet per lane with a FRESH work key (the old key is
immutable-rejected), `spend.limit` strictly greater than the sum of child `reserve`s (Codex's
`limit 6 / reserve 6` left zero for children → "aggregate child spend exceeds parent
envelope"), builder children split from that root via `limen conduct split`. Before writing the
first packet: `rg -n "aggregate child spend" web/worker/src cli/src/limen/conduct` to read the
exact rule. Reuse `av-root-packet.json` / `av-standing-packet.json` in custody staging as the
shape. Before Lane G reads the main checkout, confirm no live lease claims it
(`host-work-admission.py status --no-probe`). Each lane is one capsule; the owner authorizes
how many capsules run now (asked below).

### What stays human-gated after everything above lands (each filed as a lever in Lane B)
1. (Deferred by decision) history purge — `L-TMB-HISTORY-REMOVAL` holds the recipe.
2. Retire the plaintext custody copies (same lever).
3. Mount Ingress + a custody disk (`L-TMB-INGRESS-SOURCE-MOUNT`).
4. Approve 100GOPRO as view 4 or schedule a capture (`L-TMB-FOURTH-CAMERA`, Danse #69).
5. Phone + headset + capture-hardware sessions (`L-TMB-DEVICE-ACCEPTANCE`).
6. Install BlackHole 2ch (`L-TMB-LOOPBACK-AUDIO-DEVICE`).

## Verification

- Every limen lane: `scripts/verify-scoped.sh` bare exit 0 on the final tree; named gates above
  green; PR merged with `--match-head-commit`; receipt path exists on `origin/main`.
- Lane B: `scripts/check-his-hand.py --check` and `scripts/lever-classify.py --check` exit 0;
  every `L-TMB-*` id cited anywhere resolves (`no-tasks-on-me.sh` §8).
- Lane C: `sealed-custody.py verify --key-less` exit 0 on both replicas; `restore` exit 0 on
  both with `ARCA_KEY_SOURCE=op` (proves escrow); receipt validates via `CustodyReceiptV1`.
- Lane E: `check-sensitive-history-removal.py preflight --packet …` exit 0 BEFORE the lever is
  handed to the human; postflight exit 0 + receipt merged AFTER.
- TMB lanes: the named pytest/node predicates bare exit 0 at the exact head recorded in the
  receipt; `DEVICE_ACCEPTANCE_RESULTS.json` / `N_GENERATION_SOAK_RESULTS.json` /
  `FOA_LIVE_OUTPUT_RESULTS.json` carry head SHA, admission lease, and limits honestly.
- Lane K: `pytest tests/e2e/test_ingress_resume.py` green; `ingress_resume.py --dry-run` on the
  absent volume reports exactly the lever to pull.
- Closeout: `scripts/no-tasks-on-me.sh --session-id ID --worktree PATH --receipt RECEIPT --json`
  bare exit 0 twice (idempotent); `check-live-checkout.py` drift=0.
- Status words reported separately per lane: merged / live / observed.
