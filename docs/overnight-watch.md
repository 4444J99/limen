# Overnight Watch

Use `scripts/overnight-watch.py` for overnight proof. Do not keep any
interactive agent turn attached just to poll heartbeat output.

Default mode is one-shot:

```bash
python3 scripts/overnight-watch.py
```

The entrypoint resolves its root from explicit `LIMEN_ROOT`, otherwise from the
checkout that owns the invoked script. Before a normal sample, attached
`--watch` sample, or `--start-trial`, it checks that root's
`logs/AUTONOMY_PAUSED`. When the marker is present, the process writes one
counts-only `blocked` receipt with zero probes and exits successfully; it does
not inspect the board/corpus, heal services, append a trial observation, or
enter/continue the attached loop. The only bypass is the existing governed
escape hatch, `LIMEN_FORCE_AUTONOMY=1`; the watcher defines no separate pause
override. Explicit `--finalize-trial` and read-only `--check-trial` remain
available while paused so an operator can close or inspect existing custody.

It writes:

- `logs/overnight-watch.jsonl` append-only receipts
- `logs/overnight-watch-state.json` repeated-tick state
- `logs/overnight-watch.md` latest human-readable status
- `logs/overnight-watch-alert.json` only when a `WATCH_ALERT` is active

Recommended supervisor cadence is a cheap one-shot invocation every five
minutes. The script exits non-zero only when it has concrete evidence of a
blocker, such as a missing heartbeat log, stale heartbeat log, repeated latest
tick with no active workers, or optional dispatch-env drift.

The repo includes a launchd job for that cadence:

```bash
cp container/launchd/com.limen.overnight-watch.plist \
  "$HOME/Library/LaunchAgents/com.limen.overnight-watch.plist"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.limen.overnight-watch.plist"
```

For the overnight fleet profile, run with explicit expectations:

```bash
LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_ASYNC=1 \
LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_LANES=auto \
python3 scripts/overnight-watch.py
```

`--watch` exists for a local terminal, but it is not the interactive-agent
pattern. Agents should inspect the receipt or respond to `WATCH_ALERT`; they
should not spend a large conversation context on routine five-minute polling.

## Eight-hour unattended trial

Start the fixed contract once; the normal five-minute one-shot producer will
finalize it automatically after eight hours:

```bash
python3 scripts/overnight-watch.py --start-trial
```

The active window is recorded in `logs/overnight-trial-window.json`. It seals the
existing byte prefixes of the ordinary watch log and the dedicated
`logs/overnight-trial-observations.jsonl` chain, plus every task-event ID already
present. An exclusive content-addressed anchor records the marker's actual file
creation time, and monotonic-clock custody must also span the full eight hours;
changing the wall clock cannot backfill the run. Finalization writes
`logs/overnight-trial.json`, a counts-only,
content-addressed receipt. A passing receipt requires:

- a prospective, single active marker whose evaluator remains unchanged for exactly eight hours;
- complete prospective sample coverage with no gap over ten minutes, with each sample bound to
  every newly appended ordinary watch row and the previous observation hash; every row in each
  offset span is independently re-evaluated, so an alert row cannot be skipped behind a later
  healthy row;
- a newly first-observed typed `done` or owner-blocked event, whose predicate passes and whose
  durable receipt target resolves, whose dispatch timestamp is inside the already-observed trial
  interval (never pre-window or future-dated), with no rolling activity gap over 90 minutes
  including both trial boundaries;
- a fresh warm handoff at the end;
- at least one newly observed `in_progress` event whose provider-native session is independently
  active, recently associated with the in-window task event, and independently present in a
  supported source (currently Jules remote sessions or a currently active GitHub Actions run);
- a fresh, validated, exact `all/all` prompt-atom snapshot on every sample, with zero increase in
  operator occurrence IDs from the preserved append-only prompt journal; and
- zero watch alerts.

