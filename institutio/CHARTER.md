# VIGILIA — Charter (v0.1, provisional)

*the body keeps its own watch*

> **The name is provisional.** `VIGILIA` is a codename, not a ratification. It is the
> first row of the parameter panel (`governance/parameters.yaml` → `INSTITVTIO_NOMEN`)
> and will be settled later through INDEX·NOMINVM. Even the name is a parameter.

---

## Telos

**One reproducible body that operates a computer on its owner's behalf, unattended —
and keeps itself alive while doing it.**

Not "health." Not "the central bank of a 16 GB machine." This is the *self-keeping layer*
of an AI-operated computer — a thing any operator could install, not a him-specific tool.

## Why now — three faults in eighteen hours, one disease

| Time (2026-06-25) | Fault | Root | Layer |
|---|---|---|---|
| 08:47 | kernel panic | memory-exhaustion livelock → watchdog timeout (compressor 100%, 12 swapfiles, watchdogd starved 92 s) | **VITALS** |
| ~13:42 | session thread lost | auto-compaction (second overflow) handed off a **200-char stub** into the next session | **CONTINUITY** |
| this session | "Claude app is corrupt" dialog | auto-update / code-signature version-path churn (self-recovered; signature valid now) | **INTEGRITY** |

The disease is one, not three: **the body does excellent work but has no organ that keeps
the body itself alive.** The *somatic* system (the `limen` daemon, the agent arms, dispatch)
is mature and strong. The *autonomic* system — the part that keeps you breathing without
thinking — does not exist. A strong worker that crashed the machine, forgot its own thread,
and threw a corrupt dialog, all in one day.

Each fault already had a *diagnosis* and a *lever* on file (`_diagnostics` FIND-005 "16 GB is
a budget, not a floor"; the `DISABLE_AUTOUPDATER` TCC lever; the corpus/session-meta thread).
None had a **hand**. Diagnosis without an executive is what crashed the machine.

## The non-appeasing distinction — federation, not fusion

"They all belong together" is true **at the level of body** — but three different *kinds* of
thing were named together, and fusing them into one repo would recreate the exact scatter
this institution exists to end:

- **ORGANS that run** — `limen`, `_arms`/`agent-all`, `session-meta`, vitals, creds,
  permissions. The living body.
- **The FACE you look through** — `tui`, `portus`, the dashboard. Skin, not an organ.
- **The GENOME you tune** — `configs`, `extensions`, `.env`, the ~70 `LIMEN_*` vars.
  DNA, not an organ.

**One body, one spine, one seat; many organs, each in its own home.** Each owner records its
own residual work (per the closeout charter). The seat *indexes* the somatic organs; it does
not *absorb* them.

## Anatomy

```
VIGILIA — autonomic operation of a reproducible AI-run computer
  telos: meets its own operational needs, unattended, and survives its own faults

  SPINE / GENOME  (connective tissue — not an organ)
    • PARAMETER PANEL — every name/path/threshold/secret-ref = one declared param
      (default + env override + optional self-update), enforced by a no-hardcodes CI gate
    • INDEX·NOMINVM  — naming (already exists)
    • THE SEAT       — the single registry of every organ → legibility ("one place I see it all")

  AUTONOMIC LAYER  (keep-self-alive — the missing system; today's three faults live here)
    • VITALS      mem/cpu/disk/swap   → don't crash        [executive MISSING]
    • CONTINUITY  session thread       → don't forget        [session-meta; failed this session]
    • INTEGRITY   app/binary/signature → don't self-corrupt  [auto-update lever, ungoverned]
    • IDENTITY    creds/secrets/env    → don't re-ask         [creds-hydrate — mostly built]
    • AUTHORITY   permissions/dialogs  → stop asking          [mostly solved]

  SOMATIC LAYER  (do-the-work — already strong; indexed, not absorbed)
    • LIMEN daemon   metabolism / heartbeat / dispatch
    • ARMS / AGENTS  the vendor lanes that act (agent-all, _arms)

  FACE  (how the operator sees & steers)
    • tui / portus / dashboard — one pane onto the seat
```

## Separation of powers (the Censor template, mapped across repos)

No single process both senses and acts.

- **SENSE** — silent, read-only, **no daemon** (Rule #9: "fit the host or become the disease").
  Home: `_diagnostics` sensors (`sysdiag`, `memdiag`, …).
- **LEGISLATE** — publishes the reaction function (thresholds, ladders). Home: this charter +
  `governance/parameters.yaml`.
- **JUDGE** — the six-lens inquiry, assessments, precedents. Home: `_diagnostics/inquiry`.
- **EXECUTE** — *acts*, riding the **already-resident heartbeat** so it adds **no new resident
  process** (honors Rule #9's spirit). Home: `limen` heartbeat.

## Build order (the ideal form dictates the sequence)

0. **THIS PR** — charter + seat (organ registry) + parameter-panel seed. **Legibility first**:
   you cannot keep alive what you cannot see.
1. **The autonomic self-keeping loop** — VITALS + CONTINUITY + INTEGRITY on **one executive**
   (three sensors, one hand). This is the genuinely-missing organ. Rides the heartbeat;
   sheds load / checkpoints the thread / pins the binary *before* a fault becomes a crash.
2. **Fold IDENTITY + AUTHORITY into the seat** — both mostly built; wire the gaps, index them.
3. **The no-hardcodes CI gate** over the parameter panel — the "100×". Turn derive-never-pin
   from a discipline into a gate (like the `nomenclator` name gate).
4. **The face** — `tui`/`portus` rendered from the seat.

## What this does NOT do

- It does **not** absorb the somatic organs (`limen` daemon, arms). It indexes and keep-alives them.
- It does **not** add a resident process. The executive rides the existing heartbeat.
- It does **not** finalize the name. `INSTITVTIO_NOMEN` is provisional, pending INDEX·NOMINVM.
- It does **not** rebuild what exists. The excavation verdict is *consolidation, not rebuild*.

## Provisional home

This seat is provisionally housed in `limen/institutio/` (adjacent to the heart, where the
executive will be wired) **pending ratification** of its own dedicated repo. The repo home is
itself a parameter (`INSTITVTIO_HOME`) — git history is portable; extracting to its own seat
later is a clean `subtree`, not a rewrite.
