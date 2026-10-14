# SPDX-License-Identifier: GPL-2.0-or-later
"""Read actual complete JPEG and finite small/mid input at original ISR entry."""
import json
from pathlib import Path
from probe import sha


def dump_completed(g, observation, registers):
    s = observation['jpeg']
    job = s['jobs']
    seen = g.data.setdefault('jpeg_completed_native_dumps', [])
    if any(x['job'] == job for x in seen):
        raise ValueError('Do not overwrite an original completed-job snapshot')
    files = []

    def dump(label, address, n, suffix):
        if not 0 < n <= 128*1024*1024 or not any(
                lo <= address < address+n <= hi for lo,hi in
                ((0x840000000, 0x8adf8da00), (0x8adf8dc00, 0x8fff47400))):
            raise ValueError('Complete actual encoded/source span must be in real RAM')
        p = g.out / ('native-jpeg-job'+str(job)+'-'+label+suffix)
        if p.exists():
            raise ValueError('Immutable native codec observation required')
        reply = g.qmp.hmp(f'pmemsave {address:#x} {n:#x} "{p}"')
        if reply:
            raise RuntimeError(reply)
        files.append(dict(label=label, address=hex(address), bytes=n, file=p.name, sha256=sha(p)))

    preflight = None
    if (g.data.get('probe_arguments',{}).get('engine15e2_preflight')
            or g.data.get('probe_arguments',{}).get('capture_pipeline')):
        preflight = json.loads(g.qmp.command('qom-get',path='/machine',property='engine15e2-preflight-state'))
    count_only = bool(preflight and preflight['last_count_only'])
    if not count_only:
        dump('encoded', s['output'], s['last_bytes'], '.jpg')
    plane = s['stride'] * s['height']
    # Main-frame actual output is already saved by the capture graph observer.
    # Read complete middle/small planes here; no repeated 90MB main snapshot.
    if plane <= 4*1024*1024:
        dump('y', s['y'], plane, '.bin')
        dump('uv', s['uv'], plane, '.bin')
    config = json.loads(g.qmp.command('qom-get',path='/machine',property='engine15e2-config-state'))
    pipeline = json.loads(g.qmp.command('qom-get',path='/machine',property='capture-nv16-pipeline-state'))
    result = dict(job=job, count_only=count_only, preflight=preflight, original_pc=hex(registers['PC']), observation=observation,
                  jpeg_config=config, actual_capture_pipeline=pipeline, files=files,
                  scope='read-only whole actual encoded RAM and actual small/mid source at original ISR before software ACK; no host pixels/codec output or completion supplied')
    p = g.out / ('native-jpeg-job'+str(job)+'-observation.json')
    p.open('x').write(json.dumps(result,indent=2)+'\n')
    seen.append(result)
    (g.out / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    return result
