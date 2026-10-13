# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded read-only ZR UI collections described by original 404393xx code.

The group and element numbers are ZR C1.11 identities, not shared model enums.
Raw per-element flags are retained without assigning physical meanings to them.
"""
from pathlib import Path
import struct
from probe import sha
from probe_graphics_image import save


def capture(g,label,*,elements=False):
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    key_raw=save(g,label+'-key',0xa028373ac,4)
    pointer_raw=save(g,label+'-pointer',0xa035338f0,8)
    key=struct.unpack('<I',key_raw)[0]
    pointer=struct.unpack('<Q',pointer_raw)[0]
    table=g.read_rom_bytes(0x42bf40f8,14*0x18)
    matches=[struct.unpack_from('<QQI',table,off) for off in range(0,len(table),0x18)
             if struct.unpack_from('<I',table,off)[0]==key]
    row=dict(source_sha256=sha(Path(__file__)),key=key,pointer=hex(pointer),
             key_raw_hex=key_raw.hex(),pointer_raw_hex=pointer_raw.hex(),
             classification='original_UI_collection_storage_not_LCD',ram_patches=[],
             cpu_register_redirection=False,camera_acceptance=False)
    if not matches:
        if key!=14 or pointer:raise ValueError('unknown nonempty original UI collection')
        row.update(count=0,element_ids=[],elements=[])
        return row
    _,expected,count=matches[0]
    if len(matches)!=1 or pointer!=expected or not 0<count<=0x5f:
        raise ValueError('collection differs from original ROM membership table')
    raw=g.read_rom_bytes(pointer,count*4)
    ids=list(struct.unpack('<'+str(count)+'I',raw))
    if len(set(ids))!=len(ids) or any(v>=0x5f for v in ids):
        raise ValueError('bounded distinct original UI element numbers required')
    row.update(count=count,element_ids=ids,membership_hex=raw.hex(),elements=[])
    if not elements:return row
    pointers=struct.unpack('<95Q',g.read_rom_bytes(0x42bf38f0,95*8))
    # These descriptors are a contiguous initialized ZR RAM table. Read it once;
    # still verify every ROM pointer before interpreting an element record.
    if pointers!=tuple(0xa02836c40+i*0x10 for i in range(95)):
        raise ValueError('original UI descriptor table differs')
    headers=save(g,label+'-headers',pointers[0],95*0x10)
    total=0
    for element in ids:
        header=headers[element*0x10:(element+1)*0x10]
        n=header[2];address=struct.unpack_from('<Q',header,8)[0]
        size=n*0x50;total+=size
        if n>128 or total>1024*1024 or (size and not 0xa00000000<=address<=0xa00000000+g.ram_mib*1024*1024-size):
            raise ValueError('bounded original UI element storage required')
        body=save(g,f'{label}-element-{element:02x}',address,size) if size else b''
        row['elements'].append(dict(id=element,header_hex=header.hex(),record_count=n,
            address=hex(address),records_hex=body.hex()))
    return row
