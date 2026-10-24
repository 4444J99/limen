# Native schedule collection runbook

Owner: schedule estate, `4444J99/limen#3177`. The single audit projection is
`institutio/governance/schedules.yaml`; its checker and utilization sensor remain the existing
ones. This adds no timer, service, queue, dependency, webhook or launch authority.

## Authority and deployment

Use only the **existing hourly ChatGPT Intake task** for recurring collection. Preserve its native
ID, original recovery contract, prompt responsibilities, cadence and timezone. Add read-only
collection responsibility to that prompt rather than replacing the task or repurposing the Jules
Steward. The existing Jules Steward remains the sole scheduled capacity-filling launcher;
uncertain attempts retain their holds. OPS owns shared admission, budget and schedule policy;
Limen aggregates engineering evidence. A project can contain multiple repositories or none.

Before amending the existing Intake, record the exact reviewed, deployed **40-character git commit
SHA**, the prior task revision and prompt digest, the additive prompt revision, the private snapshot
destination and the artifact archive destination in its private deployment receipt. Pin that exact
code revision in the collector instructions; never use a moving branch or “latest.” Resolve the pin
from the final reviewed publication and verify `git rev-parse HEAD` against it before invoking local
commands. No code pin or prompt mutation by itself proves scheduled collection or delivery.

The implementation session directly retrieved ChatGPT task results and Grok vendor notification
email through connected tools. The public projection records 15 enabled ChatGPT tasks observed at
2026-10-23T19:22:57Z with partial history: 10 full correlated results and 5 full unresolved results.
The bounded Gmail replay observed at 2026-10-23T19:37:34Z contains 20 partial, unresolved excerpts; it is **not an exhaustive
historical or current account census**. The separate peer Claude trigger receipt is dated
configuration evidence, not this collector's native account read or proof of execution. Cowork,
Gemini Apps, Grok Bot and Jules native account access remain unverified independently of those
products' APIs. Browser bootstrap currently requires the originating connected browser context;
the actionable access gap belongs to #3177, not to a new scheduler.

The design follows packet 2026-10-16-v1.1 and sanitized projection r2 as supplied context; this lane
has not directly retrieved the private packet or memory project. Historical approvals are evidence,
not a fresh authority grant.

## Bounded collection contract

The scheduled native Intake uses its existing supported connectors to read results; it must not
call launch endpoints to test access. Human copy/paste is not the steady-state collection route.
The CLI below is an offline ingestion boundary for those connector readbacks, not a provider API.
If the scheduled environment cannot invoke pinned code or write/read durable private evidence,
record a source/capability gap and retain prior snapshots; do not claim activation is complete.

At each occurrence, select a fixed UTC window ending at the occurrence's start. Cover the previous
24 hours with a two-hour overlap on the preceding successful checkpoint. Give each account/source
a distinct opaque private checkpoint key. Read at most 25 native task records and 50 vendor messages
per occurrence, with at most five connector pages and their documented request deadline. Never
expand bounds silently. Continue remaining pages on the next existing Intake occurrence. A source
failure, unavailable account, malformed record, exhausted bound, or nonterminal page token leaves
the requested window incomplete and its committed watermark unchanged. Store bounded continuation
tokens privately in the collector receipt; they are continuation state, not a completed checkpoint.

ChatGPT collection reads the existing native task inventory and each task's current attempt plus
independently supplied latest result. Readbacks with reused run IDs, a result older than the attempt,
or a different scheduled occurrence remain unresolved. Preserve both original identities and all
previous observations. A null history is unknown. Per-task latest-result reads cannot prove complete
run history or account usage, even after every currently listed task was read.

For Grok Automations, search connected Gmail for the exact sender `noreply@x.ai` within the fixed
window, read each returned message's actual MIME payload and verify the exact parsed sender again.
Support text and HTML-only notifications. Retain canonical Gmail message/thread references and
safe native conversation links; strip tracking/unsubscribe/token links. Arrival/header timestamps
are notification times, not provider execution times. Email excerpts stay partial and unresolved,
including “Continue reading” mail. Full native result access requires a separate supported read.
Grok Automations email access grants no Grok Bot access.

Historical restoration is a separate bounded backlog on that same hourly task: begin from the last
human-reviewed history boundary, use fixed dated windows, keep an independent restoration cursor,
and spend only the remaining per-occurrence message/page allowance after current-window coverage.
Record which windows/pages remain. Do not conflate a 20-message sample, current-day scan, partial
pagination or restored subset with exhaustive history. Preserve any earlier durable data during a
source outage and resume from the last committed window with overlap.

## Private persistence and CLI

Use a dedicated ignored, untracked private directory with mode 0700, e.g.
`logs/private/schedule-evidence/`; database and snapshot files are mode 0600. Tracked/public paths,
symlinks and already-existing nonprivate cache parents are rejected. Do not chmod an existing shared
directory to force it through. The metadata database is append-only evidence history, never an
execution queue, task board, lease store or configuration authority.

