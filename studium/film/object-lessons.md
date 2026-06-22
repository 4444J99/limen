# Object lessons — the selection ethos of the daily film

> *"i asked for a movie for today — a film that is fitting and not obvious, from film history — but this
> also feeds into object lessons."*

An **object lesson** is a concrete object that makes an abstract principle *visible and teachable*. The
term is Anthony's own: his project **[Object Lessons — The Recurring Objects of Cinema](https://objectlessons.film)**
(the AMP Lab Media YouTube channel; repo `organvm/object-lessons`) traces a fixed set of objects —
**milk · mirrors · cigarettes · clocks · doors · guns · eggs · telephones · balloons · cereal** — across a
century of film, with a **253-film database** where every film carries a `letterboxd_url` and is tagged
`object → scene → {symbolic_category, tier}`.

The Studium's **fourth commentary system** (film) plugs straight into that. A day's film is chosen so it
serves *both* projects at once:

## The three-way model
```
film  ↔  { force (Studium) · object (Object Lessons) · watched (Letterboxd) }
```
- **force** — the text's encoding for today's passage (wrath, fate, grief, law …), from `dominant-force.yaml`.
- **object** — a tracked cinematic object the film carries (`object-taxonomy.yaml`), the rail into `objectlessons.film`.
- **watched** — whether it sits in his own Letterboxd history, so the pick is *personal*, not generic.

## The selection ethos (how the Film of the Day is chosen)
1. **Fitting** — it must meet *today's* division and its dominant force, not just the work in general. The
   picker (`scripts/studium.py`) promotes the film whose `divisions:` includes today's book, then falls back to force.
2. **Not obvious** — the literal adaptation is the *obvious* one and is **set aside** (Iliad → *Troy* lives in
   `adaptations:`, never promoted). The truthful object lesson usually comes from elsewhere in film history — a
   boxer's chamber-tragedy for the mēnis of Book 1, not a battle epic.
3. **From film history** — drawn from the whole century, anywhere it encodes the force most truthfully.
4. **An object lesson** — it carries a tracked **object** whose use *is* the principle: the **mirror** in
   *Raging Bull* is Achilles' geras (the prize that was only ever the self made visible); the failed
   synchronized **clock** in *Gallipoli* is kleos paid for on a gap in time.

## How it surfaces
- **Daily face** — a headline **"🎬 Today's film — an object lesson in `<force>`"** block above the full
  weekly companion (the rest of the work's films).
- **Daily page** (`ledger/`) — a logged `FILM / OBJECT LESSON:` line, so the pick is a real artifact.
- **Crosswalk** (`scripts/studium-objectlessons.py`) — joins the day's pick to his 253-film DB by Letterboxd
  slug, and to his watch history, so the Studium and `objectlessons.film` share one spine.

## Today (proof of form)
Iliad **Book 1** = *mēnis*: the quarrel, wounded honor, the seized prize, the ruinous withdrawal — **not**
battlefield violence. The fitting, non-obvious object lesson is **Raging Bull (Scorsese, 1980)** — wrath as a
wound to the self-image — with the **mirror** as the object. *Troy* (the obvious one) is set aside.
