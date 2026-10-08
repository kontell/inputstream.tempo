/*
 *  Copyright (C) 2026 kontell
 *
 *  SPDX-License-Identifier: GPL-2.0-or-later
 *  See LICENSE.md for more information.
 */

#pragma once

#include <string>

namespace ffmpegdirect
{

#ifdef TARGET_WINDOWS
constexpr bool WINDOWS_PATHS = true;
#else
constexpr bool WINDOWS_PATHS = false;
#endif

/*!
 * Whether `path` names something inside the folder `root`, judged on the text
 * of the two paths alone: nothing on disk is consulted and no link is
 * followed.
 *
 * It is the check for a file name that arrives from outside the add-on. A
 * ListItem property can come from a playlist the user was given, so the tempo
 * file it names, which the add-on reads and writes a state file beside, must
 * not be free to point anywhere on the disk.
 *
 * A path with a ".." component is refused whatever it would resolve to. With
 * `windowsPaths` a backslash separates as a slash does and letters compare
 * without case. Header-only and free of Kodi, so tests/pathinside_test.cpp
 * covers both sets of rules on any host.
 */
inline bool IsPathInside(const std::string& path,
                         const std::string& root,
                         bool windowsPaths = WINDOWS_PATHS)
{
  const auto normalise = [windowsPaths](const std::string& in)
  {
    std::string out;
    out.reserve(in.size());
    for (char c : in)
    {
      if (windowsPaths)
      {
        if (c == '\\')
          c = '/';
        else if (c >= 'A' && c <= 'Z')
          c = static_cast<char>(c - 'A' + 'a');
      }
      if (c == '/' && !out.empty() && out.back() == '/')
        continue; // "a//b" is "a/b"
      out += c;
    }
    return out;
  };

  const std::string p = normalise(path);
  std::string r = normalise(root);
  while (r.size() > 1 && r.back() == '/')
    r.pop_back();

  // An untranslated or empty root, or the filesystem root itself, would make
  // every path "inside".
  if (r.empty() || r == "/")
    return false;

  for (size_t start = 0; start <= p.size();)
  {
    size_t end = p.find('/', start);
    if (end == std::string::npos)
      end = p.size();
    if (p.compare(start, end - start, "..") == 0)
      return false;
    start = end + 1;
  }

  // The root, a separator, and a name after it.
  return p.size() > r.size() + 1 && p.compare(0, r.size(), r) == 0 && p[r.size()] == '/';
}

} //namespace ffmpegdirect
