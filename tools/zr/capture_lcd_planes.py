# SPDX-License-Identifier: GPL-2.0-or-later
"""Read the original LCD planes while the owning native probe is paused."""
import json
from pathlib import Path
from probe import sha


def capture(g, label, scanout):
    if not scanout.get('last_frame_has_video'):
        return
    source=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1548-source-state'))
    direct=source['units'][1]['direct']
    w,h=scanout['width'],scanout['height']
    vw,vh=direct[2]&65535,(direct[2]>>16)&16383
    left,top=direct[5]&65535,(direct[5]>>16)&16383
    stride=direct[3];n=stride*vh
    pixel_format=direct[0]&15
    if pixel_format not in (0,4):
        raise ValueError('Unsupported native LCD chroma format')
    uv_height=vh if pixel_format==0 else vh//2
    if not (0<vw<=w and 0<vh<=h and left+vw<=w and top+vh<=h and
            not (vw|vh)&1 and vw<=stride<=8192 and 0<n<=16*1024*1024):
        raise ValueError('Native LCD video geometry changed before plane capture')
    captured={}
    previous_timeout=g.qmp.sock.gettimeout()
    try:
        g.qmp.sock.settimeout(15)
        for kind,addr,amount in [('video-y',scanout['video_y'],n),
                ('video-uv',scanout['video_uv'],stride*uv_height),('alpha',scanout['alpha'],w*h),
                ('color',scanout['color'],w*h*2)]:
            target=g.out/(label+'-'+kind+'.bin')
            if target.exists():raise ValueError('Preserve previous LCD evidence')
            from host_capture_file import memory
            memory(g,addr,amount,target)
            captured[kind]=dict(file=target.name,sha256=sha(target),address=addr,bytes=amount)
    finally:
        g.qmp.sock.settimeout(previous_timeout)
    coefficients=[g.rd(0x15486864+i*4) for i in range(3)]
    raw=json.loads(g.qmp.command('qom-get',path='/machine',property='raw-pipeline-state'))
    outputs=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1542-state'))['blocks']
    output_registers={str(index):outputs[index]['config']
                      for index in (0,1,3,4,5,10,11,15,16,17)}
    controls=json.loads(g.qmp.command('qom-get',path='/machine',property='engine151-control-state'))
    resize=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1543-control-state'))
    g.data.setdefault('pipeline_console_sources',[]).append(dict(label=label,stride=stride,
        width=w,height=h,video_width=vw,video_height=vh,video_left=left,video_top=top,
        source_direct_fields=direct,overlay_coefficients=coefficients,
        video_format='NV16' if pixel_format==0 else 'NV12',video_uv_height=uv_height,
        producer_registers=output_registers,producer_controls=controls,resize_controls=resize,
        scanout=scanout,files=captured,raw_pipeline=raw,
        observer_sha256=sha(Path(__file__))))
    archived=g.out/Path(__file__).name
    if not archived.exists():archived.write_bytes(Path(__file__).read_bytes())
