# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit English preference in the virtual ZR's cached setting only.

This is a declared four-byte guest RAM edit, not recovered NVM and not an
unmodified-guest result. Original language initialization and text rendering
continue normally; no instruction, PC, flash file or physical camera is changed.
"""
from pathlib import Path
import struct
from contract_guest import ContractGuest
from probe import sha
from probe_zr_boot import MAIN,MAIN_SHA

CACHE=0xa03fd1768
INIT=0x403fd95c
SETTER=0x4033a034
LOCALE=0xa030faed8
POINTS={INIT:'ui_language_initialization',0x403fd96c:'ui_language_preference_return',
        SETTER:'ui_language_setter',0x4033a080:'ui_language_setter_stored'}


def prepare(g,language):
    if language!='english' or sha(MAIN)!=MAIN_SHA:raise ValueError('pinned ZR English preference required')
    data=MAIN.read_bytes();base=0x40160000
    group=data[0x4430a868+0x1d*0x30-base:0x4430a868+(0x1d+1)*0x30-base]
    start,count=struct.unpack_from('<HH',group,0x18)
    descriptor=data[0x442e7948+start*24-base:0x442e7948+start*24-base+24]
    if (start,count)!=(2086,228) or struct.unpack('<3Q',descriptor)!=(0x400000009,CACHE,0x4431a34c):
        raise ValueError('language getter descriptor differs')
    mapping=data[0x42bddd24-base:0x42bddd24-base+30*8]
    if dict(struct.iter_unpack('<2I',mapping)).get(4)!=1 or dict(struct.iter_unpack('<2I',mapping)).get(29)!=0:
        raise ValueError('original language mapping differs')
    g.data['ui_language_preference']=dict(language=language,code=4,locale_index=1,
        cache_address=hex(CACHE),original_init=hex(INIT),original_setter=hex(SETTER),
        source_sha256=sha(Path(__file__)),descriptor_hex=descriptor.hex(),mapping_hex=mapping.hex(),
        classification='explicit lab cached language preference; four-byte guest RAM edit',
        persistent_nvm_recovered=False,applied=False)
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())


def observe(g,row):
    record=g.data['ui_language_preference'];pc=row['registers']['PC'];cpu=row['cpu']
    if pc==INIT and not record['applied']:
        if g.qmp.command('query-status')['running']:raise ValueError('language input requires paused guest')
        responses=[g.qmp.hmp(f'gva2gpa {address:#x}',cpu) for address in (CACHE,CACHE+3)]
        if [x.strip() for x in responses]!=[f'gpa: {address:#x}' for address in (CACHE,CACHE+3)]:
            raise ValueError('original language cache translation differs')
        before=g.read_bytes(CACHE,4)
        if before!=struct.pack('<I',29):raise ValueError('Japanese baseline cache differs; do not guess a setting')
        after=struct.pack('<I',4)
        (g.out/'zr-language-cache-before.bin').write_bytes(before)
        # Bypass the general prohibition only for this pinned, paused cache.
        # All other ZRGuest.write_bytes calls remain prohibited.
        ContractGuest.write_bytes(g,CACHE,after)
        actual=g.read_bytes(CACHE,4)
        if actual!=after:raise ValueError('language preference write did not match')
        (g.out/'zr-language-cache-after.bin').write_bytes(actual)
        patch=dict(kind='ui_language_preference',address=hex(CACHE),bytes=4,
                   before_hex=before.hex(),after_hex=actual.hex(),pc=hex(pc),cpu=cpu)
        g.data['ram_patches'].append(patch)
        record.update(applied=True,patch=patch,translation_responses=responses)
        row['declared_language_preference']=patch
    elif pc==0x403fd96c:
        row['original_language_code']=row['registers']['X00']&0xffffffff
    elif pc==SETTER:
        row['original_locale_index']=row['registers']['X00']&0xffffffff
    elif pc==0x4033a080:
        row['original_locale_stored_hex']=g.read_bytes(LOCALE,4).hex()
        record['original_locale_stored_hex']=row['original_locale_stored_hex']
