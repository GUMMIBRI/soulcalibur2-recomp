# SPDX-License-Identifier: GPL-3.0-or-later
# Included into the game's build (tools/build_game.py, CMAKE_PROJECT_INCLUDE): the builder's own folders kept out of
# the programs. __FILE__ (in the runtime's messages and asserts) and debug paths are written relative to the
# repository, so a release names no one's home folder.
if(SC2_SOURCE_ROOT)
    add_compile_options("-ffile-prefix-map=${SC2_SOURCE_ROOT}=.")
endif()
# Android: the game is a library there, and a library's calls to its own functions and reads of its own globals (the
# translated code's registers among them) went through the dynamic linker's tables, which a program's never do: bound
# directly, as in a program (nothing outside the library replaces them)
if(ANDROID)
    add_compile_options(-fno-semantic-interposition)
    add_link_options(-Wl,-Bsymbolic)
endif()
