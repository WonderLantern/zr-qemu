# SPDX-License-Identifier: GPL-2.0-or-later
"""Partial display-parameter ROM reconstructed from an existing ZR RAM capture.

This is a V1.10-derived candidate for C1.11, not a complete Flash/calibration
image. Only fields read by the pinned C1.11 constructor are reconstructed.
Unknown bytes stay zero. No main firmware, guest RAM, CPU or callback edits.
"""
import hashlib
import json
from pathlib import Path
from probe import sha
from probe_zr_boot import MAIN, MAIN_SHA

from zr_device_parameter_input import ROOT
CAPTURE=ROOT/'nonlinux-dram-20261008-01/001-a02cc5000-a063de000.bin.partial'
CAPTURE_SHA='90b77eede9e0d3f285e0a9b307031dea0fa13dc051ff0798a25facdd45b9f41d'
OBJECT=0xa03046cc8
OBJECT_SHA='24314390b4d5226d57220267417685dc3acaf1065f5462e06f8ace6b2b36cdc1'
ADDRESS=0x46dea800
SIZE=0x700


def reconstruct():
    if sha(MAIN)!=MAIN_SHA or sha(CAPTURE)!=CAPTURE_SHA:
        raise ValueError('firmware/hardware capture identity mismatch')
    receipt=json.loads((CAPTURE.parent/'result.json').read_text())
    region=receipt['ranges'][1]
    if region['file']!=CAPTURE.name or region['sha256']!=CAPTURE_SHA:
        raise ValueError('capture receipt mismatch')
    if not int(region['start'],0)<=OBJECT<=int(region['next_address'],0)-0xeac:
        raise ValueError('display object not fully received')
    if any(OBJECT<int(g['end_exclusive'],0) and int(g['start'],0)<OBJECT+0xeac
           for g in region['gaps']):raise ValueError('capture hole overlaps object')
    with CAPTURE.open('rb') as f:
        f.seek(OBJECT-int(region['start'],0));block=f.read(0xeac)
    if hashlib.sha256(block).hexdigest()!=OBJECT_SHA:
        raise ValueError('display object mismatch')
    # Exact read/copy layout of native 402e1764..402e2184. Arrays are
    # 15 words each; unconsumed padding and runtime-only fields are omitted.
    spans=[(s,d,15*4) for s,d in
        ((0x178,0x894),(0x1c0,0x948),(0x1c,0x8d0),
         (0xac,0x984),(0x64,0x90c),(0xf4,0x9c0))]
    spans += [(0x208,0x6bc,0x28),(0x13c,0x680,0x2c),
              (0x23c,0x9fc,0x454),(0x6a4,0xe50,0x5c)]
    output=bytearray(SIZE);known=bytearray(SIZE)
    for src,dst,count in spans:
        if any(known[src:src+count]):raise ValueError('overlapping reconstructed fields')
        output[src:src+count]=block[dst:dst+count]
        known[src:src+count]=b'\1'*count
    return bytes(output),block,spans,known


def attach(g,variant):
    if variant not in ('hardware-reconstructed','zero-first-length'):
        raise ValueError('unsupported display input')
    output,block,spans,known=reconstruct()
    fixture=bytearray(output)
    if variant=='zero-first-length':fixture[0x23c:0x240]=b'\0'*4
    path=g.out/'zr-display-parameter-rom.bin'
    with path.open('xb') as f:f.write(fixture)
    (g.out/'zr-display-hardware-object.bin').write_bytes(block)
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    record=dict(classification='partial reconstructed parameter ROM candidate',
        variant=variant,source_version='V1.10',target_version='C1.11',
        source_capture=str(CAPTURE),source_capture_sha256=CAPTURE_SHA,
        object_address=hex(OBJECT),object_sha256=OBJECT_SHA,
        target_address=hex(ADDRESS),bytes=SIZE,sha256=sha(path),
        mapped_bytes=sum(known),unknown_bytes=SIZE-sum(known),
        spans=[dict(source_offset=hex(s),object_offset=hex(d),bytes=n) for s,d,n in spans],
        complete_flash_dump=False,raw_nvm_recovered=False,hardware_layout_equivalence_proven=False,
        original_constructor='402e1764..402e2184',
        guest_ram_patch=False,cpu_redirection=False,firmware_patch=False,
        end_marker_added=False)
    (g.out/'zr-display-input.json').write_text(json.dumps(record,indent=2)+'\n')
    g.data['display_parameter_rom_input']=record
    g.command += ['-device',f'loader,file={path},addr={ADDRESS:#x},force-raw=on']
    return bytes(fixture)
