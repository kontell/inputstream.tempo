#  Copyright (C) 2026 kontell
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.md for more information.

"""The add-on's one RunScript entry point.

RunScript(inputstream.tempo,<command>) lands here: addon.xml declares this
file as the add-on's xbmc.python.library, which is what Kodi runs when
RunScript names an add-on that is not itself a script. Naming the add-on
rather than a file under special://home/addons works wherever the add-on is
installed.

Anything not listed below does nothing.
"""

import sys

SPEED_COMMANDS = ('speed_up', 'speed_down', 'speed_reset', 'dialog')

command = sys.argv[1] if len(sys.argv) > 1 else ''

if command in SPEED_COMMANDS:
    import speed
    speed.main(command)
elif command == 'install_keymap':
    import keymap
    keymap.install()
elif command == 'remove_keymap':
    import keymap
    keymap.remove()
