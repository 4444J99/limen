# apps/danse — agent contract

Directory-scoped, and deliberately short. The repo root `AGENTS.md` owns the dispatch/task
contract, task states, and the Peer Conductor Contract; **this file owns only what is true inside
`apps/danse/` and cannot be derived by reading the code.** Where the two disagree, root wins.

Read this before touching anything under `apps/danse/`. It is written for any harness — Claude
Code, Copilot, OpenCode, Codex, Cursor, Aider, a human — because none of the knowledge below
lives in one agent's session.

---

## 1. The one command

```bash
python3 scripts/check-danse.py        # 39 portable invariants · ~0.2 s · python3 + node · no GPU
```

Exit `0` ⟺ the engine still is what it claims to be. It is registered in
[`institutio/governance/gates.yaml`](../../institutio/governance/gates.yaml) as **`danse-invariants`**,
so you get it for free two ways and do not have to remember it:

- `scripts/verify-scoped.sh` selects it on any `apps/danse/**` diff (the repo's default push gate)
- the always-on `pr-gate` workflow runs it on **every** pull request, from any author

That registration is load-bearing. Before it existed, `verify.py --explain apps/danse/engine/clock.js`
selected exactly two gates — file syntax and whitespace — so an agent could rewrite the engine, run
the repo's own gate, get a green exit, and ship a broken piece.

**The count ratchets, and it is split on purpose.** `FLOOR = 39` in `scripts/check-danse.py` counts
the **portable** invariants — the ones that run anywhere. `CONDITIONAL = {"grain bank": 3}` counts
invariants needing a local artifact derived from originals that never enter git.

> **You will see 39 here and 42 on the artist's machine. That is correct, and it is stated by the
> run.** Before the floor existed the total silently shrank from 42 to 39 on CI with nothing said —
> a number that quietly means less depending on where it ran is exactly what an agent should not
> trust. Now an absent group is *named* in the output. **Never lower a floor to make two machines
> agree.** Add a portable check → raise `FLOOR`. Add a conditional one → raise its group's count.

## 2. What is checkable, and where

Half of danse's verification is portable and half is bound to this machine. Knowing which is which
saves you from concluding a check is broken when it is merely refusing to lie.

| What it proves | Command | Runs on |
|---|---|---|
| The 39 portable arithmetic invariants (+3 with a local grain bank) | `python3 scripts/check-danse.py` | **anything** with python3 + node |
| The flat state is still the 2017 composite (**31.60 dB**) | `apps/danse/render/browser.py --verify` | macOS + Google Chrome + Apple Metal **only** |
| Every visitor gets their own river | `apps/danse/render/browser.py --arrival` | same |
| Planes at unrelated angles still read as one room | open `probe.html` | any WebGL2 browser — by eye |

`browser.py` **asserts the GL renderer names Metal and exits rather than proceed** on a software
rasteriser. That is not overcaution: the offline film is 23,400 frames, SwiftShader takes most of a
day to produce a file that is subtly and unfixably wrong, and the only way to find out is to watch
the whole thing at the end. On Linux/CI you cannot run it — say so plainly instead of weakening it.

**You do not need the pipeline to work on the engine.** The corpus is committed (652 files, 324
plates). `pipeline/` regenerates it from Photos.app on macOS against 2.8 GB of originals that are
git-ignored on purpose, and you will almost never need to run it.

## 3. The three claims a refactor must not "simplify"

These are the reasons, not just the rules — a rule without its reason gets optimised away by the
next agent who thinks it is an accident.

**The engine is a pure `f(seed, t)`.** No accumulated state, no `requestAnimationFrame`, no clock
inside `engine/`. That one property is what buys deterministic offline capture, O(1) seek, shareable
permalinks, and multi-projector sync **with no network between the projectors**. An innocent-looking
`let last = performance.now()` in a render loop destroys all four at once, so `check-danse.py` greps
for it.

**Entropy has exactly one home: `arrival.js`.** The check is an equality, not a prohibition — it
fails if a clock or an RNG appears in `engine/`, *and* if one appears anywhere else in the app. That
is what keeps the engine pure while a visitor's arrival still seeds the piece. Put new randomness
there or nowhere.

**The flat state *is* the 25 July 2017 composite, and `verify.html` measures it in dB.** It is the
regression net for every engine change. If a change drops the number, the change is wrong — **never
lower the threshold to make a diff pass.** The measured value is 31.60 dB against a 31.61 dB
arithmetic ceiling, so there is no headroom hiding a fudge.

## 4. Never

- **Never render the piece to a fixed file and call that the work.** It has no duration and no end;
  it traverses a phrase forever and each passage draws its own seed and its own length. A capture is
  a *recording of* the river, named by the passage it caught — never the piece itself.
- **Never let `.work/` into git.** 2.8 GB of 2017 originals. Only the code that regenerates them is
  versioned.
- **`sources.json` stays git-ignored** — it lists thousands of private recordings under a home
  directory, in a repo that publishes.
- **`film.html` must never call `arrive()`.** A capture pins its seed and start explicitly; that is
  exactly what makes it reproducible.
- **Never widen the engine seed past 32 bits.** `sound/rng.py` is held to `engine/rng.js` value for
  value by `check_sound()`, and `hex()` prints the seed as the piece's signature. The 32-bit ceiling
  is stated honestly in the predicate's notes rather than papered over.
- **Never commit to `main`.** Topic branch + PR, and stage explicitly with `git add <path>` — never
  `git add -A`.

## 5. Open work — this component's own record

Per the root charter, each component carries its own residual items rather than parking them in a
session. Nothing here is blocked on anything else here.

| Item | State | Where it lands |
|---|---|---|
| `render/deliver.py` speaks the **pre-river** vocabulary (`windows`, `t0/t1`, a fixed `master`) | re-fitted to captures + `--start` per `danse.program.v2` | passage-caught outputs & capture spans |
| ScreenDance 2027 package | `attest.yaml` staged, pending full artifact generation | `check.py` must exit 0 once all renders complete |
| The title | **confirmed** as `THE THING WITHOUT A NAME` in `program.json` | done |
| `bio` / `rights_declaration` | claims **about a person** | only he can verify them — do not invent or infer |
| Fleet homing / publishing | `chambers/danse.yaml`, `deploy_triggers.danse`, and `.github/workflows/deploy-danse.yml` staged | done |
| `join.html` / MediaPipe — a visitor's own body entering the corpus | deferred past the submission | `#name=` in `arrival.js` is the shipped cheap slice; part of final evolution (a) user interaction |
| Spatial sound triggering | final evolution (b) concept | sound from the space triggered by each panel/slice generation across background XY axes |
| The room / installation spec | lives only in a plan file | wants a home in the repo |

**Dates and specs are owned by [`submission/screendance-2027.yaml`](submission/screendance-2027.yaml),
which is checked.** Read them there. That register's own header forbids carrying them in prose, so
this file deliberately restates none of them — if you need the deadline, the runtime, or the codec,
query the register.

## 6. Run it

Pure static. No build step, no dependencies, no tokens, no env.

```bash
cd apps/danse && python3 -m http.server 8080
```

- `/` — the living page. A bare URL mints your own river and puts it in the address bar.
- `#s=<seed>&e=<epoch>` — someone else's river, joined live and in sync.
- `#s=<seed>&t=<seconds>` — one moment, cited.
- `#s=20170620` — the archival river, from its source.
- `probe.html` · `verify.html` · `studio.html` — the projection go/no-go, the reproduction
  measurement, the seed browser.

[`README.md`](README.md) is the piece explained — what it is, what the corpus turned out to be, and
how the 2017 composite was solved back into a score. Read it for intent; read this file for rules.
