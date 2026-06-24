# Beowulf Fitts 2–5: Music Arc Composition — Complete Reference Index

**Date Created:** 2026-06-24  
**Status:** Ready for music curation and composition  
**Scope:** Fitts 2, 3, 4, 5 — thematic analysis, scene progression, composer guidance

---

## Overview

This collection of documents provides a complete thematic and compositional breakdown of Beowulf Fitts 2–5, structured to support the creation of a four-fitt music arc that mirrors the poem's emotional and narrative progression.

**The Four-Fitt Arc:**
1. **Fitt 2** — Grendel's exclusion and eruption; twelve years of terror
2. **Fitt 3** — The kingdom's exhaustion; spiritual nadir; Beowulf hears and resolves
3. **Fitt 4** — The hero's embarkation and whale-road passage
4. **Fitt 5** — The hero's arrival and threshold-crossing at Hrothgar's court

**Dominant Emotional Progression:** Despair → Hope → Journey → Arrival & Protocol

---

## Document Guide

### PRIMARY REFERENCE: BEOWULF-FITTS-2-5-MUSIC-COMPOSITION-GUIDE.md
**Type:** Comprehensive thematic analysis  
**Location:** `/Users/4jp/Workspace/.limen-worktrees/studium-deepen-beowulf-ac7b/`  
**Length:** ~3,500 words  
**Format:** Markdown, narrative + structured sections

**Contents:**
- Full breakdown of each fitt (Fitts 2–5)
- For each fitt:
  - Dominant thematic force (primary + secondary)
  - Scene structure (3 major anchors per fitt = 12 total)
  - Dramatic arc (emotional progression)
  - Music arc potential (guidance per scene)
  - Force registry (breakdown of which dramatic forces appear where)
- Four-fitt synthesis section:
  - Overarching structure
  - Thematic progression
  - Dominant emotional trajectory
  - Music composition guidance (4-movement structure)
  - Force distribution table
  - Critical notes on continuity

**Use When:** You need the full intellectual foundation for understanding the thematic structure of Fitts 2–5. Read first for comprehensive context.

**Key Insight:** The dominant emotional center of the arc is Fitt 3 (the nadir); Fitts 2 and 4 are movement fitts (action); Fitts 3 and 5 are threshold fitts (transition and recognition). Law and protocol, emphasized in Fitt 5, are not decoration but the poem's structural values.

---

### SCENE-STRUCTURE REFERENCE: studium/music/beowulf/fitts-2-5-arc-reference.yaml
**Type:** Structured scene data file  
**Location:** `/Users/4jp/Workspace/.limen-worktrees/studium-deepen-beowulf-ac7b/studium/music/beowulf/`  
**Length:** ~400 lines (YAML)  
**Format:** YAML, machine-readable

**Contents:**
- Fitts 2–5 overview (emotional arc, force arc, dominant forces)
- 4 fitt entries, each containing:
  - Title and line numbers
  - Dominant force + secondary forces
  - Principle (what to emphasize, what to avoid)
  - Force arc (sequence through scenes)
  - Scenes array (each scene with: number, title, force, emotional tone, narrative, music anchor)
- Synthesis section:
  - Four-fitt structure (summaries)
  - Thematic progression
  - Force distribution
  - Composition guidance

**Use When:** You need quick reference to scene anchors during track curation. Matches the structure of `book-01.yaml` (Fitt I music arc) for consistency.

**Key Format:** Each of the 12 scenes has:
- A title (e.g., "Grendel hears the joy of Heorot")
- A force designation (from: wrath, grief, fate, desire, sacrifice, law, kingship, supplication)
- An emotional tone descriptor
- A brief narrative summary
- A "music_anchor" field with guidance for the track

---

### COMPOSER SELECTION: studium/music/beowulf/FITTS-2-5-COMPOSER-GUIDANCE.md
**Type:** Detailed composer and work-selection guidance  
**Location:** `/Users/4jp/Workspace/.limen-worktrees/studium-deepen-beowulf-ac7b/studium/music/beowulf/`  
**Length:** ~5,000 words  
**Format:** Markdown, narrative with structured sections

**Contents:**
- Individual guidance for each of the 12 scenes
- For each scene:
  - Thematic requirement (what the music must convey)
  - Emotional register (texture, not content)
  - 3–4 suggested composer approaches with reasoning
  - Critical notes (what to avoid, and why)
- Cross-fitt continuities (musical bridges between fitts)
- Practical notes:
  - Recommended timing per scene
  - How to use reprises and motifs
  - Voice vs. instrument choices
  - Tempo and dynamic range guidance
- Reference: Fitt I force arc (for comparative perspective)

**Use When:** Actively curating tracks or selecting composers. Provides concrete options and reasoning for each scene. Offers flexibility—suggestions, not prescriptions.

