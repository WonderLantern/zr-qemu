# SPDX-License-Identifier: GPL-2.0-or-later
"""Versioned source/build provenance for standalone capture experiments."""
import json
from pathlib import Path
from probe import sha

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent


def validate(binary=None):
    manifest = json.loads((PUBLIC / '.local/build-manifest.json').read_text())
    if binary is not None and Path(binary).resolve() != Path(manifest['binary']).resolve():
        raise ValueError('Capture requires the binary in this checkout\'s build manifest')
    if sha(Path(manifest['binary'])) != manifest['binary_sha256']:
        raise ValueError('Binary differs from its build receipt; rebuild')
    for name, digest in manifest['sources'].items():
        if sha(PUBLIC / name) != digest:
            raise ValueError('Source changed since build: ' + name)
    return manifest


def archive(g, manifest):
    (g.out / 'public-build-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    compiled = Path(manifest['binary']).parents[1] / 'qemu-10.2.4/hw/arm'
    for name, digest in manifest.get('compiled_sources', {}).items():
        source = compiled / name
        if sha(source) != digest:
            raise ValueError('Compiled source changed since build: ' + name)
        (g.out / name).write_bytes(source.read_bytes())
    g.data['public_build'] = manifest


def output_path(path):
    path = Path(path).resolve()
    if path.is_relative_to(PUBLIC) and not path.is_relative_to(PUBLIC / '.local'):
        raise ValueError('Outputs within the repository must be under ignored .local/')
    if path.exists():
        raise ValueError('Use a fresh output directory; existing evidence is preserved')
    return path
