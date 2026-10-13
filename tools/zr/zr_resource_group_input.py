# SPDX-License-Identifier: GPL-2.0-or-later
"""Captured ZR parameter group 13 with explicitly optional diagnostic framing.

Runtime item 13 excludes the four-byte ENDM flash trailer. No capture or pinned
firmware is changed. Supplying that trailer is a lab ROM candidate, not evidence
that its original flash bytes have been recovered or are version equivalent.
"""
import hashlib
import json
from pathlib import Path
import struct
from probe import sha
from probe_zr_boot import MAIN,MAIN_SHA
from zr_device_parameter_input import BASE,BASE_FILE,BASE_SHA,MANIFEST_SHA,HIGH,CAPTURE,CAPTURE_SHA


def reconstruct():
    manifest=BASE/'composite-manifest.json'
    if (sha(MAIN)!=MAIN_SHA or sha(BASE_FILE)!=BASE_SHA or sha(CAPTURE)!=CAPTURE_SHA
            or sha(manifest)!=MANIFEST_SHA):
        raise ValueError('pinned firmware/capture fingerprint mismatch')
    base=json.loads(manifest.read_text())
    if base['gaps'] or not base['all_written_segments_verified']:
        raise ValueError('verified composite required')
    receipt=json.loads((HIGH/'result.json').read_text());region=receipt['ranges'][0]
    physical=int(region['physical_start'],0)
    if (region['file']!=CAPTURE.name or region['sha256']!=CAPTURE_SHA
            or not region['complete'] or region['gaps']):
        raise ValueError('complete captured extension required')
    def metadata(address,size):
        if len([s for s in base['segments'] if int(s['physical_start'],0)<=address
                <=int(s['end_exclusive'],0)-size])!=1:
            raise ValueError('metadata must be inside one received composite segment')
        with BASE_FILE.open('rb') as f:
            f.seek(address-int(base['physical_start'],0));block=f.read(size)
        if len(block)!=size:raise ValueError('short metadata read')
        return block
    data=MAIN.read_bytes();header=0x8000
    ram_base=struct.unpack_from('<Q',data,header+0xd8)[0]
    ram_size=struct.unpack_from('<Q',data,header+0xd0)[0]
    file_base=struct.unpack_from('<Q',data,header+0x148)[0]
    def initial(address,size):
        offset=file_base+address-ram_base
        if not ram_base<=address<=ram_base+ram_size-size or not 0<=offset<=len(data)-size:
            raise ValueError('initializer outside pinned payload')
        return data[offset:offset+size]
    ident=group_id=0x13
    item_address=0xa029414a8+ident*0x30;group_address=0xa02942798+group_id*0x28
    item=metadata(item_address,0x30);group=metadata(group_address,0x28)
    target_item=initial(item_address,0x30);target_group=initial(group_address,0x28)
    off,pointer,length=struct.unpack_from('<QQQ',item,8)
    address,_,group_size=struct.unpack_from('<QQI',group)
    if (struct.unpack_from('<I',item)[0]!=ident or off or length!=0x1fffc
            or struct.unpack_from('<I',item,0x24)[0]!=group_id
            or address!=0x46de0000 or group_size!=0x20000
            or target_item[:0x10]!=item[:0x10] or target_item[0x18:0x28]!=item[0x18:0x28]
            or target_group!=group or not physical<=pointer<=physical+region['received_bytes']-length):
        raise ValueError('complete root item/group identity differs from C1.11')
    with CAPTURE.open('rb') as f:
        f.seek(pointer-physical);content=f.read(length)
    if len(content)!=length or content[:4]!=b'MIIN':raise ValueError('short or unrecognized group content')
    children=[]
    for child in range(101):
        slot=0xa029414a8+child*0x30;entry=metadata(slot,0x30)
        if struct.unpack_from('<I',entry,0x24)[0]!=group_id:continue
        target=initial(slot,0x30);start,heap,size=struct.unpack_from('<QQQ',entry,8)
        if (struct.unpack_from('<I',entry)[0]!=child or start+size>length or heap!=pointer+start
                or target[:0x10]!=entry[:0x10] or target[0x18:0x28]!=entry[0x18:0x28]):
            raise ValueError('captured child identity/layout differs '+hex(child))
        block=content[start:start+size]
        children.append(dict(id=hex(child),offset=hex(start),bytes=size,
            address=hex(address+start),captured_object=hex(heap),
            sha256=hashlib.sha256(block).hexdigest(),item_hex=entry.hex(),target_item_hex=target.hex()))
    if not any(x['id']=='0x22' and x['bytes']==0x200 for x in children):
        raise ValueError('front item 22 is missing from complete root')
    return content,dict(classification='captured runtime resource group; flash framing not captured',
        source_version='V1.10',target_version='C1.11',source_capture=str(CAPTURE),
        source_capture_sha256=CAPTURE_SHA,source_receipt_sha256=sha(HIGH/'result.json'),
        base_capture_sha256=BASE_SHA,base_manifest_sha256=MANIFEST_SHA,
        id=hex(ident),group=hex(group_id),address=hex(address),captured_object=hex(pointer),
        content_bytes=length,group_bytes=group_size,content_sha256=hashlib.sha256(content).hexdigest(),
        item_hex=item.hex(),target_item_hex=target_item.hex(),group_hex=group.hex(),
        target_group_hex=target_group.hex(),children=children,atomic=False,complete_flash_image=False,
        original_flash_trailer_recovered=False,cross_version_equivalence_verified=False,
        firmware_patches=[],ram_patches=[],cpu_register_redirection=False)


def attach(g,variant):
    if variant not in ('captured-content','diagnostic-ENDM'):raise ValueError('unsupported group framing')
    content,record=reconstruct();marker=b'ENDM' if variant=='diagnostic-ENDM' else b''
    blob=content+marker;path=g.out/'zr-resource-group13-rom.bin'
    with path.open('xb') as f:f.write(blob)
    g.command+=['-device',f"loader,file={path},addr={record['address']},force-raw=on"]
    record.update(variant=variant,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),
        end_marker_added=bool(marker),trailer_hex=marker.hex(),
        trailer_scope='explicit diagnostic bytes required by original 40f86dfc' if marker else
            'no trailer supplied; unpopulated ROM reads remain the existing board behavior')
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (g.out/'zr-resource-group13-input.json').write_text(json.dumps(record,indent=2)+'\n')
    g.data['resource_group_rom_input']=record
