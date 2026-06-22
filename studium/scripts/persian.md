# Persian — the script for Rumi (Masnavi, Divan-e Shams)

> Script first, grammar second, translation third. The key is not fluency — it is **physical contact
> with the text**. Handwriting slows you down enough to notice structure. Three layers below; go as
> deep as the day allows (set `language_depth` in `logs/studium-state.json`).

---

## Layer 1 — Calligraphy / paleography (the hand)

Persian uses the **Perso-Arabic script** in the **nastaʿlīq** (نستعلیق) style — the premier calligraphic
hand of classical Persian poetry. It runs **right to left**; most letters join to the letter following
them (to their right); letters take up to four contextual forms (isolated · initial · medial · final).

### The 32-letter alphabet (Persian adds 4 letters to Arabic's 28)

Each entry: **isolated form · name · approximate sound · ductus note**

| Letter | Name | Sound | Ductus note |
| --- | --- | --- | --- |
| ا | alef | /ɑ/ or silent vowel seat | A vertical stroke, right-leaning in nastaʿlīq; does not join on the left |
| ب | be | /b/ | Shallow dish, single dot below; joins both sides |
| پ | pe | /p/ | Same dish as ب, three dots below — uniquely Persian |
| ت | te | /t/ | Same dish, two dots above |
| ث | se | /s/ | Same dish, three dots above |
| ج | jim | /dʒ/ | Deep bowl with tail; joins left; medial form ﺠ compresses the bowl |
| چ | che | /tʃ/ | Same bowl as ج, three dots below — uniquely Persian |
| ح | he (ḥā) | /h/ | Similar bowl to ج but no dot — distinguish carefully |
| خ | khe | /x/ (as in Bach) | Same as ح with one dot above |
| د | dal | /d/ | A small rightward wedge; **does not join on the left** |
| ذ | zal | /z/ | Same wedge, one dot above; does not join left |
| ر | re | /r/ | A swooping tail, rightward; **does not join on the left** |
| ز | ze | /z/ | Same tail as ر, one dot above |
| ژ | zhe | /ʒ/ (measure) | Same tail, three dots above — uniquely Persian |
| س | sin | /s/ | Three humps (like a camel spine); joins both sides |
| ش | shin | /ʃ/ | Same three humps, three dots above |
| ص | sad | /sˤ/ (emphatic) | Large loop + ascending tail; joins both sides |
| ض | zad | /zˤ/ (emphatic) | Same as ص with one dot above |
| ط | ta (ṭā) | /tˤ/ (emphatic) | A closed oval with a vertical spine rising from it |
| ظ | za (ẓā) | /zˤ/ (emphatic) | Same as ط, one dot above |
| ع | ʿayn | /ʕ/ (pharyngeal) | One of the hardest to write: three distinct contextual shapes; study each |
| غ | gheyn | /ɣ/ (gargle) | Same as ع with one dot above |
| ف | fe | /f/ | A loop on a baseline with one dot above; joins both sides |
| ق | qaf | /q/ (deep k) | Similar loop, two dots above; joins both sides |
| ک | kaf | /k/ | A long flat stroke with a small diagonal tooth; joins both sides |
| گ | gaf | /g/ | Same as ک with an extra stroke — uniquely Persian |
| ل | lam | /l/ | An ascending stroke leaning right, joins left with a dramatic ligature ﻻ when meeting alef |
| م | mim | /m/ | A small closed circle with a descending tail |
| ن | nun | /n/ | Like ب but with one dot above and a deeper bowl |
| و | vav | /v/ or /u/ or /o/ | A round head with a descending tail; **does not join on the left** |
| ه | he | /h/ | Four contextual forms; in nastaʿlīq the medial form looks like a small figure-8 |
| ی | ye | /j/ or /i/ or /e/ | A long sweeping tail to the left; joins both sides; final form has no dots |

**The four uniquely Persian letters:** پ (pe) · چ (che) · ژ (zhe) · گ (gaf). If you see these in a text,
it is Persian (or Urdu), not Arabic.

### Nastaʿlīq ductus — what makes it different from naskh

