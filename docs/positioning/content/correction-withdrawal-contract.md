# Correction and withdrawal contract — staged

This contract is the return path for a claim, source, derivative, or measurement record that becomes inaccurate, expired, private, or insufficiently qualified. It is a preflight control, not a claim that a public artifact currently exists.

## Trigger conditions

- A claim no longer matches its cited source or the source becomes stale.
- A derivative lacks a canonical source, door tag, or required qualification.
- A real incident source cannot pass sanitization or causal-accuracy review.
- A measurement record is synthetic, incomplete, or cannot be tied to a receiving-system receipt.

## Required response

1. Pause the affected staged asset or approved channel; do not strengthen the claim to compensate.
2. Preserve the source reference and the reason for quarantine in the claims-ledger owner.
3. Replace public-safe copy only with a corrected, source-backed version; otherwise withdraw it.
4. Record a withdrawal receipt only after a real, owner-approved external action occurs. A fixture or draft is never a withdrawal receipt.
5. Re-run the package check before the corrected material re-enters staging.

## Non-negotiable boundaries

- A synthetic event remains synthetic after review.
- A missing owner approval cannot be inferred from a clean draft or a green local check.
- Private evidence is not copied into an editorial artifact to make a claim feel stronger.
