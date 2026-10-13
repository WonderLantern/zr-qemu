# SPDX-License-Identifier: GPL-2.0-or-later
"""Track repeated photos in one native session without reusing old completion.

This is a prerequisite for burst testing, not a burst drive-mode implementation.
No guest memory, register or device completion is changed here.
"""
import json
from pathlib import Path
from capture_workflow_ready import evaluate


def raw_dump_span(side, previous):
    """Derive one completed DMA span from monotonic device counters.

    The device's bytes field totals all jobs. Reading that total at the
    second completion would include another frame beyond the actual buffer.
    Preserve the complete counter state separately from the per-job span.
    """
    prior = previous[-1]['state'] if previous else {'jobs': 0, 'bytes': 0}
    if (side.get('jobs') != prior['jobs'] + 1 or side.get('acks') != side['jobs'] or
            side.get('pending')):
        raise ValueError('One newly acknowledged RAW producer required per snapshot')
    amount = side.get('bytes', 0) - prior['bytes']
    if not 0 < amount <= 128 * 1024 * 1024:
        raise ValueError('Bounded actual per-job RAW side dump required')
    for key in ('source', 'target'):
        address = side.get(key, 0)
        if not 0x800000000 <= address <= 0x900000000 - amount:
            raise ValueError('Actual RAW producer span must fit image RAM')
    return amount


def snapshot_raw_producer(guest, side, cycle):
    """Preserve each actual RAW buffer at its original acknowledged ISR."""
    previous=guest.data.setdefault('raw_side_native_dumps',[])
    job=side.get('jobs',0)
    if not job or any(entry['job']==job for entry in previous):return None
    amount=raw_dump_span(side,previous)
    files={}
    timeout=guest.qmp.sock.gettimeout()
    guest.qmp.sock.settimeout(30)
    try:
        for key in ('source','target'):
            prefix='engine151-raw-side-' if job==1 else 'engine151-raw-side-job'+str(job)+'-'
            path=guest.out/(prefix+key+'.bin')
            if path.exists():raise ValueError('Preserve each actual RAW producer snapshot')
            reply=guest.qmp.hmp(f'pmemsave {side[key]:#x} {amount:#x} "{path}"')
            if reply:raise RuntimeError(reply)
            if path.stat().st_size!=amount:raise ValueError('Incomplete per-photo RAW producer')
            files[key]=path.name
    finally:
        guest.qmp.sock.settimeout(timeout)
    entry=dict(job=job,cycle=cycle,bytes=amount,files=files,state=side,
        scope='actual complete RAM at original ISR after W1C, before original callback; not native file')
    previous.append(entry)
    if job==1:guest.data['raw_side_native_dump']=entry
    (guest.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    return entry


def ready(released, raw, lcd, jpeg, side, streams, baseline):
    fresh = [entry for entry in streams if entry['job'] > baseline['jpeg_jobs']]
    result = evaluate(released, raw, lcd, jpeg, side, fresh)
    result['checks']['new_raw_capture_acknowledged'] = bool(
        side.get('jobs', 0) == baseline['raw_jobs'] + 1 and
        side.get('acks') == side.get('jobs') and not side.get('pending'))
    result['checks']['new_codec_jobs_completed'] = jpeg.get('jobs', 0) > baseline['jpeg_jobs']
    result['ready'] = all(result['checks'].values())
    result['baseline'] = baseline
    return result


def recovery(start_state):
    return dict(enabled=True, start_state=start_state, settle_before_seconds=10,
                wait_for_completed_capture=True, visible_menus={}, returned_liveviews={},
                scope='external half/menu contacts only; no source or task state forced')


def completed(cycle, baseline, recovery_record, final_state, final_index):
    receipt = json.loads(json.dumps(recovery_record))
    receipt['returned_liveviews'][str(final_index)] = final_state
    menus = receipt.get('visible_menus', {})
    last_menu = list(menus.values())[-1] if menus else {}
    fresh = bool(final_state.get('raw', {}).get('frames', 0) >= last_menu.get('raw', {}).get('frames', 0) + 8 and
                 final_state.get('lcd', {}).get('last_frame_has_video') and
                 final_state.get('lcd', {}).get('video_frames', 0) > last_menu.get('lcd', {}).get('video_frames', 0))
    passed = bool(len(menus) == 2 and len(receipt['returned_liveviews']) == 2 and
                  receipt.get('ready_gate', {}).get('ready') and fresh)
    if not passed:
        raise ValueError('Each repeated photo requires fresh image work and both actual menu returns')
    return dict(cycle=cycle, baseline=baseline, recovery=receipt,
                fresh_liveview_and_menus=True, file_pixels_accepted=False,
                scope='same native guest and virtual card; independent whole-file audit still required')
