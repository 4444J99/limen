# AI exports archive

The operational map of the loop that turns the raw exports of the operator's AI accounts into a
browsable archive, a prompt ledger and a checked receipt. It holds commands, locations and rules, no
conversation content and no counts, because the committed receipt owns the numbers. It replaces the
earlier draft, which described a store on the Scratch volume.

## The loop

```
raw exports (/Volumes/Scratch/ai-exports/<provider>) + the ChatGPT delta file from the Archive4T replica
  -> cce archive build               -> the archive store, folder archive-all/
  -> cce archive project feed        -> a feed and a receipt per provider, beside manifest-all.json in archive-all/
  -> prompt-atom-ledger.py --archive-feed ... --write      -> the private ledger
  -> prompt-recurring-forms.py --write                     -> the recurring-form index and report
  -> check-knowledge-alive.py --live --write-receipt       -> a counts-only receipt in docs/receipts/
```

## The front door

`limen knowledge` opens the archive, so nobody has to know the store path or the server flags. It
derives both from the corpora registry, starts the engine's server on a fixed local port if nothing is
answering, and opens the site in the browser. The site is the static pages under `site-all/` with
full-text search over every conversation added by the server. The Obsidian vault in `vault-all/` is
opened as well when Obsidian is installed, and skipped without error when it is not. The server listens
on the loopback interface only, so nothing here leaves the machine. The command is `scripts/open-knowledge.sh`
and is safe to run again: a server that already answers is reused. If the archive has not been built, the
start path stops with one line and exit code 2.

```bash
limen knowledge            # start the server if needed and open the site
limen knowledge --status   # server state, address, archive fingerprint, newest alive receipt
limen knowledge --stop     # stop the server this command started
```

`--port` picks another port from the default of 8472, and `--no-open` starts the server and prints the
address without opening a browser. The server's log and process id file sit under `<store>/state/`.

The door follows these rules, all enforced by `scripts/open-knowledge.sh`.

- `--stop` and `--status` work without a built archive. Without one, `--status` says the archive is
  not built on this host and prints no fingerprint, vault or receipt line.
- A listener counts as the archive server only when `/api/ping` answers HTTP 200 with `"ok": true` in
  the body. A port held by something else makes the start path exit 1 without launching anything, and
  `--status` reports the server as down with a note that the port is held by something else. Every
  liveness probe is `curl -q --http1.1 --noproxy '*'`, so neither a user `~/.curlrc` nor a proxy
  environment can make a live server read as down.
- A recorded process id is trusted only when its command line is an `archive serve` for this same port.
  Otherwise `--stop` drops the stale id file and signals nothing. When the signal fails because the
  server has already exited, `--stop` says so, removes the id file if it still names that process, and
  exits 0; when the process is still listed but cannot be signalled, it exits 1.
- Only one start runs at a time per port. A second start waits for the first, then reuses the server
  that came up. The lock names the process that holds it. A lock is recovered when that process is
  gone or is not this script, or when its id file holds no process id at all and the lock directory is
  at least 3 seconds old (a start killed between taking the lock and writing its id). One start at a
  time removes it, after judging it dead a second time. A start waits for a live holder for the start
  timeout plus 5 seconds, and at least 15, then exits 1.
- A state directory that cannot be created, or cannot be written when a lock must be taken or
  recovered, makes the start exit 1 at once with a message naming the directory, instead of waiting.
  A server that already answers is reused even then, since it needs no lock.
- A start that times out terminates the server process it launched and removes the process id file.
  The default wait is 10 seconds, and `OPEN_KNOWLEDGE_START_TIMEOUT_SECONDS` overrides it with a
  positive integer of at most six digits; any other value is ignored.
- `curl` must be on the path. Without it `--stop`, `--status` and the start path exit 127 with one
  line saying so, because the liveness probe cannot run; `--help` still works, and an invalid `--port`
  still exits 2 first. `--port` takes a whole number from 1 to 65535 without a leading zero, and
  anything else exits 2.
- The status receipt line is bound to the live fingerprint. When receipts of the form
  `receipt-knowledge-alive-<16 hex>-<date>.json` exist but none was made for the current fingerprint,
  it names the newest one on disk as stale.

Several narrow limits remain. Two are in the script header's residual list: a `--stop` that lands
between a start launching its engine and the engine's command line showing `archive serve` finds no
trusted process and deletes the id file the start has just written, so a later `--stop` cannot find the
server; and an id file is not locked against a concurrent stop of a different start. A start killed
while it was removing a dead lock leaves a recovery marker that a later start removes only once it is a
minute old, so a start that finds it younger than a minute minus its lock wait (45 seconds with the
default wait) exits 1 at the lock wait. The remaining windows of the lock recovery, such as a holder
stalled for 3 seconds or more, a recycled process id and a holder started through a wrapper whose
command line lacks `open-knowledge`, are accepted and listed in #3032.

