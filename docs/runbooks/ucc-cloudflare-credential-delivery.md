# UCC Cloudflare credential delivery

CLAVIS owns credential provenance and delivery under [Limen #320](https://github.com/4444J99/limen/issues/320).
[UCC #239](https://github.com/organvm-iii-ergon/public-record-data-scrapper/issues/239)
owns staging resources, bindings, migrations, and deployment. The selected platform and authority
are already established; a failed capability probe is a provisioning defect, not a new platform decision.

The UCC entry in `scripts/creds-hydrate.py` uses the existing
`op://Personal/Cloudflare API Token/credential` source and delivers only
`organvm-iii-ergon/public-record-data-scrapper:CLOUDFLARE_API_TOKEN`.
The approved staging account is pinned in that entry and UCC's configuration.
Ordinary hydration remains presence-guarded. To replace an existing stale or insufficiently scoped
CI secret after repairing its canonical source, use the exact-sink operation:

```bash
python3 scripts/creds-hydrate.py --dry-run --refresh-ci-secret gh:organvm-iii-ergon/public-record-data-scrapper:CLOUDFLARE_API_TOKEN
python3 scripts/creds-hydrate.py --apply --refresh-ci-secret gh:organvm-iii-ergon/public-record-data-scrapper:CLOUDFLARE_API_TOKEN
```

The remote execution path is `.github/workflows/ucc-cloudflare-delivery.yml`. Accepted-main changes
to its implementation automatically run a read-only account/D1 probe using Limen's existing
`CLOUDFLARE_API_TOKEN` Actions cache, independently of 1Password availability. It reports only the
candidate verdict and whether App-delivery credentials are configured. An exact-main manual
`apply` run uses `scripts/gh-app-token.sh --repo organvm-iii-ergon/public-record-data-scrapper --app-only --require-secrets-write`
to establish the destination principal and verify its returned Secrets-write grant before delivery.
The assertion does not expand the App's permissions: the ordinary governor/finalizer App profile
does not declare Secrets-write and cannot satisfy it unless a credential-delivery principal with
that existing authorized grant is configured. GitHub's ordinary workflow token is never
treated as cross-repository secret-write authority. Missing App configuration or failed target
resolution leaves the destination unchanged; no new token source is inferred or minted.

Execute on the established credential host with promptless 1Password access and GitHub secret-write
capability for UCC. The first command reads no secret. The second reads only the declared source,
checks the exact approved Cloudflare account and D1 list endpoint, and streams the token to GitHub
via stdin. It does not update other repository secrets, the environment cache, or tool-auth files.
Unknown, disabled, or ambiguous sinks fail before authentication; source, preflight, and delivery
failures return nonzero. The existing destination remains intact when the preflight fails.

The account/D1 probes use GET requests only, reject redirects, limit response size and duration,
and never print the credential or raw provider errors. Passing them proves account identity and
D1 read access. It does not prove D1/KV/R2/Access write authority, resource existence, or deployment.
Run UCC's own staging provisioning/deployment workflow after delivery and retain its exact run
receipt. A successful GitHub secret write alone cannot close UCC #239.

If promptless source access is unavailable, CLAVIS's existing `creds-provision.py` bootstrap owns
that repair. Do not copy secrets into issues, PRs, logs, or a second credential store. This runbook
does not authorize changing token permissions or trigger a credential write by itself.
