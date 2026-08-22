#!/usr/bin/env python3
"""Live checklist for inputstream.tempo's video path, driven over JSON-RPC.

Nothing here touches kofin: it plays a .strm whose #KODIPROP lines route the
item through inputstream.tempo, writes the tempo file the add-on polls, and
reads the media clock back through Player.GetProperties. Every number is a
measurement against the host clock, never a value Kodi merely stored.

Scenarios (run one or more, in order):

  slope   Items 1 and 7 of the study checklist. Baseline window, then tempo
          1.03, then 1.0 again. Reports the free-running rate (ppm), the rate
          under tempo (want +30 000 ppm), the dead time from the file write to
          the slope change, and the position step at the change point — which
          is the readout bias: ~0 with queue_secs right, (rate-1)*queue with
          it wrong.
  seek    Item 5. Absolute seeks through the add-on; reports where each landed.
  track   Item 6. Switch audio stream under tempo; the clock must keep moving.
  hold    Item 4. Seek, then hold 1.03 for 20 s; reports CRenderManager
          reconfigure lines from the log in that window.

Usage:
  tempo_checklist.py --host 127.0.0.1:8080 --password PW \
      --strm "/media/.../tempo-q4.strm" --tempo-file ~/.var/app/tv.kodi.Kodi/data/temp/tempo_test \
      --log ~/.var/app/tv.kodi.Kodi/data/temp/kodi.log slope seek

  For an Android box, --tempo-file and --log are device paths and
  --adb SERIAL makes the script write/read them through adb.
"""

import argparse
import base64
import http.client
import json
import math
import os
import statistics
import subprocess
import sys
import time

#################################################################################################


class Kodi:
    def __init__(self, host, user, password):
        self.host = host
        self.auth = base64.b64encode(("%s:%s" % (user, password)).encode()).decode()
        self.conn = None
        self.playerid = 1

    def _send(self, payload, timeout=10):
        body = json.dumps(payload)
        for attempt in (0, 1):
            try:
                if self.conn is None:
                    h, _, p = self.host.partition(":")
                    self.conn = http.client.HTTPConnection(h, int(p or 8080), timeout=timeout)
                sent = time.monotonic()
                self.conn.request(
                    "POST",
                    "/jsonrpc",
                    body,
                    {"Content-Type": "application/json", "Authorization": "Basic " + self.auth},
                )
                resp = self.conn.getresponse()
                data = resp.read()
                received = time.monotonic()
                return sent, received, json.loads(data)
            except (http.client.HTTPException, OSError, ValueError):
                self.conn = None
                if attempt:
                    raise
        raise RuntimeError("unreachable")

    def call(self, method, params=None):
        payload = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params is not None:
            payload["params"] = params
        _, _, body = self._send(payload)
        if "error" in body:
            raise RuntimeError("%s: %s" % (method, body["error"]))
        return body.get("result")

    def position(self):
        """(host_s, pos_ms, unc_ms) from one Player.GetProperties round trip."""
        sent, received, body = self._send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "Player.GetProperties",
                "params": {"playerid": self.playerid, "properties": ["time", "speed"]},
            }
        )
        t = body["result"]["time"]
        pos = ((t["hours"] * 60 + t["minutes"]) * 60 + t["seconds"]) * 1000 + t["milliseconds"]
        return (sent + received) / 2.0, pos, (received - sent) * 500.0

    def active_player(self):
        players = self.call("Player.GetActivePlayers")
        if players:
            self.playerid = players[0]["playerid"]
            return players[0]
        return None


class Side:
    """Where the tempo file and kodi.log live: locally, or on an adb device."""

    def __init__(self, adb, tempo_file, log):
        self.adb = adb
        self.tempo_file = tempo_file
        self.log = log

    def write_tempo(self, value):
        text = "%.4f" % value
        if self.adb:
            subprocess.run(
                ["adb", "-s", self.adb, "shell", "echo %s > %s.tmp && mv %s.tmp %s"
                 % (text, self.tempo_file, self.tempo_file, self.tempo_file)],
                check=True,
            )
        else:
            tmp = self.tempo_file + ".tmp"
            with open(tmp, "w") as f:
                f.write(text)
            os.replace(tmp, self.tempo_file)
        return time.monotonic()

    def read_state(self):
        path = self.tempo_file + ".state"
        try:
            if self.adb:
                out = subprocess.run(["adb", "-s", self.adb, "shell", "cat " + path],
                                     capture_output=True, text=True).stdout
            else:
                with open(path) as f:
                    out = f.read()
            return json.loads(out.strip() or "{}")
        except Exception:
            return {}

    def log_lines(self, pattern):
        if self.adb:
            out = subprocess.run(
                ["adb", "-s", self.adb, "shell", "grep -F '%s' %s" % (pattern, self.log)],
                capture_output=True, text=True).stdout
        else:
            try:
                with open(self.log, errors="replace") as f:
                    out = "".join(line for line in f if pattern in line)
            except OSError:
                out = ""
        return [line.rstrip() for line in out.splitlines() if line.strip()]


#################################################################################################


