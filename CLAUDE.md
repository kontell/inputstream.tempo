# inputstream.tempo

Fork of inputstream.ffmpegdirect with built-in audio tempo (pitch-corrected playback speed) via FFmpeg's atempo filter. Binary Kodi addon (`kodi.inputstream`).

## Architecture

- `src/stream/FFmpegStream.cpp/.h` — main demuxer, tempo pipeline, seek, time reporting
- `src/StreamManager.cpp/.h` — addon entry point, property parsing, stream lifecycle
- `src/utils/Properties.h` — parsed ListItem properties
- `inputstream.tempo/resources/lib/runner.py` — Python background service (window properties, keymap install, debounced notifications)
- `inputstream.tempo/resources/lib/speed.py` — RunScript handler for keyboard/dialog speed control

## Tempo processing pipeline

In `FFmpegStream::AddStream()`, when tempo is enabled, `InitTempoProcessing()` builds an FFmpeg filter graph: `abuffer → atempo → aformat(f32) → abuffersink`. Audio packets are decoded, filtered, and re-packaged as PCM float32 in `ProcessAudioPacketWithTempo()`. Output goes into `m_tempoOutputQueue`; `DemuxRead()` pops from it.

The tempo file (`special://temp/inputstream_tempo`) is polled every ~50 packets via `CheckTempoFileUpdate()`. Live tempo changes use `avfilter_graph_send_command()` when possible, falling back to a full graph rebuild.

FFmpeg 6's matroska/webm demuxer leaves the codec context's `sample_rate` / `ch_layout` / `sample_fmt` unpopulated for Opus until the first packet decodes — the values live in `codecpar` but not in the context. `InitTempoProcessing` defensively backfills from `codecpar` after `avcodec_open2`, otherwise `BuildFilterGraph` would build `time_base=1/0` and `abuffer` creation would fail. FFmpeg 7 fills them up front; this only matters on Kodi builds bundling FFmpeg 6 (e.g. our patched build with `ENABLE_INTERNAL_FFMPEG=ON`).

If `BuildFilterGraph` fails despite the backfill, `InitTempoProcessing` clears `m_tempoEnabled` and `m_tempoAudioStreamIndex` so the demux dispatcher routes packets through the passthrough branch instead of dereferencing the freed decoder context.

## Key properties (set on ListItem by calling addon)

| Property | Purpose |
|---|---|
| `inputstream.tempo.tempo` | Initial playback speed (e.g. "1.5") |
| `inputstream.tempo.tempo_file` | Path to runtime tempo file (atomic write triggers live tempo change) |
| `inputstream.tempo.start_time` | Resume position in seconds — pre-sets `m_currentPts` for `GetTime()` display **and** arms the initial seek hold (see below) |

Resume seeking is NOT done by the inputstream. The calling addon sets PAPlayer's `audiobook_bookmark` property instead, which PAPlayer handles natively.

## Initial seek hold

When `start_time > 0` is set, an internal hold is armed in `Open()`. While active, packets emitted to `m_tempoOutputQueue` carry zero-filled PCM (silence) instead of real samples — Kodi's format detection, `CAudioDecoder::Init`, and `SeekTime`'s wait-for-pts loop all see normal-shaped packets so they complete, but the audio sink plays silence until PAPlayer's bookmark seek lands. Without this, ~50 ms of pts=0 audio leaks to the sink between `OpenSink` and the bookmark seek (audible at resume start).

The hold clears on any `SeekTime(time)` where `time > 100 ms` (i.e. PAPlayer's init `SeekTime(0)` doesn't clear it; the bookmark seek does). Safety timeout: 2 s — if no seek arrives, the hold releases and packets emit real audio.

## Dual PTS: output rate vs content rate

ActiveAE schedules audio against packet `pts/dts`, so they must advance at the **output** rate (the rate samples are consumed by the sink). The OSD wants **content** rate (the actual position in the source file, advancing at tempo-adjusted speed). At non-1× tempo the two diverge.

`ProcessAudioPacketWithTempo` writes both:
- `outPkt->pts = outPkt->dts = m_tempoOutputPts` (advances by `nb_samples / sample_rate` per packet — output rate)
- `outPkt->dispTime = m_tempoContentPts / STREAM_TIME_BASE * 1000` ms (advances by `outputDuration × tempo` — content rate)

After a seek, `m_tempoSeekPending` is set; the first raw audio packet's DTS anchors both `m_tempoOutputPts` and `m_tempoContentPts` to the actual seek landing (important for MP3 VBR where seeks can be imprecise).

`m_currentPts` is updated from `dispTime` when packets pop out of `m_tempoOutputQueue`, so `GetTime()` (used by PAPlayer) tracks content position.

## VideoPlayer OSD: dynamic ptsStart

