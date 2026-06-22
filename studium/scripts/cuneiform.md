# Cuneiform — the script for Gilgamesh (Epic of Gilgamesh, Standard Babylonian)

> Script first, grammar second, translation third. The key is not fluency — it is **physical contact
> with the text**. Handwriting slows you down enough to notice structure. Three layers below; go as
> deep as the day allows (set `language_depth` in `logs/studium-state.json`).

---

## Layer 1 — Calligraphy / paleography (the hand)

Cuneiform ("wedge-shaped") is not an alphabet — it is a mixed logographic-syllabic system impressed
into clay with a cut reed stylus. Standard Babylonian (the literary dialect of the Gilgamesh epic,
c. 1300–700 BCE) uses roughly **600 signs** in active literary use, but a working reading vocabulary
of **~150 core signs** unlocks most continuous prose. Reading direction is **left to right**, written
in horizontal lines; the signs run left-to-right across the tablet.

### The stylus stroke

A single cuneiform mark is made by pressing the triangular tip of a reed into a damp clay surface at
an angle, creating a **wedge**: a broad head (the impressed corner) tapering to a thin tail. There are
three canonical orientations:

| stroke | name | looks like |
| --- | --- | --- |
| `▷` | horizontal wedge (*winkelhaken* = angle-hook) | flat arrow pointing right |
| `▽` / `↓` | vertical wedge | wedge pointing down |
| `◁` / diagonal | diagonal wedge | wedge angled ~45° |

Complex signs are composed of combinations of these three elements. Always draw wedges head-first,
pressing in, then lifting — never drag. The head is fat; the tail vanishes.

### Core sign repertoire (copy each 5×)

Cuneiform signs function in three modes simultaneously: as **logograms** (whole Sumerian words),
as **syllabograms** (phonetic syllables in Akkadian), and as **determinatives** (unpronounced
classifiers that tell you the semantic category of the next word). Below are essential signs with
their commonest readings:

**High-frequency syllabograms (Akkadian phonetic spine):**

| sign | syllabic value(s) | mnemonic shape note |
| --- | --- | --- |
| 𒀭 (AN/DINGIR) | *an* · det. for deities | star with rays — the divine determinative; written before every god's name |
| 𒂗 (EN) | *en* | stacked horizontals |
| 𒄿 (I) | *i* | simple cluster |
| 𒇷 (LI) | *li* | compound wedges |
| 𒄑 (GIŠ) | det. for wooden objects | tree-like; written before wood/tree nouns |
| 𒀭𒂗𒍪 (AN-EN-ZU) | reads: *d*Sîn (Moon god) | the three signs together = proper name |
| 𒀭𒂗𒍪𒆷 | — | name + genitive marker |
| 𒅆 (IGI) | *igi* · "eye" logogram | eye + horizontal lines |
| 𒆳 (KUR) | *kur* · "mountain/land" | peaked wedge cluster |
| 𒂍 (É) | *é* · "house" | building-plan outline |
| 𒂠 (EME) | *eme* · "tongue/language" | |
| 𒈗 (LUGAL) | *lugal* · "king" | "big man" composite |
| 𒁀 (BA) | *ba* | |
| 𒈠 (MA) | *ma* | |
| 𒋾 (TI) | *ti* | |
| 𒅗 (KA) | *ka* · "mouth" | mouth with teeth |
| 𒌝 (UM) | *um* | |
| 𒃻 (GARА) | *gar* | |

**Key determinatives (unpronounced — copy but do not voice):**

| sign | category it marks |
| --- | --- |
| 𒀭 *d* (dingir) | deities and divine names |
| 𒄑 *giš* | wooden objects, trees |
| 𒆳 *kur* | mountains, foreign lands (also pronounced when not det.) |
| 𒌑 *ú* | plants, herbs, drugs |
| 𒀯 *mul* | stars, constellations |
| 𒄘 *lú* | male persons and professions |

**Ductus notes:** Start with AN (𒀭, the star): press four diagonal wedges outward from a centre
point (like a compass rose), then add the central horizontal. It is the most important single sign
in the Gilgamesh tablets — it begins the name of every deity. Practice it until it appears naturally.
Next drill LUGAL: the sign for "king" appears in the tablet's opening self-description of Gilgamesh
(*šar kiššati* "king of the world"). Then KUR (mountain): it recurs whenever the text mentions the
Cedar Forest, the underworld, or foreign lands.

