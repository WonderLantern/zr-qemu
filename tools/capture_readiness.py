# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only capture of Z9 C5.32 readiness objects, not inferred hardware state."""
import struct
import hashlib
from pathlib import Path

from probe_graphics_image import save


def capture(g, prefix='readiness-'):
    (g.out/'capture_readiness.py').write_bytes(Path(__file__).read_bytes())
    regions = [
        ('lens-ready', 0xa03da67d8, 0xa8),
        ('shoot-notify-callback', 0xa0324ac18, 8),
        ('shoot-state', 0xa02833a80, 0x40),
        ('shoot-runtime', 0xa032f0a20, 0x40),
        ('app-ready-latch', 0xa03243d18, 8),
        ('capture-hold-mask', 0xa03da6c0c, 4),
        ('battery-start-result', 0xa03d645d0, 16),
        ('shoot-mode', 0xa028320a0, 16),
        ('capture-controller', 0xa03d9da00, 0xd00),
        ('capture-ready-lower', 0xa03d77e00, 0x60),
        ('capture-input-control', 0xa03da6a70, 0x110),
        ('capture-release-permission', 0xa03da68d0, 0x1a0),
        ('rtc-parsed-date', 0xa02822650, 20),
        ('rtc-runtime', 0xa02f492c8, 0xb0),
        ('native-diagnostic-state', 0xa02f48000, 0x220),
        ('key-status-latch', 0xa03222000, 0x34),
        ('key-boot-latch', 0xa03240190, 8),
        ('orientation-driver', 0xa02e756b8, 0x330),
    ]
    data = {}
    for label, address, size in regions:
        blob = save(g, prefix + label, address, size)
        data[label] = dict(address=hex(address), raw_hex=blob.hex())
    bitmaps = []
    for index, address in enumerate((0xa03da67f0, 0xa03da6808, 0xa03da6820,
                                     0xa03da6838, 0xa03da6850)):
        descriptor = save(g, prefix + f'bitmap-{index}-descriptor', address, 0x18)
        bits = struct.unpack_from('<I', descriptor)[0]
        pointer = struct.unpack_from('<Q', descriptor, 8)[0]
        item = dict(address=hex(address), bits=bits, pointer=hex(pointer))
        if not 0 < bits <= 1024 or not 0xa00000000 <= pointer < 0xa20000000:
            item['not_read'] = 'uninitialized or unexpected bitmap bounds'
        else:
            body = save(g, prefix + f'bitmap-{index}-data', pointer, ((bits + 31) // 32) * 4)
            item['raw_hex'] = body.hex()
            item['set_bits'] = [n for n in range(bits) if body[n // 8] & (1 << (n % 8))]
        bitmaps.append(item)
    data['bitmaps'] = bitmaps
    # Original capture-input initializer40fd917c registers logical GPIO IDs
    # 23/24/27/28 through40c00370 and40c001f4. Resolve the actual board table;
    # do not borrow the MCU transport pins or assume an IRQ number.
    table = int.from_bytes(save(g,prefix+'gpio-logical-table-pointer',0xa02b16fe8,8),'little')
    # The pinned board getter4118ad1c returns this file-backed ROM table.
    # Keep the RAM-only save helper strict; read ROM metadata from the pinned
    # file after checking the runtime pointer matches the original getter.
    if table != 0x43de711c:
        raise ValueError('original logical GPIO table differs from pinned board getter')
    firmware = g.firmware
    with firmware.open('rb') as stream:
        fingerprint = hashlib.file_digest(stream, 'sha256').hexdigest()
    if fingerprint != '6380ded18395ce11cb327c766721274c85127d2cf1a1e887ee60e3d156810bdd':
        raise ValueError('pinned Z9 firmware changed')
    with firmware.open('rb') as stream:
        stream.seek(table-0x40160000)
        logical_table=stream.read(0x2c*4)
    if len(logical_table)!=0x2c*4:raise ValueError('short pinned logical GPIO table')
    bindings = []
    for logical in (0x23,0x24,0x27,0x28,0x26,0x2b):
        index = struct.unpack_from('<I',logical_table,logical*4)[0]
        if index >= 512:raise ValueError('original GPIO object index exceeds observed table bound')
        pointer = int.from_bytes(save(g,prefix+f'gpio-{logical:02x}-pointer',0xa02b16000+index*8,8),'little')
        if not 0xa00000000 <= pointer <= 0xa20000000-0x30:
            raise ValueError('original GPIO descriptor outside work RAM')
        descriptor = save(g,prefix+f'gpio-{logical:02x}-descriptor',pointer,0x30)
        bank,bit = struct.unpack_from('<II',descriptor,4)
        if bank >= 32 or bit >= 32:raise ValueError('original GPIO bank/bit outside bounded input map')
        register = int.from_bytes(save(g,prefix+f'gpio-{logical:02x}-input-register',0xa02cb0d60+bank*8,8),'little')
        irq = struct.unpack_from('<Q',descriptor,0x20)[0]
        item = dict(logical_id=hex(logical),index=index,descriptor=hex(pointer),
            descriptor_hex=descriptor.hex(),bank=bank,bit=bit,input_register=hex(register),
            read_enabled=bool(descriptor[0xc]),irq_descriptor=hex(irq))
        if irq:
            if not 0xa00000000 <= irq <= 0xa20000000-0x40:
                raise ValueError('original GPIO IRQ descriptor outside work RAM')
            item['irq_descriptor_hex'] = save(g,prefix+f'gpio-{logical:02x}-irq',irq,0x40).hex()
        bindings.append(item)
    data['capture_gpio_bindings'] = bindings
    g.data[prefix.rstrip('-')] = data
    return data
