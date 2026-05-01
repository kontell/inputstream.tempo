[![License: GPL-2.0-or-later](https://img.shields.io/badge/License-GPL%20v2+-blue.svg)](LICENSE.md)

# inputstream.tempo addon for Kodi

This is a fork of inputstream.ffmpegdirect. 

The purpose of the fork is to add tempo (playback speed adjustment) for audio playback without needing to sync playback to display.

# Status

It works with VideoPlayer. With PAPlayer seeking is not available player without this fix: https://github.com/xbmc/xbmc/pull/28179.

Will also need this patch to enable correct progress display in PAPlayer: https://github.com/xbmc/xbmc/compare/master...kontell:xbmc:fix/paplayer-display-time

An audiobookshelf addon is working quite well with it: https://github.com/kontell/KoShelf

I patched the youtube addon to use inputstream.tempo for the pre-existing audio-only playback and it worked fine: https://github.com/anxdpanic/plugin.video.youtube/compare/master...kontell:plugin.video.youtube:tempo
