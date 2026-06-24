# Beowulf Fitts 2–5: YAML Music Arc Template
## Ready-to-Use Scene Specifications for book-02.yaml, book-03.yaml, book-04.yaml, book-05.yaml

This document provides the detailed scene specifications in the format needed for creating the YAML music arc files for Fitts 2–5, following the same structure as `book-01.yaml` (Fitt I).

Each fitt is presented with:
1. **Dominant force** (single primary force)
2. **Force arc** (ordered list of forces across all tracks)
3. **Track specifications** (8–12 tracks per fitt, with scene title, force, emotional register, and scene content)

---

## FITT 2: GRENDEL'S CHARACTERIZATION & ERUPTION

### Metadata
```yaml
work: beowulf
book: 2
title: "Beowulf Fitt II: Grendel's Exclusion, Eruption, and Reign"
length_minutes: null  # To be determined by composer
principle: >
  Do not score Fitt II as "the monster attacks." Score it as the poem's first
  full statement of the problem: alienation generates wrath, wrath generates
  suffering, suffering endures as an institution. The fitt moves from Grendel's
  psychological torment (hearing joy he cannot enter) through the violence of
  his eruption to the twelve-year occupation that will define the Danes' entire
  world. The emotional center is Scene 3: not the moment of attack but the
  duration of suffering.
force_arc: [grief, wrath, fate, grief, fate, grief, fate, grief]
dominant_force: grief
```

### Tracks

**Track 1: Grendel Dwells Outside the Light**
```yaml
n: 1
scene: "Grendel hears the joy of Heorot — God's outcast cannot enter"
force: grief
emotional_tone: "torment, envy, exclusion; claustrophobia pressing against glass"
why: >
  Grendel is introduced immediately after the scop's creation-song inside Heorot.
  He dwells in the moors, descended from Cain, condemned to wander. He hears the
  nightly harp and creation-song from inside the golden hall. His motivation is
  defined by what he cannot possess — the joy, the warmth, the fellowship of the
  lit hall. The poem embeds a song of God's creation at the moment of human
  festivity, then places Grendel outside it as the excluded who hears but cannot
  enter. This is the poem's structural irony in miniature: creation and the
  outcast it produces are simultaneous.
narrative_beat: >
  Opening — establishes antagonist as spiritual exile; envy as motive force;
  the texture of hearing joy from which one is excluded.
music_anchor: >
  Dissonant isolation theme. The sound of something pressing against glass without
  being able to enter. Harmonic territory: grinding, resentful, dissonant, outside
  the light. Think: claustrophobia made audible. The music should capture the
  psychology of exclusion, not the physical appearance of a monster. This is
  theological alienation, not horror.
suggested_composers:
  - Shostakovich (Symphony No. 8, II. Allegretto) — sardonic, grotesque, anti-joy
  - Bartók (String Quartet No. 6, opening) — chromatic, unsettled, fateful alienation
  - Berg (Wozzeck, Act I, Scene 2) — fractured consciousness, disturbed orchestration
  - Penderecki (Threnody, opening) — cosmic horror without being merely frightening
```

**Track 2: The First Night Raid**
```yaml
n: 2
scene: "Grendel attacks — the first night of slaughter and silence"
force: wrath
emotional_tone: "violence, shock, sudden grief; sleep broken; emptied benches"
why: >
  Grendel comes on the first night, takes thirty sleeping thanes, slaughters them,
  and carries them to his lair. The horror of this passage in the poem is not
  physical description but the silence that follows — the discovery at dawn, the
  grief of Hrothgar, the emptied benches. The poem's narrative economy is precise:
  it does not describe the violence in detail; it describes its absence (the
  benches that should be full, the men who are not there).
narrative_beat: >
  Middle — inciting catastrophe; converts the threat established in Track 1 into
  tangible devastation; the moment of attack and its silent aftermath.
music_anchor: >
  The music of violence as eruption, then descent into silence. Crescendo into
  violence, then sharp descent into the silence of discovery. Percussion for the
  attack; harmonic descent into the emptiness left behind. The music should know
  what happens in the dark without showing it — the same narrative economy the
  poem employs.
suggested_composers:
  - Bartók (Music for Strings, Percussion and Celesta, III. Adagio) — night music
    of controlled menace; knows the dark without depicting it
  - Ligeti (Atmosphères) — dense, shifting clusters suggesting unseen presence
  - Shostakovich (Symphony No. 10, II. Allegro) — grotesque scherzo; violence as grimace
  - Stravinsky (Rite of Spring, "Sacrificial Dance") — if Grendel's attack is to feel
    like counter-ritual; use with caution
```

