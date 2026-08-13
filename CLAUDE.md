# inputstream.tempo

Fork of `inputstream.ffmpegdirect` adding pitch-corrected playback speed via
FFmpeg's `atempo` filter. Binary Kodi add-on (`kodi.inputstream`), plus a Python
service for window properties, keymap install and notifications.

## Kodi knowledge lives in kodi-drive

Shared Kodi knowledge is **not** in this file. Use the `kodi-drive:*` skills, or
read `../kodi-drive/README.md`.

Directly relevant: `kodi-inputstream` (the two clocks, capability flags, filter
state across a flush, FFmpeg version differences, stream-analysis tuning),
`kodi-binary-build`, `kodi-android-ndk`, `kodi-versions-abi`, `kodi-addon-release`,
`kodi-paplayer`, `kodi-playback-resume`.

**Do not add generally-useful Kodi findings here** — contribute them to kodi-drive.
This file holds only what is specific to *this* add-on.

## Layout

| Path | |
|---|---|
| `src/stream/FFmpegStream.cpp/.h` | demuxer, tempo pipeline, seek, time reporting |
| `src/StreamManager.cpp/.h` | entry point, property parsing, stream lifecycle |
| `src/utils/Properties.h` | parsed ListItem properties |
| `resources/lib/runner.py` | background service — window properties, keymap, notifications |
| `resources/lib/speed.py` | `RunScript` handler for keyboard/dialog speed control |

## Property contract

Set on the ListItem by the calling add-on:

| Property | |
|---|---|
| `inputstream.tempo.tempo` | initial speed, e.g. `1.5` |
| `inputstream.tempo.tempo_file` | path polled for live tempo changes (atomic write) |
| `inputstream.tempo.start_time` | resume position in seconds — pre-sets `m_currentPts` for `GetTime()` **and** arms the initial seek hold |

**Resume seeking is not done here.** The calling add-on sets PAPlayer's
`audiobook_bookmark`, which PAPlayer applies natively before audio output begins.
See `kodi-playback-resume`.

## Tempo pipeline

`FFmpegStream::AddStream()` → `InitTempoProcessing()` builds
`abuffer → atempo → aformat(f32) → abuffersink`. Audio packets are decoded,
filtered, and re-packaged as PCM float32 in `ProcessAudioPacketWithTempo()`; output
goes to `m_tempoOutputQueue`, and `DemuxRead()` pops from it.

The tempo file is polled every ~50 packets via `CheckTempoFileUpdate()`. Live
changes use `avfilter_graph_send_command()` where possible, falling back to a full
graph rebuild.

If `BuildFilterGraph` fails, `InitTempoProcessing` clears `m_tempoEnabled` and
`m_tempoAudioStreamIndex` so the dispatcher routes packets through the passthrough
branch rather than dereferencing a freed decoder context.

**Rebuild policy:** `SeekTime` rebuilds the graph only when
`m_tempoEmittedPackets < 10`. Startup-window seeks reset the filter cleanly;
mid-stream seeks keep the warm filter. The v0.3.7 unconditional rebuild caused an
audible pause at every skip. The general rule is in `kodi-inputstream`.

## Initial seek hold

With `start_time > 0`, a hold is armed in `Open()`. While active, packets carry
zero-filled PCM, so Kodi's format detection, `CAudioDecoder::Init` and `SeekTime`'s
wait-for-pts loop all complete while the sink plays silence until PAPlayer's
bookmark seek lands. Without it, ~50 ms of pts=0 audio leaks to the sink.

Clears on any `SeekTime(time)` where `time > 100 ms` — so PAPlayer's init
`SeekTime(0)` does not clear it, and the bookmark seek does. Safety timeout 2 s.

## Dual PTS

Packet `pts`/`dts` advance at **output** rate for ActiveAE; `dispTime` carries
**content** rate for the OSD. `GetTimes()` returns a dynamic `ptsStart` computed at
packet **pop**, updated by `UpdatePtsStartFromPop()` at both `DemuxRead` pop sites,
and invalidated on `SeekTime`/`DemuxFlush`. At tempo 1.0 the delta is 0.

Why pop rather than emit, and why this shape at all: `kodi-inputstream`.

## Build

```bash
./scripts/build.sh --os linux   --arch x86_64 --kodi 21 --kodi-src <kodi>
./scripts/build.sh --os android --arch armv7  --kodi 22 --kodi-src <kodi> --ndk <ndk>
```

Cross-compilation goes through Kodi's own depends system; the four Android traps
and the dependency-ordering race are in `kodi-android-ndk`. This add-on's
autotools chain is ffmpeg, gnutls, nettle, gmp, iconv and libzvbi.

## Channels and releases

This branch is **Omega** (Kodi 21, versions `21.y.z`, tags `v21.*`); the other is
**Piers** (Kodi 22, `22.y.z`). The major carries the Kodi version — see
`kodi-versions-abi`.

Workflows: `ci.yml` (gcc/clang/msvc + a PR zip), `release.yml` (6-platform matrix,
draft), `drift.yml` (weekly ABI-floor check), `notify-repo.yml`.

Publish drafts yourself — `kodi-addon-release` explains why a workflow cannot.

**Two things specific to this add-on:**

- **The inputstream ABI has no cushion on either channel** (MIN equals current,
  3.3.0 on Omega and 3.4.0 on Piers), so any upstream bump immediately splits the
  pinned build from current Kodi. `drift.yml` is what makes that arrive as a cron
  failure rather than a user report.
- **Windows builds are broken, and the failure is deliberately visible.** They
  compile and upload nothing. The job is `continue-on-error` so releases still ship
  the working platforms; the release step warns by name and lists the three places
  to change once it is fixed. See `kodi-addon-release` for the
  `if-no-files-found` default that made this silent in the first place.

Linux builds are **not** in a pinned container yet — this add-on builds far more
dependency surface than `pvr.kofin`, so the runner label is pinned meanwhile. The
reasoning for preferring a container is in `kodi-binary-build`.
