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

include(CTest)
if(BUILD_TESTING)
    add_executable(sc2_ps2_material_test ../tools/test_ps2_material.cpp)
    target_link_libraries(sc2_ps2_material_test PRIVATE sc2_guest_lib)
    add_test(NAME sc2-ps2-material COMMAND sc2_ps2_material_test)
    find_package(Python3 COMPONENTS Interpreter QUIET)
    if(Python3_Interpreter_FOUND)
        add_test(NAME sc2-ps2-material-python COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/../tools/test_ps2_material.py")
    endif()
endif()
