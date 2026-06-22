# Sanskrit — the script for the Bhagavad Gita

> Script first, grammar second, translation third. The key is not fluency — it is **physical contact
> with the text**. Handwriting slows you down enough to notice structure. Three layers below; go as
> deep as the day allows (set `language_depth` in `logs/studium-state.json`).

---

## Layer 1 — Calligraphy / paleography (the hand)

Sanskrit is written in **Devanagari** (देवनागरी), a syllabic alphabet (abugida) written left to right.
Each consonant carries an inherent /a/ vowel; a vowel mark (mātrā) overrides it; a halanta (्) kills it.
The defining feature: a **horizontal head-stroke (mātrā-line)** runs across the top of each letter,
connecting characters into words. Write it last, drawn right through, after finishing the body of the letter.

### Vowels (स्वर svara) — written as independent letters at the start of a syllable

| अ a /ə/ | आ ā /aː/ | इ i /i/ | ई ī /iː/ | उ u /u/ | ऊ ū /uː/ |
| ए e /eː/ | ऐ ai /ai/ | ओ o /oː/ | औ au /au/ | ऋ ṛ /ri/ | ॐ oṃ (sacred syllable) |

### Consonants (व्यञ्जन vyañjana) — five phonetic rows + approximants

| क ka /k/ | ख kha /kʰ/ | ग ga /g/ | घ gha /gʱ/ | ङ ṅa /ŋ/ |
| च ca /tʃ/ | छ cha /tʃʰ/ | ज ja /dʒ/ | झ jha /dʒʱ/ | ञ ña /ɲ/ |
| ट ṭa /ʈ/ | ठ ṭha /ʈʰ/ | ड ḍa /ɖ/ | ढ ḍha /ɖʱ/ | ण ṇa /ɳ/ |
| त ta /t̪/ | थ tha /t̪ʰ/ | द da /d̪/ | ध dha /d̪ʱ/ | न na /n/ |
| प pa /p/ | फ pha /pʰ/ | ब ba /b/ | भ bha /bʱ/ | म ma /m/ |
| य ya /j/ | र ra /r/ | ल la /l/ | व va /ʋ/ | | 
| श śa /ʃ/ | ष ṣa /ʂ/ | स sa /s/ | ह ha /h/ | |

**Ductus notes:** Write each consonant body first, then the mātrā-line last. The stroke order for क: 
vertical staff down, then the diagonal / body strokes, then the top bar. ग (ga) is a common beginners' 
stumbling block — it looks like a reversed 3 with a right hook, not a mirror of any Roman letter. 
ट, ठ, ड, ढ, ण are the retroflex row: tongue curls back to the palate — notice the curl added to the 
base form. Practise the five rows as phonetic families, not random symbols.

### Vowel marks (mātrā) — attached to consonants

When a vowel follows a consonant it is written as a diacritic, not as a separate letter:

| consonant + mark | reads as | example |
| --- | --- | --- |
| क + ा | kā | का |
| क + ि | ki | कि |
| क + ी | kī | की |
| क + ु | ku | कु |
| क + ू | kū | कू |
| क + े | ke | के |
| क + ै | kai | कै |
| क + ो | ko | को |
| क + ौ | kau | कौ |
| क + ृ | kṛ | कृ |
| क + ् | k (halanta, kills vowel) | क् |

### Conjunct consonants (saṃyukta)

When two consonants meet without an intervening vowel they form a **conjunct** — the first loses its 
right vertical stroke and fuses with the second. Common ones to recognise:

- क् + ष = क्ष (kṣa) — as in कृष्ण Kṛṣṇa
- त् + र = त्र (tra) — as in मित्र mitra (friend)
- ज् + ञ = ज्ञ (jña) — as in ज्ञान jñāna (knowledge)
- द् + ध = द्ध (ddha) — retroflex pair
- श् + र = श्र (śra) — as in श्री Śrī

**Sandhi (external joining):** At word-boundaries Sanskrit modifies sounds in rule-governed ways 
(a + a → ā; visarga ḥ shifts before voiced consonants). In the Gita the text runs together as a 
stream; mark word-breaks in pencil until the patterns become automatic.

**Special marks:**
- Anusvāra ं (ṃ/ṁ) — a dot above the line; nasalises the preceding vowel: संसार saṃsāra
- Visarga ः (ḥ) — two dots after the vowel; an aspirate breath; marks certain case endings: नरः naraḥ
- Chandrabindu ँ — crescent + dot; nasalised vowel, rarer in classical texts

