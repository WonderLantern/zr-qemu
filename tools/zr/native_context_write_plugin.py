# SPDX-License-Identifier: GPL-2.0-or-later
"""Attach an opt-in read-only field-provenance plugin to a pinned workflow."""
import json
import os
from pathlib import Path
import subprocess
from native_lifecycle_plugin import sha

HERE=Path(__file__).resolve().parent

def attach(guest, profile, profile_path):
    if (os.name=='nt' or os.environ.get('WSL_DISTRO_NAME')=='ubuntu-noble'):
        raise ValueError('Dedicated Nikon distribution required')
    options=profile['context_write_watch']
    if options!=dict(point='source_movie_enabled_check',register=8,offset=32,
        heap_start='0xa18000000',heap_end='0xa1a000000',
        globals=['0xa03e398d0','0xa03e39468','0xa03e38394']):
        raise ValueError('Exact pinned source-context watch contract required')
    if profile['points'].get(options['point'])!='0x4108a048':
        raise ValueError('Original source-context reader required')
    work=Path(guest.command[0]).parents[1]
    source=HERE/'trace_native_context_writes.c';header=work/'qemu-10.2.4/include/qemu/qemu-plugin.h'
    cache=work/'lifecycle-plugins';cache.mkdir(exist_ok=True)
    plugin=cache/(sha(source)[:20]+'-'+sha(header)[:12]+'-context.so')
    if not plugin.exists():
        flags=subprocess.check_output(['pkg-config','--cflags','--libs','glib-2.0'],text=True).split()
        temporary=plugin.with_suffix('.building.so')
        subprocess.run(['cc','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
            '-I'+str(header.parent),str(source),'-o',str(temporary),*flags],check=True)
        temporary.replace(plugin)
    bindings=guest.out/'context-write.bindings'
    bindings.write_text('4108a048 8 a18000000 a1a000000 41485d40 41485f80 a03e398d0 a03e39468 a03e38394\n')
    (guest.out/source.name).write_bytes(source.read_bytes())
    (guest.out/'context-write-profile.json').write_text(json.dumps(options,indent=2)+'\n')
    guest.command+=['-plugin',f'{plugin},bindings={bindings},out={guest.out}/context-writes.jsonl']
    guest.data['context_write_observer']=dict(source_sha256=sha(source),plugin_sha256=sha(plugin),
        profile_sha256=sha(profile_path),bindings_sha256=sha(bindings),log='context-writes.jsonl',
        scope='Read-only original CPU stores and exact native reader-selected context+20, bounded heap/lookback; initialization predating lookback is unobserved. No guest/model/CPU/OS writes.')
