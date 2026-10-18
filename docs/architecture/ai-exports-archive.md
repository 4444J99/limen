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
and is safe to run again: a server that already answers is reused. If the archive has not been built, it
stops with one line and exit code 2.

```bash
limen knowledge            # start the server if needed and open the site
limen knowledge --status   # server state, address, archive fingerprint, newest alive receipt
limen knowledge --stop     # stop the server this command started
```

`--port` picks another port from the default of 8472, and `--no-open` starts the server and prints the
address without opening a browser. The server's log and process id file sit under `<store>/state/`.

## Where things live

| What | Location | In Git |
|---|---|---|
| Raw exports: chatgpt, claude, gemini, grok, perplexity | `/Volumes/Scratch/ai-exports/<provider>` | no |
| ChatGPT delta file (conversations newer than the account export) | Archive4T custody replica, for example `chatgpt-bodies-20261017-delta.json` | no |
| Archive store, also the engine project root | `~/Workspace/limen/.limen-private/session-corpus/archive` | no |
| Derived folder; feeds and receipts sit flat beside `manifest-all.json` | `<store>/archive-all/` | no |
| Private ledger and form index | `~/Workspace/limen/.limen-private/session-corpus/prompt-atoms/` | no |
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

The fixture gate and the live run answer different questions. Gate `check-knowledge-alive` in
`institutio/governance/gates.yaml` runs the four archive test suites, then the fixture run. It has no
remote job because it needs an engine, and `bash scripts/verify-scoped.sh` selects it by path. The
live run is by hand at closeout and is the only proof about the real archive.

## Custody gap (carried over from the earlier draft, not re-checked)

- The claude, gemini, grok and perplexity raw exports exist only on Scratch, and can be regenerated
  only by requesting new exports. Scratch shares a disk container with Archive4T, so it is not an
  independent copy, and both are unencrypted. Time Machine retention is unverified.
- A staged second copy onto an independent disk was drafted and never run. It is additive: dry run
  first, checksum afterward, ChatGPT excluded because its account export is already replicated.

## Engine dependency

The archive, feed, names and fixture commands come from the engine work in pull requests 75 and 79 of
`conversation-corpus-engine` (79 replayed the stacked 76 onto `main` after 75 landed); both merged on
2026-10-18. This loop is live from `main` only while `cce` on the host is installed from engine `main`.
An engine without these commands makes the check report `NOT ALIVE` or `UNUSABLE`. Install or refresh
it from `main`, pinning the commit so the receipt can name the engine it ran under:

```bash
uv tool install --force --from git+https://github.com/4444J99/conversation-corpus-engine@<main commit> conversation-corpus-engine
```
