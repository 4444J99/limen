# organvm design tokens

The estate design language — one living system, not one skin. The **portfolio**
(`organvm/portfolio`) leads the aesthetic: its gold accent, system-font type
direction, and Fibonacci spacing are the primitives here. Limen's dashboard
signal colors and MONETA's editorial ink/paper register are mapped *onto* those
primitives, never set beside them.

- **`organvm-tokens.css`** — three layers: primitives → semantic aliases
  (`--surface-bg`, `--ink`, `--accent`, `--ok`/`--warn`/`--err` …) →
  `[data-register="utility"|"editorial"]` scopes. Dark mode and registers remap
  ONLY the semantic layer; both registers resolve from the same primitives.
- **`organvm-tokens.json`** — the machine twin and **SSOT** future drift checks
  read. Same values, structured (`primitive` / `semantic` / `register`).

**Vendoring adoption rule.** Each surface keeps a **pinned copy** of the CSS
(committed into that surface), then remaps its own surface variables onto the
semantic aliases — e.g. dashboard `--panel: var(--surface-panel)`. **Never a
runtime fetch** across surfaces (no coupling, no network dependency); a token
change reaches a surface only when that surface re-pins its copy.

**Estate-wide adoption is gated on the owner sign-off lever `L-TOKENS-SIGNOFF`**
(`his-hand-levers.json`). Until approved, these files exist and validate but no
surface adopts them; after approval, adoption PRs are mechanical.
