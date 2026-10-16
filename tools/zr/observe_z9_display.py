# SPDX-License-Identifier: GPL-2.0-or-later
"""One-shot original LCD ISR/callback/flag observations during native boot."""
import json
from pathlib import Path
import re

from probe import sha
from probe_graphics_image import save


class Observer:
    def __init__(self, g):
        self.g = g
        self.points = {0x402b0aa4:'display_isr', 0x402bae60:'display_callback',
                       0x402bae90:'display_frame_cause', 0x402baf20:'display_high_flags_dispatch'}
        self.record = dict(source_sha256=sha(Path(__file__)), stops=[], camera_acceptance=False,
                           classification='system_emulated_read_only_original_display')
        g.data['native_display_observer'] = self.record
        (g.out/'display-observer-source.py').write_bytes(Path(__file__).read_bytes())
        for pc in self.points:
            g.rsp(f'Z1,{pc:x},4')

    def handle(self):
        hits = []
        handled = False
        for cpu in range(4):
            raw = self.g.qmp.hmp('info registers', cpu)
            regs = {k:int(v,16) for k,v in re.findall(r'\b(X\d\d|PC|SP)=([0-9a-fA-F]+)', raw)}
            pc = regs['PC']
            if pc not in self.points:
                continue
            handled = True
            name = self.points[pc]
            # Every hit is removed before resuming. Retaining a breakpoint at
            # the current PC makes QMP cont hit it again without executing the
            # original instruction (negative run native-004). The bit16 arm
            # itself selects frame completion without a persistent filter.
            hits.append(pc)
            row = dict(name=name, cpu=cpu, registers=regs,
                       scanout=json.loads(self.g.qmp.command('qom-get', path='/machine', property='engine1548-scanout-state')))
            if name == 'display_isr':
                row['descriptor_hex'] = save(self.g, 'native-display-isr-descriptor', regs['X00'], 0x38).hex()
            if name in ('display_callback', 'display_frame_cause'):
                row['payload_hex'] = save(self.g, 'native-'+name+'-payload', regs['X01'], 16).hex()
            if name == 'display_frame_cause':
                next_pc = 0x402baec8
                self.points[next_pc] = 'display_low_flags_dispatch'
                self.g.rsp(f'Z1,{next_pc:x},4')
            self.record['stops'].append(row)
        for pc in set(hits):
            self.g.rsp(f'z1,{pc:x},4')
            del self.points[pc]
        return handled

    def close(self):
        self.record['not_observed'] = list(self.points.values())
        for pc in self.points:
            self.g.rsp(f'z1,{pc:x},4')
        self.points.clear()


def capture_console(g, label):
    file = g.out/(label+'.ppm')
    before = json.loads(g.qmp.command('qom-get', path='/machine', property='engine1548-scanout-state'))
    staged=g.runtime/(file.name+'.capture')
    if staged.exists():raise ValueError('Preserve previous native screen capture')
    g.qmp.command('screendump', filename=str(staged))
    from host_capture_file import publish
    publish(g,staged,file)
    after = json.loads(g.qmp.command('qom-get', path='/machine', property='engine1548-scanout-state'))
    if before != after:
        raise ValueError('host screenshot changed the paused display state')
    arguments=g.data.get('probe_arguments',{})
    if before.get('last_frame_has_video') and (arguments.get('raw_pipeline_model') or arguments.get('raw_input')):
        from capture_lcd_planes import capture
        capture(g,label,before)
    record=dict(file=file.name,bytes=file.stat().st_size,sha256=sha(file),scanout=before)
    if arguments.get('raw_input') or arguments.get('raw_pipeline_model'):
        record['raw']=json.loads(g.qmp.command('qom-get',path='/machine',property='raw-pipeline-state'))
        record['virtual_ns']=json.loads(g.qmp.command('qom-get',path='/machine',property='runtime-clock-state'))['virtual_ns']
    g.data.setdefault('display_console_captures', []).append(record)
