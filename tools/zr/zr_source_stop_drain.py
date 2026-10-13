# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded diagnostic input for an in-flight frame after source disable.

Hypothesis only: source stop can precede the last channel/global boundary. It uses
the existing external MMIO-device status input and never changes guest RAM,
registers, timers, source controls or completion callbacks.
"""
import json
from pathlib import Path


class SourceStopDrain:
    def __init__(self,guest,kind='global0',limit=4):
        if kind not in ('global0','channel','both'):raise ValueError('known diagnostic boundary kind required')
        if limit not in (4,16,32):raise ValueError('bounded diagnostic drain limit required')
        self.kind=kind
        self.g=guest;self.previous=False;self.due=None
        self.record=dict(classification='diagnostic final-frame boundary hypothesis',
            kind=kind,global0_bits=0x90 if kind in ('global0','both') else 0,
            channel_bits=1 if kind in ('channel','both') else 0,
            max_pulses=limit,pulses=[],scheduled=[],cancelled=0,
            gate='falling source enable with channel0 bits12/13 set; one input-period delay',
            guest_pc_trigger=False,physical_protocol_verified=False,pixel_bytes=0)
        guest.data['source_stop_drain_input']=self.record
        (guest.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())

    def tick(self,clock):
        if not clock.running:return
        group=self.g.rd(0x15080010);channel=self.g.rd(0x15080028)
        active=bool(group&1 and channel&1)
        if self.previous and not active and channel&0x3000==0x3000 and len(self.record['scheduled'])<self.record['max_pulses']:
            state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='event1508-channel-state'))
            delay=state['period_ns']/1e9
            if not 0<delay<=1:raise ValueError('bounded source input period required')
            self.due=clock.seconds+delay
            self.record['scheduled'].append(dict(virtual_seconds=clock.seconds,due_seconds=self.due,
                channel_control=channel,group_control=group))
        self.previous=active
        if self.due is not None and active:
            self.due=None;self.record['cancelled']+=1
        if self.due is not None and clock.seconds>=self.due:
            if self.kind in ('channel','both'):
                self.g.qmp.command('qom-set',path='/machine',property='event1508-channel-input',value='1')
            if self.kind in ('global0','both'):
                self.g.qmp.command('qom-set',path='/machine',property='event1508-global0-input',value='144')
            self.record['pulses'].append(dict(virtual_seconds=clock.seconds,source_still_disabled=True))
            self.due=None
