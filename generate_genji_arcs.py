import os

book02_yaml = """# Tale of Genji — Chapter 2 (Hahakigi / The Broom Tree) — curated music arc
work: tale-of-genji
book: 2
title: "The Broom Tree: The Taxonomy of Desire"
length_minutes: 50
principle: >
  Score the shift from the abstract, social categorization of women in the
  'rainy night' conversation to the sudden, specific, and uncontainable reality
  of Genji's desire for Utsusemi. The register begins in courtly comedy and
  descends into chromatic longing.
force_arc: [comedy, memory, desire, law, desire]
dominant_force: desire
tracks:
  - n: 1
    scene: "The rainy night conversation / classifying women"
    force: comedy
    composer: Mozart
    work: "Così fan tutte, K. 588 — Overture"
    decision: added
    why: >
      The famous 'rainy night ranking of women' is a cynical, stylized male
      conversation about the categories of female availability and virtue.
      Mozart's overture gives the exact texture of this social geometry:
      brilliant, perfectly proportioned, and fundamentally unserious. It is
      the sound of desire treated as a solvable equation rather than a
      destructive force.
  - n: 2
    scene: "To no Chujo's tale of the vanished woman / the reality of regret"
    force: memory
    composer: Fauré
    work: "Élégie, Op. 24"
    decision: added
    why: >
      The conversation shifts from abstract taxonomy to To no Chujo's specific
      memory of a woman who disappeared from neglect. The cello line in
      Fauré's Élégie drops the temperature of the room—it is the sound of past
      carelessness returning as permanent regret. The comedy evaporates,
      replaced by the specific weight of a lost object.
  - n: 3
    scene: "Genji travels to the Governor of Kii's house / escaping the palace"
    force: desire
    composer: Debussy
    work: "Prélude à l'après-midi d'un faune"
    decision: added
    why: >
      Genji's excursion to the middle-class house of the Governor of Kii
      introduces a new kind of atmosphere: less formal, more sensual, outside
      the suffocating protocols of the imperial court. Debussy's Prélude gives
      the exact climate of this displacement—a fluid, heat-heavy chromaticism
      where boundaries begin to dissolve and unexpected desires can surface.
  - n: 4
    scene: "Utsusemi's rigid morality / the barrier of her modesty"
    force: law
    composer: Bach
    work: "The Art of Fugue, BWV 1080 — Contrapunctus I"
    decision: added
    why: >
      Utsusemi is not a court lady; she is a provincial governor's wife who
      understands her precarious social position. Her resistance to Genji is
      not coquetry; it is a desperate defense of the only architecture that
      protects her: the rules of propriety. Bach's strict counterpoint is the
      sound of that defensive architecture—beautiful, unyielding, and entirely
      built on rule.
  - n: 5
    scene: "Genji enters Utsusemi's room / the consummation"
    force: desire
    composer: Scriabin
    work: "Symphony No. 4, 'The Poem of Ecstasy' (opening)"
    decision: added
    why: >
      Genji's intrusion and the subsequent consummation bypass Utsusemi's
      defenses completely. Scriabin's chromatic longing gives the texture of
      this overriding force. It is not aggressive or martial; it is
      overwhelming, sweeping away the strict counterpoint of her resistance
      in a wash of harmonically unresolved, narcotic beauty.
"""

