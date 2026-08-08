# The epistemic-hygiene ledger — which findings in the power canon are dead

The most valuable thing in a curriculum about influence is not the list of mechanisms. It is the
list of mechanisms that **did not survive replication** — because every popular treatment of this
material cites at least one of them, usually several, and a reader who absorbs the canon
uncritically walks away **confidently wrong**. That is worse than ignorant. It feels like
competence.

Each entry below carries **the number and the citation that killed it**. Each corresponds to a row
in `mechanisms.yaml` graded `debunked` or `overstated`, so `scripts/check-potestas.py` rule 7 can
enforce that none of them ever becomes load-bearing in a drill, a protocol, or a rubric.

This file is the one place in the track permitted to name the dead freely. That is its whole job.

---

## Dead

### Ego depletion

**Claim:** willpower is a finite resource consumed by prior acts of self-control.

d = **0.62** in the Hagger et al. (2010) meta-analysis → d = **0.04** in a 23-lab preregistered
replication (Hagger & Chatzisarantis, 2016). A factor of fifteen, in the direction of nothing.

*Where you'll meet it:* "don't negotiate when tired," "make hard decisions in the morning,"
decision-fatigue advice generally.

---

### Power posing

**Claim:** expansive postures produce hormonal and behavioral changes that increase felt and
conferred power.

Disavowed by its own first author. Dana Carney, 2016: *"I do not believe that 'power pose' effects
are real."* Not a critic's verdict — the originating researcher's.

*Where you'll meet it:* interview coaching, negotiation prep, most of the confidence-building
industry.

---

### Social priming

**Claim:** incidental exposure to a concept reliably alters unrelated downstream behavior.

Bargh's elderly-priming result failed to replicate (Doyen et al., 2012), and the effect appeared
**only when experimenters knew the hypothesis** — which identifies the mechanism as the
experimenter, not the prime.

*Where you'll meet it:* "environment shapes behavior" persuasion advice, ambient-cue theories of
influence.

---

### Mass political persuasion

**Claim:** campaign contact and advertising move candidate choice in general elections.

Kalla & Broockman, *American Political Science Review* 112(1):148–166 (2018), meta-analysis of 49
field experiments: *"the best estimate of the effects of campaign contact and advertising on
Americans' candidate choices in general elections is zero."*

**Zero.** Against an industry that spends billions annually on the assumption.

*The exception, and it matters:* intensive, empathy-based **deep canvassing** (Broockman & Kalla,
*Science* 2016) durably moves opinion — and does not scale cheaply. What works is expensive and
slow. What is cheap and fast does not work.

---

## Overstated

### Nudge effect sizes

**Claim:** choice-architecture interventions produce reliable, substantial behavior change.

Maier et al. (2022): **"no evidence for nudging"** after publication-bias correction — against the
d = 0.45 reported by Mertens et al. (2022) on overlapping literature. Both are meta-analyses. The
difference is the correction.

*Not zero in every domain* — some defaults genuinely work. But the headline numbers are a
publication-bias artifact, and the honest posture is to demand preregistration before believing any
specific nudge.

---

### Psychographic micro-targeting

**Claim:** personality-profiled advertising reliably shifts mass electoral behavior. The Cambridge
Analytica frame.

Described as *"very much overstated"* by data operatives in **both** parties — the people who would
have had the most to gain from it being true.

**Do not confuse this with personalized AI persuasion**, which is measured and real (see below).
The difference is the setting: a controlled, one-to-one, adaptive conversation versus a
demographically-sorted ad impression. Conflating them is the single most common error in this
literature, and it runs in both directions — dismissing the real finding because the fake one
collapsed, or believing the fake one because the real one exists.

---

## Contested — handle with care rather than discard

### "Mind control" / coercive persuasion

The BITE model (Behavior, Information, Thought, Emotional control) is influential and
descriptively useful, but **lacks scientific consensus**. The ECHR noted in 2010 that there is
*"no generally accepted… scientific definition of what constitutes 'mind control,'"* and multiple
courts have rejected brainwashing expert testimony.

Useful as a description of what high-control environments *look like*. Not usable as a mechanism
that explains or excuses individual behavior.

---

### The propaganda model

Herman & Chomsky's five filters are a **structural argument**, not an experimental result. The model
makes no falsifiable point-prediction, which is why `mechanisms.yaml` grades it `contested` rather
than `robust`. It remains an excellent set of questions to ask of any coverage; it is not a measured
effect.

---

### The 48 Laws of Power

**Documentation, not evidence.** *Kirkus* called it "simply nonsense," and reviewers note the laws
contradict one another — Law 1 (never outshine the master) against Law 6 (court attention at all
cost); Law 16 (use absence) against Law 6 again.

The contradictions are not a flaw in the reading. They are the evidence that this is a **catalogue
of observed moves**, not a theory. That is exactly what makes it useful as a detection corpus and
useless as a rulebook — which is why every Greene-derived row in `mechanisms.yaml` is graded
`contested` and flagged `inward: true`.

---

## The paradox this ledger must not resolve

Aggregate, real-world persuasion effects are repeatedly **small or zero**. *And yet* controlled,
personalized AI persuasion is now **superhuman**: Salvi et al., *Nature Human Behaviour* (2025), 900
participants — GPT-4 with basic sociodemographic data was more persuasive than humans in **64.4%**
of debates where the two differed, and the edge was **non-significant without personalization**.

Both halves are true. The reconciling variable is **personalization + scale**.

A document that reports only the debunking half is as misleading as one that reports only the alarm.
The honest version says something more specific and more useful than either: **the risk did not
disappear — it moved**, from mass broadcast to intimate one-to-one interaction, which is precisely
where almost nobody is looking for it.

And the same capability runs the other way. Costello, Pennycook & Rand (*Science*, 2024-09-13)
engaged 2,190 conspiracy believers in dialogue with GPT-4 Turbo: belief down ~**20%**, holding at
**two months**, generalizing across theories, working **even among the deeply entrenched**.

The technique is not the ethics.

---

## How this file is used

- Every entry maps to a `mechanisms.yaml` row whose `evidence` grade matches.
- `scripts/check-potestas.py` rule 7 forbids any drill, protocol, or rubric from citing a `debunked`
  row, and flags citations of `overstated` rows for review.
- This file is exempt from rule 7 by name. Cataloguing the dead is what it is for.
- Essay #2114 publishes this material outward. Nothing here is private; all of it is citation.
