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

The second July 6, 2026 pass added a second class of work: Course Cafe / discussion replies.
Those are faster only if the reply is first classified by context:

- Course Cafe questions are open course-help threads, not formal assignment submissions.
- Regular discussion prompts usually require one peer response of at least 100 words.
- Rough-draft peer review also targets one classmate, but the review has a different standard:
  a detailed letter using the peer-review instructions.
- `Narrative Essay Final Draft` is a D2L folder name; the paper itself still needs the student's
  own MLA title.

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

## Course Cafe / Discussion Lookup Order

1. Identify whether the screenshot is in Course Cafe, a graded discussion, or an assignment folder.
   - Course Cafe source in the summer shell: `discussion_d2l_1.xml`.
   - Narrative Essay graded discussions: `discussion_d2l_2.xml`.
2. For "how many replies?" questions, search the relevant discussion XML for `peer response`.
   - Ordinary discussion language: one response of at least 100 words, preferably to a peer with no response yet.
   - Peer-review language: select one peer with no review yet, then write a substantive review letter.
3. For "what title?" questions, distinguish the D2L item name from MLA paper formatting.
   - `Narrative Essay Final Draft` is the submission folder.
   - Unit 1.2 includes `PDF: Writing an Effective Title` and `Title Capitalization Tool`.
   - The answer should tell students to create their own title, centered in MLA format above the first paragraph.
4. For broad student posts asking process questions, answer as an instructor presence:
   - validate the useful practice,
   - connect it to the writing process,
   - avoid turning the reply into extra required work.

## No Extra Instructor Work

Student email replies must not create extra instructor work unless the instructor explicitly asks
for an exception. Do not offer to reopen or unlock D2L units, change dates, create special
submission workflows, review revised posts, troubleshoot access, or invite a corrected version for
approval.

For closed work, keep the boundary concrete and professional: "I do not reopen closed D2L units.
Complete the work and email it when finished." Use that completion path only when it is useful to
the student and does not require a D2L change, new date, or instructor-side follow-up loop.

For self-revision questions like Jimmy's, point the student back to learning and current work:
"Use that revision to strengthen your own thinking/current essay work." Do not turn a discussion
post, reflection, or self-correction into "send me a corrected version for approval."

Keep the visible rationale professional: consistency, course logistics, and staying focused on
current work. Do not reveal private grading/admin reality in the reply.

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

For Course Cafe / discussion replies:

```bash
rg -n "Course Café|peer response|select one peer|Narrative Essay Final Draft|Writing an Effective Title|Title Capitalization" \
  /Users/4jp/Workspace/_ferpa-quarantine/from-downloads-2026-06-24/D2LExport_745627_ENGVBASE_ENC1101771624_202662209/discussion_d2l_*.xml \
  /Users/4jp/Workspace/_ferpa-quarantine/from-downloads-2026-06-24/D2LExport_745627_ENGVBASE_ENC1101771624_202662209/imsmanifest.xml
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

The reusable artifact from the first incident is the grounding path:

`student email -> course/ref -> generated schedule -> manage dates -> D2L assignment folder -> reply`

Any future student email about "I cannot find where to submit X" should follow that path before
drafting prose.

The reusable artifact from the second incident is the discussion triage path:

`screenshot -> forum type -> exact prompt language -> assignment-folder vs paper-format distinction -> reply`

## Contexts That Did Not Ignite Easily

- **Term-vs-shell context:** the D2L export showed the assignment exists, but not the live summer due date.
  The generated term artifacts had to be queried separately.
- **Repo location context:** the durable summer-2026 schedule lived in `organvm/edu-organism`, not this
  Limen checkout.
- **Forum-type context:** Course Cafe, regular graded discussions, and rough-draft peer review look similar
  in screenshots but have different reply rules.
- **Folder-name-vs-student-work context:** `Narrative Essay Final Draft` names the D2L submission folder,
  not the title the student should put on the essay.
- **Student-paraphrase context:** phrases like "pathway" or "Unit 2 prompt" can point to multiple course
  surfaces; they need source matching before drafting.
- **Instructor-presence context:** some replies are not policy answers. They are lightweight instructor
  nudges that should connect student advice back to writing process without adding requirements.
