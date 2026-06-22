# Arabic — the script for the Quran (القرآن الكريم)

> Script first, grammar second, translation third. The key is not fluency — it is **physical contact
> with the text**. Handwriting slows you down enough to notice structure. Three layers below; go as
> deep as the day allows (set `language_depth` in `logs/studium-state.json`).

---

## Layer 1 — Calligraphy / paleography (the hand)

**Direction: right to left. Write every line from right to left. This is not a convention — it is
the orientation of the script's entire body.**

Arabic is a **cursive alphabet of 28 consonants** (an *abjad* — vowels are mostly unmarked in
print, but the Quran is **fully vocalized** with *harakat* diacritics; learn with the marks). Most
letters have **four joining forms**: isolated · initial · medial · final. Six letters (ا و ر ز د ذ)
are **non-connectors**: they join to the right but never to the left, forcing a break in the word.

### The 28 letters — naskh hand (the standard Quranic script)

The table reads right to left per Arabic convention. Transliteration follows the Library of Congress
ALA-LC scheme (macrons for long vowels). Write each letter 5× in all four joining forms.

| Isolated | Final | Medial | Initial | Name | Sound |
|:--------:|:-----:|:------:|:-------:|------|-------|
| ا | ـا | — | — | alif | /aː/ (long a) — non-connector |
| ب | ـب | ـبـ | بـ | bāʾ | /b/ |
| ت | ـت | ـتـ | تـ | tāʾ | /t/ |
| ث | ـث | ـثـ | ثـ | thāʾ | /θ/ (English "th" in "think") |
| ج | ـج | ـجـ | جـ | jīm | /dʒ/ |
| ح | ـح | ـحـ | حـ | ḥāʾ | /ħ/ (voiceless pharyngeal — no English equivalent) |
| خ | ـخ | ـخـ | خـ | khāʾ | /x/ (like Scottish "loch") |
| د | ـد | — | — | dāl | /d/ — non-connector |
| ذ | ـذ | — | — | dhāl | /ð/ (English "th" in "the") — non-connector |
| ر | ـر | — | — | rāʾ | /r/ (trilled) — non-connector |
| ز | ـز | — | — | zayn | /z/ — non-connector |
| س | ـس | ـسـ | سـ | sīn | /s/ |
| ش | ـش | ـشـ | شـ | shīn | /ʃ/ |
| ص | ـص | ـصـ | صـ | ṣād | /sˤ/ (emphatic s — tongue root retracted) |
| ض | ـض | ـضـ | ضـ | ḍād | /dˤ/ (emphatic d) |
| ط | ـط | ـطـ | طـ | ṭāʾ | /tˤ/ (emphatic t) |
| ظ | ـظ | ـظـ | ظـ | ẓāʾ | /ðˤ/ (emphatic dh) |
| ع | ـع | ـعـ | عـ | ʿayn | /ʕ/ (voiced pharyngeal — no English equivalent) |
| غ | ـغ | ـغـ | غـ | ghayn | /ɣ/ (voiced uvular fricative — like French "r") |
| ف | ـف | ـفـ | فـ | fāʾ | /f/ |
| ق | ـق | ـقـ | قـ | qāf | /q/ (uvular stop — deeper than /k/) |
| ك | ـك | ـكـ | كـ | kāf | /k/ |
| ل | ـل | ـلـ | لـ | lām | /l/ |
| م | ـم | ـمـ | مـ | mīm | /m/ |
| ن | ـن | ـنـ | نـ | nūn | /n/ |
| ه | ـه | ـهـ | هـ | hāʾ | /h/ |
| و | ـو | — | — | wāw | /w/ or /uː/ (long u) — non-connector |
| ي | ـي | ـيـ | يـ | yāʾ | /j/ or /iː/ (long i) |
| ء | varies | varies | varies | hamza | /ʔ/ (glottal stop) — written above/below carrier letters |