book03_yaml = """# Tale of Genji — Chapter 3 (Utsusemi / The Shell of the Locust) — curated music arc
work: tale-of-genji
book: 3
title: "The Shell of the Locust: The Geometry of Evasion"
length_minutes: 42
principle: >
  Score the asymmetry between Genji's expectation of submission and Utsusemi's
  successful evasion. The chapter is about the gap between what power assumes
  and what agency can withhold. The register is tense, quiet, and unresolved.
force_arc: [desire, desire, metamorphosis, comedy, memory]
dominant_force: desire
tracks:
  - n: 1
    scene: "Genji returns to the house / the assumed conquest"
    force: desire
    composer: Szymanowski
    work: "Violin Concerto No. 1, Op. 35 (opening)"
    decision: added
    why: >
      Genji returns expecting a repetition of his victory. Szymanowski's
      ecstatic, shimmering violin lines give the sound of an anticipation
      that assumes its own fulfillment. The orchestration is dense with
      night-scents and aristocratic entitlement, vibrating with a chromatic
      heat that belongs entirely to Genji's internal state.
  - n: 2
    scene: "Genji observing the women playing Go / the visual trap"
    force: desire
    composer: Ravel
    work: "String Quartet in F major — II. Assez vif. Très rythmé"
    decision: added
    why: >
      Genji spies on Utsusemi and her stepdaughter Nokiba no Ogi playing Go.
      It is a scene of intense, covert looking. Ravel's pizzicato second
      movement gives the precise texture of this voyeurism: plucked, rhythmic,
      intensely focused, and slightly predatory. It is the sound of a trap
      being visually set.
  - n: 3
    scene: "Utsusemi slips away, leaving only her robe / the empty shell"
    force: metamorphosis
    composer: Strauss
    work: "Metamorphosen (closing section)"
    decision: added
    why: >
      When Genji finally breaches the room, Utsusemi has vanished, leaving
      only her perfumed robe—the 'shell of the locust.' She has transformed
      from an available object into an absolute absence. Strauss's shifting,
      grieving string textures capture the unreality of this moment: Genji
      is left holding the form of the woman without the woman herself.
  - n: 4
    scene: "Genji sleeps with Nokiba no Ogi instead / the substitution"
    force: comedy
    composer: Mozart
    work: "Le nozze di Figaro, K. 492 — Act IV Finale (selections)"
    decision: added
    why: >
      In the dark, Genji sleeps with the stepdaughter, Nokiba no Ogi, who
      assumes he is a normal suitor, while Genji pretends she is Utsusemi.
      Mozart's Act IV Figaro finale is the ultimate music of nocturnal
      substitution and aristocratic farce, capturing the hollow, almost
      mechanical comedy of the displaced consummation.
  - n: 5
    scene: "Genji returns with the robe / the fixation on the trace"
    force: memory
    composer: Rachmaninoff
    work: "Symphonic Dances, Op. 45 — I. Non allegro (coda)"
    decision: added
    why: >
      Genji keeps the robe and obsesses over it. The object becomes a fetish
      for the experience he was denied. Rachmaninoff's nostalgic, faded
      recapitulations provide the exact emotional weather of this fixation:
      a clinging to the trace of something that was never fully possessed in
      the first place.
"""

book04_yaml = """# Tale of Genji — Chapter 4 (Yugao / Evening Faces) — curated music arc
work: tale-of-genji
book: 4
title: "Evening Faces: The Violence of Jealousy"
length_minutes: 65
principle: >
  Score the progression from an idyllic, downward-class romance into pure,
  supernatural terror. Yugao is destroyed not by Genji, but by the psychic
  residue of his other affairs. The register shifts from intimate lyricism
  to the suffocating horror of the Rokujo Lady's living ghost.
force_arc: [desire, revelation, desire, plague, grief, memory]
dominant_force: plague
tracks:
  - n: 1
    scene: "The white flowers on the ruined wall / the discovery of Yugao"
    force: desire
    composer: Fauré
    work: "Pavane, Op. 50"
    decision: added
    why: >
      Genji finds Yugao living in a dilapidated, lower-class neighborhood,
      her identity concealed. Fauré's Pavane gives the exact mood of this
      discovery: fragile, slightly melancholic, and entirely separate from
      the heavy, political architecture of the imperial court. It is the
      sound of a desire that feels, temporarily, like innocence.
  - n: 2
    scene: "The sealed carriage / love without identity"
    force: revelation
    composer: Pärt
    work: "Spiegel im Spiegel"
    decision: added
    why: >
      Genji and Yugao conduct their affair without revealing their true names
      to each other. It is an intimacy built on a suspension of social reality.
      Pärt's Spiegel im Spiegel provides the stillness of this suspended
      state: a pure, floating verticality where time and rank seem
      temporarily abolished.
  - n: 3
    scene: "The excursion to the ruined mansion / the erotic isolation"
    force: desire
    composer: Wagner
    work: "Siegfried Idyll"
    decision: added
    why: >
      Genji takes Yugao to a desolate, overgrown estate to be entirely alone.
      The isolation is intensely romantic but structurally unsafe. Wagner's
      Siegfried Idyll gives the sound of this sequestered, overgrown love:
      tender, domestic, but vibrating with an intensity that the surrounding
      architecture cannot contain.
  - n: 4
    scene: "The apparition of the Rokujo Lady / the possession and death"
    force: plague
    composer: Penderecki
    work: "Threnody to the Victims of Hiroshima"
    decision: added
    why: >
      In the night, the living spirit of the Rokujo Lady—Genji's aristocratic,
      neglected lover—appears at the bedside and kills Yugao through sheer
      jealous force. Penderecki's shrieking string clusters are the only music
      adequate to this terror. It is not human anger; it is psychic violence
      rendered as physical trauma, an infection of the idyllic romance.
  - n: 5
    scene: "Genji's collapse and the removal of the body / the aftermath"
    force: grief
    composer: Shostakovich
    work: "String Quartet No. 8 in C minor — I. Largo"
    decision: added
    why: >
      Yugao is dead, and Genji is incapacitated by terror and grief. Her body
      must be smuggled out to avoid a scandal. Shostakovich's Largo gives the
      sound of this numb, paralyzed aftermath. The descending, suffocating
      motif is the exact texture of a world where the floor has simply dropped
      out.
  - n: 6
    scene: "Genji recovers but keeps the memory / the permanent scar"
    force: memory
    composer: Elgar
    work: "Cello Concerto in E minor, Op. 85 — III. Adagio"
    decision: added
    why: >
      Genji eventually recovers from his illness, but Yugao's death marks the
      end of his carelessness. The tragedy is locked into his psychology
      permanently. Elgar's Adagio provides the voice for this specific kind
      of survival: a beautiful, weeping line that carries the weight of an
      unfixable mistake.
"""

