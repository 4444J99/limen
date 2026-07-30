# VLTA / VLTIMA — Ground-Truth Excavation Map

**Date:** 2026-06-25
**Method:** Workflow `vlta-excavation` (run `wf_63bfb0b1-96f`) — 6 read-only parallel readers across transcripts, daemon/runtime, repos, branches/PRs, levers/ideal-forms, and corpus; 1 synthesizer that re-verified disputed claims with live `git`/`gh` during synthesis. Strictly read-only.
**Frame:** the organism described across three tenses — PAST (the sediment), PRESENT (what is alive and conducting), FUTURE (the buried, un-amalgamated portals).

---

## The one-sentence verdict

**The organism breathes; it does not yet earn.** Three launchd daemons are confirmed alive, the fleet conducts and self-heals without a human, 181 of 264 `organvm` repos were pushed this week — and after all of it, **tx-hash is still 0.** Every revenue product is code-complete; not one dollar has arrived. The hydra grows heads (157 unmerged branches, 75 open PRs in `limen` alone) faster than it amalgamates them.

The myth is load-bearing in **two of three tenses**. Past and present are real, alive, verifiable. The future tense — "portals amalgamated into one" — is almost entirely *buried, not merged*. Not a flaw in the vision; the exact cliff the doctrine already names (`close-is-the-cliff`), now measured as fact.

---

## PAST — the sediment ✓ real

- **The corpus is converged.** `knowledge-corpus/00-THE-ONE.md` — an 80-line ideal-form re-distilled 2026-06-25, collapsing 13 faces (1,980 lines in `reduced/`). Passed a 3-pass critic on 2026-06-19 (`03-critic.md`).
- **~100 memory doctrine files** (~4,815 lines) encode the north star, the VLTIMA prosthesis frame, ~7 hard invariants.
- **700 `.jsonl` transcripts across 547 project dirs.** VLTIMA appears in **130**; the FLAME continuity kernel is prepended to 96+ dispatched sessions — the self-description is literally the context every lane runs inside. The hydra reads its own myth before it acts.
- **Recurring in the sediment:** the payment-rail cliff, the durability sliver, the TPD discharge — and the user's own voice (`squishy-humming-biscuit`: *"im tired… ive asked for 1,000,000 things"*).
- **Frontier still open:** the `converge()` organ is built but **unmerged (PR #35)**; the durability sliver is in 2 local copies, **0 offsite** — a self-declared Core Rule violation, one B2 command away.

## PRESENT — what is alive ✓

Daemon **running, verified**: `com.limen.heartbeat` PID 27748, logs fresh to 14:08. `heartbeat-loop.sh` is the polyrhythmic conductor — 8 voices. The self-* ladder is materially wired:

| Rung | Organ | State |
|------|-------|-------|
| sustain | heartbeat-loop · watchdog · creds-hydrate | LIVE (launchd) |
| route → feed → merge | route · dispatch-async · auto-scale · merge-drain/policy | LIVE |
| converge → heal → improve | corpus-converge · self-heal · quicken · self-improve | LIVE |

Supporting institutions live: CENSOR, the Executive Health Office, proprioception (`organ-health.py`), `omni-view`. Web stack on Cloud Run + Firebase + Cloudflare.

**Caveats:** the organa are mostly empty shells — of the seven (`organvm-i…vii`), only **I-Theoria** and **III-Ergon** have local working surfaces; **II, IV, V, VI, VII are `.github`-only stubs** locally (all pushed remotely within 6 days). `heartbeat` showed `LastExitStatus=-9` (SIGKILL) even while alive — mid-cycle or killed-and-restarting.

## FUTURE — the buried portals ✗ (the heart of the ask)

**institutio / VIGILIA mystery — resolved:** VIGILIA **is merged and live on `origin/main`** (`git ls-tree origin/main` returns `institutio`). It only *looks* absent because **the live local checkout is 15 commits behind its own trunk** (`rev-list origin/main...HEAD` = 15 / 6). The daemon may be running 15-commits-stale code. Cheapest fix: fast-forward the live checkout — blocked in-session by SSH-key denial.

Buried inventory:

| Group | Count | Cheapest path to amalgamation |
|-------|-------|------------------------------|
| Open PRs (limen) | 75 (2 mergeable: #273, #274) | merge sweep; #270+#271 merged mid-excavation |
| Unmerged branches | 157 (70 are `gen-*` dup docs) | merge `heal/ci-ruff-semicolons` **first** — unjams CI backlog |
| Stranded worktrees | 21 | reap or finish (browser-vault stuck ~57%) |
| His-hand levers | **exactly 12** (not 811 — reader misread; corrected live) | the user's — see below |
| Dormant fleet repos | 64 (>30d) | triage; `etceter4` 122d, ORGAN-I landing stalled |
| Cross-repo product PRs | mirror-mirror 5–15, universal-mail 11, +27 dependabot | merge |

**Notably absent:** there is **no ideal-forms ledger for the limen fleet** — the only one (`sovereign-systems/docs/IDEAL-FORMS-LEDGER.md`) tracks the Maddie project exclusively. Claude's own ideas for the organism are tracked nowhere as named params. The "portals each attempting their own ideal" have no registry.

---

## The 12 his-hand levers (the user's exclusive lane)

Top three are the whole game:

1. **L-REVENUE-ACCT** — create Ko-fi/Sponsors + Lemon Squeezy, paste `LEMONSQUEEZY_STORE_ID` → **first dollar on the Exporter (~10 min).**
2. **L-MERGE-GATE** — say *"open the merge gate"* → squash-merges ~20 clean PRs.
3. **L-CLOUDFLARE-DEPLOY** — `wrangler login` → unlocks 16 deploy tasks (~2 min).

Then: L-GMAIL-CRED, L-ENC1101-GOLIVE (one-click D2L go-live 771624), + 7 more. **One lever is stale** — L-FLEET-CAPACITY still lists `gh` as a re-mint step though gh was closed in-lane (#251); one-line edit to clean up.

## Conflicts & gaps (honesty)

- **Resolved live:** lever count (12, not 811); institutio location (merged, checkout-lagged); PR state (#270/#271 merged since packet-time).
- **Still unverified:** 73 PRs show `UNKNOWN` mergeability (GitHub hasn't recomputed); the 15-commit fast-forward could not be *executed* (SSH denied); the "insights infrastructure" the user once asked *"where the fuck is it?"* about remains **un-located** — a candidate buried organ for the next dig.

---

## The reckoning, and the single act

The hydra proliferates faster than it is rideable. Prose substitutes for the predicate in exactly one place — the close. The autonomic fleet has perfected building heads and has **never once closed a sale**, because the last 10% (a Ko-fi slug literally reading `TODO_KO_FI_SLUG`, a store ID, a `wrangler login`) is the one thing it structurally *cannot* do for itself.

**The single highest-leverage act toward Aug-1 is `L-REVENUE-ACCT`.** ~10 minutes of human hands turns the only deploy-ready product (ChatGPT Exporter, `a-i-chat--exporter/`) from plumbed-but-shut into the first dollar. Everything Claude owns there is done. That is the cliff's edge — a human step, not a code problem.

**Second-order, Claude-ownable once a remote auth works:** fast-forward the live `main` 15 commits, merge `heal/ci-ruff-semicolons`, then run the merge gate.