**Hand notes (ductus — naskh style):**
- **bāʾ / tāʾ / thāʾ** share the same base shape; only the dots distinguish them (1 below · 2 above · 3 above). Master the base first, then place dots precisely.
- **ḥāʾ / jīm / khāʾ** share a base: the hook narrows at medial position. The distinction is entirely in the dot (jīm below · khāʾ above · ḥāʾ none).
- **The emphatics (ṣ ḍ ṭ ẓ)** are physically larger letters with a "filled" or "looped" body — the weight of the pen increases. They transform neighbouring vowels (pharyngealization / "darkening").
- **lām-alif (لا)** is a mandatory ligature — these two letters always fuse. It does not break even in medial position.
- **Hamza (ء)** floats above alif (أ), below alif (إ), above wāw (ؤ), above yāʾ without dots (ئ), or freestanding (ء). Its placement is governed by surrounding vowel hierarchy rules.

### Harakat — the full vowel diacritics (Quranic standard)

The Quran is written with every diacritic marked. Practise each on a bare consonant (e.g. بَ بِ بُ بْ بَّ):

| Mark | Arabic | Name | Pronunciation |
|------|--------|------|---------------|
| ـَ | فَتْحة | fatḥa | short /a/ |
| ـِ | كَسْرة | kasra | short /i/ |
| ـُ | ضَمَّة | ḍamma | short /u/ |
| ـْ | سُكُون | sukūn | no vowel (consonant rests) |
| ـَّ | شَدَّة | shadda | gemination (double the consonant) |
| ـً ـٍ ـٌ | تَنْوِين | tanwīn | nunation: -an / -in / -un (indefinite endings) |
| ا ي و | مَدّ | madd | long vowels /aː iː uː/ |

**Quranic recitation note:** the Quran is recited in *tajwīd* (تَجْوِيد) — a precise phonological
system governing assimilation, nasalization (*ghunna*), and elongation (*madd*). Every haraka
triggers specific tajwīd rules. Even reading silently, mark and sound them; they are the grammar
made audible.

---

## Layer 2 — Glossed reading (decode the line)

The *Fātiḥa* (سُورَةُ الْفَاتِحَة, "The Opening") — Surah 1, the seven-verse prayer that opens the
Quran and is recited in every unit of every prayer. Copy it by hand in full vocalized naskh, then
work the gloss word by word.

**Full text (fully vocalized):**

```
بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ
bi-smi llāhi r-raḥmāni r-raḥīmi

الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ
al-ḥamdu li-llāhi rabbi l-ʿālamīna

الرَّحْمَٰنِ الرَّحِيمِ
ar-raḥmāni r-raḥīmi

مَالِكِ يَوْمِ الدِّينِ
māliki yawmi d-dīni

إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ
iyyāka naʿbudu wa-iyyāka nastaʿīnu

اهْدِنَا الصِّرَاطَ الْمُسْتَقِيمَ
ihdina ṣ-ṣirāṭa l-mustaqīma

صِرَاطَ الَّذِينَ أَنْعَمْتَ عَلَيْهِمْ
ṣirāṭa lladhīna anʿamta ʿalayhim

غَيْرِ الْمَغْضُوبِ عَلَيْهِمْ وَلَا الضَّالِّينَ
ghayri l-maghḍūbi ʿalayhim wa-lā ḍ-ḍāllīna
```

**Word-by-word gloss — verse 1:**

| Word | Translit | Gloss |
|------|----------|-------|
| بِسْمِ | bi-smi | **in the name** — *bi* (prep. "in/by") + *ism* (noun "name", genitive after prep.) |
| اللَّهِ | llāhi | **of God/Allah** — genitive (the noun governs *ism*) |
| الرَّحْمَٰنِ | r-raḥmāni | **the Entirely Merciful** — genitive, adjective appositive to Allāh; root رحم |
| الرَّحِيمِ | r-raḥīmi | **the Especially Merciful** — genitive; same root, *raḥīm* = ongoing mercy toward believers |

**Word-by-word gloss — verse 2:**

