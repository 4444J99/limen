# Writing, reflection, and reproducible course design

Anthony James Padavano · Teaching and learning design

My education work connects composition, literary analysis, reflective practice, and
course tooling. The public entry point is an authored teaching-design case study.
It supports three inspection paths: pedagogy, educational technology, and academic
practice. It makes no claim about measured learning gains or institutional accreditation.

## The design problem

An essay can improve while its writer cannot explain what changed. Peer responses can
focus on grammar before addressing the argument. A new term can require rebuilding the
same course materials and dates by hand. The course designs address these three problems
with explicit feedback structure, a visible record of revision, and reusable instructor tools.

## A feedback loop that students can act on

The reviewed peer-review protocol addresses higher-order concerns before lower-order
concerns. Reviewers read the entire draft, then consider the claim, reasoning, evidence,
organization, development, audience, and purpose. Sentence clarity and citation patterns
follow those decisions.

For a major draft, the reviewer writes a directed letter: two strengths supported by
specific evidence, at least two higher-order revision needs, one recurring sentence or
citation pattern, and one open reader question. Each response connects to an assignment
criterion. The writer closes the loop with a short revision note explaining changes made
and feedback intentionally declined. Lower-stakes discussions use a shorter response form.

**Inspectable contribution:** a reusable feedback procedure with a concrete writer action.
The artifact demonstrates instructional design; it does not establish a measured classroom effect.

## A record of how a claim develops

The Thesis Evolution Log is an authored design specification for an ungraded, persistent
course discussion. Writers revisit their claim at four points: choosing a research position,
responding to sources, fairly representing a counterargument, and preparing the capstone.
A final reflection compares the initial and later claims.

This separates an evolving argument from isolated essay submissions and gives the
instructor a potential diagnostic: a claim that never changes may need closer discussion.

**Readiness:** the design specification is complete. Creating the live LMS discussion and
linking the final reflection require course-specific implementation; this page does not claim
those actions occurred or that student outcomes were measured.

## Educational technology: preserve reviewability

The inspected course tooling separates a reusable engine, course memory, term configuration,
and generated instructor materials. The documented flow begins with an LMS export and term
dates, generates a dated schedule and instructor layer, and produces a structural review and
handoff. A generated file is not proof of a successful live LMS import.

On October 1, 2026, local reproduction using the existing curated instructor shell
and course memory passed with this command, run from the private course workspace:

```sh
python3 -m courses._engine.recapitulate --course enc1101 courses/enc1101/terms/summer-2026.yaml
```

The engine generated ten artifacts and dated all 25 graded items. Its structural
report found no unmatched cartridge items, cadence entries, or announcement bodies.
Regeneration left the tracked text outputs unchanged, and all 69 course-engine tests
passed. Those tests cover date/DST conversion, course isolation, allowlisted structural
ingest, and generated-text privacy checks. The repository's tracked-content privacy
guard also passed. Only these structural results are published here; source exports,
course bodies, student records, and the private repository remain in private custody.

This evidence establishes reproducible local generation. LMS import, notification
activation, live classroom use, adaptive lesson delivery, and learning outcomes retain
their own acceptance requirements. Broader classroom-RPG and adaptive-syllabus
applications remain separate software projects whose build and runtime readiness need
their own verification.

## Academic practice and creative work

The course portfolio includes composition and literature design, a structured self-audit,
and recorded improvement priorities. These materials support inspection of design judgment
and constructive alignment. Credentials, institutional claims, and research outcomes require
separate verification before publication.

Creative practice continues alongside this education focus. [Danse](https://danse.pages.dev/)
is a browser-based photographic artwork; its [canonical project record](https://github.com/4444J99/the-thing-without-a-name-screendance)
distinguishes the public browser work from draft festival, film, rights, accessibility, and
installation packages. It is the current creative flagship, not an assertion that those
broader packages have been accepted.

## Evidence boundary

This case study was authored from the peer-review protocol, Thesis Evolution Log design
specification, teaching-portfolio index, and course operating charter inspected on
September 30, 2026. It contains instructional methods and design interpretation, with no
student submissions, names, rosters, grades, feedback records, or private source-repository
coordinates. The instructional corpus retains its existing private custody.
