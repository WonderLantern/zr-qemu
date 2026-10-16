# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded, read-only snapshots of submitted source DMA addresses.

This uses device configuration, not firmware code addresses. A register pair
is only an address slot: neither its pixel format nor its ownership is inferred
from its pitch. The caller must already have stopped its owned guest.
"""
import hashlib
import json
from pathlib import Path

PLANE_LIMIT = 2 * 1024**2
SNAPSHOT_LIMIT = 32 * 1024**2
MAX_SNAPSHOTS = 20
PREFIX_BYTES = 4096


def finite_preview_input_plan(state):
    """Whole submitted A1 image-RAM input, separate from producer ownership."""
    blocks=[b for b in state.get('blocks',[]) if b.get('base')==0x15421100]
    if len(blocks)!=1:return []
    config=blocks[0].get('config',{})
    def word(offset):return config.get(hex(offset),0)
    if word(4) not in (0x3800,0x3801,0x3802) or word(12) not in (0x31000000,0x31000200):return []
    width,height,stride=word(0x4c),word(0x50),word(0x38)
    bits=8 if word(12)==0x31000000 else 10
    minimum=((width+3)&~3) if bits==8 else (width+2)//3*4
    if (not width or not height or (width|height)&1 or width>8192 or height>8192
            or stride<minimum or stride>32768 or stride&3 or word(0x3c)!=stride):return []
    rows=[]
    for plane in range(2):
        low,high=word(0x20+plane*8),word(0x24+plane*8)
        address=low|(high<<32);length=stride*height//(2 if plane else 1)
        entry=dict(identity='finite-a1-'+('uv' if plane else 'y'),plane=plane,address=hex(address),
            bytes=length,requested_bytes=length,truncated=False,width=width,height=height,stride=stride,
            source_format_raw=word(12),functional_storage_bits=bits,format_proven=False,
            current_ownership_proven=False,extent_basis='complete-submitted-finite-A1-NV12-plane')
        if high>15 or not 0<length<=16*1024**2 or not 0x800000000<=address<=0x900000000-length:
            entry['skip']='invalid-or-unbounded-image-RAM-input'
        rows.append(entry)
    return rows


def main_transfer_plan(state):
    """Two complete planes of one produced functional main view, frozen guest."""
    surfaces=[(index,row) for index,row in enumerate(state.get('surfaces',[]))
              if row.get('epoch') and (row.get('valid') or row.get('leased'))]
    if not state.get('enabled') or not surfaces:
        return []
    index,row=max(surfaces,key=lambda item:(item[1]['leased'],item[1]['epoch']))
    stride,height=row['stride'],row['storage_height']
    stored=row.get('stored_bytes') if row.get('transported') else None
    total=sum(stored) if stored else stride*height*3//2
    if total>SNAPSHOT_LIMIT or not stride or not height:
        return [dict(identity='main-frame',skip='whole-main-frame-byte-limit',requested_bytes=total)]
    result=[]
    for plane in range(2):
        address=row['physical'][plane]
        length=stored[plane] if stored else stride*height//(2 if plane else 1)
        entry=dict(identity='main-'+('uv' if plane else 'y'),plane=plane,surface=index,
            address=hex(address),bytes=length,requested_bytes=length,truncated=False,
            width=row['width'],height=row['height'],storage_height=height,stride=stride,
            epoch=row['epoch'],source_format=row.get('source_format',0x332),format_proven=False,
            extent_basis='complete-produced-functional-main-plane',functional_format_declared=True,
            transported=bool(stored),logical_bytes=stride*height//(2 if plane else 1))
        if not 0x800000000<=address<=0x900000000-length:
            entry['skip']='outside-image-ram'
        result.append(entry)
    return result


def capture_plan(state):
    """Return bounded image-RAM reads and explicit reasons for skipped slots."""
    rows = []
    for instance in (0, 2):
        config = state['instances'][instance]['config']
        if len(config) < 0x2000 // 4:
            raise ValueError('Complete source register bank required')
        geometry = config[0x80 // 4]
        height = (geometry >> 16) & 0x7fff
        for bank in range(2):
            for row in range(4):
                for slot in range(5):
                    offset = bank * 0x1000 + row * 0x400 + 0x100 + slot * 8
                    lo, hi = config[offset // 4:offset // 4 + 2]
                    address = lo | ((hi & 15) << 32)
                    stride = config[(0x88 + slot * 4) // 4] if slot < 2 else None
                    requested = stride * height if stride and height else PREFIX_BYTES
                    length = min(requested, PLANE_LIMIT) if slot < 2 else PREFIX_BYTES
                    entry = dict(instance=instance, bank=bank, row=row, slot=slot,
                        register=hex(offset), address=hex(address), address_high_raw=hi,
                        geometry_raw=geometry, stride_raw=stride,
                        requested_bytes=requested, bytes=length,
                        extent_basis='stride-times-height' if stride and height else 'prefix',
                        truncated=requested > length, format_proven=False)
                    if not 0x800000000 <= address <= 0x900000000 - length:
                        entry['skip'] = 'outside-image-ram'
                    rows.append(entry)
    return rows


def completed_transfer_plan(state):
    """Read the last completed model transfer, with its latched geometry.

    These spans can have been reused since completion. They are evidence to
    compare, not a claim that the model still owns their contents.
    """
    if not state.get('enabled') or not state.get('jobs'):
        return []
    width, height = state['width'], state['height']
    pitch, rgb_pitch = state['pitch'], state['rgb_pitch']
    if (not 0 < width <= 2048 or not 0 < height <= 2048 or width & 1 or
            not width * 3 // 2 <= pitch <= 8192 or
            not width * 9 // 2 <= rgb_pitch <= 16384):
        raise ValueError('Invalid completed source transfer geometry')
    rows = []
    for plane, stride in (('y', pitch), ('uv', pitch), ('rgb', rgb_pitch)):
        address, requested = state[plane], stride * height
        length = min(requested, PLANE_LIMIT)
        entry = dict(identity='completed-' + plane, plane=plane,
            address=hex(address), bytes=length, requested_bytes=requested,
            truncated=requested > length, width=width, height=height,
            stride_raw=stride, epoch=state['epoch'], jobs=state['jobs'],
            extent_basis='last-completed-model-transfer', format_proven=False,
            current_ownership_proven=False)
        if not 0x800000000 <= address <= 0x900000000 - length:
            entry['skip'] = 'outside-image-ram'
        rows.append(entry)
    return rows


def capture(guest, stage, phase):
    records = guest.data.setdefault('video_source_ram_snapshots', [])
    if len(records) >= MAX_SNAPSHOTS:
        return
    label = f'video-source-ram-{stage:03d}-{phase}'
    if any(record['label'] == label for record in records):
        return
    guest_status = guest.qmp.command('query-status')
    if (guest_status.get('running') is not False or
            guest_status.get('status') not in ('paused', 'debug', 'prelaunch')):
        raise ValueError('Read-only source capture requires an already stopped guest')
    source = Path(__file__)
    archived = guest.out / source.name
    if not archived.exists():
        archived.write_bytes(source.read_bytes())
    record = dict(label=label, stage=stage, phase=phase, read_only=True, guest_status=guest_status,
        source_sha256=hashlib.sha256(archived.read_bytes()).hexdigest(),
        main_sha256=guest.data['main_sha256'], qemu_sha256=guest.data['qemu_sha256'],
        byte_limit=SNAPSHOT_LIMIT, saved_bytes=0, device_states={}, reads=[],
        scope='Paused submitted address slots; format, producer ownership and native consumption not inferred')
    records.append(record)
    old_timeout = guest.qmp.sock.gettimeout()
    guest.qmp.sock.settimeout(30)
    try:
        for prop in ('engine1518-state', 'engine151-active-program-state',
                     'engine1542-ram-input-control-state', 'engine1542-state', 'raw-pipeline-state',
                     'video-raw-transport-state', 'engine151-capture-pixels-state',
                     'engine150c-state'):
            record['device_states'][prop] = json.loads(guest.qmp.command(
                'qom-get', path='/machine', property=prop))
        if guest.data.get('probe_arguments', {}).get('video_source_ram'):
            record['device_states']['video-source-ram-state'] = json.loads(guest.qmp.command(
                'qom-get', path='/machine', property='video-source-ram-state'))
        if guest.data.get('probe_arguments', {}).get('programmed_channel_clock'):
            record['device_states']['event1508-programmed-clock-state'] = json.loads(guest.qmp.command(
                'qom-get', path='/machine', property='event1508-programmed-clock-state'))
        if guest.data.get('probe_arguments', {}).get('video_main_output'):
            record['device_states']['video-main-output-state'] = json.loads(guest.qmp.command(
                'qom-get', path='/machine', property='video-main-output-state'))
        record['reads'] = finite_preview_input_plan(record['device_states'].get('engine1542-state',{}))
        record['reads'] += main_transfer_plan(record['device_states'].get('video-main-output-state',{}))
        record['reads'] += completed_transfer_plan(
            record['device_states'].get('video-source-ram-state', {}))
        record['reads'] += capture_plan(record['device_states']['engine1518-state'])
        saved = {}
        for entry in record['reads']:
            if 'skip' in entry:
                continue
            key = (entry['address'], entry['bytes'])
            if key in saved:
                entry.update(saved[key], duplicate=True)
                continue
            if record['saved_bytes'] + entry['bytes'] > SNAPSHOT_LIMIT:
                entry['skip'] = 'snapshot-byte-limit'
                continue
            identity = entry.get('identity')
            if identity is None:
                identity = 'i{instance}-b{bank}-r{row}-s{slot}'.format(**entry)
            target = guest.out / (label + '-' + identity + '.bin')
            if target.exists():
                raise FileExistsError('Private snapshot must not replace prior evidence')
            response = guest.qmp.hmp(f'pmemsave {entry["address"]} {entry["bytes"]:#x} "{target}"')
            if response or not target.exists() or target.stat().st_size != entry['bytes']:
                raise RuntimeError('Incomplete bounded source RAM observation')
            payload = target.read_bytes()
            evidence = dict(file=target.name, sha256=hashlib.sha256(payload).hexdigest(),
                zero_bytes=payload.count(0), distinct_bytes=len(set(payload)))
            saved[key] = evidence
            entry.update(evidence)
            record['saved_bytes'] += entry['bytes']
    except Exception as error:
        record['observation_error'] = repr(error)
    finally:
        guest.qmp.sock.settimeout(old_timeout)
        (guest.out / (label + '.json')).write_text(json.dumps(record, indent=2) + '\n')
