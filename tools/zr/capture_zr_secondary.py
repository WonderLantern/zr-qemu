# SPDX-License-Identifier: GPL-2.0-or-later
"""Read original secondary geometry and current GPU storage at its submission.

No CPU/RAM writes, no packet completion, no Z9 CPU globals are followed. The
source and target use current shared MMIO windows, with bounded RAM captures.
"""
import json
from pathlib import Path
import struct
from probe import sha
from probe_graphics_image import save


def read_windows(g):
    windows=[]
    for entry in range(0,12,2):
        address=0x140d0040+entry*0x20
        fields=[int(g.qt_command(f'readq {address+off:#x}')[0],0) for off in (0,8,16)]
        windows.append(dict(entry=entry,raw=[hex(v) for v in fields],
            start=fields[0]&0xffffffc0,span=(-(fields[1]&0xffffffc0))&0xffffffff,
            physical=(0x800000000+(fields[2]&0xfffffffc0))&0xfffffffc0))
    return windows


def storage(g,windows,label,local,width,height,bpp):
    size=width*height*bpp
    if not 0<width<=8192 or not 0<height<=8192 or not 0<size<=16*1024*1024:
        raise ValueError('bounded current storage layout required')
    matches={w['physical']+local-w['start'] for w in windows
        if w['start']<=local and local+size<=w['start']+w['span']}
    if len(matches)!=1:raise ValueError('ambiguous/unprovided current GPU aperture')
    physical=matches.pop()
    if not 0xa00000000<=physical<=0xa00000000+g.ram_mib*1024*1024-size:
        raise ValueError('current GPU aperture is outside provisioned work RAM')
    data=b''.join(g.read_bytes(physical+off,min(0x80000,size-off)) for off in range(0,size,0x80000))
    path=g.out/(label+'.bin')
    with path.open('xb') as f:f.write(data)
    return dict(local=hex(local),physical=hex(physical),width=width,height=height,bpp=bpp,
        bytes=size,file=path.name,sha256=sha(path),nonzero_bytes=sum(v!=0 for v in data))


def capture(g,regs):
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    raw=save(g,'zr-secondary-geometry',regs['X00'],44)
    words=list(struct.unpack('<11I',raw))
    if words[0]!=0x2000:raise ValueError('observed 11-word secondary shape differs')
    graphics=json.loads(g.qmp.command('qom-get',path='/machine',property='graphics-state'))
    cfg={(op,reg):value for op,reg,value in graphics['configuration']}
    windows=read_windows(g)
    # Keep the original capture labels and bounds for historical callers.
    read_storage=lambda label,local,width,height,bpp:storage(g,windows,label,local,width,height,bpp)
    source_pitch=cfg.get((0x48,0x4b3),0)
    source_format=cfg.get((0x48,0x4b4),0)
    target_layout=cfg.get((0x48,0x21),0)
    if source_format!=3 or target_layout&0xffff!=0x72:
        raise ValueError('observed RGBA source/two-plane target layout differs')
    source=read_storage('zr-secondary-source',cfg[(0x48,0x4b2)],source_pitch&0xffff,source_pitch>>16,4)
    target_width=target_layout>>16;target_height=(words[2]>>16)+1
    target=read_storage('zr-secondary-target-before',cfg[(0x48,0x20)],target_width,target_height,2)
    alpha=read_storage('zr-secondary-alpha-before',cfg[(0x48,0x2a)],target_width,target_height,1)
    return dict(classification='read_only_pre_secondary_submit_not_LCD',command_words=[hex(v) for v in words],
        configuration=graphics['configuration'],windows=windows,source=source,target=target,alpha=alpha,
        ram_patches=[],cpu_register_redirection=False,lcd_acceptance=False)


def capture_final(g):
    """Current storage at a stopped guest, not a capture at the last job's execution."""
    if g.qmp.command('query-status')['running']:
        raise ValueError('coherent stopped guest required for final display storage')
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    graphics=json.loads(g.qmp.command('qom-get',path='/machine',property='graphics-state'))
    secondary=json.loads(g.qmp.command('qom-get',path='/machine',property='zr-secondary-state'))
    scan=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1548-scanout-state'))
    cfg={(op,reg):value for op,reg,value in graphics['configuration']}
    if not secondary['enabled'] or not secondary['jobs'] or cfg.get((0x48,0x4b4))!=3 or cfg.get((0x48,0x21),0)&0xffff!=0x72:
        raise ValueError('completed RGBA secondary path required')
    windows=read_windows(g)
    source_pitch=cfg[(0x48,0x4b3)]
    target_pitch=cfg[(0x48,0x21)]>>16
    source=storage(g,windows,'zr-final-secondary-source',cfg[(0x48,0x4b2)],source_pitch&0xffff,source_pitch>>16,4)
    target=storage(g,windows,'zr-final-secondary-color',cfg[(0x48,0x20)],target_pitch,secondary['height'],2)
    alpha=storage(g,windows,'zr-final-secondary-alpha',cfg[(0x48,0x2a)],target_pitch,secondary['height'],1)
    if any(int(item['physical'],0)!=secondary[field] for item,field in ((source,'source'),(target,'color'),(alpha,'alpha'))):
        raise ValueError('current configuration no longer identifies last completed secondary storage')
    # A later secondary job may target an offscreen buffer. Capture the
    # actual LCD planes independently instead of treating that job as LCD.
    same=(scan['color'],scan['alpha'])==(secondary['color'],secondary['alpha'])
    scanout_storage=dict(same_secondary_storage=same)
    for field,item,bpp in (('color',target,2),('alpha',alpha,1)):
        if scan[field]==int(item['physical'],0) and (scan['width'],scan['height'])==(item['width'],item['height']):
            scanout_storage[field]=item
            continue
        size=scan['width']*scan['height']*bpp
        locals={w['start']+scan[field]-w['physical'] for w in windows
            if w['physical']<=scan[field] and scan[field]+size<=w['physical']+w['span']}
        if len(locals)!=1:raise ValueError('unique current LCD GPU aperture required')
        scanout_storage[field]=storage(g,windows,'zr-final-scanout-'+field,locals.pop(),scan['width'],scan['height'],bpp)
    ui={label:dict(address=hex(address),raw_hex=save(g,label,address,size).hex())
        for label,address,size in (
            ('zr-final-ui-view-selector',0xa03537c00,4),
            ('zr-final-ui-mode-selector',0xa034fbd80,0x20),
            ('zr-final-ui-mode0-object',0xa034fc1a0,0x118),
            ('zr-final-ui-mode1-object',0xa034fc2b8,0x118),
            ('zr-final-ui-mode2-object',0xa034fc3d0,0x118))}
    from capture_zr_ui_flow import capture as capture_ui
    collection=capture_ui(g,'zr-final-ui-collection',elements=True)
    return dict(classification='read_only_current_display_storage_after_last_job',
        source_sha256=sha(Path(__file__)),configuration=graphics['configuration'],windows=windows,
        source=source,target=target,alpha=alpha,secondary=secondary,scanout=scan,
        scanout_storage=scanout_storage,ui=ui,collection=collection,
        ram_patches=[],cpu_register_redirection=False,lcd_acceptance=False,
        caveat='Source RAM may have changed after the last processed job; this does not by itself prove the input bytes used by that job.')
