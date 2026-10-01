The retained Group 04 session journal's missing session-custody gate now passes.
Two registered, physically independent encrypted copies restored successfully and
matched all 1,387 file contents and modes. The second restore used the independent
escrow key. A newly published private release was freshly downloaded, decrypted with
that escrow key, and restored against the same immutable manifest successfully.
The redacted receipts, manifest digest, restoration utility and exact private remote
asset readback are committed in the existing private owner PR.

This acceptance covers the exact session-generated journal only. Complete capture,
metadata acceptance and retirement for the 12-candidate cohort remain false under
the existing owner. No candidate was deleted. The second historical session's existing
two original-vault ciphertext copies were rechecked unchanged by digest and size;
their prior independent restore evidence remains valid.

Multi-scope source support is published in Limen PR #2811. Landing gates and three
unknown Workspace-anchor process identities still prevent certified session release.
The canonical release owner #2763 has the source gate results and next predicates.
