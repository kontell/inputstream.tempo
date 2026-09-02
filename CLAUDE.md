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
| `src/stream/TempoMap.h` | the content↔output time map every stream is projected through (header-only; `tests/tempomap_test.cpp`) |
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
| `inputstream.tempo.start_time` | resume position in seconds — pre-sets `m_currentPts` for `GetTime()` **and** arms the initial seek hold (audio-only items; never for video) |
| `inputstream.tempo.queue_secs` | depth of Kodi's demux queues in seconds: 8 on Omega (hard-coded), Kodi 22's `videoplayer.queuetimesize` on Piers (default 4). Time is reported this far behind the demux head. Default 8 |
| `inputstream.tempo.lead_secs` | optional add-on-side lead bound for video items; 0 (default) leaves pacing to Kodi's queues |

The add-on writes back to **`<tempo_file>.state`** — one JSON line, replaced
atomically, on every applied tempo change, anchor and audio re-target:
`{"seq","event","tempo","content_ms","output_ms","delta_ms","queue_secs","video","source_ms","player_ms"}`.
A caller confirms a change landed by watching `seq`/`event`. `source_ms` is the head on
the container's own clock (`SourceStartSecs()` added back — the start `ConvertTimestamp()`
subtracts) and `player_ms` the player-clock reading for that head in the stream class's
own frame (`HeadPlayerMs()`: content time here, the shifted output clock for a catchup
stream); a SyncPlay member reads the shared source clock as `getTime() + (source_ms −
player_ms)`.

**Resume seeking is not done here.** The calling add-on sets PAPlayer's
`audiobook_bookmark`, which PAPlayer applies natively before audio output begins.
See `kodi-playback-resume`.

## Tempo pipeline

`FFmpegStream::AddStream()` → `InitTempoProcessing()` builds
`abuffer → atempo → aformat(f32) → abuffersink`. Audio packets are decoded,
filtered, and re-packaged as PCM float32 in `ProcessAudioPacketWithTempo()`; output
goes to `m_tempoOutputQueue`, and `DemuxRead()` pops from it.

**Every audio stream is advertised as PCM f32** (source codec/bitrate kept for
the OSD), because any of them may be the one Kodi selects. The pipeline is
brought up on the first audio stream met and **re-targeted in `OpenStream(id)`**
(`RetargetTempoAudio`) to whichever track Kodi opens — Kodi re-reads the stream
properties after `OpenStream` returns true, which is what makes this work. The
other audio tracks get `AVDISCARD_ALL` and their packets never reach Kodi. If the
new track cannot be decoded, tempo switches off and all audio streams are
re-advertised with their real codecs.

**Tempo at read-out (timeshift).** `TimeshiftStream` fills its disk buffer from
an input thread that runs `FFmpegStream::DemuxRead()` at the source's pace and
serves Kodi from the buffer. A rate stage on that input side acts on packets Kodi
consumes only once the buffer has drained, and the tempo file gets polled at the
source's segment cadence — measured on a live HLS: a SyncPlay pulse never
confirmed. So a class that serves from a buffer sets `m_tempoAtReadout`:
`ReadNew()` (gated by `TempoOnInput()`) then stores raw content-domain packets,
and `ApplyTempoOnRead()` does on the way out what `ReadNew()` does on the way in
— the tempo audio stream is rebuilt into an `AVPacket` (`ToStreamTimestamp()`,
the inverse of `ConvertTimestamp()`) and run through
`ProcessAudioPacketWithTempo()`, other audio is dropped, video and subtitles
go through `ProjectPacket()`. The poll (`PollTempoFile()`), the seek flush
(`FlushTempoForSeek()`) and the Δ-folded `GetTimes()` (ptsStart = −Δ, the buffer
bounds shifted alike) all live on Kodi's read side, so the OSD, `getTime()` and
seek targets read content time there as they do for a plain stream. The input
thread never touches the map, the decoder or the state file; the read side
never walks `m_streams`.

The tempo file is polled by wall clock every 250 ms (`kTempoPollInterval`) via
`CheckTempoFileUpdate()`. Live changes use `avfilter_graph_send_command()` where
possible, falling back to a full graph rebuild. Each change starts a new map
segment (below) at the audio's next output packet.

If `BuildFilterGraph` fails, `InitTempoProcessing` clears `m_tempoEnabled` and
`m_tempoAudioStreamIndex` so the dispatcher routes packets through the passthrough
branch rather than dereferencing a freed decoder context.

