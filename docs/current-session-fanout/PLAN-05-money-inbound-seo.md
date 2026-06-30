# Current Session Fanout: PLAN-05 Money Inbound SEO

Generated: `2026-06-30`
Status: `ready`
Packet: `PLAN-05-37b731f8`
Task: `CSF-CAEB31D8-PLAN-05-37B731F8`
Theme: `money-inbound-seo`
Source session: `/Users/4jp/.codex/sessions/2026/06/30/rollout-2026-06-30T06-17-55-019f1809-13b4-7780-9b1f-d4584f872333.jsonl`

This receipt plans the money-inbound SEO stream only. It does not paste raw
prompt or plan text. Provenance is by hashes and repo-local ledgers.

## Full-Session Provenance

The source session contains `11` plan events, `10` unique plan sources, and `1`
duplicate plan event. This packet is derived from the full unique plan set, not
only from the latest turn.

Source plan hashes:

- `7eb608baa99c`
- `c93bc2c89ad8`
- `dbf49126308e`
- `3cc93e1d8fbd`
- `0cb1773e8fef`
- `1a3fd7bbca9d`
- `569ac3d1deea`
- `b0f5c26d40a3`
- `f15665fb9ad3`
- `21e790435885`

Source prompt refs: `44` hash refs, `19` unique. Full hash list is kept in the
ignored private receipt:
`.limen-private/session-corpus/lifecycle/plan-05-money-inbound-seo.json`.

## Selection Inputs

- Value repo source: `value-repos.json` (`12` repos).
- Positioning source: `positioning-seeds.json` (`9` seeded repos).
- Revenue source: `revenue-ladder.json` (`6` ranked products).
- Existing doctrine: `docs/inbound-magnet-system.md`.
- Existing generator: `scripts/generate-positioning.py`.
- Existing revenue queue feed: `scripts/generate-revenue-backlog.py`.

Global product selection order for this stream starts with the ranked revenue
ladder, then falls through to seeded value repos when a higher-ranked product is
blocked by a human or outward-facing gate.

## Owner Packets

| Packet | Owner | Route | Executor Criteria | Verification Predicate |
|---|---|---|---|---|
| `MIB-01-positioning-proof` | `organvm/limen` | Refresh public positioning for the first money surfaces already backed by seeds. Start with `organvm/public-record-data-scrapper` and `organvm/a-i-chat--exporter`. | Executor may edit only positioning seeds, generated public positioning docs, or generator tests. Public surfaces must contain no prices, raw prompts, or outbound sends. Internal anchors remain ignored. | `python3 scripts/generate-positioning.py --repo organvm/public-record-data-scrapper` and `python3 scripts/generate-positioning.py --repo organvm/a-i-chat--exporter`. |
| `MIB-02-discoverability-map` | `organvm/limen` plus selected owner repo | Convert each seeded product into buyer-search vocabulary: repo topics, README terms, title/description, and front-door copy. Do not mutate GitHub topics until an executor has a repo-specific gate. | Executor must name the exact owner repo, changed files, buyer search terms, and rollback path. If GitHub topic mutation is needed, stage the command only. | Parse `value-repos.json`, `positioning-seeds.json`, and `revenue-ladder.json`; run `git diff --check` on any changed SEO docs/seeds. |
| `MIB-03-frontdoor-capture` | `organvm/portfolio` and `organvm/limen` | Keep the two-door inbound surface current: client door and recruiter door. Capture remains tagged inbound only. | Executor may stage mailto or form copy, but cannot publish a personal contact address, send email, buy ads, deploy past a release gate, or expose a private repo. `frontdoor.contact` is a human gate while empty. | `python3 scripts/generate-positioning.py --apply` after a contact/publish gate, otherwise dry-run only and record the gate in the packet receipt. |
| `MIB-04-selection-continuity` | `organvm/limen` | When a local product is blocked, record the blocker once and select the next unblocked product/repo for SEO or positioning work. | Executor must keep global selection active. A blocked local rail can end that rail, but not the stream. The next packet should pick the next repo with seed + public-safe verification. | `python3 scripts/generate-revenue-backlog.py --floor 1 --max-new 1` plus a receipt line naming any blocker and the next selected unblocked repo. |

## Blocked Local Work

These are recorded blockers for this stream. They do not stop global product
selection.

- `frontdoor.contact` is empty in `positioning-seeds.json`; public CTAs remain
  plain text until Anthony chooses an indexed inbound address or alias.
- `docs/NEEDS-HUMAN-DIGEST.md` records Cloudflare auth, branch-protection,
  launchd `gh` auth, PR security secrets, and release-gate actions. These gates
  block deploys or identity-bearing actions, not local SEO planning.
- `organvm/mirror-mirror` is marked `awaiting_publish` in `positioning-seeds.json`;
  do not render it onto a public inbound surface until the repo visibility gate is
  explicitly opened.
- This task worktree does not contain live `logs/organ-health.json` or
  `logs/usage.json`; lane health must be re-derived at dispatch time. Planning can
  still continue from repo-local value, positioning, and revenue ledgers.

Fallback rule: if the current selected repo is blocked by one of the gates above,
write the blocker to the owning receipt and move to the next ranked repo with a
public-safe seed. Do not wait on account signup, deployment auth, or outbound
contact setup before continuing local positioning/discoverability work.

## Executor Contract

Every executor packet spawned from this plan must return:

- owner repo and branch/worktree;
- exact changed paths or an explicit no-op reason;
- predicate command and result;
- public-safe receipt using source plan hashes above, not raw prompt text;
- blocker receipt when a human/outward-facing gate is hit;
- next unblocked repo/product when local work is blocked.

Forbidden without a fresh human gate:

- sending email or outbound messages;
- publishing contact details not already configured;
- changing repo visibility;
- spending money, buying ads, or using reset/credit top-ups;
- deploying past a release gate;
- pasting source prompt or plan bodies into public files.

## Verified Predicates

The following predicates were run in this worktree while creating the packet:

```bash
python3 scripts/generate-positioning.py --repo organvm/public-record-data-scrapper
python3 scripts/generate-positioning.py --repo organvm/a-i-chat--exporter
python3 scripts/generate-revenue-backlog.py --floor 1 --max-new 1
python3 - <<'PY'
import json
from pathlib import Path
for name in ['value-repos.json', 'positioning-seeds.json', 'revenue-ladder.json']:
    json.loads(Path(name).read_text())
PY
```

All passed. `generate-revenue-backlog.py` reported the revenue queue healthy
instead of generating duplicate work, which is the desired continuity behavior:
blocked rails are recorded, but product selection remains active.

