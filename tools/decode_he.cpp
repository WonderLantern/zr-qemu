/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Authored compatibility harness for the separately pinned public LibRaw PR826.
 * Does not modify a container, camera firmware, codec source or source media.
 * It is not an R3D encoder or a claim of original Nikon arithmetic execution.
 */
#include "nikon_he_decode.h"
#include "nikon_he_picture_header.h"
#include "nikon_he_gtli_table.h"
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>

static int64_t floor_shift(int64_t v,unsigned n) {
    return v>=0 ? v/(INT64_C(1)<<n) : -((-v+(INT64_C(1)<<n)-1)/(INT64_C(1)<<n));
}

int main(int argc,char **argv) {
    if(argc!=3) return 2;
    std::ifstream input(argv[1],std::ios::binary|std::ios::ate);
    if(!input) return 3;
    auto length=input.tellg();
    if(length<0 || length>32*1024*1024) return 4;
    input.seekg(0);std::vector<uint8_t> bytes(static_cast<size_t>(length));
    if(!input.read(reinterpret_cast<char *>(bytes.data()),bytes.size())) return 3;
    nikon_he::PictureHeader ph;
    bool parsed=nikon_he::parse_picture_header(bytes.data(),bytes.size(),ph);
    bool supported=parsed && nikon_he::is_supported_picture_header(ph,bytes.size());
    std::printf("{\"parsed\":%s,\"header_supported\":%s,\"width\":%u,\"height\":%u,\"bands\":%d,\"precinct_offset\":%zu}\n",
        parsed?"true":"false",supported?"true":"false",ph.hdr_width,ph.hdr_height,ph.nbands,ph.precinct_offset);
    std::fflush(stdout);
    if(!supported || !ph.hdr_width || !ph.hdr_height || (uint64_t)ph.hdr_width*ph.hdr_height>50000000) return 5;
    // Public integer transfer described by RdWing in LibRaw#826, Sep11,2026.
    // Avoid the unpatched upstream breakpoint-table endpoint overread.
    size_t pih=2;
    while(pih+4<bytes.size() && !(bytes[pih]==0xff && bytes[pih+1]==0x12)) {
        pih+=2+((unsigned)bytes[pih+2]<<8|bytes[pih+3]);
    }
    if(pih+41>bytes.size() || bytes[pih+2]!=0 || bytes[pih+3]!=39) return 6;
    const uint8_t *tail=bytes.data()+pih+4+24;
    unsigned B=((tail[3]&15)<<8)|tail[4];
    unsigned A=((tail[7]&3)<<16)|(tail[8]<<8)|tail[9];
    unsigned C=(tail[10]<<8)|tail[11];
    std::vector<int32_t> lut(81792);
    for(int index=0;index<(int)lut.size();index++) {
        int64_t i=std::min(index,65535),d=i-C,q;
        if(d<0) q=-d*d;
        else {int64_t t=(d*A+32768)>>16;q=t*t;}
        int64_t raw=std::max(INT64_C(0),std::min(INT64_C(16383),(int64_t)B+floor_shift(q+163840,18)));
        lut[index]=4*raw;
    }
    std::printf("{\"tone_A\":%u,\"tone_B\":%u,\"tone_C\":%u,\"lut_source\":\"public integer formula, no breakpoint OOB\"}\n",A,B,C);
    std::fflush(stdout);
    std::vector<uint16_t> bayer((size_t)ph.hdr_width*ph.hdr_height);
    nikon_he::set_active_picture_header(&ph);
    const auto result=nikon_he::decode_nikon_he_image(bytes.data()+ph.precinct_offset,
        bytes.size()-ph.precinct_offset,ph.hdr_width,ph.hdr_height,lut.data(),bayer.data());
    nikon_he::set_active_picture_header(nullptr);
    std::printf("{\"success\":%s,\"tiles\":%d,\"precincts\":%d}\n",result.success?"true":"false",result.tiles_decoded,result.total_precincts);
    if(!result.success) return 7;
    FILE *output=std::fopen(argv[2],"wbx");
    if(!output) return 8;
    bool written=std::fwrite(bayer.data(),sizeof(uint16_t),bayer.size(),output)==bayer.size();
    return std::fclose(output)==0 && written ? 0 : 9;
}