## Where things live

Shell variables used below:

```bash
STORE=~/Workspace/limen/.limen-private/session-corpus/archive    # the archive store
DELTA=<path to the ChatGPT delta file>                            # a placeholder: point it at the file
PRIVATE=~/Workspace/limen/.limen-private/session-corpus          # the parent of prompt-atoms/
```

`PRIVATE` is the parent folder. `prompt-atom-ledger.py` and `check-knowledge-alive.py` both append
`prompt-atoms/` themselves, so passing the `prompt-atoms/` folder as `--private-root` makes the ledger
read as missing.

| What | Location | In Git |
|---|---|---|
| Raw exports: chatgpt, claude, gemini, grok, perplexity, and notebooklm, whose raw export nests under gemini | `/Volumes/Scratch/ai-exports/<provider>`, and `/Volumes/Scratch/ai-exports/gemini/NotebookLM` | no |
| ChatGPT delta file (conversations newer than the account export) | Archive4T custody replica, for example `chatgpt-bodies-20261017-delta.json` | no |
| Archive store, also the engine project root | `~/Workspace/limen/.limen-private/session-corpus/archive` | no |
| Derived folder; feeds and receipts sit flat beside `manifest-all.json` | `<store>/archive-all/` | no |
| Private ledger and form index | `<PRIVATE>/prompt-atoms/` | no |
| Registry rows | `institutio/governance/corpora.yaml` | yes |
| Alive receipt | `docs/receipts/receipt-knowledge-alive-<16hex>-<yyyymmdd>.json` | yes |

Everything before the receipt is private and can be rebuilt. It never enters Git, a pull request, an
issue, a commit message or a tracked receipt. The store sits under `.limen-private/`, which
`.gitignore` excludes. It is a regenerable working copy with no custody row, because a copy that can
be rebuilt is not custody. Scratch is never registered as a store. `corpora.yaml` declares the store `limen-private-archive` and one corpus row,
`archive-all`, of kind `normalized-archive`. The store is declared last, and
`scripts/corpus_resolve.py` skips any store whose rows are all `normalized-archive` when it picks the
corpus home (`archive_only_store_roots`), so this store is never `corpus_home()`. Before the first
build, the registry check reports the missing store as unaccounted and fails by design.

## Stage one: build

The engine reads each provider folder, writes the normalized layer, then the reading surfaces, then
verifies them against the manifest. It never writes to the exports, and every write must land in a
registered store that is not a symlink and not in Git. Register once, then build:

```bash
cce corpus-store register --root "$STORE" --project-root "$STORE"
cce archive build --export-root /Volumes/Scratch/ai-exports --chatgpt-extra "$DELTA" \
  --project-root "$STORE" --corpus-store-root "$STORE"
```

The ChatGPT account export is a snapshot, and the delta file wins over the same conversation in it.
Attachment bytes are never ingested, account identity, billing and settings files are not read, and
turns the user deleted at the source are skipped and counted. `archive-all/` then holds
`manifest-all.json` (counts, channels read and not read, source hashes, source fingerprint),
`manifest-all-vault.json`, `provider-<provider>/` (normalized conversations), `vault-all/` (the
Obsidian vault, which is also the wiki), `site-all/`, `graph-all/` and `database-all-search.sqlite`
(full-text search for `cce archive search`).

## Stage two: feeds

```bash
cce archive project feed --root "$STORE/archive-all" --out "$STORE/archive-all"
```

The feeds sit flat in the archive folder, not in a subfolder, because `cce archive verify-names` walks
every entry under `archive-all/` and a folder named `feed` is not a minted name. Writing there touches
nothing else: the command replaces only `feed-<provider>-prompts.jsonl` and removes only that provider's
older `receipt-<provider>-prompts-*` files.

Each provider gets `feed-<provider>-prompts.jsonl`, one row per ask the person typed, and
`receipt-<provider>-prompts-<16hex>-<yyyymmdd>.json`. The command refuses an output folder inside a
Git work tree unless it is ignored. Eligible asks have role user and channel typed, in a conversation
of kind chat, search or activity. Edited ChatGPT asks are kept as an alternate branch. The receipt holds counts and digests, never text: the
feed hash, row count, exclusions by reason, the manifest fingerprint and the naming version. Its
sixteen hex characters are the start of the SHA-256 of the fingerprint string, and its date is the
newest activity day in the data, never the clock. Two runs write identical bytes. A provider whose
messages are all excluded still gets a feed and a receipt: the feed is empty and the receipt says
zero rows with the hash of an empty file. The ledger tool ingests nothing from it, and check 5
accepts the pair.

## Stage three: ledger and recurring forms

