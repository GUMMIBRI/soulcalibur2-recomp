# SPDX-License-Identifier: GPL-3.0-or-later
# sc2_guest_lib: included by guest/CMakeLists.txt and the launcher's.
set(SC2_GUEST_DIR ${CMAKE_CURRENT_LIST_DIR})
set(SC2_RUNTIME_DIR ${CMAKE_CURRENT_LIST_DIR}/../third_party/doa2u-re/recomp-runtime)
add_library(sc2_guest_lib STATIC
    ${SC2_GUEST_DIR}/olnk.cpp ${SC2_GUEST_DIR}/textures.cpp ${SC2_GUEST_DIR}/motion.cpp
    ${SC2_GUEST_DIR}/sound.cpp ${SC2_GUEST_DIR}/vmx.cpp ${SC2_GUEST_DIR}/discs.cpp ${SC2_GUEST_DIR}/build.cpp
    ${SC2_GUEST_DIR}/gs.cpp ${SC2_GUEST_DIR}/ps2tex.cpp ${SC2_GUEST_DIR}/vmp.cpp)
# (the PS2 converter's floats must round as the Python's do: no fused multiply-adds)
if(NOT MSVC)
    target_compile_options(sc2_guest_lib PRIVATE -ffp-contract=off)
endif()
target_include_directories(sc2_guest_lib PUBLIC ${SC2_GUEST_DIR} PRIVATE ${SC2_RUNTIME_DIR})
if(NOT TARGET sc2_guest_disc_image)
    add_library(sc2_guest_disc_image STATIC ${SC2_RUNTIME_DIR}/disc_image.c)
    target_include_directories(sc2_guest_disc_image PUBLIC ${SC2_RUNTIME_DIR})
endif()
target_link_libraries(sc2_guest_lib PUBLIC sc2_guest_disc_image)
