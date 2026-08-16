# Milestone 2 Investigation: Worktree Initialization Architecture & Transactional Procedure

**Agent**: `teamwork_preview_explorer_m2_2`  
**Working Directory**: `/Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_m2_2`  
**Milestone**: Milestone 2 — Worktree Isolation & Topic Branch Setup  
**Date**: 2026-08-15  

---

## 1. Observation

### 1.1 Architecture & Contract References
- **`docs/architecture/worktree-initialization.md`**: Defines `limen.worktree_initialization.v1` as a 5-step transactional protocol:
  1. Staging root resolution and creation (`state=staging`).
  2. Staging root validation (HEAD, branch, index tree vs HEAD tree, clean diffs, zero untracked paths).
  3. Proving same filesystem (`st_dev`), recording `state=moving`, and atomic rename into final destination.
  4. Git worktree backlink repair (`<gitdir>/gitdir`) and re-validation at final root.
  5. Publication (`state=published`) upon final validation passing.
  - Crash safety: Journal lives in `$GIT_COMMON_DIR/limen-worktree-initialization/<key>.json`. Never invokes reset, clean, or recursive deletion on failure (`state=crashed`).
- **`cli/src/limen/worktree_initialization.py`** (lines 16–285):
  - `WORKTREE_INITIALIZATION_SCHEMA = "limen.worktree_initialization.v1"`
  - `initialize_worktree(repo: Path, final_path: Path, *, branch: str, checkout_ref: str, task_id: str, phase_hook: PhaseHook | None = None)`
  - Phases: `preflight` -> `add` -> `validate-staging` -> `move` -> `validate-final`
  - Validations in `_validate_checkout`:
    - `head == expected_head`
    - `symbolic-ref == branch`
    - `git write-tree == git rev-parse HEAD^{tree}`
    - `git diff --cached --quiet HEAD` (returncode 0)
    - `git diff --quiet` (returncode 0)
    - `git status --porcelain=v1 -z --untracked-files=all` (empty output)
- **`cli/src/limen/workstream_contract.py`** (lines 29–60, 1367–1567):
  - Schema constants: `SCHEMA = "limen.workstream.contract.v1"`, `SCHEMA_V2 = "limen.workstream.contract.v2"`, `RECEIPT_SCHEMA = "limen.workstream.receipt.v1"`, `IDENTITY_SCHEMA = "limen.workstream.capsule-identity.v2"`.
  - Subcommands: `normalize`, `configure`, `configure-successor`, `successor-metadata`, `validate-codex-sandbox`, `validate-codex-launch`, `admit`, `sync-receipt`, `validate-receipt-metadata`, `sync-identity`, `verify-identity`, `admit-identity`, `run-bounded`.
  - Module manifests:
    - Identity Modules (8): `README.md`, `manifest.md`, `workstream.json`, `workstream-contract.py`, `intent.md`, `runtime.md`, `closeout.md`, `kickstart.sh`.
    - Receipt Modules (9): 8 identity modules + `capsule.identity`.
- **`scripts/start-worktree-session.sh`** (lines 107–111, 738–780, 806–816):
  - `VALID_BRANCH_PREFIXES="work feat fix heal chore docs refactor"` (default: `work`).
  - Git exclusion setup: Ensures `.worktrees/` and `.limen-workstream/` are written to `.git/info/exclude`.
  - Calls `render_workstream_capsule` from `scripts/lib/workstream-capsule.sh`.
- **`scripts/lib/workstream-capsule.sh`** (lines 1321–2203):
  - Renders `.limen-workstream/` capsule inside worktree.
  - Implements concurrency locking via `fcntl.flock` on `.limen-workstream/.capsule.lock`.
  - Computes invocation hash `input_digest` and binds it into `.limen-workstream/capsule.identity`.
  - Synchronizes and validates `docs/continuations/<slug>/workstream.json` tracked receipt.

### 1.2 Live Topology in `/Users/4jp/Workspace/`
- Command `git -C /Users/4jp/Workspace/limen worktree list` shows:
  - `/Users/4jp/Workspace/limen` (branch `main` @ `9c8a87215`)
  - `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-proof-architecture` (branch `codex/psp-omega-lane-proof-architecture` @ `77d1069de`)
- Active directory inspection of `/Users/4jp/Workspace/.worktrees/`:
  - Contains `limen-psp-omega-lane-proof-architecture` (active Git worktree, clean tree, but without `.limen-workstream/` capsule rendered yet).
  - `limen-psp-omega-lane-identity-offer` and `limen-psp-omega-lane-portfolio-front-door` do not yet exist under `/Users/4jp/Workspace/.worktrees/`.
