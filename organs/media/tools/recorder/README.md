# media-recorder — native screen + system-audio capture

Capture front-end of the **Carrier-Wave Media** organ (Spine A intake). Records the
screen **with the Mac's internal/system audio** — the thing macOS's built-in ⇧⌘5
recorder cannot do on its own.

## Why this exists

macOS screen recording captures a **microphone**, never the computer's internal/app
audio, unless a virtual loopback driver is installed. This tool uses
**ScreenCaptureKit's `SCRecordingOutput`** (macOS 15+) with `capturesAudio = true`,
which taps system audio **natively — no BlackHole, no Loopback, no Multi-Output
device**. Optional microphone is captured as a second track (`--no-mic` to skip).

## Build

```bash
./build.sh          # swiftc -parse-as-library record.swift -o media-recorder
```

No external dependencies. Requires macOS 15+ and the Xcode command-line tools
(`swiftc`). The compiled `media-recorder` binary is git-ignored — build it locally.

## Use

```bash
./media-recorder --seconds 30                     # 30s, screen + system audio + mic
./media-recorder -s 30 --no-mic                    # system audio only
./media-recorder -s 30 -o ~/clip.mov               # explicit output
./media-recorder -s 30 -d 1                         # second display
```

Default output: `~/Pictures/Screen Captures/Recording-<timestamp>.mov` — the same
folder the live screenshot importer watches, so recordings flow into Photos.app and
the media-ark archive pipeline automatically (Spine A).

## The one human atom — TCC (lever `L-TCC-RECORDER`)

First run triggers a one-time macOS **Screen Recording** (and **Microphone**)
permission dialog. Grant it once in System Settings → Privacy & Security. Everything
after is scriptable. This grant is the single irreducible human step for the native
path.

## Fallback: BlackHole (lever `L-AUDIO-BLACKHOLE`)

For the rare app whose audio ScreenCaptureKit can't tap, a virtual loopback driver
is the fallback. That path is **human-gated** (privileged driver install):

```bash
brew install --cask blackhole-2ch        # sudo + security approval + reboot
```

Then in **Audio MIDI Setup** create a **Multi-Output Device** (Speakers + BlackHole
2ch) so you still hear audio while routing it to BlackHole, and record it via:

```bash
ffmpeg -f avfoundation -list_devices true -i ""          # find the device index
ffmpeg -f avfoundation -i ":BlackHole 2ch" -c:a aac sysaudio.m4a
```

Prefer the native `media-recorder` path; BlackHole is only for gaps.
