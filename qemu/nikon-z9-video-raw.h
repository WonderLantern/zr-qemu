/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Functional internal video RAW transport. This authored WLVR/zlib envelope
 * is a simulator-only lossless transport, NOT Nikon compression. Both ends
 * run in modeled devices; original firmware instructions are unchanged.
 * External Bayer -> packed14 FIFO -> real packet RAM -> checked unpack ->
 * functional ISP. No CPU/RTOS flags, media files or display pixels supplied.
 */
#include <zlib.h>

static bool video_raw_descriptor(NikonZ9State *s)
{
    const uint32_t *c=s->primary_d980_latched;
    unsigned w=c[1]>>16,h=c[2]>>16,pitch=c[4];
    if (!s->video_raw_transport_model || !s->raw_pixels || c[0]!=1 ||
        (c[1]&0xffff) || (c[2]&0xffff) || !w || !h || ((w|h)&1) ||
        w>NIKON_RAW_MAX_DIMENSION || h>NIKON_RAW_MAX_DIMENSION ||
        (uint64_t)w*h>NIKON_RAW_MAX_SAMPLES ||
        pitch!=(((w*14+7)/8+31)&~31u) || (uint64_t)pitch*h>128*MiB ||
        c[3] || c[5]!=1 || c[6]!=1 || c[7] || c[8]!=1 || c[9] || c[10]!=3 || c[11]) { return false; }
    for (unsigned row=0;row<4;row++) {
        if (c[12+row*2]!=0xe0000000 || c[13+row*2]) { return false; }
    }
    return true;
}

static void video_raw_decoder_irq_update(NikonZ9State *s)
{
    if (s->video_raw_decoder_irq) {
        qemu_set_irq(s->video_raw_decoder_irq,
            (s->engine1530_config[0x1c/4] & s->engine1530_config[0x18/4])!=0);
    }
}

static bool video_raw_decode(NikonZ9State *s)
{
    if (!s->video_raw_transport_model || !s->video_raw_packet_owned || s->video_raw_frame_ready ||
        !s->engine1530_active || s->engine1530_config[0x404/4] ||
        s->engine1530_config[0x14/4]!=1 || s->engine15b0_config[0x38/4]!=1 ||
        (s->engine1530_config[0x1c/4]&4)) { return false; }
    unsigned row=s->video_raw_packet_row,off=(0x120+row*8)/4;
    uint64_t encoded=s->engine1530_config[off] | (uint64_t)s->engine1530_config[off+1]<<32,source;
    uint8_t header[64];
    if (!raw_pipeline_address(s,encoded,64,&source) || source!=s->video_raw_packet_address ||
        address_space_read(&address_space_memory,source,MEMTXATTRS_UNSPECIFIED,header,64)!=MEMTX_OK ||
        memcmp(header,"WLVR0001",8) || ldl_le_p(header+8)!=64 || ldl_le_p(header+12)!=1 ||
        ldq_le_p(header+16)!=s->video_raw_epoch) { goto invalid; }
    unsigned w=ldl_le_p(header+24),h=ldl_le_p(header+28),pitch=ldl_le_p(header+32);
    uint64_t bytes=ldq_le_p(header+40);unsigned packed=ldl_le_p(header+48),crc=ldl_le_p(header+52);
    if (!w || !h || ((w|h)&1) || w>NIKON_RAW_MAX_DIMENSION || h>NIKON_RAW_MAX_DIMENSION ||
        (uint64_t)w*h>NIKON_RAW_MAX_SAMPLES || pitch!=(((w*14+7)/8+31)&~31u) ||
        bytes!=(uint64_t)pitch*h || bytes>128*MiB || ldl_le_p(header+36)!=14 ||
        !packed || packed>s->engine152c_stream_capacity-64 ||
        !dma_ram_range(s,source+64,packed) || w!=s->video_raw_width || h!=s->video_raw_height) { goto invalid; }
    uint8_t *packet=g_malloc(packed),*raw=g_malloc(bytes);uLongf actual=bytes;
    bool ok=address_space_read(&address_space_memory,source+64,MEMTXATTRS_UNSPECIFIED,packet,packed)==MEMTX_OK &&
        uncompress(raw,&actual,packet,packed)==Z_OK && actual==bytes && crc32(0,raw,bytes)==crc;
    g_free(packet);
    if (!ok) { g_free(raw);goto invalid; }
    /* Decode actual RAM, including declared packed14 row padding. No host
     * RAW cache is substituted for the checked decompressed payload. */
    if (!s->video_raw_pixels || s->video_raw_pixels_crc!=crc ||
        s->video_raw_pixels->width!=w || s->video_raw_pixels->height!=h) {
        uint8_t *samples=g_malloc((uint64_t)w*h*2);
        for (unsigned y=0;y<h;y++) {
            for (unsigned x=0;x<w;x++) {
                unsigned at=x*14/8,shift=(x*14)&7;
                uint32_t value=raw[(uint64_t)y*pitch+at] | ((uint32_t)raw[(uint64_t)y*pitch+at+1]<<8);
                if (shift>2) { value|=(uint32_t)raw[(uint64_t)y*pitch+at+2]<<16; }
                stw_le_p(samples+((uint64_t)y*w+x)*2,(value>>shift)&0x3fff);
            }
        }
        NikonRawPixels *pixels=nikon_raw_pixels_new(samples,w,h,0,16383);g_free(samples);
        if (!pixels) { g_free(raw);goto invalid; }
        nikon_raw_pixels_free(s->video_raw_pixels);s->video_raw_pixels=pixels;
        s->video_raw_pixels_crc=crc;
        for (unsigned ch=0;ch<3;ch++) { g_free(s->raw_pipeline_cache[ch]);s->raw_pipeline_cache[ch]=NULL; }
    }
    g_free(raw);
    s->video_raw_decoded_epoch=s->video_raw_epoch;s->video_raw_decode_jobs++;
    s->video_raw_decoded_bytes+=bytes;s->video_raw_frame_ready=true;
    s->video_raw_packet_owned=false;
    /* Original1530 ISR/W1C owns this completed internal decoder output. */
    s->engine1530_config[0x1c/4]|=4;video_raw_decoder_irq_update(s);
    return true;
invalid:
    s->video_raw_decode_rejects++;return false;
}