```bash
uv run --project cli --extra test python scripts/prompt-atom-ledger.py \
  --root . --private-root "$PRIVATE" --archive-feed "$STORE/archive-all/feed-<provider>-prompts.jsonl" --write
uv run --project cli --extra test python scripts/prompt-recurring-forms.py \
  --root . --private-root "$PRIVATE" --write
```

Repeat `--archive-feed` for each provider. The ledger tool verifies each feed against its one sibling
receipt first. The guard is in `docs/architecture/prompt-corpus-control.md`, section *Vendor archive
feed*. A row must name `archive-<provider>-messages` as its source, carry the fixed provenance
`unknown_user_input`, and hold only the allowed keys, so no archive source can carry operator
authority. A rejected feed exits 2 and writes nothing.

Ledger atoms that share a lineage are the same ask in different places. Two or more make a form,
named `pattern-all-<16hex>`. The forms tool writes `index-all-patterns.jsonl` and
`report-all-patterns.json` (counts only) beside the journal. `--verify` recomputes and byte-compares.

## The check

`scripts/check-knowledge-alive.py` runs ten checks in fixed order and stops at the first failure. The
last line is `ALIVE <16hex>`, `NOT ALIVE: <check name>` or `UNUSABLE: <reason>`. Exit 0 means alive,
1 means a check failed, and 2 means the environment is unusable. A missing tool is never skipped.

| # | Check | What it proves |
|---|---|---|
| 1 | tools | a working engine is found and its naming version meets the minimum |
| 2 | names | the engine accepts every name under the archive |
| 3 | registry | live only: the archive store is bound (declared last with its row, registered root is the store under check, check-corpora checks B and C pass for it alone, not the corpus home); drift in other stores is counted, never failed |
| 4 | archive | the engine verifies the archive and at least two providers are ok |
| 5 | feed receipts | one feed and one receipt per provider, bound to fingerprint and feed bytes |
| 6 | ledger binding | each feed holds the rows, alternate rows and exclusions its receipt declares (rows plus excluded equal messages seen), feeds reproject byte for byte, and every row is in the ledger as unknown authority |
| 7 | recurring forms | the form builder verifies and the form invariants hold |
| 8 | privacy | roots are Git-ignored and no conversation id, title, message id or full typed sentence (6 words and 40 characters or more; shorter asks are shared vocabulary) appears in a public file |
| 9 | receipt | live only: the counts-only receipt for the current fingerprint exists |
| 10 | determinism | a second pass prints identical bytes |

```bash
python3 scripts/check-knowledge-alive.py --fixture
python3 scripts/check-knowledge-alive.py --live --store-root "$STORE" \
  --private-root "$PRIVATE" --project-root "$STORE" --write-receipt
```

`--feed-dir` defaults to the archive root, where the feeds and receipts are.

The fixture run uses synthetic exports in a temporary folder and never reads private data. The live
run reads the real store and ledger and writes only the receipt, and only when it is missing. The
engine is the first candidate that passes a names probe: `KNOWLEDGE_ALIVE_ENGINE` if set, then `cce`
on the path, then each known checkout. Check 1 reports the winner.

## Naming contract

The engine owns it and Limen copies none of it. Every name comes from `derive_name`: a kind word, then
optional scope, subject, identity and date, as lowercase words joined by single hyphens, at most
eighty characters, and an over-long name is an error, never cut. The kind comes from a closed table, a
subject is never taken from a title, and an identity is a plain vendor identifier or the first
sixteen hex characters of a SHA-256. A conversation is `conversation-` plus its unique id, and an id
the grammar cannot express is replaced by a derived one and counted in the manifest. Only three
folder words sit outside the grammar: conversations, hubs and meta. `cce archive names --json` prints
the kinds, scopes and naming version, and `cce archive verify-names --root DIR` checks a tree. The
version rises when a kind is added or widened, and each receipt records the one it was made under.

## Rebuild and verify

A full build is a heavy workload on a sixteen gigabyte host. Take the heavy lease, then run at
background priority with the legacy store variable unset:

```bash
python3 scripts/host-work-admission.py acquire --kind heavy --owner <session> \
  --surface cce-archive-build --pid <shell pid> --ttl-seconds 2400
env -u CCE_CORPUS_STORE_ROOT taskpolicy -b cce archive build <arguments from stage one>
cce archive verify --project-root "$STORE" --corpus-store-root "$STORE"
cce archive verify-names --root "$STORE/archive-all"
```

The shell exports `CCE_CORPUS_STORE_ROOT` pointing at a legacy store. Left set, it can send the
engine there, so unset it for the command and also pass `--corpus-store-root`. Release the lease with
`host-work-admission.py release` afterward, repeat stages two and three, then run the check with
`--write-receipt`. A new fingerprint makes a new receipt file, and older ones are never deleted.
`build` and `verify` exit non-zero when a provider failed to read, a vault link dangles, or a surface
disagrees with the manifest. A failing provider never stops the others.

