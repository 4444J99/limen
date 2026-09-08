# Personal relay merge enforcement

Status: implemented for review; **activation remains blocked**. The relay stays at
`4444J99/organvm-ci-relay` (repository ID `1350979676`) on the personal runner plane.
This extends `merge-drain.py`; it is not another scheduler or task authority.

## Authority and freshness

`Relay trust policy` and PR #30's asynchronous `Relay admission / trusted` are
diagnostics under this architecture. Neither is the merge authorization. The
unclosed webhook-delivery race in PR #30 is not repaired by another final GET.

The deployed governor runs `_relay_merge.py` under its existing work packet and
exclusive `repo/4444J99/organvm-ci-relay/write` resource claim. TABVLARIVS retains
lease, budget, custody, and receipt authority. This adapter does not issue leases
or replace that keeper. Its dedicated installation credential exists only in
the trusted governor deployment, never in an ordinary agent process, candidate
checkout, relay Actions secret, webhook service, or reusable workflow.

The adapter reads active enforcement, captures base B, candidate H and GitHub's
test merge M, and verifies M's ordered parents are exactly `[B,H]`. It creates
`Relay merge / governor` on **M only**, synchronously evaluates the candidate, then
rechecks settings and the tuple before issuing one exact-head squash merge. It
requires positive merged readback and consumes the check even on an ambiguous
response. Every attempt evaluates again; no existing check is accepted as an
evaluation receipt. Standalone `merge-policy.sh` callers always HOLD this repo,
including release helpers. The drain cannot fall back to its generic merge path.

Evaluation executes the four audited Bash bodies from the pinned relay policy
workflow, with a separate read-only token and clean HOME/environment. Current
base executable roots must match the audited deployment commit. The candidate
is fetched as data; the existing regular-blob, frozen-root, registry identity,
operational SHA, policy and regression predicates all execute. No candidate
script or action runs. Updating the policy deployment pin requires a separately
reviewed trust-root promotion; main movement that preserves those roots does not.

A same-SHA Actions rerun or delayed webhook cannot authorize or revoke this
separate synchronous evaluation. The contract is evaluation of immutable B/H
under the deployed policy, with live external identities observed during that
evaluation. It does not promise an atomic snapshot of every external repository.
Ordinary workflow reruns are diagnostics, not revocation commands. Emergency
revocation belongs to the governor pause and repository administration boundary.

GitHub's required-check semantics are the server-side base fence: a new B has a
different M and no governor pass; there is never a governor pass on H to satisfy
head fallback. Head races are additionally fenced by the merge API's `sha`.
This depends on live GitHub enforcement, not the last GET being atomic. The
post-read base-race canary below is mandatory before activation. A failed canary
keeps the lane disabled and returns the design to engineering; it is not waived.

## Concrete administrator configuration

Create/install a **distinct dedicated governor GitHub App**, selected repository
only: Metadata read, Contents write, Pull requests write, Checks write,
Administration read. It needs no Administration write and no Actions write.
Do not reuse `github-actions` (15368), the webhook admission App, a broad PAT, or
an App credential available to candidate execution. Use short-lived installation
tokens supplied by the existing trusted credential broker. The separate evaluator
token has Contents/Metadata read only; it must not be the governor token.

Deploy the reviewed adapter in the existing governor's trusted execution surface
with Python/PyYAML, Bash >=4, Git, curl and the relay's qualified Node runtime.
Keep the scheduler's existing lease/host-admission controls. Configure
`LIMEN_RELAY_GOVERNOR_APP_ID`, `LIMEN_RELAY_UPDATE_RULESET_ID`,
`LIMEN_RELAY_POLICY_SHA`, `LIMEN_RELAY_GOVERNOR_TOKEN` and
`LIMEN_RELAY_READ_TOKEN` through that private deployment. Never distribute the
governor credential through fleet-wide hydration. There is no new public server.

Render reviewed API bodies with:

```bash
python3 scripts/_relay_merge.py --render-config GOVERNOR_APP_ID
```

The two returned objects go to `PUT /repos/4444J99/organvm-ci-relay/branches/main/protection`
and `POST /repos/4444J99/organvm-ci-relay/rulesets` respectively. Read first and
preserve stricter unrelated protection. The newly required context replaces the
asynchronous admission context as merge authority; do not blindly apply PR #30's
older standalone branch-protection recipe.

