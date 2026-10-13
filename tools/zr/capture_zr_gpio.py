# SPDX-License-Identifier: GPL-2.0-or-later
"""Read the ZR's own GPIO tables; do not assign Z9 shutter semantics to pins."""
from pathlib import Path
import struct
from probe_zr_boot import MAIN, MAIN_SHA
from probe import sha
from probe_graphics_image import save


def capture(g):
    if sha(MAIN) != MAIN_SHA:
        raise ValueError('pinned ZR input changed')
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    # Independently disassembled ZR40e00370 /40e001f4 /40e161e8.
    # The candidate logical IDs come from Z9 and remain hypotheses until
    # the ZR initializer and native consumers are independently identified.
    table = int.from_bytes(save(g,'zr-gpio-logical-table-pointer',0xa02cc6ff0,8),'little')
    size = 0x29 * 4
    if not 0x40160000 <= table <= 0x40160000+MAIN.stat().st_size-size:
        raise ValueError('ZR logical table outside pinned file-backed ROM')
    with MAIN.open('rb') as stream:
        stream.seek(table-0x40160000)
        logical = stream.read(size)
    if len(logical) != size:
        raise ValueError('short ZR table read')
    rows = []
    for candidate in (0x23,0x24,0x27,0x28):
        index = struct.unpack_from('<I',logical,candidate*4)[0]
        if index >= 512:
            raise ValueError('ZR index outside bounded object table')
        label = f'zr-gpio-{candidate:02x}'
        pointer = int.from_bytes(save(g,label+'-pointer',0xa02cc6000+index*8,8),'little')
        descriptor = save(g,label+'-descriptor',pointer,0x28)
        bank,bit = struct.unpack_from('<II',descriptor,4)
        if bank >= 32 or bit >= 32:
            raise ValueError('unbounded ZR GPIO location')
        register = int.from_bytes(save(g,label+'-input',0xa02e611c0+bank*8,8),'little')
        irq = struct.unpack_from('<Q',descriptor,0x20)[0]
        row = dict(candidate_logical_id=hex(candidate),index=index,
            descriptor=hex(pointer),descriptor_hex=descriptor.hex(),bank=bank,bit=bit,
            input_register=hex(register),irq_descriptor=hex(irq))
        if irq:
            data = save(g,label+'-irq',irq,0x28)
            row.update(irq_descriptor_hex=data.hex(),irq_bank=struct.unpack_from('<I',data,4)[0],
                irq_bit=struct.unpack_from('<I',data,8)[0],intid=struct.unpack_from('<I',data,12)[0],
                isr=hex(struct.unpack_from('<Q',data,16)[0]),
                callback=hex(struct.unpack_from('<Q',data,24)[0]),
                mode=struct.unpack_from('<I',data,32)[0])
        rows.append(row)
    g.data['capture_gpio_candidates'] = dict(logical_table=hex(table),rows=rows,
        original_gpio_tables_observed=True,shutter_semantics_verified=False,
        external_inputs_applied=bool(g.data.get('capture_gpio_input',{}).get('inputs')))
    return rows


class ShutterInput:
    """Mirror explicit MCU contacts onto the independently observed ZR pins."""
    def __init__(self,g):
        self.g=g
        self.validated=False
        self.previous=0
        self.record=dict(inputs=[],gpio_bindings_checked=False,
            physical_timing_verified=False,capture_acceptance=False)
        g.data['capture_gpio_input']=self.record

    def apply(self,body,family):
        if family!=2:
            return
        if len(body)!=124 or body[7] not in (0,1) or body[8] not in (0,1):
            raise ValueError('complete binary shutter contact frame required')
        levels=body[7]|(body[8]<<1)
        if levels==self.previous:
            return
        if not self.validated:
            for row,bit,intid,isr in zip(capture(self.g)[:2],(4,5),(59,60),
                                       ('0x40e16770','0x40e16788')):
                if (row['bank'],row['bit'],row['input_register'],row['irq_bank'],
                    row['irq_bit'],row['intid'],row['isr'],row['callback'],row['mode']) != (
                    3,bit,'0xd15100c',0,bit,intid,isr,'0x411c6e8c',2):
                    raise ValueError('current ZR GPIO mapping differs from run240')
            self.validated=True
            self.record['gpio_bindings_checked']=True
        self.g.qmp.command('qom-set',path='/machine',property='capture-gpio-input',value=str(levels))
        self.previous=levels
        self.record['inputs'].append(dict(levels=levels))
