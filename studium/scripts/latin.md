# Latin — the script for Virgil (Aeneid), Caesar, Cicero, Lucretius

> Script first, grammar second, translation third. The key is not fluency — it is **physical contact
> with the text**. Handwriting slows you down enough to notice structure. Three layers below; go as
> deep as the day allows (set `language_depth` in `logs/studium-state.json`).

---

## Layer 1 — Calligraphy / paleography (the hand)

Latin uses the Roman alphabet — 23 letters in classical inscriptions (no J, U, W); 26 in modern
editions. The crucial paleographic skill is **scribal abbreviations and ligatures** from medieval
manuscripts, since most Latin texts survived through the copyist tradition.

**The classical Roman alphabet (upper · lower · name · sound):**

| A a /aː/ or /a/ | B b /b/ | C c /k/ (always hard) | D d /d/ | E e /eː/ or /e/ |
| F f /f/ | G g /g/ (hard) | H h /h/ (weakly aspirated) | I i /iː/ or /i/ or /j/ | K k /k/ (rare) |
| L l /l/ | M m /m/ | N n /n/ | O o /oː/ or /o/ | P p /p/ |
| Q q /kʷ/ (always QV) | R r /r/ (trilled) | S s /s/ (never /z/) | T t /t/ | V v /uː/ or /u/ or /w/ |
| X x /ks/ | Y y /yː/ (Greek loans only) | Z z /dz/ (Greek loans only) | | |

> **Note:** Classical Latin had no distinction between I/J or U/V — both pairs were single letters
> with vocalic and consonantal values. Modern editions often distinguish them for readability.

**Vowel quantity (the pulse of Latin verse):**
Latin poetry turns on **long** (¯) vs **short** (˘) vowels — quantity, not stress. In modern texts,
macrons mark longs: ā ē ī ō ū. In manuscripts and inscriptions you must infer from metre or context.
Copy macrons faithfully: `arma` (arms) ≠ `ārmā` — endings change meaning entirely.

**Hand notes (ductus — Roman cursive → medieval Caroline minuscule):**
The manuscripts you will encounter most are **Caroline minuscule** (9th–12th c.) and **Gothic textura**
(13th–15th c.). Key letter shapes to master:

- **a** in Caroline = open two-stroke form (not the modern single-loop α); in Gothic = closed bowl.
- **d** can be straight-backed (d) or uncial (δ-like), depending on period.
- **r** in Gothic contexts has a "2-shaped" rotunda-r (ꝛ) when it follows o or certain round letters.
- **long s** (ſ) is used word-medially in medieval and early-modern copies; only the round **s** appears word-finally.
- **ti** before a vowel reads /tsi/ in medieval Latin (so *gratia* = GRAT-si-a), not classical /ti/.

**Key scribal abbreviations (encountered in every manuscript):**
| Abbreviation | Expansion | Example |
|---|---|---|
| q́ (q + macron or curl) | -que (and) | arm**aque** |
| ꝓ / p̄ | per- / pro- | **per**fectus |
| ē / ñ (vowel + macron) | -em / -um / -n | virū = virum |
| **&** (ampersand) | et (and) | et → & |
| ꝭ | est (is) | |
| .i. | id est (that is) | |
| **nr̄a** | nostra (our) | |

**Inscriptional caps (stone-cutting tradition):**
Classical inscriptions use all caps, no spaces between words, and interpuncts (·) for word division.
The Trajan Column (113 CE) is the canonical model for Roman serif letterforms — the source of all
modern Roman typefaces. Copy a line of it: `IMP·CAESARI·DIVI·NERVAE·F·NERVAE` to feel the rhythm.

---

## Layer 2 — Glossed reading (decode the line)

The opening of the Aeneid — copy it by hand, then work the gloss.
(This is the gold-standard daily unit; it encodes all the essential Latin moves in seven lines.)

```
Arma  virumque  canō,   Troiae  quī   prīmus  ab  ōrīs
arma  virum-que  cano   Troiae  qui   primus  ab  oris
```

