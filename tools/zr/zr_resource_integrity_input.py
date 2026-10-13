# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit resource ROM candidates for ZR's original seven-item check.

Preserve recovered content; unreceived Flash padding and ENDM are diagnostic
inputs. They are not a full Flash dump or proof of C1.11 data equivalence.
MagicLamp/ZR is read only. No guest state, code or checker is modified.
"""
import hashlib
import json
from pathlib import Path
import struct
from probe import sha
from probe_zr_boot import MAIN, MAIN_SHA, ENTRY
from zr_device_parameter_input import BASE, BASE_FILE, BASE_SHA, MANIFEST_SHA, HIGH, CAPTURE, CAPTURE_SHA

IDS=(9,0x56,0x64,0x62,0x5a,0x50)


def reconstruct():
    manifest=BASE/'composite-manifest.json';receipt=HIGH/'result.json'
    for p,want in ((MAIN,MAIN_SHA),(BASE_FILE,BASE_SHA),(CAPTURE,CAPTURE_SHA),(manifest,MANIFEST_SHA)):
        if sha(p)!=want:raise ValueError('pinned resource dependency mismatch')
    base=json.loads(manifest.read_text());region=json.loads(receipt.read_text())['ranges'][0]
    if (base['gaps'] or not base['all_written_segments_verified'] or not region['complete'] or
            region['gaps'] or region['file']!=CAPTURE.name or region['sha256']!=CAPTURE_SHA):
        raise ValueError('complete verified capture dependencies required')
    data=MAIN.read_bytes();rb=struct.unpack_from('<Q',data,0x80d8)[0]
    rs=struct.unpack_from('<Q',data,0x80d0)[0];fb=struct.unpack_from('<Q',data,0x8148)[0]
    def initial(a,n):
        o=fb+a-rb
        if not rb<=a<=rb+rs-n or not 0<=o<=len(data)-n:raise ValueError('initializer boundary')
        return data[o:o+n]
    def base_read(a,n):
        if len([s for s in base['segments'] if int(s['physical_start'],0)<=a<=int(s['end_exclusive'],0)-n])!=1:
            raise ValueError('metadata must be in one received segment')
        with BASE_FILE.open('rb') as f:f.seek(a-int(base['physical_start'],0));b=f.read(n)
        if len(b)!=n:raise ValueError('short metadata')
        return b
    items=[]
    for ident in IDS:
        ia=0xa029414a8+ident*0x30;item=base_read(ia,0x30);target=initial(ia,0x30)
        gi=struct.unpack_from('<I',item,0x24)[0]
        if gi>0x2c:raise ValueError('group outside recovered table')
        ga=0xa02942798+gi*0x28;group=base_read(ga,0x28);tg=initial(ga,0x28)
        off,ptr,length=struct.unpack_from('<QQQ',item,8)
        address,second,size=struct.unpack_from('<QQI',group)
        if (struct.unpack_from('<I',item)[0]!=ident or off or second or group!=tg or
                item[:0x10]!=target[:0x10] or
                (ident!=9 and item[0x18:0x28]!=target[0x18:0x28]) or
                not 0<length<=size-4 or not 0x40000000<=address<=0x48000000-size or
                group[0x22]!=1 or struct.unpack_from('<I',group,0x1c)[0] not in (0,1)):
            raise ValueError('resource identity/layout/framing differs '+hex(ident))
        if ident==9:
            # Original 40f87890 copies this exact pinned C1.11 default object.
            # Its item length is assigned at runtime, unlike the other roots.
            source=0x442b81aa;length=0x1fffc
            if struct.unpack_from('<Q',target,0x18)[0]!=0 or size!=0x20000:
                raise ValueError('original default item9 layout differs')
            content=data[source-ENTRY:source-ENTRY+length]
            scope='original C1.11 ROM default copied by 40f87890'
        else:
            physical=int(region['physical_start'],0)
            if not physical<=ptr<=physical+region['received_bytes']-length:
                raise ValueError('entire resource outside received extension')
            with CAPTURE.open('rb') as f:f.seek(ptr-physical);content=f.read(length)
            source=ptr;scope='captured V1.10 runtime object; C1.11 equivalence unproven'
        if len(content)!=length:raise ValueError('short original content')
        padding=size-length-4
        # Functional Flash input uses explicit 0xff for unreceived padding.
        # The four-byte trailer is intentionally synthetic, never called a
        # recovered signature or a hardware measurement.
        blob=content+b'\xff'*padding+b'ENDM'
        if len(blob)!=size:raise ValueError('framed input size mismatch')
        rec=dict(resource_id=hex(ident),group_id=hex(gi),address=hex(address),bytes=size,
            content_bytes=length,content_sha256=hashlib.sha256(content).hexdigest(),
            sha256=hashlib.sha256(blob).hexdigest(),source_address=hex(source),source_scope=scope,
            item_hex=item.hex(),target_item_hex=target.hex(),group_hex=group.hex(),
            diagnostic_padding_bytes=padding,padding_byte=255,diagnostic_trailer_hex=b'ENDM'.hex(),
            original_flash_trailer_recovered=False,cross_version_equivalence_verified=ident==9)
        items.append((blob,rec))
    spans=sorted((int(x['address'],0),int(x['address'],0)+x['bytes']) for _,x in items)
    if any(a[1]>b[0] for a,b in zip(spans,spans[1:])):raise ValueError('overlapping resource inputs')
    return items,dict(classification='explicit functional resource ROM with diagnostic framing',
        main_sha256=MAIN_SHA,source_capture=str(CAPTURE),source_capture_sha256=CAPTURE_SHA,
        source_receipt_sha256=sha(receipt),base_capture_sha256=BASE_SHA,base_manifest_sha256=MANIFEST_SHA,
        complete_flash_image=False,atomic=False,physical_flash_semantics_verified=False,
        firmware_patches=[],ram_patches=[],cpu_register_redirection=False)


def configuration_input(blob,item,variant):
    """One explicit non-executable ROM setting; retain every other byte."""
    if variant not in ('diagnostic-ENDM','diagnostic-ENDM-video-capability'):
        raise ValueError('explicit diagnostic framing required')
    if variant=='diagnostic-ENDM' or item['resource_id']!='0x9':
        return blob,dict(item)
    if (len(blob)!=0x20000 or item['content_bytes']!=0x1fffc or
            blob[-4:]!=b'ENDM' or blob[0x124]!=0):
        raise ValueError('pinned default configuration/framing required')
    output=bytearray(blob);output[0x124]=1
    record=dict(item)
    record.update(sha256=hashlib.sha256(output).hexdigest(),
        content_sha256=hashlib.sha256(output[:item['content_bytes']]).hexdigest(),
        original_default_blob_sha256=hashlib.sha256(blob).hexdigest(),
        configuration_changes=[dict(offset='0x124',before=0,after=1,
            scope='synthetic display-route configuration read by original403951d0; legacy variant name does not establish PHOTO/VIDEO mode')],
        source_scope='original C1.11 default with explicit synthetic configuration input',
        cross_version_equivalence_verified=False)
    return bytes(output),record


def attach(g,variant):
    if variant not in ('diagnostic-ENDM','diagnostic-ENDM-video-capability'):
        raise ValueError('explicit diagnostic framing required')
    if not g.data.get('resource_group_rom_input',{}).get('end_marker_added'):
        raise ValueError('original group13 diagnostic input required')
    items,record=reconstruct();record.update(variant=variant,items=[])
    existing=g.data.get('device_parameter_rom_input',{})
    for original,item in items:
        blob,item=configuration_input(original,item,variant)
        prefix=0
        if item['resource_id']=='0x64':
            if (existing.get('variant')!='hardware-captured' or existing.get('target_address')!=item['address'] or
                    existing.get('bytes')!=item['content_bytes'] or existing.get('sha256')!=item['content_sha256']):
                raise ValueError('existing device resource must match the entire original prefix')
            prefix=item['content_bytes']
        path=g.out/('zr-resource-integrity-'+item['resource_id'][2:]+'.bin')
        payload=blob[prefix:]
        with path.open('xb') as f:f.write(payload)
        item.update(loader_address=hex(int(item['address'],0)+prefix),loader_bytes=len(payload),
                    loader_prefix_already_supplied=prefix,loader_file=path.name,loader_sha256=sha(path))
        g.command+=['-device',f"loader,file={path},addr={item['loader_address']},force-raw=on"]
        record['items'].append(item)
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (g.out/'zr-resource-integrity-input.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    g.data['resource_integrity_rom_input']=record
