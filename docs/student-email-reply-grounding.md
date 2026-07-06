# Student Email Reply Grounding

Use this before drafting a student-facing D2L reply from a screenshot or pasted email.
The goal is a low-labor, grounded answer that names the assignment, date, and submission
channel without inventing a course policy.

## Core Lesson

Do not draft from the student's paraphrase alone.

In the July 6, 2026 ENC1101 email, the screenshot made the student sound unsure about
"a prompt in Unit 2" and "why I chose the pathway I did." A generic answer would have
been wrong. The course materials showed three separate facts:

- Unit 2 is the Narrative Essay unit.
- The major item is `Narrative Essay Final Draft`, due `Wed Jul 15, 2026 11:59 PM`.
- The correct submission channel is `Assignments -> Essays -> Narrative Essay Final Draft`, not email.

## Lookup Order

1. Identify the course/ref from the email header or D2L shell.
   - Example: `ENC1101 COMPOSITION I ONLINE 771624`.
2. Find the term artifact, not just the base D2L export.
   - Current durable source: `organvm/edu-organism`.
   - Example generated files:
     - `courses/enc1101/terms/summer-2026/generated/schedule-summer-2026.md`
     - `courses/enc1101/terms/summer-2026/generated/manage-dates-summer-2026.md`
     - `courses/enc1101/terms/summer-2026/generated/HANDOFF.md`
3. Confirm the shell has the assignment and submission folder.
   - Example D2L export path:
     - `classes/enc1101-summer-2026/d2l-shell-745627/dropbox_d2l.xml`
   - The folder proved `Narrative Essay Final Draft` exists, is visible, and is worth 200 points.
4. Check the announcement or schedule layer for student-facing date language.
   - Example:
     - `classes/enc1101-summer-2026/prep/instructor-layer-ready/announcements-summer2026.md`
     - `classes/enc1101-summer-2026/prep/instructor-layer-ready/announcements-summer2026-IMPORT-aligned.csv`
5. Only then draft the reply.

## Fast Commands

```bash
gh api 'repos/organvm/edu-organism/git/trees/main?recursive=1' \
  --jq '.tree[] | select(.path | test("(enc1101|summer-2026|schedule|announcement|generated)"; "i")) | .path'

gh api 'repos/organvm/edu-organism/contents/courses/enc1101/terms/summer-2026/generated/schedule-summer-2026.md?ref=main' \
  --jq .content | base64 -d

gh api 'repos/organvm/edu-organism/contents/courses/enc1101/terms/summer-2026/generated/manage-dates-summer-2026.md?ref=main' \
  --jq .content | base64 -d
```

For the local D2L export, search narrowly:

```bash
rg -n "Narrative Essay Final Draft|Unit 2|Narrative Essay|pathway" \
  /Users/4jp/Workspace/_ferpa-quarantine/from-downloads-2026-06-24/D2LExport_745627_ENGVBASE_ENC1101771624_202662209
```

## Reply Shape

Use this structure:

1. Acknowledge the student's check-in.
2. Correct the concrete confusion with the exact D2L item name.
3. Name the due date and, if useful, the open date.
4. Point to the official submission channel.
5. Avoid creating extra labor or a new exception.

Template:

```text
Hi {FirstName},

Thanks for checking. You did not write it for nothing.

The {unit/work} is part of the course. The {related smaller item} was due {date}, but
the major {assignment_name} is due {due_date}.

If what you wrote is the full {assignment_name}, keep it saved and use it as your draft.
Submit the final version in D2L under {submission_path}. Please do not submit it by
email unless I specifically ask you to.

If you do not see the submission folder yet, it is scheduled to open on {open_date}.

Best,
Professor Padavano
```

## Extraction

The reusable artifact from this incident is the grounding path:

`student email -> course/ref -> generated schedule -> manage dates -> D2L assignment folder -> reply`

Any future student email about "I cannot find where to submit X" should follow that path before
drafting prose.
