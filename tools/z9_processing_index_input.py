# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded virtual initialization-table input for the observed lookups.

The table body is absent. This opt-in chooses record one for the exact
selectors captured at 4117635c, without supplying their missing coefficients.
It is a diagnostic input, not recovered factory calibration.
"""
import json
from pathlib import Path
from probe import MAIN_SHA, sha

ADDRESS = 0x47f5af41
VALUES = {'first':(ADDRESS,b'\x01'), 'first-two':(ADDRESS-1,b'\x01\x01')}


def attach(g, variant):
    MAIN = g.firmware
    if variant not in VALUES or sha(MAIN) != MAIN_SHA:
        raise ValueError('invalid processing index input or wrong MAIN')
    address,raw = VALUES[variant]
    path = g.out/'synthetic-processing-index.bin'
    with path.open('xb') as f:
        f.write(raw)
    record = dict(classification='diagnostic bounded virtual ROM selectors',
        variant=variant, address=hex(address), bytes=len(raw), hex=raw.hex(),
        file=path.name, sha256=sha(path), source_sha256=sha(Path(__file__)),
        firmware_sha256=MAIN_SHA, table_recovered=False, hardware_calibration=False,
        guest_ram_patch=False, callback_or_cpu_patch=False,
        mapping='4117635c: table47e80000 + selector + daf40 -> record daf60 + (index-1)*20',
        selectors=[1] if variant=='first' else [0,1],
        limits='Observed selectors only; record body stays missing; no coefficients, pixels, events or readiness supplied')
    (g.out/'processing-index-input-source.py').write_bytes(Path(__file__).read_bytes())
    (g.out/'processing-index-input.json').write_text(json.dumps(record,indent=2)+'\n')
    g.command += ['-device',f'loader,file={path},addr={address:#x},force-raw=on']
    g.data['processing_index_rom_input'] = record
    return raw