**Seek probe keeps its packets.** `SeekTime` reads packets after `av_seek_frame`
to learn where it landed; they go to `m_pendingPackets` and `DemuxRead` returns
them first (upstream frees them, so every decoder started mid-GOP after a seek —
HEVC logged it, a Pixel 7's AV1 decoder wedged on it). `DemuxFlush`, which Kodi
calls right after `PosTime`, must leave that queue alone; `Dispose` frees it.

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

**Not armed for video items** (`m_hasVideo`): VideoPlayer seeks the demuxer
before any output starts, so the hold would only delay the first picture.

## Two domains, one map

Packet `pts`/`dts` advance at **output** rate for ActiveAE; the OSD wants
**content** time. `src/stream/TempoMap.h` holds the piecewise-linear map between
them (slope `1/rate` per segment, a new segment per tempo change) and **every
stream goes through it**:

- audio: `m_tempoContentPts`/`m_tempoOutputPts` walk the map (content advances
  `out × rate` per output packet); they anchor on the **first decoded frame's
  timestamp** (`best_effort_timestamp`, with `pkt_timebase` set so codec priming
  is already stripped), not the packet dts;
- video and subtitles: `ProjectPacket()` maps `pts`, `dts` and `duration` in
  `DemuxRead`'s non-tempo branch. Data untouched.

**Continuity rule.** Δ = content − output changes only while rate ≠ 1 — never at
a seek or a flush. `ResetTempoMapForSeek()` carries the last Δ Kodi saw
(`m_deltaReported`, else Δ at the head) into the next anchor. That is what makes
Kodi's own accurate-seek arithmetic (`startpts = target − time_offset`) land, and
`SeekTime` returns `*startpts` through the map for the same reason.

**Time is reported at the playing point.** `GetTimes()` returns
`ptsStart = −Δ(head − queue_secs)`, not Δ at the head: the head runs a queue
depth ahead of what is playing, and Δ at the head is wrong by `(rate − 1) ×
queue` while a tempo change runs. Audio-only items use 0 (legacy behaviour;
PAPlayer never calls `GetTimes`).

**Capability flags.** `IPOSTIME` is advertised only for video items with tempo
on: VideoPlayer then passes seek targets in content time and calls
`PosTime()` + `DemuxFlush()`; `PosTime` seeks **backward** itself because Kodi
drops its flag on that path. Audio-only items keep the legacy flag set so
PAPlayer's seek/flush sequence is untouched. Why each flag matters:
`kodi-inputstream`.

**Pacing.** The 2 s wall-clock throttle (sleeping inside `DemuxRead`) applies to
audio-only items only. For video, `DemuxRead` runs on VideoPlayer's own loop, so
Kodi's queues pace delivery; `lead_secs > 0` re-enables a bound as empty packets
with a 10 ms nap. Keep it that way — a long sleep there delays every pause and
seek.

Test the map without Kodi or FFmpeg:

```bash
g++ -std=c++17 -I src/stream tests/tempomap_test.cpp -o /tmp/tempomap_test && /tmp/tempomap_test
```

## Build

```bash
./scripts/build.sh --os linux   --arch x86_64 --kodi 21 --kodi-src <kodi>
./scripts/build.sh --os android --arch armv7  --kodi 22 --kodi-src <kodi> --ndk <ndk>
```

**The Linux zips carry a static libstdc++, so no iostreams in the add-on.**
CI links with `-static-libstdc++ -static-libgcc -Wl,--exclude-libs,ALL`; without
the `--exclude-libs` the `.so` exported 2,499 `std::` symbols and an
`std::ifstream` bound across the add-on's copy and Kodi's, crashing the flatpak
Kodi on the first tempo-file poll. Read and write files with C stdio
(`CheckTempoFileUpdate`, `WriteTempoState`); `std::string`/containers are fine.

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
- **Windows builds ship again** (22.4.1 / 21.4.1 carried an 11 MB `windows-x86_64` zip) and
  `release.yml` lists `windows-x86_64` among the required assets, so a release with none
  fails rather than shipping silently empty — the `if-no-files-found` default that once hid
  this is in `kodi-addon-release`.

Linux builds are **not** in a pinned container yet — this add-on builds far more
dependency surface than `pvr.kofin`, so the runner label is pinned meanwhile. The
reasoning for preferring a container is in `kodi-binary-build`.
