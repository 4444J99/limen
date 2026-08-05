# GitHub Contribution Balance

The screenshots show a real signal: the work exists, but the public proof shape is uneven. The yearly graph is commit-heavy (`76%` commits, `12%` pull requests, `11%` issues, `1%` code review in the screenshot window). That does not mean less work happened. It means too much work landed as commit-only evidence.

The fix is not fake activity. The fix is to make the normal workflow leave the right receipts.

## Ideal Shape

Every meaningful work unit should have three public surfaces:

| Surface | Meaning |
|---|---|
| Issue | The work has a named problem, owner, acceptance condition, and evidence target. |
| Pull request | The implementation is packaged, reviewable, and attached to checks. |
| Review | A second pass exists: approval, requested change, or substantive comment. |

Commits are still needed, but they should mostly be inside PRs. Direct `main` commits should be narrow owner receipts: daemon board snapshots, branch hygiene, storage receipts, urgent protocol repair, or other record-preserving changes that are intentionally not feature work.

## Steering Targets

These targets are steering rails, not vanity metrics:

| Category | Target |
|---|---|
| Commits | At or below `60%` of visible contribution mix |
| Issues | At or above `15%` |
| Pull requests | At or above `15%` |
| Code reviews | At or above `10%` |

When the mix is out of range, choose the next action in this order:

1. If reviews are below target, review an existing PR before starting new feature work.
2. If issues are below target, open or refresh a real issue with acceptance criteria for the next unresolved work unit.
3. If pull requests are below target, put the next implementation behind a branch and PR.
4. If commits are above target, stop direct-to-main feature commits; keep commits inside PRs.

## Command

```bash
python3 scripts/github-contribution-balance.py --login 4444j99
```

For a screenshot-equivalent window:

```bash
python3 scripts/github-contribution-balance.py --login 4444j99 --from 2025-06-29 --to 2026-07-05
```

The script is read-only. It uses GitHub through `gh api graphql` when available, or `--from-json` for a saved GraphQL response/report. It never opens issues, submits PRs, posts comments, or sends reviews.

## Live Receipt

Generated: `2026-07-10T01:48:14Z`

`python3 scripts/github-contribution-balance.py --login 4444J99 --json`:

| Category | Count | Share | Target |
|---|---:|---:|---:|
| Commits | `13,381` | `73.70%` | `<=60%` |
| Issues | `2,126` | `11.71%` | `>=15%` |
| Pull requests | `2,483` | `13.68%` | `>=15%` |
| Reviews | `165` | `0.91%` | `>=10%` |

Review-first and owner-blocker receipts in this beat:

- Added July 10 formal review receipts while preserving the review-first gate as unresolved long-term steering: commented on `organvm/krypto-velamen#13` after checking the single-file TypeScript bump, green minimal CI, and a Scratch build comparison against `main`; approved `organvm/gamified-coach-interface#153` after checking the patch-level Vite/Vitest updates, lockfile scope, clean merge state, and green Node 18/20/22 CI matrix; commented on `organvm/audio-synthesis-bridge#13`, `organvm/example-choreographic-interface#12`, and `organvm/client-sdk#18` after checking their dependency diff scope, clean merge state, and green CI.
- Added a second July 10 review batch: approved `organvm/narratological-algorithmic-lenses#48`, `organvm/recursive-engine--generative-entity#24`, and `organvm/sema-metra--alchemica-mundi#26`; commented on `organvm/narratological-algorithmic-lenses#49`, `organvm/recursive-engine--generative-entity#23`, and `organvm/my-block-warfare#39`; requested changes on `organvm/my-knowledge-base#76`, `organvm/trade-perpetual-future#77`, `organvm/narratological-algorithmic-lenses#50`, `organvm/ivi374ivi027-05#32`, `organvm/your-fit-tailored#22`, `organvm/portfolio#182`, `organvm/a-recursive-root#50`, and `organvm/a-recursive-root#51` when checks were absent, failing, or too narrow for the changed dependency surface.
- Requested changes on `organvm/a-i-council--coliseum#178`: backend dependency resolution and frontend lockfile config mismatch.
- Approved `organvm/a-i-council--coliseum#174`: scoped PostCSS bump with green CI.
- Commented on blocked or under-proven PRs: `organvm/persona-fleet#11`, `organvm/organvm-engine#165`, `organvm/vigiles-aeternae--agon-cosmogonicum#10`, `organvm/universal-mail--automation#149`, and `organvm/domus-genoma#201`.
- Opened and linked owner blockers for repeated residue/failure patterns: `organvm/universal-mail--automation#150`, `organvm/growth-auditor#23`, `organvm/mirror-mirror#113`, `organvm/domus-genoma#202`, and `organvm/domus-genoma#203`.
- Linked those owner blockers across the affected PR clusters: UMA `#146`-`#149`, Growth Auditor `#18`-`#22`, Mirror Mirror `#106`, `#107`, `#109`, `#111`, and Domus `#183`, `#184`, `#185`, `#187`.
- Added review receipts on dependency-maintenance PRs while waiting for async closeout: approved `organvm/application-pipeline#75`, `organvm/promptscope#16`, `organvm/agent--claude-smith#35`, `organvm/system-governance-framework#48`, `organvm/select-or-left-or-right-or#32`, and `organvm/card-trade-social#15`; requested changes on `organvm/padavano#11`, `organvm/meta-source--ledger-output#34`, `organvm/materia-collider#14`, `organvm/vox--publica#10`, `organvm/sign-signal--voice-synth#15`, `organvm/object-lessons#23`, `organvm/a-mavs-olevm#106`, `organvm/classroom-rpg-aetheria#146`, and `organvm/specvla-ergon--avditor-mvndi#53`.
- Added a second review pass on unreviewed dependency PRs: approved `organvm/search-local--happy-hour#43` and `organvm/shared-remembrance-gateway#9`; requested changes on `organvm/content-engine--asset-amplifier#33`, `organvm/peer-audited--behavioral-blockchain#773`, `organvm/persona-fleet#11`, `organvm/metasystem-master#39`, `organvm/tool-interaction-design#34`, `organvm/glyph-cascade#10`, `organvm/sovereign-systems--elevate-align#268`, and `organvm/my-knowledge-base#74`.

Owner issue receipts: `https://github.com/organvm/limen/issues/687#issuecomment-4911849538`, `https://github.com/organvm/limen/issues/687#issuecomment-4931184489`, `https://github.com/organvm/limen/issues/687#issuecomment-4931225878`.

## ELI5

Each real job gets a sticky note, a box, and a checkmark.

The issue is the sticky note. The PR is the box with the work inside. The review is the checkmark from another pass. The graph evens out when every real job gets all three.
