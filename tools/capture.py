# SPDX-License-Identifier: GPL-2.0-or-later
"""Run one native full RAW capture, resumed liveview and two postshot menus."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
from capture_support import HERE, PUBLIC, output_path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--firmware', type=Path, required=True)
    p.add_argument('--raw', type=Path, default=PUBLIC / '.local/z9-14bit.raw')
    p.add_argument('--qemu', type=Path)
    p.add_argument('--output', type=Path, default=PUBLIC / '.local' / time.strftime('capture-%Y%m%d-%H%M%S'))
    p.add_argument('--seconds', type=int, default=600, help='Host deadline, including preparation (15..600)')
    p.add_argument('--profile',choices=('compatibility','lossless14'),default='compatibility',help='lossless14 runs two released-photo/menu cycles')
    p.add_argument('--audit', action='store_true', help='After shutdown, extract NEF and independently decode every sample (requires rawpy)')
    a = p.parse_args()
    if not 15 <= a.seconds <= 600:
        p.error('--seconds must be 15..600')
    output = output_path(a.output)
    with a.raw.open('rb') as f:
        header = f.read(32)
    fields = struct.unpack('<8s6I', header) if len(header) == 32 else None
    if not fields or fields[0] != b'NZ9RAW1\0' or fields[1:3] not in ((8256,5504),(8280,5520)) or fields[3:] != (14,0,0,16383):
        p.error('Full capture requires local 8256x5504 or 8280x5520, 14-bit RGGB NZ9RAW1 input; see docs/capture.md')
    if a.raw.stat().st_size != 32 + fields[1]*fields[2]*2:
        p.error('Full sensor input is truncated or has trailing bytes')
    profile = json.loads((HERE / ('capture-lossless14-profile.json' if a.profile=='lossless14' else 'capture-profile.json')).read_text())
    argv = [sys.executable, str(HERE / 'capture_sequence.py'), '--name', 'z9-capture',
            '--firmware', str(a.firmware.resolve()), '--raw', str(a.raw.resolve()), '--output', str(output)]
    if a.qemu:
        argv += ['--qemu', str(a.qemu.resolve())]
    for key, value in dict(profile['arguments'], seconds=a.seconds).items():
        flag = '--' + key.replace('_', '-')
        if value is True:
            argv.append(flag)
        elif value is not False and value is not None:
            argv += [flag, str(value)]
    subprocess.run(argv, check=True)
    if a.profile=='lossless14':
        from virtual_recording_card import audit
        from inspect_virtual_exfat import catalog
        checked=audit(output/'capture-card.raw')
        (output/'capture-card.catalog.json').write_text(json.dumps(catalog(Path(checked['derived_volume'])),indent=2)+'\n')
        if a.audit:subprocess.run([sys.executable,str(HERE/'audit_repeated_capture.py'),'--output',str(output)],check=True)
    else:
        subprocess.run([sys.executable, str(HERE / 'export_card.py'), '--output', str(output)], check=True)
        if a.audit:subprocess.run([sys.executable, str(HERE / 'audit_native_nef.py'), '--output', str(output)], check=True)
    print('Capture output: ' + str(output))


if __name__ == '__main__':
    main()
