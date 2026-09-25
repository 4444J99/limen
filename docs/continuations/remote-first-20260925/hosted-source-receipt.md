# Recovery source: hosted execution receipt

Observed 2026-09-25. Owner: https://github.com/4444J99/limen/issues/2745 (E1, program #2739).

## Verified facts

- Live GitHub repository identity: 1255213941, 4444J99/limen.
- Fresh git ls-remote: docs/heartbeat-natural-receipt-20260924 points to cd287e5893b70e59f52894f58e7ce978030ac8b4.
- Hosted run: https://github.com/4444J99/limen/actions/runs/36172147213 ; event pull_request, head SHA cd287e5893b70e59f52894f58e7ce978030ac8b4; conclusion success.
- Job: https://github.com/4444J99/limen/actions/runs/36172147213/job/108194540145 ; GitHub-hosted ubuntu-latest, runner ID 1000039443, started 2026-09-25T18:15:55Z, completed 2026-09-25T18:34:00Z; conclusion success.
- Checkout log identifies merge tree eb78288c5271249bb338dbaeaf821d22403862dc, whose API-verified parents are 057e05fed1df6a9215cb3bcb0ead08d84d944d70 and cd287e5893b70e59f52894f58e7ce978030ac8b4. This is a merge-tree receipt, not an assertion that the literal candidate commit was checked out alone.
- GitHub compare reports 15 changed files between candidate and tested merge tree. The named repo lifecycle, clone reaper and tool-cache implementation/test files are not among those differences.
- The hosted job installed the revision's declared Python dependencies and executed python scripts/verify.py --changed. The actual selected CLI suite returned 8193 passed, 4 skipped, 4 warnings and 8 subtests passed in 877.61 seconds. The API suite returned 52 passed in 8.88 seconds. Both runner gate records are PASS and the job completed successfully.
- The hosted filesystem and interpreter were the GitHub runner's own checkout and Python 3.12.14 environment; the job was not a self-hosted laptop execution.

## Acceptance scope

This proves published recovery source can be acquired and meaningfully verified on an independent hosted executor. Existing exact-input evidence was reused; no duplicate heavy suite or new provider run was launched.

It does not prove all local refs/stashes/ignored files/private metadata are preserved, the draft is merged or installed, a source checkout is eligible for removal, or ChatGPT/Muse/Grok/Jules autonomous access works. Local ARCA file-object edits are outside this candidate and remain untouched. Four skipped CLI cases remain explicitly skipped; this is not a claim of exhaustive estate verification.

The cloud source/verification part of E1.1 has a positive receipt. E1 and the overall program remain open. Next: take one smallest preservation gap and attach a repository-specific remote work packet; provider implementation admission requires its own live capability/deadline evidence.
