# Branch Constitution

This document is generated from `institutio/governance/branch-families.yaml`; do not edit it directly.

`main` is the protected production trunk and changes only through pull-request integration. Every non-trunk branch belongs to exactly one family below. Age is never a cleanup criterion: the family's receipt must be present before any cleanup consideration.

| Family | Match | Owner | Intent | Required receipt |
|---|---|---|---|---|
| trunk | `^main$` | governance | protected production trunk | merged pull request |
| feature | `^feat/.+$` | product | new product capability | open or merged pull request |
| repair | `^fix/.+$` | engineering | targeted defect repair | open or merged pull request |
| healing | `^heal/.+$` | engineering | reconciliation or self-healing repair | open or merged pull request |
| maintenance | `^chore/.+$` | engineering | maintenance and tooling | open or merged pull request |
| documentation | `^docs/.+$` | docs | documentation-only change | open or merged pull request |
| refactor | `^refactor/.+$` | engineering | behavior-preserving restructure | open or merged pull request |
| codex | `^codex/.+$` | codex | Codex-native work | open or merged pull request |
| copilot | `^copilot/.+$` | copilot | Copilot-native work | open or merged pull request |
| security | `^security(?:/.+|-.+)?$` | security | security remediation | open or merged pull request |
| recovery | `^recovery(?:/.+|-.+)?$` | recovery | historical recovery work | open or merged pull request |
| successor | `^successor/.+$` | recovery | lineage-preserving successor | linked predecessor and open or merged pull request |
| work | `^work/.+$` | fleet | bounded fleet work | open or merged pull request |
| corrective | `^corrective/.+$` | governance | governance correction | open or merged pull request |
| capture | `^capture/.+$` | fleet | durable capture work | open or merged pull request |
| dependency | `^dependency(?:/.+|-.+)?$` | dependencies | dependency maintenance | open or merged pull request |
| workspace | `^4444j99-plan-requested-change$` | copilot | active Copilot workspace branch | open pull request or session owner receipt |
| repair-exception | `^fix-(profile-api-observation-transport|live-profile-count-acceptance)-20260909$` | engineering | legacy repair branch | linked preservation receipt |

Successor branches retain a linked predecessor and integration receipt; they do not erase historical branches or pull requests. Stacked branches declare their merge order in their pull requests and are not independent `main` work.
