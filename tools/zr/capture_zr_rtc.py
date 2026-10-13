# SPDX-License-Identifier: GPL-2.0-or-later
"""Read ZR's independently located RTC and release permission objects."""
from pathlib import Path
import struct
from probe_graphics_image import save


def capture(g):
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    data = dict(scope='read-only ZR runtime; release completion not inferred')
    for name, address, size in (('parsed_date', 0xa02823150, 20),
            ('capture_date_state', 0xa03e3db20, 4), ('release_permission', 0xa03e46298, 0xe0)):
        data[name] = dict(address=hex(address), raw_hex=save(g, 'zr-rtc-'+name, address, size).hex())
    maps = {}
    for name, address in (('inhibits', 0xa03e462b8), ('mask', 0xa03e462e0)):
        descriptor = save(g, 'zr-rtc-'+name+'-descriptor', address, 0x18)
        bits = struct.unpack_from('<I', descriptor)[0]
        pointer = struct.unpack_from('<Q', descriptor, 8)[0]
        size = ((bits+31)//32)*4
        if not 0 < bits <= 512 or not 0xa00000000 <= pointer <= 0xa20000000-size:
            maps[name] = dict(initialized=False, descriptor_hex=descriptor.hex())
            continue
        body = save(g, 'zr-rtc-'+name+'-body', pointer, size)
        maps[name] = dict(bits=bits, pointer=hex(pointer),
            set_bits=[n for n in range(bits) if body[n//8] & (1 << (n % 8))])
    data['bitmaps'] = maps
    if all('set_bits' in item for item in maps.values()):
        data['active_inhibits'] = sorted(set(maps['inhibits']['set_bits']) & set(maps['mask']['set_bits']))
    g.data['zr_rtc_readiness'] = data
