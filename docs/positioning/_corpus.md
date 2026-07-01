<!-- STAGED LURE — the knowledge-substrate front door. Companion to _method.md: presents ONE internal
     surface — the atomization pipeline — as its own findable external door. Substance drawn from the
     distilled, non-PII architecture statement (knowledge-corpus/reduced/knowledge-atomization-engines.md).
     Commercial-tier price bands from the source were DELIBERATELY stripped (no-price by design). NO PII,
     NO PRICES. ONE SWITCH FROM LIVE: paste to a public README or dedicated repo (your hand). -->

# The Atomization Engine

**Every AI tool you use produces a transcript. All of it is evaporating into formats you can't query.**

Claude, ChatGPT, Gemini, Grok, opencode — each in its own silo, its own export blob, its own schema. The knowledge you generated across all of them is real and it is disappearing. The atomization engine turns that scattered exhaust into one content-addressed, deduplicated, secret-clean substrate that everything downstream can query.

## One pipeline, every source

Every raw input — transcript, note, export blob, SQLite database, even a protobuf conversation — passes through the same four stages:

**ADDRESS → PROCESS → CLEAN → ENRICH.**

- **Address** — content-address every file by SHA-256, classify it, detect duplicates before parsing.
- **Process** — per-source adapters parse each format into atomic records. Adapters own format; the pipeline owns the contract.
- **Clean** — redact secrets on ingest; collapse duplicates globally by content hash.
- **Enrich** — language detection, session lineage, embeddings, indexes — the query-ready substrate.

## Built to production weight — measured

- one full run: **20,189** files across **9** sources → **313,071** raw messages → **242,482** unique atoms
- **22%** collapsed as global duplicates — the same bytes always resolve to the same address
- **58** credentials redacted at ingest; a leak scan of the output returned **zero** live keys
- hard cases closed: an opencode SQLite database yielded **46,403** atoms where a naive parser found two; an antigravity protobuf store gave up its conversations to a heuristic wire-walk

## The invariants that make it hold

1. **Content addressing is universal** — SHA-256 of normalized content is the identity key at every layer.
2. **Adapters own format, the pipeline owns the contract** — a new source is one dropped adapter, never a fork.
3. **Promotion is gated, never silent** — nothing reaches live without clearing a review gate.
4. **The message is the granularity boundary** — the substrate isn't pre-chopped; each consumer projects the grain it needs (retrieval/RAG, cross-session graph, linguistic decomposition).
5. **The ingest layer is extractable** — the adapter/schema contract is an importable module, not a local-only tool.

## What's open — and what you'd actually work with me on

**Open:** the architecture — the four stages, the adapter contract, the invariants. Readable in full.

**What you'd retain:** the running pipeline pointed at *your* sources — your transcripts, your exports, your databases — collapsed into one queryable substrate that keeps ingesting as you work.

---

**Drowning in AI transcripts across five tools? — Let's make them one queryable corpus.**  ·  **Hiring the person who built this? — This is the evidence.**

_If it fits, reach out. This conversation starts at serious._