**Sign lists to use:** Borger's *Mesopotamisches Zeichenlexikon* (MZL) is the scholarly standard;
for beginners, Worthington's online *aBZL* sign list (with stroke-order diagrams) is freely accessible.
Huehnergard's *Grammar of Akkadian* includes a sign list with frequency data.

---

## Layer 2 — Glossed reading (decode the line)

### Tablet I, opening lines — the self-praise of Gilgamesh

The Standard Babylonian version of Tablet I opens with a third-person hymn to Gilgamesh before the
narrative begins. The first line (or close variant) found on multiple tablet copies reads:

```
𒅆 𒅗𒆠𒁕𒁀𒈾   𒁹𒀭𒄑𒉈𒆳𒈗𒈠𒀭   𒀭𒄑𒉈𒆳𒈗𒈠𒀭
ša  nagba  īmuru    šadâ  mālik
```

The canonical opening (transliterated, Tablet I col. i lines 1–3, Nineveh recension):

```
Line 1:   šа   nag-ba   ī-mu-ru   iš-da-a-at   ma-ti
Line 2:   šа   kal-la-ma   i-du-ú   uš-ta-maš-ši-ru   u₃   ma-at-ma
Line 3:   ù   šá-niš-šu   a-li-ik   ur-ḫi   ša   a-na   ki-bra-a-ti
```

Use line 1 as your daily copy-and-gloss unit:

**Transliteration:** `ša nagba īmuru išdâat māti`

| word | transliteration | sign cluster | gloss |
| --- | --- | --- | --- |
| ša | *ša* | 𒁕 | **who / he who** — relative pronoun |
| nagba | *nag-ba* | 𒈾𒂵 | **totality, the deep** — *nagbu* = all things, the flood-waters beneath; accusative |
| īmuru | *ī-mu-ru* | 𒄿𒈬𒊒 | **saw** — Gtn perfect of *amāru* "to see"; 3sg masc. "he saw" |
| išdâat | *iš-da-a-at* | 𒅆𒁕𒀀𒀜 | **foundations of** — *išdātu* f.pl. construct state "foundations of the land" |
| māti | *ma-a-ti* | 𒈠𒀀𒋾 | **land** — *mātu* "land, country"; genitive after construct |

- **Literal:** "He who the totality saw, the foundations of the land —"
- **Literary:** "He who saw the Deep, the foundations of the earth —"

*The opening is a relative clause that will not resolve its subject ("Gilgamesh") until line 29 of
Tablet I. The entire opening hymn is a suspended crescendo. The verb comes third — object then verb
is common in Akkadian, though word order is freer than the paradigm.*

**Formulae to recognise on sight:**

