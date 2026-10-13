# SPDX-License-Identifier: GPL-2.0-or-later
"""Read actual finite source/target planes at original A2 IRQ ACK boundary."""
import json
import struct
from pathlib import Path
from shared_z9_build import sha


def dump_completed(g, states, registers):
    s=states['capture-thumbnail-nv16-state']
    c=states['engine1542-ram-input-control-state']['latched']
    source_y=c['0x20']|(c['0x24']<<32);source_uv=c['0x28']|(c['0x2c']<<32)
    source_n=c['0x38']*c['0x50'];target_n=s['stride']*s['height']
    if not s['jobs'] or not 0<source_n<=64*1024*1024 or not 0<target_n<=64*1024*1024:
        raise ValueError('finite actual thumbnail DMA spans required')
    spans=[('source-y',source_y,source_n),('source-uv',source_uv,source_n),
           ('output-y',s['y'],target_n),('output-uv',s['uv'],target_n)]
    files=[]
    for label,addr,amount in spans:
        if addr&31 or not 0x840000000<=addr<addr+amount<=0x900000000:
            raise ValueError('bounded actual image RAM only')
        if not ((0x840000000<=addr and addr+amount<=0x8adf8da00) or
                (0x8adf8dc00<=addr and addr+amount<=0x8fff47400)):
            raise ValueError('thumbnail observation may not cross image RAM holes')
        p=g.out/('thumbnail-native-'+label+'.bin')
        if p.exists():raise ValueError('do not overwrite a native plane snapshot')
        reply=g.qmp.hmp(f'pmemsave {addr:#x} {amount:#x} "{p}"')
        if reply:raise RuntimeError(reply)
        files.append(dict(label=label,address=hex(addr),length=amount,path=p.name,sha256=sha(p)))
    result=dict(files=files,thumbnail=s,input_control=states['engine1542-ram-input-control-state'],
        graph_registers=states['engine1542-state'],original_pc=hex(registers['PC']),cause=hex(registers['X08']&0xffffffff),
        scope='actual complete source/output planes at original A2 input ACK before original scaler returns; no host pixels or completion supplied',camera_file=False)
    (g.out/'thumbnail-native-observation.json').open('x').write(json.dumps(result,indent=2)+'\n')
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    return result


def dump_border(g, descriptor, thumbnail):
    pitch,uvpitch,width,height,activew,activeh,xoffset,yoffset=struct.unpack_from('<8H',descriptor,8)
    y,uv=struct.unpack_from('<QQ',descriptor,0x18)
    n=pitch*height
    if not 0<width<=1024 or not 0<height<=1024 or pitch!=uvpitch or pitch<width or xoffset or yoffset or activew!=width or activeh!=height:
        raise ValueError('original normalized finite thumbnail descriptor required')
    if not 0<n<=4*1024*1024 or not thumbnail['jobs']:
        raise ValueError('actual completed finite thumbnail only')
    files=[]
    for name,p in [('y',y),('uv',uv)]:
        if p&31 or not any(lo<=p and p+n<=hi for lo,hi in ((0x840000000,0x8adf8da00),(0x8adf8dc00,0x8fff47400))):
            raise ValueError('border snapshot outside complete real RAM bank')
        file=g.out/('thumbnail-native-bordered-'+name+'.bin')
        if file.exists():raise ValueError('border snapshot must not be overwritten')
        reply=g.qmp.hmp(f'pmemsave {p:#x} {n:#x} "{file}"')
        if reply:raise RuntimeError(reply)
        files.append(dict(label=name,address=hex(p),length=n,path=file.name,sha256=sha(file)))
    return dict(files=files,descriptor_hex=descriptor.hex(),width=width,height=height,stride=pitch,
        y=y,uv=uv,scope='actual original CPU border fill and normalized descriptor, before ready-byte store; no JPEG-source assumption')
