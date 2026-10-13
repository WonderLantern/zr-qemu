# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded read-only native1510 pixels and original IRQ/callback receipt."""
import json
import struct
from pathlib import Path


def observe(guest, *, model='zr'):
    get=lambda p:json.loads(guest.qmp.command('qom-get',path='/machine',property=p))
    row = dict(pixels=get('engine151-capture-pixels-state'),
        average=get('engine151-average-result-state') if guest.data.get('probe_arguments',{}).get('engine151_average_result') else None,
        pending=guest.rd(0x15100044),
        registered_callback=hex(struct.unpack('<Q',guest.read_bytes(
            {'zr':0xa02e60d78, 'z9':0xa02cb0910}[model],8))[0]),
        scope='read-only original native1510 checkpoint; no flags or PC edits')
    if model=='zr':row['driver_hex']=guest.read_bytes(0xa028086a8,24).hex()
    if guest.data.get('probe_arguments',{}).get('engine151_raw_output'):
        row['raw_side']=get('engine151-raw-output-state')
    return row


def capture(guest, *, model='zr'):
    report=observe(guest,model=model);guest.data['engine151_pixels_native_observation']=report
    (guest.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    # Failed START does not update the latched snapshot. Read only documented
    # configuration words, retaining the original guest's rejected request.
    offsets=(0x60,0x64,0x200,0x204,0x218,0x21c,0x220,0x400,0x404,
             0x430,0x450,0x454,0x480,0x484,0x4a0,0x4a4,0x4ac,
             0x4c0,0x4c4,0x4d0,0x900,0x904,0x980,0x984,0x9c0,0x9c4)
    report['configured']={hex(off):guest.rd(0x15100000+off) for off in offsets}
    report['row_pairs']=[]
    if not report['pixels']['jobs']:
        (guest.out/'engine151-pixels-native-observation.json').write_text(json.dumps(report,indent=2)+'\n')
        return
    control=json.loads(guest.qmp.command('qom-get',path='/machine',property='engine151-control-state'))
    config=control['instances'][0]['latched']
    iw=config['0x400']&0x3fff;ih=config['0x400']>>16
    cx=config.get('0x454',0)&0x3fff;cy=config.get('0x454',0)>>16
    pitch=config['0x430'];s=report['pixels'];stride=s['stride'];oh=s['height']
    if not 0<iw<=16384 or not 0<ih<=16384 or not 0<pitch<=32768 or not 0<stride<=16384:
        raise ValueError('bounded native pixel geometry required')
    report.update(input_width=iw,input_height=ih,input_pitch=pitch,crop_x=cx,crop_y=cy)
    def physical(address,size):
        if not 0x800000000<=address<=0x900000000-size:raise ValueError('physical sample outside image RAM')
        if model=='zr':
            from contract_guest import ContractGuest
            return ContractGuest.read_bytes(guest,address,size).hex()
        return guest.read_bytes(address,size).hex()
    for y in sorted({0,2,(oh//2)&~1,oh-2}):
        if y<0 or y+2>oh:continue
        report['row_pairs'].append(dict(y=y,
            source_hex=physical(s['source']+(cy+y)*pitch,2*pitch),
            y_hex=physical(s['y']+y*stride,2*stride),
            uv_hex=physical(s['uv']+y*stride,2*stride)))
    (guest.out/'engine151-pixels-native-observation.json').write_text(json.dumps(report,indent=2)+'\n')