book02_md = """# The Broom Tree: The Taxonomy of Desire
## A music arc for *The Tale of Genji*, Chapter 2

Chapter 2 opens with the famous "rainy night ranking of women," where Genji and his friends categorize female virtue and availability as if solving a social equation. But the chapter's true arc is the collapse of this abstract taxonomy upon contact with reality. When Genji meets Utsusemi, the young wife of a provincial governor, the stylized comedy of the opening is entirely swept away by the overpowering, chromatic force of actual desire. 

Scoring this chapter means tracking this descent: from the bright, Mozartian proportions of male conversation into the heat-heavy, unresolved depths of a transgression that bypasses the rules it pretends to respect.

---

## Track Table

|  # | Scene / Function | Track | Decision |
| -: | --- | --- | --- |
|  1 | The rainy night conversation / classifying women | **Mozart — *Così fan tutte*, K. 588: Overture** | Added |
|  2 | To no Chujo's tale of the vanished woman / the reality of regret | **Fauré — *Élégie*, Op. 24** | Added |
|  3 | Genji travels to the Governor of Kii's house / escaping the palace | **Debussy — *Prélude à l'après-midi d'un faune*** | Added |
|  4 | Utsusemi's rigid morality / the barrier of her modesty | **Bach — *The Art of Fugue*, BWV 1080: Contrapunctus I** | Added |
|  5 | Genji enters Utsusemi's room / the consummation | **Scriabin — Symphony No. 4, 'The Poem of Ecstasy' (opening)** | Added |

---

## Per-Track Reasoning

**1. Mozart — *Così fan tutte*, K. 588: Overture**
The famous 'rainy night ranking of women' is a cynical, stylized male conversation about the categories of female availability and virtue. Mozart's overture gives the exact texture of this social geometry: brilliant, perfectly proportioned, and fundamentally unserious. It is the sound of desire treated as a solvable equation rather than a destructive force.

**2. Fauré — *Élégie*, Op. 24**
The conversation shifts from abstract taxonomy to To no Chujo's specific memory of a woman who disappeared from neglect. The cello line in Fauré's Élégie drops the temperature of the room—it is the sound of past carelessness returning as permanent regret. The comedy evaporates, replaced by the specific weight of a lost object.

**3. Debussy — *Prélude à l'après-midi d'un faune***
Genji's excursion to the middle-class house of the Governor of Kii introduces a new kind of atmosphere: less formal, more sensual, outside the suffocating protocols of the imperial court. Debussy's Prélude gives the exact climate of this displacement—a fluid, heat-heavy chromaticism where boundaries begin to dissolve and unexpected desires can surface.

**4. Bach — *The Art of Fugue*, BWV 1080: Contrapunctus I**
Utsusemi is not a court lady; she is a provincial governor's wife who understands her precarious social position. Her resistance to Genji is not coquetry; it is a desperate defense of the only architecture that protects her: the rules of propriety. Bach's strict counterpoint is the sound of that defensive architecture—beautiful, unyielding, and entirely built on rule.

**5. Scriabin — Symphony No. 4, 'The Poem of Ecstasy' (opening)**
Genji's intrusion and the subsequent consummation bypass Utsusemi's defenses completely. Scriabin's chromatic longing gives the texture of this overriding force. It is not aggressive or martial; it is overwhelming, sweeping away the strict counterpoint of her resistance in a wash of harmonically unresolved, narcotic beauty.
"""

