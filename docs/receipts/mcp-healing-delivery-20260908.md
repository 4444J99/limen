# Persistent MCP healing increment

Owner: MCP-ESTATE-20260908, Limen #2567. Base:
`9e4daacf8128b6a38b30191cf42cc185fb3f4987`. Isolated branch:
`feat/mcp-healing-delivery-20260908`. Protected broker run:
`run-de0dabece9c7ab620b6b0f0c913ae87e`.

`mcp_healing.py` provides a private, fsynced episode journal shared by the existing
`mcp-server-boot.py --apply` entry point and its registered monitor hook. It does
not add or activate a scheduler. The existing sensor's `LIMEN_MCP_BOOT_HEAL` valve
continues to control repair invocation.

Episodes bind registration identity, client and target configuration, observed
dependency/version fingerprints, owner launcher bytes, policy, and measured
failure dimensions. One nonblocking owner/repair lock serializes competing
attempts. A write-ahead marker precedes each repair and verification callback.
A restart resumes verification only if the repair receipt was committed and
verification had not started. Uncertain callbacks require owner disposition;
they are never replayed. Completed episodes do not mint fresh evidence on reuse.

Domus retains mutation, backup and conditional rollback authority. The journal
retains its rollback episode identity, never its private backup location. Missing
native dependency witnesses remain missing evidence; a fingerprint containing an
unknown version is not proof of a verified native dependency or route.

## Verification

- Healing plus estate-contract batch: 47 passed, exit 0.
- New entry-point regression: 1 passed, exit 0. Two consecutive `--apply` calls
  invoke one owner repair and remain exit 77 with the full 1/1 fixture denominator.
- Final changed healing shard: 7 passed, exit 0, including malformed owner output,
  concurrent calls, simulated process death, resumed unstarted verification,
  changed episode bindings, private custody and retained rollback identity.
- Scoped integration command against the base above: cheap wave PASS, exit 75 at
  heavy admission (`swap-fraction`). No heavy gate was bypassed or executed.
- `git diff --check`: exit 0.

The full campaign criteria in `mcp-estate-handoff-20260908.md` remain unchanged.
No configuration apply, native startup certification, merge or deployment is
claimed. #2569 publication recovery still needs local admission, exact-head
landing, captured merged Worker deployment, and two real broker mutations.

Fresh read-only `codex mcp list --json` returned exit 0 with both Context7 and
LaunchDarkly `not_logged_in`. The hosted LaunchDarkly consent owner remains
`L-LAUNCHDARKLY-OAUTH-CONSENT`; no login was initiated by a health check. The
documented flow was checked against
https://learn.chatgpt.com/docs/extend/mcp?surface=cli and local CLI help.

Next execution predicate after changed host conditions is the implicated heavy
batch via `bash scripts/verify-scoped.sh --integration --base
9e4daacf8128b6a38b30191cf42cc185fb3f4987`, retaining unchanged passing shards.
Native adapter completion, exact deployment, authentication exchange, and the
unfiltered zero-defect estate measurement remain owned by #2567, not fulfilled
by this source increment.

## Recovery ownership receipt correction

Recovery isolation is pushed to #2576 targeting #2573. Its first broker report
was stored with `mutation_authorized: false` because the command included a base
argument not present in the packet predicate. The corrected receipt
`recovery-isolation-increment-bound-20260908` bound the original predicate,
returned `mutation_authorized: true`, released the lease, and harvested with
`unharvested: []`. This terminal partial run does not mark recovery complete.
