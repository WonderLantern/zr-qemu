# SPDX-License-Identifier: GPL-2.0-or-later
"""Discover a bounded original name/ID diagnostic table without fixed model offsets.

Read-only metadata discovery. Names do not establish storage addresses, types,
legal setting values, firmware support, or permission to modify guest state.
"""
import hashlib
import struct


def discover(blob, expected_sha256, rom_base=0x40160000,
             anchor='eDSID_Setting_ReleaseSpeedContHigh', maximum_names=8192):
    if hashlib.sha256(blob).hexdigest()!=expected_sha256:
        raise ValueError('Exact input fingerprint required')
    needle=anchor.encode('ascii')+b'\0'
    start=blob.find(needle)
    if start<0 or blob.find(needle,start+1)>=0:
        raise ValueError('Exactly one complete diagnostic anchor required')
    pointer=struct.pack('<Q',rom_base+start)

    def name_at(offset):
        if offset<0 or offset+8>len(blob):return None
        value=struct.unpack_from('<Q',blob,offset)[0]-rom_base
        if not 0<=value<len(blob) or blob[value:value+6]!=b'eDSID_':return None
        end=blob.find(b'\0',value,min(value+192,len(blob)))
        if end<0:return None
        name=blob[value:end]
        if not all(x==95 or 48<=x<=57 or 65<=x<=90 or 97<=x<=122 for x in name):return None
        return name.decode('ascii')

    candidates={};offset=0
    while True:
        offset=blob.find(pointer,offset)
        if offset<0:break
        match=offset;offset+=1
        if match%8:continue
        lo=hi=match
        while (match-lo)//8<maximum_names and name_at(lo-8):lo-=8
        while (hi-match)//8<maximum_names and name_at(hi+8):hi+=8
        count=(hi-lo)//8+1
        if not 16<=count<=maximum_names:continue
        ids=hi+8
        if ids+count*4>len(blob):continue
        rows=[];seen=set()
        for i in range(count):
            ident=struct.unpack_from('<I',blob,ids+4*i)[0]
            if ident&0xffff in seen:break
            seen.add(ident&0xffff)
            rows.append(dict(index=i,name=name_at(lo+8*i),listed_id=hex(ident),
                normalized_id=hex(ident&0xffff)))
        if len(rows)==count:candidates[lo]=(ids,rows)
    if len(candidates)!=1:
        raise ValueError('Unique bounded parallel diagnostic lists not established')
    names,(ids,rows)=next(iter(candidates.items()))
    return dict(firmware_sha256=expected_sha256,rom_base=hex(rom_base),
        names_file_offset=names,ids_file_offset=ids,count=len(rows),rows=rows,
        scope='Read-only name/parallel-ID candidates; original caller and runtime getter validation separate')
