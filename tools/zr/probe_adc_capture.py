# SPDX-License-Identifier: GPL-2.0-or-later
"""Follow four ordinary Z9 ADC scans through original ISR and consumers.

No CPU-register redirection or guest RAM patches. Hardware breakpoints observe
original flow; QOM supplies explicit synthetic peripheral inputs before each
start. Four-core boot uses the documented other bring-up fixtures.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import time
from contract_guest import ContractGuest
from probe import sha
from probe_graphics_image import FIXTURES, save
from check_adc import BASE, state

START, ISR, CALLBACK, CONSUMER = 0x40c13eb4, 0x40c13d14, 0x40ca5cd8, 0x40c8f938
SAMPLES = [(256,512,768,1023), (100,900,200,300), (300,700,200,400), (500,600,100,200)]


def at(g, pc, *, preferred_x19=None):
    g.rsp(f'Z1,{pc:x},4')
    deadline = time.monotonic() + 30
    expired = False
    while True:
        g.qmp.command('cont')
        while g.qmp.command('query-status')['running']:
            if time.monotonic() >= deadline:
                g.qmp.command('stop')
                expired = True
                break
            time.sleep(.01)
        early = getattr(g,'early_shutdown_observer',None)
        handled = early.handle() if early and not expired and 'Z9_UNKNOWN' not in g.log() else False
        states = [g.qmp.hmp('info registers',cpu) for cpu in range(4)]
        wanted = any(int(re.search(r'\bPC=([0-9a-fA-F]+)',s)[1],16)==pc for s in states)
        if wanted or not handled or expired:
            break
    g.data.setdefault('stops', []).append(dict(expected_pc=hex(pc), timeout=expired, registers=states))
    if expired:
        raise TimeoutError('native ADC breakpoint ' + hex(pc))
    matches = []
    for cpu, text in enumerate(states):
        regs = {k: int(v, 16) for k, v in re.findall(r'\b(X\d\d|PC|SP)=([0-9a-fA-F]+)', text)}
        if regs['PC'] == pc:
            matches.append((cpu, regs))
    if preferred_x19 is not None:
        selected = [(cpu, regs) for cpu, regs in matches if regs['X19'] == preferred_x19]
        if selected:
            # Concurrent channels may stop at the same shared PIO instruction.
            # Preserve all CPU states above, then select the actual channel
            # object; two hits for that SAME object remain ambiguous.
            g.data['stops'][-1]['preferred_x19'] = hex(preferred_x19)
            g.data['stops'][-1]['matching_cpus'] = [cpu for cpu, _ in selected]
            matches = selected
    if len(matches) != 1 or 'Z9_UNKNOWN' in g.log():
        raise RuntimeError('expected unique ADC stop without unknown MMIO')
    g.rsp(f'z1,{pc:x},4')
    return matches[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--name', required=True)
    args = ap.parse_args()
    g = ContractGuest(args.name, FIXTURES+',graphics-image-model=on,adc-fixture=on', intercept_irq=False)
    g.command[g.command.index('-smp')+1] = '4'
    with g:
        g.data.update(source_sha256=sha(Path(__file__)), classification='system_emulated_synthetic_adc',
                      diagnostic='Original four-core boot, read-only hardware breakpoints; QOM synthetic ADC inputs',
                      cpu_register_redirection=False, ram_patches=[], physical_units_known=False, scans=[])
        g.rsp('z1,40160000,4')
        for index, inputs in enumerate(SAMPLES):
            cpu, regs = at(g, START)
            g.check(f'scan {index+1}: original two-channel powered start',
                    regs['X09'] == 0x303 and regs['X30'] == 0x40ca5c8c and
                    state(g)['conversions'] == index)
            before = state(g)
            g.qmp.command('qom-set', path='/machine', property='adc-input', value=':'.join(map(str, inputs)))
            irq_cpu, irq = at(g, ISR)
            pending = state(g)
            g.check(f'scan {index+1}: original ISR sees actual latched synthetic data',
                    pending['conversions'] == index+1 and pending['samples'] == list(inputs[:2])+[0,0] and
                    pending['status'] == 0x38 and pending['control'] == 0x203)
            callback_cpu, callback = at(g, CALLBACK)
            g.check(f'scan {index+1}: original ISR acknowledges and invokes registered callback',
                    state(g)['status'] == 0x30 and callback['X00'] == 0x41212c01 and
                    callback['X01'] == 8 and callback_cpu == irq_cpu)
            consumer_cpu, consumer = at(g, CONSUMER)
            values = save(g, f'scan-{index+1}-consumer-input', consumer['X20'], 10)
            g.check(f'scan {index+1}: original upper consumer receives selected readings',
                    struct.unpack('<5H', values) == (3,inputs[0],inputs[1],0,0))
            averages = save(g, f'scan-{index+1}-averages', 0xa02e803f4, 24)
            observed = [struct.unpack_from('<H', averages, i*12+10)[0] for i in range(2)]
            expected = list(SAMPLES[0][:2]) if index < 3 else [sum(x[i] for x in SAMPLES)//4 for i in range(2)]
            g.check(f'scan {index+1}: original four-sample accumulation/average', observed == expected)
            g.data['scans'].append(dict(inputs=inputs, before=before, pending=pending,
                                        start_cpu=cpu, irq_cpu=irq_cpu, consumer_cpu=consumer_cpu,
                                        expected_averages=expected, actual_averages=observed))
        g.check('all scans pass without unknown MMIO', 'Z9_UNKNOWN' not in g.log())
        g.data['final_state'] = state(g)


if __name__ == '__main__':
    main()
