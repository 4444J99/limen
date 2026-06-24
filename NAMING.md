# NAMING — the styling canon

*Stylings for titles, product names, and domains. Minimalist, but not bare: we
reach for the **earlier, undivided form** of each letter — its prima materia —
not for decoration.*

---

## The principle

`U`, `J`, and `W` are all **later splits**. Classical Latin had 23 letters and
none of them: `V` was both vowel and consonant, `I` was both vowel and
consonant, and `W` did not exist — it was built by doubling `V`. So:

- `u = v`
- `j = i`
- `w = vv`

are not tricks. They are the alphabet before the medieval differentiation —
the ideal form of the letter, before it was cut in two.

Everything below follows from that one principle, plus one hard constraint:

> **Nothing here may break the terminal, Finder, or a domain.**
> ASCII only. No characters that need shell-quoting. No Unicode that DNS strips.

There are two tiers. **Substitutions** survive *everywhere* — including the
domain. **Layout** lives only in the rendered wordmark; DNS drops it.

---

## Tier 1 — substitutions (survive into the domain)

DNS lowercases and allows only `a–z 0–9 -`. Any pure letter-for-letter swap
reaches the URL intact.

| Swap | Rule | Why (the real history) | Example |
|---|---|---|---|
| **U → V** | every `u` → `v` | one letter `V` served `/u/` and `/v/`; `U` is medieval | `STVDIVM`, `VLTIMA` |
| **J → I** | every `j` → `i` | `J` is a 16th-c. split off `I` (Trissino, ~1524) | `IANVS`, `IVLIVS`, `MAIOR` |
| **W → VV** | `w` → `vv` | literally "double-V"; absent from Latin | `VVYRD` |
| **QU → QV** | follows from U=V | Romans wrote `AQVA`, `QVINTVS` | `QVICKEN` |
| **G → C** | *(archaic)* `g` → `c` | oldest Latin had no `G`; `C` did both `/k/` and `/g/`. Preserved in `C.`=Gaius, `Cn.`=Gnaeus | `CAIVS` |
| **K before A** | *(archaic)* `ca` → `ka` | Old Latin `KALENDAE`, `KAPVT`; `C` later displaced it | `KALENDA` |
| **AE / OE** | spell digraphs out | classical `ae/oe`; the ligatures `æ/œ` **break ASCII** — use two letters | `CAESAR` not `CÆSAR` |
| **Y, Z** | keep, as Greek markers | borrowed from Greek (`Y` = *i graeca*), appended to the alphabet, used only in Greek roots — their rarity is itself a signal | `STYX`, `ZEPHYR` |

---

## Tier 2 — layout (wordmark only; domains drop it)

- **ALL CAPS** — *capitalis monumentalis*. Lowercase (minuscule) is Carolingian
  (~8th c.); "carved in stone" is uppercase. Free in domains (case-insensitive),
  meaningful in the mark.
- **Scriptio continua** — no word spaces (ancient running script). Automatic in
  domains, which cannot hold spaces anyway.
- **Roman numerals** — `I V X L C D M` for editions/versions: `STVDIVM IV`.
- **Interpunct `·`** — the genuine Roman word-divider (`SENATVS·POPVLVSQVE`) —
  but **not** terminal/Finder-safe. The honest ASCII fallback is the period `.`,
  which conveniently *is* the domain separator.

---

## Avoid — these break the terminal, Finder, or domain

| Don't | Use instead | Why |
|---|---|---|
| `æ` `œ` | `AE` `OE` | not ASCII |
| `·` | `.` or `-` | not terminal/Finder-safe |
| `&` | `ET` | genuinely the *et*-ligature, but shells/URLs treat it as an operator |
| `þ ð ƿ ſ` | — | medieval Germanic / early-modern; not ASCII |
| `ā ē ī ō ū` (macrons) | bare vowel | not ASCII |
| `Λ Σ Φ` (Greek letters) | romanize (`L S PH`) | not ASCII |

---

## Registers — pick a depth, keep it pure per name

1. **Classical / Augustan** *(default)* — `U→V, J→I, W→VV, QU→QV`, AE/OE
   digraphs, all caps. Clean, still readable. **`VLTIMA` is exactly this.**
2. **Archaic / Old Latin** — also `G→C` and `K` before A. Heavier, more cryptic,
   "pre-G" feel.
3. **Greek-inflected** — `K` over `C`, keep `Y/Z`, `KH/PH/TH` for χ/φ/θ,
   `-OS/-ON` endings. For names that should read as Greek-rooted (fits `STYX`).

Mixing registers in one name dilutes both. Numeronym / leet (`4=a`, as in
`etceter4`) is a **fourth, modern** tradition — ASCII-safe, but keep it out of a
classical mark unless the mix is the point.

---

## Worked examples — our vocabulary

| Name | Classical mark | Domain-safe label |
|---|---|---|
| LIMEN | `LIMEN` | `limen` — already prima materia; nothing to strip |
| STUDIUM | `STVDIVM` | `stvdivm` *(two u's → two v's)* |
| QUICKEN | `QVICKEN` | `qvicken` |
| ULTIMA | `VLTIMA` | `vltima` |
| STYX | `STYX` | `styx` — Greek; leave it |

**Domain reality check:** only Tier 1 reaches the URL — `studivm.com` works,
`vvyrd.com` works — while caps, spacing, numerals, and interpunct live only in
the rendered wordmark. A product can carry the full monumental treatment on the
page (`STVDIVM · IV`) and still resolve at a clean `stvdivm.com`.

---

## How to apply (for the fleet)

When minting a title, product name, or domain:

1. Default to **Classical / Augustan**. Apply Tier 1 swaps.
2. The **domain** is the Tier-1 form, lowercased: `studivm.com`.
3. The **wordmark** may add Tier 2 (caps, interpunct→`·`, numerals).
4. Never emit a character from the **Avoid** list into a path, URL, or shell arg.
5. One register per name. Don't mix classical with leet.
