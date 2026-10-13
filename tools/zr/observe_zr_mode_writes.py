# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded original writes to ZR exposure-mode storage, with no RAM/PC edits."""
import json
from contextlib import contextmanager
from pathlib import Path
import re
import struct
import time

from observe_zr_startup import Observer as StartupObserver
from probe import sha
from probe_graphics_image import save
import zr_mode_write_watch as watch


class Observer(StartupObserver):
    def __init__(self, g, *, startup_points=True, **kwargs):
        if startup_points:
            super().__init__(g, **kwargs)
        else:
            self.g = g
            self.capture_phase = kwargs['phase']
            self.points = {}
            self.record = dict(source_sha256=sha(Path(__file__)),
                classification='original_mode_storage_write_observation',
                stops=[], remaining={})
            g.data[self.capture_phase+'_mode_write_observer'] = self.record
        self.pending_write = None
        self.watch_armed = False
        self.write_limit = 8
        self.property_id = g.data.get('mode_property_watch', '280c')
        self.address = {'280c':watch.ADDRESS, '2423':0xa03fea274}[self.property_id]
        self.converter_calls = 0
        self.converter_record_address = None
        if self.property_id == '2423' and startup_points:
            self.points[0x406d9a88] = 'mode_source_converter_entry'
            g.rsp('Z1,406d9a88,4')
        self.record.update(write_watch_property='0x'+self.property_id,
            write_watch_address=hex(self.address), write_watch_stops=[],
            write_watch_limit_per_phase=self.write_limit,
            write_watch_execution='GDB continue; original one-instruction step with observation removed',
            write_watch_scope='early/power/post and explicit frame-delivery windows')
        for file in ('observe_zr_mode_writes.py', 'zr_mode_write_watch.py', 'probe_adc_capture.py'):
            path = Path(__file__).with_name(file)
            (g.out/file).write_bytes(path.read_bytes())
            self.record.setdefault('write_watch_sources', {})[file] = sha(path)
        watch.enable(g, self.address)
        self.watch_armed = True

    def regs(self, cpu):
        if cpu not in range(4):
            raise ValueError('write stop CPU outside original four cores')
        return {k:int(v, 16) for k,v in re.findall(r'\b(X\d\d|PC|SP)=([0-9a-fA-F]+)',
            self.g.qmp.hmp('info registers', cpu))}

    def handle(self):
        stop = watch.query_stop(self.g)
        if self.pending_write is not None:
            row = self.pending_write
            regs = self.regs(row['stop']['cpu'])
            if stop['cpu'] != row['stop']['cpu'] or stop['write_address'] is not None or \
                    regs['PC'] != row['registers']['PC']+4:
                raise ValueError('watched store did not complete as one original instruction')
            prefix = f'zr-mode-write-{self.capture_phase}-{row["index"]:02d}'
            row.update(step_stop=stop, step_registers=regs,
                after_hex=save(self.g, prefix+'-after', self.address, 4).hex())
            self.pending_write = None
            with (self.g.out/'zr-mode-writes.partial.jsonl').open('a') as f:
                f.write(json.dumps(row)+'\n')
            if len(self.record['write_watch_stops']) < self.write_limit:
                watch.enable(self.g, self.address)
                self.watch_armed = True
            return True
        if stop['write_address'] != hex(self.address):
            first = len(self.record['stops'])
            handled = super().handle()
            for event in self.record['stops'][first:]:
                regs = event['registers']
                if event['name'] == 'mode_source_converter_entry':
                    self.converter_calls += 1
                    self.converter_record_address = regs['X01']
                    event.update(call_number=self.converter_calls, input_value=regs['X00']&0xffffffff,
                        original_caller=hex(regs['X30']),
                        record_before_hex=save(self.g,f'zr-mode-converter-{self.capture_phase}-{self.converter_calls:02d}-before',
                            regs['X01'],0x68).hex())
                    if regs['X30'] != 0x406ecefc or regs['X30'] in self.points:
                        raise ValueError('distinct original converter return required')
                    self.points[regs['X30']] = 'mode_source_converter_return'
                    self.g.rsp(f'Z1,{regs["X30"]:x},4')
                if event['name'] == 'mode_source_converter_return':
                    event.update(call_number=self.converter_calls, returned_value=regs['X00']&0xffffffff,
                        record_after_hex=save(self.g,f'zr-mode-converter-{self.capture_phase}-{self.converter_calls:02d}-after',
                            self.converter_record_address,0x68).hex())
                    if self.converter_calls < 8:
                        self.points[0x406d9a88] = 'mode_source_converter_entry'
                        self.g.rsp('Z1,406d9a88,4')
            return handled
        if not self.watch_armed:
            raise ValueError('unexpected write observation while disabled')
        regs = self.regs(stop['cpu'])
        if regs['PC'] & 3:
            raise ValueError('aligned original instruction required')
        watch.disable(self.g)
        self.watch_armed = False
        index = len(self.record['write_watch_stops'])
        prefix = f'zr-mode-write-{self.capture_phase}-{index:02d}'
        row = dict(index=index, phase=self.capture_phase, stop=stop, registers=regs,
            before_hex=save(self.g, prefix+'-before', self.address, 4).hex())
        end = 0xa00000000+self.g.ram_mib*1024*1024
        if 0xa00000000 <= regs['SP'] <= end-0x200:
            stack = save(self.g, prefix+'-stack', regs['SP'], 0x200)
            row['stack_hex'] = stack.hex()
            if regs['PC'] == 0x41206334 and regs['X30'] == 0x4120356c:
                count = regs['X20'] & 0xffffffff
                if not 1 <= count <= 256:
                    raise ValueError('bounded original batch property count required')
                ids = save(self.g, prefix+'-batch-ids', regs['X22'], count*4)
                values = save(self.g, prefix+'-batch-values', regs['X21'], count*4)
                row['batch_input'] = dict(count=count, ids_address=hex(regs['X22']),
                    values_address=hex(regs['X21']), ids_hex=ids.hex(), values_hex=values.hex())
                # 41203520 saves its caller's x24/x20/x19/x30 at these
                # exact offsets. 406ecfd4 reaches it via 406d9960.
                parent = {name:struct.unpack_from('<Q', stack, off)[0] for name,off in
                    (('x24',0x18),('x20',0x38),('x19',0x40),('x30',0x48))}
                row['batch_input']['caller_saved_registers'] = {k:hex(v) for k,v in parent.items()}
                if parent['x30'] == 0x406ecfd8:
                    if parent['x19'] != 0x68 or not 1 <= parent['x20'] <= 2048:
                        raise ValueError('bounded original producer table required')
                    table = save(self.g, prefix+'-producer-table', parent['x24'], parent['x20']*0x68)
                    row['batch_input']['producer_table'] = dict(address=hex(parent['x24']),
                        entries=parent['x20'], stride=0x68, file=prefix+'-producer-table.bin',
                        sha256=sha(self.g.out/(prefix+'-producer-table.bin')),
                        property280c_records=[dict(index=i, raw_hex=table[i*0x68:(i+1)*0x68].hex())
                            for i in range(parent['x20']) if struct.unpack_from('<I',table,i*0x68+0x38)[0]==0x280c])
        else:
            row['stack_scope'] = 'stack outside modeled work RAM; not captured'
        self.record['write_watch_stops'].append(row)
        self.pending_write = row
        watch.step(self.g, stop['thread'])
        return True

    def close(self):
        try:
            # The host time window can end with an observed store still
            # pending. Finish exactly that original instruction before
            # restoring the normal continuation transport.
            if self.pending_write is None or not hasattr(self.g, 'mode_watch_next_resume'):
                self.handle()
            if self.pending_write is not None:
                if hasattr(self.g, 'mode_watch_next_resume'):
                    self.g.qmp.command('cont')
                deadline = time.monotonic()+3
                while self.g.qmp.command('query-status')['running']:
                    if time.monotonic() > deadline:
                        self.g.qmp.command('stop')
                        raise TimeoutError('pending original mode store step')
                    time.sleep(.005)
                self.handle()
            self.record['write_watch_pending_at_end'] = self.pending_write is not None
        finally:
            if self.watch_armed:
                watch.disable(self.g)
                self.watch_armed = False
            watch.restore(self.g)
            super().close()


@contextmanager
def delivery_window(g, phase):
    """Use the shared at() helper's existing optional debug-stop observer."""
    if hasattr(g, 'early_shutdown_observer'):
        raise ValueError('delivery debug-stop observer already owned')
    observer = Observer(g, startup_points=False, phase=phase)
    g.early_shutdown_observer = observer
    try:
        yield
    finally:
        del g.early_shutdown_observer
        observer.close()
