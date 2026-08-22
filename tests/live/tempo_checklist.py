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


def ensure_addon_enabled(kodi, addonid="inputstream.tempo"):
    """Kodi registers a freshly dropped-in (or swapped) add-on disabled, and a
    disabled inputstream makes the #KODIPROP a no-op: the item then plays
    through the internal demuxer and every number below measures the wrong
    thing while looking plausible."""
    details = kodi.call("Addons.GetAddonDetails", {"addonid": addonid, "properties": ["enabled", "version"]})
    addon = details.get("addon", {})
    if not addon.get("enabled"):
        print("[start] %s %s was disabled — enabling" % (addonid, addon.get("version")))
        kodi.call("Addons.SetAddonEnabled", {"addonid": addonid, "enabled": True})
        time.sleep(2.0)
        details = kodi.call("Addons.GetAddonDetails", {"addonid": addonid, "properties": ["enabled"]})
        if not details.get("addon", {}).get("enabled"):
            raise SystemExit("%s could not be enabled" % addonid)
    else:
        print("[start] %s %s enabled" % (addonid, addon.get("version")))


def start(kodi, strm):
    ensure_addon_enabled(kodi)
    kodi.call("Player.Stop", {"playerid": kodi.playerid}) if kodi.active_player() else None
    time.sleep(1.0)
    kodi.call("Player.Open", {"item": {"file": strm}})
    if not wait_for_playback(kodi):
        raise SystemExit("playback did not start for %s" % strm)
    kodi.active_player()


def breakpoint_fit(series, t_write, min_side=4.0):
    """Two independent straight lines with one breakpoint after t_write,
    chosen to minimise the total squared residual. Returns the breakpoint and
    both fits, or None. Far less sensitive to position jitter than a threshold
    on the first deviating sample, which lags a 3 % rate change by seconds
    when readings jitter by ±60 ms."""
    best = None
    cands = [s[0] for s in series if s[0] >= t_write + min_side]
    for tb in cands:
        pre = [s for s in series if s[0] < tb]
        post = [s for s in series if s[0] >= tb]
        if len(pre) < 10 or len(post) < 10:
            continue
        if post[-1][0] - tb < min_side:
            break
        f1, f2 = fit(pre), fit(post)
        if not f1 or not f2:
            continue
        sse = f1["rms"] ** 2 * len(pre) + f2["rms"] ** 2 * len(post)
        if best is None or sse < best[0]:
            best = (sse, tb, f1, f2)
    if best is None:
        return None
    _, tb, f1, f2 = best
    return {"t_break": tb, "pre": f1, "post": f2,
            "step_ms": predict(f2, tb) - predict(f1, tb)}


def dump(args, name, payload):
    if not args.dump:
        return
    os.makedirs(args.dump, exist_ok=True)
    with open(os.path.join(args.dump, name + ".json"), "w") as f:
        json.dump(payload, f)


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
    t_restore = side.write_tempo(1.0)
    print("[slope] restored 1.0; sampling %.0fs" % (args.window + args.lead))
    rest_all = sample(kodi, args.window + args.lead)
    state = side.read_state()
    dump(args, "slope", {"t_write": t_write, "t_restore": t_restore, "tempo": args.tempo,
                         "base": base, "fast": fast_all, "rest": rest_all, "state": state})

    # Onset: breakpoint fit over baseline tail + tempo window. The pre-line is
    # the baseline rate, the post-line the tempo rate; the step between them at
    # the breakpoint is the readout bias (zero = position stayed continuous).
    on = breakpoint_fit(base[-150:] + fast_all, t_write)
    off = breakpoint_fit(fast_all[-150:] + rest_all, t_restore)
    out = {
        "free_run_ppm": fmt_ppm(bf),
        "want_delta_ppm": round((args.tempo - 1.0) * 1e6),
        "state_file": state,
        "samples": (len(base), len(fast_all), len(rest_all)),
    }
    if on:
        out.update({
            "tempo_ppm": fmt_ppm(on["post"]),
            "delta_ppm": round(on["post"]["ppm"] - on["pre"]["ppm"], 1),
            "dead_time_on_s": round(on["t_break"] - t_write, 2),
            "step_on_ms": round(on["step_ms"], 1),
        })
    if off:
        out.update({
            "restored_ppm": fmt_ppm(off["post"]),
            "dead_time_off_s": round(off["t_break"] - t_restore, 2),
            "step_off_ms": round(off["step_ms"], 1),
        })
    print_report("slope", out)


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
        # Sample through the seek: the position sits still while Kodi flushes
        # and decodes up to the target, then moves. The landed position is the
        # post-restart line evaluated at the instant motion resumed — the
        # seek's own latency must not be mistaken for a landing error.
        series = sample(kodi, 4.0, hz=20.0)
        moving = [s for s in series if s[0] > t_seek + 0.3]
        restart = None
        for i in range(1, len(moving)):
            if moving[i][1] > moving[i - 1][1] + 20 and abs(moving[i][1] - target_s * 1000.0) < 5000:
                restart = moving[i - 1][0]
                break
        f = fit([s for s in moving if restart is not None and s[0] >= restart + 0.3])
        if restart is None or not f:
            results.append({"target_s": target_s, "landed_s": None, "note": "no restart seen"})
            print("[seek] target %.3f -> no restart seen" % target_s)
            continue
        landed = predict(f, restart)
        results.append({"target_s": target_s, "landed_s": round(landed / 1000.0, 3),
                        "error_ms": round(landed - target_s * 1000.0),
                        "seek_latency_s": round(restart - t_seek, 2),
                        "rate_after_ppm": round(f["ppm"])})
        print("[seek] target %.3f -> landed %.3f (%+d ms) after %.2fs" % (
            target_s, landed / 1000.0, results[-1]["error_ms"], restart - t_seek))
        dump(args, "seek-%g" % target_s, {"t_seek": t_seek, "series": series})
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
    before = side.log_lines("CRenderManager::Configure")
    side.write_tempo(args.tempo)
    time.sleep(20.0)
    side.write_tempo(1.0)
    time.sleep(args.lead + 10.0)
    after = side.log_lines("CRenderManager::Configure")
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
    ap.add_argument("--dump", default="", help="directory to write raw samples to (JSON per scenario)")
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
