# SPDX-License-Identifier: GPL-2.0-or-later
"""Two-byte synthetic ROM version for a Z9 initialization causal experiment.

This is NOT a recovered parameter table or valid camera calibration. Only the
version read by 41179dcc is supplied; all other missing ROM bytes remain absent.
The main firmware, guest instructions and readiness/error state are untouched.
"""
import json
from pathlib import Path

from probe import MAIN_SHA, sha

ADDRESS = 0x47f62dd4
VALUES = {'v240': bytes.fromhex('2400'), 'v210': bytes.fromhex('2100')}


def attach(g, variant):
    MAIN = g.firmware
    if variant not in VALUES or sha(MAIN) != MAIN_SHA:
        raise ValueError('invalid input variant or wrong firmware')
    data = VALUES[variant]
    path = g.out/'synthetic-init-table-version.bin'
    with path.open('xb') as stream:
        stream.write(data)
    record = dict(classification='synthetic two-byte ROM input for causal testing',
        variant=variant, address=hex(ADDRESS), bytes=len(data), hex=data.hex(),
        file=path.name, sha256=sha(path), firmware_sha256=MAIN_SHA,
        source_sha256=sha(Path(__file__)), table_recovered=False,
        hardware_calibration=False, guest_ram_patch=False, callback_or_cpu_patch=False,
        limits='Only two version bytes; no table body, pixels, or camera acceptance supplied')
    (g.out/'init-table-input-source.py').write_bytes(Path(__file__).read_bytes())
    (g.out/'init-table-input.json').write_text(json.dumps(record, indent=2)+'\n')
    g.data['init_table_version_input'] = record
    g.command += ['-device', f'loader,file={path},addr={ADDRESS:#x},force-raw=on']
    return data
