# Case-Study Template

One template for every Level-2 flagship page. Sections are mandatory; length is not. Every
number carries source + date per `claims-ledger.md`; authorship line per
`authorship-disclosure-policy.md`.

---

## <System name> — <plain-language label>

**Status:** <live with demonstrated use | deployed, adoption unvalidated | working prototype |
code-complete | specification package> · **Authorship:** <class per policy> · **Evidence
anchors:** <dated links: dashboard / CI run / live URL>

### The expensive problem
Who has it, what it costs them, why existing alternatives fail. (Buyer language, no jargon.)

### What was built
The system in three sentences. Then the architecture — one diagram, the real one.

### Decisions and tradeoffs
The 3–5 decisions that shaped the build; the options rejected and why. This section proves
judgment — it is the part a demo cannot fake.

### The verification story
How correctness is enforced: tests (count, source, date), gates, liveness receipts, failure
modes observed and handled. Include what failed and how it surfaced — receipts with failure
modes are the costly-to-fake part.

### What it proves about the method
One paragraph connecting this system to the governed production system that built it — packet,
lease, verification, receipt. (The method page carries the full lifecycle; link, don't repeat.)

### Current state and honest limits
What is live, what is asserted-but-unreproduced, what is roadmap. Never let a designed capacity
read as an implemented one.

### Doors
The two standing calls to action (client door / builder door), unchanged from the front page.

---

### Rules

- No claim above its ledger tier; "repository-asserted" numbers are labeled as such until a P4
  receipt flips them.
- Every URL registered in `link-surfaces.json` (link-rot is a guarded failure mode).
- The Greek/Latin shelf name may appear once, always beside its plain label.