book03_md = """# The Shell of the Locust: The Geometry of Evasion
## A music arc for *The Tale of Genji*, Chapter 3

Chapter 3 is a study in asymmetry: the gap between what power assumes and what agency can withhold. Genji returns to the Governor of Kii's house expecting a repetition of his triumph over Utsusemi. Instead, she slips away in the dark, leaving only her perfumed robe behind. Genji is forced to sleep with her stepdaughter in a hollow substitution, and then to fetishize the empty garment.

The register here is tense, quiet, and unresolved. The music tracks Genji's unfulfilled anticipation, the covert visual trap of his voyeurism, the structural defeat of Utsusemi's evasion, and the melancholy of possessing the trace rather than the object.

---

## Track Table

|  # | Scene / Function | Track | Decision |
| -: | --- | --- | --- |
|  1 | Genji returns to the house / the assumed conquest | **Szymanowski — Violin Concerto No. 1, Op. 35 (opening)** | Added |
|  2 | Genji observing the women playing Go / the visual trap | **Ravel — String Quartet in F major: II. Assez vif. Très rythmé** | Added |
|  3 | Utsusemi slips away, leaving only her robe / the empty shell | **Strauss — *Metamorphosen* (closing section)** | Added |
|  4 | Genji sleeps with Nokiba no Ogi instead / the substitution | **Mozart — *Le nozze di Figaro*, K. 492: Act IV Finale (selections)** | Added |
|  5 | Genji returns with the robe / the fixation on the trace | **Rachmaninoff — *Symphonic Dances*, Op. 45: I. Non allegro (coda)** | Added |

---

## Per-Track Reasoning

**1. Szymanowski — Violin Concerto No. 1, Op. 35 (opening)**
Genji returns expecting a repetition of his victory. Szymanowski's ecstatic, shimmering violin lines give the sound of an anticipation that assumes its own fulfillment. The orchestration is dense with night-scents and aristocratic entitlement, vibrating with a chromatic heat that belongs entirely to Genji's internal state.

**2. Ravel — String Quartet in F major: II. Assez vif. Très rythmé**
Genji spies on Utsusemi and her stepdaughter Nokiba no Ogi playing Go. It is a scene of intense, covert looking. Ravel's pizzicato second movement gives the precise texture of this voyeurism: plucked, rhythmic, intensely focused, and slightly predatory. It is the sound of a trap being visually set.

**3. Strauss — *Metamorphosen* (closing section)**
When Genji finally breaches the room, Utsusemi has vanished, leaving only her perfumed robe—the 'shell of the locust.' She has transformed from an available object into an absolute absence. Strauss's shifting, grieving string textures capture the unreality of this moment: Genji is left holding the form of the woman without the woman herself.

**4. Mozart — *Le nozze di Figaro*, K. 492: Act IV Finale (selections)**
In the dark, Genji sleeps with the stepdaughter, Nokiba no Ogi, who assumes he is a normal suitor, while Genji pretends she is Utsusemi. Mozart's Act IV Figaro finale is the ultimate music of nocturnal substitution and aristocratic farce, capturing the hollow, almost mechanical comedy of the displaced consummation.

**5. Rachmaninoff — *Symphonic Dances*, Op. 45: I. Non allegro (coda)**
Genji keeps the robe and obsesses over it. The object becomes a fetish for the experience he was denied. Rachmaninoff's nostalgic, faded recapitulations provide the exact emotional weather of this fixation: a clinging to the trace of something that was never fully possessed in the first place.
"""

