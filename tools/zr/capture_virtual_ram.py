# SPDX-License-Identifier: GPL-2.0-or-later
"""Read a stopped emulator's virtual RAM through verified CPU translations.

No writes, CPU redirection, MMU bypass or physical non-RAM reads. Translations
must cover every page and both ends of a bounded contiguous physical span.
"""
import re


def read_virtual_ram(g, address, size, *, cpu, allow_image_ram=False):
    lower=0xa00000000
    if getattr(g,'ram_mib',None) not in (512,1024):
        raise ValueError('known work RAM geometry required')
    upper=lower+g.ram_mib*1024*1024
    if (not 0<=cpu<4 or not 0<size<=0x2000 or
            not 0<=address<=2**64-size):
        raise ValueError('bounded virtual RAM request required')
    if g.qmp.command('query-status')['running']:
        raise ValueError('virtual capture requires a stopped guest')
    virtuals=sorted({address,address+size-1,
                    *range((address+0xfff)&~0xfff,address+size,0x1000)})
    responses=[g.qmp.hmp(f'gva2gpa {v:#x}',cpu) for v in virtuals]
    matches=[re.fullmatch(r'gpa: (0x[0-9a-fA-F]+)\s*',s) for s in responses]
    if not all(matches):
        g.data.setdefault('virtual_ram_rejections',[]).append(dict(
            virtual=hex(address),bytes=size,cpu=cpu,responses=responses,
            reason='CPU translation failed; no physical read'))
        raise ValueError('virtual RAM translation failed')
    physicals=[int(m.group(1),16) for m in matches]
    physical=physicals[0]
    region='work' if lower<=physical<=upper-size else None
    # These are the actual sparse image RAM banks in the validated EXPEED7
    # board. Opt in explicitly for original metadata objects in this pool;
    # keep the 512-byte gap and all non-RAM addresses unreadable.
    image_banks=((0x840000000,0x8adf8da00),(0x8adf8dc00,0x8fff47400))
    if allow_image_ram and any(lo<=physical<=hi-size for lo,hi in image_banks):
        region='image'
    if region is None or any(p!=physical+v-address for p,v in zip(physicals,virtuals)):
        g.data.setdefault('virtual_ram_rejections',[]).append(dict(
            virtual=hex(address),physical=hex(physical),bytes=size,cpu=cpu,
            responses=responses,allow_image_ram=allow_image_ram,
            reason='noncontiguous or outside allowed RAM banks; no physical read'))
        raise ValueError('noncontiguous or non-RAM virtual capture')
    raw=bytes.fromhex(g.qt_command(f'read {physical:#x} {size:#x}')[0][2:])
    if len(raw)!=size:
        raise ValueError('truncated physical RAM capture')
    g.data.setdefault('memory_translations',[]).append(dict(
        virtual=hex(address),physical=hex(physical),bytes=size,cpu=cpu,
        responses=responses,ram_region=region,
        scope='bounded stopped-CPU virtual RAM observation'))
    return raw
