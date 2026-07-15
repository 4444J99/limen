# Disclosure audit — the 2026-07 PII sweep, re-decided by the engine

Every repo the 2026-07-01 containment sweep touched, run through
[`scripts/publication-policy.py`](../../scripts/publication-policy.py) so the disposition is the
engine's, not a per-repo judgment call. Regenerate with:

```bash
python3 scripts/publication-policy.py audit <ledger.json>
```

## The verdict

| repo | vis | class | disposition | state / action |
|---|---|---|---|---|
| peer-audited--behavioral-blockchain | PUBLIC | internal_strategy | `KEEP_OFF_PUBLIC_HEAD` | **PR#752: do not merge — close it (or leave it unmerged).** Engine says internal strategy (premortem + planning) does not belong on a public HEAD; content is preserved in git history. The *close* is a gated external write (it reverses an earlier merge attempt) → his one-click, recorded in `L-PII-SWEEP-CONTAIN`. The point stands regardless: it must not be merged. |
| call-function--ontological | PUBLIC | internal_strategy | `KEEP_OFF_PUBLIC_HEAD` | PR#15 MERGED a 9,036-line raw session dump to public HEAD. **Remediation backlog:** strip that file from HEAD (reversible; history retains it). |
| your-fit-tailored | PUBLIC | internal_strategy | `KEEP_OFF_PUBLIC_HEAD` | PR#19 MERGED `transcript.md` + `prompts.md` to public HEAD. **Remediation backlog** + a **separate flag**: PR#19 also modified `pilot-users.csv` (real pilot-user rows on a public repo — third-party data, review). |
| adaptive-personal-syllabus | PUBLIC | internal_strategy* | `KEEP_OFF_PUBLIC_HEAD` | prior sweep. class inferred — verify per-PR, then strip from HEAD. |
| cognitive-archaelogy-tribunal | PUBLIC | internal_strategy* | `KEEP_OFF_PUBLIC_HEAD` | prior sweep. verify per-PR. |
| life-my--midst--in | PUBLIC | internal_strategy* | `KEEP_OFF_PUBLIC_HEAD` | prior sweep. verify per-PR. |
| meta-source--ledger-output | PUBLIC | internal_strategy* | `KEEP_OFF_PUBLIC_HEAD` | prior sweep. verify per-PR. |
| narratological-algorithmic-lenses | PUBLIC | internal_strategy* | `KEEP_OFF_PUBLIC_HEAD` | prior sweep. verify per-PR. External public fork = GitHub sensitive-data-removal residue (his lever). |
| orchestration-start-here | PUBLIC | internal_strategy* | `KEEP_OFF_PUBLIC_HEAD` | prior sweep. verify per-PR. |
| organvm-corpvs-testamentvm | PUBLIC | internal_strategy* | `KEEP_OFF_PUBLIC_HEAD` | prior sweep. Positioning recon flagged this as a raw-prompt leak repo — high priority verify. |
| praxis-perpetua | PUBLIC | internal_strategy* | `KEEP_OFF_PUBLIC_HEAD` | prior sweep. verify per-PR. |
| sovereign-systems--elevate-align | PUBLIC | internal_strategy | `KEEP_OFF_PUBLIC_HEAD` | **already satisfied** — `.claude/` correctly kept off public HEAD last session (subject-matter). No action. |
| system-system--system | PRIVATE | internal_strategy | `RESTORE_REDACT` | **correct as-is** — private is a safe home; restore-and-redact was the right call. No action. |
| my-knowledge-base | PRIVATE | internal_strategy | `RESTORE_REDACT` | **correct as-is** — flipped PRIVATE last session (pervasive personal + named third parties); restore-redact correct. No action. |
| a-i--skills | PUBLIC | public_safe | `PUBLISH` | PR#32 is a legitimate product PR (skill distributions) that *also deletes* a raw session dump — engine-compatible. Blocked only by a required review (his hand). |

\* class inferred from the sweep pattern (session-content restore); confirm against each PR's file
list before acting. The two session repos with confirmed file lists (call-function, your-fit) and
the open case (peer-audited) are the authoritative anchors.

## What changed in our understanding

The sweep's earlier framing had it backwards. The *removal* PRs were right in **outcome** —
internal-strategy session artifacts (raw transcripts, prompt dumps, premortems, planning docs)
do not belong on a **public** HEAD. The error was never the outcome; it was deciding it per-repo
by hand (first delete-everything, then restore-everything). The **engine** gives the one
consistent rule: on a public surface such content is `KEEP_OFF_PUBLIC_HEAD` (preserved in git
history, off the live face); on a private repo the same content is a safe `RESTORE_REDACT`.

"Never removed from the universe" is satisfied either way — git history retains everything;
removal from HEAD is not deletion.

## Remaining work (owner = the Publication Policy organ)

- **Resolved now:** the *decision* on peer-audited#752 — it must not be merged (recorded here + in the lever). The one-click *close* is a gated external write (reverses a prior merge attempt), so it is his click; leaving it unmerged is equally fine.
- **Backlog (auto, reversible):** strip the confirmed internal-strategy files from the public
  HEADs of call-function + your-fit; verify-then-strip the ~7 inferred public repos. Each is a
  reversible, protective HEAD edit (content stays in history) — the organ's self-heal domain
  (open-never-merge, the human keeps the publish click). Tracked under `L-PII-SWEEP-CONTAIN`.
- **His lever:** the pilot-users.csv third-party-data review (your-fit); the external
  narratological fork (GitHub sensitive-data-removal); a-i--skills#32's required review.

## 2026-07-15 — application-pipeline (PUBLIC): client engagement content on HEAD

**Found while:** staging the Carbone/AFG Florida rendezvous pack. The session pushed
`strategy/rendezvous-2026-07-tony-carbone.md` (client PII + internal price anchors) to
`organvm/application-pipeline` via PR #77 **on the assumption the repo was private** — visibility
was verified only after merge. The pre-existing `strategy/consulting-tony-carbone-altfunding.md`
(client name/email/cell) had been on that public HEAD since 2026-03-23, undetected by the 07-01
sweep (application-pipeline was not among the 15 sweep repos).

**Disposition applied (same session, ~3-minute window for the new file):**
`KEEP_OFF_PUBLIC_HEAD` — both files removed from HEAD via PR #78 (heal), content re-homed to the
private people room (`_people-private/people/tony-carbone/`). Public HEAD verified clean.

**Residue (accepted per the engine's 07-02 disposition):** the merged PR #77 and #78 diffs — like
scraper PR #227 — remain publicly visible; history is preservation, not deletion. Standing
client-facing rule: never link PRs #77/#227.

**Lesson (root cause):** repo **visibility is checked BEFORE the push, never after** — one
`gh api repos/<owner>/<repo> --jq .private` gate ahead of any engagement/PII/anchor content.
application-pipeline should join the publication-policy engine's repo set so its disposition is
computed, not assumed.
