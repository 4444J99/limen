# Danse moved

Danse Macabre has one source and one public address:

- source: <https://github.com/organvm/the-thing-without-a-name>
- artwork: <https://danse.pages.dev/>

This former application tree is intentionally retired. Its full history remains
recoverable in Git. The repository-level `deploy-danse.yml` workflow is now a
credential-only relay: it checks out the exact canonical OrganVM commit, builds
and verifies that repository's allowlisted Pages artifact, and deploys those
bytes to the `danse` Cloudflare Pages project. No Danse source is maintained
here.