| Word | Translit | Gloss |
|------|----------|-------|
| الْحَمْدُ | al-ḥamdu | **praise** — definite noun, nominative (subject); root حمد |
| لِلَّهِ | li-llāhi | **belongs to God** — *li* (prep. "for/to") + Allāh genitive |
| رَبِّ | rabbi | **Lord of** — genitive, in *iḍāfa* (construct) with what follows; root ربب |
| الْعَالَمِينَ | l-ʿālamīna | **the worlds** — genitive plural; *ʿālamīn* = all realms of existence |

**Word-by-word gloss — verse 5:**

| Word | Translit | Gloss |
|------|----------|-------|
| إِيَّاكَ | iyyāka | **You alone** — object pronoun fronted for emphasis (it means "You, specifically, and no other") |
| نَعْبُدُ | naʿbudu | **we worship** — present imperfect, 1st pl.; root عبد ("to worship / to serve") |
| وَإِيَّاكَ | wa-iyyāka | **and You alone** — conjunction + same fronted pronoun (the repetition is deliberate) |
| نَسْتَعِينُ | nastaʿīnu | **we seek help** — present imperfect, 1st pl.; Form X (*istaʿāna*) = to seek to receive aid; root عون |

- **Literal (v. 5):** "You we worship and You we seek help from."
- **Literary:** "You alone do we worship, and You alone do we ask for help."

