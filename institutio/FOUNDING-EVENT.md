# VIGILIA — Founding Event (2026-06-25)

The institution remembers what spawned it. This is the record; the evidence itself is
**preserved outside git** (it contains memory excerpts — names, paths, possibly secrets).

## The artifact

- **Panic report:** `panic-full-2026-06-25-084708.0002.panic` (2.1 MB)
- **Original location:** `/Library/Logs/DiagnosticReports/` (root-owned, world-readable)
- **Preserved copy:** `~/.local/share/vigilia/founding-event/` — durable, **non-git**, so the
  macOS "Share with Apple → immediately removed from your device" path cannot erase the origin.
- **Companions seen in the submit dialog:** `2026-06-25-084708.kernel.core.gz`,
  `…kernel.core.log`, a `macOS Sysdiagnose` bundle (full core dumps — not preserved; larger
  and more sensitive; keep or discard at the operator's discretion).

## The verdict (already established locally)

Memory-exhaustion **livelock → kernel watchdog panic** on a `Mac17,2` (Apple M5, 16 GB):
compressor at 100% of its hard limit, 12 swapfiles, ~14 MB free, `watchdogd` starved 92 s.
**Not hardware, not an Apple bug** — the daemon fleet (Python + ollama) exhausted RAM.
The 01:27 jetsam (largestProcess: Python) was the dress rehearsal; 08:47 was the panic.

## The "Share with Apple" decision — operator's lever

The submit dialog offers **Share with Apple** vs **Cancel**, and warns the files may contain
"name, usernames, email addresses, email content, … credit card data, file paths, file names,
passwords, …". Sending is an outward-facing, irreversible disclosure → it stays a human lever.

**Recommendation: Cancel.** The cause is already known and is *not* Apple's to fix; sharing
would disclose sensitive memory contents for no diagnostic gain. The founding evidence is now
preserved locally regardless of the choice.

## Why it matters

This single event exposed all three autonomic faults at once and is the reason VIGILIA exists
(see [`CHARTER.md`](./CHARTER.md) → "Why now"). It is the institution's case zero.
