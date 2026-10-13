# SPDX-License-Identifier: GPL-2.0-or-later
"""Existing V1.10 runtime resource 0x64 as an explicit C1.11 ROM candidate.

This is captured resource data, not a complete Flash image or proof of version
equivalence. The original resource resolver and version check remain active.
MagicLamp is read only; extracted bytes stay in private run directories.
"""
import hashlib
import json
import struct
from pathlib import Path
from probe import sha
from probe_zr_boot import MAIN, MAIN_SHA

import os
ROOT=Path(os.environ['WL_ZR_RESOURCES']).resolve()
BASE=ROOT/'base-bank-composite-20261009-01'
BASE_FILE=BASE/'a00000000-a16bff000.nonatomic-composite.bin'
BASE_SHA='966d6f64d75aba3ba8e2b2fa289666ffb0db4321a66ba32f5c8be184ba725f87'
MANIFEST_SHA='410ce78505fbee1dbcb409380e8c63eac87327c7369f5230059b780f5bc34274'
HIGH=ROOT/'eg-extension-alias-20261009-01'
CAPTURE=HIGH/'000-e16c00000-e2a874400.bin'
CAPTURE_SHA='a65ef7a7732fc93cf8a61d09fb5d00beceb6fbd749b919a326d2b897e4286230'
ADDRESS=0x47e80000
OBJECT=0xa1d08dd80
SIZE=0x135000
VERSION_OFFSET=0x117ab4


def reconstruct():
    if sha(MAIN)!=MAIN_SHA or sha(BASE_FILE)!=BASE_SHA or sha(CAPTURE)!=CAPTURE_SHA:
        raise ValueError('pinned firmware/capture fingerprint mismatch')
    manifest=BASE/'composite-manifest.json'
    if sha(manifest)!=MANIFEST_SHA:raise ValueError('composite receipt mismatch')
    receipt=json.loads(manifest.read_text())
    if receipt['gaps']!=0 or not receipt['all_written_segments_verified']:
        raise ValueError('complete verified composite required')
    def base_read(address,size):
        matches=[s for s in receipt['segments'] if
            int(s['physical_start'],0)<=address<=int(s['end_exclusive'],0)-size]
        if len(matches)!=1:raise ValueError('metadata must be inside one captured segment')
        with BASE_FILE.open('rb') as f:
            f.seek(address-int(receipt['physical_start'],0));block=f.read(size)
        if len(block)!=size:raise ValueError('short metadata read')
        return block
    item=base_read(0xa02942768,0x30)
    group=base_read(0xa02942e78,0x28)
    pointer=base_read(0xa057b0340,8)
    if (struct.unpack_from('<I',item)[0]!=0x64 or
        struct.unpack_from('<Q',item,8)[0]!=0 or
        struct.unpack_from('<Q',item,0x10)[0]!=OBJECT or
        struct.unpack_from('<Q',item,0x18)[0]!=SIZE or
        struct.unpack_from('<I',item,0x24)[0]!=0x2c or
        struct.unpack_from('<Q',group)[0]!=ADDRESS or
        struct.unpack_from('<Q',pointer)[0]!=OBJECT):
        raise ValueError('captured resource/group/device binding mismatch')
    data=MAIN.read_bytes();header=0x8000
    ram_base=struct.unpack_from('<Q',data,header+0xd8)[0]
    file_base=struct.unpack_from('<Q',data,header+0x148)[0]
    def initial(address,size):
        offset=file_base+address-ram_base
        if not 0<=offset<=len(data)-size:raise ValueError('initializer outside payload')
        return data[offset:offset+size]
    target_item=initial(0xa02942768,0x30)
    target_group=initial(0xa02942e78,0x28)
    # The runtime item pointer is allocated separately. Compare the static
    # resource ID, offset, length and group, not a cross-version heap address.
    if (target_item[:0x10]!=item[:0x10] or target_item[0x18:0x28]!=item[0x18:0x28]
            or target_group[:8]!=group[:8]):
        raise ValueError('C1.11 resource layout differs from captured item')
    capture_receipt=json.loads((HIGH/'result.json').read_text())
    region=capture_receipt['ranges'][0]
    physical=int(region['physical_start'],0)
    if (region['file']!=CAPTURE.name or region['sha256']!=CAPTURE_SHA or
        not region['complete'] or region['gaps'] or
        not physical<=OBJECT<=physical+region['received_bytes']-SIZE):
        raise ValueError('resource not fully received through verified alias')
    with CAPTURE.open('rb') as f:
        f.seek(OBJECT-physical);output=f.read(SIZE)
    if len(output)!=SIZE:raise ValueError('short resource read')
    return output,dict(source_capture=str(CAPTURE),source_capture_sha256=CAPTURE_SHA,
        source_receipt_sha256=sha(HIGH/'result.json'),base_capture_sha256=BASE_SHA,
        base_manifest_sha256=MANIFEST_SHA,item_hex=item.hex(),group_hex=group.hex(),
        pointer_hex=pointer.hex(),target_item_hex=target_item.hex(),
        target_group_hex=target_group.hex())


def attach(g,variant):
    if variant not in ('hardware-captured','zero-version'):
        raise ValueError('unsupported device parameter variant')
    output,record=reconstruct()
    fixture=bytearray(output)
    if variant=='zero-version':fixture[VERSION_OFFSET:VERSION_OFFSET+2]=b'\0\0'
    path=g.out/'zr-device-parameter-rom.bin'
    with path.open('xb') as f:f.write(fixture)
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    record.update(classification='captured runtime resource ROM candidate',variant=variant,
        resource_id='0x64',group='0x2c',source_version='V1.10',target_version='C1.11',
        source_address=hex(OBJECT),target_address=hex(ADDRESS),bytes=SIZE,
        original_resource_sha256=hashlib.sha256(output).hexdigest(),sha256=sha(path),
        original_version_hex=output[VERSION_OFFSET:VERSION_OFFSET+4].hex(),
        complete_flash_dump=False,raw_nvm_recovered=False,atomic_snapshot=False,
        cross_version_equivalence_proven=False,guest_ram_patch=False,
        firmware_patch=False,cpu_redirection=False,end_marker_added=False)
    (g.out/'zr-device-input.json').write_text(json.dumps(record,indent=2)+'\n')
    g.data['device_parameter_rom_input']=record
    g.command+=['-device',f'loader,file={path},addr={ADDRESS:#x},force-raw=on']
