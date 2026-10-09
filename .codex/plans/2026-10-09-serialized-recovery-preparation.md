# Serialized recovery preparation, 2026-10-09

Owner: 4444J99/limen#2739; receipt PR #2834. This is a finite continuation proposal, not execution authorization.

Standards stays with existing A. A released its own writer at 02d6741907bd2f3d5e18600f0816b60298d94125. Prior B/C/D/E checkouts remain unreleased; no correction packet may launch. Preserve draft #496.

Limen preparation stops at absent external staging and expired execution authority. Carry 17,284.892685 seconds as a lower bound; full usage remains unknown. No recovery writer, heavy workload, transfer or retirement started.

Read-only G recipe when the registered staging volume returns:

1. Authenticate volume identity, archive generations, escrow route and exact restored directories using existing private receipts. Do not use a similarly named replacement. Begin with `GIT_NO_LAZY_FETCH=1 git --git-dir "$RESTORED_CACHE" rev-list --objects --all --missing=print`, with bounded process deadline and captured actual exit code. Run once per candidate; no lazy fetch.
2. Enumerate all required missing OIDs against each retained immutable source commit/tree. Record candidate membership, commit, tree, path, expected type/size and source generation in private staging. Resolve every missing OID; unresolved mapping is HOLD. Do not treat candidate archive generation as the source commit for a missing blob.
3. Deduplicate by object identity, checking type and size consistency. Report per-cache count/bytes, shared OIDs/bytes and union OIDs/bytes separately. The historical 300/9,834,457,915 and 562/12,378,670,837 closures are not additive unique bytes. Historical union upper bound is 22,213,128,752 bytes; it is not a measured union.
4. Capacity proposal: require measured external free bytes greater than 10 GiB reserve plus archives/readbacks/restored metadata plus twice the measured unique blob closure plus separately estimated Git storage/pack overhead and native-metadata margin. The historical twice-closure component alone is at most 44,426,257,504 bytes; do not claim that as total capacity required. Shared closure reduces transfer, not logical membership. If the exact envelope or time forecast fails, retain and checkpoint; do not hydrate internal storage.

F execution requires actual finite authorization under the existing owner, supported broker admission and ordinary host/storage admission. Proposed maximum is 1,800 seconds, with at most 600 seconds verification, one candidate and no automatic renewal. Do not inherit the prior pressure override. Estimate full transfer and verification time from actual admitted throughput before starting.

F first recovers and inspects the verified encrypted controller, including its BrokenPipe repair, without executing historical scripts as authority. Reconstruct closure only in private external staging, downloading each blob from the exact immutable source and checking expected bytes and Git object identity before insertion into an isolated recovery copy. Preserve original archives and cache administrative metadata; any added closure is separately recorded. No ref pruning or source-cache mutation.

H must independently audit exact archives, recovered controller and reconstructed closure, stored/native bytes, refs, unique/unreachable objects, LFS/hardlinks, dependencies, and collection disposition. Stored-byte equality does not clear missing-required-git-object. F alone may retire a passing candidate after fresh live ownership/dependency checks and unchanged guards. Record removals, allocated bytes and attributable df/APFS recovery separately; require an unchanged second maintenance pass.

I remains gated on complete immutable collection, both registered Archive4T/T7Recovery devices, finite/heavy admission, and independent restoration including native histories, SQLite sidecars and key routes. Scratch cannot substitute for either replica. Preventive runtime work stays with Domus.