The receipt contains only window/count summaries plus SHA-256 hashes of the
evaluator and normalized inputs. The evaluator hash covers the watcher plus
every local module or script it invokes for evidence semantics (`intake.py`,
`prompt_corpus.py`, `jules_remote.py`, `handoff-relay.py`,
`session-value-review.py`, and `autonomy-governor.py`), so changing any one
during or after the window invalidates the marker and receipt. Re-finalizing the same window is byte-idempotent.
The checker reconstructs the receipt from the prospective observation hash chain,
verifies every preserved watch and prompt-journal prefix, rejects task-event
removal or rewriting, and confirms that credited proof IDs first appeared after
the sealed baseline. Every observation and its proof set is also written once to
read-only prospective custody whose creation time must match the live sample;
terminal proof predicates and receipts are re-executed during checking. Pre-seeded
future timestamps, post-window self-consistent chain rebuilds, source truncation,
and rewritten source prefixes do not count.

Predicate proof never invokes a shell. It executes only classified read-only
GitHub, Git, and fixed-system `test`/`[` commands as direct argument vectors;
arbitrary Python/shell/check scripts are not trial evidence. Shell pipes,
backgrounding, control operators, redirection, mutating
GitHub mutations, API field/input/method/cache options, browser/help viewers,
all short-option bundles, and every option outside the command-specific exact
read allowlist are rejected before execution. Ambiguous GitHub `blob`/`tree`
URLs are not receipts; use the exact `git:owner/repo:path` form so the path
object itself must resolve, and any declared anchor must occur exactly in the
remote object. Declared GitHub task keys must match exactly, and issue, PR, run,
and commit URLs must prove the terminal state they claim rather than mere object
existence. Git output, pager,
config, signature, external-diff, help, and version options receive the same
fail-closed treatment. Allowed local Git reads use the trusted system executable
and fixed system path; discard inherited repository, object-alternate, config,
transport, helper, pager, and tracing variables; deny every transport protocol and
promisor lazy fetch; force a signature-free built-in display format; and disable
replacement refs, hooks, fsmonitor, text conversion, external diffs, credential
helpers, pagers, and optional index writes.
GitHub receipt/API proofs and Jules session-seam probes likewise resolve their
executables only from the fixed trusted tool path and run with a minimal
allowlisted environment; inherited `PATH`, shell/Python startup hooks, and
`LIMEN_JULES_BIN` cannot select or initialize a proof producer.

Trial start and finalization intentionally have no backfill arguments; finalization
also refuses to run before the marker's real end time. Trial start refuses to replace an active
marker. Prompt authority is fail-closed: while issue
[`#957`](https://github.com/organvm/limen/issues/957) remains `partial:all`, or while its
source cursor cannot prove a fresh exact scan, `--start-trial` fails instead of
manufacturing a zero-operator receipt.

The prompt scan may be at most the narrow clock-skew tolerance ahead of the
sample; the ten-minute sample-gap allowance is not a prompt-freshness allowance.
At finalization, the exact terminal handoff, prompt cursor, and private prompt
snapshot bytes are copied once into read-only, content-addressed custody sidecars.
The receipt binds their sizes and SHA-256 digests to the hash-chained terminal
observation, and every later check re-derives that binding before verifying the
immutable sidecars. Normal heartbeat, watch, and prompt projections may therefore
advance without invalidating the completed trial. Repeating
`--finalize-trial` returns the same receipt with `changed:false`, exits
successfully, and writes no terminal bytes; substituted, missing, writable,
symlinked, ancestor-symlinked, special-file, or rewritten custody sidecars fail
closed. Verification validates regular-file custody before reading, then uses a
no-follow descriptor plus `fstat`, so a FIFO or device cannot block the checker. Every
custody path component from the trusted Limen root is checked with no-follow
metadata and realpath containment, so moving the configured receipt root and
replacing it with a symlink also invalidates the receipt. The same canonical-file
check covers the prospective anchor, active/terminal marker, final receipt,
watch and observation ledgers, `tasks.yaml`, and all prompt event, outcome,
cursor, and snapshot sources; a byte-identical symlink redirect is not custody.
The ordinary watch JSONL writer and its lock use the same canonical-parent,
directory-descriptor, and `O_NOFOLLOW` boundary, so a redirected watch file,
lock, or ancestor fails before a trial observation can be appended.
All authoritative marker, watch, observation, task, prompt, handoff, and custody
reads validate canonical regular-file state first and then use nonblocking,
no-follow descriptors; special files fail without blocking strict Omega.

Verify it with:

```bash
python3 scripts/overnight-watch.py --check-trial
```
