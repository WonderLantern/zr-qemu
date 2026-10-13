# SPDX-License-Identifier: GPL-2.0-or-later
"""Two captured V1.10 parameter items for the native C1.11 F205 driver.

Only external ROM inputs are supplied. The source tree is read only, and the
original initialization, bus driver and completion callbacks remain active.
Captured runtime resource data is not a complete Flash/calibration image.
"""
import hashlib
import json
import struct
from pathlib import Path
from probe import sha
from probe_zr_boot import MAIN,MAIN_SHA
from zr_device_parameter_input import BASE,BASE_FILE,BASE_SHA,MANIFEST_SHA,HIGH,CAPTURE,CAPTURE_SHA

ITEMS=((0x18,0x46dea400,0x200),(0x43,0x46e00100,0x100))


def reconstruct():
    manifest=BASE/'composite-manifest.json'
    if (sha(MAIN)!=MAIN_SHA or sha(BASE_FILE)!=BASE_SHA or sha(CAPTURE)!=CAPTURE_SHA
            or sha(manifest)!=MANIFEST_SHA):
        raise ValueError('pinned firmware/capture fingerprint mismatch')
    base=json.loads(manifest.read_text())
    if base['gaps'] or not base['all_written_segments_verified']:
        raise ValueError('verified composite required')
    receipt=json.loads((HIGH/'result.json').read_text())
    region=receipt['ranges'][0];physical=int(region['physical_start'],0)
    if (region['file']!=CAPTURE.name or region['sha256']!=CAPTURE_SHA
            or not region['complete'] or region['gaps']):
        raise ValueError('complete captured extension required')
    data=MAIN.read_bytes();header=0x8000
    ram_base=struct.unpack_from('<Q',data,header+0xd8)[0]
    file_base=struct.unpack_from('<Q',data,header+0x148)[0]
    ram_size=struct.unpack_from('<Q',data,header+0xd0)[0]
    def base_read(address,size):
        if len([s for s in base['segments'] if int(s['physical_start'],0)<=address
                <=int(s['end_exclusive'],0)-size])!=1:
            raise ValueError('metadata must be inside one received composite segment')
        with BASE_FILE.open('rb') as f:
            f.seek(address-int(base['physical_start'],0));block=f.read(size)
        if len(block)!=size:raise ValueError('short metadata read')
        return block
    def initial(address,size):
        offset=file_base+address-ram_base
        if not ram_base<=address<=ram_base+ram_size-size or not 0<=offset<=len(data)-size:
            raise ValueError('initializer outside payload')
        return data[offset:offset+size]
    output=[]
    for ident,address,size in ITEMS:
        item_address=0xa029414a8+ident*0x30
        item=base_read(item_address,0x30)
        off,pointer,length=struct.unpack_from('<QQQ',item,8)
        group_id=struct.unpack_from('<I',item,0x24)[0]
        if group_id>0x2c:raise ValueError('unknown group range')
        group_address=0xa02942798+group_id*0x28
        group=base_read(group_address,0x28)
        target_item=initial(item_address,0x30);target_group=initial(group_address,0x28)
        if (struct.unpack_from('<I',item)[0]!=ident or length!=size
                or struct.unpack_from('<Q',group)[0]+off!=address
                or target_item[:0x10]!=item[:0x10] or target_item[0x18:0x28]!=item[0x18:0x28]
                or target_group[:8]!=group[:8]):
            raise ValueError('captured/C1.11 item identity or layout differs')
        if not physical<=pointer<=physical+region['received_bytes']-size:
            raise ValueError('entire resource must be inside the received extension')
        with CAPTURE.open('rb') as f:
            f.seek(pointer-physical);block=f.read(size)
        if len(block)!=size:raise ValueError('short parameter resource read')
        output.append((block,dict(id=hex(ident),address=hex(address),bytes=size,
            captured_object=hex(pointer),sha256=hashlib.sha256(block).hexdigest(),
            item_hex=item.hex(),group_hex=group.hex(),target_item_hex=target_item.hex(),
            target_group_hex=target_group.hex())))
    return output,dict(classification='captured runtime parameter ROM candidate',
        source_version='V1.10',target_version='C1.11',
        source_capture=str(CAPTURE),source_capture_sha256=CAPTURE_SHA,
        source_receipt_sha256=sha(HIGH/'result.json'),base_capture_sha256=BASE_SHA,
        base_manifest_sha256=MANIFEST_SHA,atomic=False,complete_flash_image=False,
        cross_version_equivalence_verified=False,firmware_patches=[],ram_patches=[],
        cpu_register_redirection=False,physical_sensor_protocol_verified=False)


def attach(g,variant):
    if variant!='hardware-captured':raise ValueError('unsupported orientation input')
    items,record=reconstruct();record.update(variant=variant,items=[])
    for block,item in items:
        group=g.data.get('resource_group_rom_input')
        covered=[child for child in group['children'] if child['id']==item['id']] if group else []
        if covered and (len(covered)!=1 or any(covered[0][key]!=item[key]
                for key in ('address','bytes','sha256'))):
            raise ValueError('whole-group orientation resource differs from captured item')
        p=g.out/('zr-orientation-resource-'+item['id'][2:]+'.bin')
        with p.open('xb') as f:f.write(block)
        if covered:
            item['loader_scope']='identical item already supplied by complete resource group'
            item['supplied_by_group']=group['id']
        else:
            g.command+=['-device',f"loader,file={p},addr={item['address']},force-raw=on"]
            item['loader_scope']='separate captured item loader'
        record['items'].append(item)
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (g.out/'zr-orientation-input.json').write_text(json.dumps(record,indent=2)+'\n')
    g.data['orientation_parameter_rom_input']=record
