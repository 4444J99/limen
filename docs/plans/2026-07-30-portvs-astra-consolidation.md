# THE PLAN — PORTVS / ASTRA / THE LIBRARY / THE UNDERWORLD

Composed with the other live session's shipped law: **Custody v4.0.0 — the Storefront and the
Shelves** (`plans/tranquil-spinning-possum.md`; Phase 1 executed — ten partner transfers fired
and verified; Phase 2 in flight — shelf tranches, ERGON's 51 first). That session owns GitHub
custody. This session owns the vertical: spine, jack-in, rename, domains, local cleanup, and the
hot flash cache. The two evolve together; neither collides with the other's lane.

## Decisions made for the operator (veto any in one word)

1. **limen → `astra`** — "AS-truh," Latin for the stars: his own solar-system metaphor, *per
   aspera ad astra*. Limen is dead (his veto — "lie-men"). Fallback: `stratvm` (verified free).
2. **PORTVS exists — converge on it, don't rebuild.** `organvm/portvs` is live; `~/_portal`
   already points where its clone belongs. A second portal is the named failure mode.
3. **SVBTERRANEA is a stratum, not an org.** The venture law (new org only for an external party
   with independent standing) kills the new-org idea. The underworld = repos archived in place
   (grayed, sunk, reversible) + the private estate-ledger repo holding drive manifests and
   archive receipts.
4. **The audience split.** Every storefront repo — partner estate AND totally-solo work —
   declares `audience: world | collab | self` as registry data in `estate.yaml`:
   - `world` — "me and the world": public, solo. The showcase lane.
   - `collab` — "me and collab": private repo, collaborator invited. Shared inside, invisible
     outside.
   - `self` — private, nobody else. Engine-room default.
   The custody doctor enforces GitHub-visibility parity (`world` ⟺ public; `collab` ⟺ private +
   collaborator granted; `self` ⟺ private, no outside access). Never a hand list.
5. **The Meeseeks law — local is a hot flash cache.** Every summoned surface (worktree, agent
   runtime, scratch clone, session branch, fan-out agent) is born for one purpose, executes,
   **returns its result to source** (push + receipt), and self-erases. Residue is a defect
   caught by predicates — `verify-hot-cache.sh`, retention sensors, the reclaim organ, the
   workspace-manifest gate — never a periodic cleanup chore. Source of truth is always upstream.
6. **Domains live in persistent directories, never worktrees.** Persistence is for the
   *domains*; the Meeseeks law governs everything summoned around them.
7. **Nothing deleted from GitHub — archived or transferred only** (all reversible).

## The library (custody end-state — the other session's law, already firing)

- **Storefront** `4444J99` (~14), split by audience: world lane (map README, 6 pins, name-site,
  flagship solo repos) / collab lane (partner estate, private + invited).
- **Eight shelves** (~120 public forms): I-THEORIA ~11 · II-POIESIS ~17 · III-ERGON ~51 ·
  IV-TAXIS ~16 · V-LOGOS ~2 · VI-KOINONIA ~9 · VII-KERYGMA ~5 · meta-organvm ~10.
- **Engine room** `organvm` (~95, never advertises): PORTVS, ASTRA (née limen), DOMUS-GENOMA,
  pipelines, vaults, fleet state.
- **Underworld**: archived-in-place forks/copies/dead + estate-ledger.

Nobody faces 300 again: a screener walks the storefront, opens a themed shelf; the engine room
never advertises.

## Division of labor (two sessions, one evolution)

- **Possum session** (live, goal-hooked): storefront phase, shelf population tranches, archive
  reap, custody doctor, estate.yaml `organ:` field. Its worktree and uncommitted estate.yaml are
  UNTOUCHABLE from here.
- **This session**: ARCs 1–5 below. The audience field (decision 4) is *proposed through their
  registry machinery* — a PR adding the `audience:` column + doctor rung to the same estate.yaml
  pipeline, sequenced after their in-flight tranche commits, never a parallel registry.

## Why it kept not-landing (census ground truth, 2026-07-30)

- Main checkout **10 commits behind** — the shipped root-defat never landed on his disk.
- **13.5 GB of limen invisible to git**: agent runtime 9.8 G, a 906 MB backlog dump, 1.1 G
  session worktrees, a nested repo 17-dirty/12-behind.
- **Dotfile spine broken**: chezmoi points at a stub; the real clone is buried inside limen; ten
  home symlinks point at a missing cartridge.
- **1Password storm = one bug**: one `op read` per credential. A single `op inject` pass = one
  biometric prompt total.
- **A screener sees 9 repos, not 308** — the wall hides behind the org; the possum session's
  shelf population is the fix, already in motion.
- **Nothing is version-pinned anywhere**; mise installed, unconfigured — dynamic summoning is
  configuration, not invention.

## ARC 1 — Repair the spine (first; everything depends on it)

Fast-forward the checkout. Un-nest domus-genoma to `~/Workspace/domus-genoma`, retire the stub,
repoint chezmoi, `chezmoi apply` — broken symlinks regenerate or die (predicate:
`scripts/chezmoi-drift.py` green). Clone portvs where `~/_portal` expects it. Rewrite credential
hydration to one `op inject` pass — **one Touch-ID prompt total**, `--verify` preserved, never
unattended. Configure mise with version *ranges*, not pins. Ship **`verify-hot-cache.sh`**:
exit 0 ⟺ this machine is disposable (every repo pushed, dotfiles clean, creds valid, manifests
fresh) — the Meeseeks law's court, beat-wired via a sensors.yaml row.

## ARC 2 — PORTVS becomes the jack-in

`portvs/jack.sh`: ONE command on a bare machine → tools (gh, chezmoi, mise, op, uv) →
`chezmoi init --apply organvm/domus-genoma` → `mise install` → creds hydrate (one prompt) →
clone the manifest-declared set → `verify-hot-cache`. That script IS the matrix jack. PORTVS
also carries the **map of the law** — an index of where every rule lives (naming, semver,
routing, labeling; custody registry = *their* `estate.yaml`, pointed at, never copied) —
deferring to AGENTS.md for protocol.

## ARC 3 — The rename (limen → astra)

GitHub rename (history/stars/redirects preserved). `astra` CLI with a `limen` compat shim;
tap + install.sh (fix its wrong-org bug day 0); Worker rename staged. `LIMEN_*` parameters get
an alias layer accepting both prefixes forever — internals migrate opportunistically.

## ARC 4 — Domains = persistent directories

`~/Workspace/domains/<domain>/` for the nine life-domains — persistent clones on the
never-prune list + reclaim exclusions. The streams launcher routes domain rows there
(`residency: persistent` row field); the 6 existing domain worktrees migrate; `_*-private`
stores become each domain's data interior.

## ARC 5 — Local cleanup = Meeseeks enforcement (receipts for every byte)

Quick wins: empty dirs + the literal `~` dir (quoted absolute path only), zero-byte tmp, the
duplicate clone (verify-pushed predicate → quarantine). Limen de-bulk: retention caps on
`.agent-runtime` (beat-enforced), the 906 MB dump + loose peer-audit files
archive-to-Archive4T-then-delete (human-gated), caches cleared; `.venv` NEVER touched
(mail-organ interpreter); browser-state quarantined uninspected. Worktrees: 32 → live-set-only
through the existing reclaim organ; ONE canonical internal root. Workspace root: 20 loose files
routed to owners; dated residue archived; then the **workspace-manifest gate** — junk cannot
silently return, the return-to-source half of the summoning contract. Drives: manifest + an
owned stream row only; Ingress designated the clean landing zone.

## ARC 6 — dissolved into the possum session

GitHub estate separation, shelf population, archive reap, pins/READMEs/presentation: **theirs,
already in flight** — this plan defers entirely. Remaining here: the estate-ledger repo
(underworld receipts), and the `audience:` field PR routed through their machinery (see
division of labor).

## Order & proof

ARC 1 → then 2/3/4 (parallel-safe) → 5 alongside. Every change ships as PRs through existing
gates (`verify-scoped.sh`, merge-policy). Done = `verify-hot-cache` + `no-tasks-on-me.sh` +
`credential-wall.py --check` all green — the idempotent fixed point: summoned, executed,
returned to source, no residue.

## Receipts — ARC 1 spine repair, executed 2026-07-30

```jsonl
{"ts":"2026-07-30","action":"prune-dangling-symlink","path":"/Users/4jp/bin","target":"/Users/4jp/Workspace/.home-cartridge/bin","reason":"home-cartridge migration relic; target absent; not chezmoi-managed"}
{"ts":"2026-07-30","action":"prune-dangling-symlink","path":"/Users/4jp/bound","target":"/Users/4jp/Workspace/.home-cartridge/bound","reason":"home-cartridge migration relic; target absent; not chezmoi-managed"}
{"ts":"2026-07-30","action":"prune-dangling-symlink","path":"/Users/4jp/Code","target":"/Users/4jp/Workspace/.home-cartridge/Code","reason":"home-cartridge migration relic; target absent; not chezmoi-managed"}
{"ts":"2026-07-30","action":"prune-dangling-symlink","path":"/Users/4jp/data","target":"/Users/4jp/Workspace/.home-cartridge/data","reason":"home-cartridge migration relic; target absent; not chezmoi-managed"}
{"ts":"2026-07-30","action":"prune-dangling-symlink","path":"/Users/4jp/Developer","target":"/Users/4jp/Workspace/.home-cartridge/Developer","reason":"home-cartridge migration relic; target absent; not chezmoi-managed"}
{"ts":"2026-07-30","action":"prune-dangling-symlink","path":"/Users/4jp/docs","target":"/Users/4jp/Workspace/.home-cartridge/docs","reason":"home-cartridge migration relic; target absent; not chezmoi-managed"}
{"ts":"2026-07-30","action":"prune-dangling-symlink","path":"/Users/4jp/Obsidian Vault","target":"/Users/4jp/Workspace/.home-cartridge/Obsidian Vault","reason":"home-cartridge migration relic; target absent; not chezmoi-managed"}
{"ts":"2026-07-30","action":"prune-dangling-symlink","path":"/Users/4jp/pets","target":"/Users/4jp/Workspace/.home-cartridge/pets","reason":"home-cartridge migration relic; target absent; not chezmoi-managed"}
{"ts":"2026-07-30","action":"prune-dangling-symlink","path":"/Users/4jp/System","target":"/Users/4jp/Workspace/.home-cartridge/System","reason":"home-cartridge migration relic; target absent; not chezmoi-managed"}
{"ts":"2026-07-30","action":"prune-dangling-symlink","path":"/Users/4jp/tools","target":"/Users/4jp/Workspace/.home-cartridge/tools","reason":"home-cartridge migration relic; target absent; not chezmoi-managed"}
{"ts":"2026-07-30","action":"quarantine","path":"/Users/4jp/Workspace/.domus-genoma-stub-20260730","reason":"uv-cache dump squatting chezmoi sourceDir; moved aside"}
{"ts":"2026-07-30","action":"un-nest","path":"/Users/4jp/Workspace/domus-genoma","from":"/Users/4jp/Workspace/limen/domus-genoma","branch":"master@origin"}
{"ts":"2026-07-30","action":"clone","path":"/Users/4jp/Workspace/4444J99/portvs","repo":"organvm/portvs"}
```

Landed the same day: PR #1680 (one-prompt op-inject batch), PR #1681 (hot-cache spine: mise.toml + verify-hot-cache.sh + sensor), domus-genoma edb4737d (global mise config), organvm/domus-genoma#359 (cartridge reconcile owner).
