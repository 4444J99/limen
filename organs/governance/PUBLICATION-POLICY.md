# Publication Policy — the disclosure court

**One question, one answer, every repo.** For any piece of content, *"does this belong on
this repo, and in what form?"* is not a per-file human judgment — it is a lookup in a fixed
rule table. This organ is that table plus the engine that reads it, so the answer is always
clear and never re-litigated.

- **Engine:** [`scripts/publication-policy.py`](../../scripts/publication-policy.py)
- **Tests / predicate:** [`cli/tests/test_publication_policy.py`](../../cli/tests/test_publication_policy.py) + `publication-policy.py --verify`
- **Beat:** `C_PUBPOLICY` (heartbeat) → `--verify` each cycle → stamps `logs/publication-policy-state.json` → proprioception rung `PUBPOLICY`.

## The decision

Two inputs. **Repo visibility** (`public` | `private`) and **content class**, classified
path-first then by content:

| class | what it is |
|---|---|
| `secret` | tokens / keys / credentials / `.env` / `*.pem` — or content matching a secret shape |
| `personal_pii` | an ordinary doc carrying the **owner's** identifiers (name / handle / home-path / convo-link) |
| `internal_strategy` | raw session dumps (`YYYY-MM-DD-HHMMSS-*`), prompt archives, `docs/planning/`, premortems, transcripts |
| `product_content` | app/source code + its fixtures (product contacts, UI placeholders, `555`/`example.com` fakes) |
| `public_safe` | everything else (README, curated docs, data) |

### The disposition matrix

| content ↓ / repo → | **PUBLIC** | **PRIVATE** |
|---|---|---|
| `secret` | `REMOVE_ROTATE` | `REMOVE_ROTATE` |
| `personal_pii` | `REDACT_IDENTIFIERS` | `REDACT_IDENTIFIERS` |
| `internal_strategy` | **`KEEP_OFF_PUBLIC_HEAD`** | `RESTORE_REDACT` |
| `product_content` | **`LEAVE`** | `LEAVE` |
| `public_safe` | `PUBLISH` *(his click)* | `PUBLISH` *(his click)* |

## The doctrine it encodes

1. **PII is processed and redacted, never deleted.** Owner identifiers are scrubbed; all
   substance is preserved. Redaction is **owner-scoped only** — it never uses a category-wide
   `@domain` / any-phone wildcard. That bare wildcard was the 2026-07 over-redaction bug (it ate
   `legal@styx.protocol`, `you@styx.protocol`, `partner@example.com`, and the fiction-reserved
   `555` fixtures, breaking product builds + tests). The engine's redactor is scoped to the
   `OWNER` config and nothing else. See [`DISCLOSURE-AUDIT.md`](DISCLOSURE-AUDIT.md).
2. **Secrets are never restored anywhere.** They are removed; rotation is the credential organ +
   a vendor mint (his hand). See [`scripts/creds-hydrate.py`](../../scripts/creds-hydrate.py) (the
   credential organ that mints + verifies — the `_SECRET_RX` pattern is the canonical firewall
   mirrored in this engine).
3. **Subject-matter-sensitive content stays off the public HEAD.** Internal strategy, raw session
   artifacts, and named third parties on a *public* surface are kept **off the live HEAD** —
   preserved in git **history** (never deleted from the universe), just not on the face. On a
   *private* repo the same content is a safe restore-and-redact. Identifier-redaction cannot
   neutralize sensitive *subject matter*, only sensitive *identifiers*.
4. **Autonomy is derived from reversibility** (the Censor's constitution — see
   [`scripts/heartbeat-loop.sh`](../../scripts/heartbeat-loop.sh) for the beat cadence and the
   `his_lever`/`auto` autonomy split in the disposition matrix):
   reversible/protective → `auto`; **publish / flip-visibility / send → his hand** (the media-pillar
   boundary "mine, but the publish click is his").

## Convergence table — every scattered gate references THIS rule table

The content-safety surface was built as several independent gates. This table maps each
to its single row in the disposition matrix so any future change starts here, not in a
new gate:

| Scattered gate | File | What it guards | Converges to (rule-table row) | Autonomy |
|---|---|---|---|---|
| `_SECRET_RX` | `scripts/creds-hydrate.py:455` | Secret-shaped strings in credential output + content | `secret` × any vis → `REMOVE_ROTATE` | `his_lever` (rotation is a vendor mint) |
| `SENSITIVE_PATTERNS` | `scripts/scan-legacy-session-batch.py:37` | Keyword-based session-content classification for legacy review batch | `internal_strategy` (path-first classifier in engine supersedes keyword classification) | `auto` (classification, not action) |
| `persona contracts` | `spec/contracts/surface-manifest.schema.json` | WHO may see WHAT on WHICH surface (persona-based surface gating) | Complementary: disposition matrix decides CONTENT safety; persona contracts decide AUDIENCE access. Both must agree before content reaches a surface. | mixed |
| `awaiting_publish` | `scripts/generate-positioning.py:93` | Repo-level publish gate: banked + tested positioning seeds kept OFF all public surfaces | `public_safe` × `PUBLIC` → `PUBLISH` (his_lever). The `awaiting_publish` flag IS the `his_lever` manifestation: he flips the repo public and clears the flag, then disposition allows `PUBLISH`. | `his_lever` (the publish click is his) |

**Protocol:** every new content-safety concern enters the engine (classifier + disposition)
first — never a standalone gate. If a new gate is unavoidable, it must reference this table
as its authority and be added to the table above.

## How a repo / sweep defers

Instead of judging each file, ask the engine:

```bash
python3 scripts/publication-policy.py classify <path> --visibility public
python3 scripts/publication-policy.py audit ledger.json           # a whole estate at once
python3 scripts/publication-policy.py redact <path> --apply       # owner-scoped only
python3 scripts/publication-policy.py --verify                    # is the engine still sound?
```

The 2026-07-02 PII-sweep re-audit was resolved *by this engine* — see
[`DISCLOSURE-AUDIT.md`](DISCLOSURE-AUDIT.md) for the per-repo disposition ledger it produced.
