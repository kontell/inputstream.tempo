"""Speed control commands for inputstream.tempo. Called via RunScript.

Commands:
    speed_up     bump tempo by one step, clamped to max
    speed_down   drop tempo by one step, clamped to min
    speed_reset  set tempo to 1.0x
    dialog       show a picker dialog of all stepped values from min to max

Which rate and config file to act on comes from the sentinel — the calling
addon names them there, so two addons that both drive tempo do not write over
each other. Addons that predate that contract get the shared legacy paths.

Config is JSON with keys step, min, max, written by the calling addon (e.g.
KoShelf). Defaults are used if the file is missing.
"""

import json
import sys
import time

import xbmcgui
import xbmcvfs

import os

# Legacy shared paths, used when the sentinel does not name a set of its own.
TEMPO_FILE = xbmcvfs.translatePath('special://temp/inputstream_tempo')
CONFIG_FILE = xbmcvfs.translatePath('special://temp/inputstream_tempo_config')
NOTIFY_FILE = xbmcvfs.translatePath('special://temp/inputstream_tempo_notify')
# Sentinel written by the calling addon while tempo is the active inputstream.
# Keys/dialog are no-ops if missing, so bindings don't affect non-tempo playback.
ACTIVE_FILE = xbmcvfs.translatePath('special://temp/inputstream_tempo_active')

DEFAULT_STEP = 0.10
DEFAULT_MIN = 0.5
DEFAULT_MAX = 5.0


def resolve_files():
    """Return the (tempo, config) paths the playing addon is using.

    The sentinel may carry 'key=value' lines naming them. Anything that does
    not parse — including the bare item id KoShelf wrote before this existed
    — means an addon that has not moved to its own files, so the shared ones
    are still the right answer for it.
    """
    try:
        with open(ACTIVE_FILE) as f:
            content = f.read()
    except (IOError, OSError):
        return TEMPO_FILE, CONFIG_FILE

    fields = {}
    for line in content.splitlines():
        key, sep, value = line.partition('=')
        if sep:
            fields[key.strip()] = value.strip()

    tempo_file = fields.get('tempo_file')
    if not tempo_file:
        return TEMPO_FILE, CONFIG_FILE
    return tempo_file, fields.get('config_file') or CONFIG_FILE


def read_config(config_file=CONFIG_FILE):
    try:
        with open(config_file) as f:
            cfg = json.load(f)
        step = float(cfg.get('step', DEFAULT_STEP))
        lo = float(cfg.get('min', DEFAULT_MIN))
        hi = float(cfg.get('max', DEFAULT_MAX))
    except (IOError, ValueError, TypeError):
        step, lo, hi = DEFAULT_STEP, DEFAULT_MIN, DEFAULT_MAX
    # Guard against bad data — must have a usable range and positive step.
    if step <= 0 or lo > hi:
        step, lo, hi = DEFAULT_STEP, DEFAULT_MIN, DEFAULT_MAX
    return step, lo, hi


def read_tempo(tempo_file=TEMPO_FILE):
    try:
        with open(tempo_file) as f:
            return float(f.read().strip())
    except Exception:
        return 1.0


def write_tempo(val, tempo_file=TEMPO_FILE):
    # Atomically, as the add-on polls this file while it is being replaced.
    tmp = tempo_file + '.tmp'
    with open(tmp, 'w') as f:
        f.write(str(val))
    os.replace(tmp, tempo_file)


def set_props(speed):
    win = xbmcgui.Window(10000)
    win.setProperty('InputstreamTempo.Speed', str(speed))
    win.setProperty('InputstreamTempo.SpeedDisplay', format_speed(speed))


def format_speed(speed):
    return '{:.2f}x'.format(speed)


def stepped_values(lo, hi, step):
    """Return the list of values from lo to hi (inclusive) in step increments."""
    # Snap hi down to the nearest step boundary from lo so the list ends cleanly.
    count = int(round((hi - lo) / step))
    return [round(lo + i * step, 2) for i in range(count + 1)]


def step_tempo(cmd, current, lo, hi, step):
    if cmd == 'speed_up':
        return round(min(current + step, hi), 2)
    if cmd == 'speed_down':
        return round(max(current - step, lo), 2)
    return current


def pick_via_dialog(current, lo, hi, step):
    values = stepped_values(lo, hi, step)
    labels = [format_speed(v) for v in values]
    # Preselect the nearest listed value.
    idx = min(range(len(values)), key=lambda i: abs(values[i] - current))
    sel = xbmcgui.Dialog().select('Playback speed', labels, preselect=idx)
    if sel < 0:
        return current
    return values[sel]


def queue_notification(display):
    # runner.py debounces and emits the actual toast.
    try:
        with open(NOTIFY_FILE, 'w') as f:
            f.write('{}|{}'.format(time.time(), display))
    except IOError:
        pass


if __name__ == '__main__':
    if not os.path.exists(ACTIVE_FILE):
        sys.exit(0)

    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    tempo_file, config_file = resolve_files()
    step, lo, hi = read_config(config_file)
    current = read_tempo(tempo_file)

    if cmd == 'speed_reset':
        new_speed = round(max(lo, min(hi, 1.0)), 2)
    elif cmd == 'dialog':
        new_speed = pick_via_dialog(current, lo, hi, step)
    else:
        new_speed = step_tempo(cmd, current, lo, hi, step)

    if abs(new_speed - current) > 0.001:
        write_tempo(new_speed, tempo_file)
        set_props(new_speed)
        queue_notification(format_speed(new_speed))
