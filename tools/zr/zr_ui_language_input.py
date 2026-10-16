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


def prepare(g,language,*,firmware=None,version='1.11'):
    # The C1.10 descriptor tables/mapping are shifted by 16 bytes, while
    # the checked cache, initializer and setter addresses are unchanged.
    versions={'1.11':(MAIN_SHA,0),
        '1.10':('d495cce73462a51b971ad25941a2deea92ccc667f127b930da00949101a51b82',16)}
    if language!='english' or version not in versions:raise ValueError('pinned ZR English preference required')
    source=MAIN if firmware is None else Path(firmware)
    expected,delta=versions[version]
    if sha(source)!=expected:raise ValueError('version-specific ZR language input identity differs')
    data=source.read_bytes();base=0x40160000
    group=data[0x4430a868+delta+0x1d*0x30-base:0x4430a868+delta+(0x1d+1)*0x30-base]
    start,count=struct.unpack_from('<HH',group,0x18)
    descriptor=data[0x442e7948+delta+start*24-base:0x442e7948+delta+start*24-base+24]
    if (start,count)!=(2086,228) or struct.unpack('<3Q',descriptor)!=(0x400000009,CACHE,0x4431a34c+delta):
        raise ValueError('language getter descriptor differs')
    mapping=data[0x42bddd24+delta-base:0x42bddd24+delta-base+30*8]
    if dict(struct.iter_unpack('<2I',mapping)).get(4)!=1 or dict(struct.iter_unpack('<2I',mapping)).get(29)!=0:
        raise ValueError('original language mapping differs')
    g.data['ui_language_preference']=dict(language=language,code=4,locale_index=1,
        firmware_version=version,firmware_sha256=expected,
        baseline_code=26 if version=='1.10' else 29,
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
        record['original_cache_hex']=before.hex()
        if before==struct.pack('<I',4):
            # C1.10's captured input has an English factory default. Retain
            # the original cache and still observe its native setter below.
            record.update(applied=True,applied_without_write=True,
                classification='original English cache observed; no preference RAM edit',
                translation_responses=responses)
            return
        if before!=struct.pack('<I',record['baseline_code']):
            raise ValueError('Language baseline differs: '+before.hex())
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
