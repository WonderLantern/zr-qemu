# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only scalar registry from each pinned ZR original getter.

Shares name discovery and table semantics with Z9 research, not its addresses.
Presence of a field does not establish a legal value or a supported UI feature.
"""
import hashlib
import struct
from firmware_diagnostic_names import discover

ROM_BASE = 0x40160000
PROFILES = {
    '9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f':
        ('1.11', 0x41205a4c, '5fd0487d9f82907c21a19dabb2776f37210a4a9b83a765829c9c79760d0bf627'),
    'd495cce73462a51b971ad25941a2deea92ccc667f127b930da00949101a51b82':
        ('1.10', 0x41205a64, '268dd0f58f61cb6b9cf6d43f84c1907913c31615c60077b1f16fdb6efecf291c'),
}
WIDTHS = {0:1, 1:1, 2:2, 3:4, 5:1, 6:2, 7:4, 9:4}


class Registry:
    def __init__(self, blob, expected_sha256):
        self.blob = blob
        if hashlib.sha256(blob).hexdigest() != expected_sha256:
            raise ValueError('Exact original MAIN fingerprint required')
        self.version, self.getter, expected_getter = PROFILES[expected_sha256]
        code = self.read_rom(self.getter, 0xdc)
        if hashlib.sha256(code).hexdigest() != expected_getter:
            raise ValueError('Original getter contract differs')

        def address(offsets, register):
            result = 0
            for shift, offset in enumerate(offsets):
                word = struct.unpack_from('<I', code, offset)[0]
                opcode = 0xd2800000 if shift == 0 else 0xf2800000
                if word & 0xff80001f != opcode | register or (word >> 21) & 3 != shift:
                    raise ValueError('Expected original wide-address construction')
                result |= ((word >> 5) & 0xffff) << (shift * 16)
            return result

        self.groups = address((0x1c, 0x20, 0x28, 0x2c), 10)
        self.descriptors = address((0x5c, 0x60, 0x68, 0x70), 11)
        self.methods = address((0x88, 0x90, 0x94, 0x98), 10)
        # Exact reader order established by original indirect dispatch and
        # verified by bounded execution, including signed byte/halfword cases.
        readers = tuple(self.getter + off for off in
                        (0xb4,0xb4,0xbc,0xa4,0xd8,0xc4,0xcc,0xa4,0xd8,0xa4))
        seed = struct.pack('<10Q', *readers)
        self.methods_file = blob.find(seed)
        if self.methods_file < 0 or blob.find(seed, self.methods_file+1) >= 0:
            raise ValueError('Unique original reader table required')
        discovered = discover(blob, expected_sha256)
        self.names = {int(row['normalized_id'],16): row for row in discovered['rows']}

    def read_rom(self, address, length):
        offset = address - ROM_BASE
        if offset < 0 or length < 0 or offset+length > len(self.blob):
            raise ValueError('Registry read outside original MAIN')
        return self.blob[offset:offset+length]

    def lookup(self, ident):
        group, slot = (ident >> 8) & 255, ident & 255
        row = dict(id=hex(ident), normalized_id=hex(ident & 0xffff), valid=False)
        row.update(self.names.get(ident & 0xffff, {}))
        if group > 0x7a: return row
        raw = self.read_rom(self.groups + group*0x30, 0x30)
        valid = struct.unpack_from('<I', raw)[0]
        first, count = struct.unpack_from('<HH', raw, 0x18)
        if not valid or slot >= count: return row
        descriptor = self.descriptors + (first+slot)*0x18
        kind, length, pointer, default = struct.unpack('<IIQQ', self.read_rom(descriptor, 24))
        row.update(valid=True, descriptor_address=hex(descriptor), storage_type=kind,
                   declared_length=length, data_address=hex(pointer), default_address=hex(default))
        width = WIDTHS.get(kind)
        if width and length == width and 0xa00000000 <= pointer <= 0xa20000000-width:
            row.update(scalar_width=width, signed=kind in (5,6))
            if ROM_BASE <= default <= ROM_BASE+len(self.blob)-width:
                row['default_hex'] = self.read_rom(default, width).hex()
        return row

    def release_settings(self):
        return [self.lookup(int(v['listed_id'],16)) for v in self.names.values()
                if any(name in v['name'] for name in
                       ('Release', 'ShootingMode', 'PhotoMode', 'DriveMode'))]
