# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify ZR's own post-photo/menu evidence without requiring extra observers."""
import hashlib
from pathlib import Path

FINGERPRINT='9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f'


def evaluate(data, run):
    run=Path(run)
    out=dict(verified=False,roundtrips=[],scope='original consumed contacts, acknowledged image work and fresh same-guest RAW/LCD; file audit separate')
    w=data.get('mode_key_waveform',{})
    if data.get('main_sha256')!=FINGERPRINT or not w.get('all_consumed'):return out
    states=w.get('input_states',[]);stages=w.get('stages',[])
    if len(states)!=len(stages):return out
    def consumed(index):
        if not 0<=index<len(stages):return False
        r=stages[index].get('consumption_evidence',{})
        return (r.get('kind')=='original-key-consumer-return' and
            r.get('sequence_id')==states[index].get('sequence_id')==index+1 and
            r.get('call_number',0)>stages[index].get('after_consumer_call',r.get('call_number',0)))
    releases=[i for i,s in enumerate(states) if s.get('label')=='full-release']
    if not 1<=len(releases)<=8:return out
    cycles=data.get('capture_cycles',[])
    if len(releases)>1 and len(cycles)!=len(releases):return out
    screens={s.get('file'):s for s in data.get('display_console_captures',[])}
    def screen(index):
        row=screens.get('zr-key-state-%03d.ppm'%(index+1),{})
        path=run/row.get('file','missing')
        if not path.is_file():return None
        raw=path.read_bytes();header=b'P6\n1280 800\n255\n'
        if (len(raw)!=len(header)+1280*800*3 or not raw.startswith(header) or
                hashlib.sha256(raw).hexdigest()!=row.get('sha256')):return None
        return row,raw[len(header):]
    photos=[]
    for number,release in enumerate(releases,1):
        work=data.get('post_capture_image_gates',{}).get(str(release+1),{})
        if not (consumed(release-1) and consumed(release) and work.get('ready') and work.get('settled') and
                all(work.get('checks',{}).get(k) for k in ('jpeg_work_acknowledged',
                    'raw_work_acknowledged','all_nef_previews_committed'))):return out
        cycle=cycles[number-1] if cycles else {}
        if cycles and (cycle.get('cycle')!=number or cycle.get('press_sequence')!=release or
                cycle.get('release_sequence')!=release+1 or not cycle.get('queued_while_stopped') or
                work.get('baseline')!=cycle.get('baseline') or
                not all(work.get('checks',{}).get(k) for k in
                        ('new_raw_capture_acknowledged','new_codec_jobs_completed')) or
                work.get('raw_jobs')!=cycle['baseline']['raw_jobs']+1 or
                work.get('jpeg_jobs',0)<=cycle['baseline']['jpeg_jobs']):return out
        end=releases[number]-1 if number<len(releases) else len(states)-1
        roundtrips=_roundtrips(data,states,consumed,screen,work,release,end)
        if len(roundtrips)<2:return out
        photos.append(dict(cycle=number,baseline=cycle.get('baseline'),release_sequence=release+1,
            roundtrips=roundtrips,fresh_liveview_and_menus=True))
        out['roundtrips'].extend(roundtrips)
    out.update(verified=True,photos=photos,requested=len(releases),all_cycles_recovered=True)
    return out


def _photo_menu_visible(pixels):
    # Pinned English ZR menu geometry. Check plain tab/row backgrounds,
    # not glyphs or whether a covered video underlay is still scanned out.
    def rgb(x,y):return pixels[(y*1280+x)*3:(y*1280+x)*3+3]
    green=lambda x,y: rgb(x,y)[1]>1.4*max(rgb(x,y)[0],rgb(x,y)[2],1)
    neutral=lambda x,y: max(rgb(x,y))-min(rgb(x,y))<=2 and max(rgb(x,y))<=50
    return (all(green(x,y) for x,y in ((56,16),(64,24),(136,24))) and
            all(neutral(x,y) for x,y in ((64,150),(136,150))) and
            all(neutral(x,y) for x in (200,1100) for y in (100,201,301,397,498,601,700)))


def _roundtrips(data,states,consumed,screen,work,release,end):
    roundtrips=[]
    for i in range(release+1,end):
        if states[i].get('label')!='menu-release' or states[i+1].get('label')!='half-press':continue
        gate=data.get('post_capture_liveview_gates',{}).get(str(i+2),{})
        focus=data.get('mode_focus_screen_gates',{}).get(str(i+1),{})
        if not (consumed(i-1) and consumed(i) and consumed(i+1) and
                focus.get('matched') and gate.get('ready')):continue
        menu=screen(i);live=screen(i+1)
        if menu is None or live is None:continue
        m,pixels=menu;l,_=live
        photo_menu=_photo_menu_visible(pixels)
        raw_delta=l.get('raw',{}).get('frames',0)-m.get('raw',{}).get('frames',0)
        lcd_delta=l.get('scanout',{}).get('video_frames',0)-m.get('scanout',{}).get('video_frames',0)
        if (not photo_menu or
                not l.get('scanout',{}).get('last_frame_has_video') or raw_delta<8 or lcd_delta<=0 or
                not (m.get('virtual_ns',0)>work.get('first_ready_virtual_seconds',float('inf'))*1e9 and
                    l.get('virtual_ns',0)>m['virtual_ns']) or
                gate.get('raw_frames',0)-gate.get('baseline_raw_frames',gate.get('raw_frames',0))<8):continue
        roundtrips.append(dict(menu_sequence=i+1,return_sequence=i+2,
            menu_sha256=m['sha256'],live_sha256=l['sha256'],new_raw_frames=raw_delta,
            new_lcd_video_frames=lcd_delta,photo_menu_visible=True,
            menu_video_underlay=m.get('scanout',{}).get('last_frame_has_video'),menu_virtual_ns=m.get('virtual_ns'),
            return_virtual_ns=l.get('virtual_ns')))
    return roundtrips
