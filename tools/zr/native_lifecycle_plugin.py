# SPDX-License-Identifier: GPL-2.0-or-later
"""Build/cache a read-only whole-workflow observer in the authorized lab."""
import json
import hashlib
import os
import re
from pathlib import Path
import subprocess
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_bindings(profile):
    """Check the C observer's fixed capacities before starting a guest."""
    points, regions = profile.get('points'), profile.get('memory')
    if not isinstance(points, dict) or not 1 <= len(points) <= 64:
        raise ValueError('Lifecycle observer requires 1..64 instruction points')
    if not isinstance(regions, dict) or len(regions) > 8:
        raise ValueError('Lifecycle observer permits at most 8 memory regions')
    for name in (*points, *regions):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,63}', name):
            raise ValueError('Lifecycle labels require 1..63 ASCII letters, digits or underscores')
    for address in points.values():
        pc = int(address, 0)
        if not 0x40160000 <= pc < 0x45000000 or pc & 3:
            raise ValueError('Lifecycle point must be an aligned instruction in the bound image')
    for region in regions.values():
        size = region.get('bytes')
        if type(size) is not int or not 1 <= size <= 4096:
            raise ValueError('Lifecycle memory reads must be bounded to 1..4096 bytes')
        if 'register' in region:
            if 'address' in region or type(region['register']) is not int or not 0 <= region['register'] < 32:
                raise ValueError('One bounded AArch64 register required for dynamic observation')
        else:
            address = int(region['address'], 0)
            if not 0xa00000000 <= address <= 0xa40000000 - size:
                raise ValueError('Static lifecycle reads must remain in the work RAM window')


def attach(guest, profile_path):
    if (os.name == 'nt' or os.environ.get('WSL_DISTRO_NAME') == 'ubuntu-noble'):
        raise ValueError('Dedicated Nikon distribution required')
    profile_path = Path(profile_path)
    profile = json.loads(profile_path.read_text())
    validate_bindings(profile)
    if profile['firmware_sha256'] != guest.data.get('main_sha256', guest.data.get('firmware_sha256')):
        raise ValueError('Lifecycle bindings belong to another firmware')
    work = Path(guest.command[0]).parents[1]
    source = HERE/'trace_native_lifecycle.c'
    header = work/'qemu-10.2.4/include/qemu/qemu-plugin.h'
    cache = work/'lifecycle-plugins'
    cache.mkdir(exist_ok=True)
    plugin = cache/(sha(source)[:20]+'-'+sha(header)[:12]+'.so')
    if not plugin.exists():
        flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', 'glib-2.0'], text=True).split()
        temporary = plugin.with_suffix('.building.so')
        subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-I'+str(header.parent), str(source), '-o', str(temporary), *flags], check=True)
        temporary.replace(plugin)
    lines = []
    for name, address in profile['points'].items():
        lines.append(f'P {name} {int(address, 0):x} 0')
    for name, region in profile['memory'].items():
        if 'register' in region:
            if 'address' in region or type(region['register']) is not int or not 0 <= region['register'] < 32:
                raise ValueError('One bounded AArch64 register required for dynamic observation')
            lines.append(f'D {name} {region["register"]:x} {region["bytes"]}')
        else:
            lines.append(f'M {name} {int(region["address"], 0):x} {region["bytes"]}')
    bindings = guest.out/'lifecycle.bindings'
    bindings.write_text('\n'.join(lines)+'\n')
    (guest.out/'lifecycle-profile.json').write_bytes(profile_path.read_bytes())
    (guest.out/source.name).write_bytes(source.read_bytes())
    guest.command += ['-plugin', f'{plugin},bindings={bindings},out={guest.out}/lifecycle.jsonl']
    guest.data['lifecycle_observer'] = dict(source_sha256=sha(source), plugin_sha256=sha(plugin),
        profile_sha256=sha(profile_path), log='lifecycle.jsonl', maximum_records=8192,
        scope='Read-only non-stopping native callbacks and bounded work RAM; no device completion or guest edits')
