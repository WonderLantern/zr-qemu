# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit two-halfword virtual ROM input for the observed primary gate.

Checkpoint138 proves the original ROM -> builder -> configuration mapping.
These variants are diagnostic inputs, not recovered Nikon calibration.
"""
import json
from pathlib import Path
import struct
from probe import MAIN_SHA, sha

ADDRESS = 0x47e8b568
VALUES = {'zero': (0, 0), 'first': (1, 0), 'second': (0, 1), 'both': (1, 1)}


def attach(g, variant):
    MAIN = g.firmware
    if variant not in VALUES or sha(MAIN) != MAIN_SHA:
        raise ValueError('invalid primary gate input or wrong MAIN')
    values = VALUES[variant]
    data = struct.pack('<2H', *values)
    path = g.out/'synthetic-primary-gate.bin'
    with path.open('xb') as stream:
        stream.write(data)
    record = dict(classification='diagnostic virtual ROM primary configuration', variant=variant,
                  address=hex(ADDRESS), bytes=len(data), halfwords=list(values), hex=data.hex(),
                  file=path.name, sha256=sha(path), firmware_sha256=MAIN_SHA,
                  source_sha256=sha(Path(__file__)), table_recovered=False, hardware_calibration=False,
                  guest_ram_patch=False, callback_or_cpu_patch=False,
                  mapping='41172700 row47e8b560 +8/+a -> a04c23338 -> 40c1dc9c -> 150c8010/14',
                  limits='Four ROM bytes only; no pixels, buffers, OS flags or camera acceptance supplied')
    (g.out/'primary-gate-input-source.py').write_bytes(Path(__file__).read_bytes())
    (g.out/'primary-gate-input.json').write_text(json.dumps(record, indent=2)+'\n')
    g.data['primary_gate_rom_input'] = record
    g.command += ['-device', f'loader,file={path},addr={ADDRESS:#x},force-raw=on']
    return data
