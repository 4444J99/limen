# IF-GATEKEEPER-INERT — give the "ClaudeCode.app is damaged" class its missing ideal form

Issue: #1849
PR: #1848

## Context — why this arc exists

The macOS Gatekeeper dialog *"ClaudeCode.app is damaged and can't be opened"* recurred **~10–15×
over six weeks**, across **24 commits and five shipped cures** (#1206 effector → #1219 organ family
→ #1242 "instant" WatchPaths heal → #1704 TCC audit → #1837 identity keeper). Every cure reported
green. It kept firing.

The operator's question was the right one: *"we supposedly fixed it in the past — so why is it still
happening?"*

## What was actually true (reproduced from scratch, not recalled)

1. **The bundle is Gatekeeper-invalid by construction, not by corruption.** The CLI is signed as a
   **bare Mach-O** with `Sealed Resources=none`. Wrapped in a hand-written `.app`, macOS evaluates
   it as a *bundle* and `--strict` demands a `Contents/_CodeSignature/CodeResources` the signature
   never sealed. The **same inode** passes bare (exit 0) and fails bundled (exit 1). It is "damaged"
   every single time it is written.
2. **ABSENT is unreachable.** The live binary materializes it on every start — the vendor's own
   `_jb()`: `mkdir` + `writeFile(Info.plist)` + `link(process.execPath)`.
3. **VALID is unreachable and disqualified.** `Contents/MacOS/claude` is a **hardlink** to the
   running `versions/<v>`, so re-signing would rewrite Anthropic's Developer ID signature on the
   live CLI in place and break auto-update.
4. **So the cure was a duty cycle.** `lsregister -dump` costs **2.85s**; the WatchPaths agent
   carries `ThrottleInterval 10` — a **≥12.85s exposure window per start** against a three-syscall
   write. #1242 named itself "instant" and could not be.
5. **And it cost more than it bought.** Deletion destroyed the stable TCC identity sensor `0g8d`
   exists to keep. Two shipped organs held contradictory invariants over one file — `0g8d` kept it
   present, `0g8b` declared *"ZERO registrations … do NOT restore the stub"* — both green, with the
   valve armed so the beat **and** the WatchPaths agent deleted what the keeper had just written.

## The root defect

**The class had no ideal form.** An effector, a sensor, a launchd agent, a lever, 24 commits — and
nothing in `docs/IDEAL-FORMS-LEDGER.md` declaring the fixed point they were converging on. So each
cure optimized a private invariant and none could be wrong, because none was *stated*.
`dialogs-silenced.sh` had printed class 4b since 2026-07-09 into no owner: the same *measured but
unregistered* defect `IF-NO-MODAL`'s own Evidence names.

Compounding it, the class's root-cause knowledge was homed in `[[macos-tcc-gatekeeper-dialogs-solved]]`
— a wikilink cited from **five** registry surfaces that **did not exist on disk**. Every session
followed it, found nothing, and re-derived the root from the effector's header comment, which
carried the false premise ("an older CLI shipped a stub; 2.1.190+ ships none; do NOT restore").
**The false belief propagated because its refutation had no home.**

## What shipped (PR #1848)

- **Heal.** The effector **unregisters** instead of deleting. `execve` never consults
  LaunchServices; only the dialog does. So *present* (`0g8d`, and the vendor) and *unregistered*
  (`0g8b`) stop being contradictory claims and become two non-overlapping predicates over one file.
  `condemnable()` also widened from one exact codesign string to any non-zero verdict, closing the
  mid-write blind spot (`code object is not signed at all`) that is precisely what macOS renders as
  "damaged".
- **Expand.** The keeper enumerates the whole vendor-bundle **class**, per `IF-AGENT-IDENTITY`'s own
  rule that a count is zero *"across every service … a lens that judges one service scores the
  sprawl green."* An unreadable LaunchServices now reports `registration_unmeasured` and can never
  go green.
- **Evolve.** `IF-GATEKEEPER-INERT` declared in both ideal-forms files (checks A–F clean, 21
  ideals), status **PARTIAL**. The deep-link handler is measured but not repaired — its only
  convergent cure is the vendor's `disableDeepLinkRegistration`, a feature trade homed as lever
  `L-CLAUDE-DEEPLINK-REGISTRATION`.
- **Contracts.** First-ever coverage for this class: 17 effector contracts that **fail 5×** against
  the prior logic, plus 5 keeper contracts; the keeper suite went from 78s and host-dependent to
  0.07s.
- The missing note now exists at `docs/architecture/macos-tcc-gatekeeper-dialogs-solved.md`.

## Method note — the error this arc kept making, including in this arc

Three times now, a mechanism has been named from reading vendor source or a single measurement and
never confronted with the running system:

1. PPID read as evidence of identity — falsified by `verify-lifetime`, one command.
2. "A missing bundle is why dialogs show a bare version" — falsified by `ps -o args=`, one command,
   *while the keeper reported `at-ideal`*.
3. **In this arc:** "the deep-link handler holds a stale hardlink to a deleted version's bytes" —
   falsified by `ls -l`, one command, in-flight before shipping. Its `Contents/MacOS/claude` is a
   **symlink** to the launcher; `ls -i` reports the symlink's own inode while `stat()` follows it,
   and the two were read as one measurement. The `stale_vendor_hardlink` predicate was removed
   rather than shipped measuring nothing.

Every one was cheap to check. Naming a plausible mechanism is not evidence.

## Residual

- The fix is not live on the host until #1848 merges: the WatchPaths agent executes the script from
  the live checkout, so it still runs the deleting version.
- `L-CLAUDE-DEEPLINK-REGISTRATION` is open by design — a product decision, not a chore.
- Per-version TCC consent prompts remain upstream (`anthropics/claude-code#79867`), unchanged by
  this arc and explicitly out of its scope.