- `šar kiššati` — "king of the world" (Gilgamesh's title; appears in the self-praise prologue)
- `ina ūmīšuma` — "in his days / in those days"
- `ana šadî ēlī` — "I climbed to the mountain" (motif repeated for Cedar Forest ascent and return)
- `ittanammar` — "he kept seeing / saw repeatedly" (Gtn stem = habitual or iterative; marks visions)
- `Ḫumbaba pâšu īpušma` — "Humbaba opened his mouth and spoke" (narrative speech-introduction formula)
- `kīma abīšu rābiṣ` — "crouching like a lion" (simile formula, repeated of warriors and monsters)

**Method:** The local corpus holds the Akkadian text (George's composite tablet + transliteration)
alongside Foster's, Sandars's, and Ferry's English translations. Copy the Akkadian line by hand
(write the Latin transliteration if cuneiform typesetting is unavailable — both count), gloss each
word, then compare how Foster vs. Sandars renders *nagba* ("the Deep" vs. "all things"). That
divergence is where the text is alive.

---

## Layer 3 — Serious grammar (toward unaided translation)

Minimal orientation; expand with Huehnergard, *A Grammar of Akkadian* (3rd ed.) — the standard
pedagogical reference.

### Script note: syllabic vs. logographic reading

Before parsing grammar, note that any given cuneiform sign may be read (a) as a Sumerian logogram
(writing a whole word in the "prestige" written language), (b) as an Akkadian syllabogram (phonetic
building-block), or (c) as a silent determinative. Knowing which reading applies depends on context
and on the scholar's sign-list. Most Standard Babylonian literary text is syllabically spelled
Akkadian, so concentrate on the syllabogram values first.

### Nouns: two genders, three cases

Akkadian nouns decline for **gender** (masculine / feminine), **number** (singular / dual / plural),
and **case** (nominative / accusative / genitive), marked by short vowel endings:

| case | singular | plural (masc.) |
| --- | --- | --- |
| nominative | -u | -ū |
| accusative | -a | -ī |
| genitive | -i | -ī |

In practice the case vowels are **often unpronounced or elided** in verse (called *mimation* loss),
so endings appear as -∅, especially in poetry. Parse by syntax and context, not endings alone.

**Construct state** (genitive-chaining): when a noun directly precedes a genitive, it drops its
final -u/-a/-i and takes a shortened "construct" form. `išdâat māti` = "foundations-of (the) land."
This is the backbone of Akkadian noun phrases — learn to spot the chained construct immediately.

### Verbs: the stem system

Akkadian verbs are built on **trilateral roots** (three consonants) + a vowel class (a/i/u in the
present/preterite slot). The core paradigm:

| stem | name | meaning | example (*amāru* "to see") |
| --- | --- | --- | --- |
| G | basic | simple action | *imur* "he saw" |
| Gt | reflexive/reciprocal | "to see each other" | *ittamar* |
| Gtn | iterative/habitual | "to keep seeing" | *ittanammar* |
| D | intensive/factitive | "to make see; to reveal" | *ummar* |
| Š | causative | "to cause to see" | *ušāmir* |
| N | passive/medio-passive | "to be seen" | *innāmur* |

**Tense/aspect** in the Standard Babylonian literary dialect:
- *Preterite* (G: CvCC or CCvC shape): single completed action — *imur* "he saw"
- *Present-future* (G: iCCaC): ongoing or future — *inammar* "he sees / will see"
- *Perfect* (Gt-like but with -ta- infix): recent or experiential past — *ītamar* "he has (just) seen"
- *Stative*: describes a state — *damiq* "he is good / he is beautiful"

### Word order

The default is **Subject – Object – Verb** (SOV), but Akkadian poetry routinely inverts for emphasis
(as in the opening: object *nagba* precedes verb *īmuru*). Subordinate clauses introduced by *ša*
(relative) or *šumma* (conditional) generally keep their verb final. Prepositions *ana* (to, for),
*ina* (in, from, by), *ištu* (from, since), *eli* (over, upon) are the core locatives — learn them
as a block.

### The cuneiform writing challenge

Unlike an alphabet, you cannot read cuneiform by sounding out letters left to right. You must:
1. **Identify the sign** — is it a determinative (silent), a logogram (whole Sumerian word), or a syllabogram?
2. **Assemble the syllables** — *na-ag-ba* → /nagba/.
3. **Identify the word** — look it up in the glossary (CAD or the back of George's edition).
4. **Parse the grammar** — case ending? verbal stem? construct state?

This is slow at first. It will become pattern recognition. The reward is reading the oldest surviving
literary narrative in human hands.

### Daily grammar drill

Take the day's line. Choose ONE word. Write down:
1. The transliteration of its sign cluster.
2. Its dictionary form (citation form: masc. sg. nom. for nouns; Gtn infinitive for verbs).
3. Its grammatical parsing (case/number/gender, or person/gender/number/tense/stem).
4. The rule it illustrates (construct state, Gtn iterative, relative clause *ša*, etc.).

Record in your ledger. After thirty days you will have internalized the core grammar through the
text itself — which is the only grammar worth having.

---

*Source rails:*
- **CDLI** (cuneiform.ucla.edu) — Cuneiform Digital Library Initiative: images of actual tablets,
  transliterations, and catalogue for the entire Gilgamesh tradition.
- **George, A.R., *The Babylonian Gilgamesh Epic* (OUP, 2003)** — the definitive critical edition
  (composite text + transliteration + commentary); the two-volume set is the scholar's desk copy.
- **Huehnergard, *A Grammar of Akkadian*, 3rd ed. (Eisenbrauns)** — the standard pedagogical
  grammar; use alongside the text.
- **CAD** (Chicago Assyrian Dictionary, online free at OI) — the definitive lexicon; look up every
  word you gloss.
- **ePSD2** (epsd2.mpiwg-berlin.mpg.de) — electronic Pennsylvania Sumerian Dictionary, for the
  Sumerian logograms embedded in the Akkadian text.
- **Worthington's aBZL sign list** (free PDF) — stroke-order diagrams for cuneiform sign practice.
- Local corpus: `classical/gilgamesh/` (George composite + Foster, Sandars, Ferry translations).
