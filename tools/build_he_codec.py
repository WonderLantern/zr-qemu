# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the functional codec without camera firmware or private SDKs."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

HERE=Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(work_root):
    if os.name=='nt' or os.environ.get('WSL_DISTRO_NAME')=='ubuntu-noble':
        raise ValueError('Use Linux or the explicitly authorized Nikon distribution')
    WORK=Path(work_root).resolve()
    binary=WORK/'build/qemu-system-aarch64'
    for p in Path('/proc').glob('[0-9]*/exe'):
        try:
            if p.resolve()==binary:raise RuntimeError('Stop this build\'s QEMU before rebuilding')
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    source=HERE/'qemu';public=source/'nikon-he-public'
    receipt=json.loads((public/'runtime-source-receipt.json').read_text())
    for name,digest in receipt['files'].items():
        assert sha(public/name)==digest,name
    paths=[source/'nikon-he-runtime.cpp',source/'nikon-he-runtime.h',source/'nikon-he-forward.inc']
    paths+=sorted(p for p in public.iterdir() if p.is_file())
    inventory={str(p.relative_to(source)):sha(p) for p in paths}
    work=WORK/'he-runtime';work.mkdir(exist_ok=True)
    manifest=work/'build-manifest.json';library=work/'libnikon-he-runtime.a'
    if manifest.exists():
        prior=json.loads(manifest.read_text())
        if prior['sources']==inventory and library.exists() and sha(library)==prior['library_sha256']:
            return prior
    compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0]
    objects=[]
    with (work/'build.log').open('w') as log:
        for p in [source/'nikon-he-runtime.cpp']+sorted(public.glob('*.cpp')):
            obj=work/(p.stem+'.o');objects.append(obj)
            subprocess.run(['g++','-std=c++17','-O2','-fPIC','-Wall','-Wextra',
                '-c',str(p),'-o',str(obj)],stdout=log,stderr=subprocess.STDOUT,check=True)
        subprocess.run(['ar','rcs',str(library),*[str(p) for p in objects]],check=True)
    record=dict(sources=inventory,library=str(library),library_sha256=sha(library),compiler=compiler,
        classification='authored functional HE forward encoder and pinned public inverse; original Nikon arithmetic unverified')
    manifest.write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True)
    print(json.dumps(build(p.parse_args().work_dir)))
