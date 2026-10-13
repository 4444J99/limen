# Reconcile the retained recovery delivery

Owner: Limen #2840; dependent ops#6; independent draft GES #496.

The human's continuation responds to the explicit request to reclaim the retained
#2856 checkout and authorize at most 600 additional CLI-verification seconds.
Keep the original exhausted 600-second ledger and the separate 60-second extension;
do not reset either or the 120 cumulative agent-minute outcome cap. This authority
does not replenish ops reservations or unknown GES allowance.

Reclaim the clean retained checkout from published #2856 head
64d0fb98ed356ca8a1c555f02b55a0c5eea1f04d, preserving its branch and objects.
Restore published #2840 head 8e1cef4d6dfa5ab898762d496a7df5860cea16a7 on an
isolated reconciliation branch. The PR base anchor
66b2ee71a1075d652a32a44186d01db258c8adce was reconciled first, but is not live
main. Integrate the captured live main snapshot
d1e15e2506f97147a20d7aaa3387bb2aa67473ff without further moving-main rewrites.
Preserve the accepted shared runtime pool and all heartbeat fixes. Preserve
the current optional policy-custody route and its tests alongside the new allowance
route, default fingerprint-only readback, authorization and no-store behavior.

Run implicated final-tree verification under machine-wide heavy admission, bounded
output and hard subprocess deadlines; preserve actual exits and retained failures.
Reuse unchanged passing shards only with matching input/environment/gate identity.
Push the reconciled successor once to #2840. Merge its exact head only after the
required predicates pass, then use the managed immutable installation route.

Live policy fingerprint 0f9ea6155e0c5d1c0a823a91d6c8fa01f3d8126c9578a48df803e2501aec0587
does not match the specified native installation record. No replacement is allowed.
Retain current secrets/configuration and every approval/limit. Deployment, policy
generation reconciliation, admission, hosted idempotency and incident acceptance
remain distinct. GES implementation stays held without exhaustive accounting and
positive checkout custody. No histories, databases or custody partials are removed.