Nastaʿlīq (the hand of Rumi's manuscripts) is characterised by:
- **Diagonal flow:** words descend from right to left at roughly 45°, then the final letter swoops up.
- **Calligraphic ligatures:** ل+ا = لا (lam-alef), a mandatory compound. م+ح+م+د = محمد flows without lifting the pen.
- **Thick-thin stroke variation:** the qalam (reed pen) is cut at an angle; horizontal strokes are thin,
  vertical or diagonal strokes are thick. Rotate the pen in your hand to feel this.
- **No short vowels marked** in classical manuscripts: vowel marks (ḥarakāt — zabar ـَ /a/ · zir ـِ /e/ ·
  pish ـُ /o/ · madd آ /ā/ · tashdid ـّ doubling · sukūn ـْ no vowel) appear only in beginners' texts and
  the Quran. You must supply them from context.

**Daily hand exercise:** Copy the opening bayt (couplet) five times in your best approximation of
nastaʿlīq. Start with a broad felt-tip or chisel-nib pen; the reed (qalam) is the ideal but unforgiving.

---

## Layer 2 — Glossed reading (decode the line)

The opening of Rumi's **Masnavi-ye Maʿnavi** (مثنوی معنوی), Book I — the most copied and recited couplet
in Persian literature. Copy it by hand, then work the gloss.

```
بشنو این نی چون شکایت می‌کند
bishnaw  īn  ney  chon  shekāyat  mī-konad

از جدایی‌ها حکایت می‌کند
az  jodāyī-hā  hekāyat  mī-konad
```

### Gloss — line 1: بشنو این نی چون شکایت می‌کند

| Word | Translit | Gloss |
| --- | --- | --- |
| بشنو | bishnaw | **listen!** — imperative 2sg of شنیدن (shenīdan, "to hear"); the prefix **ب-** marks the imperative |
| این | īn | **this** — proximal demonstrative (invariable) |
| نی | ney | **reed flute** — the central symbol of the poem; a reed cut from the reed-bed, crying separation |
| چون | chon | **how / as / because** — here: "how, in what manner" |
| شکایت | shekāyat | **complaint, lament** — Arabic loanword (شكاية); the noun object of the verb |
| می‌کند | mī-konad | **it makes / it is making** — 3sg present imperfective; می‌ is the imperfective prefix; کند from کردن (kardan, "to do/make") |

**Line 1 literal:** "Listen to this reed, how it tells of complaints —"

### Gloss — line 2: از جدایی‌ها حکایت می‌کند

| Word | Translit | Gloss |
| --- | --- | --- |
| از | az | **from / of** — the primary ablative/source preposition |
| جدایی‌ها | jodāyī-hā | **separations** — جدایی (jodāyī, "separation") + ـ‌ها (-hā, the Persian plural suffix) |
| حکایت | hekāyat | **story, tale, account** — Arabic loanword; parallel to شکایت above (note the rhyme and near-paronomasia) |
| می‌کند | mī-konad | **it makes / it tells** — same verb again; the repetition is structural (the masnavi form echoes) |

**Line 2 literal:** "From separations it tells its tale —"

**Literary rendering (after Arberry):** "Listen to the reed, how it tells a tale of separations."

**Rumi's own gloss (Masnavi I.4):** the reed is the human soul separated from the divine origin — the
reed-bed (نیستان, neystān). Every listener who has known longing recognises the cry. This single image
carries the entire poem.

**Method:** The Masnavi corpus holds this text with the Persian original + multiple English translations
(Arberry · Nicholson · Helminski · Barks). Read the Persian aloud (even approximately), copy it, gloss
each word, then COMPARE how the translators render نی (ney) and جدایی (jodāyī) — Barks poeticises
("the reed of separation, crying"); Nicholson stays philological ("reed-flute"). That gap *is* the lesson.

**Recurring formulae to recognise on sight:**
- `می‌کند` (mī-konad) — the imperfective 3sg workhorse; once you know it, verbs unlock across the text
- `از ... تا ...` (az … tā …) — "from … to …" — the structural arc of many bayts
- `دل` (del, "heart") — appears hundreds of times; always the seat of spiritual longing
- `عشق` (ʿeshq, "love/eros") — Rumi's ultimate subject; feel the ʿayn at the throat
- `هر که` (har ke, "whoever") — opens many universal declarations in the Divan

---

## Layer 3 — Serious grammar (toward unaided translation)

Minimal orientation; expand as you go (recommended: Wheeler Thackston, *An Introduction to Persian*,
freely available as a PDF; also Lazard, *A Grammar of Contemporary Persian* for the classical base).

### Word order: Subject — Object — Verb (SOV)

Persian is firmly SOV. The verb almost always stands last in its clause. "Ahmad the apple ate" = احمد سیب خورد
(Ahmad sib khord). When you encounter a long line of nouns and adjectives, the verb at the end resolves everything.
Rumi often delays the verb for maximum impact; the reader is suspended.

### No grammatical gender; no definite article

Persian has neither — a radical simplification compared to Arabic or Greek. سیب can mean "a apple" or
"the apple" depending on context. Definiteness is signalled pragmatically or by the direct-object marker را (rā).

### The direct-object marker را (rā)

When a specific / definite object is named, را follows it: **نی را بشنو** — "listen to *the* reed
(specifically)." This is the single most important function-word to recognise; it marks the grammatical object.

### Ezāfe: the linking particle ـِ / -e / -ye

The ezāfe (اضافه) is the glue of Persian phrases. It links noun + adjective, noun + noun (possessive),
and noun + prepositional phrase. It is written as a short vowel (not usually marked): **دل‌هایِ شاعران**
(del-hāy-e shāʿerān) = "the hearts of the poets." In reading, supply an unstressed /e/ wherever an
adjective or genitive noun follows another noun. This is the second most important structure to internalise.

### Verbs: stem + ending

Every Persian verb has a **present stem** and a **past stem**. All tenses are built on these two.

| Form | Persian | Translit | Notes |
| --- | --- | --- | --- |
| Infinitive | شنیدن | shenīdan | "to hear" — infinitives always end in -دن (-dan) or -تن (-tan) |
| Present stem | شنو | shnaw | Drop -دن, what remains; irregular verbs listed in grammars |
| Past stem | شنید | shenīd | Usually infinitive minus -ن (-n) |
| Imperfective (habitual/continuous) | می‌شنوم | mī-shnaom | می‌ + present stem + personal endings |
| Perfective (simple past) | شنیدم | shenīdam | Past stem + personal endings |
| Imperative 2sg | بشنو | bishnaw | ب- + present stem |

**Personal endings (present):** -م (I) · -ی (you sg.) · -د (he/she/it) · -یم (we) · -ید (you pl.) · -ند (they)

### Plurals

Animate/human: suffix **ـان** (-ān): شاعر (poet) → شاعران (poets); عاشق (lover) → عاشقان (lovers).
Inanimate (and common informal): suffix **ـها** (-hā): دل → دل‌ها (hearts); نی → نی‌ها (reed flutes).
Both suffixes are invariable — no declension by case.

### Arabic loanwords (about 50% of classical Persian vocabulary)

Classical Persian poetry draws heavily on Arabic roots. Arabic broken plurals occasionally survive:
عاشق (ʿāsheq, "lover") → عشاق (ʿoshshāq, "lovers"). Recognise the trilateral Arabic root beneath
the Persian vowel frame: ع-ش-ق = root of love/longing; ج-د-ی = root of separation. Knowing twenty
Arabic roots unlocks hundreds of Persian derivatives.

### Script-specific reading strategies

1. **Left edge first, then interior.** In a joined cluster, the rightmost character is the word-start;
   track left to find the end. The eye habits reverse.
2. **Count dots.** ب · پ · ت · ث differ only in dot count and placement. Slow down at every dot cluster.
3. **Context resolves ambiguity.** Unvocalised Persian is genuinely ambiguous without context; this is
   not a flaw, it is classical reading practice. The meaning emerges from the whole bayt (couplet), not
   the isolated word.
4. **Memorise the must-know clusters:** می‌کند · می‌شود · گفت · بود · هست — five verbs covering 30%
   of prose encounters.

### Daily drill

Take today's bayt. Parse ONE word fully: (a) identify the root / infinitive; (b) name the form
(present stem / past stem / noun / adjective / preposition); (c) write the ezāfe chain if present;
(d) write the English alongside. Then read the full couplet aloud three times without looking at
the gloss. Write your parse in the studium ledger.

---

*Source rails:*
- **Ganjoor** (ganjoor.net) — the definitive Persian poetry corpus; Masnavi, Divan-e Shams, Hafez, Saʿdi,
  all in original script with line-by-line navigation
- **Wikisource fa:** full Masnavi in Persian with interlinear resources
- **Nicholson's Masnavi** (Archive.org) — 8-vol. Persian text + literal translation + commentary;
  the scholarly standard
- **Thackston, *Introduction to Persian*** (free PDF, Harvard) — the best self-study grammar for
  classical and modern; start Chapter 1 alongside this file
- **Forvo / Persian pronunciation guides** — hear native nastaʿlīq recitation; search "تلاوت مثنوی"
  on YouTube for master qāris reading Rumi aloud — listen before you speak
- Local corpus: `classical/masnavi/persian_original.txt` (+ Arberry, Nicholson, Helminski, Barks translations)
