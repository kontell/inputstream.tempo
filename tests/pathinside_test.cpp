// Standalone test for IsPathInside. No Kodi or FFmpeg dependency:
//
//   g++ -std=c++17 -I src/utils tests/pathinside_test.cpp -o /tmp/pathinside_test && /tmp/pathinside_test

#include "PathInside.h"

#include <cstdio>
#include <cstdlib>

using ffmpegdirect::IsPathInside;

static int g_failures = 0;

static void Expect(const char* what, bool got, bool want)
{
  if (got != want)
  {
    std::printf("FAIL %s: got %s want %s\n", what, got ? "true" : "false", want ? "true" : "false");
    ++g_failures;
  }
}

int main()
{
  const bool posix = false;
  const bool windows = true;

  {
    const char* temp = "/home/u/.kodi/temp/";
    Expect("file in root", IsPathInside("/home/u/.kodi/temp/inputstream_tempo.pvr.kofin", temp, posix), true);
    Expect("root without trailing slash", IsPathInside("/home/u/.kodi/temp/x", "/home/u/.kodi/temp", posix), true);
    Expect("file in a subfolder", IsPathInside("/home/u/.kodi/temp/a/b", temp, posix), true);
    Expect("doubled separator", IsPathInside("/home/u/.kodi/temp//x", temp, posix), true);
    Expect("the root itself", IsPathInside("/home/u/.kodi/temp", temp, posix), false);
    Expect("the root with a slash", IsPathInside("/home/u/.kodi/temp/", temp, posix), false);
    Expect("sibling that shares the prefix", IsPathInside("/home/u/.kodi/temporary/x", temp, posix), false);
    Expect("elsewhere", IsPathInside("/home/u/.bashrc", temp, posix), false);
    Expect("climbing out", IsPathInside("/home/u/.kodi/temp/../userdata/guisettings.xml", temp, posix), false);
    Expect("climbing out and back", IsPathInside("/home/u/.kodi/temp/../temp/x", temp, posix), false);
    Expect("trailing ..", IsPathInside("/home/u/.kodi/temp/a/..", temp, posix), false);
    Expect("a name that only starts with dots", IsPathInside("/home/u/.kodi/temp/..x", temp, posix), true);
    Expect("a name that only ends with dots", IsPathInside("/home/u/.kodi/temp/x..", temp, posix), true);
    Expect("relative path", IsPathInside("temp/x", temp, posix), false);
    Expect("untranslated special path", IsPathInside("special://temp/x", temp, posix), false);
    Expect("empty path", IsPathInside("", temp, posix), false);
    Expect("empty root", IsPathInside("/home/u/.kodi/temp/x", "", posix), false);
    Expect("filesystem root as root", IsPathInside("/etc/passwd", "/", posix), false);
    Expect("case matters on POSIX", IsPathInside("/home/u/.kodi/TEMP/x", temp, posix), false);
    Expect("backslash is a name character on POSIX", IsPathInside("/home/u/.kodi/temp\\x", temp, posix), false);
  }

  {
    const char* temp = "C:\\Users\\u\\AppData\\Roaming\\Kodi\\cache\\";
    Expect("windows: file in root", IsPathInside("C:\\Users\\u\\AppData\\Roaming\\Kodi\\cache\\inputstream_tempo.x", temp, windows), true);
    Expect("windows: forward slashes", IsPathInside("C:/Users/u/AppData/Roaming/Kodi/cache/x", temp, windows), true);
    Expect("windows: mixed separators", IsPathInside("C:\\Users\\u\\AppData\\Roaming\\Kodi\\cache/x", temp, windows), true);
    Expect("windows: case differs", IsPathInside("c:\\users\\U\\appdata\\roaming\\kodi\\CACHE\\x", temp, windows), true);
    Expect("windows: climbing out", IsPathInside("C:\\Users\\u\\AppData\\Roaming\\Kodi\\cache\\..\\userdata\\x", temp, windows), false);
    Expect("windows: another drive", IsPathInside("D:\\Users\\u\\AppData\\Roaming\\Kodi\\cache\\x", temp, windows), false);
    Expect("windows: sibling that shares the prefix", IsPathInside("C:\\Users\\u\\AppData\\Roaming\\Kodi\\cache2\\x", temp, windows), false);
    Expect("windows: the root itself", IsPathInside("C:\\Users\\u\\AppData\\Roaming\\Kodi\\cache\\", temp, windows), false);
  }

  if (g_failures)
  {
    std::printf("%d failure(s)\n", g_failures);
    return EXIT_FAILURE;
  }
  std::printf("pathinside: all checks passed\n");
  return EXIT_SUCCESS;
}
