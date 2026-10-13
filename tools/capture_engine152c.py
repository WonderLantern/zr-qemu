# SPDX-License-Identifier: GPL-2.0-or-later
"""Read the original Z9 RAW receiver binding; never provide data or flags."""
import json
from pathlib import Path
import struct


CONTEXT = 0xa02f46830


def observe(g, registers, label):
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    def ram(address, size):
        if not 0xa00000000 <= address <= 0xa40000000-size:
            raise ValueError('Original RAW receiver argument outside actual work RAM')
        return g.read_bytes(address, size)

    row = dict(scope='read-only original Z9 C5.32 receiver/notification; no supplied pixels, CPU registers or RTOS flags',
               configuration=json.loads(g.qmp.command('qom-get', path='/machine', property='engine152c-config-state')),
               request=json.loads(g.qmp.command('qom-get', path='/machine', property='engine152c-request-state')))
    if label.endswith(('completion_notice', 'start_notice')):
        row.update(event=hex(registers['X00'] & 0xffffffff), argument=hex(registers['X01']),
                   scope='original event notification, not a pixel supplier or a RAM pointer')
        return row
    if label.endswith('receiver_armed'):
        if registers['PC'] != 0x40cc00b8 or registers['X19'] != CONTEXT:
            raise ValueError('Original RAW receiver context differs from fingerprinted routine')
        context = ram(CONTEXT, 0x2e8)
        driver, _, notice = struct.unpack_from('<3Q', context, 0x2c0)
        job = registers['X20']
        raw_job = ram(job, 0x38)
        request = struct.unpack_from('<Q', raw_job, 0x28)[0]
        row.update(context_address=hex(CONTEXT), context_hex=context.hex(),
                   driver_address=hex(driver), start_notice_callback=hex(notice),
                   job_address=hex(job), job_hex=raw_job.hex(),
                   request_address=hex(request), request_hex=ram(request, 0xf0).hex())
        if notice and not (0x40160000 <= notice < 0x41600000 and notice & 3 == 0):
            raise ValueError('RAW start notification outside original executable prefix')
        return row
    pointer = registers['X00']
    row.update(argument_address=hex(pointer), argument_hex=ram(pointer, 0xf0).hex())
    return row
