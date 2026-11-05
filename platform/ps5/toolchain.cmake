# SPDX-License-Identifier: GPL-3.0-or-later
# Wrap the public payload SDK without checking tool binaries into the port.
if(NOT DEFINED ENV{PS5_PAYLOAD_SDK})
    message(FATAL_ERROR "Set PS5_PAYLOAD_SDK to the public PS5 payload SDK directory")
endif()
file(TO_CMAKE_PATH "$ENV{PS5_PAYLOAD_SDK}" SC2_PAYLOAD_SDK)
include("${SC2_PAYLOAD_SDK}/toolchain/prospero.cmake")
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
set(CMAKE_C_FLAGS_INIT "${CMAKE_C_FLAGS_INIT} -DSC2_PS5=1")
set(CMAKE_CXX_FLAGS_INIT "${CMAKE_CXX_FLAGS_INIT} -DSC2_PS5=1 -fexceptions -frtti")
# Use an explicitly supplied console SDL build, never download desktop SDL.
set(RECOMP_FETCH_SDL3 OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
if(SC2_PS5_SDL_PREFIX)
    list(PREPEND CMAKE_PREFIX_PATH "${SC2_PS5_SDL_PREFIX}")
endif()
