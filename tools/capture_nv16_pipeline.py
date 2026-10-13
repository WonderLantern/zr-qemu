# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only native capture pipeline observations; no injected data or flags."""
import struct
from capture_virtual_ram import read_virtual_ram

POINTS = {0x40c0a978:'capture_nv16_source_isr',
          0x40c0a984:'capture_nv16_source_after_w1c',
          0x40c2599c:'capture_nv16_receiver_isr',
          0x40c25a30:'capture_nv16_receiver_ack_call',
          0x40c25a3c:'capture_nv16_receiver_after_w1c'}


def observe(g,record,regs,state,arm,points):
    label=record['name'];cpu=record['cpu']
    pipeline=state(g,'capture-nv16-pipeline-state')
    record['capture_nv16_pipeline']=pipeline
    record['graph_control']=state(g,'engine1543-control-state')
    record['graph_registers']=state(g,'engine1542-state')
    record['source_registers']=state(g,'engine1518-state')
    record['scope']='actual original ISR/ACK/callback and complete RAM; no OS flags or camera files supplied'
    if label.endswith(('source_isr','receiver_isr')):
        size=0x18 if label.endswith('source_isr') else 0x20
        driver=read_virtual_ram(g,regs['X00'],size,cpu=cpu)
        record['driver_address']=hex(regs['X00']);record['driver_hex']=driver.hex()
        callback=struct.unpack_from('<Q',driver,0x10 if size==0x18 else 0x18)[0]
        record['registered_callback']=hex(callback)
        if callback:
            if not 0x40160000<=callback<0x41600000 or callback&3:
                raise ValueError('original NV16 callback outside verified executable prefix')
            if callback not in points:
                arm(callback,'capture_app_capture_nv16_'+('source' if size==0x18 else 'receiver')+'_callback')
    if label.endswith(('source_callback','receiver_callback')):
        record['callback_event']=hex(regs['X00']);record['callback_cause']=hex(regs['X01'])
    if label.endswith('source_after_w1c'):
        record['isr_cause']=hex(regs['X01'])
    if label.endswith(('receiver_ack_call','receiver_after_w1c')):
        record['ack_base']=hex(regs['X20'])
        if label.endswith('receiver_after_w1c'):
            record['isr_cause']=hex(struct.unpack('<I',read_virtual_ram(g,regs['SP']+0x10+regs['X22'],4,cpu=cpu))[0])
    if not pipeline['jobs'] or g.data.get('capture_nv16_native_dump'):return
    upstream=state(g,'engine151-capture-pixels-state')
    if upstream['jobs']!=pipeline['consumed151job']:
        raise ValueError('capture dump requires original consumed151 generation still current')
    sizes=[]
    for k in ('y','uv'):
        sizes.append(('source-'+k,upstream[k],upstream['stride']*upstream['height']))
    for j,out in enumerate(pipeline['outputs']):
        for k in ('y','uv'):sizes.append(('output'+str(j)+'-'+k,out[k],out['stride']*out['height']))
    files={}
    for name,p,n in sizes:
        if not 0<n<=64*1024*1024 or p&31 or not any(lo<=p and p+n<=hi for lo,hi in
            ((0x840000000,0x8adf8da00),(0x8adf8dc00,0x8fff47400))):
            raise ValueError('native capture dump outside complete bounded real image RAM')
        path=g.out/('capture-nv16-'+name+'.bin')
        reply=g.qmp.hmp(f'pmemsave {p:#x} {n:#x} "{path}"')
        if reply:raise RuntimeError(reply)
        files[name]=dict(file=path.name,address=p,bytes=n)
    g.data['capture_nv16_native_dump']=dict(files=files,pipeline=pipeline,upstream=upstream,
        graph_registers=record['graph_registers'],checkpoint=label,original_pc=record['pc'],
        camera_file=False,physical_algorithm_verified=False,physical_stream_packing_verified=False,
        scope='complete actual source and six output planes before original callback; functional nearest sampling')
