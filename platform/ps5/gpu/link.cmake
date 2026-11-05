# SPDX-License-Identifier: GPL-3.0-or-later
# Include after the runner target has been defined. This target supplies real
# console SDL GPU and RADV libraries; it never substitutes the software SDL port.
if(NOT PS5)
    message(FATAL_ERROR "SC2 PS5 GPU linkage requires the public PS5 toolchain")
endif()
set(SC2_PS5_SDL_PREFIX "" CACHE PATH "GPU-enabled console SDL3 installation")
set(SC2_PS5_RADV_PREFIX "" CACHE PATH "PS5 RADV release containing lib and include")
set(SC2_PS5_GRAPHICS_SDK "${PS5_PAYLOAD_SDK}" CACHE PATH "Public SDK with Agc imports")
set(SC2_PS5_PLATFORM_LIBRARY "" CACHE FILEPATH "Optional public SDK platform support archive")
foreach(_input "${SC2_PS5_SDL_PREFIX}/lib/libSDL3.a"
               "${SC2_PS5_SDL_PREFIX}/include/SDL3/SDL.h"
               "${SC2_PS5_RADV_PREFIX}/lib/libvulkan_radeon.ps5.a")
    if(NOT EXISTS "${_input}")
        message(FATAL_ERROR "Missing console GPU dependency: ${_input}")
    endif()
endforeach()
foreach(_name SceAgc SceAgcDriver)
    find_library(SC2_PS5_${_name} NAMES "${_name}" REQUIRED
        PATHS "${SC2_PS5_GRAPHICS_SDK}/target/lib" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
endforeach()
add_library(sc2_ps5_sdl_gpu STATIC IMPORTED GLOBAL)
set_target_properties(sc2_ps5_sdl_gpu PROPERTIES
    IMPORTED_LOCATION "${SC2_PS5_SDL_PREFIX}/lib/libSDL3.a"
    INTERFACE_INCLUDE_DIRECTORIES "${SC2_PS5_SDL_PREFIX}/include")
add_library(sc2_ps5_radv STATIC IMPORTED GLOBAL)
set_target_properties(sc2_ps5_radv PROPERTIES
    IMPORTED_LOCATION "${SC2_PS5_RADV_PREFIX}/lib/libvulkan_radeon.ps5.a"
    INTERFACE_INCLUDE_DIRECTORIES "${SC2_PS5_RADV_PREFIX}/include")
add_library(sc2_ps5_gpu INTERFACE)
# The static SDL loader references vk_icdGetInstanceProcAddr directly. A group
# resolves archive cycles without dragging every unused RADV entry into a game.
target_link_libraries(sc2_ps5_gpu INTERFACE
    "-Wl,--start-group" sc2_ps5_sdl_gpu sc2_ps5_radv "-Wl,--end-group"
    "${SC2_PS5_SceAgc}" "${SC2_PS5_SceAgcDriver}"
    SceVideoOut SceAudioOut ScePad SceUserService SceSystemService)
if(SC2_PS5_PLATFORM_LIBRARY)
    if(NOT EXISTS "${SC2_PS5_PLATFORM_LIBRARY}")
        message(FATAL_ERROR "Missing platform support archive: ${SC2_PS5_PLATFORM_LIBRARY}")
    endif()
    target_link_libraries(sc2_ps5_gpu INTERFACE "${SC2_PS5_PLATFORM_LIBRARY}")
endif()
target_compile_definitions(sc2_ps5_gpu INTERFACE SC2_PS5=1)
function(sc2_ps5_link_gpu target)
    if(NOT TARGET "${target}")
        message(FATAL_ERROR "SC2 target does not exist: ${target}")
    endif()
    target_link_libraries("${target}" PRIVATE sc2_ps5_gpu)
endfunction()
