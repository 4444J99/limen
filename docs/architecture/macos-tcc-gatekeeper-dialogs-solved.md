# macOS TCC / Gatekeeper dialogs — the corrected root causes

**This file is the target of the `[[macos-tcc-gatekeeper-dialogs-solved]]` wikilink** cited from
`scripts/dialogs-silenced.sh`, `institutio/governance/sensors.yaml` (0g8b),
`institutio/governance/parameters.yaml`, `his-hand-levers.json` (L-DIALOGS-HEAL, L-FIREWALL-PROMPT),
and `docs/never-hang-permission-spec.md`.

**It did not exist until 2026-08-05, and that absence is the mechanism of a six-week defect loop.**
Five sessions followed the link, found nothing, and re-derived the root cause from the effector's
own header comment — which carried a false premise. The refutation had no home, so the false premise
propagated. If you are reading this because you are about to "fix the ClaudeCode.app dialog again":
**read this file first, then run the predicate. Do not re-derive.**

Ideal form: `IF-GATEKEEPER-INERT` (`docs/IDEAL-FORMS-LEDGER.md`). Probe:
`python3 scripts/claude-identity-bundle.py --strict`.

---

## Class 4b — "ClaudeCode.app is damaged and can't be opened"

### What is actually true (reproduced 2026-08-05, not recalled)

**1. The bundle is Gatekeeper-invalid by construction, not by corruption.**
The Claude Code CLI is signed as a **bare Mach-O** — `Developer ID Application: Anthropic PBC`,
`Sealed Resources=none`, `Info.plist=not bound`. Wrapped in a hand-written `.app`, macOS evaluates
it as a **bundle**, and bundle-form `--strict` requires a `Contents/_CodeSignature/CodeResources`
that a bare-Mach-O signature never sealed. The verdict is deterministic:

| evaluated as | `codesign --verify --strict` |
|---|---|
| `versions/2.1.223` (bare) | **0** |
| `ClaudeCode.app/Contents/MacOS/claude` — *the same inode* | **1** — `code has no resources but signature indicates they must be present` |

It is "damaged" **every time it is written**. There is no corruption event, no bad download, no
partial update. Reproduce it in thirty seconds: hardlink the CLI into
`Foo.app/Contents/MacOS/claude`, write any `Info.plist`, run `codesign --verify --strict Foo.app`.

**2. "Absent" is unreachable.** The *live* binary materializes the bundle on **every start**. From
`strings` on 2.1.223 — this is the vendor's own function, not a legacy artifact:

```js
async function y7b(){ let e = join(WFt(),"claude");
  if(!process.execPath.startsWith(join(e,"versions")+sep)) return null;
  let t = join(e,"ClaudeCode.app","Contents","MacOS"), r = join(t,"claude");
  try{ let n = (await stat(process.execPath)).ino;
    await mkdir(t,{recursive:!0}), await writeFile(join(t,"..","Info.plist"), …
```

It exists to give the disclaimed session a stable TCC identity (`com.anthropic.claude-code`) instead
of a per-version one. Every removal guarantees the next recreate.

**3. "Valid" is unreachable too, and dangerously so.** Making the bundle pass means re-signing it —
but `Contents/MacOS/claude` is a **hardlink** to the running `versions/<v>` binary. Signing the
bundle would rewrite Anthropic's Developer ID signature **on the live CLI, in place**, breaking both
its signature and auto-update. This option is disqualified, not merely undesirable. **Never
`codesign` this bundle.**

**4. Therefore deletion was never a cure — it was a duty cycle, and it cost more than it bought.**
`lsregister -dump` alone takes **2.85s**; the WatchPaths agent carries `ThrottleInterval 10`. That
is a **≥12.85s exposure window on every start**, against a three-syscall vendor write. #1242 named
itself "instant heal"; no amount of tuning closes a race whose loser is fixed. Worse, removal
**destroys the stable TCC identity** that sensor `0g8d` (`scripts/claude-identity-bundle.py`) exists
to keep — the two organs held opposite invariants over one file and both shipped green.