The update-only ruleset has exactly one exemption: the dedicated governor App,
**pull_request** mode. The separate branch protection has no corresponding
exemption: strict App-bound checks, enforced for administrators, one fresh
independent approval, last-push approval, code-owner review, conversations,
linear history, no force pushes or deletion. Define reviewed CODEOWNERS if that
ownership control is intended to add protection; its flag alone creates no owner.
Never put checks or review rules inside the exempted update ruleset. Never grant
an `always`, administrator-role, team or user update exemption.

The adapter reads both controls on every attempt and refuses missing credentials,
403s, malformed responses, absent rules, broad exemptions and shared App IDs.
It also rejects queued/auto-merge PRs. The GitHub setting boundary excludes direct
UI/API merges and direct pushes by ordinary users/tokens; a script convention
alone does not. A repository administrator can still change the rules themselves
and remains part of the explicit trusted computing base.

Submit through the existing governor, once, after review:

```bash
python3 scripts/merge-drain.py --repo 4444J99/organvm-ci-relay --pr NUMBER --expected-head SHA
```

Missing deployment fails closed. An ambiguous merge or failed cleanup retains
custody: read the exact PR/head and merge receipt before any new attempt. A
consumed authorization appears failed on the old synthetic commit by design;
the drain's relay route does not reuse rollup state.

## Adversarial acceptance

Unit fixtures are not protected-merge evidence. Run these only after the App and
both independent controls have verified live readback. Use disposable PRs and
approved harmless control changes; never merge a malicious candidate. Record
repository ID, base/head/test-merge SHAs, App ID, check ID, caller identity,
settings JSON, HTTP result and positive PR/main readback. No credential values.

| Canary | Required result |
| --- | --- |
| Healthy candidate through governor | Synchronous predicates pass, one merge, positive landed SHA; authorization consumed |
| Passing duplicate `Relay trust policy` from Actions | Cannot authorize governor; invalid candidate remains unmerged |
| Forged `Relay merge / governor` on H or M from Actions | Wrong producer cannot satisfy required App binding |
| Arbitrary-head spoof from a rejected same-repo branch | Other candidate remains blocked without its own governor evaluation |
| Delayed webhook / same-SHA rerun, including a failing rerun | No new governor authorization; failed synchronous evaluation never calls merge |
| H changes during evaluation or after final read | No merge of unexpected head |
| B changes during evaluation | Adapter rejects stale tuple |
| B changes after final read / success, before merge | GitHub rejects stale-M authorization; no head-check fallback |
| Old success, process crash, failed next evaluation | Next attempt evaluates again and cannot merge on historical success |
| Direct user/PAT/Actions UI/API merge and direct push | Server rejects outside dedicated governor PR route |
| Dedicated governor direct push | Server rejects: exemption is PR-only |
| Disabled rule, broad bypass, shared App, missing approval, unreadable settings | HOLD or server rejection; no merge |
| Wrong live target ID / missing operational SHA | Trusted synchronous evaluation fails (historical #27/#28 fixtures) |

Current evidence (2026-09-08): relay main remains `6766fcc70f0c383ca2ddf70e7d6da0cbec7eeafa`,
`protected:false`, rulesets `[]`. The managed integration returns 403 on branch
protection reads and exposes no administration writes, App installation or
trusted governor deployment surface. Those boundaries prevent live activation
and protected canaries in this session. Relay issue #3 owns the activation record.

Sources: [GitHub required-check source and test-merge semantics](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks),
[ruleset API and PR-only exemptions](https://docs.github.com/en/rest/repos/rules).

Verification boundary: 14 adversarial transaction tests and 43 merge-policy
cases passed. The two new Python sources passed focused Ruff checks (the remote
controller entry is executable). The local writer admission attempt refused
`lease owner PID/start identity is unavailable`; no synthetic PID or admission
bypass was supplied. Full scoped verification and trusted deployment remain
unaccepted. This source is a draft, not an activated security boundary.

The scoped preparation batch also passed the existing merge-queue contracts
(108 Python cases), but its whole verdict was FAIL. Its three new registration
findings (test note, parameter declarations, read-only main-ref classification)
are corrected in this draft. Existing historical-object/public-live predicates
and the snapshot's tracked-root census prevented a complete local verdict; no
full-tree acceptance is claimed. The normal remote gates must assess this exact
published tree before promotion.