Run through the repository's resolved Python interpreter. Each collect invocation accepts one JSON
mapping or a list, capped at 1,000 records and 16 MiB; normalize the entire batch before durable
ingestion. Standard output/error contains counts/status only. Do not print source bodies, IDs,
prompts, mailbox headers, account details, artifact references or private paths into public logs.

```bash
python3 scripts/schedule-collect.py collect --source chatgpt --input PRIVATE_READBACK_JSON --db PRIVATE_DB --observed-at ISO_WITH_TIMEZONE --account-ref OPAQUE_ACCOUNT --owner-ref OWNER
python3 scripts/schedule-collect.py collect --source grok-email --input PRIVATE_READBACK_JSON --db PRIVATE_DB --observed-at ISO_WITH_TIMEZONE --account-ref OPAQUE_ACCOUNT --owner-ref OWNER
python3 scripts/schedule-collect.py collect --source artifact --input PRIVATE_READBACK_JSON --db PRIVATE_DB --observed-at ISO_WITH_TIMEZONE --account-ref OPAQUE_ACCOUNT --owner-ref OWNER
python3 scripts/schedule-collect.py import --db PRIVATE_DB --input PRIVATE_UNION_SNAPSHOT
python3 scripts/schedule-collect.py export --db PRIVATE_DB --output PRIVATE_NEW_SNAPSHOT
```

### Strict account binding

For a source with authenticated principal readback, supply **both** `--account-binding` and
`--profile-observation` to `collect`. The optional mode preserves existing unbound callers when
both arguments are omitted; a configured source must require the pair in its native collector
prompt. Missing or empty arguments, wrong source/provider/surface/account, a different principal,
or stale profile evidence fail before opening the evidence database. Existing observations are
never relabelled or merged. Matching Gmail message IDs or digests do not establish account aliases;
historical label drift without authenticated provenance remains unresolved.

Both inputs belong in the dedicated private directory. The binding has exactly these fields
(replace the example references and digest with the actual private evidence):

```json
{
  "schema": "limen.schedule_account_binding.v1",
  "source": "grok-email",
  "provider": "grok",
  "surface": "automations_email",
  "account_ref": "private:stable-mailbox",
  "profile_provider": "gmail",
  "principal_sha256": "64-lowercase-hex-digits",
  "evidence_ref": "private:account-binding-evidence",
  "bound_at": "2026-10-24T00:00:00Z"
}
```

Compute `principal_sha256` as SHA256 of the UTF-8 bytes of
`profile_provider + "\u0000" + principal_id`. Use the stable ID returned by the authenticated
profile operation, without inventing an ID from task names or message matches. The fresh profile
observation has exactly these fields:

```json
{
  "schema": "limen.schedule_profile_observation.v1",
  "provider": "gmail",
  "principal_id": "private-authenticated-principal-id",
  "observed_at": "2026-10-24T00:01:00Z",
  "evidence_ref": "private:exact-profile-tool-readback"
}
```

The observation must be no more than **900 seconds old** and not future-dated against the actual
CLI clock; `--observed-at` cannot extend that freshness window. The binding date must also not be
in the future. Native Grok email requires profile provider `gmail`; native ChatGPT tasks require
`chatgpt`. If authenticated principal access is unavailable for a source, retain that limitation
instead of manufacturing a profile. Generic artifact bindings must match every normalized row's
provider, surface and account. The CLI checks the consistency and freshness of **caller-attested
inputs**; it does not authenticate the connector itself. Preserve the actual profile tool result
privately so the account claim can be checked independently.

### Local execution receipts

`collect` and `export` accept `--receipt PRIVATE_NEW_RECEIPT`. Each invocation requires a new
unused private path, distinct from its inputs, database and export. Collection additionally accepts
paired `--window-start` and `--window-end` timestamps; the start must precede the end. These window
bounds describe the caller's requested read and do not prove pagination or source coverage.

```bash
python3 scripts/schedule-collect.py collect --source grok-email --input PRIVATE_READBACK_JSON --db PRIVATE_DB --observed-at ISO_WITH_TIMEZONE --account-ref OPAQUE_ACCOUNT --owner-ref OWNER --account-binding PRIVATE_BINDING_JSON --profile-observation PRIVATE_FRESH_PROFILE_JSON --window-start ISO_START --window-end ISO_END --receipt PRIVATE_NEW_COLLECT_RECEIPT
python3 scripts/schedule-collect.py export --db PRIVATE_DB --output PRIVATE_NEW_SNAPSHOT --receipt PRIVATE_NEW_EXPORT_RECEIPT
```

