# SPDX-License-Identifier: GPL-2.0-or-later
"""Private captured resource0c with explicit, unrecovered Flash framing.

Preserves all captured item bytes. Only a fresh primary-bank ROM input is
created; original firmware, captures and runtime event state stay untouched.
The secondary bank remains absent. Source V1.10/C1.11 equivalence is unproved.
"""
import hashlib
import json
from pathlib import Path
import struct
from probe import sha
from probe_zr_boot import MAIN,MAIN_SHA
from zr_device_parameter_input import BASE,BASE_FILE,BASE_SHA,MANIFEST_SHA,HIGH,CAPTURE,CAPTURE_SHA

CONTENT_SHA='6c2ab58fc323a5fef2907c77a53326bd700906495cdbfdb288ad5cc574f3426a'
ADDRESS=0x465e0000
SECONDARY=0x469c0000
SIZE=0x260000
LENGTH=0x200000


def reconstruct():
    manifest=BASE/'composite-manifest.json';receipt=HIGH/'result.json'
    for p,want in ((MAIN,MAIN_SHA),(BASE_FILE,BASE_SHA),(CAPTURE,CAPTURE_SHA),(manifest,MANIFEST_SHA)):
        if sha(p)!=want:raise ValueError('pinned resource0c dependency mismatch')
    base=json.loads(manifest.read_text());region=json.loads(receipt.read_text())['ranges'][0]
    if (base['gaps'] or not base['all_written_segments_verified'] or not region['complete'] or
            region['gaps'] or region['file']!=CAPTURE.name or region['sha256']!=CAPTURE_SHA):
        raise ValueError('complete verified capture dependencies required')
    def captured_metadata(address,size):
        if len([s for s in base['segments'] if int(s['physical_start'],0)<=address
                <=int(s['end_exclusive'],0)-size])!=1:raise ValueError('metadata outside complete segment')
        with BASE_FILE.open('rb') as f:
            f.seek(address-int(base['physical_start'],0));block=f.read(size)
        if len(block)!=size:raise ValueError('short captured metadata')
        return block
    data=MAIN.read_bytes();rb=struct.unpack_from('<Q',data,0x80d8)[0]
    rs=struct.unpack_from('<Q',data,0x80d0)[0];fb=struct.unpack_from('<Q',data,0x8148)[0]
    def initial(address,size):
        offset=fb+address-rb
        if not rb<=address<=rb+rs-size or not 0<=offset<=len(data)-size:
            raise ValueError('initializer outside pinned payload')
        return data[offset:offset+size]
    ia=0xa029414a8+12*0x30;ga=0xa02942798+12*0x28
    item=captured_metadata(ia,0x30);group=captured_metadata(ga,0x28)
    target=initial(ia,0x30);target_group=initial(ga,0x28)
    offset,pointer,length=struct.unpack_from('<QQQ',item,8)
    if (item[:16]!=target[:16] or item[24:]!=target[24:] or group!=target_group or
            struct.unpack_from('<I',item)[0]!=12 or offset or length!=LENGTH or
            struct.unpack_from('<II',item,32)!=(2,12) or
            struct.unpack_from('<QQII',group)!=(ADDRESS,SECONDARY,SIZE,LENGTH) or
            group[0x1c:0x24]!=bytes.fromhex('0000000000000101')):
        raise ValueError('resource0c captured/static identity differs')
    physical=int(region['physical_start'],0)
    if not physical<=pointer<=physical+region['received_bytes']-length:
        raise ValueError('entire resource must be in captured extension')
    with CAPTURE.open('rb') as f:
        f.seek(pointer-physical);content=f.read(length)
    if len(content)!=length or hashlib.sha256(content).hexdigest()!=CONTENT_SHA:
        raise ValueError('captured item fingerprint differs')
    # Original helper40f85bfc reads a generation word8bytes before bank end;
    # 40f86dfc checks ENDM in the last4bytes. Neither was captured as Flash.
    padding=SIZE-LENGTH-8
    blob=content+b'\xff'*padding+struct.pack('<I',0)+b'ENDM'
    record=dict(classification='captured resource0c with diagnostic primary-bank Flash framing',
        main_sha256=MAIN_SHA,source_capture=str(CAPTURE),source_capture_sha256=CAPTURE_SHA,
        source_receipt_sha256=sha(receipt),base_capture_sha256=BASE_SHA,base_manifest_sha256=MANIFEST_SHA,
        source_version='V1.10',target_version='C1.11',item_hex=item.hex(),target_item_hex=target.hex(),
        group_hex=group.hex(),captured_pointer=hex(pointer),content_bytes=LENGTH,
        content_sha256=CONTENT_SHA,address=hex(ADDRESS),bytes=len(blob),
        sha256=hashlib.sha256(blob).hexdigest(),diagnostic_padding_bytes=padding,padding_byte=255,
        diagnostic_generation=0,diagnostic_trailer_hex=b'ENDM'.hex(),
        secondary_bank_supplied=False,original_flash_framing_recovered=False,
        cross_version_equivalence_verified=False,atomic=False,complete_flash_image=False,
        firmware_patches=[],ram_patches=[],cpu_register_redirection=False)
    return blob,record


def attach(g,variant):
    if variant!='captured-primary-with-framing':raise ValueError('explicit resource0c framing required')
    blob,record=reconstruct();record['variant']=variant
    path=g.out/'zr-resource0c-primary.bin'
    with path.open('xb') as f:f.write(blob)
    g.command+=['-device',f'loader,file={path},addr={ADDRESS:#x},force-raw=on']
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (g.out/'zr-resource0c-input.json').write_text(json.dumps(record,indent=2)+'\n')
    g.data['sequence_resource0c_input']=record