def fit(series):
    """Least squares pos = a + b*t over (host_s, pos_ms). Returns (a, b_ppm, rms, stderr_ppm)."""
    if len(series) < 4:
        return None
    ts = [s[0] for s in series]
    ps = [s[1] for s in series]
    t0 = ts[0]
    xs = [t - t0 for t in ts]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ps) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ps)) / sxx  # ms per s
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ps)]
    rms = math.sqrt(sum(r * r for r in resid) / n)
    se = math.sqrt(sum(r * r for r in resid) / max(n - 2, 1) / sxx) if n > 2 else 0.0
    return {"t0": t0, "a": a, "b": b, "ppm": (b / 1000.0 - 1.0) * 1e6, "rms": rms,
            "stderr_ppm": se / 1000.0 * 1e6}


def predict(f, t):
    return f["a"] + f["b"] * (t - f["t0"])


def sample(kodi, seconds, hz=10.0, max_unc_ms=25.0):
    out = []
    end = time.monotonic() + seconds
    period = 1.0 / hz
    while time.monotonic() < end:
        t = time.monotonic()
        try:
            host, pos, unc = kodi.position()
            if unc <= max_unc_ms:
                out.append((host, pos, unc))
        except Exception:
            pass
        time.sleep(max(0.0, period - (time.monotonic() - t)))
    return out


