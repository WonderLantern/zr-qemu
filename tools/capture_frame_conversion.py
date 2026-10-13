# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded, read-only observations of original frame-processing requests.

Object pointers are virtual addresses translated on the stopped issuing CPU.
DMA addresses in image descriptors are recorded, never followed as work RAM.
This observer does not create pixels, callbacks, flags or completion events.
"""
import struct
from capture_virtual_ram import read_virtual_ram


POINTS = {
    0x40eb02d0: 'frame_conversion_application_config',
    0x40eb0380: 'frame_conversion_application_start',
    0x40e854fc: 'frame_conversion_config',
    0x40e85698: 'frame_conversion_config_return',
    0x40e856fc: 'frame_conversion_queue',
    0x40c95dd0: 'frame_conversion_worker',
    0x40c95ed8: 'frame_conversion_worker_started',
    0x40c0ad78: 'frame_conversion_driver_config',
    0x40c0b278: 'frame_conversion_driver_config_return',
    0x40c0acd4: 'frame_conversion_driver_start',
    0x40c0ace0: 'frame_conversion_driver_start_return',
    0x40eaf3b0: 'frame_conversion_capture_graph_prepare',
    0x40eaf430: 'frame_conversion_capture_source_config',
    0x40eaf4e4: 'frame_conversion_capture_source_start',
    0x40eaf4b8: 'frame_conversion_application_wait_ready',
    0x40eaf500: 'frame_conversion_application_wait_source_start',
    0x40eaf540: 'frame_conversion_application_wait_input_done',
    0x40eaf578: 'frame_conversion_application_wait_graph_stop',
    0x40eaf5f4: 'frame_conversion_application_finish',
    0x40eaf624: 'frame_conversion_application_commit_frames',
}


def observe(g, record, regs, state):
    cpu = record['cpu']
    label = record['name']
    record['original_caller'] = hex(regs['X30'])
    record['frame_conversion_state'] = {
        'source': state(g, 'engine1518-state'),
        'processor': state(g, 'engine151-state'),
        'capture_pixels': state(g, 'engine151-capture-pixels-state'),
        'primary': state(g, 'engine150c-state'),
        'graph_registers': state(g, 'engine1542-state'),
        'graph_control': state(g, 'engine1543-control-state'),
    }
    record['scope'] = 'translated original request RAM and existing device state; no frame conversion supplied'

    def read(name, address, size):
        raw = read_virtual_ram(g, address, size, cpu=cpu)
        record[name + '_address'] = hex(address)
        record[name + '_hex'] = raw.hex()
        return raw

    if 'application_wait_' in label or label.endswith(('application_finish','application_commit_frames')):
        context=read('context',regs['X19'],0x7a0)
        record['stage_wait_flags']=hex(struct.unpack('<I',read_virtual_ram(g,regs['SP']+0x454,4,cpu=cpu))[0])
        record['stage_wait_result']=regs['X23']&0xffffffff if label.endswith('wait_input_done') else regs['X00']&0xffffffff
        pointer=struct.unpack_from('<Q',context,0x6a0)[0]
        if pointer:
            frame=read('thumbnail_frame',pointer,0xa0)
            record['thumbnail_ready_bytes_18_19_1a']=frame[0x18:0x1b].hex()
        record['scope']='original wait result/flags and frame metadata, read-only; no flags or success supplied'
        return

    application = label.endswith(('application_config', 'application_start'))
    capture_graph = label.endswith(('capture_graph_prepare', 'capture_source_config', 'capture_source_start'))
    if application or capture_graph:
        context = read('context', regs['X22'] if application else regs['X19'], 0x7a0)
        record['context_frames'] = []
        for offset in (0x688, 0x690):
            pointer = struct.unpack_from('<Q', context, offset)[0]
            if pointer:
                raw = read_virtual_ram(g, pointer, 0x280, cpu=cpu)
                record['context_frames'].append(dict(context_offset=hex(offset),
                    address=hex(pointer),frame_hex=raw.hex()))
    if label.endswith(('application_config', 'frame_conversion_config', 'capture_source_config')):
        read('parameter', regs['X01'], 0x180)
    if label.endswith('capture_graph_prepare'):
        read('graph_parameter', regs['X00'], 0x290)
    if label.endswith(('application_start', 'frame_conversion_queue', 'capture_source_start')):
        instance = regs['X00']
        if instance not in (0, 1):
            raise ValueError('original frame conversion instance outside two workers')
        read('static_packet', 0xa03d41590 + instance * 0x290, 0x290)
    if label.endswith('frame_conversion_worker'):
        read('worker_parameter', regs['X01'], 0x180)
        read('wait_parameter', regs['X02'], 0x10)
    if label.endswith(('driver_config', 'driver_start')):
        read('driver', regs['X00'], 0x18)
    if label.endswith('driver_config'):
        raw = read('driver_parameter', regs['X01'], 0x88)
        record['parameter_references'] = []
        # Only record bounded pointed-to work RAM. The roles and lengths of
        # these references remain to be established from the original driver.
        for offset in range(8, 0x88, 8):
            pointer = struct.unpack_from('<Q', raw, offset)[0]
            if pointer:
                pointed = read_virtual_ram(g, pointer, 0x60, cpu=cpu)
                record['parameter_references'].append(dict(offset=hex(offset),
                    address=hex(pointer),prefix_hex=pointed.hex(),semantic_role_verified=False))
