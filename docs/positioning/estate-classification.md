# Estate Classification — Method and Strategic Summary

Repository-level classification of the GitHub estate, per the reconciliation mandate: automated
inventory first, deep inspection of the highest-signal candidates, explicit confidence and
coverage. Companion to `docs/positioning/claims-ledger.md`.

Census baseline: 313 repositories (235 public / 78 private) at 2026-08-08T19:14Z
(`docs/github-estate-census.json`). Live sweep 2026-08-09: 309 repositories (235 public / 74
private) — drift of 4 private repos between observations, recorded here rather than averaged.
Private repositories are counted analytically only; their names and contents are never disclosed
on public surfaces.

## Method

Two orthogonal axes, applied per-repository.

**Authorship classes:**
1. Original (manual).
2. Agent-generated under the owner's architecture and direction.
3. Substantially transformed fork.
4. Light fork.
5. Human collaboration.
6. Mirror / archive / template / infrastructure.

**Product states:**
1. Live with demonstrated use.
2. Deployed but adoption unvalidated.
3. Working prototype.
4. Code-complete but undeployed.
5. Specification or pilot package.
6. Design or concept.
7. Internal infrastructure.
8. Archived / abandoned / superseded.

The automated pass classifies by API metadata (fork flag, archived flag, template flag, size,
homepage, language, name patterns). Metadata cannot distinguish original-manual from
agent-directed authorship (that distinction requires commit forensics), nor "deployed" from
"actually serving" (three Pages sites report `built` yet serve 404 — see ledger §3). Those
distinctions are made only for deep-inspected repositories.

## Automated inventory (309 live estate repos, 2026-08-09)

| Bucket | Count | Notes |
|---|---:|---|
| Forks (light or transformed — per-repo diff needed to split) | 29 | 9.4% of estate |
| Archived | 71 | 23% — honest archive tier, already suppressed |
| Templates / infrastructure-patterned | ~20 | `.github`, registries, profile repos, meta-* |
| Homepage-bearing (deploy *intended*; liveness unvalidated) | ~115 | Overlaps other buckets; 3 known-404 |
| Small (<100KB, spec/concept-class) | ~30 | |
| Working-code, state needs inspection | ~71 | The long tail |
| Top languages | Python 112, TypeScript 48, HTML 24, JS 17, Shell 15 | |

**Strategic picture:** roughly a quarter of the estate is already honestly archived; under 10% is
forked; the productive core is ~200 original/agent-directed repositories of which a small number
carry nearly all external signal (stars/forks concentrate in 3 repos) and an even smaller number
are verifiably operating.

## Deep-inspected set (high-signal candidates)

| Repository | Authorship | Product state | Evidence anchor |
|---|---|---|---|
| `organvm/limen` | Agent-directed under owner architecture (3,678 owner commits + bot lanes) | **Live with demonstrated use** (internal): public dashboard receipts — 3,111 tasks / 1,357 done since 2026-05-31 | dashboard + worker `/health`, observed 2026-08-09 |
| `organvm-iv-taxis/a-i--skills` | Original/agent-directed | Deployed; **highest external signal** (15★/7F, external stargazers verified) | live repo |
| `organvm-iii-ergon/public-record-data-scrapper` | Agent-directed | Working prototype→deployed; 4 implemented state collectors (CA/TX/FL/NY), 50-state architecture; 3,399 asserted tests; 7★/6 external forks incl. one company | repo + fork graph |
| `organvm-iii-ergon/a-i-chat--exporter` | Agent-directed | Deployed (install page 200); ~170 tests / 5 formats / 9 locales repo-asserted; usage claim unverified | ledger §2 |
| `organvm-iii-ergon/agentic-titan` | Agent-directed | Working prototype; 5★/2F | repo |
| `moneta` (in `organvm/limen`) | Agent-directed | **Live** (`mint.4444j99.dev` 200); revenue capability, no verified sales | live HTTP |
| `styx` | Agent-directed | Code-complete; 1,107 asserted tests; no adoption evidence | repo assertion |
| `universal-mail--automation` | Agent-directed | Working prototype; 400+ asserted tests | repo assertion |
| `your-fit-tailored` | Agent-directed | **Specification/pilot package** (no runtime) | repo inspection |
| `organvm-vii-kerygma/portfolio` | Agent-directed | Deployed + live (200 at kerygma URL + Netlify mirror) | live HTTP |
| `4444J99/peer-audited--behavioral-blockchain` | Agent-directed | Working prototype (large TS codebase) | repo |

## Confidence and coverage

- Automated metadata pass: **100% of 309 live repos** (fork/archived/template/size/homepage).
- Deep inspection (authorship + true product state): **11 repositories** — the entire top of the
  external-signal and operational-evidence rankings, plus every repository named in positioning
  seeds. Confidence in flagship selections: high.
- Remaining ~200 productive-core repos: classified by metadata only; authorship split
  (original-manual vs agent-directed) not yet performed per-repo. Confidence: medium for
  bucket-level counts, low for any per-repo claim. This is sufficient for the strategic picture;
  a full per-repo authorship ledger is proof-program work (see
  `docs/positioning/proof-production-program.md`), not a blocker for positioning.

## Classification rules going forward

- A repository claims "live with demonstrated use" only with a dated liveness receipt (HTTP 200 /
  health endpoint / dashboard metric) — the Pages "built" API status is not liveness (three
  counter-examples on record).
- "Deployed" without usage evidence is stated as "deployed; adoption unvalidated."
- Authorship is described per the terminology policy
  (`docs/positioning/authorship-disclosure-policy.md`); "solo-built" is never used.
- Archived repositories stay archived — they are the honest Level-3 archive tier, not debt.
