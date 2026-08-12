# Engagement Intake Standard

**The conditions that must hold before performing paid work for anyone.**

Prose alone decays and is never read at the moment it matters — which is the moment someone is
being asked to sign quickly. So the operative half of this standard is a predicate:

```bash
scripts/engagement-guard.py --config engagements/<name>.yaml   # exit 0 ⟺ safe to keep working
scripts/engagement-guard.py --all                              # every live engagement
```

Its regression test is a real engagement that failed every rule below
(`engagements/victoroff.yaml`). **The guard must fail on that file.** A change that makes it
pass has broken the guard.

---

## Why this exists

An engagement was performed in July–August 2026 in which the contractor:

- began work **8 days before any instrument existed**,
- **signed a document with blank compensation fields** — the amount was set *after* signature,
- accepted terms where the material promise was made **in chat and never reached paper**, and
  was withdrawn 5 days later,
- was offered compensation **100% contingent** on a counterparty with **no revenue**,
- was asked to **transfer the only asset** before being paid,
- negotiated **without counsel against a counterparty who had counsel**,

and delivered **98% of a codebase for zero payment**. Every one of those is checkable in
advance. None of them required legal expertise to notice — only a list, read on day one.

This is that list.

---

## The ten rules

### 1. No work before a countersigned instrument
A document you signed and they didn't **binds only you**. It is worse than no contract, because
it creates the feeling of protection without the fact of it. Check the counterparty's signature
block and — for e-signature — the **certificate of completion**, not the copy they emailed you.

> *Failure mode observed: a DocuSign envelope reading "Completed timestamp: Pending" for two weeks
> while work continued.*

### 2. Never sign a document with blank fields
Especially compensation. If a field is blank at signature, the number gets set without you, and
your signature is already on the page.

> *Failure mode observed: "I signed it but there's empty boxes" → "what do you want to be paid ???"
> — in that order.*

### 3. Compensation must include a fixed, dated, non-contingent component
A percentage of a counterparty's revenue is worth exactly that counterparty's revenue.
For a pre-revenue company, **any percentage of nothing is nothing** — and a higher percentage of
nothing is not an improvement, though it reads like one.

Get a deposit, a retainer, or a milestone fee. Money must be due on a **date**, not on an event
the other party controls.

### 4. Verify ability to pay before extending credit
**Unpaid work is an extension of credit.** You would check a tenant's income before handing over
keys. Check: operating revenue, prior payment history, whether the entity is *raising* money
rather than *earning* it, and whether the contracting entity actually exists yet.

> *Failure mode observed: a counterparty simultaneously promising payment and circulating a $3m
> seed financing memorandum. Those two facts are the same fact.*

### 5. Retain custody of the asset until funds clear
The repository, the files, the accounts, the deployment. **Custody is the only leverage that
exists in a dispute**, it is worth everything before transfer and nothing after, and transfer is
usually one irreversible click.

Transfer is the **last** step. It is never a favour done early to unblock someone.

### 6. Deposit before build; never a lump sum on completion
Milestones convert one large act of trust into several small ones. If the counterparty cannot
pay the first milestone, you have learned that for the price of the first milestone rather than
the whole project.

### 7. Material promises go in the instrument, not the chat
If it is not in the document, it does not exist. Warm intent in a message thread is not a term,
and it evaporates precisely when it becomes expensive.

> *Failure mode observed: "obviously i would give you more than 3%" (July 29) → "i think 3% is a
> big ask for the output" (August 3). Nothing above 3% ever reached paper, so nothing was lost —
> because nothing was ever held.*

### 8. Pressure to sign fast is the signal, not the noise
A genuine deadline appears **in the document**. Urgency supplied verbally — especially late at
night, especially with a stated fear of a third party ("sign before X sues us") — is a
negotiating tactic, and it is the single most reliable predictor that the terms will not survive
reading.

**Any instrument is still there in the morning.** If it isn't, that was the answer.

### 9. Keep the commercial channel separable
Where the counterparty is also a friend, partner, or family member, the commercial relationship
still needs its own record: written scope, written terms, written acceptance. Not because the
person is untrustworthy, but because **affection and obligation get answered in the same thread**
and neither one gets answered well.

If the entire negotiation lives inside an intimate channel, there is no vantage point from which
to read it as a deal.

### 10. Log the engagement on day one
Create `engagements/<name>.yaml` **before** the first commit. Fill it in honestly — the guard is
worthless against a config written to pass. Run the guard. Re-run it whenever the position
changes.

An engagement that cannot be described in that file is one that has not actually been agreed.

---

## The intake ritual

Four commands, once per engagement, before any work:

```bash
cp engagements/examples/healthy.yaml engagements/<name>.yaml
$EDITOR engagements/<name>.yaml                              # honestly
scripts/engagement-guard.py --config engagements/<name>.yaml # must exit 0
# only then: start work
```

And whenever the position changes — a new document, a transfer request, a missed payment:

```bash
scripts/engagement-guard.py --all
```

---

## What this is not

- **Not legal advice.** It does not read contracts, judge enforceability, or replace counsel.
  It holds an engagement to conditions that are checkable without expertise.
- **Not a substitute for counsel.** Rule 9 of the guard warns on counsel asymmetry for a reason:
  if the other side has a lawyer and you do not, the terms will reflect that.
- **Not a prediction.** A counterparty who fails these checks may still pay. The rules bound the
  downside; they do not forecast anyone's behaviour.

## Related

- `scripts/engagement-guard.py` — the predicate
- `engagements/REGISTER.md` — the log
- `engagements/victoroff.yaml` — the regression test (must fail)
- `engagements/examples/healthy.yaml` — the target shape (must pass)
