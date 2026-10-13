# SPDX-License-Identifier: GPL-2.0-or-later
"""Capture the actual pending DSP0 correction parameter window, read-only.

The 4-KiB observation bound is not a claim about TCpc/TVslc structure size.
No initialization, processing result, guest write or callback is supplied.
"""
import hashlib
import json
from pathlib import Path
import shutil
import struct

from capture_dsp_job_inputs import FIRMWARE, ram_address, byte_summary

OBSERVATION_BYTES = 4096


def pending_request(interface, ram_mib):
    if not interface.get('session_initialization_enabled') or interface.get('dsp_arithmetic_executed'):
        raise ValueError('Explicit functional startup without original DSP execution required')
    channel = interface['channels'][0]
    slots = [slot for slot in channel['tx_slots'] if slot['claim']]
    if len(slots) != 1:
        raise ValueError('One actually owned pending DSP0 correction request required')
    slot = slots[0]
    words = slot['words']
    if (slot['written_mask'] != 15 or slot['route'] != 3 or slot['destination'] != 16 or
            len(words) != 16 or words[0] not in (0, 2) or words[2:] != [0] * 14 or
            channel['reset_held'] or not channel['booted']):
        raise ValueError('Complete original bounded initialization request required')
    address = ram_address(words[1], OBSERVATION_BYTES, ram_mib * 1024**2,
                          channel['init_debug_window'])
    return dict(channel=0, opcode=words[0], slot=slot['slot'],
                wire_words=words[:4], parameter=address,
                observation_bytes=OBSERVATION_BYTES,
                aperture=channel['init_debug_window'])


def capture(guest):
    if guest.data.get('main_sha256') != FIRMWARE:
        raise ValueError('Fingerprint-bound original ZR guest required')
    owned = [slot for slot in guest.data['dsp_boot_mailbox_final']['channels'][0]['tx_slots']
             if slot['claim']]
    if not owned:
        guest.data['dsp_correction_input_observation'] = dict(
            pending_request=False,
            scope='Owned guest stopped at another boundary; no DSP0 parameter read attempted')
        print(json.dumps(dict(dsp0_correction_pending=False)), flush=True)
        return None
    request = pending_request(guest.data['dsp_boot_mailbox_final'], guest.ram_mib)
    name = 'dsp0-correction-' + str(request['opcode']) + '-parameter-private.bin'
    runtime, archive = guest.runtime / name, guest.out / name
    if runtime.exists() or archive.exists():
        raise ValueError('Fresh stopped owned readback destination required')
    before = guest.read_bytes(request['parameter'], OBSERVATION_BYTES)
    response = guest.qmp.hmp(f'pmemsave {request["parameter"]:#x} {OBSERVATION_BYTES:#x} "{runtime}"')
    if response.strip() or runtime.stat().st_size != OBSERVATION_BYTES or runtime.read_bytes() != before:
        raise ValueError('Complete stable original parameter RAM readback required')
    shutil.copyfile(runtime, archive)
    receipt = dict(classification='system_emulated_observation', pending_request=request,
                   file=archive.name, **byte_summary(before),
                   tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   parameter_structure_bytes_verified=False, pointed_workspaces_captured=False,
                   initialization_executed=False, original_dsp_execution=False,
                   recording_accepted=False,
                   scope='Read-only bounded parameter window from the stopped owned pending '
                         'DSP0 request. No structure-size, nested-pointer ownership, initialization '
                         'result, algorithm execution or recording claim.')
    if request['opcode'] == 0 and struct.unpack_from('<I', before, 40)[0] == 1504:
        local = struct.unpack_from('<Q', before)[0]
        address = ram_address(local, 1504, guest.ram_mib * 1024**2, request['aperture'])
        if address < request['parameter'] + OBSERVATION_BYTES and request['parameter'] < address + 1504:
            raise ValueError('Actual CPC calibration DMA must not alias its parameter window')
        content = guest.read_bytes(address, 1504)
        nested = guest.out / 'dsp0-cpc-calibration-private.bin'
        with nested.open('xb') as stream:
            stream.write(content)
        receipt['calibration_capture'] = dict(file=nested.name, address=hex(address),
                                              count_field=struct.unpack_from('<H', content)[0],
                                              **byte_summary(content))
        receipt['pointed_workspaces_captured'] = True
    (guest.out / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    guest.data['dsp_correction_input_capture'] = receipt
    print(json.dumps(dict(dsp0_correction_input_captured=True, opcode=request['opcode'],
                          bytes=OBSERVATION_BYTES, sha256=receipt['sha256'],
                          initialization_executed=False)), flush=True)
    return receipt
