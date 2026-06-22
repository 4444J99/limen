# Hebrew — the script for Tanakh (Torah, Prophets, Writings)

> Script first, grammar second, translation third. The key is not fluency — it is **physical contact
> with the text**. Handwriting slows you down enough to notice structure. Three layers below; go as
> deep as the day allows (set `language_depth` in `logs/studium-state.json`).

---

## Layer 1 — Calligraphy / paleography (the hand)

Hebrew is written **right to left**. The alef-bet has 22 consonantal letters; vowels are added below
and above as **niqqud** (pointing). Block (printed) form is your entry; square script is what the Torah
scroll uses — practise both. Five letters have a final form when they close a word.

Write each letter 5× — right to left, column by column.

| Letter | Name | Sound | Final form | Ductus note |
|--------|------|-------|------------|-------------|
| א | alef | silent / glottal | — | two diagonal strokes meeting a central diagonal; the "spine" leans right |
| ב | bet / vet | /b/ · /v/ (dot = dagesh → /b/) | — | one open rectangle, open on left; dot inside = bet |
| ג | gimel | /g/ | — | a foot-shape; downstroke then a short right foot |
| ד | dalet | /d/ | — | a right-angle corner; roof + drop |
| ה | he | /h/ | — | like dalet but with a gap at lower-left and a floating inner stroke |
| ו | vav | /v/ · vowel-holder | — | a simple downstroke with a small head; the slimmest letter |
| ז | zayin | /z/ | — | vav with a cap; the head extends left and right |
| ח | het | /ħ/ (guttural h) | — | two parallel legs joined at top with a bridge; no gap |
| ט | tet | /t/ | — | a closed rounded form with an inward-curling top |
| י | yod | /y/ · vowel-holder | — | the smallest letter: a floating comma-tick |
| כ | kaf / khaf | /k/ · /x/ | ך | open on left like bet but taller; final = long downstroke |
| ל | lamed | /l/ | — | a tall ascending stroke with a hook right — tallest letter |
| מ | mem | /m/ | ם | closed square with a small gap at bottom-left; final = fully closed square |
| נ | nun | /n/ | ן | a short stroke curving right; final = long straight downstroke |
| ס | samekh | /s/ | — | a fully closed circle/oval |
| ע | ayin | silent / pharyngeal | — | a Y-shape; two strokes meeting at a point above a downstroke |
| פ | pe / fe | /p/ · /f/ | ף | like kaf with a small interior nose; final = long descending stroke curving left |
| צ | tsade | /ts/ | ץ | a yod-like head on a wider base; final = long descending stroke |
| ק | qof | /q/ | — | like kaf but with a descending stroke through the baseline |
| ר | resh | /r/ | — | like dalet but the roof rounds into the drop without a sharp corner |
| ש | shin / sin | /ʃ/ · /s/ (dot position: right = shin, left = sin) | — | three prongs rising from a base |
| ת | tav | /t/ | — | like dalet with a left foot added at the base |

**Dagesh (dot inside a letter):** a dot inside ב ג ד כ פ ת doubles or hardens the consonant (בּ = /b/
vs. בֿ = /v/). After a vowel, it is "lene" (phonemic); after a consonant, "forte" (gemination).

**Niqqud — the vowel pointing system** (below/above the consonant they follow):

| Vowel | Sign | Sound | Example |
|-------|------|-------|---------|
| Qamats | ָ (below) | /aː/ | בָּ bā |
| Patah | ַ (below) | /a/ | בַּ ba |
| Tsere | ֵ (below) | /eː/ | בֵּ bē |
| Segol | ֶ (below) | /e/ | בֶּ be |
| Hireq | ִ (below) | /i/ | בִּ bi |
| Holem | ֹ (above-left) | /oː/ | בֹ bō |
| Qibbuts | ֻ (below) | /u/ | בֻּ bu |
| Shureq | וּ (vav + dot) | /uː/ | בוּ bū |
| Sheva | ְ (below) | /ə/ or silent | בְּ bᵉ |

**Script note:** when copying a Torah passage by hand (even in a notebook), write right to left, leave
space for vowels even if you omit the pointing, and read back aloud. The physical direction rewires
the eye. Five to ten minutes daily builds the recognition reflex faster than any drill sheet.

---

## Layer 2 — Glossed reading (decode the line)

The opening of Bereshit (Genesis 1:1) — the most copied Hebrew sentence in history.
Copy it by hand (right to left), then work the gloss.

```
בְּרֵאשִׁית  בָּרָא  אֱלֹהִים  אֵת  הַשָּׁמַיִם  וְאֵת  הָאָרֶץ
bᵉrēʾšît   bārāʾ  ʾĕlōhîm  ʾēt  haššāmayim  wᵉʾēt  hāʾāreṣ
```

| Word | Transliteration | Gloss |
|------|----------------|-------|
| בְּרֵאשִׁית | bᵉrēʾšît | **In the beginning** — בְּ (prep. "in") + רֵאשִׁית (beginning, construct state) |
| בָּרָא | bārāʾ | **he created** — Qal perfect 3ms of בָּרָא (bāraʾ); subject follows verb in VSO order |
| אֱלֹהִים | ʾĕlōhîm | **God** — plural form (majestic plural) but takes singular verb; the subject |
| אֵת | ʾēt | **[object marker]** — untranslated; marks the definite direct object; no English equivalent |
| הַשָּׁמַיִם | haššāmayim | **the heavens** — הַ (definite article) + שָּׁמַיִם (dual/plural, "heavens/sky") |
| וְאֵת | wᵉʾēt | **and [object marker]** — וְ (conjunction "and") + אֵת (object marker again) |
| הָאָרֶץ | hāʾāreṣ | **the earth** — הָ (definite article, lengthened before ʿayin/alef) + אָרֶץ (earth/land) |

