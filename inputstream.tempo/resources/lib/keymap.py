#  Copyright (C) 2026 kontell
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.md for more information.

"""Install or remove the playback-speed keymap, when the user asks.

Kodi reads keymaps from special://userdata/keymaps. That folder is not this
add-on's own, so nothing is written to it or deleted from it without a
confirmation that says which file and where.
"""

import os
import shutil

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON_ID = 'inputstream.tempo'
KEYMAP_DST = xbmcvfs.translatePath('special://userdata/keymaps/inputstream.tempo.xml')

# String ids
HEADING = 30060
CONFIRM_INSTALL = 30701
CONFIRM_REMOVE = 30702
INSTALLED = 30703
REMOVED = 30704
NOT_INSTALLED = 30705
FAILED = 30706


def _failed(dialog, text, what, err):
    xbmc.log('inputstream.tempo: could not {} {}: {}'.format(what, KEYMAP_DST, err), xbmc.LOGERROR)
    dialog.notification(text(HEADING), text(FAILED), xbmcgui.NOTIFICATION_ERROR)


def install():
    addon = xbmcaddon.Addon(ADDON_ID)
    text = addon.getLocalizedString
    dialog = xbmcgui.Dialog()

    if not dialog.yesno(text(HEADING), text(CONFIRM_INSTALL)):
        return

    src = os.path.join(xbmcvfs.translatePath(addon.getAddonInfo('path')), 'resources', 'keymap.xml')
    try:
        os.makedirs(os.path.dirname(KEYMAP_DST), exist_ok=True)
        # The content only. The shipped file may be read-only, and a copy
        # that inherited that could not be replaced by the next install.
        shutil.copyfile(src, KEYMAP_DST)
    except OSError as err:
        _failed(dialog, text, 'install', err)
        return

    xbmc.executebuiltin('Action(reloadkeymaps)')
    dialog.notification(text(HEADING), text(INSTALLED), xbmcgui.NOTIFICATION_INFO)


def remove():
    addon = xbmcaddon.Addon(ADDON_ID)
    text = addon.getLocalizedString
    dialog = xbmcgui.Dialog()

    if not os.path.exists(KEYMAP_DST):
        dialog.notification(text(HEADING), text(NOT_INSTALLED), xbmcgui.NOTIFICATION_INFO)
        return
    if not dialog.yesno(text(HEADING), text(CONFIRM_REMOVE)):
        return

    try:
        os.remove(KEYMAP_DST)
    except OSError as err:
        _failed(dialog, text, 'remove', err)
        return

    xbmc.executebuiltin('Action(reloadkeymaps)')
    dialog.notification(text(HEADING), text(REMOVED), xbmcgui.NOTIFICATION_INFO)
