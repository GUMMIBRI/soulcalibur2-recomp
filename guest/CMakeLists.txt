# SPDX-License-Identifier: GPL-3.0-or-later
# The guest converters (Link from the player's GameCube disc): a library the
# launcher links, and sc2_guest, the same from the command line.
cmake_minimum_required(VERSION 3.20)
project(sc2_guest C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()
include(guest.cmake)
add_executable(sc2_guest tool.cpp)
target_link_libraries(sc2_guest PRIVATE sc2_guest_lib)
