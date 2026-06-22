# Rubric — Film Engagement

Film is the fourth commentary system. Where music meets the passage's force as sound, a film that
"relates" meets it as image, time, and human action — an independent account of the same force
(wrath, fate, grief, law) rendered in another medium entirely. The unit of engagement is the
*reading the film forces back onto the text*: not "did I enjoy it" but "what did the film make
visible in the work that the page, the score, and the handwriting had not."

**This rubric is diagnostic, never gatekeeping. A low day is data — evidence of a film that didn't
yet connect, or a force you hadn't yet heard the work demand — not failure.** ([[no-never-happens-again]])

---

## The four levels

### 1 — Nascent

You watched the film and registered the pairing. You can state which force it was matched to and that
the work shares it. The connection is asserted but not yet shown — "Apocalypse Now is about wrath, and
so is the Iliad." The fourth commentary has been received; the conversation has not started.

*Observable sign:* You can name the film, its force tag, and the work's shared force. No specific scene
of the film is connected to a specific division of the text.

---

### 2 — Developing

You can connect one concrete moment in the film to one moment in the work through the shared force —
a shot, a cut, a performance choice set beside a scene, a line, a turn in the text. The pairing is
argued, not asserted: you can say what the film does with the force and where the work does the same.

*Observable sign:* The note references a specific film scene AND a specific division, joined by the
force (per `../dominant-force.yaml`). The claim is a sentence, not a label.

---

### 3 — Practiced

The film operates as a reading. It illuminates something in the work the other three commentaries
left implicit — the way Paths of Glory exposes that Book 1 is a *legal* crisis before it is a martial
one, or the way Letters from Iwo Jima makes Book 24's mercy structurally legible. You can also say
where the film *fails* the work — where the force is cheapened, simplified, or scored for sentiment —
and that failure teaches you what the work refuses to do.

*Observable sign:* The note contains a claim about the *text* that the film made visible, and (often)
a claim about where the film falls short of the text. Either could refine `film/<work>.yaml`.

---

### 4 — Fluent

The pairing has become generative across mediums. You hear how the film, the score, the script, and
the translation are four readings of one force, and you can say what only the *film* — its duration,
its faces, its montage — could contribute that none of the others could. A fluent day may produce a
line that goes into an essay, a better film for the companion, or a counter-system observation (this
Western film's wrath against an Eastern work's renunciation of it). The verdict is not a review; it is
a contribution to the transmission record and a candidate for the community Watch-Along.

*Observable sign:* The note synthesizes across two or more mediums and isolates the film's specific
contribution. It could seed a `film/<work>.yaml` entry, an essay paragraph, or a trial claim.

---

## How to use this

Film is a **weekly** medium, not a daily one — score it on the week's screening, not every day, and
keep the practice finite (the protocol's principle: "do not let this become an infinite research
swamp"). The grief / lament / mercy films belong to a work's late divisions; screen them there, as the
music layer reserves the funeral-march for the catastrophe. A sustained run of 1s is a signal to change
the screening conditions (watch actively, then annotate; pick a film whose force you have actually felt
the work demand) — never a signal to drop the medium. Logging a film-engagement score emits a
`film_react` event for the analysis layer (`../analysis/events-schema.yaml`).
