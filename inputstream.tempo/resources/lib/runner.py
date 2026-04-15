"""inputstream.tempo background service.

Updates Window(Home) properties with current playback speed so skins can
display it. Also auto-installs the keyboard shortcut keymap on first run
and cleans up timeshift buffer files on startup.
"""

import os
import shutil
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
TEMPO_FILE = xbmcvfs.translatePath('special://temp/inputstream_tempo')
NOTIFY_FILE = xbmcvfs.translatePath('special://temp/inputstream_tempo_notify')
KEYMAP_SRC = os.path.join(ADDON.getAddonInfo('path'), 'resources', 'keymap.xml')
KEYMAP_DST = xbmcvfs.translatePath('special://userdata/keymaps/inputstream.tempo.xml')

# Debounce: only emit notification after pending value is this old.
# Rapid key presses keep bumping the timestamp, so only the final value shows.
NOTIFY_DEBOUNCE = 0.35


def install_keymap():
    """Copy keymap.xml to Kodi's keymaps dir. Reinstalls when addon version
    bumps the shipped keymap so updates (new keys) take effect automatically."""
    if not os.path.exists(KEYMAP_SRC):
        return
    # Skip if destination already matches (avoids spurious reloadkeymaps).
    try:
        with open(KEYMAP_SRC, 'rb') as a, open(KEYMAP_DST, 'rb') as b:
            if a.read() == b.read():
                return
    except (IOError, OSError):
        pass
    dst_dir = os.path.dirname(KEYMAP_DST)
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
    shutil.copy2(KEYMAP_SRC, KEYMAP_DST)
    xbmc.executebuiltin('Action(reloadkeymaps)')
    xbmc.log('inputstream.tempo: installed keymap to {}'.format(KEYMAP_DST), xbmc.LOGINFO)


def read_tempo():
    """Read current tempo from the IPC file."""
    try:
        with open(TEMPO_FILE) as f:
            return float(f.read().strip())
    except Exception:
        return 1.0


def cleanup_timeshift():
    """Clean up leftover timeshift buffer files (from upstream ffmpegdirect)."""
    def hidden(path):
        return path.startswith('.') or path.startswith('_UNPACK')

    ts_path = ADDON.getSetting('timeshiftBufferPath')
    if not ts_path:
        return
    if not ts_path.endswith('/'):
        ts_path += '/'
    if xbmcvfs.exists(ts_path):
        _dirs, files = xbmcvfs.listdir(ts_path)
        for f in files:
            if not hidden(f) and (f.endswith('.idx') or f.endswith('.seg')):
                xbmcvfs.delete(ts_path + f)


def run():
    install_keymap()
    cleanup_timeshift()

    monitor = xbmc.Monitor()
    player = xbmc.Player()
    win = xbmcgui.Window(10000)
    was_playing = False

    xbmc.log('inputstream.tempo: service started', xbmc.LOGINFO)

    while not monitor.abortRequested():
        if monitor.waitForAbort(0.2):
            break

        # Debounced speed-change notification. speed.py writes "<ts>|<display>"
        # each keypress; we only emit once writes have stopped for DEBOUNCE sec.
        try:
            if os.path.exists(NOTIFY_FILE):
                with open(NOTIFY_FILE) as f:
                    ts_str, _, display = f.read().strip().partition('|')
                if time.time() - float(ts_str) >= NOTIFY_DEBOUNCE:
                    xbmc.executebuiltin(
                        'Notification(Playback Speed, {}, 1200)'.format(display))
                    os.remove(NOTIFY_FILE)
        except Exception:
            try:
                os.remove(NOTIFY_FILE)
            except OSError:
                pass

        playing = player.isPlayingAudio()
        if playing:
            tempo = read_tempo()
            win.setProperty('InputstreamTempo.Speed', str(tempo))
            win.setProperty('InputstreamTempo.SpeedDisplay', '{:.1f}x'.format(tempo))
            win.setProperty('InputstreamTempo.Active', 'true')
            was_playing = True
        elif was_playing:
            win.clearProperty('InputstreamTempo.Speed')
            win.clearProperty('InputstreamTempo.SpeedDisplay')
            win.clearProperty('InputstreamTempo.Active')
            was_playing = False

    xbmc.log('inputstream.tempo: service stopped', xbmc.LOGINFO)


if __name__ == '__main__':
    run()
