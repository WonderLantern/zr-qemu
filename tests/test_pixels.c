/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <glib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#define MiB (1024 * 1024)
static uint16_t lduw_le_p(const void *p) {
    const uint8_t *b = p;
    return b[0] | ((uint16_t)b[1] << 8);
}
#include "../qemu/nikon-raw-pixels.h"
int main(void) {
    const uint8_t red[8] = {255,15,0,0,0,0,0,0};
    const uint8_t white[8] = {255,15,255,15,255,15,255,15};
    const uint8_t black[8] = {0};
    const uint8_t *inputs[] = {red, white, black};
    const int expected[][3] = {{77,85,255},{255,128,128},{0,128,128}};
    for (unsigned i=0;i<3;i++) {
        NikonRawPixels *p=nikon_raw_pixels_new(inputs[i],2,2,0,4095);
        assert(p);
        for (unsigned half=0;half<2;half++) {
            uint8_t *out=nikon_raw_pixels_yuv(p,8,6,10,half);
            assert(out);
            for (unsigned y=0;y<6;y++) {
                for (unsigned x=0;x<8;x++) assert(abs(out[y*10+x]-expected[i][0])<=1);
                assert(out[y*10+8]==0 && out[y*10+9]==0);
            }
            for (unsigned y=0;y<(half?3:6);y++) {
                for (unsigned x=0;x<8;x+=2) {
                    assert(abs(out[60+y*10+x]-expected[i][1])<=1);
                    assert(abs(out[61+y*10+x]-expected[i][2])<=1);
                }
                assert(out[68+y*10]==128 && out[69+y*10]==128);
            }
            g_free(out);
        }
        assert(!nikon_raw_pixels_yuv(p,8,6,6,true));
        assert(!nikon_raw_pixels_yuv(p,7,6,8,true));
        nikon_raw_pixels_free(p);
    }
    assert(!nikon_raw_pixels_new(red,1,2,0,4095));
    assert(!nikon_raw_pixels_new(red,2,2,4095,4095));
    return 0;
}
