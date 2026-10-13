# SPDX-License-Identifier: GPL-2.0-or-later
"""Read and extract a NEF from a stopped guest's actual virtual card."""
import argparse
import json
from pathlib import Path
from probe import sha
from virtual_recording_card import audit
from inspect_virtual_exfat import catalog
from extract_virtual_exfat import extract


def export(output):
    output = Path(output).resolve()
    native = json.loads((output / 'result.json').read_text())
    if not native.get('owned_qemu_stopped') or native.get('error') or native.get('cpu_register_redirection') or native.get('ram_patches'):
        raise ValueError('Stopped, unmodified and fault-free native capture required')
    if not native.get('capture_sequence', {}).get('all_inputs_consumed'):
        raise ValueError('Original input sequence was not completely consumed')
    card = output / 'capture-card.raw'
    receipt = card.with_suffix('.audit.json')
    checked = json.loads(receipt.read_text()) if receipt.exists() else audit(card)
    if checked['fsck_exit'] != 0 or not checked['source_unchanged']:
        raise ValueError('Actual filesystem audit failed')
    volume = Path(checked['derived_volume'])
    listing = catalog(volume)
    files = [f for f in listing['files'] if not f['directory'] and f['path'].upper().endswith('.NEF')]
    if len(files) != 1:
        raise ValueError('Expected exactly one native NEF; card catalog: ' + repr(files))
    row = files[0]
    target = output / 'DSC_0001.NEF'
    if target.exists():
        old = json.loads(target.with_suffix('.NEF.extraction.json').read_text())
        if old['sha256'] != sha(target) or old['entry'] != row:
            raise ValueError('Preserved extraction differs; use a fresh run')
        result = old
    else:
        result = extract(volume, row['path'], target)
    (output / 'capture-card.catalog.json').write_text(json.dumps(listing, indent=2)+'\n')
    print(json.dumps({'file': row['path'], 'bytes': result['bytes'], 'sha256': result['sha256'],
                      'output': str(target), 'full_pixel_audit_required': True}))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    export(p.parse_args().output)
