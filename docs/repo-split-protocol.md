# The Repo-Split Protocol — publish the form, rent the operation

**Doctrine.** A private repo holding both a publishable FORM (docs, schemas, interfaces, sanitized
examples) and a private OPERATION (data, transcripts, pipelines, credentials) is never flipped whole.
It splits: the form goes to a fresh public twin; the operation stays the moat. The registry row is
the trigger — an `estate.yaml` `repo_overrides` entry carrying `split: {into: [...], why: ...}` —
and the doctor cites every such row as owed work until the verifier passes.

**The one hard law: NEVER fork, branch-copy, or `cp -r` the private repo.** Git history leaks — a
fork shares every object; a tree copy drags ignored/embedded residue. The public twin starts from
`git init` and receives files one allowlist entry at a time.

## Full split (form twin)

1. **Rename** the private repo `<name>` → `<name>--operatio` (GitHub redirects preserve every
   remote). The product name — the strongest GitHub search signal — goes to the public twin.
2. **Extract** into a clean directory: fresh `git init`; copy an explicit allowlist (docs/, schemas/,
   interface/type files, sanitized examples). Each file is admitted **only** if
   `scripts/publication-policy.py classify <path>` says `public_safe` or `product_content`;
   `secret` / `personal_pii` / `internal_strategy` refuse the copy.
3. **Manifest**: commit `form-manifest.yaml` at the twin's root — single initial commit:

   ```yaml
   schema_version: 0.1
   source_repo: organvm/<name>--operatio
   source_commit: <sha>
   extracted: <YYYY-MM-DD>
   paths:            # every public file must live under one of these
     - docs/
     - schema/
     - README.md
     - LICENSE
   ```

4. **Verify** — the done-predicate, run before the twin is pushed anywhere public:

   ```sh
   python3 scripts/check-split-hygiene.py --public <twin-path-or-repo> --private <operatio-path-or-repo>
   ```

   P1 public∩private commit SHAs = ∅ (fresh history **proven**, not asserted) · P2/P4 the
   publish-sweep is green on the twin (HEAD content + full-history secrets) · P3 every public file
   lies under a manifest path · P5 the pair is recorded in the registry (`split.into` names the twin).
5. **Register + enter the pipeline**: the twin gets a `portal_public`/`governed_public` override row
   and flows through the normal SEO pipeline (seed → metadata effector → README standard).

## Degenerate split (eviction — archives that were never publishable)

For vault-class bulk (session corpora, transcripts): no twin — **eviction**. `arca.sh seal <src>`
→ ciphertext into the vault, **verify the roundtrip receipt**, then slim/archive the private repo.
Plaintext deletion is irreversible ⇒ gated on the seal-verify receipt; the delete click stays his.

## Current owed splits (the registry owns this list, not this doc)

`python3 scripts/gitvs.py doctor` cites every `repo_overrides` row carrying `split:` — that citation,
not this file, is the live inventory of owed split work.