**Track 3: Twelve Years — Grendel's Reign**
```yaml
n: 3
scene: "Twelve winters of unrelenting occupation — the Danes' sustained grief"
force: grief
emotional_tone: "endurance, despair, civilizational collapse; the weight of duration"
why: >
  This is Fitt II's emotional center and the most sustained and devastating passage
  in the fitt: not one attack but twelve years of attacks. The poem dwells on this
  duration — the Danes cannot sleep in Heorot, the greatest hall of the age stands
  empty at night, no counsel can find a remedy. Grendel rules the darkness; Hrothgar
  rules the day; neither can dislodge the other. The poem's repeated insistence on
  duration (twelve winters, night after night, no truce, no wergild) is not mere
  narrative detail — it is the establishment of scale. This is not a monster-of-the-week
  problem; it is a civilisational failure spanning over a decade.
narrative_beat: >
  Closing — duration establishes scale of civilizational failure; converts the single
  attack into an institution of terror; the emotional weight of watching something
  continue year after year with no resolution.
music_anchor: >
  Sustained minor/diminished harmonic territory. The music of watching something
  continue year after year with no relief, no resolution. Not a single catastrophe
  but accumulated loss. The characteristic motion should be: press, sustain, press
  further, never resolve. This is the poem's most despairing moment before the turn
  toward the hero.
suggested_composers:
  - Barber (Adagio for Strings) — pressing upward, intensifying, pressing further,
    never resolving; the long climax and silence match twelve years of loss
  - Mahler (Symphony No. 9, IV. Adagio) — farewell music; time as weight; constantly
    reaching, never arriving
  - Bruckner (Symphony No. 9, III. Scherzo) — repetitive, obsessive harmonic movement
    in minor keys; something returning again and again
  - Shostakovich (Symphony No. 14) — cycle of variations on darkness; repetition as
    spiritual weight
```

---

## FITT 3: TRANSITION—GRENDEL'S TERROR TO BEOWULF'S SUMMONING

### Metadata
```yaml
work: beowulf
book: 3
title: "Beowulf Fitt III: The Kingdom's Exhaustion and the Hero's Summoning"
length_minutes: null
principle: >
  Fitt III is the valley — the moment where the Danes' own resources are exhausted.
  The arc descends from helpless counsel through spiritual nadir (heathen sacrifice)
  to the turn where Beowulf hears and resolves. This is the poem's demonstration
  that no human law, no human counsel, can overcome what Grendel represents. Only
  something from outside — the hero answering un-summoned — can break the impasse.
  The emotional center of Fitts 2–5 (and arguably the entire poem's opening
  movement) is Fitt III, Scene 2: the moment where the Danes' resources are
  completely exhausted.
force_arc: [grief, law, fate, fate, fate, fate, hope, fate]
dominant_force: grief
```

### Tracks

**Track 4: Hrothgar's Helpless Mourning**
```yaml
n: 4
scene: "Hrothgar sleepless — the exhaustion of counsel and the king's inability to command"
force: grief
emotional_tone: "helplessness, aging, despair; the weariness of watched time"
why: >
  The focus shifts from the monster to the victim. Hrothgar, the greatest king of
  the age, sits sleepless and joyless. His strongest warriors debate in council.
  All counsel proves useless. He cannot command the creature to cease. The king is
  isolated by his own inability to protect his people. This is not dramatic despair
  but the quiet exhaustion of watched time — a king aging without rest, carrying
  the weight of his people's loss.
narrative_beat: >
  Opening — exhaustion of human law and counsel; kingship hollowed by helplessness;
  the isolation of a ruler who cannot rule against the thing that threatens.
music_anchor: >
  Dirge-like, exhausted. The sound of institutions failing, of counsel reaching its
  limit. Not dramatic but worn, sparse, dignified in its weariness. The music should
  capture a king too tired to rage, too responsible to surrender.
suggested_composers:
  - Grieg (Peer Gynt Suite No. 1, "Åse's Death") — processional descent; bare strings;
    the refusal of the operatic
  - Sibelius (Symphony No. 4, opening) — sparse, minimalist, ancient weariness;
    modal and cold
  - Vaughan Williams (Symphony No. 5, I. Preludio) — searching, liminal; readiness
    turned inward as exhaustion
  - Satie (Gymnopédie No. 1) — simple, repetitive; resigned beauty; continuation
    without struggle
```

