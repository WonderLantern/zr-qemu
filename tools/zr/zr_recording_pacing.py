# SPDX-License-Identifier: GPL-2.0-or-later
"""Pace external VIDEO shutter inputs from the original dispatch selector.

The original 40f729cc reads actor+254 to choose event11 or12. This field
selects a next start/stop request; it does not prove encoded frames or files.
"""
import struct
import hashlib
import json
import time
from fractions import Fraction
import math
from pathlib import Path
from probe import sha
from zr_key_sequence import recording_shutter_presses


def dispatch_sample_matches(expected, selector, request_state):
    """Require the original settled state, not just its next-input selector.

    C1.11 40f72f54 sets selector1 and state6 after successful START.
    STOP sets state7 but leaves selector1 until its callback completes.
    Consequently a pending STOP must never satisfy a continuous REC gate.
    Successful STOP at40f72fc4 clears the selector and sets state0.
    """
    if selector is None:
        return False
    if expected == 1 and request_state == 7:
        raise RuntimeError('Original VIDEO entered STOP before the required clip duration')
    return selector == expected and request_state == (6 if expected else 0)


def encoded_duration_progress(state, seconds):
    """Additional pacing only; actual MOV frame count/decode remain required.

    Native627 held REC for30 virtual seconds but its714 MOV frames span
    23.8238 seconds. Allow one final picture of mux lookahead when pacing
    STOP. This does not accept a file, timestamps or source correctness.
    """
    active=[i for i in state['instances'] if i.get('created') and i.get('configured')]
    if len(active)!=1:
        return dict(ready=False,reason='one active configured encoder required')
    item=active[0]
    n,d=item.get('fps_n',0),item.get('fps_d',0)
    if n<=0 or d<=0:
        return dict(ready=False,reason='encoded rational frame rate unavailable')
    required=math.ceil(Fraction(str(seconds))*n/d)+1
    return dict(ready=item['pictures']>=required,pictures=item['pictures'],
                required_pictures=required,fps_n=n,fps_d=d,file_accepted=False)


