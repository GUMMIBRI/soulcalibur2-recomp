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
        for (size_t length : {0u,1u,4u,12u,15u,16u,20u,28u,31u,32u,63u}) {
            const size_t end = payload + length;
            guest::Bytes sample(end + 4, 0);
            sample[start]=7; sample[start+1]=uint8_t(end-start); sample[start+2]=9;
            std::memcpy(sample.data()+payload,values,length);
            const auto parsed=guest::block(sample,start);
            assert(parsed.size()==1 && parsed[0].colours.size()==length/16*4);
            for (size_t i=0;i<length/16*4;++i) assert(parsed[0].colours[i]==values[i]);
        }
        guest::Bytes header_only(start+8,0);
        header_only[start]=7; header_only[start+1]=4; header_only[start+2]=9;
        assert(guest::block(header_only,start)[0].colours.empty());
        guest::Bytes truncated(payload+15,0);
        truncated[start]=7; truncated[start+1]=uint8_t(payload+16-start); truncated[start+2]=7;
        bool rejected=false;
        try {guest::block(truncated,start);} catch(const guest::Error &) {rejected=true;}
        assert(rejected);
    }
    guest::Bytes empty_env(20,0);
    empty_env[0]=7; empty_env[1]=16; empty_env[2]=9;
    assert(guest::block(empty_env,0)[0].colours.empty());
    empty_env[1]=0;
    bool rejected=false;
    try {guest::block(empty_env,0);} catch(const guest::Error &) {rejected=true;}
    assert(rejected);
    std::puts("PASS: PS2 alignment, empty/partial colours, bounds and zero-size checks");
}
