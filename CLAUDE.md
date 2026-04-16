# inputstream.tempo

Fork of inputstream.ffmpegdirect with built-in audio tempo (pitch-corrected playback speed) via FFmpeg's atempo filter. Binary Kodi addon (`kodi.inputstream`).

## Architecture

- `src/stream/FFmpegStream.cpp/.h` — main demuxer, tempo pipeline, seek, time reporting
- `src/StreamManager.cpp/.h` — addon entry point, property parsing, stream lifecycle
- `src/utils/Properties.h` — parsed ListItem properties
- `inputstream.tempo/resources/lib/runner.py` — Python background service (window properties, keymap install, debounced notifications)
- `inputstream.tempo/resources/lib/speed.py` — RunScript handler for keyboard/dialog speed control

## Tempo processing pipeline

In `FFmpegStream::AddStream()`, when tempo is enabled, `InitTempoProcessing()` builds an FFmpeg filter graph: `abuffer → atempo → aformat(f32) → abuffersink`. Audio packets are decoded, filtered, and re-packaged as PCM float32 in `ProcessAudioPacketWithTempo()`.

The tempo file (`special://temp/inputstream_tempo`) is polled every ~50 packets via `CheckTempoFileUpdate()`. Live tempo changes use `avfilter_graph_send_command()` when possible, falling back to a full graph rebuild.

## Key properties (set on ListItem by calling addon)

| Property | Purpose |
|---|---|
| `inputstream.tempo.tempo` | Initial playback speed (e.g. "1.5") |
| `inputstream.tempo.tempo_file` | Path to runtime tempo file |
| `inputstream.tempo.start_time` | Resume position in seconds — pre-sets m_currentPts for GetTime() display |

Resume seeking is NOT done by the inputstream. The calling addon sets PAPlayer's `audiobook_bookmark` property instead, which PAPlayer handles natively.

## PTS tracking with tempo

`m_tempoOutputPts` tracks the output PTS for tempo-processed packets. After a seek, `m_tempoSeekPending` is set; the first raw audio packet's DTS anchors `m_tempoOutputPts` to the actual seek landing (important for MP3 VBR where seeks can be imprecise). `m_currentPts` is updated from tempo output packets in DemuxRead so GetTime() advances correctly.

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

GitHub Actions: `build.yml` (GCC+Clang × Omega+master on push), `release.yml` (10-platform matrix on v* tag → draft release).
