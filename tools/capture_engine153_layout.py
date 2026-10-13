# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only original153 setup arguments; no guest writes or CPU redirection."""
import struct
from pathlib import Path


def observe(guest, registers):
    row = dict(scope='read-only Z9 original40cbb744 entry arguments; port roles unproved')
    try:
        address = registers['X01']
        if not 0xa00000000 <= address <= 0xa40000000-0x140:
            raise ValueError('153 application configuration outside work RAM')
        raw=guest.read_bytes(address,0x140)
        row.update(configuration_address=hex(address),configuration_hex=raw.hex(),
            instance=registers['X00'],caller=hex(registers['X30']))
        for offset,name,size in [(0xf0,'parameter_packet',0x700),(0x128,'header_input',32)]:
            target=struct.unpack_from('<Q',raw,offset)[0]
            if not 0xa00000000 <= target <= 0xa40000000-size:
                row[name+'_unreadable_address']=hex(target)
                continue
            row[name+'_address']=hex(target)
            row[name+'_hex']=guest.read_bytes(target,size).hex()
        (guest.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    except Exception as exc:
        row['capture_error']=repr(exc)
    return row
