# Privacy Containment Receipt

At `2026-07-16T19:52Z`, live remote inspection confirmed that the material associated with Limen
PR #1089 remained reachable at the public default-branch head, while material removed by
application-pipeline PR #78 remained reachable in that public repository's Git history. Both
repositories reported zero public forks.

The two affected repositories, `organvm/limen` and `organvm/application-pipeline`, were temporarily
changed from `PUBLIC` to `PRIVATE`. Authenticated GitHub reads confirmed `isPrivate=true`; fresh
unauthenticated requests to both repository URLs and the application-pipeline Pages URL returned
HTTP 404. No file content, identifier, private path, or personal record is reproduced here.

This is containment, not deletion or reacceptance:

- Limen's current public-serving path still needs a redacted replacement committed through an
  isolated repair PR.
- Both repositories' histories still require a private reachability scan and a deletion packet.
- Rewriting history, requesting cache purges, deleting personal records, or restoring public
  visibility remains a human-gated step after two-copy custody proof.
- Existing local clones and any copies made while the repositories were public remain outside the
  technical reach of this visibility change.
- GitHub documents why force-pushing alone does not remove every cached view or reference:
  <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository>.

Release predicate: current trees contain no sensitive material; two distinct private custody
copies are verified; the owner determines that history action is not required or records its
authorized completion; unauthenticated repository and Pages probes remain unreachable until that
predicate passes; and the corresponding ledger rows and finding crosswalks have durable receipts.
An owner-blocked or pending-human history action remains an honest failed release gate.
