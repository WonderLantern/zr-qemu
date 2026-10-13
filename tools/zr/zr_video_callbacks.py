# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded read-only original VIDEO callbacks for early failure detection.

An original failure result should end the input recipe promptly. Success still
requires camera source DMA, actual video files and independent full decoding.
"""
import hashlib
import json
import struct
from pathlib import Path

FIRMWARE = '9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f'
ACTOR = 0xa02830858
POINTS = {
    'app_video_started_callback': ('start', 0x40f72f2c, 5),
    'app_video_stopped_callback': ('stop', 0x40f72f80, 7),
}


def callback(row):
    binding = POINTS.get(row.get('name'))
    if binding is None:
        return None
    kind, pc, state = binding
    if int(row['pc'], 0) != pc or int(row['registers'][0], 0) != ACTOR:
        raise ValueError('Original VIDEO callback binding changed')
    data = row['memory']
    actor, parent, payload = (data.get(key) for key in
        ('app_shoot_actor', 'app_control_state', 'native_command_payload'))
    if actor is None or parent is None or payload is None:
        return None
    actor, parent, payload = (bytes.fromhex(value) for value in (actor, parent, payload))
    if (len(actor) < 0x254 or len(parent) < 0x6cc or len(payload) < 4):
        raise ValueError('Truncated original VIDEO callback observation')
    if (struct.unpack_from('<I', actor, 0x240)[0] != state or
            struct.unpack_from('<I', parent, 0x6c8)[0] != 2):
        # The original callback ignores replies outside its pending state.
        return None
    code = struct.unpack_from('<I', payload)[0]
    reason = struct.unpack_from('<I', actor, 0x250)[0]
    return dict(kind=kind, index=row['index'], cpu=row['cpu'], pc=hex(pc),
                result=code, actor_pending_state=state, stop_reason=reason,
                failed=code != 0 and (kind == 'start' or reason != 4))


class NativeVideoCallbacks:
    def __init__(self, guest):
        self.offset = 0
        self.results = {'start': [], 'stop': []}
        self.record = dict(enabled=False, events=[], guest_writes=False,
            scope='Original guarded callback failure detection; success is not frame/file acceptance')
        guest.data['video_callback_failure_observation'] = self.record
        observer = guest.data.get('lifecycle_observer')
        if not observer:
            return
        profile_path = guest.out/'lifecycle-profile.json'
        profile = json.loads(profile_path.read_text())
        if profile.get('firmware_sha256') != FIRMWARE or guest.data.get('main_sha256') != FIRMWARE:
            raise ValueError('Original VIDEO callback observer requires pinned ZR firmware')
        memory = profile['memory']
        ready = all(profile['points'].get(name) and int(profile['points'][name], 0) == pc
            for name, (_, pc, _) in POINTS.items())
        ready &= (memory.get('native_command_payload', {}).get('register') == 1 and
                  memory.get('native_command_payload', {}).get('bytes', 0) >= 4 and
                  int(memory.get('app_shoot_actor', {}).get('address', '0'), 0) == ACTOR and
                  memory.get('app_shoot_actor', {}).get('bytes', 0) >= 0x254 and
                  int(memory.get('app_control_state', {}).get('address', '0'), 0) == 0xa0282f4b8 and
                  memory.get('app_control_state', {}).get('bytes', 0) >= 0x6cc)
        if not ready:
            return
        if hashlib.sha256(profile_path.read_bytes()).hexdigest() != observer['profile_sha256']:
            raise ValueError('Original callback profile/result binding differs')
        self.path = guest.out/'lifecycle.jsonl'
        source = Path(__file__)
        (guest.out/source.name).write_bytes(source.read_bytes())
        self.record.update(enabled=True, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                           profile_sha256=observer['profile_sha256'])

    def failure(self, kind, ordinal):
        if not self.record['enabled']:
            return None
        if self.path.stat().st_size < self.offset:
            raise ValueError('Original callback trace was truncated')
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            while True:
                start = stream.tell()
                line = stream.readline()
                if not line:
                    break
                if not line.endswith(b'\n'):
                    stream.seek(start)
                    break
                result = callback(json.loads(line))
                if result is not None:
                    events = self.results[result['kind']]
                    if len(events) >= 8:
                        raise ValueError('Original VIDEO callbacks exceed bounded shutter recipe')
                    events.append(result)
                    self.record['events'].append(result)
            self.offset = stream.tell()
        events = self.results[kind]
        if len(events) < ordinal:
            return None
        result = events[ordinal-1]
        return result if result['failed'] else None
