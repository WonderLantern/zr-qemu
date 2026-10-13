# SPDX-License-Identifier: GPL-2.0-or-later
"""Realize both boards with stopped CPUs and check explicit video opt-ins."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

OPTIONS = (
    'video-yuv-output-events-model', 'video-source-end-model',
    'video-secondary-isp-model', 'video-secondary-sensor-model',
    'video-secondary-source-end-model', 'video-receiver-before-supplier-model',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = []
    for model in ('nikon-z9-lab', 'nikon-zr-lab'):
        for enabled in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                stub = Path(directory)/'authored-zero.bin'
                stub.write_bytes(bytes(4))
                machine = model
                if enabled:
                    machine += ','+','.join(name+'=on' for name in OPTIONS)
                commands = [dict(execute='qmp_capabilities')]
                for name in OPTIONS:
                    commands.extend((
                        dict(execute='qom-get', arguments=dict(path='/machine', property=name)),
                        dict(execute='qom-set', arguments=dict(path='/machine', property=name, value=not enabled)),
                        dict(execute='qom-get', arguments=dict(path='/machine', property=name)),
                    ))
                commands.append(dict(execute='quit'))
                proc = subprocess.run([
                    str(args.qemu.resolve()), '-M', machine, '-kernel', str(stub), '-smp', '4',
                    '-display', 'none', '-serial', 'none', '-monitor', 'none', '-S', '-qmp', 'stdio',
                ], input=''.join(json.dumps(command)+'\n' for command in commands),
                    capture_output=True, text=True, timeout=30)
                if proc.returncode:
                    raise RuntimeError(proc.stderr)
                replies = [json.loads(line) for line in proc.stdout.splitlines()]
                replies = [item for item in replies if 'return' in item or 'error' in item]
                if len(replies) != len(commands):
                    raise ValueError('Incomplete QMP replies')
                for index, name in enumerate(OPTIONS):
                    before, rejected, after = replies[1+3*index:4+3*index]
                    if before.get('return') is not enabled or after.get('return') is not enabled:
                        raise ValueError('Incorrect cold or retained option state: '+name)
                    if 'immutable after realization' not in rejected.get('error', {}).get('desc', ''):
                        raise ValueError('Post-realization option change was not rejected: '+name)
                reports.append(dict(model=model, enabled=enabled, options_checked=len(OPTIONS),
                    owned_qemu_stopped=True, firmware_used=False, cpu_execution=False))
    result = dict(passed=True, binary_sha256=hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
        reports=reports, checks=len(reports)*len(OPTIONS)*3, native_movie_accepted=False)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=True, realizations=len(reports), checks=result['checks'])))


if __name__ == '__main__':
    main()
