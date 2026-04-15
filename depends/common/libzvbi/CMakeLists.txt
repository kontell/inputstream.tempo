project(libzvbi)

cmake_minimum_required(VERSION 3.5)

list(APPEND CMAKE_MODULE_PATH ${PROJECT_SOURCE_DIR})

list(APPEND zvbi_conf CPPFLAGS=-I${CMAKE_INSTALL_PREFIX}/include)
if (CORE_SYSTEM_NAME STREQUAL android)
  set(zvbi_cflags "CFLAGS=-I${CMAKE_INSTALL_PREFIX}/include -Wno-implicit-function-declaration")
  list(APPEND zvbi_conf ${zvbi_cflags})
else()
  list(APPEND zvbi_conf CFLAGS=-I${CMAKE_INSTALL_PREFIX}/include)
endif()
list(APPEND zvbi_conf LDFLAGS=-L${CMAKE_INSTALL_PREFIX}/lib)
# libzvbi's configure detects the bundled libiconv.a (built transitively via
# gmp/libxml2) and generates libiconv_* symbol references, so its utility
# binaries (zvbi-ntsc-cc, x11font) must link against -liconv. Needed on every
# platform that builds libzvbi; the previous conditional only covered
# Android/webOS, which is why fresh Linux hosts failed to link.
list(APPEND zvbi_conf LIBS=-liconv)

include(ExternalProject)
externalproject_add(libzvbi
                    SOURCE_DIR ${CMAKE_SOURCE_DIR}
                    PATCH_COMMAND <SOURCE_DIR>/autogen.sh
                    CONFIGURE_COMMAND <SOURCE_DIR>/configure
                      --prefix=${CMAKE_INSTALL_PREFIX}
                      --enable-shared=no
                      --enable-static
                      --disable-dvb
                      --disable-bktr
                      --disable-nls
                      --disable-proxy
                      --without-doxygen
                      --with-pic
                      --without-x
                      ${zvbi_conf})

install(CODE "Message(Done)")
