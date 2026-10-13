# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded read-only ownership snapshots while the original stream runs.

Capture before native fault recovery changes the source state. No interrupt,
descriptor, reference, task state or guest register is supplied by this tool.
"""
import json
import hashlib
from pathlib import Path

_SOURCE=Path(__file__).read_bytes()
_SOURCE_SHA256=hashlib.sha256(_SOURCE).hexdigest()


def observe(guest, raw, virtual_seconds):
    archived=guest.out/Path(__file__).name
    if not archived.exists():archived.open('xb').write(_SOURCE)
    if archived.read_bytes()!=_SOURCE:raise ValueError('Preserve the actual stream observer revision')
    def get(name):
        return json.loads(guest.qmp.command('qom-get', path='/machine', property=name))
    source = get('engine150c-state')
    control = get('engine151-control-state')['instances'][1]
    resize = get('engine1543-control-state')['blocks'][0]
    source_unit = get('engine1518-state')['instances'][2]
    outputs = get('engine1542-state')['blocks']
    result = dict(virtual_seconds=virtual_seconds, raw=raw, observer_sha256=_SOURCE_SHA256,
        source_clock=get('event1508-channel-state'),
        primary={key:source[key] for key in ('active','stop_requested','stop_done')},
        primary_hold=guest.rd(0x150c0018), reset=get('primary-reset-state')['stage'],
        source_control=[guest.rd(0x15080010),guest.rd(0x15080028)],
        resize={key:resize[key] for key in ('active','held','starts','stops')},
        isp={key:control[key] for key in ('active','starts','stops')},
        source_gate=source_unit['config'][0x30//4],
        source_pending=source_unit['pending'], isp_pending=guest.rd(0x15140044),
        source_a_pending=outputs[0]['pending'], output_c_pending=outputs[10]['pending'],
        scope='read-only stream ownership before native recovery; no completion supplied')
    if guest.data.get('probe_arguments', {}).get('source_front_boundary'):
        result['front_boundary'] = get('event1508-front-boundary-state')
    return result


def due(records, raw, virtual_seconds):
    if len(records)>=64:return False
    if not records:return True
    previous=records[-1]
    return (virtual_seconds-previous['virtual_seconds']>=.5 and
            (raw['frames']!=previous['raw']['frames'] or
             virtual_seconds-previous['virtual_seconds']>=2))