- Git branch status in `/Users/4jp/Workspace/limen`:
  - `codex/psp-omega-lane-proof-architecture` exists.
  - `work/psp-omega-lane-identity-offer` does not exist yet.
  - `work/psp-omega-lane-portfolio-front-door` does not exist yet.

---

## 2. Logic Chain

### 2.1 Worktree Session Initialization & Validation Flow
1. **Low-Level Transactional Worktree Creation (`limen.worktree_initialization.v1`)**:
   - To guarantee zero half-initialized worktrees, worktree creation must occur in a temporary staging root (e.g. `/Users/4jp/Workspace/.worktrees/.limen-init-<name>-<hex>`).
   - Staging verification tests tree purity, index alignment, and filesystem device identity (`st_dev`).
   - Atomic rename transfers the staged directory to `/Users/4jp/Workspace/.worktrees/<name>`.
   - The Git worktree backlink file (`.git/worktrees/<name>/gitdir`) is atomically updated to point to the final `.git` file.
   - The final directory is re-validated to guarantee HEAD, branch, and tree invariants hold post-rename.
2. **Git Info Exclusion Invariant**:
   - Main repo `.git/info/exclude` must contain `.worktrees/` and `.limen-workstream/` so local checkouts and private capsule runtimes never create dirty repo status.
3. **Continuation Capsule (`.limen-workstream/`) & Public Receipt Lifecycle**:
   - Each worktree requires a self-contained continuation capsule in `<worktree>/.limen-workstream/`.
   - The capsule holds the executable contract (`workstream.json`), contract runner (`workstream-contract.py`), task boundary (`intent.md`), runtime contract (`runtime.md`), closeout contract (`closeout.md`), historical manifest (`manifest.md`), prompt index (`README.md`), and startup harness (`kickstart.sh`).
   - `sync-identity` computes sha256 digests across all 8 modules and writes `capsule.identity`.
   - `sync-receipt` syncs the public Git-tracked receipt to `<worktree>/docs/continuations/<slug>/workstream.json`.
4. **Branch Prefix Enforcement**:
   - `scripts/start-worktree-session.sh` restricts branch prefixes to `work|feat|fix|heal|chore|docs|refactor`.
   - The Proof Architecture worktree uses `codex/psp-omega-lane-proof-architecture`, which was created directly via Git / Python `initialize_worktree`. For the other two lanes, `work/psp-omega-lane-identity-offer` and `work/psp-omega-lane-portfolio-front-door` use the standard `work` prefix.

---

## 3. Detailed Answers to Core Questions

### Q1. How worktree sessions are initialized, validated, and recorded
Worktree sessions follow a strict two-tier architecture:
1. **Tier 1 — Transactional Filesystem & Git Checkout Initialization** (`limen.worktree_initialization.v1`):
   - **Journaling**: Creates `$GIT_COMMON_DIR/limen-worktree-initialization/<sha256(final_path\0branch)>.json`. Initial state: `state=staging, phase=preflight`.
   - **Staging**: Adds worktree at sibling path `.limen-init-<name>-<hex>` on branch `<branch>` from `<checkout_ref>`.
   - **Staging Validation**: Validates exact HEAD match, symbolic branch ref, `write-tree` == `HEAD^{tree}`, clean index (`git diff --cached --quiet`), clean working tree (`git diff --quiet`), zero untracked paths (`git status --porcelain=v1 -z`). Checks `staging.st_dev == parent.st_dev`. Updates journal to `state=validated, phase=validate-staging`.
   - **Atomic Publish**: Updates journal to `state=moving, phase=move`. Atomically renames staging directory to final target path via `os.rename()`.
   - **Backlink Repair**: Updates `<git_dir>/gitdir` to `<final_path>/.git\n`.
   - **Final Validation & Publication**: Repeats all checkout validations at the final path. Updates journal to `state=published, phase=validate-final`.
   - **Forensic Failure Safety**: On exception, records `state=crashed` with failure code and details. Leaves filesystem untouched for forensic diagnosis.
2. **Tier 2 — Workstream Capsule & Custody Receipt Admission** (`scripts/lib/workstream-capsule.sh` & `workstream_contract.py`):
   - **Exclusion**: Verifies/appends `.worktrees/` and `.limen-workstream/` in `.git/info/exclude`.
   - **Capsule Rendering**: Writes 8 modules into `<worktree>/.limen-workstream/`.
   - **Identity Hashing**: Computes SHA-256 digests of all 8 files and writes `<worktree>/.limen-workstream/capsule.identity` (`limen.workstream.capsule-identity.v2`).
   - **Tracked Receipt**: Generates `<worktree>/docs/continuations/<slug>/workstream.json` (`limen.workstream.receipt.v1`).

