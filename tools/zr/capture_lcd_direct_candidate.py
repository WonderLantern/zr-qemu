# SPDX-License-Identifier: GPL-2.0-or-later
"""Preserve an original direct LCD input even if scanout rejects its format."""
import json
from pathlib import Path
from probe import sha


def capture(g, label='native-direct-candidate'):
    if g.qmp.command('query-status')['running']:raise ValueError('Paused owner required')
    source=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1548-source-state'))['units'][1]
    fields=source['direct'];fmt=fields[0]&31;w=fields[2]&65535;h=fields[2]>>16
    out=dict(scope='Read-only configured input; format0 NV16 interpretation remains a candidate until pixel verification',
        source=source,captured=False,lcd_accepted=False)
    if fmt not in (0,4) or not (0<w<=fields[3]<=8192 and 0<h<=8192 and
            not (w|h)&1 and fields[3]==fields[4] and fields[3]*h<=16*1024*1024):return out
    n=fields[3]*h;end=0xa00000000+g.ram_mib*1024*1024
    pairs=[('y',source['addresses'][0],n),('uv',source['addresses'][1],n//2 if fmt==4 else n)]
    if any(a>>34!=3 or not 0xa00000000<=a-0x400000000<=end-size for _,a,size in pairs):return out
    old=g.qmp.sock.gettimeout();out['planes']={}
    try:
        g.qmp.sock.settimeout(15)
        for name,encoded,size in pairs:
            physical=encoded-0x400000000;file=g.out/(label+'-'+name+'.bin')
            if file.exists():raise ValueError('Preserve original direct-input snapshot')
            reply=g.qmp.hmp(f'pmemsave {physical:#x} {size:#x} "{file}"')
            if reply or file.stat().st_size!=size:raise ValueError('Incomplete direct-input snapshot')
            raw=file.read_bytes()
            out['planes'][name]=dict(file=file.name,bytes=size,physical=physical,sha256=sha(file),
                minimum=min(raw),maximum=max(raw),mean=sum(raw)/len(raw),zero_bytes=raw.count(0))
    finally:g.qmp.sock.settimeout(old)
    out.update(captured=True,width=w,height=h,stride=fields[3],format=fmt)
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    return out
