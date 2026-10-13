# SPDX-License-Identifier: GPL-2.0-or-later
"""Snapshot modeled DSP load RAM without supplying code or completions."""
import hashlib
from pathlib import Path
import re


def capture(guest):
    board=guest.out/'nikon-z9-lab.c'
    source=board.read_bytes();text=source.decode()
    match=re.search(r'\}\s*dsp_load_ram\[\]\s*=\s*\{(.*?)\n\};',text,re.S)
    if not match:raise ValueError('Actual compiled DSP RAM table required')
    regions=[(int(a,16),int(n,16))for a,n in re.findall(r'\{\s*(0x[0-9a-f]+),\s*(0x[0-9a-f]+)\s*\}',match.group(1))]
    if len(regions)!=8 or any(not 0<n<=1024*1024 for _,n in regions):
        raise ValueError('Bounded eight-region modeled processor input required')
    rows=[]
    for address,size in regions:
        target=guest.out/(f'processor-ram-{address:x}-private.bin')
        if target.exists():raise ValueError('Preserve prior processor input capture')
        reply=guest.qmp.hmp(f'pmemsave {address:#x} {size:#x} "{target}"')
        if reply or target.stat().st_size!=size:raise ValueError('Processor RAM capture failed')
        data=target.read_bytes()
        rows.append(dict(address=address,bytes=size,file=target.name,
            sha256=hashlib.sha256(data).hexdigest(),nonzero_bytes=sum(v!=0 for v in data),
            private_vendor_input=True))
    script=Path(__file__);archived=guest.out/script.name
    if archived.exists()and archived.read_bytes()!=script.read_bytes():raise ValueError('Processor observer revision changed')
    if not archived.exists():archived.write_bytes(script.read_bytes())
    guest.data['processor_ram_inputs']=dict(board_sha256=hashlib.sha256(source).hexdigest(),
        observer_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),regions=rows,
        original_processor_execution_verified=False,
        scope='Read-only modeled load RAM at owned native stop; nonzero data alone does not prove original ELF provenance or physical layout')