Always build every provider. `--provider` narrows only the ingest stage: the manifest is rewritten
from the providers named in that call and from nothing else, while the folders of the other
providers stay on disk and the later stages still read them. On a synthetic store holding two
providers (`cce archive fixture`, observed through the installed `cce` on 2026-10-18),
`build --provider claude` left a manifest listing claude alone with a new fingerprint, and both
`build` and `verify` exited 1: the analysis row count, the graph node count and the site page count
each differed from the manifest. A second, full build restored the first manifest and fingerprint
exactly. Never aim `--provider` at the live store. To add or refresh one provider, repeat the whole
stage-one command, and give a provider whose folder is not under the export root its own with
`--source <provider>=<folder>`, as Copilot needs below.

The fixture gate and the live run answer different questions. Gate `check-knowledge-alive` in
`institutio/governance/gates.yaml` runs the four archive test suites, then the fixture run. It has no
remote job because it needs an engine, and `bash scripts/verify-scoped.sh` selects it by path. The
live run is by hand at closeout and is the only proof about the real archive.

## Custody

Encrypted remote portability is a separate opt-in layer described in
[encrypted knowledge publication](encrypted-knowledge-publication.md). It preserves this archive
loop and the physical backup below. Its implementation/review status and live acceptance gates are
explicit; a ciphertext workflow is not a new physical-custody receipt or a live publication claim.

The committed receipt `docs/receipts/receipt-custody-ai-exports-second-copy-20261018.json` owns the
numbers and states what the second-copy run claims.

- It covers the providers claude, gemini, grok and perplexity, copied from the Scratch volume to the
  volume T7Recovery on a different physical device, with a sha256 manifest of every file on both sides
  compared byte for byte.
- It excludes chatgpt. The receipt states that the account export is already replicated on two
  independent devices; that is the receipt's statement and is not re-checked here.
- NotebookLM's raw export sits at `/Volumes/Scratch/ai-exports/gemini/NotebookLM`, inside the gemini
  folder, so the gemini copy very likely covers it. That is not verified.
- T7Recovery was not attached on 2026-10-18, so the destination was not re-verified after the run.
  Re-verify it whenever it is attached.
- The receipt does not document how its `manifest_sha256` was built, so that digest cannot be
  reproduced from the receipt alone.

Archive4T, Ingress, Scratch and the Time Machine volume TM-Mac are volumes of one APFS container on one
physical disk, so none of them is an independent copy of Scratch, and FileVault is off on all four
(`diskutil apfs list`, 2026-10-18). Only the T7Recovery copy is independent, and only while that volume
is attached and has been re-read. Time Machine retention is unverified here.

## Providers not in the archive

Microsoft Copilot is not in the live normalized archive. Its sources are held outside the archive
store as a single copy, in `/Volumes/Archive4T/workspace-backup/session-meta/data/session-transcripts/copilot-captures-2026-03/`.
The engine has read them since `conversation-corpus-engine` pull request 82 (commit `c46256075a5d`):
the reader takes the saved `copilot.microsoft.com` pages (SingleFile `.html`) as conversations,
counts the Word and text files in the folder by suffix without opening them, and puts `copilot`
among the providers of `cce archive build`. The live archive has not been rebuilt with it, so its
manifest still lists six providers and holds no Copilot conversation. The folder is not under the
export root, so adding Copilot is the full stage-one build with `--source copilot=<that folder>`
(see Rebuild and verify), never `--provider copilot` alone. The registry lists the captures as a
harvest source of the `session-atoms` stream; whether anything there reads them beyond opaque blobs
is not verified here. The registry row `copilot-history-memory` in
`institutio/governance/corpora.yaml` records that vacuum until the rebuild. The preservation receipt
is `docs/receipts/receipt-custody-copilot-captures-20261018.json`, and issue #3010 orders the
rebuild, the registry update and the second copy, which is blocked on attaching T7Recovery. GitHub
Copilot CLI history under `~/.copilot/session-state` is a different product and is not part of this.

## Engine dependency

The archive, feed, names and fixture commands come from the engine work in pull requests 75 and 79 of
`conversation-corpus-engine` (79 replayed the stacked 76 onto `main` after 75 landed); both merged on
2026-10-18. This loop is live from `main` only while `cce` on the host is installed from engine `main`.
An engine without these commands makes the check report `NOT ALIVE` or `UNUSABLE`. Install or refresh
it from `main`, pinning the commit so the receipt can name the engine it ran under:

```bash
uv tool install --force --from git+https://github.com/4444J99/conversation-corpus-engine@<main commit> conversation-corpus-engine
```
