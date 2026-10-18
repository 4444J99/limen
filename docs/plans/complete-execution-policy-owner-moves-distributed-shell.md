# Lane-specific credential consumer (OpenCode broker access)

Issue: #2961
PR: (pending)

## Context

The chain in the request (policy owner moves mode off `observe` and approves the work key → host pressure
clears → runtime advances past `9bfdb592b` → `limen workstream … --destination` creates the bounded checkout
→ lane-specific credential consumer written and tested) is the closing paragraph of #2961, the OpenCode
native-lane repair. Its last step is the only unstarted one and it is the actual repair.

Today an OpenCode MCP process cannot reach the broker: `mcp/src/limen_mcp/server.py:268` `_conduct_client()`
calls `client_from_env()` with no hydration, and ianva launches `limen_mcp.server` with no upstream environment,
so it fails with `conduct broker is not configured`. The opt-in cache loader cannot fix that as written:
`cli/src/limen/conduct/env_cache.py:68` `read_conduct_credentials()` reads only `LIMEN_CONDUCT_URL` and the
*generic* `LIMEN_CONDUCT_TOKEN`, which is the legacy `codex-direct-legacy` bearer. Reusing it would label an
OpenCode job `codex` (the #3000/#3001 defect). The named bearer `LIMEN_CONDUCT_TOKEN_OPENCODE` already exists
in the ownership-checked `~/.limen.env` and authenticates as principal `opencode-direct` (verified in #2961).

## Gate status (live-checked 2026-10-18; do not re-litigate)

| Chain link | State |
|---|---|
| Policy row + corrective key (#3022) | Installed and read back (fingerprint `bc303fa6…`). #2961 still needs its own row for `opencode-conduct-access-20261018` and mode off `observe`: **owner act, already filed in #2961**. |
| Worker at/after `9bfdb592b` | Deployed (workflow 39111497850). The PATH `limen` runtime (Domus shim, SHA-pinned) is separate and still `d8703e079`: **Domus/operator-gated**. |
| Host pressure | **Still denied**: `host-work-admission.py status --no-probe` → `allowed:false`, reason `swap-fraction` (0.407), 14 held leases. |
| Bounded checkout via `limen workstream --destination` | Blocked on the three above. |

None of these gates are needed to *author and test* the change in an ordinary isolated worktree; they gate the
bounded Archive4T repair checkout and the live acceptance. This plan does not touch policy, priorities, leases,
the retained `repair-checkout.json`, or any peer checkout.

## Approach: one resolver, two surfaces, default path unchanged

1. `cli/src/limen/conduct/env_cache.py`
   - Add `lane_token_key(lane)`: validate against a strict lane-id pattern, then return
     `LIMEN_CONDUCT_TOKEN_<LANE>` (upper-case, `-` → `_`). Anything else raises `BrokerUnavailable`, so a crafted
     `LIMEN_AGENT` can never select an arbitrary cache key.
   - `read_conduct_credentials(environ=None, *, lane=None)` and `complete_from_cache(..., lane=None)`: with a
     lane, parse only `{URL_KEY, lane_key}` and require both; never return the generic token. `lane=None`
     is unchanged.
2. `cli/src/limen/conduct/client.py`: `client_from_env(*, hydrate_cache=False, lane=None)`.
   - `lane=None` → byte-identical to today (about 40 call sites and the zero-arg `lambda: client` test patches
     stay valid; do not change any call site's signature).
   - With a lane: the token comes only from `LIMEN_CONDUCT_TOKEN_<LANE>` in the environment or, if
     `hydrate_cache`, from the cache. The generic `LIMEN_CONDUCT_TOKEN` is ignored (no fallback, ever). A lane
     request never returns `LocalConductClient`; a missing lane credential raises `BrokerUnavailable` that names
     the key, never the value.
3. `mcp/src/limen_mcp/server.py`: `_conduct_client()` passes `lane=os.environ["LIMEN_AGENT"]` with
   `hydrate_cache=True` **only when `LIMEN_AGENT` is explicitly set** (no implicit `"opencode"` default for
   credentials, so existing MCP tests and local-adapter use are unaffected). Credentials are resolved per call
   and never cached or exported, as the docstring already requires.
4. ianva upstream (declared in Domus-owned config; example in `ianva/upstreams.example.json`): the limen MCP
   upstream sets only `LIMEN_AGENT=opencode` and `LIMEN_CONDUCT_ENV_FILE=<absolute path>`, never a token.
   Repo side: update the example and doc. The deployed config edit is a Domus follow-up atom, not an edit to a
   rendered file. `ianva/src/ianva/creds.py` `sanitize_backend_env` already strips every cache key, which pins
   "no whole-cache export into the gateway".
5. Docs: add a short "Lane credential resolution" section to the existing conduct-credentials doc (find with
   `git grep -l LIMEN_CONDUCT_TOKEN_CLAUDE docs/`); no new doc file. Lane bearers are declared in
   `institutio/governance/parameters.yaml` (CLAUDE, JULES, CODEX_CLOUD), not `creds-hydrate.py`; add the one missing
   `LIMEN_CONDUCT_TOKEN_OPENCODE` entry there (done; `check-params` holds it).

Out of scope: R6 owner-role session release (#3001), any change to `conduct-register.sh` /
`bind-running-claude-session.py` (the Claude lane already does this correctly; keep it untouched and add only a
test that `lane_token_key("claude") == "LIMEN_CONDUCT_TOKEN_CLAUDE"`), keeper or Worker code, deployment.

## Tests (hermetic, no real credentials)

Extend `cli/tests/test_conduct_env_cache.py` (its `CACHE` fixture already carries a generic and a `_CLAUDE`
token) and `cli/tests/test_mcp_server.py` (the MCP server's existing test home; `mcp/` has no tests dir, so the
originally planned `mcp/tests/test_conduct_lane_client.py` was not created). The conftest forbids real
`/api/conduct/` traffic even on loopback, so the MCP bearer assertion uses a mock `urlopen` transport rather
than a fake HTTP server:

- lane read returns the lane token, never the generic one, when both are in the cache;
- lane key absent while the generic is present → `BrokerUnavailable` naming the key, no fallback;
- invalid lane ids (`""`, `../x`, `open code`, lower/upper case, `github-actions`) rejected or normalized exactly;
- the environment's generic `LIMEN_CONDUCT_TOKEN` is ignored for a laned client;
- hydration leaves `os.environ` untouched; an unsafe cache (mode 0644, symlink) is the existing named blocker;
- a laned client is `HttpConductClient` even with `LIMEN_CONDUCT_STATE` set, and never `LocalConductClient`;
- no token value appears in any exception text or `repr`;
- MCP against a local fake broker (pattern: `scripts/tests/conduct-register-hook.test.sh`) asserts the presented
  bearer is the lane token and that CLI `client_from_env(lane=…)` and `_conduct_client()` resolve the identical
  `(endpoint, token)` for one environment;
- ianva: one assertion in `ianva/tests/test_backend_env.py` that a lane key is stripped from the gateway env.

## Verification

```
bash scripts/run-pytest-hermetic.sh cli/tests/test_conduct_env_cache.py -q      # hermetic wrapper is mandatory
bash scripts/run-pytest-hermetic.sh cli/tests/test_conduct_client.py -q
bash scripts/run-pytest-hermetic.sh mcp/tests/test_conduct_lane_client.py -q
python3 scripts/check-ruff-pin.py                                                # then ruff check + format --diff on changed files
python3 -m mypy --config-file cli/pyproject.toml cli/src/limen/
python3 scripts/credential-wall.py --check                                       # must still pass all 32 atoms
bash scripts/verify-scoped.sh                                                    # the push gate; heavy wave may be refused by swap
```

Each run bare, exit code read directly. If host admission refuses the heavy wave, say so and defer to the
exact-head hosted run; never report a denial as green.

## Execution and fallback

1. Work in this worktree (`worktree-lane-credential-consumer-2961`, already created). Do not create a competing
   repair checkout. If a guard denies the same action twice, stop and write one script to the job scratch dir
   with dry-run and apply commands plus the post-check, and hand it over (guard-escalation protocol).
2. Implement, run the hermetic tests, run `verify-scoped.sh`, commit with a single concern, push, open the PR
   (`Issue: #2961`), then `session-plan.py close`. Merge only on `scripts/merge-policy.sh` CLEARED, via the exact-head rail.
3. Before closeout, bind this running job: `scripts/bind-running-claude-session.py` with the job's exact native
   session id and its `.claude/worktrees` root, then `scripts/no-tasks-on-me.sh` twice.
4. Report status words separately: merged (on `origin/main`), live (not claimed; the Domus-pinned runtime and
   the ianva upstream env are separate operator-gated steps), observed (only the hermetic fake-broker run).
5. Comment on #2961 with the result and the single remaining owner atoms: policy row + mode, Domus runtime/upstream
   env advance, host admission for the OpenCode root/child acceptance. State each once; do not poll.
