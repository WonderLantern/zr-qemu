# SPDX-License-Identifier: GPL-2.0-or-later
"""Pace external VIDEO shutter inputs from the original dispatch selector.

The original 40f729cc reads actor+254 to choose event11 or12. This field
selects a next start/stop request; it does not prove encoded frames or files.
"""
import struct
import hashlib
import time
from pathlib import Path
from probe import sha
from zr_key_sequence import recording_shutter_presses


class RecordingPacing:
    def __init__(self, guest, states, active_seconds, timeout_seconds, *, observer=None, peer=None):
        self.g = guest
        self.observer, self.peer = observer, peer
        self.active_seconds = active_seconds
        self.timeout_seconds = timeout_seconds
        self.next_poll = 0
        full = recording_shutter_presses(states)
        self.targets = {}
        self.callback_targets = {}
        for number, i in enumerate(full, 1):
            if i + 3 >= len(states) or states[i+3]['label'] != 'half-release':
                raise ValueError('Recording gate requires complete half/full/half release')
            self.targets[i+4] = number % 2
            self.callback_targets[i+4] = ('start' if number % 2 else 'stop', (number+1)//2)
        self.record = dict(source_sha256=sha(Path(__file__)), after_states=self.targets,
            clip_seconds=active_seconds, timeout_seconds=timeout_seconds, gates={},
            source='ZR C1.11 original application actor+254:0 chooses event11,1 chooses event12',
            scope='Read-only next-start/stop dispatch pacing; no guest writes or recording/file acceptance')
        guest.data['video_shutter_dispatch_gates'] = self.record
        (guest.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
        from zr_video_callbacks import NativeVideoCallbacks
        self.callbacks = NativeVideoCallbacks(guest)

    def advance(self, stage, clock):
        if stage not in self.targets:
            return True
        expected = self.targets[stage]
        gate = self.record['gates'].setdefault(str(stage), dict(expected=expected,
            begun_clock_seconds=clock.seconds, samples=[], matched=False))
        if gate['matched']:
            return True
        if time.monotonic() >= self.next_poll:
            kind, ordinal = self.callback_targets[stage]
            failure = self.callbacks.failure(kind, ordinal)
            if failure is not None:
                gate['original_callback_failure'] = failure
                raise RuntimeError(f'Original VIDEO {kind.upper()} returned failure {failure["result"]}')
            self.g.qmp.command('stop')
            try:
                if self.observer:
                    self.observer.handle()
                if self.peer:
                    self.peer.handle()
                parent = self.g.read_bytes(0xa0282f4b8, 0x748)
                actor_address = struct.unpack_from('<Q', parent, 0x2c8)[0]
                bindings = {0xa02830858:0x40f729cc, 0xa02830148:0x40f71bb0}
                if actor_address not in bindings:
                    gate['unsupported_actor'] = hex(actor_address)
                    raise ValueError('Current original VIDEO actor is outside verified dispatch bindings')
                actor = self.g.read_bytes(actor_address, 0x280)
                if (struct.unpack_from('<Q', actor)[0] != 0xa0282f4b8 or
                        struct.unpack_from('<Q', actor, 0x98)[0] != bindings[actor_address] or
                        struct.unpack_from('<I', parent, 0x6c8)[0] != 2):
                    raise ValueError('Original VIDEO dispatch binding/mode changed')
                # State3's verified40f71bb0 always selects START. It is not
                # the settled shoot actor and must not release either gate.
                value = actor[0x254] if actor_address == 0xa02830858 else None
                if value is not None and value not in (0, 1):
                    raise ValueError('Original VIDEO selector must remain binary')
                sample = dict(clock_seconds=clock.seconds, selector=value, actor=hex(actor_address),
                    app_state=struct.unpack_from('<I', parent, 0x2d0)[0],
                    actor_request_state=struct.unpack_from('<I', actor, 0x240)[0],
                    actor_stop_reason=struct.unpack_from('<I', actor, 0x250)[0],
                    actor_sha256=hashlib.sha256(actor).hexdigest())
                if len(gate['samples']) < 128:
                    gate['samples'].append(sample)
                else:
                    gate['samples_omitted'] = gate.get('samples_omitted', 0) + 1
                    gate['last_sample'] = sample
                if value == expected:
                    gate.setdefault('transition_clock_seconds', clock.seconds)
                    held = clock.seconds - gate['transition_clock_seconds']
                    if not expected or held >= self.active_seconds:
                        file = self.g.out/f'zr-video-dispatch-gate-{stage:03d}.bin'
                        file.write_bytes(actor)
                        gate.update(matched=True, matched_clock_seconds=clock.seconds,
                            file=file.name, sha256=sha(file))
                else:
                    gate.pop('transition_clock_seconds', None)
            finally:
                self.g.qmp.command('cont')
            self.next_poll = time.monotonic() + 0.5
        if not gate['matched'] and clock.seconds - gate['begun_clock_seconds'] >= self.timeout_seconds:
            raise TimeoutError(f'Original VIDEO dispatch did not settle to {expected} after input state{stage}')
        return gate['matched']
