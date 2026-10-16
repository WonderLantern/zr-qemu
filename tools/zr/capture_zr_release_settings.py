# SPDX-License-Identifier: GPL-2.0-or-later
"""Read original scalar fields while the harness already has its guest stopped."""
import json
from pathlib import Path
from probe import sha
from zr_data_registry import Registry
from zr_key_sequence import MAX_KEYS


def capture(guest, stage):
    record = guest.data.get('release_settings_observation')
    if record is None:
        from probe_zr_boot import MAIN, MAIN_SHA
        if guest.data['main_sha256'] != MAIN_SHA:
            raise ValueError('This native observation is bound to ZR1.11')
        registry = Registry(MAIN.read_bytes(), MAIN_SHA)
        fields = [f for f in registry.release_settings() if f.get('scalar_width')
                  and not any(n in f['name'] for n in ('Func', 'Sync', 'AfActivation'))]
        # Original registry resolves these independently for this image. Keep
        # settings and effective-mode observations distinct; do not assign an
        # enum meaning or convert shutter units from the field name alone.
        for ident in (0x205, 0x20d, 0x2423, 0x280c):
            field = registry.lookup(ident)
            if not field.get('scalar_width'):
                raise ValueError('Expected original scalar exposure observation')
            fields.append(field)
        record = dict(firmware_sha256=MAIN_SHA, fields=fields, snapshots=[], sources={},
            scope='Stopped original scalar RAM observations; no settings writes, enum interpretation or burst acceptance')
        for name in (Path(__file__).name, 'zr_data_registry.py', 'firmware_diagnostic_names.py', 'zr_key_sequence.py'):
            source = Path(__file__).with_name(name)
            (guest.out/name).write_bytes(source.read_bytes()); record['sources'][name] = sha(source)
        guest.data['release_settings_observation'] = record
    if len(record['snapshots']) >= 2 * MAX_KEYS: raise ValueError('Bounded release observation exhausted')
    values = []
    for field in record['fields']:
        raw = guest.read_bytes(int(field['data_address'],16), field['scalar_width'])
        values.append(dict(id=field['normalized_id'], raw_hex=raw.hex(),
                           value=int.from_bytes(raw,'little',signed=field['signed'])))
    record['snapshots'].append(dict(after_input_stage=stage, values=values))
    target=guest.out/'release-settings-progress.json'; temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(record,indent=2)+'\n');temporary.replace(target)
