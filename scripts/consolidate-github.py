#!/usr/bin/env python3
"""consolidate-github — collapse the fragmented 11-owner GitHub estate into ONE org.

Per the deduced structure decision: identity is from the remote, the "sphere" is metadata
(a repo TOPIC), not infrastructure (an org). So every repo moves into the single canonical
org `organvm` (already yours, empty), tagged with its source-sphere as a topic.

SAFE BY DEFAULT: dry-run prints the exact transfer table + flags name collisions. It executes
NOTHING without --apply, and --apply is gated on the user. GitHub repo transfer preserves
issues/PRs/stars and redirects old URLs (reversible: transfer back). Never deletes.

  python3 scripts/consolidate-github.py            # dry-run plan (read-only)
  python3 scripts/consolidate-github.py --apply     # ⚠ GATED: actually transfer + topic
"""
import json, subprocess, sys
from collections import defaultdict

TARGET = "organvm"
# every source owner; personal account + the 10 orgs. TARGET itself is excluded.
OWNERS = ["4444J99", "a-organvm", "meta-organvm",
          "organvm-i-theoria", "organvm-ii-poiesis", "organvm-iii-ergon",
          "organvm-iv-taxis", "organvm-v-logos", "organvm-vi-koinonia",
          "organvm-vii-kerygma"]
APPLY = "--apply" in sys.argv


def gh_json(args, t=60):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=t)
    try:
        return json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return []


def sphere_topic(owner):
    # the source owner becomes a topic so nothing is lost when the org boundary dissolves
    return owner.replace("organvm-", "sphere-").replace("4444J99", "personal").lower()


def main():
    plan = []          # (owner, repo, topic)
    by_name = defaultdict(list)
    for owner in OWNERS:
        if owner == TARGET:
            continue
        repos = gh_json(["repo", "list", owner, "--limit", "500", "--json", "name,isArchived"])
        for r in repos:
            name = r["name"]
            plan.append((owner, name, sphere_topic(owner), r.get("isArchived", False)))
            by_name[name.lower()].append(f"{owner}/{name}")

    collisions = {n: v for n, v in by_name.items() if len(v) > 1}
    print(f"=== consolidation plan → {TARGET} ===")
    print(f"  {len(plan)} repos across {len(OWNERS)} owners")
    print(f"  name collisions (must rename before transfer): {len(collisions)}")
    for n, v in sorted(collisions.items()):
        print(f"    ⚠ '{n}': {', '.join(v)}")
    print(f"\n  sample transfers (first 20):")
    for owner, name, topic, arch in plan[:20]:
        flag = " [archived]" if arch else ""
        print(f"    {owner}/{name}{flag}  →  {TARGET}/{name}   +topic:{topic}")
    if len(plan) > 20:
        print(f"    … +{len(plan)-20} more")

    if not APPLY:
        print(f"\nDRY-RUN — nothing executed. Collisions above must be resolved first.")
        print(f"Re-run with --apply (GATED) to transfer non-colliding repos + set topics.")
        return

    print(f"\n⚠ --apply: transferring NON-colliding repos into {TARGET} …")
    moved = skipped = 0
    colliding_names = set(collisions.keys())
    for owner, name, topic, _arch in plan:
        if name.lower() in colliding_names:
            skipped += 1
            continue
        tr = subprocess.run(["gh", "api", "-X", "POST", f"/repos/{owner}/{name}/transfer",
                             "-f", f"new_owner={TARGET}"], capture_output=True, text=True, timeout=60)
        if tr.returncode == 0:
            subprocess.run(["gh", "api", "-X", "PUT", f"/repos/{TARGET}/{name}/topics",
                            "-f", f"names[]={topic}"], capture_output=True, text=True, timeout=30)
            moved += 1
            print(f"  ✓ {owner}/{name} → {TARGET}/{name} (+{topic})")
        else:
            print(f"  ✗ {owner}/{name}: {tr.stderr.strip()[:70]}")
    print(f"\ndone: moved {moved}, skipped {skipped} (collisions). Old URLs auto-redirect.")


if __name__ == "__main__":
    main()
