# Close the front-door verification gaps

Issue: #3012
PR: (pending)

## Context

On 2026-10-18 the closeout of #2978 (recurrence measure), #2979 (second copy of the raw AI exports) and #2980 (the `limen knowledge` front door) was verified against live state, read-only. The merged work is sound and observed working. From the `origin/main` tree the recurrence tests and ledger convergence pass (88 tests, `prompt-atom-ledger: PASS`), `check-knowledge-alive.py` is ALIVE on the real archive (`--live` ALIVE `cd674db6f3d1cab3`, `--fixture` ALIVE `4641d7b9a0a3f632`), and the server on 127.0.0.1:8472 is a pid-bound `cce archive serve` that rejects a foreign Host header with 403 and answers `/api/search` across all six providers.

The verification also found the work is not complete:

- `limen knowledge` is merged but not live. The installed runtime is pinned at `80efee81`, 26 commits behind `main`, and its `cli.py` has no `knowledge` verb.
- `scripts/open-knowledge.sh` has one real defect (`--stop` and `--status` exit 2 once the manifest is gone) and five lower-weight ones. All were reproduced against a throwaway fixture. The tests never run `--stop` or `--status` without a manifest, which is why this slipped through.
- `docs/architecture/ai-exports-archive.md` is stale (the second copy is described as never run), lists five providers where the archive has six, and uses undefined shell variables in its command blocks.
- Two CI findings were unfiled: #3008 (`check-knowledge-alive` runs inline in `pr-gate` where no engine exists) and #3009 (`ops-owner-release.yml` failing 300 of 300 recent runs).
- The Copilot sources (29 files, 42 MB) are single-copy, ingested only as opaque blobs, and absent from the normalized archive (#3010).

## Resolved design decisions

1. **The server-control verbs never depend on the archive being built.** `--stop` and `--status` need only the registry-derived store and state directory; only the start path demands the manifest. A server must stay stoppable when its archive volume is offline. Binds in `scripts/open-knowledge.sh`, pinned by new cases in `cli/tests/test_limen_knowledge_verb.py` that run both verbs with no manifest and fail on the parent commit.
2. **Identity is protocol, not status code.** A listener is reused only when `/api/ping` answers the engine's `{"ok": true}` (the contract the site's own JavaScript uses to enable full-text search), and a recorded pid is trusted only when its command line names `archive serve` and this port. A foreign HTTP 200 on the port is refused by name and never opened as the archive. Binds in `scripts/open-knowledge.sh` and `cli/tests/test_limen_knowledge_verb.py`.
3. **Start is serialized per port, and a failed start reaps its own child.** A lock directory under the store's `state/` makes concurrent starts converge on one engine process; a dead holder is recovered; a start that times out kills its child and removes its pid file. Binds in `scripts/open-knowledge.sh` and `cli/tests/test_limen_knowledge_verb.py`.
4. **`--status` binds the receipt to the live fingerprint.** The alive receipt carries the first 16 hex of `sha256(source_fingerprint)`. Status reports the newest receipt for that fingerprint and says "stale" when only older ones exist. Binds in `scripts/open-knowledge.sh` and `cli/tests/test_limen_knowledge_verb.py`.
5. **Copilot sources are preserved in place and receipted by content hash only.** No move, no rewrite, no titles in tracked files. The receipt's manifest is the sorted list of per-file SHA-256 values, so any future copy can be verified without the names. The second copy waits on `L-UNIVERSE-RECOVERY-CUSTODY-VOLUMES` (T7Recovery), which is already filed and is not re-filed. Binds in `L-UNIVERSE-RECOVERY-CUSTODY-VOLUMES`.
6. **The installed runtime moves only through its owning installer.** `domus-limen-runtime install --sha <merged SHA>`, then `scripts/check-runtime-lag.py` must exit 0 (bound: 25 commits) and `limen knowledge` must answer through the installed CLI. A skipped or unmeasured check is reported as such and never counted green. Binds in `scripts/check-runtime-lag.py`.
7. **CI findings are filed, not patched here.** #3008 and #3009 carry evidence, options and a predicate, and belong to the gates-registry and ops-workflow owners. owed: #3008 and #3009 until their owners ship the fix.
8. **The team is declared, and its limit is stated.** The session is registered as a protected direct Claude session with the Claude lane bearer (principal `claude-direct`) so the fanout is not hidden. The individual native children are not broker leases: claiming and reporting need the executor credential, which must not meet the conductor credential in one process, and the registration hook for background jobs is still in flight. owed: #3000 (PR #3002) until background Claude jobs register through the hook.

## Team

Builders work in isolated worktrees, commit locally and never push: B1 script and tests, B2 documentation, B3 preservation receipt. Verifiers are read-only: V1 A/B against the parent commit, V2 shell safety and bash 3.2 compatibility, V3 concurrency soak, V4 documentation claims against ground truth, V5 receipt recomputation and privacy scan. A completeness critic closes the phase. Pushes, PRs, merges and the runtime rotation stay with the conductor.

## Steps

1. File the findings (#3008, #3009, #3010) and this tracking issue; persist this plan.
2. Build B1, B2 and B3 in parallel worktrees.
3. Verify each result adversarially and fix what the verifiers find, in at most two rounds.
4. Run `scripts/verify-scoped.sh` once per final tree, push, and merge by the lane's rule.
5. Rotate the runtime at the merged front-door SHA and verify `limen knowledge` through the installed CLI.
6. Close out with a receipt that carries the runtime evidence.

## Premortem

- **The `/api/ping` contract changes in the engine.** The script would report the server down while it is up and refuse a port it owns. The site's own JavaScript depends on the same endpoint and a test pins the contract, so the engine owner changes both together.
- **The heavy gate dominates wall time.** Only the script PR implicates `pytest-cli` and `pytest-api` (roughly 24 minutes, one at a time machine-wide). The documentation and receipt PRs run cheap gates only.
- **A lock can wedge a start.** A dead holder is recovered, the lock is a directory removed by a trap, and a test kills a holder mid-start.
- **The documentation describes behavior the script PR has not merged.** The documentation PR merges after the script PR, and a verifier checks every claim against the merged script.
- **The session predicate may stay unmeasured** (#3004). Then closeout is not claimed and the blocker is reported with its owner.

## Verification

- `bash scripts/verify-scoped.sh` on each final tree (it names every gate it skips).
- New tests fail on the parent commit and pass on the fix: A/B against `<sha>^`, asserting the marker is absent from the baseline.
- `python3 scripts/check-plan-decisions.py --check` and `python3 scripts/check-session-phase.py`.
- Installed runtime: `readlink ~/.local/share/limen/current`, `python3 scripts/check-runtime-lag.py` (exit 0), and `~/.local/bin/limen knowledge --status`.
