# Greek — the script for Homer (Iliad, Odyssey)

> Script first, grammar second, translation third. The key is not fluency — it is **physical contact
> with the text**. Handwriting slows you down enough to notice structure. Three layers below; go as
> deep as the day allows (set `language_depth` in `logs/studium-state.json`).

---

## Layer 1 — Calligraphy / paleography (the hand)

The 24 letters. Write each 5× until the ductus is muscle memory. (lower · UPPER · name · sound)

| α Α alpha /a/ | β Β beta /b/ | γ Γ gamma /g/ | δ Δ delta /d/ | ε Ε epsilon /e/ (short) |
| ζ Ζ zeta /zd/ | η Η eta /ɛː/ (long e) | θ Θ theta /tʰ/ | ι Ι iota /i/ | κ Κ kappa /k/ |
| λ Λ lambda /l/ | μ Μ mu /m/ | ν Ν nu /n/ | ξ Ξ xi /ks/ | ο Ο omicron /o/ (short) |
| π Π pi /p/ | ρ Ρ rho /r/ | σ/ς Σ sigma /s/ (ς word-final) | τ Τ tau /t/ | υ Υ upsilon /y/ |
| φ Φ phi /pʰ/ | χ Χ chi /kʰ/ | ψ Ψ psi /ps/ | ω Ω omega /ɔː/ (long o) | |

**Hand notes (ductus):** α as a single anticlockwise loop + tail; θ as a circle with a centre bar;
ξ and ζ are the hardest — practise the three-stroke descent. ς only at word-end (μῆνις → genitive μήνιος).

**Polytonic marks (the breathings & accents — Homer is fully accented):**
- Breathings on initial vowels/ρ: ᾽ smooth (no /h/) · ῾ rough (adds /h/). `Ἀχιλεύς` smooth; `ἕκτωρ`→`Ἕκτωρ` rough = "Hektor".
- Accents: ´ acute · ` grave · ˜ circumflex (pitch in origin). `μῆνιν` carries a circumflex on the long η.
- Iota subscript ᾳ ῃ ῳ (a silent ι written beneath long vowels). Copy these faithfully — they mark case.

---

## Layer 2 — Glossed reading (decode the line)

The opening of the Iliad — copy it by hand, then work the gloss. (This is the gold-standard daily unit.)

```
μῆνιν   ἄειδε   θεὰ   Πηληϊάδεω   Ἀχιλῆος
mēnin   aeide   thea  Pēlēïadeō    Achilēos
```
| word | translit | gloss |
| --- | --- | --- |
| μῆνιν | mēnin | **wrath** — accusative sing. (the object: "the wrath"; first word of the poem) |
| ἄειδε | aeide | **sing** — present imperative ("sing!") |
| θεά | theā | **goddess** — vocative ("O goddess", the Muse) |
| Πηληϊάδεω | Pēlēïadeō | **of the son of Peleus** — patronymic, genitive (Homeric -εω = -ου) |
| Ἀχιλῆος | Achilēos | **of Achilles** — genitive sing. (Homeric for Ἀχιλλέως) |

- **Literal:** "The wrath sing, goddess, of Peleus' son Achilles —"
- **Literary:** "Rage — sing, goddess, the rage of Achilles, son of Peleus"

**Method:** the corpus holds the Greek + four English translations (Butler · Pope · Lang · Cowper). Read
the Greek aloud, copy it, gloss each word, then COMPARE how the four translators render `μῆνιν` (wrath /
anger / rage) — translation is where the book becomes an encounter.

**Homeric formulae to recognise on sight** (they recur thousands of times):
- `πόδας ὠκὺς Ἀχιλλεύς` — "swift-footed Achilles" (epithet + name, fills the line-end)
- `ἔπεα πτερόεντα` — "winged words"
- `οἴνοπα πόντον` — "the wine-dark sea"
- `ῥοδοδάκτυλος Ἠώς` — "rosy-fingered Dawn"
- `κορυθαίολος Ἕκτωρ` — "Hector of the flashing helm"

---

## Layer 3 — Serious grammar (toward unaided translation)

Minimal orientation; expand as you go (recommended companion: Pharr, *Homeric Greek*).
- **Nouns decline** in 5 cases (nom./gen./dat./acc./voc.) × 3 genders × sing/dual/plural. Word ORDER is
  free because the ENDING carries the role — `μῆνιν` is the object because of `-ιν`, wherever it sits.
- **First declension** (ā/ē-stems, mostly fem.): θεά, θεᾶς, θεᾷ, θεάν, θεά.
- **Verbs** conjugate for person/number/tense/mood/voice. `ἄειδε` = 2nd-sg present imperative active.
- **Homeric dialect** quirks vs. Attic: genitive -οιο/-εω, dative pl. -οισι/-ῃσι, uncontracted vowels
  (ἀείδω not ᾄδω), the augment often dropped. Expect them; they are features, not errors.

Daily grammar drill: take the day's line, parse ONE word fully (part of speech · case/tense · why),
and write the rule it illustrates in your ledger.

---

*Source rails:* Perseus / Scaife (Greek text + morphological parser, hover any word) ·
the local corpus `classical/iliad/greek_original.txt` (+ 4 translations to compare).
