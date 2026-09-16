# Dropbox updater census ownership

Owner: Codex; IRF-SYS-257 background-item declaration parity.

The live installed census identified one undeclared plist: com.dropbox.DropboxUpdater.wake, executable basename DropboxUpdater. codesign --verify --strict returned zero. Signature metadata identifies com.dropbox.DropboxUpdater, Developer ID Application Dropbox, Inc., team G7HH3F8CAK, through the Apple Root CA. No executable was launched or modified.

Register only the com.dropbox.DropboxUpdater. prefix under the existing vendor-updater exemption. Do not exempt all Dropbox-like labels or change scheduling, credentials, update settings, or process state. BTM remains independently unmeasured and liveness remains separately owned. This is classification of a verified vendor updater, not evidence of background estate health.

Live plist classification now reports zero undeclared entries; an unrelated com.dropbox.unrelated label remains unclassified. The first scoped build encountered absent worktree dependencies (yaml). The documented npm ci bootstrap completed under the machine-wide heavy lease; no lockfile changed. BTM was not re-probed for this classification observation.
