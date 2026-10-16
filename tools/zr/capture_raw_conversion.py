# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded, stopped-guest snapshots of the last actual RAW RAM conversion."""
import hashlib
import json


def capture(guest):
    conversions = guest.data.get('engine1540_conversion_final', {}).get('banks', [])
    selected = [i for i, row in enumerate(conversions) if row.get('jobs') and row.get('last_conversion')]
    if not selected:
        return
    actual = json.loads(guest.qmp.command('qom-get', path='/machine', property='engine1540-alternate-bank-state'))
    for bank in selected:
        row = actual['banks'][bank]
        size = row['last_result_bytes']
        if not 0 < size <= 128*1024*1024 or row['frame'] != 0:
            raise ValueError('Bounded completed identity conversion required')
        record = dict(bank=bank, bytes=size, device=row, files={}, sha256={},
            scope='terminal stopped RAM contents; actual identity conversion, not a new exposure or saved RAW file')
        old_timeout = guest.qmp.sock.gettimeout()
        guest.qmp.sock.settimeout(30)
        try:
            for key in ('source','target'):
                address = row[key]
                if not 0x840000000 <= address <= 0x900000000-size:
                    raise ValueError('Conversion span outside image RAM')
                path = guest.out/f'raw-conversion-bank{bank}-{key}.bin'
                reply = guest.qmp.hmp(f'pmemsave {address:#x} {size:#x} "{path}"')
                if reply or path.stat().st_size != size:
                    raise RuntimeError('Incomplete actual conversion RAM snapshot: '+str(reply))
                record['files'][key] = path.name
                with path.open('rb') as stream:
                    record['sha256'][key] = hashlib.file_digest(stream,'sha256').hexdigest()
        finally:
            guest.qmp.sock.settimeout(old_timeout)
        record['terminal_contents_equal'] = record['sha256']['source']==record['sha256']['target']
        guest.data.setdefault('raw_conversion_terminal_dumps',[]).append(record)
