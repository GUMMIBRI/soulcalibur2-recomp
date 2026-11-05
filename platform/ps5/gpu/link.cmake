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
set(SC2_PS5_COMPILER_RT_DIR "" CACHE PATH "Licensed compiler-rt CPU model source directory")
set(_sc2_sdk_lib "${SC2_PS5_GRAPHICS_SDK}/target/lib")
set(_sc2_runtime_archives)
foreach(_name libc++.a libc++abi.a libunwind.a libpthread.a libc.a)
    if(NOT EXISTS "${_sc2_sdk_lib}/${_name}")
        message(FATAL_ERROR "Missing public SDK runtime archive: ${_sc2_sdk_lib}/${_name}")
    endif()
    list(APPEND _sc2_runtime_archives "${_sc2_sdk_lib}/${_name}")
endforeach()
set(_sc2_imports)
foreach(_name kernel_web SceLibcInternal SceNet SceAgc SceAgcDriver
              SceVideoOut SceAudioOut ScePad SceUserService SceSystemService SceSysmodule)
    if(NOT EXISTS "${_sc2_sdk_lib}/lib${_name}.so")
        message(FATAL_ERROR "Missing public SDK import library: ${_sc2_sdk_lib}/lib${_name}.so")
    endif()
    list(APPEND _sc2_imports "${_sc2_sdk_lib}/lib${_name}.so")
endforeach()
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
target_link_options(sc2_ps5_gpu INTERFACE "-Wl,--wrap=fflush" "-Wl,--wrap=fclose")
# The static SDL loader references vk_icdGetInstanceProcAddr directly. A group
# resolves archive cycles without dragging every unused RADV entry into a game.
target_link_libraries(sc2_ps5_gpu INTERFACE
    "-Wl,--start-group" sc2_ps5_sdl_gpu sc2_ps5_radv ${_sc2_runtime_archives}
    "-Wl,--end-group" ${_sc2_imports})
# libc++ archive members carry a dependent-library pthread directive.
target_link_directories(sc2_ps5_gpu INTERFACE "${_sc2_sdk_lib}")
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
    foreach(_name x86.c cpu_model.h LICENSE.TXT)
        if(NOT EXISTS "${SC2_PS5_COMPILER_RT_DIR}/${_name}")
            message(FATAL_ERROR "Set SC2_PS5_COMPILER_RT_DIR to real compiler-rt sources; missing ${_name}")
        endif()
    endforeach()
    # RADV's address swizzler uses __cpu_model. Compile the actual licensed
    # compiler-rt CPU dispatch implementation instead of inventing a model.
    target_sources("${target}" PRIVATE "${SC2_PS5_COMPILER_RT_DIR}/x86.c")
    if(SC2_PS5_SHADERC_LIBRARY OR SC2_PS5_SHADERC_INCLUDE)
        if(NOT EXISTS "${SC2_PS5_SHADERC_LIBRARY}" OR
           NOT EXISTS "${SC2_PS5_SHADERC_INCLUDE}/shaderc/shaderc.h")
            message(FATAL_ERROR "Set both SC2_PS5_SHADERC_LIBRARY and SC2_PS5_SHADERC_INCLUDE to the real target build")
        endif()
        # Shader compilation lives in the presenter library, not the runner TU.
        target_compile_definitions(recomp_d3d_presenter PRIVATE RECOMP_SHADERC_LINKED=1)
        target_include_directories(recomp_d3d_presenter PRIVATE "${SC2_PS5_SHADERC_INCLUDE}")
        target_link_libraries("${target}" PRIVATE "${SC2_PS5_SHADERC_LIBRARY}")
    endif()
    target_link_libraries("${target}" PRIVATE sc2_ps5_gpu)
endfunction()
