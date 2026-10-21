# Recovery commands and acceptance boundary

The host hook rejected both local scratch staging and the source script dry-run.
The source script is preserved in Domus draft #490. It has not been run. Its apply
mode corrects the one known fixture reason and runs focused tests; it does not
finish six-client wiring, deploy files or establish native enforcement.

After the existing admission owner resolves the scope rejection, review and run:

```sh
python3 /Volumes/Archive4T/domus-dynamic-routing-20261017-cf1c/scripts/model-routing-recover-20261017-cf1c.py --dry-run
python3 /Volumes/Archive4T/domus-dynamic-routing-20261017-cf1c/scripts/model-routing-recover-20261017-cf1c.py --apply
```

The script runs Limen's dynamic/provider selection tests and Domus's adapter,
policy, liveness and hook-evidence tests. Both bare exits must be zero before
those focused checks can be claimed. The final scoped gates still need their
own host admission. Preserve any generated recovery receipt and publish through
the current draft's PR rail; no cleanup or native trust changes are included.

The canonical closeout command remains bound to native caller home and both
scope roots in session-closeout.json. Its first attempted execution was rejected
before a process started. Do not invent an exit code or repeat an unchanged host
rejection. Custody/release is explicitly unverified; the terminal completion
statement is forbidden until the real session predicate passes twice without
new effects.