**Key Feature:** Avoids fixed selections (like Fitt I's specific track list) in favor of multiple viable approaches, allowing you to choose based on available recordings and your vision for the arc.

---

### SUMMARY & QUICK START: BEOWULF-FITTS-2-5-SUMMARY.txt
**Type:** Summary and orientation guide  
**Location:** `/Users/4jp/Workspace/.limen-worktrees/studium-deepen-beowulf-ac7b/`  
**Length:** ~350 lines  
**Format:** Plain text with section headers

**Contents:**
- Overview of all 3 documents and what each provides
- Quick reference: the 12 scene anchors (one-line summaries)
- Thematic breakdown (dominant forces, emotional progression)
- Key insights for composition (5 critical points)
- Files created (locations and types)
- How to use these documents (different use cases)
- Next steps for composition

**Use When:** You're new to the project or need to remember the big picture. Read this first for orientation; then move to the other documents for detail.

---

### STRUCTURAL DATA: beowulf-fitts-2-5-structure.json
**Type:** JSON data structure  
**Location:** `/Users/4jp/Workspace/.limen-worktrees/studium-deepen-beowulf-ac7b/`  
**Format:** JSON

**Contents:**
- Machine-readable breakdown of all 12 scenes
- For each scene:
  - Scene number and title
  - Dominant themes
  - Description and narrative beat
  - Emotional tone
  - Music arc potential
- Four-fitt synthesis with overarching structure, thematic progression, and composition guidance

**Use When:** You need to programmatically access scene data or integrate this into a digital tool.

---

## The 12 Scene Anchors (Quick Reference)

### Fitt 2: Grendel's Characterization & Eruption
1. **Grendel hears the joy of Heorot** — dissonant isolation theme (Fitt 2, Scene 1)
2. **The first night raid** — crescendo into violence, then silence (Fitt 2, Scene 2)
3. **Twelve years of unrelenting reign** — sustained minor/diminished harmony (Fitt 2, Scene 3)

### Fitt 3: Transition—Grendel's Terror to Beowulf's Summoning
4. **Hrothgar's helpless mourning** — dirge-like exhaustion theme (Fitt 3, Scene 1)
5. **Heathen vows at idol-shrines** — dissonant sacrifice sequence (Fitt 3, Scene 2)
6. **News reaches Beowulf in Geatland** — ascending heroic motif (Fitt 3, Scene 3)

### Fitt 4: Beowulf's Voyage Across the Whale-Road
7. **Choosing the company and launching** — martial gathering theme (Fitt 4, Scene 1)
8. **The voyage over the whale-road** — flowing, rhythmic seafaring theme (Fitt 4, Scene 2)
9. **Sighting Danish cliffs and beaching** — triumphant landfall fanfare (Fitt 4, Scene 3)

### Fitt 5: Beowulf's Arrival in Denmark & Threshold-Crossing
10. **The coast-guard challenges strangers** — formal challenge theme (Fitt 5, Scene 1)
11. **Beowulf's reply: lineage and errand** — clear statement of purpose (Fitt 5, Scene 2)
12. **The coast-guard grants passage and becomes guide** — welcoming transition theme (Fitt 5, Scene 3)

---

## Thematic Forces Across the Fitts

| Scene | Scene Title | Primary Force | Secondary Forces |
|-------|---|---|---|
| F2S1 | Grendel hears joy | grief | wrath, fate |
| F2S2 | First night raid | wrath | fate, grief |
| F2S3 | Twelve years reign | grief | fate, endurance |
| F3S1 | Hrothgar's mourning | grief | law, despair |
| F3S2 | Heathen sacrifice | fate | despair, spiritual collapse |
| F3S3 | News to Beowulf | fate | hope, resolution |
| F4S1 | Choosing company | desire | resolve, camaraderie |
| F4S2 | Whale-road voyage | desire | fate, passage |
| F4S3 | Danish cliffs | fate | arrival, gratitude |
| F5S1 | Coast-guard challenge | law | order, protocol |
| F5S2 | Beowulf declares | supplication | kingship, courtesy |
| F5S3 | Gate opens | law | hospitality, transition |

---

## Dominant Emotional Arc

**Overall Progression:** Despair → Hope → Journey → Arrival & Protocol

- **Fitt 2:** Torment → Violence → Endurance (12 years)
- **Fitt 3:** Helplessness → Spiritual Collapse → The Turn (hero hears)
- **Fitt 4:** Resolve → Passage → Arrival
- **Fitt 5:** Challenge → Declaration → Acceptance

---

## Music Arc Structure (4-Movement Form)

**Movement I (Fitt 2):** Grendel's Isolation and Eruption
- Dissonant, isolated monster-music reflecting Grendel's exclusion
- Crescendo into violence, then sustained minor/diminished harmony for twelve years
- Emotional center: the texture of an occupation that cannot be stopped

**Movement II (Fitt 3):** The Kingdom's Exhaustion
- Exhausted, dirge-like collapse reflecting Hrothgar's helplessness
- Dissonant sacrifice sequence at spiritual nadir
- Shift upward into ascending heroic motif as Beowulf hears
- Emotional center: the valley—where all resources fail

**Movement III (Fitt 4):** The Hero's Embarkation and Passage
- Martial gathering theme for assembly of will and means
- Flowing, rhythmic seafaring theme for the whale-road passage
- Triumphant landfall fanfare for arrival on Danish shore
- Emotional center: forward momentum, the answering of need

**Movement IV (Fitt 5):** Threshold and Recognition
- Formal challenge theme at the border reflecting law and protocol
- Clear, noble declaration of identity and purpose
- Welcoming transition reflecting the opening of the threshold
- Emotional center: proper form honored, the stranger accepted

---

## How to Use This Collection

### For Understanding the Poem
1. Read **BEOWULF-FITTS-2-5-SUMMARY.txt** for orientation
2. Read **BEOWULF-FITTS-2-5-MUSIC-COMPOSITION-GUIDE.md** for full thematic context

### For Quick Reference
- Use **fitts-2-5-arc-reference.yaml** as your reference document while working

### For Track Selection
1. Consult **FITTS-2-5-COMPOSER-GUIDANCE.md** for suggested composers/works
2. Reference the "music anchor" for each scene in the YAML file
3. Test selections against the emotional progression in the guide

### For Structural Continuity
- Pay special attention to the "Cross-Fitt Continuities" section in COMPOSER-GUIDANCE.md
- Consider reprising harmonic or rhythmic elements across fitts
- Use the transition moments to maintain the overall emotional arc

### For Digital Integration
- Use **beowulf-fitts-2-5-structure.json** to integrate data into tools or databases

---

## Critical Insights for Composition

1. **Grendel's presence extends beyond Fitt 2.** While Fitt 2 establishes Grendel, his occupation continues as an unspoken background through Fitts 3–5. The music should carry harmonic memory of Fitt 2's dissonance.

2. **The emotional center is Fitt 3.** This is where the Danes reach their deepest despair. It gives meaning to both Fitts 2 (the source of crisis) and Fitts 4–5 (the answering).

3. **Law and protocol are structural values.** Fitt 5's insistence on proper form (the coast-guard's challenge, Beowulf's courteous reply) is not decoration. It is the poem's claim that order, even under mortal threat, holds civilization together.

4. **Transition moments shape the arc.** The bridges from Fitt 2→3, Fitt 3→4, and Fitt 4→5 are crucial for maintaining continuity and emotional progression.

5. **The structure naturally forms four distinct movements.** Each corresponds to a phase in the narrative: (I) monster's threat, (II) kingdom's collapse, (III) hero's answering, (IV) proper entry.

---

## Next Steps for Composition

1. **Choose your emotional register.** Do these fitts follow Book I's Barber/Shostakovich register, or do they shift into a different compositional language?

2. **Identify your 12 tracks.** Use FITTS-2-5-COMPOSER-GUIDANCE.md to select composers and works that fit each scene anchor.

3. **Sequence for continuity.** Ensure the tracks flow naturally between scenes and across fitts. Use the "Cross-Fitt Continuities" section as a guide.

4. **Test the arc.** Listen to the full sequence (or read through it) alongside the poem. Does the music guide the listener through the same emotional progression as the poem?

5. **Document your decisions.** Create a companion document (like book-01.yaml) that records your selections, reasoning, and any deviations from the suggested approach.

---

## Files Manifest

| File | Location | Type | Size |
|------|----------|------|------|
| BEOWULF-FITTS-2-5-MUSIC-COMPOSITION-GUIDE.md | `/` root | Markdown | 18 KB |
| BEOWULF-FITTS-2-5-SUMMARY.txt | `/` root | Text | 9.9 KB |
| INDEX-BEOWULF-FITTS-2-5-COMPOSITION.md | `/` root | Markdown | This file |
| fitts-2-5-arc-reference.yaml | `studium/music/beowulf/` | YAML | 13 KB |
| FITTS-2-5-COMPOSER-GUIDANCE.md | `studium/music/beowulf/` | Markdown | 23 KB |
| beowulf-fitts-2-5-structure.json | `/` root | JSON | ~6 KB |

---

## Connection to Fitt I

This collection extends the Fitt I music arc documented in:
- `studium/music/beowulf/book-01.yaml` (Fitt I scene and track structure)
- `studium/essays/beowulf/book-01.md` (Fitt I thematic and compositional reasoning)
- `studium/film/beowulf.yaml` (Force mappings across the whole poem)

The Fitts 2–5 structure follows the same methodology (scene-anchor approach, force-based composition, four-movement arc) but expands the scope to 4 fitts and provides options rather than prescriptions for track selection.

---

## Version & Status

**Created:** 2026-06-24  
**Status:** Complete and ready for music curation  
**Scope:** Fitts 2–5 thematic analysis and composition guidance  
**Next Phase:** Track selection, curation, and creation of a Fitts 2–5 music arc (equivalent to book-01.yaml for Fitt I)

---

**For questions or clarifications, refer to the detailed sections in the primary reference documents. Start with BEOWULF-FITTS-2-5-SUMMARY.txt for orientation.**
