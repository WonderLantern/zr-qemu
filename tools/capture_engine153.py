# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded, read-only descriptor/buffer snapshots after original153 setup.

QOM configuration records are independent of optional RAM snapshots. RAM
read failures are retained without replacing a strict device failure.
"""
import json
import struct
from pathlib import Path


DRIVERS = {'z9': (0xa0280d7f0, 0xa0280d810), 'zr': (0xa0280d890, 0xa0280d8b0)}


def observe(guest, *, model):
    row = dict(scope='read-only original1538 ISR/callback checkpoint')
    row['frame_pass'] = json.loads(guest.qmp.command('qom-get',path='/machine',property='engine153-frame-pass-state'))
    try:
        raw = guest.read_bytes(DRIVERS[model][1],32)
        row['driver_hex'] = raw.hex()
        argument = struct.unpack_from('<Q',raw,24)[0]
        if not 0xa00000000 <= argument <= 0xa40000000-32:
            raise ValueError('1538 original argument is outside bounded work RAM')
        row['argument_hex'] = guest.read_bytes(argument,32).hex()
    except Exception as exc: row['capture_error'] = repr(exc)
    return row


def capture(guest, *, model):
    report = dict(scope='read-only original driver/descriptor snapshots at final stop', banks=[])
    guest.data['engine153_native_observation'] = report
    (guest.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    state = guest.data['engine153_config_final']
    if guest.data.get('engine153_frame_pass_final'):
        report['frame_pass'] = guest.data['engine153_frame_pass_final']
        for bank in report['frame_pass']['banks']:
            if not bank['jobs']: continue
            try:
                for key in ('source', 'target'):
                    address = bank[key]
                    if not 0x800000000 <= address <= 0x900000000-256:
                        raise ValueError('153 frame prefix outside physical image RAM')
                    if model=='zr':
                        # ZR's override deliberately accepts only virtual A...
                        # work RAM. Use its base transport for this separately
                        # bounded physical image-RAM observation.
                        from contract_guest import ContractGuest
                        raw = ContractGuest.read_bytes(guest,address,256)
                    else:
                        # Public Z9's probe module has a different API; do not
                        # import the private ContractGuest into its namespace.
                        raw = guest.read_bytes(address,256)
                    bank[key+'_head_hex'] = raw.hex()
                bank['prefix_equal'] = bank['source_head_hex']==bank['target_head_hex']
            except Exception as exc: bank['prefix_capture_error'] = repr(exc)
    for bank, driver in enumerate(DRIVERS[model]):
        item = dict(bank=bank, driver_address=hex(driver), configuration=state['banks'][bank])
        report['banks'].append(item)
        if not state['banks'][bank]['writes']: continue
        try:
            raw = guest.read_bytes(driver, 32)
            ident, port, descriptor, argument = struct.unpack('<QQQQ', raw)
            item.update(driver_hex=raw.hex(), descriptor_id=ident, port=hex(port),
                descriptor_address=hex(descriptor), argument_address=hex(argument))
            if not 0xa00000000 <= descriptor <= 0xa40000000-0x7c0:
                raise ValueError('descriptor is outside bounded original work RAM')
            item['descriptor_hex'] = guest.read_bytes(descriptor, 0x7c0).hex()
            if argument:
                if not 0xa00000000 <= argument <= 0xa40000000-32:
                    raise ValueError('ISR argument is outside bounded original work RAM')
                item['argument_hex'] = guest.read_bytes(argument, 32).hex()
            item['address_words'] = [state['banks'][bank]['fields'][(0xb0+0x14*i)//4:(0xb0+0x14*i)//4+5] for i in range(6)]
        except Exception as exc:
            item['capture_error'] = repr(exc)
    (guest.out/'engine153-native-observation.json').write_text(json.dumps(report, indent=2)+'\n')
