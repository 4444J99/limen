#!/usr/bin/env python3
"""
Constellation DAG seeder — the CONST- board program, emitted through TABVLARIVS.

Reads the constellation register, cross-checks every planned task against it,
lints person-scoped tasks against the private overlay's boundaries (a task
that smells of payment for a no-money person, or outreach for a dormant one,
is refused at the source), then hands each MISSING task to
`tabularius.submit_task_upsert()` — the single-writer intake seam. Ids are
stable, so re-running never duplicates: present ids are skipped here and the
keeper's `absent` precondition quarantines any race.

Dry-run by default (validates every task through the real intake contract and
work-loan underwriting without emitting). `--live` submits.

Usage:
  organs/consulting/constellation/seed-tasks.py            # dry-run
  organs/consulting/constellation/seed-tasks.py --live     # emit tickets
  organs/consulting/constellation/seed-tasks.py --check    # exit 0 iff every task already on board
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "cli" / "src"))

REGISTRY = HERE / "registry.yaml"
OVERLAY = Path(
    os.environ.get(
        "LIMEN_CONSTELLATION_OVERLAY",
        str(Path.home() / "Workspace" / "_people-private" / "constellation" / "registry-private.yaml"),
    )
)
CHECK = "organs/consulting/constellation/check.py"

MONEY_TERMS = ("invoice", "charge", "payment", "bill ", "price", "retainer", "spend")
OUTREACH_TERMS = ("outreach", "send a message", "dm ", "email him", "email her", "contact him", "contact her")

# Program DAG — one row per CONST- task. `slug` binds a row to a register
# person (None = program-level); every dep must name another row's id.
# (id, slug, title, repo, type, priority, cost, deps, predicate, value_case)
TASKS: list[dict] = [
    dict(
        id="CONST-CORPUS-REFRESH",
        slug=None,
        title="Populate the conversation corpus (live pulls + staged bundle imports)",
        repo="organvm/limen",
        type="code",
        priority="high",
        cost=10,
        deps=[],
        predicate=f"{CHECK} corpus-refresh",
        value="every project dossier draws on the full brainstorm corpus instead of memory",
    ),
    # --- interaction protocols (the review-first layer) ---
    dict(
        id="CONST-JESSICA-PROTO",
        slug="jessica",
        title="Jessica interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="high",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto jessica",
        value="live co-founder negotiation steered by the proven conversation record",
    ),
    dict(
        id="CONST-ROB-PROTO",
        slug="rob",
        title="Rob interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="high",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto rob",
        value="three active lanes (chess, fitness, game) share one grounded interaction policy",
    ),
    dict(
        id="CONST-MADDIE-PROTO-REFRESH",
        slug="maddie",
        title="Re-verify the maddie protocol baseline and advance the review cursor",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="medium",
        cost=5,
        deps=[],
        predicate=f"{CHECK} proto maddie",
        value="the template protocol stays PROVEN while the funnel lane runs",
    ),
    dict(
        id="CONST-CHARLES-PROTO",
        slug="charles",
        title="Charles interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="medium",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto charles",
        value="relationship-first lane encoded so every agent honors the standing boundaries",
    ),
    dict(
        id="CONST-SCOTT-PROTO",
        slug="scott",
        title="Scott interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="medium",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto scott",
        value="partnership terms for the cannibalizer grounded in the actual record",
    ),
    dict(
        id="CONST-ARI-PROTO",
        slug="ari",
        title="Ari interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="medium",
        cost=10,
        deps=[],
        predicate=f"{CHECK} proto ari",
        value="host interface stays inside its weekly budget with a grounded policy",
    ),
    dict(
        id="CONST-DUSTIN-PROTO",
        slug="dustin",
        title="Dustin interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="low",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto dustin",
        value="demand evidence for two idea-stage ventures before any build spend",
    ),
    dict(
        id="CONST-DAVID-PROTO",
        slug="david",
        title="David interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="low",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto david",
        value="creative-collaborator lane grounded before auditor/OS work is scoped",
    ),
    dict(
        id="CONST-MONFORTE-PROTO",
        slug="john-m",
        title="John M. interaction protocol from the archived record (no contact)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="low",
        cost=20,
        deps=[],
        predicate=f"{CHECK} proto john-m",
        value="dormant channel read before any finance-gaming idea is entertained",
    ),
    # --- T1: Jessica / Styx ---
    dict(
        id="CONST-STYX-DOSSIER",
        slug="jessica",
        title="Styx brainstorm dossier from the conversation corpus",
        repo="organvm/peer-audited--behavioral-blockchain",
        type="content",
        priority="high",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier jessica styx",
        value="every scattered Styx idea lands in one public-safe dossier the build consumes",
    ),
    dict(
        id="CONST-STYX-MVP",
        slug="jessica",
        title="Drive ask-styx to a demoable MVP",
        repo="organvm/peer-audited--behavioral-blockchain",
        type="code",
        priority="high",
        cost=60,
        deps=["CONST-STYX-DOSSIER", "CONST-JESSICA-PROTO"],
        predicate=f"{CHECK} stage jessica styx mvp",
        value="the co-founder deal gets a demoable product while terms are negotiated",
    ),
    dict(
        id="CONST-STYX-FACE",
        slug="jessica",
        title="Styx-branded public face on the product repo",
        repo="organvm/peer-audited--behavioral-blockchain",
        type="content",
        priority="high",
        cost=15,
        deps=["CONST-STYX-MVP"],
        predicate=f"{CHECK} face-brand organvm/peer-audited--behavioral-blockchain styx",
        value="the product is discoverable under its own name for the 18k audience pivot",
    ),
    dict(
        id="CONST-STYX-FUNNEL",
        slug="jessica",
        title="Styx funnel instance wired through the Niche-Funnel Engine",
        repo="organvm/limen",
        type="content",
        priority="high",
        cost=20,
        deps=["CONST-STYX-FACE"],
        predicate=f"{CHECK} funnel organs/consulting/funnel/instances/jessica-styx.yaml",
        value="discovery-to-offer path exists the day the deal closes",
    ),
    # --- T1: Rob ---
    dict(
        id="CONST-HOKAGE-DOSSIER",
        slug="rob",
        title="Hokage Chess brainstorm dossier from the conversation corpus",
        repo="organvm/hokage-chess",
        type="content",
        priority="high",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier rob hokage-chess",
        value="the 144 recovered strategy docs and chat brainstorms converge in one dossier",
    ),
    dict(
        id="CONST-HOKAGE-FACE",
        slug="rob",
        title="Hokage Chess public face refresh",
        repo="organvm/hokage-chess",
        type="content",
        priority="high",
        cost=15,
        deps=["CONST-ROB-PROTO"],
        predicate=f"{CHECK} face-brand organvm/hokage-chess hokage",
        value="the chess lane presents as a product, not a code dump",
    ),
    dict(
        id="CONST-ROB-FUNNEL",
        slug="rob",
        title="Extend the rob-fitness funnel instance with the Hokage offer ladder",
        repo="organvm/limen",
        type="content",
        priority="high",
        cost=20,
        deps=["CONST-ROB-PROTO"],
        predicate=f"{CHECK} funnel organs/consulting/funnel/instances/rob-fitness.yaml",
        value="the proven BODi shape carries both of Rob's earning lanes",
    ),
    dict(
        id="CONST-TATO-DOSSIER",
        slug="rob",
        title="Micro Tato brainstorm dossier from the conversation corpus",
        repo="organvm/micro-tato",
        type="content",
        priority="medium",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier rob micro-tato",
        value="the game lane's scattered ideas become a buildable backlog",
    ),
    dict(
        id="CONST-SCE-DOSSIER",
        slug="rob",
        title="Sales & client-management engine brainstorm dossier from the conversation corpus",
        repo="organvm/limen",
        type="content",
        priority="medium",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier rob sales-client-engine",
        receipt="git:organvm/limen:organs/consulting/constellation/registry.yaml",
        value="Rob's fourth lane recovered from scattered chat brainstorms into a buildable decision base",
    ),
    dict(
        id="CONST-TATO-FACE",
        slug="rob",
        title="Micro Tato public face refresh",
        repo="organvm/micro-tato",
        type="content",
        priority="medium",
        cost=10,
        deps=["CONST-ROB-PROTO"],
        predicate=f"{CHECK} face-brand organvm/micro-tato brotato",
        value="the beta reads as a playable game with a clear next step",
    ),
    # --- T1: Maddie (funnel only — build lane closed by her own record) ---
    dict(
        id="CONST-SPIRAL-DOSSIER",
        slug="maddie",
        title="Spiral brainstorm dossier from the conversation corpus",
        repo="organvm/sovereign-systems--elevate-align",
        type="content",
        priority="medium",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier maddie spiral",
        value="the spiral archive and chat brainstorms are consolidated without new build spend",
    ),
    dict(
        id="CONST-SPIRAL-FUNNEL",
        slug="maddie",
        title="Spiral funnel instance wired through the Niche-Funnel Engine",
        repo="organvm/limen",
        type="content",
        priority="high",
        cost=15,
        deps=["CONST-MADDIE-PROTO-REFRESH"],
        predicate=f"{CHECK} funnel organs/consulting/funnel/instances/maddie-spiral.yaml",
        value="the live site converts; the lane earns without further unpaid build",
    ),
    # --- T1: Your-Fit-Tailored (pilot-ready venture) ---
    dict(
        id="CONST-YFT-FACE",
        slug="charles",
        title="Your-Fit-Tailored face fix: purge stale org links, showcase Epoch 0",
        repo="organvm/your-fit-tailored",
        type="content",
        priority="high",
        cost=10,
        deps=[],
        predicate=f"{CHECK} face-clean organvm/your-fit-tailored organvm-iii-ergon",
        value="a pilot-ready venture stops pointing visitors at empty orgs",
    ),
    dict(
        id="CONST-YFT-DOSSIER",
        slug="charles",
        title="Your-Fit-Tailored brainstorm dossier (co-creation provenance stays private)",
        repo="organvm/your-fit-tailored",
        type="content",
        priority="medium",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier charles your-fit-tailored",
        value="Epoch-1 build starts from the complete idea record",
    ),
    dict(
        id="CONST-YFT-EPOCH1",
        slug="charles",
        title="Execute the YFT Epoch-1 foundation build (Airtable+Retool kit, software half only)",
        repo="organvm/your-fit-tailored",
        type="code",
        priority="high",
        cost=80,
        deps=["CONST-YFT-DOSSIER"],
        predicate=f"{CHECK} stage charles your-fit-tailored mvp",
        value="the closest revenue-validation event in the constellation becomes executable",
    ),
    # --- T2: Charles / Mirror Mirror ---
    dict(
        id="CONST-MM-DOSSIER",
        slug="charles",
        title="Mirror Mirror brainstorm dossier from the conversation corpus",
        repo="organvm/mirror-mirror",
        type="content",
        priority="medium",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier charles mirror-mirror",
        value="the try-on platform's scattered concept record is consolidated",
    ),
    dict(
        id="CONST-MM-VISIBILITY",
        slug="charles",
        title="Mirror Mirror visibility-drift decision packet (live PUBLIC vs registry private)",
        repo="organvm/limen",
        type="content",
        priority="medium",
        cost=5,
        deps=[],
        predicate=f"{CHECK} decision-packet charles mirror-mirror-visibility",
        value="the estate registry and the live repo stop disagreeing about exposure",
    ),
    dict(
        id="CONST-MM-FACE",
        slug="charles",
        title="Mirror Mirror public face refresh",
        repo="organvm/mirror-mirror",
        type="content",
        priority="medium",
        cost=15,
        deps=["CONST-MM-VISIBILITY", "CONST-CHARLES-PROTO"],
        predicate=f"{CHECK} face-brand organvm/mirror-mirror try-on",
        value="the beauty-tech lane presents to its named buyer class",
    ),
    # --- T2: Scott / Content Cannibalizer ---
    dict(
        id="CONST-CANNIBAL-DOSSIER",
        slug="scott",
        title="Content Cannibalizer brainstorm dossier from the conversation corpus",
        repo="organvm/content-engine--asset-amplifier",
        type="content",
        priority="medium",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier scott content-cannibalizer",
        value="the partnership build starts from the recorded intent, not recollection",
    ),
    dict(
        id="CONST-CANNIBAL-FACE",
        slug="scott",
        title="Content Cannibalizer public face (post publish-wave clearance)",
        repo="organvm/content-engine--asset-amplifier",
        type="content",
        priority="medium",
        cost=15,
        deps=["CONST-SCOTT-PROTO"],
        predicate=f"{CHECK} face-state scott content-cannibalizer readme",
        value="the yield engine becomes showable to its co-creator's clients",
    ),
    dict(
        id="CONST-CANNIBAL-FUNNEL",
        slug="scott",
        title="Content Cannibalizer funnel instance",
        repo="organvm/limen",
        type="content",
        priority="medium",
        cost=20,
        deps=["CONST-CANNIBAL-FACE"],
        predicate=f"{CHECK} funnel organs/consulting/funnel/instances/scott-cannibalizer.yaml",
        value="design-side demand routes into a working offer ladder",
    ),
    # --- T2: Ari / podcast suite ---
    dict(
        id="CONST-HOSPES-DOSSIER",
        slug="ari",
        title="Podcast-suite brainstorm dossier from the conversation corpus",
        repo="organvm/hospes",
        type="content",
        priority="medium",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier ari podcast-suite",
        value="the guest-ops OS roadmap draws on the recorded show conversations",
    ),
    dict(
        id="CONST-HOSPES-FACE-SPLIT",
        slug="ari",
        title="hospes public face split (vault transcripts stay private)",
        repo="organvm/hospes",
        type="code",
        priority="medium",
        cost=30,
        deps=["CONST-ARI-PROTO"],
        predicate=f"{CHECK} face-state ari podcast-suite readme",
        value="the suite becomes rentable form while the operation stays the moat",
    ),
    # --- T3: protocol-gated demand reviews ---
    dict(
        id="CONST-DUSTIN-DEMAND-REVIEW",
        slug="dustin",
        title="Dustin demand-evidence memo from the protocol review",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=5,
        deps=["CONST-DUSTIN-PROTO"],
        predicate=f"{CHECK} decision-packet dustin demand-review",
        value="DSP and consulting ventures are promoted or parked on evidence",
    ),
    dict(
        id="CONST-DAVID-DEMAND-REVIEW",
        slug="david",
        title="David demand-evidence memo from the protocol review",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=5,
        deps=["CONST-DAVID-PROTO"],
        predicate=f"{CHECK} decision-packet david demand-review",
        value="the auditor idea is scoped from the recorded interest, or parked",
    ),
    dict(
        id="CONST-VICTOROFF-FACE",
        slug="david",
        title="Victoroff-OS review-class + public-face decision packet",
        repo="organvm/victoroff-os",
        type="content",
        priority="low",
        cost=10,
        deps=["CONST-DAVID-PROTO"],
        predicate=f"{CHECK} decision-packet david victoroff-visibility",
        value="an unreviewed private repo gets an owned exposure decision",
    ),
    dict(
        id="CONST-MONFORTE-REVIEW",
        slug="john-m",
        title="Dormant-channel memo from the John M. protocol (read-only; no build)",
        repo="organvm/limen",
        type="content",
        priority="backlog",
        cost=5,
        deps=["CONST-MONFORTE-PROTO"],
        predicate=f"{CHECK} decision-packet john-m dormant-review",
        value="the finance-gaming idea space is read from the record and closed or parked",
    ),
    # --- wave 2 (operator-named 2026-07-22): T3 protocol-first ---
    dict(
        id="CONST-JOHNF-PROTO",
        slug="john-f",
        title="John F. interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="low",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto john-f",
        value="the finance-niche record is read before any shared idea is entertained",
    ),
    dict(
        id="CONST-JOHNF-DEMAND-REVIEW",
        slug="john-f",
        title="John F. demand-evidence memo from the protocol review",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=5,
        deps=["CONST-JOHNF-PROTO"],
        predicate=f"{CHECK} decision-packet john-f demand-review",
        value="the john-f finance-gaming idea space is promoted or parked on evidence",
    ),
    dict(
        id="CONST-MIKES-PROTO",
        slug="mike-s",
        title="Mike S. interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="low",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto mike-s",
        value="the security-firm lane is scoped from the recorded relationship, not recollection",
    ),
    dict(
        id="CONST-SECURITY-DOSSIER",
        slug="mike-s",
        title="Security-firm brainstorm dossier from the conversation corpus",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier mike-s security-firm",
        receipt="git:organvm/limen:organs/consulting/constellation/registry.yaml",
        value="scattered security-firm ideas become one buildable decision base",
    ),
    dict(
        id="CONST-MIKES-DEMAND-REVIEW",
        slug="mike-s",
        title="Mike S. demand-evidence memo from the protocol review",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=5,
        deps=["CONST-MIKES-PROTO"],
        predicate=f"{CHECK} decision-packet mike-s demand-review",
        value="the security-firm venture is promoted or parked on evidence",
    ),
    dict(
        id="CONST-AARON-PROTO",
        slug="aaron",
        title="Aaron interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="low",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto aaron",
        value="the education/writing cluster is grounded in the actual record",
    ),
    dict(
        id="CONST-AARON-EDU-DOSSIER",
        slug="aaron",
        title="Education-suite brainstorm dossier (aaron) from the conversation corpus",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier aaron education-suite",
        receipt="git:organvm/limen:organs/consulting/constellation/registry.yaml",
        value="the education-domain brainstorms with aaron land in one decision base",
    ),
    dict(
        id="CONST-AARON-DEMAND-REVIEW",
        slug="aaron",
        title="Aaron demand-evidence memo from the protocol review",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=5,
        deps=["CONST-AARON-PROTO"],
        predicate=f"{CHECK} decision-packet aaron demand-review",
        value="education-suite scope is promoted or parked on evidence; further cluster names surface here",
    ),
    dict(
        id="CONST-CHRIS-PROTO",
        slug="chris",
        title="Chris interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="low",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto chris",
        value="the education/writing cluster is grounded in the actual record",
    ),
    dict(
        id="CONST-CHRIS-EDU-DOSSIER",
        slug="chris",
        title="Education-suite brainstorm dossier (chris) from the conversation corpus",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier chris education-suite",
        receipt="git:organvm/limen:organs/consulting/constellation/registry.yaml",
        value="the education-domain brainstorms with chris land in one decision base",
    ),
    dict(
        id="CONST-CHRIS-DEMAND-REVIEW",
        slug="chris",
        title="Chris demand-evidence memo from the protocol review",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=5,
        deps=["CONST-CHRIS-PROTO"],
        predicate=f"{CHECK} decision-packet chris demand-review",
        value="education-suite scope is promoted or parked on evidence; further cluster names surface here",
    ),
    dict(
        id="CONST-SHARI-PROTO",
        slug="shari",
        title="Shari interaction protocol (entity profile + dialogue persona)",
        repo="organvm/relationship-pipeline",
        type="content",
        priority="low",
        cost=15,
        deps=[],
        predicate=f"{CHECK} proto shari",
        value="the party-game lane is scoped from the recorded relationship, not recollection",
    ),
    dict(
        id="CONST-PARTY-DOSSIER",
        slug="shari",
        title="Party-game-suite brainstorm dossier from the conversation corpus",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=10,
        deps=["CONST-CORPUS-REFRESH"],
        predicate=f"{CHECK} dossier shari party-game-suite",
        receipt="git:organvm/limen:organs/consulting/constellation/registry.yaml",
        value="scattered party-game ideas become one buildable decision base",
    ),
    dict(
        id="CONST-SHARI-DEMAND-REVIEW",
        slug="shari",
        title="Shari demand-evidence memo from the protocol review",
        repo="organvm/limen",
        type="content",
        priority="low",
        cost=5,
        deps=["CONST-SHARI-PROTO"],
        predicate=f"{CHECK} decision-packet shari demand-review",
        value="the party-game-suite venture is promoted or parked on evidence",
    ),
    # Monument stage — one portfolio case study per project, gated behind its
    # public face. The register row carries the case_study pointer; the
    # portfolio repo owns the artifact's layout.
    dict(
        id="CONST-STYX-CASESTUDY",
        slug="jessica",
        title="Styx case study for the portfolio",
        repo="organvm/portfolio",
        type="content",
        priority="low",
        cost=8,
        deps=["CONST-STYX-FACE"],
        predicate=f"{CHECK} casestudy jessica styx",
        value="the styx build becomes a written portfolio monument once its face lands",
    ),
    dict(
        id="CONST-HOKAGE-CASESTUDY",
        slug="rob",
        title="Hokage Chess case study for the portfolio",
        repo="organvm/portfolio",
        type="content",
        priority="low",
        cost=8,
        deps=["CONST-HOKAGE-FACE"],
        predicate=f"{CHECK} casestudy rob hokage-chess",
        value="the recovered strategy-doc build story rides the portfolio surface",
    ),
    dict(
        id="CONST-TATO-CASESTUDY",
        slug="rob",
        title="Micro Tato case study for the portfolio",
        repo="organvm/portfolio",
        type="content",
        priority="low",
        cost=8,
        deps=["CONST-TATO-FACE"],
        predicate=f"{CHECK} casestudy rob micro-tato",
        value="the game build joins the portfolio as a shipped-with-a-partner proof",
    ),
    dict(
        id="CONST-MM-CASESTUDY",
        slug="charles",
        title="Mirror Mirror case study for the portfolio",
        repo="organvm/portfolio",
        type="content",
        priority="low",
        cost=8,
        deps=["CONST-MM-FACE"],
        predicate=f"{CHECK} casestudy charles mirror-mirror",
        value="the mirror-mirror build story becomes a portfolio monument",
    ),
    dict(
        id="CONST-YFT-CASESTUDY",
        slug="charles",
        title="Your Fit Tailored case study for the portfolio",
        repo="organvm/portfolio",
        type="content",
        priority="low",
        cost=8,
        deps=["CONST-YFT-FACE"],
        predicate=f"{CHECK} casestudy charles your-fit-tailored",
        value="the your-fit-tailored build story becomes a portfolio monument",
    ),
    dict(
        id="CONST-CANNIBAL-CASESTUDY",
        slug="scott",
        title="Content Cannibalizer case study for the portfolio",
        repo="organvm/portfolio",
        type="content",
        priority="low",
        cost=8,
        deps=["CONST-CANNIBAL-FACE"],
        predicate=f"{CHECK} casestudy scott content-cannibalizer",
        value="the cannibalizer build joins the portfolio once its face is split out",
    ),
    dict(
        id="CONST-HOSPES-CASESTUDY",
        slug="ari",
        title="Podcast suite case study for the portfolio",
        repo="organvm/portfolio",
        type="content",
        priority="low",
        cost=8,
        deps=["CONST-HOSPES-FACE-SPLIT"],
        predicate=f"{CHECK} casestudy ari podcast-suite",
        value="the podcast-suite build gets its public monument after the face split",
    ),
    dict(
        id="CONST-VICTOROFF-CASESTUDY",
        slug="david",
        title="Victoroff OS case study for the portfolio",
        repo="organvm/portfolio",
        type="content",
        priority="low",
        cost=8,
        deps=["CONST-VICTOROFF-FACE"],
        predicate=f"{CHECK} casestudy david victoroff-os",
        value="the victoroff-os build story becomes a portfolio monument if its face lands",
    ),
    # Moat stage — evict-then-guard on the partner-shared products: externalize the tuned
    # values from the partner-visible tree FIRST, then land the moat-guard entry that asserts
    # their absence (a guard entry for a value still in-tree reddens the audit instantly).
    dict(
        id="CONST-STYX-MOAT",
        slug="jessica",
        title="Styx moat: externalize the tuned values from the public tree, then guard them",
        repo="organvm/peer-audited--behavioral-blockchain",
        type="code",
        priority="medium",
        cost=20,
        deps=[],
        predicate="python3 scripts/moat-audit.py --repo organvm/peer-audited--behavioral-blockchain --require-guard",
        value="the venture calibration stops being world-readable while the public form keeps luring",
        receipt="git:organvm/limen:moat-guard.json",
    ),
    dict(
        id="CONST-CANNIBAL-MOAT",
        slug="scott",
        title="Content Cannibalizer moat: externalize the tuned values from the shared tree, then guard them",
        repo="organvm/content-engine--asset-amplifier",
        type="code",
        priority="medium",
        cost=15,
        deps=[],
        predicate="python3 scripts/moat-audit.py --repo organvm/content-engine--asset-amplifier --require-guard",
        value="the engine calibration is partitioned out of the partner-visible lane",
        receipt="git:organvm/limen:moat-guard.json",
    ),
]


def _receipt_for(row: dict) -> str:
    """Derive the durable receipt target from the task's own predicate shape.

    Protocol receipts land in the pipeline repo's out/<slug>/ (public-safe
    slugs by construction), dossiers in the project repo's docs/, funnels at
    the instance file, and stage/decision moves at the register row itself.
    """
    if row.get("receipt"):
        return row["receipt"]
    predicate = row["predicate"]
    if " proto " in predicate:
        return f"git:organvm/relationship-pipeline:out/{row['slug']}"
    if " dossier " in predicate:
        return f"git:{row['repo']}:docs/brainstorm-dossier.md"
    if " funnel " in predicate:
        return f"git:organvm/limen:{predicate.split()[-1]}"
    if " corpus-refresh" in predicate:
        return "git:organvm/conversation-corpus-engine:README.md"
    if any(k in predicate for k in (" stage ", " face-state ", " decision-packet ", " casestudy ")):
        return "git:organvm/limen:organs/consulting/constellation/registry.yaml"
    return f"git:{row['repo']}:README.md"


def _boundary_terms(slug: str | None) -> tuple[str, ...]:
    """Forbidden-term floor per person, extended by the private overlay's boundaries."""
    if slug is None:
        return ()
    terms: list[str] = []
    if slug == "charles":
        terms += list(MONEY_TERMS) + list(OUTREACH_TERMS)
    if slug == "john-m":
        terms += list(OUTREACH_TERMS)
    if OVERLAY.exists():
        try:
            for row in yaml.safe_load(OVERLAY.read_text(encoding="utf-8")).get("people") or []:
                if row.get("slug") != slug:
                    continue
                blob = " ".join(str(b).lower() for b in row.get("boundaries") or [])
                if "money" in blob:
                    terms += list(MONEY_TERMS)
                if "messag" in blob or "outreach" in blob:
                    terms += list(OUTREACH_TERMS)
                if str(row.get("channel_state")) == "dormant":
                    terms += list(OUTREACH_TERMS)
        except (OSError, yaml.YAMLError):
            pass
    return tuple(dict.fromkeys(terms))


