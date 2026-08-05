# VOX Program — Macro-Verification Receipt

**The signed verdict surface for `spec/vox-program.md` §2 (pre-dispatch gate) + §4 (macro review).**
`scripts/vox-verify.py` parses the machine-readable verdict block below, requires every gate to be
`pass` or `pass-with-note`, and **drift-guards** each mechanically-checkable gate against its own
re-computation (if a verdict here says `pass` but the code check is red, that is a hard failure — the
code wins). The judgment gates (2, 5, macro) and the cross-repo floor of gate 3 were established by a
read-only multi-agent verification pass; the mechanical gates (3-lane, 4, 1-floor) are re-derived by
the predicate at run time.

**Verified:** 2026-07-10 · **By:** limen dispatch macro-verification pass (3 read-only reviewers +
predicate) · **Program:** VOX-0…VOX-5 + VOX-META across `organvm/vox`, `organvm/in-my-head`,
`organvm/universal-mail--automation`, `organvm/limen`.

<!-- vox-verify:verdicts
gate1_precedence: pass
gate2_organ_boundaries: pass
gate3_credential_protocol: pass
gate4_naming: pass
gate5_single_contract: pass-with-note
macro_sibling_collision: pass
-->

## Gate 1 — AGENTS.md precedence + lifecycle + his-hand → **pass**

No account-creation / login step is encoded as a dispatchable code task in any of VOX-0…VOX-5 or
VOX-META; every credential need is routed to the credential protocol (a `creds-hydrate` lane) or a
human lever, never a chat/code task. Explicit protocol statements in the task contexts: VOX-0 "owns no
accounts"; VOX-1 "no ElevenLabs login UI"; VOX-3a "no Twilio/Gmail OAuth in vox"; VOX-3b "reuse
existing `gmail_auth.py` — no new credential code, no ElevenLabs account creation"; VOX-4 "register
ElevenLabs — value never in repo". Mechanical floor (predicate): every `VOX-*` task carries a status
in the canonical `VALID_STATUSES` set.

## Gate 2 — Organ boundaries (vox core / sign-signal play / mail transports) → **pass**

`organvm/vox` is a pure voice core: `clone_voice` / `synthesize` / `transcribe` / presets, reading
`ELEVEN_API_KEY` from the environment at most. A fleet search found **zero** transport/account code in
vox (`twilio`, `gmail`, `oauth`, `smtp`, `imap` → no results). The Twilio/Gmail transports live only in
`organvm/universal-mail--automation` (`gmail_auth.py`, `providers/gmail.py`); the consumer
`organvm/in-my-head` holds no credential UI. Clean separation.

## Gate 3 — Credential protocol (creds-hydrate; no secret in repo, env-injected) → **pass**

Cross-repo secret sweep: **zero committed secret literals** across all four repos; every sensitive
value is an env read (`os.getenv("ELEVEN_API_KEY")` in vox `synthesizer.py`/`cloning.py`;
`process.env.VOX_API_URL` in in-my-head). The ElevenLabs credential is now registered in limen's
`creds-hydrate.py` `DEFAULT_MAP` (lane `vox (elevenlabs voice clone)` → env `ELEVEN_API_KEY`,
`enabled: False` until the vendor key is minted — the mint atom is homed on issue #898 + the Wall
#320, never recited). Mechanical floor (predicate): the ElevenLabs lane exists in `DEFAULT_MAP` routed
to `ELEVEN_API_KEY`; `credential-wall.py --check` exits 0; no secret shape (`_SECRET_RX` + the
ElevenLabs `sk_`/`xi-api-key` shapes) appears in limen's tracked files.

## Gate 4 — NAMING.md ideal-form derivation → **pass**

Program identifiers (`vox`, `in-my-head`, `ELEVEN_API_KEY`) carry no hard (forbidden) nota. Mechanical
floor (predicate): `nomenclator.py --check "<name>"` exits 0 (no forbidden characters) for each.

## Gate 5 — `vox/types` single-contract rule → **pass-with-note**

The canonical contract is a single module — `vox/profiles.py` (`VoiceCharacteristics`, `VoiceProfile`,
`ReadingStyle`, the 7 presets, the voice enums) — re-exported through `vox/__init__.py` and imported by
every vox consumer (`vox/api/main.py`, tests); `vox/types/index.ts` is a documented TypeScript mirror
of it. **Note (constraint not fully met):** the `organvm/in-my-head` consumer redefines the shapes
locally in `lib/types.ts` — a documented mirror carrying an explicit TODO ("Future: import directly
from the `vox` package") rather than importing the canonical contract. This is a minor, intentional
deviation, filed to the board as **VOX-6** (in-my-head: consume `vox/types` from the package, retire
the `lib/types.ts` mirror) so the constraint is homed with its owner, not lost in prose.

## Macro — sibling-organ collision (§4) → **pass**

VOX (voice cloning/synthesis/transcription for a consumer product) is cleanly distinct from every
sibling organ in `organ-ladder.json`: Carrier-Wave Media (distribution/reach), the Education organism
(learning progression), and MANVMISSIO (inference-spend governance). No speech-scoring or competing
voice organ exists in the registry. Media/education are potential *consumers* of the voice layer, not
overlapping organs.

## Disposition

All gates `pass` / `pass-with-note`; the one open constraint (gate 5) is homed as VOX-6. VOX-META's
macro-verification is therefore complete: predicate + receipt shipped, verdicts recorded, the single
residual constraint filed to its owner. Re-run `python3 scripts/vox-verify.py` to re-assert.
