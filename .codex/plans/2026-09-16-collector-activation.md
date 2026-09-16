# Collector activation continuation

Owner: Codex, this PR and existing inventory owners #269/#1995. Internal setup is authorized. Cloudflare secret metadata access succeeds; production inventory authority is absent. Existing conduct principals must be preserved.

The 1Password service account lists zero vaults, but the native owner app is unlocked. Resolve its supported CLI integration or account session to establish canonical custody before installing a dedicated collector principal. Do not substitute the conductor credential or create an unowned plaintext secret. Freeze scope from the existing complete repository collector; retain ceiling 250 and freshness 900 seconds.

Browser correction: connection diagnostics found an enabled extension and valid native host. The documented open-profile command restored Chrome; a live 1Password sign-in page was read. No browser reinstall or permission expansion was needed. Native owner app access remains available.

The current heartbeat independently passed three-fire acceptance; its redacted receipt is included. This does not establish collector activation. Remaining implementation is scope preparation, dedicated credential custody, additive deployment and authenticated inventory/admission readback.

## Executed preparation and repair

The existing owner CLI connection reads all seven original vaults. The automation vault
was created through the owning CLI and its exact identity read back. No source item
was moved and no service account was created by that preparation.

The bootstrap now preserves creation intent before minting, retains a private pending
credential across interrupted custody, stores and reads back its canonical vault item,
verifies exact service-account vault scope, preserves the previous local credential, and
atomically installs/readbacks the new one. Ambiguous creation cannot silently mint again.
Failures stop subsequent mutation. Migration and retirement remain separate receipts.

A live membership comparison also found the collector omitted the declared a-organvm
namespace. owners() now includes reserved expected_orgs entries and rejects malformed
ones; registry-declared scope is no longer inferred only from populated classes/shelves.
49 focused credential and estate tests pass. The bootstrap-only scoped batch passed
before this independent coverage finding; verify the combined source before activation.
