# TMB Ingress first pass — receipt (2026-10-17)

Plan: `docs/plans/2026-10-17-tmb-acceptance-gaps.md` (Lane K, G9, G8) · Issue: #2909 ·
Source repo change: `4444J99/time-moment-brief` PR #9 (merge `60c6453f4b88048f115591dfd55abf8648a79e2b`).

## Observed

- The Ingress archival volume is mounted (APFS volume `disk7s2`, 292 GB used) and carries all five
  collections under `backwards-up-hill`: `2022FEB-100GOPRO`, `2022FEB-360GOPRO`, `2022FEB-DJI`,
  `2022FEB-F6`, `2022FEB-PANASONIC`.
- The volume mounted writable. The pass wrote nothing to it: a `find -newer` check over the volume after
  the pass returned empty.
- Ingress (`disk7s2`) and Archive4T (`disk7s1`) are volumes of the same APFS container `disk7`, backed by
  one physical store `disk6s2`. Archive4T is therefore not an independent physical copy of the originals.
  The originals currently have exactly one physical copy. Archive4T remains independent of the Mac internal
  disk, so the sealed-media custody from limen PR #2927 is unaffected.

## First hash chain

- TMB PR #9 committed the first-ever sha256 chain of the originals: 6 originals hashed, originals root
  sha256 `69e942b768d5b407fabaee07dbfea84049173d3ca739c19641601a4e4e0a1e84`.
- 16 derivatives hashed, derivatives root sha256
  `7b913266467eab58ed5aefac03ce0ddd525ef499a104b5e457b23ecefb2a84d8`.
- Full per-file hashes live only in the private hash manifest (git-ignored in the TMB repo). A mode-0600
  copy sits in custody staging under the run directory `tmb-ingress-hash-chain-20261017`.
- The tracked census is redacted: 16-hex prefixes per file plus the two roots above.

## Derivative lineage

The derivative rebuild produced no drift: `webcodecs-spike/source-manifest.json` is unchanged
(`git diff --exit-code` exited 0).

## 100GOPRO verdict

`evidence/hundred-gopro-coverage.json` records:

- `metadata_verdict`: `no-coverage-likely` (gap 1492.7 s; camera clocks are untrusted).
- `onset_verdict`: **negative**. Both clips strong-match the F6 audio elsewhere, not in the matched passage:
  - GH010043: peak 54.0018 s, margin 71.0%.
  - GH010044: peak 760.0005 s, margin 57.25%.
  - Match floor 19.2%. Window overlap 0.0 s with the matched passage [510, 526] s.
- Method: blind full-range onset-envelope correlation of each 100GOPRO clip against the F6 audio, with the
  peak located over the whole recording rather than inside the expected window, scored against a 19.2%
  floor.
- 100GOPRO is the only fourth sensor on the disk, so the four-independent-camera predicate still requires a
  new capture or a recording from elsewhere. 100GOPRO is eliminated as a candidate.

## What this changes

- G9 (mount): the mount precondition is satisfied and the first hash chain is committed. The originals are
  single-copy, so `L-TMB-INGRESS-SOURCE-MOUNT` stays open but is narrowed to one atom: connect a disk on a
  physical device other than `disk6s2`; the agent then copies and hash-verifies the originals there and
  receipts it.
- G8 (fourth camera): the 100GOPRO candidate is eliminated. `L-TMB-FOURTH-CAMERA` stays open, no longer
  depends on the mount lever, and now asks for a new capture or an existing fourth-sensor recording of the
  matched passage.
- No lever was added or closed; the registry count is unchanged.

## What it does not establish

- No second physical copy of the originals exists. Archive4T shares the physical store with Ingress.
- The hash chain proves the current bytes, not provenance before the first mount.
- The onset negative is evidence of non-overlap with the matched window for these two clips, not evidence
  that no other fourth-sensor recording exists.
