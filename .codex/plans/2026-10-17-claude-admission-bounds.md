# Claude admission input bounds

Owner: Limen native Claude host-admission source; direct human hook-estate repair.

1. Reconcile existing Codex repair owner PR #2900 rather than duplicate it.
2. Bound Claude stdin to 1 MiB and total evaluation to eight seconds; reject malformed,
   wrong-event, or unevaluated requests with the existing structured denial channel.
3. Exercise malformed/oversize input, held-open stdin, evaluation failure, ordinary
   successful evaluation, and existing provider process ownership tests.
4. Push this isolated branch and open a draft PR; no runtime deployment or trust edits.

Retention: isolated external checkout retained until root session custody closeout.
Domus owns mandatory native onFailure:block adapter wiring and deployment.
