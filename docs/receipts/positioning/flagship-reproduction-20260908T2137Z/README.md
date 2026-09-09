# Dated flagship reproduction — 2026-09-08 21:37 UTC

Continuation of PSP-P05-W04 / [#2201](https://github.com/4444J99/limen/issues/2201), owned by the existing R01 Codex lane. This appendix preserves a new execution observation. The earlier [16:57 observation](../flagship-freshness-20260908/README.md) remains unchanged. No PSP completion receipt or lifecycle transition is asserted.

## What executed

The public-records flagship was checked out at `04eb20eeba2391a053c4a129f0090f5295c1460e` in a real linked Git worktree. The repository ID is `1083287130`. Tracked source was clean after the run. The owning `.github/workflows/ci-gate.yml` correctness commands were run under an authentic scoped host lease and the machine-wide heavy lease, using Node 20 and npm 11.17.0 package selections. Dependency installation used `npm ci --ignore-scripts` and exited 0.

The accepted Limen runner `scripts/positioning-flagship-receipt.py` at `ac351ed163e83aba37e549fe1954cffa38b1c2a3` checked each requested exact head, executed each command with a finite timeout, and recorded its own exit code, UTC timestamps and combined-output digest.

| Predicate | Actual exit | Observation |
| --- | --- | --- |
| Server Vitest correctness suite | 0 | 1,504 passed, 6 skipped, 93 test files |
| Repository lint | 0 | Completed |
| Render build | 0 | Completed |

The unmodified JSON reporter output is compressed in `ucc-tests.json.gz`; its decompressed SHA-256 and per-file results are in `ucc-test-summary.json`. The v1 runner retains combined stdout/stderr digests, not raw predicate output. Those output bodies cannot be reconstructed from their hashes. The separately retained test report and install log are additional evidence, with their own digest manifest.

## Claim boundaries

This is one fresh exact-head set of bounded predicate successes among the three selected flagships. It is not an accepted PSP work receipt or a full product-reproduction claim. Server coverage enforcement was explicitly disabled by the owning workflow: no coverage percentage is asserted. Six tests were skipped. No database, Redis, live scraper, deployment, client data, payment, consent or end-user journey was exercised. The build uses `tsc --noCheck`; it does not prove TypeScript diagnostics pass. Existing typecheck correction PR #402 remains with its existing owner.

The AI exporter was checked out at `900da0fa256b443b3fe976963c9b2c67e8c09176`. Its declared pnpm 8.14.1 frozen installation began and reported the lockfile current, but no terminal result was retained and no downstream predicate began. The attached partial log is not an installation success or failed-test receipt. Its status remains `not_current`.

Limen accepted main has no new complete reproduction in this observation and remains `not_current`. The separately preserved R00 candidate verification has unresolved failures; it is not accepted-main proof.

Formal W04 acceptance still requires canonical dependency and receipt adjudication. The dated 35/111 stored-receipt baseline is not recomputed by this appendix. No external outcome or publication authority is created.