**Structural note on the *Fātiḥa*:** verses 1–3 are description (God's nature); verse 4 is *māliki
yawmi d-dīn* — "Master of the Day of Judgment" — the pivot; verse 5 shifts from *he* to *you*
(from description to address), which classical commentators call the most dramatic pronoun shift in
Arabic literature. Mark where that shift happens in your handwritten copy.

**Compare translations:** the Quran corpus holds at least three English translations (Pickthall ·
Yusuf Ali · Abdel Haleem). Read the Arabic, gloss it yourself, then compare how each translator
renders *raḥmān* vs. *raḥīm* (both from the same root — why are they different words?), and how
each handles the fronted *iyyāka* in verse 5.

---

## Layer 3 — Serious grammar (toward unaided translation)

Minimal orientation. Recommended companion: Wright, *A Grammar of the Arabic Language* (classic,
exhaustive) or Haywood & Nahmad, *A New Arabic Grammar* (accessible). For Quranic specifically:
Abdur Rahim, *Teach Yourself Arabic* + any *tajwīd* primer.

### The root system — the spine of everything

Arabic is built on **triliteral roots** (almost always three consonants). All words from a root
share a semantic field; the vowel pattern (*wazn*, "measure") signals the grammatical function.

- Root **ك-ت-ب** (k-t-b) = "writing": *kataba* (he wrote) · *kitāb* (book) · *kātib* (writer/scribe) · *maktab* (office/desk) · *maktūb* (written/letter)
- Root **ع-ل-م** (ʿ-l-m) = "knowledge": *ʿalima* (he knew) · *ʿilm* (knowledge) · *ʿālim* (scholar) · *ʿālamīn* (worlds/realms) · *taʿallama* (he learned)
- Root **ر-ح-م** (r-ḥ-m) = "mercy/womb": *raḥima* (he had mercy) · *raḥma* (mercy) · *raḥmān* (intensely merciful) · *raḥīm* (continually merciful) · *arḥam* (womb, pl. *arḥām*)

**Drill habit:** when you meet a new word, strip its vowels and identify the root. Everything else
follows.

### Nouns and the dual system

Arabic has three numbers: singular · dual · plural. The plural is often **broken** (internal vowel
change, not a suffix) and must be memorized per word — like English "goose / geese" but pervasive.

- **Definite article:** *al-* (ال) prefixed to the noun, always. It assimilates to "sun letters"
  (الشمس *ash-shams*, not *al-shams*) and remains unchanged before "moon letters" (القمر *al-qamar*).
- **Cases:** three — nominative (*ḍamma* -u) · genitive (*kasra* -i) · accusative (*fatḥa* -a). In
  Quranic Arabic the case endings are written and recited. *al-ḥamdu* (nom.) vs. *li-llāhi* (gen.
  after preposition).
- **Iḍāfa (الإضافة) — the construct chain:** possession is shown by juxtaposition, not a separate
  word. First noun is indefinite (no *al-*), second is genitive. *rabbi l-ʿālamīn* = "Lord of the
  worlds" (*rabb* = definite by the genitive following it, even without *al-*).
- **Gender:** two — masculine (unmarked) and feminine (usually marked with ة *tāʾ marbūṭa*). Adjectives agree with the noun they modify in gender, number, definiteness, and case.

### Verbs — the pattern system

The base form is the **3rd person masculine singular perfect** (*māḍī*): *kataba* "he wrote."
Conjugation changes the endings (perfect) or surrounds the root with prefixes/suffixes (imperfect).

| Person | Perfect | Imperfect |
|--------|---------|-----------|
| 3rd m. sg. | كَتَبَ *kataba* | يَكْتُبُ *yaktubu* |
| 3rd f. sg. | كَتَبَتْ *katabat* | تَكْتُبُ *taktubu* |
| 2nd m. sg. | كَتَبْتَ *katabta* | تَكْتُبُ *taktubu* |
| 1st sg. | كَتَبْتُ *katabtu* | أَكْتُبُ *aktubu* |
| 1st pl. | كَتَبْنَا *katabnā* | نَكْتُبُ *naktubu* |

**The ten derived verb forms (أَوْزَان, awzān):** Arabic extends roots through 10 standard patterns,
each adding a predictable shade of meaning. Form I (*faʿala*) is the base. Form II (*faʿʿala*)
intensifies or makes causative. Form IV (*afʿala*) causative. Form V (*tafaʿʿala*) reflexive of II.
Form X (*istaʿfala*) — seen in *nastaʿīnu* — means "to seek to do / to deem X." Once you know a
root, the ten forms are largely predictable.

### Word order

Classical/Quranic Arabic is **verb-subject-object (VSO)** in verbal sentences, but the subject can
precede the verb for emphasis. The *Fātiḥa* verse 5 (*iyyāka naʿbudu*) is OV — the object is
fronted for rhetorical emphasis ("You — it is You we worship"). Fronting any element emphasizes it;
this is the main device of Quranic rhetoric.

### The emphatic letters and their effect

The four emphatic consonants (ص ض ط ظ) cause **pharyngealization** of surrounding vowels: the
vowels "darken" toward /ɑ/ even when written as /a/ or /i/. This is why *ṣirāṭ* (صِرَاط, "path")
sounds darker than *sirāt* would. The effect spreads to adjacent syllables. Train your ear by
listening to a reciter (Mishary Rashid Al-Afasy · Abdul Basit · Minshawi) before reading aloud.

### Daily drill

1. Copy one verse of the Fātiḥa in naskh — fully vocalized.
2. Parse every noun: case · gender · number · definite or indefinite.
3. Parse every verb: root · form (I–X) · person · number · gender · tense.
4. Identify the root of three words and derive two other words from the same root.
5. Listen to a reciter say the verse; mark where your vowels were correct or wrong.

---

*Source rails:*
- **Quran.com** — fully vocalized Arabic text, verse-by-verse word gloss (morphological parser), 15+ English translations to compare, audio from top reciters (click any word for full parsing)
- **Quranic Arabic Corpus** (corpus.quran.com) — dependency graphs and detailed morphological annotation for every word in the Quran
- **Perseus / Buckwalter Transliteration** — for romanized search when you cannot yet type Arabic
- **Hans Wehr, *A Dictionary of Modern Written Arabic*** — the standard dictionary; roots arranged alphabetically by root consonants
- **Lane's Lexicon** (archive.org) — exhaustive classical Arabic dictionary; essential for Quranic vocabulary which often carries meanings absent from Modern Standard Arabic
- Local corpus: `classical/quran/arabic_original.txt` (+ translations for comparison)
