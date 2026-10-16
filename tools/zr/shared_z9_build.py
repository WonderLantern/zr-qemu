# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate this public checkout's build; archive only its declared sources."""
import json
from pathlib import Path
from probe import HERE,WORK,sha
PUBLIC=HERE.parents[1]

def validate():
    manifest=json.loads((PUBLIC/'.local/build-manifest.json').read_text())
    if Path(manifest['binary']).resolve()!=WORK/'build/qemu-system-aarch64' or sha(Path(manifest['binary']))!=manifest['binary_sha256']:
        raise ValueError('Use the unchanged binary from this checkout build receipt')
    for name,digest in manifest['sources'].items():
        if sha(PUBLIC/name)!=digest:raise ValueError('Source changed; rebuild: '+name)
    return manifest

def archive(g,manifest):
    for name,digest in manifest['compiled_sources'].items():
        path=WORK/'qemu-10.2.4/hw/arm'/name
        if sha(path)!=digest:raise ValueError('Compiled source changed: '+name)
        (g.out/name).write_bytes(path.read_bytes())
    for name,digest in manifest.get('he_codec_dependency',{}).get('sources',{}).items():
        path=PUBLIC/'qemu'/name
        if sha(path)!=digest:raise ValueError('Compiled HE source changed: '+name)
        target=g.out/'he-runtime-source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(path.read_bytes())
    (g.out/'shared-z9-build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    g.data['public_build']=manifest