---

### Q2. Arguments to create/initialize the 3 worktrees

| Parameter | Lane 1: Identity & Offer | Lane 2: Proof Architecture | Lane 3: Portfolio Front Door |
|---|---|---|---|
| **Worktree Path** | `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-identity-offer` | `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-proof-architecture` | `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-portfolio-front-door` |
| **Topic Branch** | `work/psp-omega-lane-identity-offer` | `codex/psp-omega-lane-proof-architecture` | `work/psp-omega-lane-portfolio-front-door` |
| **Branch Prefix** | `work` | `codex` | `work` |
| **Slug** | `psp-omega-lane-identity-offer` | `psp-omega-lane-proof-architecture` | `psp-omega-lane-portfolio-front-door` |
| **Workstream** | `positioning-identity-offer` | `positioning-proof-architecture` | `positioning-portfolio-front-door` |
| **Base Ref** | `HEAD` (or `origin/main`) | `HEAD` (`77d1069de`, existing) | `HEAD` (or `origin/main`) |
| **Runway** | `1d` (default) | `1d` (default) | `1d` (default) |
| **Current Status** | To be initialized | Pre-existing Git worktree; needs capsule rendering | To be initialized |

*Note on Branch Prefixes*: `scripts/start-worktree-session.sh` enforces `--branch-prefix` from `{work, feat, fix, heal, chore, docs, refactor}`. Lane 2 uses prefix `codex/`, which is handled either through existing worktree reuse or directly via Python `initialize_worktree(..., branch="codex/psp-omega-lane-proof-architecture", ...)`.

---

### Q3. Files and Metadata Created

```
/Users/4jp/Workspace/limen/
├── .git/
│   ├── info/exclude                             # Appended: .worktrees/ and .limen-workstream/
│   └── limen-worktree-initialization/           # Transaction journals:
│       └── <sha256>.json                        # {"schema": "limen.worktree_initialization.v1", "state": "published", ...}
│
/Users/4jp/Workspace/.worktrees/<worktree-name>/
├── .git                                         # Git worktree pointer file (e.g. gitdir: .../worktrees/...)
├── .limen-workstream/                           # Private capsule (local & git-excluded)
│   ├── README.md                                # Prompt index & host-shell launch command
│   ├── manifest.md                              # Historical metadata snapshot
│   ├── workstream.json                          # Contract (schema: limen.workstream.contract.v1, runway, auth)
│   ├── workstream-contract.py                   # Self-contained contract helper script (executable)
│   ├── intent.md                                # Objective description & prompt context
│   ├── runtime.md                               # Live probes and boundary decision contract
│   ├── closeout.md                              # Closeout and successor requirements
│   ├── kickstart.sh                             # Host-shell execution script (executable)
│   ├── capsule.identity                         # Integrity manifest (schema: limen.workstream.capsule-identity.v2)
│   └── .capsule.lock                            # Concurrency lockfile
└── docs/continuations/<slug>/
    └── workstream.json                          # Tracked custody receipt (schema: limen.workstream.receipt.v1)
```

---

### Q4. Recommended Exact Implementation Procedure for Worker

The Worker should execute the following 5-phase procedure:

#### Phase 1: Environment & Repository Preflight
1. Ensure `/Users/4jp/Workspace/.worktrees` directory exists.
2. Verify `.git/info/exclude` in `/Users/4jp/Workspace/limen` contains `.worktrees/` and `.limen-workstream/`.
3. Resolve current repo `HEAD` commit (`git rev-parse HEAD`).

#### Phase 2: Transactional Worktree Initialization
Run Python script calling `initialize_worktree` from `limen.worktree_initialization`:
```python
import sys
from pathlib import Path
sys.path.insert(0, "/Users/4jp/Workspace/limen/cli/src")
from limen.worktree_initialization import initialize_worktree

repo = Path("/Users/4jp/Workspace/limen")
worktrees_dir = Path("/Users/4jp/Workspace/.worktrees")

# Lane 1: Identity & Offer
wt1 = worktrees_dir / "limen-psp-omega-lane-identity-offer"
if not wt1.exists():
    initialize_worktree(
        repo,
        wt1,
        branch="work/psp-omega-lane-identity-offer",
        checkout_ref="HEAD",
        task_id="psp-omega-lane-identity-offer",
    )

# Lane 2: Proof Architecture (Verify existing worktree)
wt2 = worktrees_dir / "limen-psp-omega-lane-proof-architecture"
assert wt2.exists(), "Lane 2 worktree should already exist"

# Lane 3: Portfolio Front Door
wt3 = worktrees_dir / "limen-psp-omega-lane-portfolio-front-door"
if not wt3.exists():
    initialize_worktree(
        repo,
        wt3,
        branch="work/psp-omega-lane-portfolio-front-door",
        checkout_ref="HEAD",
        task_id="psp-omega-lane-portfolio-front-door",
    )
```

