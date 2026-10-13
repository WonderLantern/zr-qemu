# SPDX-License-Identifier: GPL-2.0-or-later
"""Four-byte virtual ROM trailers for a Z9 resource-notification experiment.

Only framing is supplied. Resource bodies remain unrecovered; this diagnostic
must never be described as a valid parameter image or camera calibration.
"""
import json
from pathlib import Path
import struct
from probe import MAIN_SHA,sha


GROUPS = {0x0b:(0x0b,0x45aa0000,0x45e80000,0x248000),
          0x55:(0x1f,0x46ca0000,0,0xd2000),
          0x5d:(0x27,0x47700000,0,0x1f5000),
          0x5f:(0x29,0x47e80000,0,0xf2000)}


def attach(g,variant):
    MAIN = g.firmware
    if variant not in ('ENDM','bad-ENDM','extent-ENDM'):raise ValueError('explicit diagnostic trailer variant required')
    if sha(MAIN)!=MAIN_SHA:raise ValueError('pinned Z9 input required')
    data=MAIN.read_bytes()
    ram_base=struct.unpack_from('<Q',data,0x80d8)[0]
    ram_bytes=struct.unpack_from('<Q',data,0x80d0)[0]
    file_base=struct.unpack_from('<Q',data,0x8148)[0]
    def initial(address,size):
        offset=file_base+address-ram_base
        if not ram_base<=address<=ram_base+ram_bytes-size or not 0<=offset<=len(data)-size:
            raise ValueError('bounded original initializer required')
        return data[offset:offset+size]
    record=dict(classification='diagnostic four-byte external resource framing only',
        variant=variant,firmware_sha256=MAIN_SHA,source_sha256=sha(Path(__file__)),items=[],
        resource_body_recovered=False,hardware_calibration=False,physical_flash_verified=False,
        ram_patches=[],firmware_patches=[],cpu_register_redirection=False,camera_acceptance=False)
    for ident,(group,a,b,length) in GROUPS.items():
        item=initial(0xa029256b8+ident*0x30,0x30)
        raw=initial(0xa029268b8+group*0x28,0x28)
        if (struct.unpack_from('<I',item)[0]!=ident or struct.unpack_from('<I',item,0x24)[0]!=group or
            struct.unpack_from('<QQ',raw)!=(a,b) or struct.unpack_from('<I',raw,0x14)[0]!=length or
            raw[0x22]!=1):raise ValueError('pinned original resource group differs')
        for bank,base in enumerate((a,b)):
            if not base:continue
            extent=struct.unpack_from('<I',raw,0x10)[0]
            framed_bytes=extent if variant=='extent-ENDM' else length
            address=base+framed_bytes-4
            if not 0x45000000<=address<=0x48000000-4:raise ValueError('virtual ROM trailer outside aperture')
            payload=b'ENDL' if variant=='bad-ENDM' else b'ENDM'
            path=g.out/f'z9-sequence-tail-{ident:02x}-{bank}.bin'
            with path.open('xb') as stream:stream.write(payload)
            g.command+=['-device',f'loader,file={path},addr={address:#x},force-raw=on']
            record['items'].append(dict(resource_id=hex(ident),group_id=hex(group),bank=bank,
                address=hex(address),bytes=4,hex=payload.hex(),file=path.name,sha256=sha(path),
                original_item_hex=item.hex(),original_group_hex=raw.hex(),data_size=length,
                flash_extent=extent,framed_bytes=framed_bytes))
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (g.out/'z9-sequence-resource-input.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    g.data['sequence_resource_tail_input']=record
