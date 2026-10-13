# SPDX-License-Identifier: GPL-2.0-or-later
"""Z9 four-channel converter contract, explicit synthetic inputs only.

Native getters/start/ISR execute, but CPU calls and RAM setup are diagnostic.
Physical ADC units, analog timing, continuous and external-trigger modes are
not implemented. Ordinary native integration is a separate capture probe.
"""
import argparse
import json
from pathlib import Path
from contract_guest import ContractGuest
from probe import sha

BASE = 0x0e002000
IRQ = 0xde - 32
PROPS = ',bootstrap-fixtures=on,adc-fixture=on'
INPUT = ':'.join(map(str, (101, 303, 707, 1023)))


def state(g):
    return json.loads(g.qmp.command('qom-get', path='/machine', property='adc-state'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--name', required=True)
    args = ap.parse_args()
    with ContractGuest(args.name, PROPS+',adc-input='+INPUT) as g:
        g.data.update(source_sha256=sha(Path(__file__)), synthetic_input=True, cases=[])
        g.check('reset has no samples, completion or IRQ',
                g.rd(BASE+0xc) == 0 and [g.rd(BASE+0x10+i*4) for i in range(4)] == [0]*4 and
                state(g)['conversions'] == 0 and not any(g.irq.values()))
        g.wr(BASE, 0x203)
        g.call(0x40c13f24, 0, 0x123)
        g.call(0x40c13f64, 0, 0x456)
        g.call(0x40c13f80, 0, 0xabc)
        g.check('native configuration masks sampling byte and ten-bit thresholds',
                g.rd(BASE+8) == 0x23 and g.rd(BASE+0x40) == 0x56 and g.rd(BASE+0x44) == 0x2bc)
        g.call(0x40c13e9c, 0)
        g.check('masked scan latches only selected channels and clears start',
                g.rd(BASE) == 0x203 and g.rd(BASE+0xc) == 0x38 and
                [g.rd(BASE+0x10+i*4) for i in range(4)] == [101,303,0,0] and not g.irq.get(IRQ, False))
        g.call(0x40c13e78, 0, 0x1000)
        g.check('unmasking retained completion asserts converter IRQ',
                g.rd(BASE+8) == 0x1023 and g.irq.get(IRQ, False))
        g.wr(BASE+0xc, 0xe)
        g.check('writing ones preserves pending instead of W1C', g.rd(BASE+0xc) == 0x38 and g.irq.get(IRQ, False))
        # The original descriptor callback is deliberately null for this
        # direct ISR test; full boot tests the real registered callback.
        g.write_bytes(0xa02808770, bytes(8))
        g.call(0x40c13d14)
        g.check('original ISR W0C clears completion and lowers IRQ', g.rd(BASE+0xc) == 0x30 and not g.irq.get(IRQ, False))
        g.wr(BASE+0xc, 0xff)
        g.check('status writes cannot synthesize pending or channel bits', g.rd(BASE+0xc) == 0x30)
        g.qmp.command('qom-set', path='/machine', property='adc-input', value='12:34:56:78')
        g.check('changing external source does not change latched samples',
                [g.rd(BASE+0x10+i*4) for i in range(4)] == [101,303,0,0])
        g.call(0x40c13e58, 0, 0xc)
        g.call(0x40c13e9c, 0)
        g.check('next scan uses new source and preserves unselected results',
                [g.rd(BASE+0x10+i*4) for i in range(4)] == [101,303,56,78] and g.rd(BASE+0xc) == 0xc8)
        out = 0xa00010000
        for channel, expected in enumerate((101,303,56,78)):
            g.write_bytes(out-1, b'\xa5\xcc\xcc\x5a')
            g.call(0x40c13ef0, 0, channel, out)
            g.check(f'native channel {channel} copies exact 16-bit result within guards',
                    g.read_bytes(out-1, 4) == b'\xa5'+expected.to_bytes(2,'little')+b'\x5a')
        g.write_bytes(out, b'\xcc\xcc')
        g.call(0x40c13ef0, 0, 4, out)
        g.check('native out-of-range channel leaves destination unchanged', g.read_bytes(out, 2) == b'\xcc\xcc')
        g.call(0x40c13fc0, 0, out)
        g.check('synchronous complete is no longer busy', g.read_bytes(out, 4) == bytes(4))
        g.call(0x40c13fe0, 0, out)
        g.check('native completion bitmap getter', g.read_bytes(out, 1) == b'\x0c')
        g.call(0x40c13d14)
        for invalid in ('1:2:3', '1:2:3:1024', '1:2:3:-1', '1:2:3:4:5', '1:2:3:4x'):
            try:
                g.qmp.command('qom-set', path='/machine', property='adc-input', value=invalid)
            except RuntimeError as exc:
                rejected = True
                g.data['cases'].append(dict(invalid_input=invalid, error=str(exc)))
            else:
                rejected = False
            g.check('invalid input is rejected: '+invalid, rejected)
        g.wr(BASE, 0x20f)
        g.call(0x40c13e9c, 0)
        g.check('rejected input leaves prior source intact',
                [g.rd(BASE+0x10+i*4) for i in range(4)] == [12,34,56,78])
        g.call(0x40c13d14)
        g.wr(BASE, 0)
        g.check('power off and source changes do not create another scan',
                state(g)['conversions'] == 3 and g.rd(BASE+0xc) == 0xf0 and not g.irq.get(IRQ, False))
        g.check('no unknown MMIO in supported native contract', 'Z9_UNKNOWN' not in g.log())
        g.data['final_state'] = state(g)
    negatives = [
        ('disabled', ',bootstrap-fixtures=on', [], 'readl 0xe002000'),
        ('width', PROPS, [], 'readw 0xe002000'),
        ('input-missing', PROPS, [(0,0x203)], 'writel 0xe002000 0x303'),
        ('power-missing', PROPS+',adc-input='+INPUT, [], 'writel 0xe002000 0x103'),
        ('empty-selection', PROPS+',adc-input='+INPUT, [], 'writel 0xe002000 0x300'),
        ('continuous', PROPS+',adc-input='+INPUT, [], 'writel 0xe002000 0x4303'),
        ('external-trigger', PROPS+',adc-input='+INPUT, [(8,0x100)], 'writel 0xe002000 0x303'),
        ('control-reserved', PROPS, [], 'writel 0xe002000 0x8000'),
        ('config-reserved', PROPS, [], 'writel 0xe002008 0x2000'),
        ('data-write', PROPS, [], 'writel 0xe002010 123'),
        ('neighbor', PROPS, [], 'readl 0xe002020'),
    ]
    for label, props, setup, command in negatives:
        with ContractGuest(args.name+'-'+label, props) as g:
            g.data['source_sha256'] = sha(Path(__file__))
            for off,value in setup:
                g.wr(BASE+off,value)
            before = state(g)
            g.qt_command(command)
            g.check(label+': unknown transaction at exact address',
                    g.log().count('Z9_UNKNOWN') == 1 and
                    f'addr=0x{int(command.split()[1],0):x} ' in g.log())
            g.check(label+': no state transition, sample or IRQ', state(g) == before and not any(g.irq.values()))


if __name__ == '__main__':
    main()
