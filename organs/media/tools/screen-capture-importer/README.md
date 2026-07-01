# screen-capture-importer

Capture front-end of the **Carrier-Wave Media** organ (Spine A intake). A per-user
LaunchAgent that imports new screengrabs & recordings from `~/Pictures/Screen Captures`
into **Photos.app**, once each.

> **Provenance note.** This was live on disk (`~/.local/bin/…` + a LaunchAgent) but
> **untracked in any repo** — if the local copy were lost it could not be regenerated.
> Rescued into git 2026-07-01 ([[preserve-user-inputs-as-provenance]]).

## Files

| File | Role |
|------|------|
| `import-screen-captures.sh` | the importer (idempotent via a seen-list) |
| `install.sh` | installs to `~/.local/bin` + generates & loads the LaunchAgent for the current user |

## Install / uninstall

```bash
./install.sh              # copy + load LaunchAgent (WatchPath on ~/Pictures/Screen Captures)
./install.sh --uninstall  # unload + remove the plist
```

## Known issue — exit code 1 (AppleScript -4960)

The live agent's `err.log` shows repeated `execution error … -4960` on the
`tell application "Photos" … import` step. This is an **Automation permission**
failure: the launchd-spawned process is not authorized to send Apple Events to
Photos.app. Fix (human atom, lever **L-TCC-PHOTOS-AUTOMATION**):

1. System Settings → Privacy & Security → **Automation** → allow the importer (or
   Terminal/its parent) to control **Photos**.
2. If the prompt never appears under launchd, run the importer once from a terminal
   to trigger the Automation grant, then reload the agent.

## Relationship to the native recorder & media-ark

This importer targets **Photos.app** specifically. The sibling `../recorder`
(`media-recorder`) writes recordings into the same `~/Pictures/Screen Captures`
folder, so they compose. For a deduped/OCR'd/indexed archive (rather than Photos.app),
the same folder is also an ingest source for the **media-ark** pipeline (Spine A).
