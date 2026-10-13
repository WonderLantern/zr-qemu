# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit diagnostic group-12 ROM input for the pinned Z9 5.32 payload.

The body is the firmware's built-in default, not a hardware calibration dump.
Its final four bytes are replaced with the original reader/writer's ENDM tag.
Only QEMU's separate ROM loader receives it; original firmware is never edited.
"""
import hashlib
import json
from pathlib import Path

from probe import MAIN_SHA, sha


SOURCE = 0x44ab18c0
ADDRESS, SIZE = 0x462e0000, 0x20000
BODY_SHA = '243d47c7e4c6f19a6283811d7f2d70bd0b27c84113195663c924f624575c6e31'
TAG_FILE_OFFSET = 0x4c1a6b0


def attach(g, variant):
    MAIN = g.firmware
    if variant not in ('defaults', 'bad-end-marker'):
        raise ValueError('unsupported parameter input variant')
    if sha(MAIN) != MAIN_SHA:
        raise ValueError('wrong original firmware')
    with MAIN.open('rb') as source:
        source.seek(SOURCE-0x40160000); original = source.read(SIZE)
        source.seek(TAG_FILE_OFFSET); tag = source.read(4)
    if hashlib.sha256(original).hexdigest() != BODY_SHA or tag != b'ENDM':
        raise ValueError('default body/marker fingerprint mismatch')
    fixture = bytearray(original)
    fixture[-4:] = tag
    if variant == 'bad-end-marker':
        fixture[-1] ^= 1
    path = g.out/'parameter-group12-rom.bin'
    with path.open('xb') as stream:
        stream.write(fixture)
    record = dict(kind='diagnostic ROM input from built-in default data', variant=variant,
        source_sha256=sha(Path(__file__)), firmware_sha256=MAIN_SHA,
        source_address=hex(SOURCE), source_bytes=SIZE, source_body_sha256=BODY_SHA,
        address=hex(ADDRESS), bytes=SIZE, file=path.name, sha256=sha(path),
        original_tail_hex=original[-8:].hex(), input_tail_hex=fixture[-8:].hex(),
        edits=[dict(offset=SIZE-4, bytes=4, meaning='original ENDM format, deliberately corrupted in negative control')],
        hardware_calibration=False, guest_ram_patch=False, callback_or_cpu_patch=False)
    (g.out/'parameter-input-source.py').write_bytes(Path(__file__).read_bytes())
    (g.out/'parameter-input.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    g.command += ['-device', f'loader,file={path},addr={ADDRESS:#x},force-raw=on']
    g.data['parameter_rom_input'] = record
    return bytes(fixture)