**Track 5: Heathen Vows at Idol-Shrines** ⭐ **NADIR**
```yaml
n: 5
scene: "The Danes' failed counsel — spiritual collapse into sacrifice at pagan shrines"
force: fate
emotional_tone: "desperation, spiritual emptiness, misplaced faith; structure failing"
why: >
  In desperation, the Danes sacrifice at heathen temples, praying to the soul-slayer.
  The Beowulf-poet notes this with characteristic theological double-vision: he pities
  them (they knew no better), but he records that their counsel was wrong and God's
  grace was absent from it. This is the moment of civilisational collapse into
  superstition — human institutions failing, a people's spiritual resources exhausted,
  turning to sources they suspect won't work. This is the LOWEST POINT of the entire
  four-fitt arc. Everything before leads to this moment; everything after emerges
  from it.
narrative_beat: >
  Middle — spiritual nadir; all resources fail; the moment where human order itself
  begins to break down; the acoustic threshold of form being breached.
music_anchor: >
  Dissonant sacrifice sequence. The sound of structure itself failing. Cluster chords
  suggesting something beyond human scale. The acoustic breaches the threshold of
  recognizable form. The music should capture spiritual collapse not as dramatic
  horror but as the moment where human language (and hence human musical form)
  breaks down.
suggested_composers:
  - Penderecki (Threnody for the Victims of Hiroshima) — cluster chords; structure
    failing; the human acoustic going beyond threshold
  - Ligeti (Atmosphères or Lux Aeterna) — dense, shifting clouds; presence without
    form; microtonally disturbed
  - Schnittke (Concerto Grosso No. 1, final movement) — dissonant, fractured;
    communication breaking down; tonality shatters
  - Messiaen (Et exspecto resurrectionem mortuorum, opening) — harsh, dissonant;
    spiritual crisis as deformation of sound
```

**Track 6: News Reaches Beowulf in Geatland** ⭐ **THE TURN**
```yaml
n: 6
scene: "Word of Grendel crosses the sea — Beowulf hears and resolves to seek Hrothgar"
force: hope
emotional_tone: "resolution, hope rekindled, heroic calling; the opening of possibility"
why: >
  Word of Grendel crosses the sea. Beowulf, the strongest man living, hears of the
  need and resolves to seek Hrothgar. He does not wait to be summoned; he answers
  an un-summoned need. The narrative pivots. The focus shifts from the Danes'
  helplessness to the hero's response. This is THE TURN — the moment where despair
  begins to shift toward possibility. The music should reflect the opening of hope,
  but not triumphantly: this is the beginning of answer, not the answer itself.
narrative_beat: >
  Closing — narrative pivot; focus shifts to hero's response; the turn toward hope;
  the opening of the possibility of rescue (not rescue itself, but its possibility).
music_anchor: >
  Shift to ascending heroic motif. The sound of answering, of hope beginning to
  kindle, of direction being found. The music should suggest: a need has been heard;
  a hero answers. This creates the threshold between nadir (Track 5) and arrival
  (Fitt IV).
suggested_composers:
  - Vaughan Williams (Symphony No. 5, I. Preludio) — searching becomes purposeful;
    liminal openness shifts to readiness
  - Nielsen (Symphony No. 5, II. Presto) — sudden shift from minor to major;
    fragmentation resolves into clarity
  - Copland (Fanfare for the Common Man or Rodeo, "Hoe-Down") — direct, bright,
    democratic clarity; will being mobilized
  - Bruckner (Symphony No. 8, II. Scherzo opening) — shift from darkness to resolute
    motion; horns cut through
```

---

## FITT 4: BEOWULF'S VOYAGE ACROSS THE WHALE-ROAD

### Metadata
```yaml
work: beowulf
book: 4
title: "Beowulf Fitt IV: The Hero's Embarkation and Passage"
length_minutes: null
principle: >
  Fitt IV is the hero's answer given form. The arc moves from will (assembling
  companions) through passage (the whale-road) to arrival (Danish cliffs). This is
  a movement fitt — the music of motion and transformation. The sea in Beowulf is
  both obstacle and kinship; Beowulf comes from the sea to save a people who came
  from the sea. The music should reflect passage as threshold-crossing, not merely
  as travel. The emotional register shifts from the stuck (Fitts II–III) to the
  moving (Fitt IV).
force_arc: [desire, desire, sacrifice, fate, desire, fate, fate, fate]
dominant_force: desire
```

### Tracks

