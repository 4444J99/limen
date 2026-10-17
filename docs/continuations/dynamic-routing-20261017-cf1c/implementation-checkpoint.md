# Dynamic routing implementation checkpoint

Native caller: home directory. Session: 01a14ac6-cf1c-7043-a3d6-839e4fbd4f56.
Attempt started 2026-10-17T16:51Z, ends no later than 17:21Z.
This is an incomplete implementation handoff, not native acceptance or release.

Limen source 183a9793bcf0a1febfb9546e18f562b82058059a implements known-price
capability selection and current OpenCode v2 registry discovery. Focused tests:
25 passed, exit 0. Eight new tests first failed on the observed old behavior.
The installed runtime lacks the new selector; no runtime deployment is claimed.

Domus source aff4f7671318c7691edf94d73b1e6adcb74c6a4e contains native response
encoders, precise advisory op command recognition, inherited-model/fork checks,
a bounded selector bridge and routing metadata in the existing hook observations.
Fifteen new encoder/command tests pass; pre-integration modifier suite: 30 passed.
After integrating landed #485/#486/#488, the combined suite was 52 passed and
one failure: test_codex_fork_ignores_explicit_child_model expects the old
model.execution-tier reason; source now deliberately returns model.explicit-fresh-fork.
The known one-line correction is in scripts/model-routing-recover-20261017-cf1c.py.
No all-green Domus branch or completed six-client wiring is claimed.

## Guard hold

The host rejected apply_patch with workspace-scope-unavailable, a scoped multiline
patch command with command-substitution-or-multiline, renewed chezmoi status with
workspace-scope-unavailable, and scratch recovery-script staging with that same
scope reason. Patch retries stopped under the user's two-denial escalation rule.
No guard was changed or bypassed. Git preservation remained available. The
recovery script is published as a source artifact rather than executed.

## Client disposition

| Client | Implemented | Remaining owner acceptance |
|---|---|---|
| Claude | encoder and inherited-definition validation | per-child dynamic catalog, wiring, allowed/denied native probe |
| Codex | encoder and explicit fresh-fork validation | fixture reason update, native trust/dispatch and actual-child readback |
| Gemini | BeforeTool response encoder with equivalent predefined agent selection | registry integration, actual BeforeTool routing and specialized-agent readback |
| OpenCode | v2 model.list parser/discovery | v2 plugin port and role/tool routing without shared per-call mutation |
| Cursor | subagent_model encoder | blocking subagentStart registration and consumed native denial |
| Copilot | string/object toolArgs encoder | source-owned enforcement hook and payload/lifecycle coverage proof |

Do not activate the experimental native_model_runner: it currently only receives
registry metadata from an OpenCode envelope, and its Gemini runner does not yet
pass the predefined-agent registry to the encoder. Missing metadata must remain
unknown; blanket activation would deny capability without proving cost routing.
Reserved-candidate acceptance, per-phase authority, budget/retry inheritance,
concurrent differing-model delegation, outcome receipts, and actual native
models still need full integration coverage. Preserve Fable gates and app trust.

The initial status inventory had 62 entries (23 scripts and two deletions),
not the plan's historical 54. The adjacent per-file report preserves every
observed entry and explicitly defers semantic/deployment acceptance. Concurrent
rollout changed the live denominator; renewed refresh was denied. No apply or
script execution was performed. Deletions, migrations, cleanup and quarantine
changes remain held; .serena/project.yml and all sessions remain preserved.

CI preservation: all four remote heads were read back exactly, including newly
pushed fix/ci-python-env-20261017 at b811cdc0d55d8fe3cbd5911ba4cb06e2e539aefc.
Both CI checkouts and both implementation checkouts are retained. No retirement.

Existing owners: Limen #940 and Domus #487. No duplicate Codex trust task.
Canonical IRF linkage and current CI landed/superseded receipt extension remain
unfinished; native acceptance/rollout and two-zero session release are unproven.
The registry review and native probes must not be relabeled complete.

Final scoped verification was rejected by the live host hook for swap-fraction.
That denial produced no predicate exit code and is not a failed source test.
Drafts: Limen #2903 and Domus #490. The source/fixture snapshots above are not
substitutes for an exact-head final scoped gate or native enforcement.
