"""inputstream.tempo background service.

Updates Window(Home) properties with current playback speed so skins can
display it. Also auto-installs the keyboard shortcut keymap on first run
and cleans up timeshift buffer files on startup.
"""

import os
import shutil

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
TEMPO_FILE = xbmc.translatePath('special://temp/inputstream_tempo')
KEYMAP_SRC = os.path.join(ADDON.getAddonInfo('path'), 'resources', 'keymap.xml')
KEYMAP_DST = xbmc.translatePath('special://userdata/keymaps/inputstream.tempo.xml')


def install_keymap():
    """Copy keymap.xml to Kodi's keymaps dir if not already present."""
    if os.path.exists(KEYMAP_DST) or not os.path.exists(KEYMAP_SRC):
        return
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
        if monitor.waitForAbort(1):
            break

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
