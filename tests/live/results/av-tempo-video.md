# Video-tempo checklist — results (2026-08-22)

Build 22.4.0 from PR #5, driven by `tests/live/tempo_checklist.py`. Two boxes,
both with the display clock **off** (the configuration the shakedown found
tightest): the local desktop flatpak Kodi (22.0-BETA1, freedesktop 25.08,
x86_64) and the Galaxy Tab S5e (Kodi 22.0-BETA1, Android armv7, 60 Hz-only
panel). Asset: a 10-minute 1920×1080 h264 timecode film at 23.976 fps with two
stereo AAC tracks (1 kHz beep default, 440 Hz second), played through a `.strm`
whose `#KODIPROP` lines route it to `inputstream.tempo` with `queue_secs` set to
the Kodi in use. Nothing here involves kofin.

Every figure is a least-squares fit of `Player.GetProperties` position against
the host clock; rate onset/offset use a breakpoint fit (two lines, one join),
so the dead time and the position step at the change are read off the same
model rather than a threshold on a jittery sample.

## Item 0 — the crash that came first

The very first video play **segfaulted** the flatpak Kodi (frame 0 in the
add-on's own `.so` at `typeinfo name for std::ios_base::failure`, frame 1
`CheckTempoFileUpdate`). Root cause was pre-existing and not the video change:
the Linux zips link libstdc++ statically but exported ~2,500 `std::` symbols, so
the `std::ifstream` in the tempo poll bound across the add-on's libstdc++ and
Kodi's. Fixed in this PR — C stdio for the tempo/state files plus
`-Wl,--exclude-libs,ALL` on the Linux link — and re-tested clean. koshelf's
audiobook path (its first poll is at read #50) would have hit the same crash on
any Linux Kodi whose libstdc++ differs from the build host's.

## Item 1 & 7 — the actuator moves the clock, with the display clock off

| box | queue_secs | free-run ppm | tempo 1.03 ppm | delta (want +30 000) | restored ppm |
|---|---|---|---|---|---|
| desktop | 4 | −53 ± 396 | +29 694 ± 371 | **+30 078** | −171 ± 362 |
| Tab S5e | 4 | +537 ± 419 | +29 642 ± 414 | **+30 029** | +392 ± 437 |
| desktop | 1 (queuetimesize 10) | +263 ± 397 | +30 135 ± 405 | **+28 966** | — |

The in-stream actuator works with `usedisplayasclock` **off** — the mode the
shakedown wanted and the one Kodi's native `SetTempo` cannot serve. Free-run and
restored rates sit within a few hundred ppm of real time, so a group would be
tight without any correction and the pulse only has to close jitter.

## Item 3 — readout bias, and the queue_secs correction

The position step at the rate change is the readout bias: 0 means the reported
position stayed continuous across the change, `(rate−1)×lead` means it jumped.

| box | queue_secs | step at 1.0→1.03 | step at 1.03→1.0 |
|---|---|---|---|
| desktop | 4 (matched) | **+5 ms** | +2 ms |
| desktop | 0 (legacy head) | +78 ms | −94 ms |
| desktop | 1 (matched) | +60 ms | −83 ms |
| Tab S5e | 4 (matched) | +44 ms | −91 ms |

With `queue_secs` set to the real queue depth the step collapses to a few ms on
the desktop — the readout is at the playing point, exactly what §4.3 of the
study designed. With `queue_secs=0` (the old head-of-demux reading) the same run
shows the predicted ~80–90 ms bias at 3 %. The Tab still shows ~40–90 ms at
queue_secs=4: its media clock and the demux head do not sit exactly a queue
depth apart on the Android sink, so the residual is real but bounded and one-
signed — a fixed lead to tune, not the ramping error the uncorrected path has.
`tempo_file.state` reported `delta_ms ≈ 960` throughout, i.e. the map's offset
tracked the ~1 s queue.

## Item 5 — accurate seeks through IPOSTIME

Seek targets, landed position (post-restart line at the instant motion resumed):

| box | tempo | 120.0 s | 305.5 s | 60.25 s | seek latency |
|---|---|---|---|---|---|
| Tab S5e | 1.03 | −149 ms | −179 ms | +75 ms | ~0.5 s |
| desktop (internal demuxer control) | 1.0 | −24 ms | −79 ms | +2 ms | ~0.6 s |
| desktop (add-on) | 1.03 | −379 ms | −399 ms | +27 ms | ~0.4 s |

At 1.0 the add-on path matches Kodi's own internal demuxer (−24/−79/+2 ms) — a
keyframe-only landing on this 48-frame GOP would have been up to 2 s early, so
`IPOSTIME` + the backward `PosTime` seek are doing their job. At 1.03 the desktop
lands ~380 ms early on the two forward seeks: Kodi resyncs the clock to the
**video's** first picture, which after the flush sits ~0.5 s behind the audio's
first frame (logged: video pts 118.376 vs audio 119.10 at the 120 s seek), and
at 3 % that offset is larger. This only bites a seek *issued while a pulse is
running*; a SyncPlay seek happens at rate 1.0 (pause → seek → unpause), where the
control run shows it lands accurately. Noted as a caveat, not a blocker.

## Item 6 — audio-track switch under tempo

Two tracks, switched mid-play with `Player.SetAudioStream` while tempo 1.03 was
running. On both boxes the clock kept advancing at ~30 000 ppm across the switch
(desktop +28 547→+30 882 ppm, Tab +29 618→+31 637), the OSD codec stayed
`pcm_f32le`, and the log shows `re-targeting the pipeline` then `audio anchored`
on the new track within one frame. The re-target path works.

## Item 4 — renderer rebuild on a held rate

A 20 s hold at 1.03 issued ~2 s after a seek. On the desktop this triggered
**2** `CRenderManager::Configure - framerate changed` events, because Kodi's
frame-rate detector re-measured 23.976→24.70 fps (23.976 × 1.03) and rebuilt the
renderer; it flipped back when tempo returned. The Tab logged the same fps
re-detection (`framerate was:23.976 calculated:24.695`) but **0** reconfigures in
the sampled window — the detector had already widened its window by the time the
pulse landed. This is the study's predicted behaviour: a sustained rate change a
few seconds after a seek can cost one renderer rebuild (a brief hiccup, no mode
switch); minutes into steady play the detection window is long enough that pulses
pass under it. A real display-mode switch never occurred on either box.

## Not covered here

- **A/V lip-sync through a pulse** (photo + beep) needs two devices side by side
  and is the rig's job; the frame counter and dual beeps in the asset are there
  for it.
- **HDR10 colour passthrough** and a real **mode switch** need a switching panel.
- The **Bravia/Pixel** arms of the shakedown rig, and the multi-device group.