#### Phase 3: Capsule & Receipt Generation
For each of the 3 worktrees (`limen-psp-omega-lane-identity-offer`, `limen-psp-omega-lane-proof-architecture`, `limen-psp-omega-lane-portfolio-front-door`):
1. Create `<wt>/.limen-workstream/`.
2. Populate:
   - `manifest.md` with worktree snapshot metadata.
   - `workstream-contract.py` copied from `/Users/4jp/Workspace/limen/cli/src/limen/workstream_contract.py` (`chmod +x`).
   - `intent.md` with lane-specific objective.
   - `runtime.md` copied from `/Users/4jp/Workspace/limen/spec/continuation-capsule/runtime-interactive.md`.
   - `closeout.md` copied from `/Users/4jp/Workspace/limen/spec/continuation-capsule/closeout.md`.
   - `README.md` with prompt index.
   - `kickstart.sh` with launcher script.
3. Configure contract:
   `python3 <wt>/.limen-workstream/workstream-contract.py configure --path <wt>/.limen-workstream/workstream.json --runway 1d`
4. Sync identity:
   `python3 <wt>/.limen-workstream/workstream-contract.py sync-identity --identity <wt>/.limen-workstream/capsule.identity --invocation-sha256 <digest> --module README.md=<...> --module manifest.md=<...> ...`
5. Sync receipt:
   `python3 <wt>/.limen-workstream/workstream-contract.py sync-receipt --contract <wt>/.limen-workstream/workstream.json --receipt <wt>/docs/continuations/<slug>/workstream.json --slug <slug> --branch <branch> --workstream <ws> --module ...`

#### Phase 4: Full Validation & Verification
Execute the verification predicates across all 3 worktrees:
```bash
# 1. Verify Git worktree registration and branch binding
git -C /Users/4jp/Workspace/limen worktree list

# 2. For each worktree, verify:
for wt in /Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-*; do
  echo "Verifying $wt..."
  git -C "$wt" rev-parse --is-inside-work-tree
  git -C "$wt" status --porcelain=v1
  python3 "$wt/.limen-workstream/workstream-contract.py" validate-receipt-metadata \
    --slug "$(basename "$wt" | sed 's/^limen-//')" \
    --branch "$(git -C "$wt" branch --show-current)"
done
```

---

## 4. Caveats
1. **Pre-existing Worktree State**: `limen-psp-omega-lane-proof-architecture` is already a valid linked worktree on branch `codex/psp-omega-lane-proof-architecture` @ commit `77d1069de`. It does not need `git worktree add`, but requires capsule rendering and receipt generation.
2. **Branch Prefix Naming in Shell vs Python**: `start-worktree-session.sh` rejects `codex` as a branch prefix because of CLI whitelist validation, whereas Python `initialize_worktree` accepts arbitrary valid Git branch names. Direct Python initialization or script-level capsule rendering is recommended.
3. **No Direct Main Modifications**: All operations strictly mutate `.git/info/exclude` or individual topic worktrees; `main` branch HEAD remains untouched.

---

## 5. Conclusion
- Worktree initialization architecture in Limen is fully standardized and crash-resilient across both the low-level Git plumbing (`limen.worktree_initialization.v1`) and the higher-level continuation capsule layer (`limen.workstream.contract.v1`/`v2`).
- All 3 topic worktrees (`limen-psp-omega-lane-identity-offer`, `limen-psp-omega-lane-proof-architecture`, `limen-psp-omega-lane-portfolio-front-door`) have clearly defined branch namespaces, slug conventions, capsule modules, and receipt paths.
- The Worker can execute the setup procedure cleanly and deterministically without risking branch collisions or untracked state leaks.

---

## 6. Verification Method

To independently verify these findings:
1. **Inspect initialization implementation**:
   ```bash
   python3 -c "import sys; sys.path.insert(0, 'cli/src'); from limen.worktree_initialization import initialize_worktree; print(initialize_worktree)"
   ```
2. **Inspect contract helper subcommands**:
   ```bash
   python3 cli/src/limen/workstream_contract.py --help
   ```
3. **Inspect current worktree topology**:
   ```bash
   git -C /Users/4jp/Workspace/limen worktree list
   ls -la /Users/4jp/Workspace/.worktrees/
   ```
4. **Run unit tests for worktree initialization and contract helpers**:
   ```bash
   pytest cli/tests/test_worktree_initialization.py cli/tests/test_workstream_contract.py
   ```