The `limen.schedule_collection_execution.v1` receipt identifies itself as
`local-cli-self-report`. It records a unique invocation, actual start/finish times, hashes of the
CLI and evidence module, outcome and counts, and up to the collection limit of 1,000 observation
IDs. `input_sha256` hashes the exact byte buffer parsed for collection. A matched binding contributes
its scope and evidence digests without exposing the raw principal. Source observation time, source
window and profile authentication remain explicitly caller-attested. Successful export records
`export_sha256` only after comparing the local readback with the exact serialized bytes written.
A mismatching readback returns `commit_state: uncertain`; it is not a successful export receipt.

The CLI reserves a `started` receipt before evidence operations and atomically updates that same
invocation on completion. A crash can leave it `started`; failed receipt publication returns an
error and evidence operations may already have committed. Re-read durable state before retrying;
do not treat a missing terminal receipt as proof that nothing happened. Normal stdout/stderr remains
counts/status only. Save the actual execution-tool result and separately verify remote snapshot,
archive and receipt versions/digests. Receipt JSON alone cannot prove pinned code ran in a native
scheduled occurrence. If execution is unavailable, preserve the previous normalized union and record
an incomplete attempt instead of hand-authoring normalized observations or claiming execution.

`operation_outcome` describes the evidence operation **before receipt publication**, not the final
CLI exit. A terminal receipt can already be visible when its directory sync fails and the CLI exits
2. Always take the actual process exit from the execution-tool result. The receipt target and its
lock must also avoid the database's `-journal`, `-wal` and `-shm` sidecars and the export lock; these
collisions are rejected before creating any of those paths.

Generic artifacts require explicit provider, surface, account, owner, source and native identities,
coverage and attribution evidence. CLI account/owner scope must match the payload. Imported text
never executes shell instructions or creates work. Collection does not execute owner predicates.

Before collection, import the prior durable union snapshot, including assessments and checkpoint
history. Preserve unknowns. Duplicated polls update sighting ranges without increasing observation
counts; changed source facts append events. Export the union and persist it durably after ingestion.
Each export reads observations, assessments and checkpoints from one SQLite read transaction,
preserving any caller-owned outer transaction. Report current state by the **last actual source
readback**, including a repeated identical state after an intervening different state. Snapshot
imports retain their supplied first/last source-observation times: import time is never a new native
task readback. Historical artifact backfill must carry its actual historical observation timestamps;
do not stamp an old occurrence as a fresh authoritative current-task read just because it was
retrieved/imported later. Exact acceptance and delivery history remains bound to its original
observation even when current state becomes unknown.
Re-read and compare the saved snapshot's digest and metadata counts before advancing a watermark.
Replacing an existing export requires `--expected-sha256 EXPECTED_CURRENT_FILE_DIGEST`; replacement
uses a stable private per-target lock, held across existence/revision checks, private temporary-file
creation, file fsync, atomic rename and parent-directory fsync. Concurrent first creation also permits
one writer only. Locks have a finite 10-second acquisition deadline and remain at their stable path
across replacements; do not unlink them while other writers may be waiting. A stale expected digest
or busy deadline fails closed. Symlinks and unsupported nonregular paths are rejected.
If directory sync fails after rename, the command returns an explicit **readback required** error:
the new target may already be visible, but crash durability is unconfirmed. This does not roll back
the rename; keep checkpoint advancement incomplete, read the visible revision, and retry a durable
export with its current digest before advancing. The scheduled durable-file writer must also use
revision-conditional replacement and retry a conflict by reading/importing the newer union, never
by overwriting it. This CLI provides local revision checking, not remote storage concurrency control.

**The normalized snapshot contains no result bodies.** Durably union a separate private archive of
retrieved full ChatGPT result text, keyed by the normalized artifact SHA-256, alongside the metadata
snapshot. Verify each archive body's digest and retention after upload. This is essential when a
future `latest_result` can replace a result without a stable native chat reference. Do not reconstruct
a body from its digest or claim metadata alone preserves full content. The archive's private
index must retain **every** provider/task/run/creation-time/occurrence association for a digest.
Identical bytes can share one body, but a new same-text occurrence must append its association,
never replace an earlier association. Retain canonical Gmail
message/thread references instead of archiving raw MIME, headers or mailboxes. On archive write or
readback failure retain the previous snapshot/archive union and leave the handoff incomplete.

Only after durable ingestion and durable union/archive readback of the **entire requested
page/window**, invoke an explicit checkpoint. Supply all observation IDs from the completed batch;
the command verifies they already exist in the database. An empty source window instead requires
`--empty-window`. Without `--complete`, the command does not advance anything.

```bash
python3 scripts/schedule-collect.py checkpoint --db PRIVATE_DB --source-id OPAQUE_SOURCE --cursor PRIVATE_CURSOR_JSON --observation-id DURABLE_OBSERVATION_ID --complete
```