- **Literal:** "In-beginning created God [obj.] the-heavens and-[obj.] the-earth"
- **Literary:** "In the beginning God created the heavens and the earth."

**Method:** the corpus holds the Hebrew Tanakh + multiple English translations (KJV · JPS 1917 · NRSV ·
Robert Alter). Read the Hebrew aloud using the transliteration, copy it letter by letter right to left,
gloss each word, then COMPARE how the four translators handle אֵת (the untranslatable object marker) —
its very untranslatability is the first lesson in Hebrew syntax.

**Formulaic phrases to recognise on sight** (they recur across the Tanakh):

- `וַיֹּאמֶר אֱלֹהִים` — "And God said" (wayyiqtol narrative formula, Genesis refrain)
- `וַיְהִי` — "And it was / And it came to pass" (standard narrative opener)
- `כִּי טוֹב` — "that it was good" (the evaluative refrain of the creation days)
- `לְעוֹלָם וָעֶד` — "forever and ever" (liturgical doxology formula)
- `בֶּן / בַּת` — "son of / daughter of" (genealogical marker throughout)
- `יְהוָה אֱלֹהֶיךָ` — "the LORD your God" (covenantal address formula)

---

## Layer 3 — Serious grammar (toward unaided translation)

Minimal orientation; expand as you go (recommended companions: Pratico & Van Pelt, *Basics of Biblical
Hebrew*; Gesenius, *Hebrew Grammar* for depth; Lambdin, *Introduction to Biblical Hebrew*).

**Word order:** Biblical Hebrew is primarily **Verb–Subject–Object (VSO)** in narrative (wayyiqtol
sequences), though word order shifts freely for emphasis. The verb usually comes first: `בָּרָא אֱלֹהִים`
("created God") not "God created."

**The root system:** Hebrew is built on **three-consonant roots** (shorashim). Nearly every word is
derived by inserting vowels and adding prefixes/suffixes around the root. The root בָּרָא (b-r-ʾ) means
"create"; you will see it across verb forms, nouns, and derivatives. Learning roots is the multiplier.

**Nouns — gender and definiteness:**
- Two genders: masculine and feminine. Feminine typically ends in ָה (-āh) or ַת (-at).
- Plural: masculine adds ִים (-îm); feminine adds וֹת (-ôt).
- **Definite article:** prefix הַ (ha-) with a dagesh in the next consonant: אָרֶץ (land) → הָאָרֶץ (the land).
- **Construct chain (smikhut):** "the word of the LORD" = דְּבַר יְהוָה; the first noun takes construct form
  (often shortened vowels), the second is definite by association. No article on the first noun.

**Verbs — the two-tense (aspect) system:**
- **Qal perfect** (suffix conjugation): completed action. `בָּרָא` = he created (3ms Qal perfect).
- **Qal imperfect** (prefix conjugation): incomplete/habitual action. `יִבְרָא` = he will create / he creates.
- **Wayyiqtol** (וַיִּ + imperfect prefix): the **narrative past** — the backbone of biblical storytelling.
  The ו (vav consecutive) + imperfect = past sequence. `וַיֹּאמֶר` = "and he said" (narrative).
- **Wᵉqatal** (וְ + perfect): future sequence in direct speech/prophecy.
- Seven stems (binyanim): Qal (basic) · Niphal (passive/reflexive) · Piel (intensive) · Pual (passive
  Piel) · Hiphil (causative) · Hophal (passive Hiphil) · Hithpael (reflexive intensive). Each stem
  transforms the root vowels and/or adds prefixes. Learn to spot the pattern.

**Pronouns as verb suffixes:** person is encoded in the verb ending; a separate pronoun is emphatic.
`בָּרָא` = "he created" (the ā ending = 3ms); `בָּרָאתָ` = "you (ms) created" (ָתָ suffix).

**The inseparable prepositions:** בְּ (in/with) · לְ (to/for) · כְּ (as/like) · מִ (from) fuse to the
next word: בְּרֵאשִׁית = "in beginning." וְ (and), שֶׁ (that/which) work the same way.

**The object marker אֵת:** has no English translation; marks a definite direct object. Its presence is
a parsing signal — what follows is the object. Encounter it, note it, move on.

**Script-specific parsing habit:** when you meet an unfamiliar word, strip the inseparable prefixes
(בְּ לְ כְּ מִ וְ הַ), identify the three-consonant root, then look it up. The root is the address.

**Daily grammar drill:** take the day's verse, identify (1) the root of each verb, (2) its stem
(binyan), (3) its person/gender/number, and (4) which nouns are definite and why. Write the parsed
line in your ledger. One verse, fully parsed, is worth ten verses skimmed.

---

*Source rails:* [Sefaria](https://www.sefaria.org) (Hebrew text + interlinear, every book of the
Tanakh, free) · [Mechon Mamre](https://mechon-mamre.org) (Westminster Leningrad Codex, unpointed +
pointed) · [Academy of the Hebrew Language](https://hebrew-academy.org.il) (morphology + lexicon) ·
the local corpus `classical/genesis/hebrew_original.txt` (+ KJV · JPS · NRSV · Alter to compare) ·
Pratico & Van Pelt *Basics of Biblical Hebrew* (grammar with graded readings) · BibleHub interlinear
(Strong's numbers + parsing for every word, useful as a check not a crutch).