static bool video_raw_receive(NikonZ9State *s)
{
    if (!video_raw_descriptor(s) || !s->event_timing_active || s->primary_reset_stage ||
        (s->video_forced_stop_model && (s->engine150c_stop_requested&0x4000)) ||
        !(s->engine150c_active&0x4000) || (s->engine_150c_init[0x18/4]&0x4000) ||
        !s->engine152c_stream_requested || s->engine152c_stream_pending ||
        s->primary_d980_pending || s->video_raw_frame_ready || s->video_raw_packet_owned ||
        !s->engine1530_active || s->engine1530_config[0x404/4]) { return false; }
    unsigned w=s->primary_d980_latched[1]>>16,h=s->primary_d980_latched[2]>>16;
    unsigned pitch=s->primary_d980_latched[4],row=s->engine152c_stream_row;
    uint32_t capacity=s->engine152c_stream_capacity;
    uint64_t output=s->engine152c_stream_outputs[row];
    if (w!=s->engine152c_stream_width || h!=s->engine152c_stream_height ||
        capacity<64 || !dma_ram_range(s,output,capacity)) { s->video_raw_encode_rejects++;return false; }
    size_t bytes=(size_t)pitch*h;
    if (!s->video_raw_compressed || w!=s->video_raw_width || h!=s->video_raw_height || pitch!=s->video_raw_pitch) {
        uint8_t *raw=primary_d980_pack14(s->raw_pixels,w,h,pitch);
        uLongf amount=compressBound(bytes);uint8_t *compressed=g_malloc(amount);
        int result=compress2(compressed,&amount,raw,bytes,3);
        uint32_t checksum=crc32(0,raw,bytes);g_free(raw);
        if (result!=Z_OK || amount>capacity-64) { g_free(compressed);s->video_raw_encode_rejects++;return false; }
        g_free(s->video_raw_compressed);s->video_raw_compressed=compressed;
        s->video_raw_compressed_bytes=amount;s->video_raw_crc=checksum;
        s->video_raw_width=w;s->video_raw_height=h;s->video_raw_pitch=pitch;
    }
    if (s->video_raw_compressed_bytes>capacity-64) { s->video_raw_encode_rejects++;return false; }
    uint8_t *packet=g_malloc0(capacity);
    memcpy(packet,"WLVR0001",8);stl_le_p(packet+8,64);stl_le_p(packet+12,1);
    stq_le_p(packet+16,s->video_raw_epoch+1);stl_le_p(packet+24,w);stl_le_p(packet+28,h);
    stl_le_p(packet+32,pitch);stl_le_p(packet+36,14);stq_le_p(packet+40,bytes);
    stl_le_p(packet+48,s->video_raw_compressed_bytes);stl_le_p(packet+52,s->video_raw_crc);
    memcpy(packet+64,s->video_raw_compressed,s->video_raw_compressed_bytes);
    bool ok=address_space_write(&address_space_memory,output,MEMTXATTRS_UNSPECIFIED,packet,capacity)==MEMTX_OK;
    g_free(packet);
    if (!ok) { s->video_raw_encode_rejects++;return false; }
    s->video_raw_epoch++;s->video_raw_packet_owned=true;s->video_raw_packet_row=row;
    s->video_raw_packet_address=output;s->video_raw_encode_jobs++;s->video_raw_internal_bytes+=bytes;
    s->video_raw_packet_bytes+=capacity;s->engine152c_stream_jobs++;
    s->engine152c_stream_bytes+=capacity;s->engine152c_stream_pending|=4;
    /* The D980 FIFO was internal, not a RAM DMA. Its old RAM-byte/frame
     * counters remain separate from this transport's actual packet writes. */
    /* This internal FIFO is consumed by152c, whose packet event owns the
     * write. It is not a finite D980 RAM transaction. Native389 masks out
     * group1 bit26; attaching that finite event stalls all later frames.
     * Receiver/decoder/output ownership already prevents every overwrite. */
    engine152c_stream_irq_update(s);
    return true;
}

