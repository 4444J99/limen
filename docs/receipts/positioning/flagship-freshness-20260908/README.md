# Flagship proof freshness — 2026-09-08

Owner: [PSP-P05-W04 / #2201](https://github.com/4444J99/limen/issues/2201).
Observation finished at 16:57:46 UTC. All three selected public repositories were resolved to
their current default-branch heads and immutable IDs. Check-run pages were collected completely.

| Selected flagship | Observed head | Reproduction status | Hosted evidence retained |
|---|---|---|---|
| [Limen](limen.json) | `aaa5cad2b6ae` | Not current | No check runs returned on this default-branch commit |
| [Public Records](public_records.json) | `04eb20eeba23` | Not current | Successful gate and scheduled scrape observations; predicate coverage not yet adjudicated |
| [AI Chat Exporter](ai_chat_exporter.json) | `900da0fa256b` | Not current | Successful CI/build observations; predicate coverage not yet adjudicated |

“Not current” means this collection does not provide a freshly accepted reproduction receipt. It
does **not** mean a system is broken, its code is necessarily old, or its hosted green checks are
false. Check labels are insufficient to establish what tests executed. The JSON records preserve
positive hosted evidence and the exact next inspection rather than discarding it.

Fresh accepted reproduction receipts collected: **0 of 3**. Receipt-age distribution: **unknown
for all three**, not zero days. Commit age, maintenance checks and endpoint availability are not
substitutes for test-reproduction age. No age threshold or positive product claim was changed.

This is an explicit negative-status observation under W04's existing acceptance wording. The
formal work issue remains open until its complete acceptance is adjudicated and a genuine
non-circular marked completion receipt is valid. It does not close P05 or validate the other proof
classes. The older C04 correction PR's closed-unmerged state is not treated as landing evidence.

## Collection boundary

GitHub repository/default-branch metadata and commit-qualified check-run APIs were read through
the authenticated CLI. There were 0, 32 and 32 check runs respectively; the two nonempty responses
required two pages each. Maintenance checks are omitted from display but counted in each record.
No workflows or product tests were started and no private repository appeared in this collection.

For a positive refresh, inspect the actual owning predicate, checkout/head binding, executed
steps, environment and captured result. Use an admitted host for any new heavy reproduction.
Append a new dated observation; do not rewrite this one into a passing receipt.
