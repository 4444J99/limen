# GitHub Consolidation Runbook — 287→organvm (executable)

Settled decision: collapse all 10 source owners → **one org `organvm`** (spheres become repo
topics, one repo per product, `limen[bot]` App = fleet identity). Everything below is verified +
ready. The ONLY human-gated step is **Step 0** (the `admin:org` scope grant). After that, the rest
is executable repo-by-repo (Claude can run it once scope exists — `gh repo rename`/`transfer` need
admin on source, which the granted scope provides).

## Step 0 — GRANT SCOPE (you, ~30s) — the one wall
```
gh auth refresh -h github.com -s admin:org -s workflow
```
Verify: `gh auth status` shows `admin:org`. Until this, every transfer 403s.

## Step 1 — Resolve the 15 name collisions (so --apply moves all 288, skips 0)
Run the 22 renames + 2 unarchives in `docs/consolidation/COLLISION-RENAMES.md`. Keeps one canonical
per clash (e.g. `meta-organvm/.github` becomes organvm's profile; correctly-owned Pages repos keep
their names), renames the losers to unique slugs. `gh repo rename` preserves redirects (reversible).

## Step 2 — Dry-run again to confirm 0 skips
```
cd ~/Workspace/limen && PYTHONPATH=cli/src python3 scripts/consolidate-github.py
# expect: "288 repos … name collisions: 0"  (was 15 / 37 skipped)
```

## Step 3 — Transfer in WAVES (lowest-risk first; `limen` LAST)
`consolidate-github.py --apply` honors order. Do it in waves so a problem is contained:
1. **Archived + low-value** repos first (smoke test the transfer mechanics on throwaways).
2. **Product repos** (the revenue surfaces) next.
3. **`limen` itself LAST**, deliberately — it's the conductor; moving it mid-run risks the daemon +
   deploy + auto-scale cron. Pause the daemon (`launchctl bootout … com.limen.heartbeat`) for this
   one transfer, then re-point + relaunch.
Verify after each wave: `gh repo list organvm --limit 400 | wc -l` climbs; old URLs 301-redirect.

## Step 4 — Rewrite configs so the fleet keeps working (the don't-break-it step)
```
cd ~/Workspace/limen && PYTHONPATH=cli/src python3 scripts/rewrite-owners.py            # dry-run (833 refs)
PYTHONPATH=cli/src python3 scripts/rewrite-owners.py --apply --emit-remotes /tmp/remotes.sh
bash /tmp/remotes.sh        # repoints the 138 ~/Workspace checkouts (POST-transfer only)
```
This remaps tasks.yaml owners → `organvm/`, fixes `deploy-api.yml`'s `LIMEN_GITHUB_REPO`, and
updates local git remotes. Reversible (`git checkout -- tasks.yaml .github/workflows/deploy-api.yml`).

## Step 5 — Durable cure: limen[bot] GitHub App (decouple CI from personal billing)
Follow `docs/consolidation/SCOPE-AND-APP.md` to create+install the App on `organvm` and wire the
fleet to mint installation tokens. This is what stops a personal-billing lock from ever killing
fleet CI again (the June root cause).

## Rollback (any wave)
`gh repo transfer` back to the source owner (redirects bridge the gap); `git checkout --` restores
the config files; renames reverse with `gh repo rename`. Nothing is ever deleted.

---
**One action from you (`gh auth refresh -s admin:org`) and Claude runs Steps 1–4 repo-by-repo, all 288.**
