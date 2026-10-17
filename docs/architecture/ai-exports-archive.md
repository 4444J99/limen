# AI Exports Archive

The raw exports of the operator's AI accounts (ChatGPT, Claude, Gemini Takeout with NotebookLM,
Grok, Perplexity) live in `/Volumes/Scratch/ai-exports`. They are read-only source material.
Everything browsable is **derived** from them by `cce archive` in
[`conversation-corpus-engine`](https://github.com/4444J99/conversation-corpus-engine)
(design: its `docs/archive-surfaces.md`; delivery: PR #75, issue #74) and is regenerable at any
time. This file is the operational map; it holds no conversation content.

> **Status.** `cce archive` is delivered by engine PR #75, which is a draft: it is merged only
> when it is on that repository's `main`, and installed only when the `cce` on `PATH` contains it.
> Until both are true, run the commands below from the PR branch (for example with
> `uv run --with-editable <checkout> cce …`). The archive described here was built that way on
> 2026-10-17 (a full `cce archive build` takes about five minutes on this host) and
> `cce archive verify` exited 0 afterwards; the front end was exercised in headless Chrome.

## Surfaces

One normalized store feeds five readers of the same material:

| Surface | Where (under the archive root) | Use |
|---|---|---|
| Obsidian vault (the wiki) | `vault/` | open the folder as a vault; backlinks, graph view coloured by provider |
| Static site | `site/` | `index.html` directly, or `cce archive serve` for full-text search |
| Knowledge base | `kb/archive.sqlite` | `cce archive search "<query>"` (SQLite FTS5) |
| Graph | `graph/` | `nodes.jsonl`, `edges.jsonl`, `archive.graphml` for Gephi / Cytoscape |
| Agent search | MCP tool `cce_archive_search` | off by default; see below |

## Locations (all outside any Git repository)

| What | Path |
|---|---|
| Raw exports (source, never written) | `/Volumes/Scratch/ai-exports/<provider>/` |
| Engine project root (registry state) | `/Volumes/Scratch/cce-site` |
| Registered private corpus store | `/Volumes/Scratch/cce-corpus-store` |
| Archive root (all derived output) | `/Volumes/Scratch/cce-corpus-store/_archive` |
| ChatGPT live delta (conversations newer than the account-export snapshot) | `chatgpt-bodies-20261017-delta.json` in the ChatGPT custody replica |

The engine refuses to write anywhere that is not a strict descendant of the registered store, and
refuses a store that is symlinked, nested in Git, or overlapping a source root.

## Rebuild, open, search

```bash
# The shell exports CCE_CORPUS_STORE_ROOT pointing at the legacy symlinked store; always pass
# --corpus-store-root explicitly (it takes precedence) or unset the variable for the command.
env -u CCE_CORPUS_STORE_ROOT cce archive build \
  --export-root /Volumes/Scratch/ai-exports \
  --chatgpt-extra <ChatGPT replica>/chatgpt-bodies-20261017-delta.json \
  --project-root /Volumes/Scratch/cce-site \
  --corpus-store-root /Volumes/Scratch/cce-corpus-store

cce archive verify   --project-root /Volumes/Scratch/cce-site --corpus-store-root /Volumes/Scratch/cce-corpus-store
cce archive search "<words>" --project-root … --corpus-store-root …
cce archive serve    --project-root … --corpus-store-root …      # http://127.0.0.1:8765/
```

A full build is a heavy workload on the 16 GB host: run it at background priority
(`taskpolicy -b`) and bind it to a `heavy` lease with `scripts/host-work-admission.py acquire
--kind heavy … --pid <build pid>`. `build` exits non-zero if any provider failed to read or any
surface disagrees with the ingest manifest, and `manifest.json` carries the denominators
(conversations, empty, duplicates, skipped, channels read / not read, source sha256).

Obsidian: "Open folder as vault" → `/Volumes/Scratch/cce-corpus-store/_archive/vault`.

Agents: start the MCP server with `cce-mcp --archive-root /Volumes/Scratch/cce-corpus-store/_archive`
(or `CCE_ARCHIVE_ROOT`). The tool is not advertised otherwise, and the root is never a tool
argument. Its results are private conversation text; enabling it for an agent is a deliberate
choice, not a default.

## Privacy rules

- Derived output contains the operator's private conversation text. It never enters Git, a PR,
  an issue, a commit message or a tracked receipt. Public docs carry commands and locations only.
- Attachment bytes and attachment text are not ingested; account identity, billing and settings
  files are deliberately not read; user-deleted Gemini turns are skipped.
- Conversation text records speech acts, not events. Corroborate with a commit, transaction or
  file before treating a plan in a conversation as done.

## Custody status

- The ChatGPT account export (the zip) has two verified replicas on independent disks.
- **The Claude, Gemini Takeout, Grok and Perplexity raw exports exist only on Scratch.** Scratch
  (`disk7s3`) is in the same APFS container as Archive4T (`disk7s1`), so it is not independent of
  that disk, and the volumes are unencrypted. The derived archive is regenerable from the raw
  exports; the raw exports are not regenerable except by requesting new ones.
- Time Machine retention for these paths is unverified.

To add a second copy on the independent disk (additive; nothing is moved or deleted; the ChatGPT
folder is excluded because its zip is already replicated twice). Run the dry run first and read it:

```bash
SRC=/Volumes/Scratch/ai-exports
DEST=/Volumes/T7Recovery/limen-private/ai-exports-20261017
mkdir -m 700 -p "$DEST"
rsync -a --dry-run --itemize-changes --exclude='.DS_Store' --exclude='chatgpt/' "$SRC/" "$DEST/"
rsync -a --exclude='.DS_Store' --exclude='chatgpt/' "$SRC/" "$DEST/"
(cd "$SRC" && find claude gemini grok perplexity -type f ! -name .DS_Store -print0 | sort -z | xargs -0 shasum -a 256) > "$DEST.sha256"
(cd "$DEST" && shasum -a 256 -c "$DEST.sha256")
```

Success is every line `OK` from the final check. Only after that, and with the two-copy gate
satisfied, may anyone reorganise the source. An offsite encrypted copy remains a separate
operator decision.

## Open follow-ups

- Bridge the normalized layer into engine corpora and federation (families, entities, review
  queue); the layers share a store but not an index today.
- Read the remaining channels currently reported as *not read* (ChatGPT Codex threads, group
  chats, Pages; Claude artifacts and reflections) once each has a privacy decision.
- Second copy and offsite copy of the single-copy raw exports (above).