def wait_for_playback(kodi, timeout=45.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            if kodi.active_player():
                _, pos, _ = kodi.position()
                if last is not None and pos > last + 100:
                    return True
                last = pos
        except Exception:
            pass
        time.sleep(0.5)
    return False


def start(kodi, strm):
    kodi.call("Player.Stop", {"playerid": kodi.playerid}) if kodi.active_player() else None
    time.sleep(1.0)
    kodi.call("Player.Open", {"item": {"file": strm}})
    if not wait_for_playback(kodi):
        raise SystemExit("playback did not start for %s" % strm)
    kodi.active_player()


def change_point(series, t_write, base_fit, window=40.0):
    """First sample after the write whose position runs ahead of the baseline
    fit by more than 3*rms + 15 ms — i.e. where the new rate became visible."""
    thresh = 3 * base_fit["rms"] + 15.0
    for host, pos, _ in series:
        if host < t_write:
            continue
        if pos - predict(base_fit, host) > thresh:
            return host
    return None


#################################################################################################


def scenario_slope(kodi, side, args):
    print("[slope] settling %.0fs" % args.settle)
    time.sleep(args.settle)
    side.write_tempo(1.0)
    print("[slope] baseline %.0fs" % args.window)
    base = sample(kodi, args.window)
    bf = fit(base)
    t_write = side.write_tempo(args.tempo)
    print("[slope] wrote tempo %.2f; sampling %.0fs" % (args.tempo, args.window + args.lead))
    fast_all = sample(kodi, args.window + args.lead)
    t_change = change_point(fast_all, t_write, bf)
    t_restore = side.write_tempo(1.0)
    print("[slope] restored 1.0; sampling %.0fs" % (args.window + args.lead))
    rest_all = sample(kodi, args.window + args.lead)
    state = side.read_state()

    report = {"base": bf, "state": state}
    if t_change is not None:
        fast = [s for s in fast_all if s[0] >= t_change + 1.0]
        ff = fit(fast)
        report["dead_time_s"] = round(t_change - t_write, 2)
        report["fast"] = ff
        if ff:
            # Position step at the change point: the fast fit extrapolated back
            # to t_change versus the baseline extrapolated forward. Zero means
            # the reported position was continuous, i.e. no readout bias.
            report["step_at_change_ms"] = round(predict(ff, t_change) - predict(bf, t_change), 1)
            report["delta_ppm"] = round(ff["ppm"] - bf["ppm"], 1)
    rf = fit([s for s in rest_all if s[0] >= t_restore + args.lead + 2.0])
    report["restored"] = rf
    if report.get("fast") and rf:
        ff = report["fast"]
        # Expected content gained by the pulse: (rate-1) x pulse length at the new rate
        t_rest_change = change_point(rest_all, t_restore, ff) if False else None
        report["restore_ppm"] = round(rf["ppm"], 1)
    print_report("slope", {
        "free_run_ppm": fmt_ppm(bf),
        "tempo_ppm": fmt_ppm(report.get("fast")),
        "delta_ppm": report.get("delta_ppm"),
        "want_delta_ppm": round((args.tempo - 1.0) * 1e6),
        "dead_time_s": report.get("dead_time_s"),
        "step_at_change_ms": report.get("step_at_change_ms"),
        "restored_ppm": fmt_ppm(rf),
        "state_file": state,
        "samples": (len(base), len(fast_all), len(rest_all)),
    })


def fmt_ppm(f):
    if not f:
        return None
    return "%+.0f ± %.0f (rms %.1f ms)" % (f["ppm"], f["stderr_ppm"], f["rms"])


def scenario_seek(kodi, side, args):
    side.write_tempo(args.seek_tempo)
    time.sleep(args.lead + 2.0)
    results = []
    for target_s in args.seek_targets:
        h, m = divmod(int(target_s), 3600)
        m, s = divmod(m, 60)
        ms = int(round((target_s - int(target_s)) * 1000))
        kodi.call("Player.Seek", {"playerid": kodi.playerid,
                                  "value": {"time": {"hours": h, "minutes": m, "seconds": s, "milliseconds": ms}}})
        t_seek = time.monotonic()
        time.sleep(2.5)
        host, pos, _ = kodi.position()
        # back out the playback since the seek: landed = pos - (elapsed x rate)
        elapsed_ms = (host - t_seek) * 1000.0 * args.seek_tempo
        results.append({"target_s": target_s, "reported_s": round(pos / 1000.0, 3),
                        "landed_est_s": round((pos - elapsed_ms) / 1000.0, 3),
                        "error_est_ms": round(pos - elapsed_ms - target_s * 1000.0)})
        print("[seek] target %.3f → reported %.3f, landed ≈ %.3f (%+d ms)" % (
            target_s, pos / 1000.0, (pos - elapsed_ms) / 1000.0, results[-1]["error_est_ms"]))
    side.write_tempo(1.0)
    print_report("seek", {"tempo": args.seek_tempo, "results": results,
                          "log": side.log_lines("demuxer seek to")[-6:]})


def scenario_track(kodi, side, args):
    side.write_tempo(args.tempo)
    time.sleep(args.lead + 2.0)
    before = fit(sample(kodi, 10.0))
    streams = kodi.call("Player.GetProperties", {"playerid": kodi.playerid,
                                                 "properties": ["audiostreams", "currentaudiostream"]})
    n = len(streams["audiostreams"])
    cur = streams["currentaudiostream"]["index"]
    nxt = (cur + 1) % n if n > 1 else cur
    kodi.call("Player.SetAudioStream", {"playerid": kodi.playerid, "stream": nxt})
    t_switch = time.monotonic()
    time.sleep(4.0)
    after = fit(sample(kodi, 10.0))
    now = kodi.call("Player.GetProperties", {"playerid": kodi.playerid,
                                             "properties": ["currentaudiostream"]})["currentaudiostream"]
    side.write_tempo(1.0)
    print_report("track", {
        "streams": n, "from": cur, "to": nxt, "now": now.get("index"),
        "now_codec": now.get("codec"), "now_name": now.get("name"),
        "ppm_before": fmt_ppm(before), "ppm_after": fmt_ppm(after),
        "retarget_log": side.log_lines("re-targeting")[-2:],
        "anchor_log": side.log_lines("audio anchored")[-2:],
        "state": side.read_state(),
    })


def scenario_hold(kodi, side, args):
    kodi.call("Player.Seek", {"playerid": kodi.playerid,
                              "value": {"time": {"hours": 0, "minutes": 1, "seconds": 30, "milliseconds": 0}}})
    time.sleep(2.0)
    t0 = time.monotonic()
    before = side.log_lines("CRenderManager::Configure - change configuration")
    side.write_tempo(args.tempo)
    time.sleep(20.0)
    side.write_tempo(1.0)
    time.sleep(args.lead + 10.0)
    after = side.log_lines("CRenderManager::Configure - change configuration")
    fps = side.log_lines("framerate was:")
    print_report("hold", {"reconfigures_during": len(after) - len(before),
                          "new_lines": after[len(before):][-4:],
                          "fps_redetect": fps[-3:], "elapsed_s": round(time.monotonic() - t0, 1)})


def print_report(name, data):
    print("=== %s ===" % name)
    print(json.dumps(data, indent=2, default=str))


#################################################################################################


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1:8080")
    ap.add_argument("--user", default="kodi")
    ap.add_argument("--password", default=os.environ.get("KODI_PASSWORD", ""))
    ap.add_argument("--strm", required=True, help="path of the .strm as Kodi sees it")
    ap.add_argument("--tempo-file", required=True, help="tempo file path (device path with --adb)")
    ap.add_argument("--log", default="", help="kodi.log path (device path with --adb)")
    ap.add_argument("--adb", default="", help="adb serial; tempo file and log are then on the device")
    ap.add_argument("--tempo", type=float, default=1.03)
    ap.add_argument("--window", type=float, default=30.0)
    ap.add_argument("--settle", type=float, default=10.0)
    ap.add_argument("--lead", type=float, default=6.0, help="worst-case dead time to allow for")
    ap.add_argument("--seek-tempo", type=float, default=1.03)
    ap.add_argument("--seek-targets", type=float, nargs="*", default=[120.0, 305.5, 60.25])
    ap.add_argument("--no-start", action="store_true", help="use whatever is already playing")
    ap.add_argument("scenarios", nargs="+", choices=["slope", "seek", "track", "hold"])
    args = ap.parse_args(argv)

    kodi = Kodi(args.host, args.user, args.password)
    side = Side(args.adb, args.tempo_file, args.log)
    side.write_tempo(1.0)
    if not args.no_start:
        start(kodi, args.strm)
    else:
        kodi.active_player()
    for name in args.scenarios:
        globals()["scenario_" + name](kodi, side, args)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
