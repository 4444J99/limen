# Rubric — Disclosure (what truth costs, and who has shown they will hold it)

Telling someone something true about yourself is an **expenditure**. It costs exposure, and the cost
is real whether or not it is received. This rubric scores whether that expenditure is **priced to
demonstrated reception** — how much you spend on a person as a function of what they have visibly
done with what you already gave them.

It does not score how well you said it. It does not score whether you were understood. Both of those
put the outcome in someone else's hands, and the skill here is the part that is in yours: **reading
reception early, and pricing accordingly.**

**Diagnostic, never gatekeeping. Being unreceived is not a low score — spending without ever checking
is.** The counter-position is built in, as everywhere in the Studium: the case against pricing is
that love is supposed to be unconditional and accounting is supposed to be cold. That objection is
answered in *What this is not*, below, and it deserves the answer.

---

## The four signs

Reception is **observable**. That is what makes this dynamic rather than a mood — the discriminator
is evidence, not how you feel about the person on a given day. Four signs, in ascending cost to
observe:

**1 — Re-entry cost.** After a silence, who re-opens? This is the cheapest sign in existence and the
most predictive: it costs nothing, requires no disclosure at all, and is legible within weeks of
meeting someone. It is the one to watch **before** anything is spent.

**2 — Answered or absorbed.** A sincere disclosure gets a response *addressed to it* — versus a
redirect to a task, a change of subject, or silence. The distinction is not warmth. A brief, awkward,
badly-worded reply that is *about the thing you said* is reception. A gracious reply about something
else is not.

**3 — Behavior change.** Does anything the other person *does* differ after being told? Words that
change nothing twice are priced accordingly the third time. Note the asymmetry this exposes: a person
can be entirely sincere in the moment of hearing and still change nothing, and the sincerity is not
the variable that matters to you.

**4 — Reciprocal spend.** Do they ever disclose unprompted — not in answer to your question, not as a
trade, but because they decided to? This is the most expensive sign to observe because it requires
waiting, and waiting feels like withholding when it is actually just *not yet knowing*.

---

## The four levels

### 1 — Nascent

Truth is spent uniformly. Everyone gets the same access, or the same silence, and reception is not
examined at all. Disclosure is treated as a property of *you* — "I'm an open person," "I don't talk
about that" — rather than as a transaction with a counterparty who has a track record.

*Observable sign:* You cannot say, for a specific person, what they did with the last real thing you
told them. Not "they reacted badly" or "they were fine" — what they **did**.

---

### 2 — Developing

Reception is noticed, but afterward. The pattern is visible in retrospect — you can narrate, later
and accurately, that a disclosure went nowhere — and the pricing lags the evidence by one or more
rounds. Often the retrospective read is correct and simply arrives too late to have changed anything.

*Observable sign:* You can name what happened to your last three disclosures with a person, and the
size of the fourth was not different because of it.

---

### 3 — Practiced

Disclosure is sized to evidence, and **revised as evidence arrives** — in both directions. A person
who receives well gets more; a person who has now twice redirected gets less, without a conversation
about it and without a verdict about their character. The revision is quiet, ongoing, and specific to
the counterparty.

Crucially, the read is held **provisionally**. Reception changes. A person under load receives badly
and later receives well; a new person's early signs are a small sample. Practiced means the estimate
updates, not that it locks.

*Observable sign:* Two different people, at the same moment, are getting measurably different amounts
of you — and you can state the evidence for each without referring to how much you like them.

---

## What this is not

**Uniform withholding is not the top level.** Spending nothing on everyone scores *identically* to
spending everything on everyone. Both are unpriced; both are a policy adopted in advance of any
evidence. A person who has decided never to say anything real has not learned this skill — they have
opted out of the measurement and kept the certainty.

**Withholding to produce an effect is also unpriced.** Going quiet *so that they notice* is the same
game with the sign flipped: the day is still organized around their reaction, and the terms are still
theirs. The honest form of spending less is **declining to spend where it demonstrably does not
land** — which is distinguishable from the tactical form by exactly one test: *are you watching for
a response?* If yes, it is a move.

**This is not a verdict on anyone.** Reception is a fact about an exchange, not a rank of a person.
Someone can be kind, decent, and worth knowing, and still be a person who does not do anything with
what you tell them. Those are compatible. The rubric measures the second thing and says nothing about
the first, and conflating them is the fastest way to turn a useful instrument into a grievance.

**And the objection deserves its answer.** *Isn't pricing what you say to people the opposite of
intimacy?* No — the opposite of intimacy is spending indiscriminately, because that makes the
disclosure about your need to say it rather than about them. Sizing what you give to what a specific
person has shown they can hold is not coldness. It is the difference between talking *to* someone and
talking *near* them.

---

## How to use this

Slow cadence. Score a specific exchange after the fact, in the day's ledger
(`../ledger/studium-YYYY-MM-DD.md`), the same way any other rubric is scored here — self-scored, one
exchange, no automation.

**Keep no running score of any person.** There is no per-person index, no history, no trend line. The
signs exist to be read **early, with new people, before much is spent** — not to re-litigate anyone.
A file that accumulates evidence about one person is a dossier, and building one is a way of
continuing to think about them while calling it growth.

Emits a `rubric_score` event with `rubric: disclosure` (`../analysis/events-schema.yaml`) — level
only, never a counterparty, per the schema's non-PII posture.
