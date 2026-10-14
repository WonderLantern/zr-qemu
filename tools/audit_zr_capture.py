# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit a stopped ZR photo workflow, its actual card and every RAW sample."""
import argparse
import json
from pathlib import Path
import sys

from virtual_recording_card import audit as audit_card
from inspect_virtual_exfat import catalog
from audit_repeated_capture import audit as audit_photos, sha


def audit(output):
    output = Path(output).resolve()
    result = output / 'result.json'
    native = json.loads(result.read_text())
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'zr'))
    from native_workflow_status import native_fault_observations
    from probe_zr_boot import MAIN_SHA
    if (native.get('main_sha256') != MAIN_SHA or native.get('error')
            or not native.get('owned_qemu_stopped')
            or native.get('cpu_register_redirection')
            or native.get('firmware_patches')
            or native.get('original_input_unchanged') is not True
            or native.get('raw_input_unchanged') is not True
            or not native.get('mode_key_waveform', {}).get('all_consumed')
            or native_fault_observations(native)):
        raise ValueError('Stopped, fault-free original ZR workflow and consumed controls required')
    # The explicit English cache preference is distinct from code, task,
    # readiness, OS result or arbitrary RAM modifications.
    patches = native.get('ram_patches', [])
    if any(row.get('kind') != 'ui_language_preference'
           or row.get('address') != '0xa03fd1768' or row.get('bytes') != 4
           or row.get('after_hex') != '04000000' for row in patches):
        raise ValueError('Unexpected guest RAM modification in ZR capture')
    declared = native.get('private_virtual_card', {})
    card_name = declared.get('path')
    if not card_name:
        raise ValueError('Original explicitly attached virtual card required')
    card = Path(card_name).resolve()
    checked = audit_card(card)
    if checked['fsck_exit'] or not checked['source_unchanged']:
        raise ValueError('Read-only card filesystem audit failed')
    listing = catalog(Path(checked['derived_volume']))
    for name, value in (('capture-card.audit.json', checked),
                        ('capture-card.catalog.json', listing)):
        path = output / name
        if path.exists():
            if json.loads(path.read_text()) != value:
                raise ValueError('Preserved card metadata differs: ' + name)
        else:
            with path.open('x') as stream:
                json.dump(value, stream, indent=2)
                stream.write('\n')
    accepted = audit_photos(output)
    if not accepted['same_session_repeated_raw_accepted']:
        raise ValueError('Every photo, preview, fresh live view and menu cycle must pass')
    print(json.dumps(dict(passed=True, result_sha256=sha(result),
        photos=accepted['requested'], raw_samples=accepted['all_raw_samples'],
        original_algorithms_accepted=False, movies_accepted=False)))
    return accepted


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.output)