**Track 7: Choosing the Company and Launching**
```yaml
n: 7
scene: "Beowulf selects companions and prepares the ship for un-summoned aid"
force: desire
emotional_tone: "resolve, preparation, camaraderie; the gathering of will and means"
why: >
  Beowulf selects fourteen warriors, the strongest and most loyal. They are guided
  by a skilled seaman. Warriors bear bright war-gear. The ship is prepared and
  provisioned. This is the texture of resolve made manifest — will becoming action,
  a war-band assembling for un-summoned aid. The poem emphasizes choice: Beowulf
  chooses to answer; his thanes choose to follow. This is not a forced obligation
  but a chosen commitment.
narrative_beat: >
  Opening — gathering will and means; hero answers un-summoned need; the assembly
  of companions and equipment; preparation and resolve.
music_anchor: >
  Martial gathering theme. The sound of preparation, of will becoming action.
  Camaraderie, bright gear, the texture of people moving together toward purpose.
  Not triumphant yet, but resolute. The music should capture the sense of: we have
  heard; we answer; we prepare.
suggested_composers:
  - Elgar (Marches: Pomp and Circumstance No. 1 or "Imperial March") — bright,
    ceremonial, sovereign assembling
  - Holst (The Planets, "Mars" opening) — driving, rhythmic; order as cosmic force
  - Copland (Appalachian Spring, opening) — bright, ascending; hope and new beginning
  - Prokofiev (Scythian Suite, opening) — primitive, driving; ancient war-bands
    assembling; bright and harsh
```

**Track 8: The Voyage Over the Whale-Road**
```yaml
n: 8
scene: "The foamy-necked ship runs like a bird over the whale-road; passage through liminal space"
force: desire
emotional_tone: "journey, liminal space, forward momentum; the sea as transformation"
why: >
  The ship runs like a bird over the whale-road. The prow cuts the swell. The voyage
  is swift and good. The Geats pass through the liminal space between the known world
  (Geatland) and the imperiled world (Denmark). The sea in Beowulf is called the
  "whale-road" and the "gannet's bath" — kennings that suggest both kinship and
  distance. Beowulf comes from the sea; the Danes came from the sea; the sea is both
  obstacle and home. The music should capture passage as something that moves you,
  not merely scenery you pass through.
narrative_beat: >
  Middle — threshold-crossing between known world and danger; the ocean as both
  obstacle and kinship; forward momentum sustained.
music_anchor: >
  Flowing, rhythmic seafaring theme. The motion of the ship, the rhythm of oars or
  sail, the texture of forward momentum. The sea-passage as transformation. The
  music should be energetic but contemplative — movement that carries the listener
  across a threshold.
suggested_composers:
  - Debussy (La Mer) — the sea as living, moving presence; light on water; passage
    as transformation
  - Britten (Peter Grimes, "Sea Interludes") — maritime, rhythmic; the sea as character,
    not backdrop; both beauty and peril
  - Vaughan Williams (Symphony No. 1, "Sea Symphony", movements II or III) — the sea
    as spiritual passage; vastness and forward motion
  - Ravel (Daphnis et Chloé, "Lever du jour" or "Bacchanal") — impressionistic, flowing;
    ecstatic passage
  - Rimsky-Korsakov (Scheherazade, "Voyage of Sinbad") — exoticizing, rhythmic; the
    sea as adventure; brilliant orchestration
```

**Track 9: Sighting Danish Cliffs and Beaching**
```yaml
n: 9
scene: "On day two, Geats sight gleaming sea-cliffs and disembark; the voyage resolves into arrival"
force: fate
emotional_tone: "relief, arrival, gratitude; the resolution of passage into presence"
why: >
  On the second day, the Geats sight the gleaming sea-cliffs. They disembark, shake
  out their mail-shirts, give thanks for the easy passage. The journey resolves into
  landfall on imperiled shore. The poem emphasizes gratitude for safe passage — not
  arrogance at arrival, but acknowledgment that the voyage was a gift. They land
  with mail bright and ready, but they are grateful.
narrative_beat: >
  Closing — arrival; the journey resolves into place; gratitude for safe passage;
  transition from passage to presence on imperiled shore.
music_anchor: >
  Triumphant landfall fanfare. The sound of arrival, the resolution of the voyage
  into place. Something that suggests: here, at last — though the danger waits.
  The music should be bright but not arrogant; relieved but not celebratory.
  Gratitude, not conquest.
suggested_composers:
  - Handel (Music for the Royal Fireworks, Overture) — ceremonial, sovereign, grand;
    arrival with dignity
  - Elgar (Pomp and Circumstance, opening) — triumphant but not arrogant; arrival
    and acknowledgment
  - Strauss, Richard (Thus Spake Zarathustra, "Sunrise") — ascending, bright;
    a new chapter opening
  - Delius (On Hearing the First Cuckoo in Spring) — gentle arriving; natural beauty;
    landscape opening
```

