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

Generated: `2026-07-08T06:07:27Z`

`python3 scripts/github-contribution-balance.py --login 4444J99 --json`:

| Category | Count | Share | Target |
|---|---:|---:|---:|
| Commits | `12,990` | `74.10%` | `<=60%` |
| Issues | `2,103` | `12.00%` | `>=15%` |
| Pull requests | `2,320` | `13.23%` | `>=15%` |
| Reviews | `117` | `0.67%` | `>=10%` |

Review-first receipts in this beat:

- Requested changes on `organvm/linguistic-atomization-framework#16`: Python dependency floor mismatch against Python 3.11 CI.
- Requested changes on `organvm/bountyscope#18`: Wrangler 4.107.0 requires Node 22+, but the PR CI build runs Node 20.
- Approved green action/tooling PRs: `organvm/organon-noumenon--ontogenetic-morphe#9`, `organvm/linguistic-atomization-framework#14`, `organvm/public-record-data-scrapper#339`, `organvm/public-record-data-scrapper#341`, `organvm/hokage-chess#9`, and `organvm/agentic-titan#96`.
- Commented on blocked or under-proven PRs: `organvm/content-engine--asset-amplifier#33`, `organvm/a-i--skills#1`, and `organvm/a-i--skills#2`.

Owner issue receipt: `https://github.com/organvm/limen/issues/687#issuecomment-4911849538`.

## ELI5

Each real job gets a sticky note, a box, and a checkmark.

The issue is the sticky note. The PR is the box with the work inside. The review is the checkmark from another pass. The graph evens out when every real job gets all three.
