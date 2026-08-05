#!/usr/bin/env python3
"""
COLLAB-SYNC — the repo_collaborators effector (partner partitioning: grants, not transfers).

Diffs live outside-collaborator access against the ACCESS registry
(institutio/github/access.yaml) and acts in exactly one direction:

  --plan   (default) print the drift and the EXACT commands: invites and role
           downgrades for the operator to fire by hand (outbound and role PUTs
           are his hand — this script never sends an invite), removals the
           machine may run under --apply.
  --apply  remove UNDECLARED access only — collaborators without a grant row,
           their pending invitations, and org outside-collaborator entries with
           no grant anywhere. The exposure-reducing direction, double-dark:
           requires LIMEN_COLLAB_APPLY=1 *and* the estate.yaml approval lever
           (L-PARTNER-GRANTS) — gitvs reconcile never auto-runs this.

Exit: 0 ⟺ no drift; 1 ⟺ drift found (plan) or a removal failed (apply);
      2 ⟺ census unavailable (offline / registry absent); 3 ⟺ --apply refused (unarmed).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gitvs  # noqa: E402 — the census and registry loaders live in one place


def main() -> int:
    ap = argparse.ArgumentParser(description="Diff live collaborator access against the ACCESS registry.")
    ap.add_argument("--apply", action="store_true", help="remove UNDECLARED access (needs LIMEN_COLLAB_APPLY=1)")
    ap.add_argument("--plan", action="store_true", help="explicit alias of the default dry report")
    args = ap.parse_args()

    if args.apply and os.environ.get("LIMEN_COLLAB_APPLY") != "1":
        print("REFUSED: --apply requires LIMEN_COLLAB_APPLY=1 (double-dark) — run the default --plan instead")
        return 3

    estate = gitvs.load_estate()
    access = gitvs.load_access()
    if access is None:
        print("SKIP: no ACCESS registry (institutio/github/access.yaml absent)")
        return 2
    if not access:
        print("DEFECT: ACCESS registry unparseable — class H parity owns this; fix institutio/github/access.yaml")
        return 1

    token = gitvs._token()
    online = token is not None and shutil.which("gh") is not None
    census = gitvs._collaborator_census(estate, access, token, online)
    if not census.get("complete"):
        print("SKIP: census unavailable (offline or gh errors)")
        return 2

    grants = access.get("grants") or {}
    declared_logins = {
        str(g.get("login", "")).lower()
        for rows in grants.values()
        if isinstance(rows, list)
        for g in rows
        if isinstance(g, dict)
    }

    removals: list[tuple[str, list[str]]] = []  # machine-runnable under --apply
    his_hand: list[str] = []  # exact commands the operator fires (invites, role PUTs)

    for repo, obs in sorted((census.get("by_repo") or {}).items()):
        declared = {str(g.get("login", "")).lower(): g for g in (grants.get(repo) or []) if isinstance(g, dict)}
        for c in obs.get("outside") or []:
            login = str(c.get("login") or "")
            role = gitvs.ROLE_NAME_TO_GRANT.get(str(c.get("role")), str(c.get("role")))
            g = declared.get(login.lower())
            if g is None:
                removals.append(
                    (
                        f"{repo}: {login} ({role}) has no grant row",
                        ["api", "-X", "DELETE", f"/repos/{repo}/collaborators/{login}"],
                    )
                )
            elif gitvs.GRANT_ROLE_RANK.get(role, 99) > gitvs.GRANT_ROLE_RANK.get(str(g.get("role")), -1):
                his_hand.append(
                    f"# {repo}: {login} live role {role} exceeds declared {g.get('role')} — downgrade:\n"
                    f"gh api -X PUT /repos/{repo}/collaborators/{login} -f permission={g.get('role')}"
                )
        live = {str(c.get("login") or "").lower() for c in obs.get("outside") or []}
        pending = {str(i.get("login") or "").lower(): i for i in (obs.get("invitations") or [])}
        for inv_login, inv in sorted(pending.items()):
            if inv_login not in declared:
                removals.append(
                    (
                        f"{repo}: pending invitation for {inv.get('login')} has no grant row",
                        ["api", "-X", "DELETE", f"/repos/{repo}/invitations/{inv.get('id')}"],
                    )
                )
        for login_l, g in sorted(declared.items()):
            if login_l not in live and login_l not in pending:
                his_hand.append(
                    f"# {repo}: {g.get('login')} declared but absent — staged invite (outbound = your hand):\n"
                    f"gh api -X PUT /repos/{repo}/collaborators/{g.get('login')} -f permission={g.get('role')}"
                )

    for org, roll in sorted((census.get("org_outside") or {}).items()):
        for login in roll or []:
            if str(login).lower() not in declared_logins:
                removals.append(
                    (
                        f"org {org}: outside collaborator {login} has no grant row anywhere",
                        ["api", "-X", "DELETE", f"/orgs/{org}/outside_collaborators/{login}"],
                    )
                )

    if not removals and not his_hand:
        print("✓ collab-sync: drift == ∅ — live access matches the ACCESS registry")
        return 0

    failed = 0
    for desc, argv in removals:
        if args.apply:
            r = gitvs._gh(argv, token, timeout=30)
            verdict = "removed" if r.returncode == 0 else f"FAILED ({(r.stderr or '').strip()[:80]})"
            failed += 0 if r.returncode == 0 else 1
            print(f"✗ {desc} → {verdict}")
        else:
            print(f"✗ {desc}\n  would run: gh " + " ".join(argv))
    for cmd in his_hand:
        print(cmd)
    if his_hand:
        print(f"→ {len(his_hand)} staged command(s) above are L-PARTNER-GRANTS work — fire them deliberately.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