The CLI cannot independently verify connector pagination or remote archive durability. The native
collector's private receipt must bind fixed window boundaries, terminal page status, all ingested
observations and archive/snapshot readback digests before supplying `--complete`. A malformed page
must not discard valid earlier pages or overwrite the committed cursor. Snapshot imports validate
semantic identities and exact assessment binding, preserving history and rejecting regressing or
conflicting checkpoint history.

## Observation, assessment and capacity

`check-schedules.py --registry PATH --json` reports schema/inventory validity separately from
operational readiness. Schema validity never means an account is accessible or production delivery
is working. GitHub minute offsets are an explicit house policy; duplicate logical launch authority
is checked independently of minute placement. Overlapping times alone are not a global resource
collision, especially for different jobs/resources.

`schedule-utilization.py --registry PATH --snapshot PRIVATE_SNAPSHOT --json` reuses the one sensor's
reader dispatch. Native snapshots are bounded and semantically validated through the canonical
EvidenceStore before aggregation. Public output contains aggregate counts, not native IDs or
artifact references. It separates historical observation records, current unique tasks/runs,
provider completions in the requested UTC day, full/partial collection, attribution and exact
accepted/delivered assessment counts. Current counts follow the latest actual source readback,
including repeated states, while observation counts remain deduplicated. Separate assessment-history counts preserve
older evidence; they do not establish acceptance of a replacement artifact. Fresh collection of an
old result cannot manufacture fresh execution. Native coverage remains partial because this cache
cannot independently attest exhaustive account/window history, so it cannot yield a whole-plane
“full” verdict.

Issue comments alone establish neither run completion nor delivery. Failed GitHub reads are unknown,
not absence. Absence from public aggregate `tasks.yaml` is not authoritative zero Jules launches.
Enabled Claude triggers measure configuration only, separately from executed work. Existing live
positioning-foundry configuration-parity failures remain failures; this extension does not weaken
that gate or silently alter the peer's dated receipt.

An owner may attest acceptance only for an exact complete, correlated artifact, using that
observation's owner, digest, predicate and evidence reference. Delivery additionally requires prior
acceptance of that exact observation/digest and destination evidence. These records report an
authorized owner's supplied evidence; the collector neither grants authority nor runs the predicate.

```bash
python3 scripts/schedule-collect.py assess --db PRIVATE_DB --observation-id OBSERVATION_ID --status accepted --owner-ref OWNER --predicate PREDICATE --evidence-ref EVIDENCE --artifact-sha256 DIGEST
python3 scripts/schedule-collect.py assess --db PRIVATE_DB --observation-id OBSERVATION_ID --status delivered --owner-ref OWNER --predicate PREDICATE --evidence-ref EVIDENCE --artifact-sha256 DIGEST --destination-ref DESTINATION
```

Capacity separates a published ceiling, evidenced account allowance, local desired floor, measured
usage and usable remainder. A public vendor ceiling—even one previously labeled “verified”—is not
verified account entitlement. A remainder requires nonnegative quantities, evidence-backed allowance,
complete fresh usage matching the same opaque account/unit/window, and fresh evidenced downstream
review **and** delivery capacity. Fresh means at most one hour old and not future-dated. Missing,
partial, mismatched or stale evidence leaves remainder null. Account-wide usage remains unmeasured
for the initial native replay. No remainder or utilization verdict admits or launches work.
`published_ceiling` requires explicit `published-ceiling` classification plus a dated publication
source; unclassified, local-policy or unmeasured values remain null in that field. The ChatGPT
ceiling is unknown pending exact publication evidence; the separately observed 15 enabled tasks is
an inventory count and supplies no ceiling.

## Separate release and acceptance gates

1. Source and offline verification: focused hermetic registry/core/CLI tests, touched-Python Ruff,
   registry parity, independent review, then one root-owned scoped verification batch. Preserve and
   name inherited live failures rather than weakening them.
2. Interactive connector replay: durable deduplicated union of actual source reads plus full-content
   archive readback. This proves collection during the implementation session only.
3. Native amendment: record exact code pin and additive Intake revision, preserving original identity,
   prompt responsibilities and schedule. Prompt acceptance does not prove the task can execute it.
4. Natural scheduled occurrence: require a linked Intake occurrence, actual bounded connector reads,
   durable union/archive readback, incomplete-page continuation, and source-specific receipt counts.
   Retain owner and next action for each inaccessible source.
5. Project acceptance and external delivery: require explicit exact-artifact owner assessments and
   destination evidence. Neither native completed status nor a successful collector occurrence
   satisfies these gates.

Route material findings to existing owners through already-authorized handoffs. If access, browser
unlock or durable-write capability is missing, record the gap once with owner and next action, keep
collecting accessible sources within bounds, and preserve the previous checkpoint and evidence.