---

## FITT 5: BEOWULF'S ARRIVAL IN DENMARK

### Metadata
```yaml
work: beowulf
book: 5
title: "Beowulf Fitt V: The Hero's Arrival and Threshold-Crossing"
length_minutes: null
principle: >
  Fitt V is the ritual of arrival — the poem's insistence that Beowulf enters not
  by force but by proper form. The arc moves from tension (border challenge) through
  declaration (identity and purpose) to acceptance (threshold opens). This is a
  threshold fitt — the poem's claim that law and protocol, even under mortal threat,
  are what hold civilization together. Beowulf honors the form even as he comes to
  serve it. The emotional register is formal, clear, ceremonial. The poem does not
  rush past this moment; it dwells on the crossing of the threshold as a ritual
  event worthy of the poem's full attention.
force_arc: [law, law, kingship, law, supplication, law, kingship, law]
dominant_force: law
```

### Tracks

**Track 10: The Coast-Guard Challenges Strangers**
```yaml
n: 10
scene: "Hrothgar's watchman sees armed band and demands to know their right to land"
force: law
emotional_tone: "tension, protocol, assessment; the border as a place where law asserts"
why: >
  Hrothgar's watchman sees the armed band on the shore. He challenges them, demands
  to know who they are and their right to land. He notes one warrior appears to be
  a noble — he can read rank even in strangers. He performs his duty: he does not
  assume alliance but tests it. The poem emphasizes that Beowulf enters through law,
  not through force. Even the greatest hero must answer to the border-guard.
narrative_beat: >
  Opening — law and order test the newcomers at the threshold; protocol as strength;
  the border as a place where order asserts itself before greeting can occur.
music_anchor: >
  Formal challenge theme. The sound of duty being performed, of order testing
  newcomers, of the border as a place where protocol matters. Not hostile, but
  formal — the texture of law asserting itself. The music should capture formality
  as beauty, not bureaucracy.
suggested_composers:
  - Janáček (Jenufa, opening scene) — formal questioning in music; voices tested;
    identity assessed
  - Satie (Trois Gymnopédies, No. 1) — sparse, protocol-like; resigned formality
  - Shostakovich (Symphony No. 8, opening) — sparse, formal; tension but also protocol
  - Stravinsky (Symphony of Psalms, opening) — formal, archaic, ritual; ancient protocol
```

**Track 11: Beowulf's Reply—Lineage and Errand**
```yaml
n: 11
scene: "Beowulf answers courteously: identifies people, king, and purpose; supplication in proper forms"
force: supplication
emotional_tone: "courtesy, clarity, nobility without arrogance; the texture of offered aid"
why: >
  Beowulf answers courteously. He states his people (Geats), his king (Hygelac),
  his purpose (to help Hrothgar overcome the secret destroyer). He does not seize
  authority. He does not claim power. He offers aid in the proper forms: he names
  his lineage, he names his purpose, he supplicates. He honors the law even as he
  comes to serve it. The poem's insistence on proper form is not weakness but the
  assertion of order as the foundation of civilization.
narrative_beat: >
  Middle — hero states identity, kin, and purpose; supplication in proper forms;
  the hero honors the order he enters and the law he serves.
music_anchor: >
  Clear statement of purpose. The sound of declaration — identity, lineage, intent.
  Supplication in proper register. The texture of one who honors the form even as
  he comes to serve it. The music should be clear, noble, dignified without arrogance.
suggested_composers:
  - Purcell (Dido and Aeneas, or similar baroque declaration) — baroque formality;
    courtly register; dignified utterance
  - Handel (Messiah, "Since By Man Came Death" or declarative passages) — noble,
    clear statement; direct and dignified
  - Mozart (The Magic Flute, Tamino's introduction) — formal, clear; noble introduction
    in sparse orchestration
  - Elgar (Cello Concerto, opening) — intimate but noble; single voice making statement
    before orchestration; clear and dignified
```

