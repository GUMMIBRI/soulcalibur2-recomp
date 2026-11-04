// SPDX-License-Identifier: GPL-3.0-or-later
#ifdef NDEBUG
#undef NDEBUG
#endif
// Test the production parser, including its private command-block reader.
#include "../guest/vmp.cpp"
#include <cassert>
#include <cstdio>
int main() {
    const float values[]{0,1,2,3, 4,5,6,7, 8,9,10,11, 12,13,14,15};
    for (size_t start : {0u,4u,8u,12u}) {
        const size_t payload=(start+19)&~size_t(15),end=payload+sizeof values;
        guest::Bytes data(end+4,0);
        data[start]=7;data[start+1]=uint8_t(end-start);data[start+2]=7;
        std::memcpy(data.data()+payload,values,sizeof values);
        const auto sections=guest::block(data,start);
        assert(sections.size()==1 && sections[0].colours.size()==16);
        for (size_t i=0;i<16;++i) assert(sections[0].colours[i]==values[i]);
        data[start+1]-=4;bool rejected=false;
        try {guest::block(data,start);} catch(const guest::Error &) {rejected=true;}
        assert(rejected);
    }
    std::puts("PASS: PS2 material alignment at all four word offsets; malformed payload rejection");
}
