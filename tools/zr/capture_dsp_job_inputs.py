# SPDX-License-Identifier: GPL-2.0-or-later
"""Read a stopped original DSP1 image request; no work/result/guest writes.

The two pinned ARM constructors define a d0-byte request and 834-byte
result region. Field semantics beyond geometry and owned spans remain open.
In particular, opcode1b is not established as a stream STOP command.
"""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib

FIRMWARE = '9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f'
CONFIG_BYTES = 0xd0
RESULT_BYTES = 0x834
WORKSPACE_BYTES = 0x44e00
MAX_INPUT_BYTES = 8 * 1024 * 1024


def ram_address(local, size, ram_bytes, window):
    if (not isinstance(window, list) or len(window) != 3 or
            ram_bytes not in (512 * 1024**2, 1024**3) or
            window[:2] != [0x40000000, (1 << 36) - ram_bytes] or
            window[2] not in (0, 0x200000000) or
            type(local) is not int or not 0x40000000 <= local <= 0xffffffff or
            type(size) is not int or not 0 < size <= ram_bytes or
            local - 0x40000000 > ram_bytes - size):
        raise ValueError('Complete request must remain in the explicit DSP work RAM aperture')
    return 0xa00000000 + local - 0x40000000


def pending_request(interface, ram_mib):
    if not interface.get('session_initialization_enabled') or interface.get('dsp_arithmetic_executed'):
        raise ValueError('Functional initialization and unexecuted image job required')
    channel = interface['channels'][1]
    slots = [s for s in channel['tx_slots'] if s['claim']]
    if len(slots) != 1:
        raise ValueError('Unambiguous owned pending DSP1 request required')
    slot = slots[0]
    words = slot['words']
    if (slot['written_mask'] != 0xf or slot['route'] != 3 or slot['destination'] != 0x10 or
            len(words) != 16 or words[0] != 0x1a or words[3] not in (0, 1) or
            channel['init_requests'] != 1 or channel['init_completed'] != 1 or
            not channel['init_configured']):
        raise ValueError('Pinned complete opcode1a after actual workspace initialization required')
    ram = ram_mib * 1024**2
    window = channel['init_debug_window']
    if not isinstance(window, list) or len(window) != 3:
        raise ValueError('Complete current rejected-request window snapshot required')
    return dict(opcode=words[0], group=words[3], slot=slot['slot'],
        config=ram_address(words[1], CONFIG_BYTES, ram, window),
        result=ram_address(words[2], RESULT_BYTES, ram, window),
        ram_bytes=ram, window=window, initialized_workspace=channel['init_workspace'])


def decode_config(raw, request):
    if len(raw) != CONFIG_BYTES:
        raise ValueError('Complete original request configuration required')
    pointer = lambda offset: struct.unpack_from('<Q', raw, offset)[0]
    word = lambda offset: struct.unpack_from('<I', raw, offset)[0]
    width, height, pitch = word(8), word(12), word(16)
    amount = pitch * height
    if (not 0 < width <= 8192 or not 0 < height <= 8192 or
            not width <= pitch <= 65536 or not 0 < amount <= MAX_INPUT_BYTES or
            word(0x14) or pointer(0x20) != WORKSPACE_BYTES):
        raise ValueError('Bounded original geometry, reserved word and workspace length required')
    ram, window = request['ram_bytes'], request['window']
    source = ram_address(pointer(0), amount, ram, window)
    workspace = ram_address(pointer(0x18), WORKSPACE_BYTES, ram, window)
    if workspace != request['initialized_workspace']:
        raise ValueError('Request must use its actually initialized workspace')
    spans = dict(config=(request['config'], CONFIG_BYTES), input=(source, amount),
        workspace=(workspace, WORKSPACE_BYTES), result=(request['result'], RESULT_BYTES))
    values = list(spans.items())
    for i, (name, (address, size)) in enumerate(values):
        for other, (start, length) in values[i+1:]:
            if address < start + length and start < address + size:
                raise ValueError('Original request ownership spans overlap: ' + name + '/' + other)
    return dict(width=width, height=height, pitch_field=pitch,
        input_capture_bytes=amount, spans=spans,
        pixel_format_verified=False, stride_unit_verified=False,
        scope='Raw source bytes spanning the reported pitch times height; '
              'pixel format and pitch unit require producer/consumer proof')


def byte_summary(raw):
    histogram = [0] * 256
    for value in raw:
        histogram[value] += 1
    return dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), crc32=zlib.crc32(raw),
        nonzero_bytes=len(raw) - histogram[0], distinct_byte_values=sum(bool(n) for n in histogram),
        minimum=min(raw) if raw else None, maximum=max(raw) if raw else None,
        byte_histogram=histogram)


def capture(guest):
    """Owned QEMU is already stopped by ZRGuest.__exit__; read RAM only."""
    if guest.data.get('main_sha256') != FIRMWARE:
        raise ValueError('Pinned original ZR input required')
    request = pending_request(guest.data['dsp_boot_mailbox_final'], guest.ram_mib)
    config = guest.read_bytes(request['config'], CONFIG_BYTES)
    decoded = decode_config(config, request)
    captures = {}
    for label, (address, amount) in decoded['spans'].items():
        runtime = guest.runtime / ('dsp-request1a-' + label + '.bin')
        archive = guest.out / runtime.name
        if runtime.exists() or archive.exists():
            raise ValueError('Fresh owned readback destination required')
        response = guest.qmp.hmp(f'pmemsave {address:#x} {amount:#x} "{runtime}"')
        if response.strip() or runtime.stat().st_size != amount:
            raise ValueError('Bounded actual DSP input RAM capture failed')
        raw = runtime.read_bytes()
        if label == 'config' and raw != config:
            raise ValueError('Stopped source configuration changed between reads')
        shutil.copyfile(runtime, archive)
        captures[label] = dict(address=hex(address), file=archive.name, **byte_summary(raw))
    receipt = dict(classification='system_emulated_observation', pending_request=request,
        geometry={k: v for k, v in decoded.items() if k != 'spans'}, captures=captures,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        dsp_job_executed=False, result_produced_by_model=False, camera_recording_accepted=False,
        scope='Read-only original pending job data from its stopped owned guest; '
              'no memory writes, MMIO completion, callback invocation or CPU changes')
    (guest.out / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    guest.data['dsp_source_input_capture'] = receipt
    print(json.dumps(dict(dsp_input_captured=True, width=decoded['width'], height=decoded['height'],
        pitch_field=decoded['pitch_field'], input_bytes=captures['input']['bytes'],
        input_nonzero_bytes=captures['input']['nonzero_bytes'], dsp_job_executed=False)), flush=True)
    return receipt
