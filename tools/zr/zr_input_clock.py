# SPDX-License-Identifier: GPL-2.0-or-later
"""Schedule diagnostic peripherals in the selected clock domain.

Uses the published Z9 read-only clock interface. It never steps QEMU time.
Host deadlines and screen polling remain host time, even in virtual mode.
"""
import json
from pathlib import Path
import time


class InputClock:
    def __init__(self, guest, *, virtual=False):
        self.guest = guest
        self.virtual = virtual
        self.seconds = 0.0
        self.running = False
        self.next_diagnostic_sample = 0.0
        self.host_start = time.monotonic()
        self.record = dict(clock='QEMU_CLOCK_VIRTUAL' if virtual else 'host_monotonic',
                           samples=0, paused_samples=0, first_ns=None, last_ns=None,
                           time_stepped=False, missed_period_policy='drop; no catch-up burst',
                           recent_runtime_samples=[])
        guest.data['external_input_clock'] = self.record
        (guest.out/'zr_input_clock.py').write_bytes(Path(__file__).read_bytes())
        self.sample()

    def sample(self):
        if self.virtual:
            state = json.loads(self.guest.qmp.command('qom-get', path='/machine',
                                                     property='runtime-clock-state'))
            if state['qtest_accelerator']:
                raise ValueError('Native execution requires TCG, not the QTest accelerator')
            now = state['virtual_ns']
            self.running = state['running']
            host_now = time.monotonic()
            if host_now >= self.next_diagnostic_sample:
                self.record['recent_runtime_samples'].append(dict(
                    host_elapsed_seconds=host_now-self.host_start,
                    virtual_ns=now, running=self.running,
                    all_cpus_idle=state['all_cpus_idle'],
                    next_deadline_ns=state['next_deadline_ns']))
                del self.record['recent_runtime_samples'][:-64]
                self.next_diagnostic_sample = host_now+2
        else:
            now = time.monotonic_ns()
            self.running = True
        if self.record['last_ns'] is not None and now < self.record['last_ns']:
            raise ValueError('Input clock moved backwards; warm reset is unsupported')
        if self.record['first_ns'] is None:
            self.record['first_ns'] = now
        self.record['last_ns'] = now
        self.record['samples'] += 1
        self.record['paused_samples'] += not self.running
        self.seconds = now/1e9