static void video_raw_tick(void *opaque)
{
    NikonZ9State *s=opaque;
    timer_mod(s->video_raw_timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+33333333);
    if (s->video_raw_packet_owned) { video_raw_decode(s); }
    video_backend_drain_tick(s);
    /* Input producer runs on the original source clock via D980 tick. */
}

static bool get_video_raw_transport_model(Object *obj, Error **errp)
{ return NIKON_Z9_LAB(obj)->video_raw_transport_model; }
static void set_video_raw_transport_model(Object *obj, bool value, Error **errp)
{
    NikonZ9State *s=NIKON_Z9_LAB(obj);
    if (s->image_ram.ram || s->image_ram.rom_device) {
        error_setg(errp,"video RAW transport immutable after realization");return;
    }
    s->video_raw_transport_model=value;
}
static char *get_video_raw_transport_state(Object *obj, Error **errp)
{
    NikonZ9State *s=NIKON_Z9_LAB(obj);
    return g_strdup_printf("{\"enabled\":%s,\"epoch\":%" PRIu64 ",\"decoded_epoch\":%" PRIu64
        ",\"consumed_epoch\":%" PRIu64 ",\"encoder_jobs\":%" PRIu64 ",\"decoder_jobs\":%" PRIu64
        ",\"internal_raw_bytes\":%" PRIu64 ",\"packet_ram_bytes\":%" PRIu64 ",\"decoded_bytes\":%" PRIu64
        ",\"encoder_rejects\":%" PRIu64 ",\"decoder_rejects\":%" PRIu64 ",\"frame_ready\":%s,"
        "\"packet_owned\":%s,\"packet_address\":%" PRIu64 ",\"packet_row\":%u,\"compressed_bytes\":%u,"
        "\"width\":%u,\"height\":%u,\"pitch\":%u,\"ring_latched\":%s,\"ring_latches\":%" PRIu64 ","
        "\"nikon_codec_verified\":false,\"physical_sensor_verified\":false,"
        "\"scope\":\"explicit WLVR/zlib simulator transport; actual packet RAM read/decompress, functional Bayer ISP and native output ownership; not Nikon wire compression\"}",
        s->video_raw_transport_model ? "true" : "false",s->video_raw_epoch,s->video_raw_decoded_epoch,
        s->video_raw_consumed_epoch,s->video_raw_encode_jobs,s->video_raw_decode_jobs,
        s->video_raw_internal_bytes,s->video_raw_packet_bytes,s->video_raw_decoded_bytes,
        s->video_raw_encode_rejects,s->video_raw_decode_rejects,s->video_raw_frame_ready ? "true" : "false",
        s->video_raw_packet_owned ? "true" : "false",s->video_raw_packet_address,s->video_raw_packet_row,
        s->video_raw_compressed_bytes,s->video_raw_width,s->video_raw_height,s->video_raw_pitch,
        s->video_raw_ring_latched ? "true" : "false",s->video_raw_ring_latches);
}