class RecordingPacing:
    def __init__(self, guest, states, active_seconds, timeout_seconds, *, observer=None, peer=None):
        self.g = guest
        self.observer, self.peer = observer, peer
        self.active_seconds = active_seconds
        self.timeout_seconds = timeout_seconds
        self.next_poll = 0
        self.next_codec_progress = 0
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
        from zr_video_recovery_pacing import VideoRecoveryPacing
        self.recovery = VideoRecoveryPacing(guest, states, max(self.targets), timeout_seconds)

    def image_devices(self,stage,phase):
        """Read coarse device ownership through this session's existing QMP."""
        arguments=self.g.data.get('probe_arguments',{})
        if arguments.get('capture_video_source_ram'):
            from capture_video_source_ram import capture
            capture(self.g, stage, phase)
        if not (arguments.get('video_yuv_output_events') or arguments.get('video_source_end') or arguments.get('video_secondary_isp')):
            return
        import json
        value=dict(stage=stage,phase=phase,read_only=True)
        for property in ('raw-pipeline-state','video-raw-transport-state','video-yuv-output-state','video-source-end-state','video-secondary-isp-state','video-secondary-sensor-state','video-secondary-source-end-state','video-primary-boundaries-state','engine151-active-program-state',
                         'engine1543-control-state','engine151-control-state','engine1518-state',
                         'engine152c-stream-receiver-state','engine1530-config-state','event1508-channel-state','engine150c-state'):
            try:
                state=json.loads(self.g.qmp.command('qom-get',path='/machine',property=property))
                if property=='engine1543-control-state':
                    state=dict(blocks=[{k:v for k,v in row.items() if k!='latched'} for row in state['blocks']])
                elif property=='engine151-control-state':
                    state=dict(instances=[dict(base=row['base'],active=row['active'],ready=row['ready'],
                        input_format=row['latched'].get('0x200')) for row in state['instances']])
                elif property=='engine1518-state':
                    state=dict(instances=[dict(pending=row['pending'],source_gate=row['config'][0x30//4],
                        mask=row['config'][8//4],drains=row['drains']) for row in state['instances']])
                elif property=='engine1530-config-state':
                    state=dict(enabled=state['enabled'],held=state['held'],front_start=state['front'][8//4],
                        front_pending=state['front'][0x1c//4],front_mask=state['front'][0x18//4],
                        decoder_gate=state['core'][0x38//4])
                elif property=='engine152c-stream-receiver-state':
                    state={k:state.get(k) for k in ('enabled','requested','pending','jobs','acks','bytes','row','cancels')}
                elif property=='engine150c-state':
                    state={k:state.get(k) for k in ('active','stop_requested','stop_done')}
                value[property]=state
            except Exception as error:
                value[property]=dict(observation_error=repr(error))
        if arguments.get('video_source_ram'):
            value['video-source-ram-state']=json.loads(self.g.qmp.command(
                'qom-get',path='/machine',property='video-source-ram-state'))
        if arguments.get('video_main_output'):
            value['video-main-output-state']=json.loads(self.g.qmp.command(
                'qom-get',path='/machine',property='video-main-output-state'))
        if arguments.get('wave5_vpu'):
            value['wave5-vpu-state']=json.loads(self.g.qmp.command(
                'qom-get',path='/machine',property='wave5-vpu-state'))
        if arguments.get('programmed_channel_clock'):
            value['event1508-programmed-clock-state']=json.loads(self.g.qmp.command(
                'qom-get',path='/machine',property='event1508-programmed-clock-state'))
        self.g.data.setdefault('video_device_state_snapshots',[]).append(value)
        # Keep the latest bounded, read-only gate snapshots available while
        # the native workflow runs. Result.json remains the terminal record.
        # Atomic replacement avoids readers observing a partial JSON write.
        progress = self.g.out/'video-device-progress.json'
        temporary = progress.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(dict(
            main_sha256=self.g.data['main_sha256'],
            qemu_sha256=self.g.data['qemu_sha256'],
            terminal=False, read_only=True,
            snapshots=self.g.data['video_device_state_snapshots']), indent=2)+'\n')
        temporary.replace(progress)

    def advance(self, stage, clock):
        if stage not in self.targets:
            return self.recovery.advance(stage, clock)
        expected = self.targets[stage]
        gate = self.record['gates'].setdefault(str(stage), dict(expected=expected,
            begun_clock_seconds=clock.seconds, samples=[], matched=False))
        if gate['matched']:
            return self.recovery.advance(stage, clock)
        if time.monotonic() >= self.next_poll:
            kind, ordinal = self.callback_targets[stage]
            failure = self.callbacks.failure(kind, ordinal)
            if failure is not None:
                gate['original_callback_failure'] = failure
                raise RuntimeError(f'Original VIDEO {kind.upper()} returned failure {failure["result"]}')
            self.g.qmp.command('stop')
            try:
                if not gate.get('device_state_before_sampled'):
                    self.image_devices(stage,'first-gate-observation')
                    gate['device_state_before_sampled']=True
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
                if expected and value == 0:
                    stopped = self.callbacks.stopped_after_start(ordinal)
                    if stopped is not None:
                        gate['original_early_stop'] = stopped
                        self.image_devices(stage, 'original-stop-before-required-clip-duration')
                        raise RuntimeError('Original VIDEO stopped before the required clip duration')
                try:
                    settled = dispatch_sample_matches(expected, value, sample['actor_request_state'])
                except RuntimeError:
                    gate['original_early_stop_request'] = sample
                    self.image_devices(stage, 'original-stop-request-before-required-clip-duration')
                    raise
                if settled:
                    if not gate.get('first_selector_transition_sampled'):
                        self.image_devices(stage, 'first-original-selector-transition')
                        gate['first_selector_transition_sampled'] = True
                    gate.setdefault('transition_clock_seconds', clock.seconds)
                    held = clock.seconds - gate['transition_clock_seconds']
                    enough_pictures=True
                    if expected and self.g.data.get('probe_arguments',{}).get('mode_video_encoded_duration'):
                        if held>=self.active_seconds or time.monotonic()>=self.next_codec_progress:
                            codec=json.loads(self.g.qmp.command('qom-get',path='/machine',property='wave5-vpu-state'))
                            gate['encoded_duration_progress']=encoded_duration_progress(codec,self.active_seconds)
                            progress=dict(stage=stage,clock_seconds=clock.seconds,held_clock_seconds=held,
                                selector=value,actor_request_state=sample['actor_request_state'],
                                encoded_duration_progress=gate['encoded_duration_progress'],
                                read_only=True,file_accepted=False,scope='Live current encoder counter; boundary snapshots are historical, NVMe ring data can remain buffered until STOP')
                            target=self.g.out/'video-recording-live.json';temporary=target.with_suffix('.json.tmp')
                            temporary.write_text(json.dumps(progress,indent=2)+'\n');temporary.replace(target)
                            self.next_codec_progress=time.monotonic()+2
                        enough_pictures=gate.get('encoded_duration_progress',{}).get('ready',False)
                    if not expected or (held >= self.active_seconds and enough_pictures):
                        file = self.g.out/f'zr-video-dispatch-gate-{stage:03d}.bin'
                        file.write_bytes(actor)
                        gate.update(matched=True, matched_clock_seconds=clock.seconds,
                            file=file.name, sha256=sha(file))
                        self.image_devices(stage,'matched-original-selector')
                else:
                    gate.pop('transition_clock_seconds', None)
                if (expected and self.g.data.get('probe_arguments', {}).get('video_source_ram')
                        and not gate.get('completed_source_transfer_sampled')):
                    source_state = json.loads(self.g.qmp.command(
                        'qom-get', path='/machine', property='video-source-ram-state'))
                    baseline = gate.setdefault('source_transfer_baseline_jobs', source_state['jobs'])
                    if source_state['jobs'] > baseline:
                        self.image_devices(stage, 'first-completed-source-transfer')
                        gate['completed_source_transfer_sampled'] = True
            finally:
                self.g.qmp.command('cont')
            self.next_poll = time.monotonic() + 0.5
        if not gate['matched'] and clock.seconds - gate['begun_clock_seconds'] >= self.timeout_seconds:
            raise TimeoutError(f'Original VIDEO dispatch did not settle to {expected} after input state{stage}')
        return gate['matched'] and self.recovery.advance(stage, clock)