### The convergent cure

**Unregister; never remove.** `execve` does not consult LaunchServices — only the *dialog* does. So
the reachable fixed point is:

> the bundle is **present and inode-correct** (the vendor's invariant, and `0g8d`'s) **and carries
> zero LaunchServices registrations** (`heal-claude-lsregister.sh`'s invariant).

Those are two non-overlapping predicates over one file, so both organs are green simultaneously.
The `~/.Trash` sweep still **removes**, because a trashed copy is genuine garbage and removing it
destroys no identity — the live bundle stays in place.

### Two traps

- **Never click "Move to Trash" on the dialog.** It reseeds into `~/.Trash`, where LaunchServices
  keeps the copy registered, and the next resolution of `com.anthropic.claude-code` hits it.
- **Never filter on one exact `codesign` string.** The prior `condemnable()` matched only
  `code has no resources but signature indicates they must be present`, and therefore missed the
  **mid-write** state — after `writeFile(Info.plist)`, before `link()` — where the bundle advertises
  a `CFBundleExecutable` pointing at a file that does not exist yet and `codesign` says
  `code object is not signed at all`. **That is the state macOS renders as "damaged"**, and the
  filter built to catch it let it through. Condemn on *any* non-zero verdict.

---

## The deep-link handler — the second instance of the same class

`~/Applications/Claude Code URL Handler.app` (`com.anthropic.claude-code-url-handler`, scheme
`claude-cli://`) is the same construction and carries the same unassessable seal. Two differences
that matter:

- Its `Contents/MacOS/claude` is a **symlink to `~/.local/bin/claude`**, not a hardlink, so it
  tracks the launcher and never goes stale across an update. (Beware: `ls -i` shows the *symlink's*
  inode while `stat()` follows it. Reading those as one measurement produces a phantom
  "stale hardlink" finding — this was caught in-flight on 2026-08-05.)
- It lives in `~/Applications`, a LaunchServices-**scanned** domain, so it is *permanently*
  registered. Unregistration does not hold there, and the effector deliberately never touches
  `~/Applications`.

Its only convergent cure is the vendor's own supported setting:

```jsonc
// ~/.claude/settings.json
"disableDeepLinkRegistration": "disable"   // "Prevent claude-cli:// protocol handler registration with the OS"
```

That is a **feature trade** (it turns off `claude-cli://` deep links), so it is the operator's call
and is homed as lever **`L-CLAUDE-DEEPLINK-REGISTRATION`** — measured by the keeper, never applied by
it.

---

## Per-version TCC consent prompts (adjacent, upstream, NOT this class)

Distinct from the "damaged" dialog and not operator-curable. Claude Code re-execs itself with
`macDisclaimResponsibility: true`, so no supervising host can carry an identity across it. The daemon
runs its pty host *from* the bundle but hands the session process its `versions/<version>` path as
literal argv, and **that** session disclaims into its own TCC client, named by its filename. The argv
is composed inside a signed 271MB Mach-O. Filed upstream:
`anthropics/claude-code#79867` (comment `5198453531`). A green reading on `0g8d` is **not** "prompts
fixed" — see the SCOPE note in `scripts/claude-identity-bundle.py`.

---

## Method note — the failure this file exists to stop

This lineage has now made the **same** error three times: *a mechanism named from reading vendor
source, or from one measurement, and never confronted with the running system.*

1. PPID read as evidence of identity — falsified by `domus-agent-host verify-lifetime`, one command.
2. "A missing bundle is why dialogs show a bare version" — falsified by `ps -o args=` on the live
   tree, one command, *while the keeper reported `at-ideal`*.
3. "The deep-link handler holds a stale hardlink" — falsified by `ls -l`, one command, in-flight.

Every one was cheap to check. **Naming a plausible mechanism is not evidence.** Before adding a sixth
cure to this class, run the predicate and read its `instances[]`.
