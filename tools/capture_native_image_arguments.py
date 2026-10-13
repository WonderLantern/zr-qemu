# SPDX-License-Identifier: GPL-2.0-or-later
"""Read bounded original image objects at RAW descriptor/NEF tag boundaries."""
from pathlib import Path
import struct
from capture_virtual_ram import read_virtual_ram


def observe(g, registers, *, cpu, label):
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    objects = {}

    def add(address, size):
        if not 0x800000000 <= address <= 0x1000000000-size:
            return None
        key = hex(address)
        if key in objects:
            return bytes.fromhex(objects[key]['hex']) if 'hex' in objects[key] else None
        try:
            raw = read_virtual_ram(g,address,size,cpu=cpu,allow_image_ram=True)
        except ValueError as error:
            objects[key] = dict(bytes=size, unreadable_virtual=str(error))
            return None
        objects[key] = dict(bytes=size, hex=raw.hex())
        return raw

    # Original object candidates may live in the uncached virtual pool or in
    # image RAM. Translate on the stopped issuing CPU, checking every page;
    # never subtract a guessed alias offset or read executable/MMIO/FIFO data.
    if label.endswith(('result_forward','raw_length_store')):
        names = ('X00','X01','X02','X03','X08','X09','X10','X13','X19','X20','X21','X22','X23','X24','X25')
    else:
        names = ('X00','X01','X02','X03','X19','X20') if label.endswith('raw_descriptor_done') else ('X00','X01','X02','X03')
    for name in names:
        raw = add(registers[name], 0xa0)
        if raw is not None:
            for offset in range(0, 0x40, 8):
                child = add(struct.unpack_from('<Q', raw, offset)[0], 0x80)
                if child is not None:
                    for at in (0, 0x10, 0x28, 0x30, 0x38):
                        add(struct.unpack_from('<Q', child, at)[0], 0x80)
    if label.endswith('raw_descriptor'):
        # The original descriptor routine reads these two geometry/mode
        # branches from its actual first argument. No mode value is supplied.
        for offset, size in ((0x2a0,0x20),(0x2860,0x38)):
            add(registers['X00']+offset,size)
    if label.endswith('result_forward'):
        add(registers['X22']+0xd0,0x20)
    if label.endswith('raw_length_store'):
        add(registers['X25']+0xd8,0x18)
    return dict(objects=objects,
                scope='read-only MMU-translated bounded original RAW/NEF object candidates; roles not inferred from pointers; no packet, count, flags or image bytes supplied')