def _lint(task: dict) -> list[str]:
    problems = []
    text = " ".join(str(task.get(k, "")) for k in ("title", "value", "predicate")).lower()
    for term in _boundary_terms(task.get("slug")):
        if term in text:
            problems.append(f"{task['id']}: boundary term {term!r} for slug {task['slug']!r}")
    return problems


def _registry_slugs() -> set[str]:
    doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return {str(p.get("slug")) for p in doc.get("people") or []}


def _board_path() -> Path:
    env = os.environ.get("LIMEN_TASKS")
    if env:
        return Path(env)
    root = os.environ.get("LIMEN_ROOT")
    if root:
        return Path(root) / "tasks.yaml"
    # the live checkout's board: derive from the shared git dir, never a hardcode
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout.strip()
    return Path(common).parent / "tasks.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the CONST- constellation DAG through tabularius.")
    parser.add_argument("--live", action="store_true", help="emit tickets (default is dry-run validation)")
    parser.add_argument("--check", action="store_true", help="exit 0 iff every CONST- task is already on the board")
    parser.add_argument("--agent", default="claude", help="target_agent for seeded tasks")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    from limen.models import Task
    from limen.tabularius import submit_task_upsert
    from limen.work_loan import task_work_loan_readiness

    slugs = _registry_slugs()
    ids = {t["id"] for t in TASKS}
    problems: list[str] = []
    for task in TASKS:
        if task.get("slug") is not None and task["slug"] not in slugs:
            problems.append(f"{task['id']}: slug {task['slug']!r} not in registry")
        for dep in task["deps"]:
            if dep not in ids:
                problems.append(f"{task['id']}: unknown dep {dep!r}")
        problems.extend(_lint(task))
    if problems:
        for p in problems:
            print(f"REFUSED  {p}", file=sys.stderr)
        return 1

    board = _board_path()
    if not board.exists():
        print(f"ERROR: board {board} does not exist — refusing to seed a fresh board", file=sys.stderr)
        return 2
    doc = yaml.safe_load(board.read_text(encoding="utf-8")) or {}
    existing = {str(t.get("id")) for t in doc.get("tasks") or []}

    today = date.today().isoformat()
    missing, present, invalid = [], [], []
    for row in TASKS:
        fields = dict(
            id=row["id"],
            title=row["title"],
            repo=row["repo"],
            type=row["type"],
            target_agent=args.agent,
            workstream="consulting",
            priority=row["priority"],
            budget_cost=row["cost"],
            status="open",
            labels=["constellation", "generated"],
            depends_on=row["deps"],
            predicate=row["predicate"],
            receipt_target=_receipt_for(row),
            source_origin="human_prompt",
            horizon="present",
            value_case=row["value"],
            created=today,
        )
        try:
            validated = Task.model_validate(fields)
            readiness = task_work_loan_readiness(validated)
            if not readiness.ready:
                invalid.append(f"{row['id']}: not loan-ready ({readiness.reason_code})")
                continue
        except Exception as exc:  # noqa: BLE001 — every model rejection is the same finding
            invalid.append(f"{row['id']}: {exc}")
            continue
        (present if row["id"] in existing else missing).append((row["id"], fields))

    if invalid:
        for line in invalid:
            print(f"INVALID  {line}", file=sys.stderr)
        return 1

    if args.check:
        if missing and not args.quiet:
            for tid, _ in missing:
                print(f"MISSING  {tid}")
        return 0 if not missing else 1

    if not args.quiet:
        print(f"board: {board}")
        print(f"{len(present)} present, {len(missing)} to seed")
    for tid, fields in missing:
        if args.live:
            ticket = submit_task_upsert(board, fields, agent=args.agent, session_id="constellation-seeder")
            if not args.quiet:
                print(f"SEEDED   {tid}  ({ticket.name})")
        elif not args.quiet:
            print(f"WOULD SEED  {tid}  [{fields['priority']}/{fields['budget_cost']}] deps={fields['depends_on']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
