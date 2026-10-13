# SPDX-License-Identifier: GPL-2.0-or-later
"""Read the stopped current LCD independently of the last secondary job.

The current graphics target must match the actually latched LCD planes. No
pixels, guest memory, registers or completion state are changed.
"""
import json
from pathlib import Path

from capture_zr_secondary import read_windows,storage
from probe import sha


def capture_latched(g):
    """Read displayed planes even when the GPU prepares a different buffer.

    This is a separate explicit scope. It does not relax the older requirement
    that the current drawing target equals the display target.
    """
    if g.qmp.command('query-status')['running']:raise ValueError('stopped LCD capture required')
    source=Path(__file__);dependency=source.with_name('capture_zr_secondary.py')
    (g.out/source.name).write_bytes(source.read_bytes())
    (g.out/dependency.name).write_bytes(dependency.read_bytes())
    graphics=json.loads(g.qmp.command('qom-get',path='/machine',property='graphics-state'))
    scan=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1548-scanout-state'))
    if (not scan['active'] or not scan['frames'] or (scan['width'],scan['height'])!=(1280,800) or
            scan['unit']!=1 or scan['layer']!=0 or graphics['fault'] or graphics['ring']['fault']):
        raise ValueError('active native 1280x800 LCD and nonfaulted graphics required')
    windows=read_windows(g);planes={}
    for field,bpp in (('color',2),('alpha',1)):
        size=scan['width']*scan['height']*bpp
        locals={w['start']+scan[field]-w['physical'] for w in windows
            if w['physical']<=scan[field] and scan[field]+size<=w['physical']+w['span']}
        if len(locals)!=1:raise ValueError('unique actual LCD aperture required')
        item=storage(g,windows,'zr-latched-lcd-'+field,locals.pop(),scan['width'],scan['height'],bpp)
        if int(item['physical'],0)!=scan[field]:raise ValueError('actual LCD plane identity mismatch')
        planes[field]=item
    if planes['color']['physical']==planes['alpha']['physical']:raise ValueError('distinct actual LCD planes required')
    from capture_lcd_direct_candidate import capture as capture_direct
    direct_candidate=capture_direct(g)
    return dict(classification='read_only_latched_LCD_independent_of_current_drawing_buffer',
        source_sha256=sha(source),storage_helper_sha256=sha(dependency),
        windows=windows,graphics=graphics,scanout=scan,planes=planes,direct_candidate=direct_candidate,
        drawing_target_is_latched=graphics['path']['target']==scan['color'],
        ram_patches=[],cpu_register_redirection=False,lcd_acceptance=False,
        caveat='Displayed planes only; no claim that the current offscreen GPU job generated these pixels.')


def capture_final(g):
    if g.qmp.command('query-status')['running']:
        raise ValueError('stopped LCD capture required')
    source=Path(__file__)
    (g.out/source.name).write_bytes(source.read_bytes())
    dependency=source.with_name('capture_zr_secondary.py')
    (g.out/dependency.name).write_bytes(dependency.read_bytes())
    graphics=json.loads(g.qmp.command('qom-get',path='/machine',property='graphics-state'))
    scan=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1548-scanout-state'))
    secondary=json.loads(g.qmp.command('qom-get',path='/machine',property='zr-secondary-state'))
    cfg={(o,a):v for o,a,v in graphics['configuration']}
    if (not scan['active'] or not scan['frames'] or (scan['width'],scan['height'])!=(1280,800) or
        graphics['fault'] or graphics['ring']['fault'] or graphics['path']['pending'] or
        cfg.get((0x48,0x21))!=(1280<<16|0x72) or
        cfg.get((0x48,0x23))!=cfg[(0x48,0x21)] or
        cfg.get((0x48,0x22))!=cfg.get((0x48,0x20)) or
        cfg.get((0x48,0x2b))!=cfg.get((0x48,0x2a)) or
        graphics['path']['target']!=scan['color']):
        raise ValueError('completed current graphics target and latched packed LCD required')
    windows=read_windows(g)
    planes={}
    for field,reg,bpp in (('color',0x20,2),('alpha',0x2a,1)):
        item=storage(g,windows,'zr-current-lcd-'+field,cfg[(0x48,reg)],1280,800,bpp)
        if int(item['physical'],0)!=scan[field]:
            raise ValueError('current graphics '+field+' is not latched LCD storage')
        planes[field]=item
    if planes['color']['physical']==planes['alpha']['physical']:
        raise ValueError('distinct LCD planes required')
    return dict(classification='read_only_current_LCD_independent_of_last_secondary',
        source_sha256=sha(source),storage_helper_sha256=sha(dependency),
        windows=windows,configuration=graphics['configuration'],graphics=graphics,
        scanout=scan,secondary=secondary,planes=planes,
        same_secondary_storage=(scan['color'],scan['alpha'])==(secondary['color'],secondary['alpha']),
        ram_patches=[],cpu_register_redirection=False,lcd_acceptance=False,
        caveat='Current LCD snapshot; does not prove CMOS input or pixels used by an earlier secondary job.')
