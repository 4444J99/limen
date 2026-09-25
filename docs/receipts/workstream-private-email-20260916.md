# Admitted receipt publication: private-email recovery

Owner: Limen workstream launcher. Scope: automatically committed admission receipts.

The closeout-global-discovery capsule stopped before provider launch because its
admission commit inherited a private Git email. GitHub rejected publication with
GH007. Account privacy protections and global Git configuration remain unchanged.

The unpublished, receipt-only commit was amended using the authenticated GitHub
account's noreply identity. Normal fast-forward publication succeeded at Domus
commit `fed294eed658f240907d41a5f3987a180a87d63f`. An exact remote-ref check and
an idempotent invocation of the publication gate both passed. No provider session
was launched by this recovery.

The launcher now resolves the authenticated GitHub noreply identity through a
bounded API lookup before creating admission commits, sets author and committer
email only for that commit, and fails closed on lookup failure or malformed
identity. Non-GitHub fixture and owner-native remotes retain their prior behavior.
Generated launchers include the helper; existing hash-bound capsules are not
rewritten in place.

Verification: 15 identity cases cover HTTPS, credential-bearing HTTPS, SSH,
inherited email variables, lookup errors, malformed responses, and non-GitHub
remotes. Three existing generated-launcher/publication regressions also pass.
The real authenticated API expression resolves successfully. Scoped cheap gates
passed after formatting; scoped heavy verification was denied by host admission
with `swap-fraction` (exit 75), not a successful full predicate.

Merge condition: complete the implicated scoped verification under admitted host
capacity before using the owner's exact-head merge rail. The PR owns this pending
verification; the user's original rejected receipt is already recovered remotely.