---

## Layer 2 — Glossed reading (decode the line)

The opening of the Bhagavad Gita (1.1) — copy it by hand, then work the gloss.
(This is the gold-standard daily unit.)

```
धृतराष्ट्र उवाच
Dhṛtarāṣṭra uvāca

धर्मक्षेत्रे   कुरुक्षेत्रे    समवेता   युयुत्सवः  ।
dharma-kṣetre  kuru-kṣetre   samavetā  yuyutsavaḥ |

मामकाः     पाण्डवाश्चैव     किमकुर्वत   सञ्जय   ॥१॥
māmakāḥ   pāṇḍavāś caiva   kim akurvata  sañjaya  ||1||
```

| word | translit | gloss |
| --- | --- | --- |
| धृतराष्ट्र | Dhṛtarāṣṭra | **Dhritarashtra** — vocative implied; the blind king speaking |
| उवाच | uvāca | **said** — 3rd sg. perfect active of √vac (to speak) |
| धर्मक्षेत्रे | dharma-kṣetre | **on the field of dharma** — locative dual compound (dharma = righteousness/duty; kṣetra = field) |
| कुरुक्षेत्रे | kuru-kṣetre | **on the field of Kuru** — locative; the battlefield; also named place |
| समवेताः | samavetāḥ | **assembled, gathered** — nom. pl. past passive participle of sam-ā-√i |
| युयुत्सवः | yuyutsavaḥ | **desiring to fight** — nom. pl. desiderative adjective from √yudh (to fight); yuyutsā = desire for battle |
| मामकाः | māmakāḥ | **mine, my people** — nom. pl.; the Kauravas (Dhritarashtra's sons) |
| पाण्डवाः | pāṇḍavāḥ | **the sons of Pandu** — nom. pl.; the Pandavas |
| च एव | ca eva | **and indeed** — emphatic conjunction pair |
| किम् | kim | **what?** — interrogative pronoun, neut. nom./acc. |
| अकुर्वत | akurvata | **did they do?** — 3rd pl. imperfect middle of √kṛ (to do, make) |
| सञ्जय | sañjaya | **O Sanjaya** — vocative; the charioteer-narrator |

- **Literal:** "Dhritarashtra said: On the field of dharma, on the field of Kuru, assembled, desiring to fight — what did mine and the Pandavas do, O Sanjaya?"
- **Literary:** "Dhritarashtra spoke: Tell me, Sanjaya — on that field of dharma, that field of Kuru, my sons and the sons of Pandu gathered, eager for battle. What did they do?"

**Method:** the corpus holds the Sanskrit + multiple translations (Prabhupada · Easwaran · Sargeant · 
van Buitenen). Read the Sanskrit aloud — the metre (anuṣṭubh: 8 syllables per quarter) will carry you. 
Copy the verse, gloss each word, then COMPARE how translators render धर्मक्षेत्रे: is it "field of 
righteousness" (Prabhupada), "field of dharma" (Easwaran), "holy field" (others)? That difference 
is a philosophical argument. Translation is where the text becomes a living encounter.

**Recurring vocabulary to recognise on sight** (they saturate the Gita):

- `योग` yoga — union, disciplined practice; names whole chapters (karma-yoga, jñāna-yoga, bhakti-yoga)
- `आत्मन्` ātman — the Self (the central subject of the entire text)
- `ब्रह्मन्` brahman — the Absolute (neut.); brahmin/priest class (masc.)
- `कर्म` karma — action, deed, its fruit; the central ethical concept
- `ज्ञान` jñāna — knowledge, wisdom (from √jñā, cognate with Greek γνώ-, Latin gnō-)
- `भक्ति` bhakti — devotion, loving surrender
- `अर्जुन उवाच / श्रीभगवान् उवाच` — Arjuna spoke / the Blessed Lord spoke — the dialogue frame, appears ~100 times
- `न` na — not (negation, ubiquitous)

---

## Layer 3 — Serious grammar (toward unaided translation)

Minimal orientation; expand as you go (recommended companions: Coulson, *Teach Yourself Sanskrit*; 
Macdonell, *A Sanskrit Grammar for Students*; Sargeant's *Bhagavad Gita* interlinear).

**The basics of Sanskrit grammar you need for the Gita:**

### Nouns — eight cases × three genders × three numbers

Sanskrit has 8 cases (vibhakti). Word order is FREE because the ending carries the role:

| case | function | ending signal (a-stems masc.) |
| --- | --- | --- |
| Nominative | subject | -aḥ (sg) / -āḥ (pl) |
| Accusative | direct object | -am (sg) / -ān (pl) |
| Instrumental | by/with | -ena (sg) / -aiḥ (pl) |
| Dative | for, to | -āya (sg) / -ebhyaḥ (pl) |
| Ablative | from | -āt (sg) / -ebhyaḥ (pl) |
| Genitive | of, 's | -asya (sg) / -ānām (pl) |
| Locative | in, on, at | -e (sg) / -eṣu (pl) |
| Vocative | address | -a (sg) / -āḥ (pl) |

- **a-stems (masculine):** deva (god) → devaḥ / devam / devena / devāya / devāt / devasya / deve / deva
- **ā-stems (feminine):** senā (army) → senā / senām / senayā / senāyai / senāyāḥ / senāyāḥ / senāyām / sene
- **i-stems (masc./fem.):** kavi (poet), agni (fire) — slightly different endings; learn alongside the a-stems

### Verbs — ten classes, conjugated for person/number/tense/mood/voice

Root (dhātu) + class marker + personal endings. Gita uses primarily:

- **Present** (laṭ): karoti (he does) — 3rd sg. pres. act.
- **Imperfect** (laṅ): akarot (he did) — note the augment *a-* prefixed
- **Perfect** (liṭ): cakāra (he has done) — reduplicated; uvāca (said) is perfect of √vac
- **Future** (lṛṭ): kariṣyati (he will do)
- **Imperative** (loṭ): kuru (do!) — Krishna's command form, central to the Gita
- **Middle voice** (-te endings): kurute (he does for himself); middle expresses reflexive or intransitive sense

### Compounds (samāsa) — the master feature

Sanskrit packs meaning into long compounds. Four main types:

1. **Tatpuruṣa** (determinative): dharma-kṣetra = "field of dharma" (2nd word heads the compound)
2. **Dvandva** (copulative): dharma-artha = dharma and artha (both members equal)
3. **Bahuvrīhi** (possessive): "having X" — adjective modifying an external noun
4. **Avyayībhāva** (adverbial): prefix + noun, the whole acts as indeclinable adverb

In the Gita, split every compound at its juncture, identify the head, then translate inside-out.

### Script-specific features to track

- **Sandhi** at word-junctions merges final and initial sounds: the edition you read may run words 
  together (continuous sandhi) or split them (pada-pāṭha edition). Use Sargeant's interlinear, which 
  splits every compound and sandhi joint into individual words — invaluable for beginners.
- **Anuṣṭubh metre:** the Gita's dominant metre is 8 syllables × 4 pādas (quarter-verses). Reading 
  aloud in metre locks vocabulary into memory faster than any drill.
- **Visarga sandhi:** ḥ before voiced consonants → r or disappears; before unvoiced → stays or shifts. 
  Recognise it; don't let it hide familiar words.

### Daily grammar drill

Take the day's verse:
1. **Split every compound** and every sandhi junction. Write out each base word separately.
2. **Parse ONE verb fully:** root · class · person · number · tense · mood · voice.
3. **Parse ONE noun fully:** stem · gender · case · number · why that case was required.
4. Write the rule it illustrates in your ledger.

Example: `akurvata` → root √kṛ (class 8) · 3rd plural · imperfect · middle voice → "they did (for 
themselves / the reflexive flavour suits the factional battle)." Write: "imperfect = past narrative; 
augment a- prefixed to root; middle -ata ending for 3rd pl."

---

*Source rails:* GRETIL (Göttingen Register of Electronic Texts in Indian Languages — Sanskrit originals) ·
SARIT (Search and Retrieval of Indic Texts) · Gretil.sub.uni-goettingen.de ·
Sanskrit Documents (sanskritdocuments.org — Devanagari + transliteration PDFs) ·
Wisdom Library (wisdomlib.org — parallel Gita verses with multiple translations) ·
Sargeant's *The Bhagavad Gita* (interlinear; every word parsed — the best learning edition) ·
Monier-Williams Sanskrit–English Dictionary (online at cologne.de/cgi-bin/monier) ·
the local corpus `philosophy/bhagavad-gita/sanskrit_original.txt` (+ translations to compare).
