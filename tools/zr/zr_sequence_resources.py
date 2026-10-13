# SPDX-License-Identifier: GPL-2.0-or-later
"""Read the pinned ZR C1.11 sequence bitmaps, without changing ownership.

411c52f4 initializes four 136-bit objects and their fixed backing arrays.
411c616c copies E0, removes an allowed list, and tests intersection with B8.
This describes an original software predicate, not physical resource wiring.
"""
import hashlib
import struct
from pathlib import Path

BASE = 0xa03e462a4
SIZE = 160
OBJECTS = {
    'b8': (0xa03e462b8, 0xa03e462a4),
    'e0': (0xa03e462e0, 0xa03e462c8),
    'group308': (0xa03e46308, 0xa03e462f0),
    'group330': (0xa03e46330, 0xa03e46318),
}
VIDEO_ALLOWED = (77, 78, 79, 48, 49, 50, 53, 4, 11, 20, 21, 23, 26, 103)


def decode(raw):
    if len(raw) != SIZE:
        raise ValueError('Complete bounded original sequence resource snapshot required')
    result = dict(initialized=False, objects={}, scope='Native software bitmaps; ownership labels and physical resources unverified')
    for name, (address, backing) in OBJECTS.items():
        bits = struct.unpack_from('<I', raw, address-BASE)[0]
        pointer = struct.unpack_from('<Q', raw, address-BASE+8)[0]
        row = dict(address=hex(address), declared_bits=bits, backing=hex(pointer))
        result['objects'][name] = row
        if (bits, pointer) != (136, backing):
            result['uninitialized_or_changed_object'] = name
            return result
        words = struct.unpack_from('<5I', raw, backing-BASE)
        if words[-1] & ~0xff:
            raise ValueError('Set padding bits outside original 136-bit declaration')
        row.update(words=list(words), set_ids=[i for i in range(136) if words[i//32] & (1 << (i%32))])
    result['initialized'] = True
    b8 = set(result['objects']['b8']['set_ids'])
    e0 = set(result['objects']['e0']['set_ids'])
    group = set(result['objects']['group330']['set_ids'])
    result.update(video_allowed_ids=list(VIDEO_ALLOWED),
                  video_disallowed_intersection=sorted(b8 & (e0-set(VIDEO_ALLOWED))),
                  current_group_intersection=sorted(b8 & group))
    return result


def capture(guest, label):
    source = Path(__file__)
    (guest.out/source.name).write_bytes(source.read_bytes())
    raw = guest.read_bytes(BASE, SIZE)
    output = guest.out/(label+'-sequence-resources.bin')
    output.write_bytes(raw)
    result = decode(raw)
    result.update(file=output.name, sha256=hashlib.sha256(raw).hexdigest(),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  constructor='0x411c52f4', predicate='0x411c616c',
                  stopped_guest_snapshot=True, guest_writes=False)
    guest.data[label+'-sequence-resources'] = result
    return result