| word | gloss |
|---|---|
| **Arma** | **arms/weapons** — accusative pl. neut. (object of *canō*; first word, setting the epic's subject) |
| **virum** | **man** — accusative sing. masc. (*vir, virī*; the hero Aeneas; object of *canō*) |
| **-que** | **and** — enclitic (attached to the word it follows; "arms and the man") |
| **canō** | **I sing** — present indicative 1st-sg. active (*canere*; the poet's assertion, not a command) |
| **Troiae** | **of Troy** — genitive sing. (possession; "from the shores OF Troy") |
| **quī** | **who** — relative pronoun nom. sing. masc. (introduces the relative clause; subject = Aeneas) |
| **prīmus** | **first** — adjective nom. sing. masc. (predicate; "who, first, came from…") |
| **ab** | **from** — preposition + ablative |
| **ōrīs** | **shores/coasts** — ablative pl. (*ōra, ōrae*; governed by *ab*) |

- **Literal:** "Arms and the man I sing, who first from the shores of Troy —"
- **Literary:** "I sing of arms and the man — the man who came first from Troy's shores"

**Continue the opening (lines 1–7, the proem):**
```
Italiam  fātō   profugus   Lāviniaque   venit
lītora;  multum  ille  et  terrīs  iactātus  et  altō
vī  superum,  saevae  memorem  Iūnōnis  ob  īram,
multa  quoque  et  bellō  passus,  dum  conderet  urbem
inferretque  deōs  Latiō — genus  unde  Latīnum
Albānīque  patrēs  atque  altae  moenia  Rōmae.
```

**Method:** the corpus holds Virgil's Latin + four translations (Dryden · Fitzgerald · Fagles · Mandelbaum).
Read the Latin aloud (quantity-metre beats, not stress-accent), copy it, gloss each word, then COMPARE
how each translator handles *arma virumque* — Dryden's "Arms, and the Man" is a literary transplant;
Fitzgerald's "I sing of warfare and a man at war" is an interpretation; Fagles "I sing of arms and
the man" stays closer. The divergence is the lesson.

**Virgilian formulae and patterns to recognise on sight:**
- `pius Aeneas` — "pious Aeneas" (his defining epithet, recurs ~20× in the Aeneid)
- `fātō profugus` — "exiled by fate" (the epic's engine: fate drives, humans resist)
- `sunt lacrimae rērum` — "there are tears in things" (Aen. 1.462, the most quoted line)
- `flectere si nequeō superos, Acheronta movēbō` — "if I cannot move the gods above, I will move Acheron" (Juno's motto)
- `dīs aliter vīsum` — "it seemed otherwise to the gods" (3.2; a formula of resigned acceptance)
- `arma virumque` — the opening words; every educated Roman recognised them on the first syllable

---

## Layer 3 — Serious grammar (toward unaided translation)

Minimal orientation; expand as you go (recommended companions: Wheelock's *Latin*; Allen & Greenough
*New Latin Grammar* for reference; Bradley's Arnold for prose composition).

### The five declensions (nouns)

Latin nouns decline in **6 cases** × **3 genders** (masc./fem./neut.) × sing./pl. The ending IS the
grammar — word order is free because the ending shows the role. Master the patterns in this order:

| Case | Role | Signal question |
|---|---|---|
| Nominative | subject | Who/what does the verb? |
| Genitive | possession/of | Of whom? Whose? |
| Dative | indirect object | To/for whom? |
| Accusative | direct object; most prepositions | Whom/what? |
| Ablative | from/with/by/in; many prepositions | By/with/from/in? |
| Vocative | address | O — ! |

**1st declension** (ā-stem, mostly fem.): *terra, terrae* (earth)
`terra · terrae · terrae · terram · terrā` (sing.) / `terrae · terrārum · terrīs · terrās · terrīs` (pl.)

**2nd declension** (o-stem, masc./neut.): *vir, virī* (man) / *bellum, bellī* (war)
Masc: `vir · virī · virō · virum · virō` / Neut: `bellum · bellī · bellō · bellum · bellō`

**3rd declension** (consonant- and i-stems, all genders): most varied; learn by recognition.
*rēx, rēgis* (king): `rēx · rēgis · rēgī · rēgem · rēge` (sing.) / `rēgēs · rēgum · rēgibus · rēgēs · rēgibus` (pl.)

### Verb conjugation (four conjugations)

Latin verbs encode: **person** (1/2/3) × **number** (sg/pl) × **tense** × **mood** × **voice** in a
single ending. The principal parts (4 forms) give you the entire verb:

| Part | Form | Tells you |
|---|---|---|
| 1st | *canō* | present stem |
| 2nd | *canere* | infinitive (2nd conj. = *-ēre*; 1st = *-āre*; 3rd = *-ere*; 4th = *-īre*) |
| 3rd | *cecinī* | perfect stem (add *-ī, -istī, -it, -imus, -istis, -ērunt* for perfect active) |
| 4th | *cantum* | supine/past participle stem |

**Present active indicative** of *amō* (1st conj., "I love"):
`amō · amās · amat · amāmus · amātis · amant`

**Perfect active indicative** (the most important past tense for prose):
`amāvī · amāvistī · amāvit · amāvimus · amāvistis · amāvērunt`

### Word order and register

Classical Latin **defaults to SOV** (Subject-Object-Verb) but exploits freedom for emphasis. The
**first and last positions** of a clause are strong — Romans front-loaded what they wanted emphasised.
*Arma virumque canō* puts the objects (arms, the man) first, the verb last: the subject-matter
arrives before the singer claims it.

**Key constructions every reader hits immediately:**

- **Ablative absolute:** `Troiā captā, Aenēās fūgit` — "Troy having been captured, Aeneas fled."
  (Participial phrase in the ablative, grammatically independent of the main clause; ubiquitous in Livy/Caesar.)
- **Indirect statement (AcI):** `Dīcit Aenēān bonum esse` — "He says that Aeneas is good."
  (Verb of speaking/thinking → accusative subject + infinitive. Latin's core reportage structure.)
- **Subjunctive mood:** used in subordinate clauses of purpose (*ut* + subj.), result, indirect question,
  cum-clauses — the most foreign feature for English readers. Its presence signals dependence/unreality/intention.
- **Gerundive (passive periphrastic):** `Carthāgō dēlenda est` — "Carthage must be destroyed."
  (Cato's formula; gerundive + *est/sunt* = obligation.)

### Quantity and metre (verse only)

Virgil writes in **dactylic hexameter**: ¯˘˘ | ¯˘˘ | ¯˘˘ | ¯˘˘ | ¯˘˘ | ¯× (6 feet; dactyl = 1 long + 2
short; spondee = 2 long substitutes). Scan line 1:
```
ĀR-mă vĭ- | RŪM-quĕ că- | NŌ | TROI-ae | QUĪ | PRĪM-ŭs ăb | ŌR-īs
```
Read aloud with quantity, not stress — the beat emerges from vowel duration, not word accent. This is
**deeply different from English poetry** and requires training the ear fresh.

### Daily grammar drill

Take the day's lines. Parse ONE word fully: name its declension/conjugation, give case/tense/person/
number/mood/voice, and state what grammatical role it plays in the sentence. Write the rule it
illustrates in your ledger. Parse one word perfectly, daily — six months of that builds reading fluency.

---

*Source rails:*
**Perseus / Scaife** (perseus.tufts.edu) — Latin text + morphological parser, hover any word for full parse ·
**The Latin Library** (thelatinlibrary.com) — plain text of all major authors, no login ·
**Loeb Classical Library** (loebclassics.com) — facing-page Latin/English (subscription; Harvard) ·
**Dickinson College Commentaries** (dcc.dickinson.edu) — annotated texts for readers, Caesar/Vergil/Ovid ·
Local corpus: `classical/aeneid/latin_original.txt` + translations to compare ·
**Wheelock's Latin** (7th ed.) for systematic grammar drill · **Lewis & Short** or **OLD** for dictionary work.
