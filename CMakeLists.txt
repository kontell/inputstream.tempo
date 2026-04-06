cmake_minimum_required(VERSION 3.5)
project(inputstream.tempo)

set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} ${PROJECT_SOURCE_DIR})

find_package(PkgConfig)
if(WIN32)
  find_package(LibXml2 REQUIRED)
  find_package(Iconv REQUIRED)
  find_package(OpenSSL REQUIRED)
endif()

# When cross-compiling, add depends path to root search path
if(ADDON_DEPENDS_PATH)
  list(APPEND CMAKE_FIND_ROOT_PATH ${ADDON_DEPENDS_PATH})
endif()

find_package(Kodi REQUIRED)
find_package(FFMPEG REQUIRED)
find_package(ZLIB REQUIRED)
find_package(BZip2 REQUIRED)

set(TEMPO_SOURCES src/StreamManager.cpp
                  src/stream/DemuxStream.cpp
                  src/stream/FFmpegCatchupStream.cpp
                  src/stream/FFmpegLog.cpp
                  src/stream/FFmpegStream.cpp
                  src/stream/CurlCatchupInput.cpp
                  src/stream/CurlInput.cpp
                  src/stream/TimeshiftBuffer.cpp
                  src/stream/TimeshiftSegment.cpp
                  src/stream/TimeshiftStream.cpp
                  src/stream/url/URL.cpp
                  src/stream/url/UrlOptions.cpp
                  src/stream/url/Variant.cpp
                  src/utils/DiskUtils.cpp
                  src/utils/FilenameUtils.cpp)

set(TEMPO_HEADERS src/StreamManager.h
                  src/stream/BaseStream.h
                  src/stream/DemuxStream.h
                  src/stream/FFmpegCatchupStream.h
                  src/stream/FFmpegLog.h
                  src/stream/FFmpegStream.h
                  src/stream/CurlCatchupInput.h
                  src/stream/CurlInput.h
                  src/stream/IManageDemuxPacket.h
                  src/stream/TimeshiftBuffer.h
                  src/stream/TimeshiftSegment.h
                  src/stream/TimeshiftStream.h
                  src/utils/HttpProxy.h
                  src/utils/DiskUtils.h
                  src/utils/FilenameUtils.h
                  src/utils/Log.h
                  src/utils/Properties.h
                  src/utils/TimeUtils.h
                  src/stream/url/URL.h
                  src/stream/url/UrlOptions.h
                  src/stream/url/Variant.h)

include_directories(${INCLUDES}
                    ${FFMPEG_INCLUDE_DIRS}
                    ${ZLIB_INCLUDE_DIRS}
                    ${BZIP2_INCLUDE_DIRS}
                    ${OPENSSL_INCLUDE_DIR}
                    ${LIBXML2_INCLUDE_DIRS}
                    ${KODI_INCLUDE_DIR}/..)

list(APPEND DEPLIBS ${ZLIB_LIBRARIES}
                    ${BZIP2_LIBRARIES})

if(WIN32)
  list(APPEND DEPLIBS ${ICONV_LIBRARIES}
                      ${OPENSSL_LIBRARIES}
                      ${LIBXML2_LIBRARIES}
                      ${FFMPEG_LIBRARIES}
                      Winmm.lib
                      WS2_32.lib
                      Bcrypt.lib
                      Secur32.lib
                      Mfplat.lib
                      Mfuuid.lib
                      Strmiids.lib)
elseif(CORE_SYSTEM_NAME STREQUAL osx OR
       CORE_SYSTEM_NAME STREQUAL darwin_embedded)
  find_library(AUDIOTOOLBOX AudioToolbox)
  find_library(COREFOUNDATION CoreFoundation)
  find_library(COREMEDIA CoreMedia)
  find_library(COREVIDEO CoreVideo)
  find_library(VIDEOTOOLBOX VideoToolbox)
  find_library(SECURITY Security)

  include_directories(${AUDIOTOOLBOX}
                      ${COREFOUNDATION}
                      ${COREMEDIA}
                      ${COREVIDEO}
                      ${VIDEOTOOLBOX}
                      ${SECURITY})

  list(APPEND DEPLIBS ${AUDIOTOOLBOX} ${COREFOUNDATION} ${COREMEDIA} ${COREVIDEO} ${VIDEOTOOLBOX} ${SECURITY})
else()
  list(APPEND DEPLIBS ${FFMPEG_LIBRARIES})
endif()

addon_version(inputstream.tempo TEMPO)
add_definitions(-DTEMPO_VERSION=${TEMPO_VERSION})

build_addon(inputstream.tempo TEMPO DEPLIBS)

if(${CMAKE_SYSTEM_NAME} MATCHES "Darwin")
  string(REGEX REPLACE "-framework;([A-Za-z0-9_]+);?" "" FFMPEG_LDFLAGS "${FFMPEG_LDFLAGS}")
endif()
string(REGEX REPLACE ";" " " FFMPEG_LDFLAGS "${FFMPEG_LDFLAGS}")
set_target_properties(inputstream.tempo PROPERTIES LINK_FLAGS "${FFMPEG_LDFLAGS}")

if(CORE_SYSTEM_NAME STREQUAL windowsstore)
  set_target_properties(inputstream.tempo PROPERTIES LINK_FLAGS_RELWITHDEBINFO "/LTCG /defaultlib:vccorlib.lib /defaultlib:msvcrt.lib /defaultlib:onecore.lib")
  set_target_properties(inputstream.tempo PROPERTIES LINK_FLAGS_RELEASE "/LTCG /defaultlib:vccorlib.lib /defaultlib:msvcrt.lib /defaultlib:onecore.lib")
  set_target_properties(inputstream.tempo PROPERTIES LINK_FLAGS_DEBUG "/LTCG /defaultlib:vccorlibd.lib /defaultlib:msvcrtd.lib /defaultlib:onecore.lib")
endif()

include(CPack)
