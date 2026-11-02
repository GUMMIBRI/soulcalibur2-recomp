# SPDX-License-Identifier: GPL-3.0-or-later
# Included into the game's build (tools/build_game.py, CMAKE_PROJECT_INCLUDE): the builder's own folders kept out of
# the programs. __FILE__ (in the runtime's messages and asserts) and debug paths are written relative to the
# repository, so a release names no one's home folder.
if(SC2_SOURCE_ROOT)
    add_compile_options("-ffile-prefix-map=${SC2_SOURCE_ROOT}=.")
endif()