VideoPlayer computes `state.time = m_clock.GetClock() − ptsStart`, and `m_clock` is locked to packet pts (output rate). To make the OSD track content time, `GetTimes()` returns a dynamic `ptsStart` updated at packet **pop** (not emit):

```
ptsStart = popped_packet.pts (output µs) − STREAM_MSEC_TO_TIME(dispTime) (content µs)
```

Substituting back: `state.time ≈ m_clock − (output − content) ≈ content`. Reading at pop bounds the value by Kodi's actual consumption rate — the v0.3.4 emit-time variant drifted ahead and made `state.time` explode.

`UpdatePtsStartFromPop()` is wired at both `DemuxRead` pop sites. `SeekTime` and `DemuxFlush` invalidate the cached value via `m_ptsStartDynamicValid = false` so the old delta doesn't survive a position change. At tempo `1.0` the delta is 0 and behaviour matches a static `ptsStart=0`.

## Filter graph rebuild policy

atempo carries internal sample history across `avcodec_flush_buffers`, so post-seek frames blend residual pre-seek samples with new input — audible click at stream start (PAPlayer's init `SeekTime(0)` immediately follows the first emit) and at user seeks. `SeekTime` rebuilds the filter graph **only when `m_tempoEmittedPackets < 10`** — startup-window seeks reset the filter cleanly; mid-stream user seeks keep the warm filter and skip the rebuild gap (the v0.3.7 unconditional rebuild caused an audible pause at every skip).

## Stream analysis optimization

For tempo-enabled streams, `analyzeduration=500000` (0.5s) and `probesize=131072` (128KB) are set before `avformat_find_stream_info()`. Audiobook/podcast containers have codec params in headers; the default 5s/5MB analysis was the main startup bottleneck.

## Cross-compile notes

The `scripts/build.sh` handles cross-compilation for Linux ARM and Android:
- `CPU` must be set as a CACHE var in the toolchain file (Kodi's HandleDepends doesn't forward it)
- Android needs per-target NDK clang wrappers (ffmpeg's configure doesn't read CMAKE_C_COMPILER_TARGET)
- Autoconf deps (gnutls, nettle, gmp, iconv, libzvbi) need `--host` and `CC`/`CXX` from env
- `PKG_CONFIG_LIBDIR` is pinned to the cross-built deps dir to avoid host-system lib pollution
- gnutls built with `--without-zstd --without-brotli` (host detection breaks cross-compile)
- libzvbi depends on iconv (explicit dep in deps.txt to prevent race condition)

## Build

```bash
./scripts/build.sh --os linux --arch x86_64 --kodi 21 --kodi-src ~/xbmc
./scripts/build.sh --os android --arch armv7 --kodi 22 --kodi-src ~/xbmc --ndk ~/android-ndk-r25c
```

## CI and releases

This branch is **Omega** and builds **Kodi 21 only**; the other channel is the `Piers` branch at `22.y.z`. Versions here are `21.y.z` and tags are `v21.y.z` — the major carries the Kodi version, which is what `repository.kontell` uses to file a build under `omega/` or `piers/`.

- `ci.yml` — every PR and push: gcc/clang/msvc compile checks plus a `package` job uploading an installable PR zip.
- `release.yml` — on a `v21.*` tag: 6-platform matrix, then a draft release. Asserts the tag matches `addon.xml.in` and that its major is 21.
- `drift.yml` — weekly: asserts upstream's declared ABI floor is still one our pinned build satisfies.
- `notify-repo.yml` — announces a published release to `repository.kontell`. Publish the draft yourself; one published by a workflow using the default `GITHUB_TOKEN` raises no event.

Kodi is pinned at `21.3-Omega` rather than tracking a branch: `@ADDON_DEPENDS@` is filled from those headers, so an unpinned ref moves the declared `kodi.binary.instance.inputstream` version with no commit here. **The inputstream ABI has no cushion on either channel** (MIN equals current, 3.3.0 on Omega and 3.4.0 on Piers), so any upstream bump immediately splits the pinned build from current Kodi — `drift.yml` watches for it.

**Windows builds are broken and the failure is deliberately visible.** They compile successfully and upload nothing, because `actions/upload-artifact` defaults to `if-no-files-found: warn`: v0.3.11 attached 10 assets from 12 green jobs, and `piers/inputstream.tempo+windows-x86_64` has never existed in the served repository. The job is `continue-on-error` so releases still ship the platforms that work; the release step warns by name, and lists the three places to change once it is fixed.

Unlike `pvr.kofin`, the Linux builds are **not** in a pinned container yet — this addon builds FFmpeg plus gnutls, nettle, gmp, iconv and libzvbi through autotools, which is far more dependency surface to move into a bare image. The runner label is pinned meanwhile.
