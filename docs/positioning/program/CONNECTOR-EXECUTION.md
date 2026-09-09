# Execute PSP receipt verification from ChatGPT

Owner: PSP controller / #2157, runtime delivery / #320.

An authenticated GitHub connector is a supported read transport. The controller's
`--github-transport connector` option performs the same manifest, receipt,
quarantine, timestamp, digest and exact-source checks as the default `gh` path.
It exchanges one live REST GET at a time with the native host. It never reads a
saved observation bundle as live state and does not extract connector credentials.

In a ChatGPT code-mode host, load the inspected version of
`scripts/positioning-connector-driver.js` and call
`verifyPositioningWithConnector(tools, absoluteRepositoryRoot, "PSP-P11-W03")`.
The helper invokes the real Python CLI, services each request with the installed
GitHub connector, and returns the command's actual exit code, output and bounded
observation URLs/timestamps. It requires `exec_command`, `write_stdin` and
`mcp__codex_apps__github_fetch`. Use an inspected checkout with its normal Python
dependencies. This is an explicit transport, not a binary named `gh` or a mocked
validator.

The underlying invocation is:

```bash
python3 scripts/positioning-program.py --verify-work PSP-P11-W03 --github-transport connector
```

The host uses a PTY because some remote executors otherwise close stdin. The
transport disables terminal echo and canonical line truncation before receiving
JSON, and restores terminal settings on exit. Each response must match a fresh
request ID, GET method, schema and exact URL. EOF, timeout, oversize, malformed
JSON, unsupported endpoints, connector errors and correlation mismatch fail
closed. Requests are read-only; `--apply` is refused before any mutation. Raw
response bodies remain in the authenticated execution exchange, never in the
returned observation summary. Do not log private response bodies or tokens.

After a successful `--verify-work`, use the existing PSP issue-closeout sequence
in [README.md](README.md): link the real output and receipt, then close the mapped
GitHub issue through the connector. Re-read its state. That projection operation
does not assert a TABVLARIVS task transition. If an actual canonical task/lease
also needs transition, it still goes through the existing broker. Do not invent
a task mapping or add a broker prerequisite to an ordinary PSP issue closeout.

The September 9 failure was transport coupling plus conflation of these two
operations. An absent local `gh` binary is no longer grounds to stop PSP receipt
verification when the installed connector can read the required repositories.
This correction supplies execution capability; it grants no publication,
participant, identity, or autonomous-observation evidence.
