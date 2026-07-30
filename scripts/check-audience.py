#!/usr/bin/env python3
"""AUDIENCE drift predicate — every surface faces the world, a collaborator, or nobody.

Decision 4 of the 2026-07-30 PORTVS/ASTRA plan: the partner estate AND totally-solo work each
split themselves into `world` ("me and the world"), `collab` ("me and collab"), and `self`.
`scripts/publication-policy.py` owns the CONTENT half of that axis (the 3-column disposition
matrix). This owns the CUSTODY half: which audience each repo actually faces, and whether the
estate's declarations and GitHub's live state agree about it.

THE AUDIENCE IS DERIVED, NEVER STORED. A third copy of a fact the registry already carries twice
would rot on contact — `sauce_policy.private_classes` already lists `conductor`, whose class
visibility is `public`, which is exactly what a stale duplicate looks like. So:

    observed = world   if the class says public
             = collab  if private AND >=1 grant row in access.yaml
             = self    otherwise

computed at read time and materialized nowhere.

But pure derivation has a blind spot big enough to hide the defect this predicate exists to find: a
partner lane with no grant row derives `self`, and `self` is self-consistent, so a repo the partner
CANNOT SEE certifies green. Intent has to come from somewhere the derivation cannot see. Two
sources, in strict precedence:

  1. DECLARED  — `repo_overrides.<repo>.audience` in estate.yaml. The operator's judgment, in the
                 registry decision 4 names, in the shape that registry already uses for intent
                 (the `publish_candidate: true` flag sitting on those same rows). Authoritative.
  2. SUGGESTED — the constellation register names a person working on a repo. This is a HINT for a
                 human judgment row and nothing more.

The register SUGGESTS; it never decides and this script never writes. That restraint is load
bearing, not stylistic: `derive-streams.py` may derive stream rows from the register because a
wrong stream row is regenerable prose, but a wrong AUDIENCE row is access posture. Drop a project
from the register and a derived `collab` would vanish, the repo would derive `self`, the rung would
read a deliberate human-decided grant as "undeclared exposure" — and per `L-PARTNER-GRANTS` the
machine-runnable direction is REMOVAL. An editorial edit to a people file must never be able to
stage revocation of a partner's access to their own work.

Two severities, because they are two different kinds of wrong:

  BREAK (exit 1)  A structural invariant no human decision can legitimize — a bad audience value,
                  or `collab` declared on a class `access.yaml` forbids from ever carrying a grant.
  OWED  (report)  A real question with a named owner. Surfaced every run, never silently resolved,
                  but it does not halt the estate: holding every PR hostage to an open partner
                  question would be a worse failure than the question. `--strict` exits 1 on these
                  too (the acceptance test and any campaign that wants them closed).

  python3 scripts/check-audience.py            # report
  python3 scripts/check-audience.py --check    # exit 1 on BREAK only
  python3 scripts/check-audience.py --strict   # exit 1 on BREAK or OWED
  python3 scripts/check-audience.py --json     # the full derivation, for a doctor rung to consume
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
ESTATE = ROOT / "institutio" / "github" / "estate.yaml"
ACCESS = ROOT / "institutio" / "github" / "access.yaml"
REGISTER = ROOT / "organs" / "consulting" / "constellation" / "registry.yaml"

AUDIENCES = ("world", "collab", "self")


def _yaml(path: Path) -> dict:
    import yaml

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return {}


def _class_visibility(estate: dict) -> dict[str, str]:
    """class name -> declared visibility (public|private|any)."""
    return {name: str((body or {}).get("visibility") or "any") for name, body in (estate.get("classes") or {}).items()}


def observed_audience(visibility: str, granted: bool) -> str:
    """The derivation, isolated and pure so a doctor rung can import it.

    `any` (contrib_fork / frozen / archived — a fork mirrors upstream, an archive is frozen at
    whatever it was) carries no declared audience of its own and is reported as such by the caller;
    here it resolves like private, the conservative reading.
    """
    if str(visibility).lower() == "public":
        return "world"
    return "collab" if granted else "self"


def register_lanes(register: dict) -> dict[str, str]:
    """repo full-name -> the lane slug that names it. First-match-wins; null repos skipped.

    First-name slugs only — the register is public-safe by construction and this script keeps it
    that way: no login, no display name, no contact detail is read here (`access.yaml` owns the
    grantee identity, and it is a separate file for exactly that reason).
    """
    lanes: dict[str, str] = {}
    for person in register.get("people") or []:
        if not isinstance(person, dict):
            continue
        slug = str(person.get("slug") or "").strip()
        for project in person.get("projects") or []:
            repo = (project or {}).get("repo")
            if repo and slug:
                lanes.setdefault(str(repo), slug)
    return lanes


def derive(estate: dict, access: dict, register: dict) -> dict:
    """The whole picture, per repo, with no side effects and no writes."""
    vis_of = _class_visibility(estate)
    grants = access.get("grants") or {}
    never_grant_classes = set((access.get("policy") or {}).get("never_grant_classes") or [])
    lanes = register_lanes(register)

    rows = []
    for repo, body in sorted((estate.get("repo_overrides") or {}).items()):
        body = body or {}
        cls = str(body.get("class") or "")
        visibility = vis_of.get(cls, "any")
        granted = bool(grants.get(repo))
        rows.append(
            {
                "repo": repo,
                "class": cls,
                "visibility": visibility,
                "granted": granted,
                "declared": body.get("audience"),
                "suggested_by": lanes.get(repo),
                "publish_candidate": bool(body.get("publish_candidate")),
                "never_grantable": cls in never_grant_classes,
                "observed": observed_audience(visibility, granted),
            }
        )
    return {"rows": rows, "never_grant_classes": sorted(never_grant_classes)}


def assess(derivation: dict) -> tuple[list[str], list[str]]:
    """(breaks, owed) — structural invariant violations, and genuine open judgments."""
    breaks: list[str] = []
    owed: list[str] = []

    for r in derivation["rows"]:
        repo, declared = r["repo"], r["declared"]

        # A — schema. A value outside the enum is a typo that would silently mis-route content.
        if declared is not None and declared not in AUDIENCES:
            breaks.append(f"{repo}: audience {declared!r} is not one of {list(AUDIENCES)}")
            continue

        # B — a class ACCESS forbids from ever carrying a grant cannot be declared shared.
        if declared == "collab" and r["never_grantable"]:
            breaks.append(
                f"{repo}: audience 'collab' on class {r['class']!r}, which access.yaml lists in "
                "never_grant_classes — a shared audience it can never actually be granted"
            )
            continue

        # C — declared vs observed. The declaration is the desire; GitHub is the fact.
        if declared and declared != r["observed"]:
            if declared == "collab" and r["observed"] == "self":
                owed.append(
                    f"{repo}: declared 'collab' but nobody is invited — the partner cannot see "
                    "their own lane (staged invite; invites are outbound → L-PARTNER-GRANTS)"
                )
            else:
                owed.append(f"{repo}: declared {declared!r} but observed {r['observed']!r}")

        # D — the judgment collision. A repo cannot be both a shared operation and a solo
        # publication; something has to give, and only the operator can say which.
        intent_collab = declared == "collab" or (declared is None and r["suggested_by"])
        if intent_collab and r["publish_candidate"]:
            owed.append(
                f"{repo}: a partner lane ({r['suggested_by'] or 'declared'}) carrying "
                "publish_candidate — shared operation or solo publication? Register the split and "
                "declare `audience: collab`, or drop the lane and let it publish as 'world'."
            )

        # E — the fourth state the enum lacks. `world` is "public, SOLO"; a public repo with a
        # live grant is neither world nor collab. It is not drift and must NEVER be read as a
        # demand to flip a traction repo private — it is a decision nobody has written down.
        if r["observed"] == "world" and r["granted"]:
            owed.append(
                f"{repo}: public AND granted — 'world+guest', a state the world|collab|self enum "
                "cannot express. Owed: name it, or move the collaboration to a private twin."
            )

    return breaks, owed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 on a structural BREAK only")
    ap.add_argument("--strict", action="store_true", help="exit 1 on BREAK or an OWED judgment")
    ap.add_argument("--json", action="store_true", help="emit the full derivation")
    args = ap.parse_args()

    derivation = derive(_yaml(ESTATE), _yaml(ACCESS), _yaml(REGISTER))
    breaks, owed = assess(derivation)

    if args.json:
        print(json.dumps({**derivation, "breaks": breaks, "owed": owed}, indent=2, sort_keys=True))
        return 1 if breaks or (args.strict and owed) else 0

    counts: dict[str, int] = {}
    for r in derivation["rows"]:
        counts[r["observed"]] = counts.get(r["observed"], 0) + 1
    print(
        f"check-audience: {len(derivation['rows'])} classified repos — "
        + " ".join(f"{k}={counts.get(k, 0)}" for k in AUDIENCES)
    )

    for b in breaks:
        print(f"  BREAK {b}")
    for o in owed:
        print(f"  OWED  {o}")

    if breaks:
        print(f"\ncheck-audience: {len(breaks)} structural break(s) — the estate contradicts itself")
        return 1
    if owed:
        print(
            f"\ncheck-audience: OK — no structural break; {len(owed)} owed judgment(s) above, each "
            "with a named owner. --strict exits 1 on these."
        )
        return 1 if args.strict else 0
    print("check-audience: OK — every declared audience matches GitHub, no owed judgments")
    return 0


if __name__ == "__main__":
    sys.exit(main())
