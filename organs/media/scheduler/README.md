# social_scheduler — outbound distribution (drafts only)

The **OUTBOUND** face of the Carrier-Wave Media organ (Spine B). Turns the media the
archive produced (screengrabs, recordings, the media-ark `out/` tree) into
platform-native social assets — and **queues** them. It never posts on its own.

```
select  ->  transcode/crop (ffmpeg)  ->  caption  ->  queue  ->  [HUMAN SEND]
```

This honors the organ's hard guardrail (KERNEL.md): *the organ drafts; the human
publishes.* Nothing leaves the machine without a human pulling lever `L-SOCIAL-SEND`.

## Use

```bash
# dry-run plan (no ffmpeg, no network) — pick assets + draft captions
python social_scheduler.py plan --platform reel --query wrath

# + actually transcode to platform spec (still queues as draft, never posts)
python social_scheduler.py plan --platform reel --source ~/Pictures/Screen\ Captures --apply

python social_scheduler.py queue-list          # review drafts
python social_scheduler.py send --id <qid>     # REFUSED without token + human lever
```

## Platforms & specs (ffmpeg cover-crop)

| Platform | Size | Aspect | Wants |
|----------|------|--------|-------|
| `reel` / `tiktok` / `story` | 1080×1920 | 9:16 | video / (story: image) |
| `x` | 1280×720 | 16:9 | video |
| `feed` | 1080×1080 | 1:1 | image |

## The human atoms (levers)

- **`L-SOCIAL-OAUTH`** — create the IG/TikTok/X developer apps + mint first tokens.
  The resulting tokens are **credentials**: they route through `creds-hydrate.py`
  `DEFAULT_MAP` (op:// → env), **never** chat or this file. `send` refuses until the
  platform token is present in the env.
- **`L-SOCIAL-SEND`** — the actual publish. Drafts stay `draft` until you pull it.

## Where things land

- Queue + staged transcodes: `$LIMEN_PRIVATE_ROOT/media-scheduler/` (git-ignored private cartridge).
- Source default: `~/Pictures/Screen Captures` (where the recorder + importer drop files).

## Federation

Reads assets from Spine A (media-ark archive / the capture folder); it does **not**
re-archive. Capture front-ends (`../tools/recorder`, `../tools/screen-capture-importer`)
feed the archive; this scheduler distributes from it.