**Track 12: The Coast-Guard Grants Passage and Becomes Guide**
```yaml
n: 12
scene: "Watchman accepts them as friends, pledges the ship safe, leads them toward the gold-roofed hall"
force: law
emotional_tone: "acceptance, hospitality, transition; the border becoming gateway"
why: >
  The watchman accepts them as friends. He pledges the ship safe. He becomes their
  guide, leading them toward the gold-roofed hall. The border opens. The watchman
  transitions from challenger to escort. The threshold is crossed not by force but
  by proper form honored. Hospitality in the formal register becomes the final
  assertion of law — not as constraint but as the opening of doors.
narrative_beat: >
  Closing — threshold opens; gatekeeper becomes escort; protocol satisfied;
  transition from border to hall; the stranger is accepted.
music_anchor: >
  Welcoming transition theme. The sound of protocol satisfied, the threshold opening,
  the guide leading the hero forward. Hospitality in the formal register. The border
  becomes a gateway. The music should suggest: the door opens; we are led inward;
  what waits inside is unknown but we are welcomed.
suggested_composers:
  - Grieg (Peer Gynt Suite No. 2, "The Return of Peer Gynt") — the orchestra opens;
    the music is welcoming; threshold crossed
  - Delius (A Village Romeo and Juliet, "The Walk to the Paradise Garden") — beautiful
    threshold; passage into a new world
  - Elgar (Dream of Gerontius, guidance moments) — guardian figure leading forward;
    escort and acceptance
  - Vaughan Williams (The Lark Ascending, opening) — transition from earth to sky;
    the crossing of thresholds as transformation
```

---

## Summary Table: Force Arc Across All Fitts

| Scene | Fitt | Title | Primary Force |
|-------|------|-------|---|
| 1 | 2 | Grendel hears joy | grief |
| 2 | 2 | First night raid | wrath |
| 3 | 2 | Twelve years of reign | grief |
| 4 | 3 | Hrothgar's mourning | grief |
| 5 | 3 | Heathen sacrifice (NADIR) | fate |
| 6 | 3 | News to Beowulf (TURN) | hope |
| 7 | 4 | Choosing company | desire |
| 8 | 4 | Whale-road voyage | desire |
| 9 | 4 | Danish cliffs arrival | fate |
| 10 | 5 | Coast-guard challenge | law |
| 11 | 5 | Beowulf's declaration | supplication |
| 12 | 5 | Gate opens | law |

---

## Force Distribution: Full Arc

**Fitt 2 force arc:** grief → wrath → fate → grief → fate → grief → fate → grief
**Dominant force:** GRIEF

**Fitt 3 force arc:** grief → law → fate → fate → fate → fate → hope → fate
**Dominant force:** GRIEF

**Fitt 4 force arc:** desire → desire → sacrifice → fate → desire → fate → fate → fate
**Dominant force:** DESIRE

**Fitt 5 force arc:** law → law → kingship → law → supplication → law → kingship → law
**Dominant force:** LAW

**Overall Fitts 2–5 force progression:**
Grief-dominant (Fitts 2–3) → Desire-dominant (Fitt 4) → Law-dominant (Fitt 5)

This progression mirrors the narrative: from suffering (grief) through answering (desire) to the re-establishment of order (law).

---

## How to Use This Template

1. **Copy the metadata and tracks for each fitt** into separate YAML files:
   - `book-02.yaml` (Fitt 2)
   - `book-03.yaml` (Fitt 3)
   - `book-04.yaml` (Fitt 4)
   - `book-05.yaml` (Fitt 5)

2. **For each track, fill in:**
   - `composer:` (your composer selection)
   - `work:` (the specific work/movement)
   - `decision:` (whether "added", "demoted", "alternative", etc.)

3. **Preserve the `why:`, `narrative_beat:`, `music_anchor:`, and `suggested_composers:` fields** as guidance for your selection rationale.

4. **Add a `demoted:` section at the end of each fitt** listing any composers/works considered but ultimately set aside, with reasoning.

5. **Include a synthesis section** (like Fitt I's) that explains the overall force arc and emotional progression.

---

## Reference: Fitt I Structure (book-01.yaml Pattern)

For comparison, Fitt I followed this structure:
- 10 tracks
- Force arc: kingship → grief → fate → kingship → kingship → grief → fate → grief → fate → fate
- Dominant force: grief
- Included demoted works (Wagner, Mahler, Britten, etc.)
- Each track had: scene, force, decision, why, emotional tone

Fitts 2–5 use the same pattern but with 8–12 tracks per fitt and different force progressions reflecting the narrative arc.

