# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded original Z9 thumbnail allocation/request observations, read only."""
import struct
from capture_virtual_ram import read_virtual_ram

POINTS={0x40eb3c84:'thumbnail_application',0x40eb42d0:'thumbnail_build_input',
        0x40eb43c4:'thumbnail_wrapper_before_call',
        0x40eb0f88:'thumbnail_frame_allocated',0x40eaee54:'thumbnail_frame_allocated_early',
        0x40eb9080:'thumbnail_frame_allocated_late',
        0x40eaf850:'thumbnail_scale_application',
        0x40eaf9f8:'thumbnail_scale_before_call',
        0x40eaf9fc:'thumbnail_scale_after_call',
        0x40eafa28:'thumbnail_scale_frame_flags'}

SCALE_POINTS={0x40e89d40:'thumbnail_scale_wrapper',
              0x40cb9bd0:'thumbnail_scale_worker',
              0x40cb9cec:'thumbnail_scale_worker_return',
              0x40c27194:'thumbnail_scale_input_irq_ack',
              0x40c27198:'thumbnail_scale_input_after_ack'}


def observe(g,record,regs,state,arm=None,points=None):
    label=record['name'];cpu=record['cpu']
    record['original_caller']=hex(regs['X30'])
    record['thumbnail_device_states']={name:state(g,name) for name in (
        'engine1518-state','engine1542-state','engine1543-control-state',
        'capture-nv16-pipeline-state','engine151-capture-pixels-state',
        'engine151-control-state','engine15e2-config-state','engine15e2-jpeg-state',
        'capture-thumbnail-nv16-state','engine1542-ram-input-control-state')}
    def read(name,p,n):
        # Work objects may use another original virtual mapping. The shared
        # reader checks every translated page against actual physical work RAM.
        raw=read_virtual_ram(g,p,n,cpu=cpu,allow_image_ram=True);record[name+'_address']=hex(p);record[name+'_hex']=raw.hex()
        return raw
    if label.endswith(('thumbnail_scale_input_irq_ack','thumbnail_scale_input_after_ack')):
        record['input_irq_base']=hex(regs['X00'])
        record['input_irq_cause']=regs['X08']&0xffffffff
        record['scope']='original input W1C instruction before ACK; actual complete source/target RAM dump only, no event supplied'
        thumb=record['thumbnail_device_states']['capture-thumbnail-nv16-state']
        if label.endswith('input_irq_ack') and regs['X00']==0x15421200 and thumb['jobs'] and not g.data.get('thumbnail_native_dump'):
            from capture_thumbnail_nv16 import dump_completed
            g.data['thumbnail_native_dump']=dump_completed(g,record['thumbnail_device_states'],regs)
        # The original ISR scans A0/A1/A2, even for zero status. Pair the
        # current instruction with its original RET; do not rearm the same
        # stopped PC. Native512's one-shot observer was consumed at A0/0.
        if not g.data.get('thumbnail_native_dump') and arm is not None:
            count=g.data.get('thumbnail_irq_observer_pairs',0)
            if label.endswith('input_after_ack'):
                g.data['thumbnail_irq_observer_pairs']=count+1
            other=0x40c27198 if label.endswith('input_irq_ack') else 0x40c27194
            if count<24 and other not in points:arm(other,'capture_app_'+SCALE_POINTS[other])
        return
    if label.endswith('thumbnail_scale_worker_return'):
        record['worker_result']=regs['X22']&0xffffffff
        record['scope']='original worker result before epilogue; no result supplied'
        return
    if label.endswith('thumbnail_scale_worker'):
        record['original_instance']=regs['X00'];read('worker_request',regs['X01'],0xd0)
        return
    if label.endswith('thumbnail_scale_wrapper'):
        read('scale_request',regs['X00'],0x290)
        return
    if label.endswith(('thumbnail_application','thumbnail_build_input','thumbnail_scale_application')):
        job=read('job',regs['X00'],0x40);context=struct.unpack_from('<Q',job,0x18)[0]
        if label.endswith('thumbnail_scale_application') and arm is not None:
            for pc,name in SCALE_POINTS.items():
                if pc not in points:arm(pc,'capture_app_'+name)
    elif label.endswith(('thumbnail_scale_before_call','thumbnail_scale_after_call','thumbnail_scale_frame_flags')):
        context=regs['X21']
        if label.endswith('thumbnail_scale_before_call'):read('scale_request',regs['X00'],0x290)
        if label.endswith('thumbnail_scale_after_call'):record['wrapper_result']=regs['X00']&0xffffffff
    elif label.endswith('thumbnail_wrapper_before_call'):
        context=regs['X19'];read('wrapper_request',regs['X01'],0x60)
    elif label.endswith('thumbnail_frame_allocated_early'):context=regs['X19']
    elif label.endswith('thumbnail_frame_allocated_late'):context=regs['X21']
    else:context=regs['X23']
    if 'frame_allocated' in label and regs['X00']:
        read('new_frame',regs['X00'],0x200)
    raw=read('context',context,0x7a0)
    metadata=struct.unpack_from('<Q',raw,0x790)[0]
    if metadata:read('capture_parameters',metadata,0x300)
    record['frames']=[]
    for off in (0x688,0x690,0x698,0x6a0,0x6a8):
        pointer=struct.unpack_from('<Q',raw,off)[0]
        if not pointer:continue
        frame=read_virtual_ram(g,pointer,0x300,cpu=cpu,allow_image_ram=True)
        record['frames'].append(dict(context_offset=hex(off),address=hex(pointer),frame_hex=frame.hex(),
            scope='bounded original object bytes; no field inferred to be a pixel producer'))
        if label.endswith('thumbnail_scale_frame_flags') and off==0x6a0 and not g.data.get('thumbnail_border_native_dump'):
            thumb=record['thumbnail_device_states']['capture-thumbnail-nv16-state']
            if thumb['jobs']:
                from capture_thumbnail_nv16 import dump_border
                g.data['thumbnail_border_native_dump']=dump_border(g,frame[0x70:0x98],thumb)
    record['scope']='original thumbnail allocation/queue and device state, read-only translated RAM; no pixels/results/flags supplied'
