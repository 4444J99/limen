# AV private-derivative custody: second-device receipt (2026-10-17)

Observed from live state by a Claude direct session. Supersedes the "same-device custody only" limit in
`DEVICE_ACCEPTANCE_RESULTS.json` (time-moment-brief, 2026-10-10) for the four recording derivatives only.

| Fact | Evidence |
|---|---|
| Conduct root `run-12a1b2390e4ca37140f00d546c1cab26` | Broker graph: `status: expired`, lease `state: expired`, hard deadline 2026-10-10T17:01:58Z. Spend/debit history is not part of the graph node and was not touched. |
| Combined head published | `origin/agent7-stable-playback-base` = `7fa9181`; `origin/agy/choreography-foa-m6-m9` = `4b9b3cd`; old heads `893efbcb` and `d53103a9` are ancestors of both. |
| Tracked private media | None at `7fa9181`: the four `generation-0{1,2}` mp4/m4a files are untracked and ignored; `tests/e2e/test_private_media_exclusion.py` asserts this. Tracked zips contain no recording media. |
| Same-device copies | 12 of 12 sha256 matches against the manifest (`custody/`, `restore/`, `ace-restore-20261012-*`). |
| Second device | `/Volumes/Archive4T/limen-custody/av-media-20261017-171406/` (USB SSD, mode 0700, unencrypted APFS): 4 of 4 sha256 matches from the destination after `sync`. |
| Acceptance landing | time-moment-brief PR #4 merged to `main` at `44d815c`; PR #3 `e5900ef`. |

Limits: git history on the remotes still contains the blobs (untracking does not purge history). The external disk
is not encrypted. The archival source volume `Ingress` is still absent, so source lineage is unverified.
Four-camera, headset, phone, lip-sync, and browser FOA audio gates stay FAILED/UNVERIFIED.
