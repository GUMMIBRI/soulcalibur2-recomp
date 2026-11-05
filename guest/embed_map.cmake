# SPDX-License-Identifier: GPL-3.0-or-later
# texture_map.cpp from the texture map (tools/textures/GRSEAF.map): cmake -DIN=map -DOUT=cpp -P embed_map.cmake
file(READ "${IN}" hex HEX)
string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," bytes "${hex}")
string(REGEX REPLACE "(0x..,0x..,0x..,0x..,0x..,0x..,0x..,0x..,0x..,0x..,0x..,0x..,0x..,0x..,0x..,0x..,)" "\\1\n" bytes "${bytes}")
file(WRITE "${OUT}" "/* Generated from tools/textures/GRSEAF.map by guest/embed_map.cmake */\n#include \"texture_pack.h\"\nnamespace guest {\nnamespace {\nconst char kMap[] = {\n${bytes}0};\n}\nconst char *const kDolphinTextureMap = kMap;\n}\n")