book04_md = """# Evening Faces: The Violence of Jealousy
## A music arc for *The Tale of Genji*, Chapter 4

Chapter 4 traces a horrifying trajectory: what begins as an idyllic, almost pastoral romance in a lower-class neighborhood ends in supernatural terror. Yugao, the "evening face," offers Genji an intimacy free of the imperial court's heavy architecture. But they cannot escape the consequences of Genji's other life.

Yugao is destroyed by the living spirit of the Rokujo Lady, whose neglected aristocratic jealousy manifests as a lethal physical force. Scoring this chapter requires a violent rupture—from delicate lyricism into pure, shrieking trauma, and finally into paralyzed grief.

---

## Track Table

|  # | Scene / Function | Track | Decision |
| -: | --- | --- | --- |
|  1 | The white flowers on the ruined wall / the discovery of Yugao | **Fauré — *Pavane*, Op. 50** | Added |
|  2 | The sealed carriage / love without identity | **Pärt — *Spiegel im Spiegel*** | Added |
|  3 | The excursion to the ruined mansion / the erotic isolation | **Wagner — *Siegfried Idyll*** | Added |
|  4 | The apparition of the Rokujo Lady / the possession and death | **Penderecki — *Threnody to the Victims of Hiroshima*** | Added |
|  5 | Genji's collapse and the removal of the body / the aftermath | **Shostakovich — String Quartet No. 8 in C minor: I. Largo** | Added |
|  6 | Genji recovers but keeps the memory / the permanent scar | **Elgar — Cello Concerto in E minor, Op. 85: III. Adagio** | Added |

---

## Per-Track Reasoning

**1. Fauré — *Pavane*, Op. 50**
Genji finds Yugao living in a dilapidated, lower-class neighborhood, her identity concealed. Fauré's Pavane gives the exact mood of this discovery: fragile, slightly melancholic, and entirely separate from the heavy, political architecture of the imperial court. It is the sound of a desire that feels, temporarily, like innocence.

**2. Pärt — *Spiegel im Spiegel***
Genji and Yugao conduct their affair without revealing their true names to each other. It is an intimacy built on a suspension of social reality. Pärt's Spiegel im Spiegel provides the stillness of this suspended state: a pure, floating verticality where time and rank seem temporarily abolished.

**3. Wagner — *Siegfried Idyll***
Genji takes Yugao to a desolate, overgrown estate to be entirely alone. The isolation is intensely romantic but structurally unsafe. Wagner's Siegfried Idyll gives the sound of this sequestered, overgrown love: tender, domestic, but vibrating with an intensity that the surrounding architecture cannot contain.

**4. Penderecki — *Threnody to the Victims of Hiroshima***
In the night, the living spirit of the Rokujo Lady—Genji's aristocratic, neglected lover—appears at the bedside and kills Yugao through sheer jealous force. Penderecki's shrieking string clusters are the only music adequate to this terror. It is not human anger; it is psychic violence rendered as physical trauma, an infection of the idyllic romance.

**5. Shostakovich — String Quartet No. 8 in C minor: I. Largo**
Yugao is dead, and Genji is incapacitated by terror and grief. Her body must be smuggled out to avoid a scandal. Shostakovich's Largo gives the sound of this numb, paralyzed aftermath. The descending, suffocating motif is the exact texture of a world where the floor has simply dropped out.

**6. Elgar — Cello Concerto in E minor, Op. 85: III. Adagio**
Genji eventually recovers from his illness, but Yugao's death marks the end of his carelessness. The tragedy is locked into his psychology permanently. Elgar's Adagio provides the voice for this specific kind of survival: a beautiful, weeping line that carries the weight of an unfixable mistake.
"""

files = {
    "studium/music/tale-of-genji/book-02.yaml": book02_yaml,
    "studium/music/tale-of-genji/book-03.yaml": book03_yaml,
    "studium/music/tale-of-genji/book-04.yaml": book04_yaml,
    "studium/essays/tale-of-genji/book-02.md": book02_md,
    "studium/essays/tale-of-genji/book-03.md": book03_md,
    "studium/essays/tale-of-genji/book-04.md": book04_md,
}

for filepath, content in files.items():
    full_path = os.path.join("/Users/4jp/.gemini/antigravity-cli/scratch/limen", filepath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w') as f:
        f.write(content)
    print(f"Written: {filepath}")

