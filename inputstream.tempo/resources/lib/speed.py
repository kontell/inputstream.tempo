"""Speed control commands for inputstream.tempo. Called via RunScript.

Supports two modes:
- Preset mode (default): steps through SPEED_PRESETS list
- Increment mode: if a step file exists, steps by that increment value

The step file is written by the calling addon (e.g. KoShelf) at:
  special://temp/inputstream_tempo_step
containing a single float like "0.1"
"""

import sys

import xbmc
import xbmcgui

SPEED_PRESETS = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.7, 2.0, 2.5, 3.0]
TEMPO_FILE = xbmc.translatePath('special://temp/inputstream_tempo')
STEP_FILE = xbmc.translatePath('special://temp/inputstream_tempo_step')
MIN_SPEED = 0.5
MAX_SPEED = 3.5


def read_tempo():
    try:
        with open(TEMPO_FILE) as f:
            return float(f.read().strip())
    except Exception:
        return 1.0


def write_tempo(val):
    with open(TEMPO_FILE, 'w') as f:
        f.write(str(val))


def read_step():
    """Read custom step increment. Returns None if not set (use presets)."""
    try:
        with open(STEP_FILE) as f:
            step = float(f.read().strip())
            if 0.01 <= step <= 0.5:
                return step
    except Exception:
        pass
    return None


def set_props(speed):
    win = xbmcgui.Window(10000)
    win.setProperty('InputstreamTempo.Speed', str(speed))
    # Show 2 decimal places for fine increments, 1 for round values
    if abs(speed - round(speed, 1)) < 0.001:
        display = '{:.1f}x'.format(speed)
    else:
        display = '{:.2f}x'.format(speed)
    win.setProperty('InputstreamTempo.SpeedDisplay', display)


def find_nearest_index(value):
    return min(range(len(SPEED_PRESETS)), key=lambda i: abs(SPEED_PRESETS[i] - value))


def step_with_presets(cmd, current):
    idx = find_nearest_index(current)
    if cmd == 'speed_up' and idx < len(SPEED_PRESETS) - 1:
        return SPEED_PRESETS[idx + 1]
    elif cmd == 'speed_down' and idx > 0:
        return SPEED_PRESETS[idx - 1]
    return current


def step_with_increment(cmd, current, step):
    if cmd == 'speed_up':
        return min(round(current + step, 2), MAX_SPEED)
    elif cmd == 'speed_down':
        return max(round(current - step, 2), MIN_SPEED)
    return current


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    current = read_tempo()

    if cmd == 'speed_reset':
        new_speed = 1.0
    else:
        step = read_step()
        if step is not None:
            new_speed = step_with_increment(cmd, current, step)
        else:
            new_speed = step_with_presets(cmd, current)

    if abs(new_speed - current) > 0.001:
        write_tempo(new_speed)
        set_props(new_speed)
        if abs(new_speed - round(new_speed, 1)) < 0.001:
            display = '{:.1f}x'.format(new_speed)
        else:
            display = '{:.2f}x'.format(new_speed)
        xbmc.executebuiltin('Notification(Playback Speed, {}, 1500)'.format(display))
