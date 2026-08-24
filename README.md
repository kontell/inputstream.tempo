[![License: GPL-2.0-or-later](https://img.shields.io/badge/License-GPL%20v2+-blue.svg)](LICENSE.md)

# inputstream.tempo

A Kodi inputstream add-on that changes playback speed **without changing pitch, and without Kodi's "Sync playback to display"** — for audio and for video.

It is a fork of [inputstream.ffmpegdirect](https://github.com/xbmc/inputstream.ffmpegdirect). The demuxer decodes the audio track, runs it through FFmpeg's `atempo` filter and hands Kodi PCM stamped at the *output* rate, so Kodi's clock keeps running at real time; video and subtitle packets are projected through the same content↔output time map, so they stay locked to the audio at any rate. Kodi's own tempo needs the display clock, and on a panel whose refresh rate is not a whole multiple of the frame rate that costs a fixed rate error of up to 4 %. This add-on does not.

Rates from **0.5× to 100×**; live changes land within a few hundred milliseconds.

## Who uses it

- **[KoShelf](https://github.com/kontell/KoShelf)** — audiobooks and podcasts from Audiobookshelf, with a speed dialog and keyboard shortcuts.
- **[Kofin](https://github.com/kontell/plugin.video.kofin)** — SyncPlay *fine sync*: while watching in a Jellyfin group, a member that has slipped from the group plays a few percent faster or slower for a few seconds instead of skipping. Kofin recommends this add-on as an optional dependency and needs **21.4.1 / 22.4.1 or later**.
- A [patched YouTube add-on](https://github.com/anxdpanic/plugin.video.youtube/compare/master...kontell:plugin.video.youtube:tempo) showed it works for that add-on's audio & video playback too.

## Installing

Zips are on the [releases page](https://github.com/kontell/inputstream.tempo/releases). Pick the one for your Kodi and platform and install it from *Add-ons → Install from zip file*.

| Kodi | Channel | Version |
| --- | --- | --- |
| 22 "Piers" | `Piers` branch, tags `v22.*` | `22.y.z` |
| 21 "Omega" | `Omega` branch, tags `v21.*` | `21.y.z` |

The major version is the Kodi version; the rest moves in step across both channels. Platforms: Linux (x86_64, aarch64, armv7), Android (aarch64, armv7) and Windows (x86_64).

The Linux zips carry their own libstdc++, so they run on any distribution's Kodi, the flatpak included.

## Using it from an add-on

Set these properties on the ListItem you resolve (all keys are `inputstream.tempo.…` except the first):

| Property | |
| --- | --- |
| `inputstream` | `inputstream.tempo` |
| `tempo` | Initial rate, e.g. `1.5`. Default `1.0`. |
| `tempo_file` | A file the add-on polls every 250 ms for a new rate. Write the number, atomically (write a temp file, rename). One file per playing add-on — do not share another add-on's. |
| `start_time` | Audio-only items under PAPlayer: the resume position in seconds. Arms a hold that plays silence until PAPlayer's bookmark seek lands, so no audio from the start of the file leaks out first. Never set it for video — VideoPlayer seeks before any output starts. |
| `queue_secs` | Depth of Kodi's demux queues in seconds, so time is reported at the playing point rather than the demux head: 8 on Kodi 21 (fixed), Kodi 22's *Audio/video queue time* setting (default 4). Default 8. |
| `lead_secs` | Video items only: an optional add-on-side bound on how far output may run ahead of real time. 0 (default) leaves pacing to Kodi's queues. |

The add-on writes **`<tempo_file>.state`** back — one JSON line, replaced atomically, on every applied rate change, anchor and audio re-target:

```json
{"seq": 7, "event": "tempo", "tempo": 1.0300, "content_ms": 88101.0, "output_ms": 87971.0, "delta_ms": 130.0, "queue_secs": 1.00, "video": true}
```

`seq` advancing with your rate in `tempo` is the confirmation that a write landed. `content_ms − output_ms` is the add-on's own account of how far a rate change has moved the position — it changes only while the rate is off 1.0, never at a seek or a flush — and `delta_ms` is the same quantity as last reported to Kodi, a queue depth behind.

Every audio track is advertised to Kodi as PCM (the source codec stays in the OSD), because any of them may be the one Kodi selects; the pipeline follows Kodi's audio-track choice. **Audio passthrough is therefore off for the stream** — the receiver gets multichannel PCM. Switching the tempo file back to `1.0` does not restore passthrough; that needs the item to play without the add-on.

Resume for video goes through Kodi's normal `setResumePoint` path unchanged. HLS transcodes open through FFmpeg's own HLS demuxer and have not been qualified for the rate-shifted path; plain files and `http(s)` streams open through Kodi's VFS and its cache.

## Keyboard control

`resources/keymap.xml` binds **Page Up / Page Down** (one step faster/slower), **=** (back to 1.0×) and **S** (a picker dialog) while the add-on is active. The keys act only while the sentinel `special://temp/inputstream_tempo_active` exists — KoShelf writes it; a SyncPlay session never does, so the keys cannot change a group member's speed.

The sentinel also says which files the keys should act on, so that two add-ons using tempo do not write over each other's rate. Write `key=value` lines:

```
addon=plugin.video.youtube
tempo_file=/…/temp/inputstream_tempo.plugin.video.youtube
config_file=/…/temp/inputstream_tempo_config.plugin.video.youtube
```

`config_file` holds the step and range as `{"step", "min", "max"}`. Content that names no `tempo_file` — including anything written before this contract existed — falls back to the shared `special://temp/inputstream_tempo` and `…_config`, so an add-on that has not moved to its own files keeps working unchanged.

**Remove the sentinel only if it is yours.** Kodi's player callbacks fire for everything played on the box, not only your own items, so an add-on that removes it unconditionally when playback ends takes the keys away from whatever else armed them.

## Status and limitations

- **PAPlayer** (audio-only items): seeking needs [xbmc/xbmc#28179](https://github.com/xbmc/xbmc/pull/28179), and correct progress display needs [this patch](https://github.com/xbmc/xbmc/compare/master...kontell:xbmc:fix/paplayer-display-time). Video items under VideoPlayer need neither.
- **Video**: accurate seeks, the OSD clock, external subtitles and audio-track switching all follow the time map; measured on Linux and three Android devices (software and hardware h264, HEVC and AV1 decoders) at rates up to 1.25× through seeks. A sustained rate change re-detects the frame rate and can cost one renderer rebuild a few seconds after a seek; no display-mode switch was seen on any device.
- **Dolby Vision in MKV on Android** loses its DV signalling through the inputstream ABI and plays as plain HEVC (fine for profile 8, wrong colours for profile 5). HDR10 static metadata and colour fields pass through.
- Everything in the stream is decoded and re-packaged by the add-on's own FFmpeg; that is a few percent of one ARM core for the audio track and nothing for video.

## Design and measurements

- [`docs/tempo-for-video.html`](docs/tempo-for-video.html) — the study that extended tempo from audio to video: why the display clock cannot be the answer, the content↔output map, the continuity rule across seeks, why time is reported at the playing point, and the plan it was built from.
- [`tests/live/results/av-tempo-video.md`](tests/live/results/av-tempo-video.md) — the add-on's rig results (desktop and Galaxy Tab); Kofin's [`tests/live/results/S4.8-fine-sync.md`](https://github.com/kontell/plugin.video.kofin/blob/main/tests/live/results/S4.8-fine-sync.md) covers four devices, real titles and the higher rates.
- [`tests/live/tempo_checklist.py`](tests/live/tempo_checklist.py) drives a Kodi through the measurements without any calling add-on in the path.

## Building

```bash
./scripts/build.sh --os linux   --arch x86_64 --kodi 22 --kodi-src <kodi>
./scripts/build.sh --os android --arch armv7  --kodi 22 --kodi-src <kodi> --ndk <ndk>
```

Cross builds go through Kodi's depends system. The time map has its own dependency-free test: `g++ -std=c++17 -I src/stream tests/tempomap_test.cpp -o /tmp/tempomap_test && /tmp/tempomap_test`. `CLAUDE.md` has the working notes for the code.

## License

GPL-2.0-or-later, as inputstream.ffmpegdirect.
