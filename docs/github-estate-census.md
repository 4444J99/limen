# GitHub estate census contract

The GitHub estate census is a source producer for the dynamic work-universe
registry. It consumes the exact owner/repository graph and per-repository PR
pagination established by GITVS; it never uses GitHub search.

Each repository exposes four independently reconciled connections: open pull
requests, open issues, branches, and check states. Every page repeats a stable
`totalCount`, every cursor must advance, identities may not repeat, and the
final node count must equal the advertised total. Repository enumeration has
the same independent cursor receipt. A failed page, moving count, missing
cursor, duplicate identity, or repository-total mismatch makes the source
`partial` and preserves the known-leaf subtotal without claiming it is the
complete leaf count.

Pull requests retain their preservation, fresh-active-custody, or owner-route
classification. Open issues, non-default branches, failed/pending checks, and
untyped or non-actionable PR custody remain distinct debt kinds. Full private
facts stay in a gitignored owner receipt. The tracked projection contains only
aggregate counts, content hashes, and opaque private leaf keys.

The runtime owner report is registered at
`config/progress-sources/github-estate.json` and must be written to
`logs/progress-sources/github-estate.json` by the live adapter:

```bash
python3 scripts/github-estate-census.py --check --json
python3 scripts/github-estate-census.py --check --write
```

Until that
producer receipt exists and is fresh/exhaustive, `limen progress-sources`
correctly reports GitHub-estate coverage debt.
