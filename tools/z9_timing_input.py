# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit virtual sensor timing input for the missing Z9 item 0x5f ROM.

This supplies two synthetic line-duration coefficients, not Nikon calibration.
The native timing calculator and all runtime waits remain unchanged. Only the
observed mode selectors 0/13 and subselector 3 are supplied in this experiment.
"""
import json
from pathlib import Path
import struct

from probe import MAIN_SHA, sha

TABLE = 0x47e80000


def attach(g, line_ticks):
    if line_ticks != 1200 or sha(g.firmware) != MAIN_SHA:
        raise ValueError('Only the pinned line1200 functional input is defined')
    record = dict(classification='synthetic_missing_ROM_timing_input',
                  line_ticks=line_ticks, selectors=[0, 13], subselector=3,
                  firmware_sha256=MAIN_SHA, source_sha256=sha(Path(__file__)),
                  table_recovered=False, physical_timing_verified=False,
                  guest_ram_patch=False, callback_or_cpu_patch=False,
                  rationale='Nonzero line coefficient for the native duration calculation; '
                            '1200/72 = 16.667 microseconds in the native arithmetic, '
                            'chosen virtual input, not measured sensor timing',
                  inputs=[])
    for selector in record['selectors']:
        address = TABLE + 0xe2ed2 + selector * 0xc0 + 3 * 0x30
        path = g.out / f'synthetic-timing-line-{selector}.bin'
        with path.open('xb') as f:
            f.write(struct.pack('<H', line_ticks))
        record['inputs'].append(dict(address=hex(address), file=path.name,
                                     bytes=2, sha256=sha(path)))
        g.command += ['-device', f'loader,file={path},addr={address:#x},force-raw=on']
    (g.out / 'timing-input-source.py').write_bytes(Path(__file__).read_bytes())
    (g.out / 'timing-input.json').write_text(json.dumps(record, indent=2) + '\n')
    g.data['synthetic_timing_input'] = record
