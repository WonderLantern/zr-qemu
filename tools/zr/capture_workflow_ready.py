# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only gate separating menus during exposure from menus after a photo.

No elapsed-time assumption: require the already consumed shutter release,
acknowledged real RAW/JPEG work and newly produced live-view frames.
Actual file and full pixel auditing remain separate and mandatory.
"""


def image_work(jpeg, side, completed_streams, main_geometry, *, baseline=None, minimum_captures=1):
    """Shared whole-image graph, with explicitly supplied model geometry."""
    if minimum_captures not in (1,8) or (minimum_captures>1 and baseline is None):
        raise ValueError('Explicit baseline and bounded burst size required')
    if baseline is not None:
        completed_streams=[entry for entry in completed_streams
                           if entry['job']>baseline['jpeg_jobs']]
    committed={tuple((r['observation']['jpeg'][k] for k in ('width','height')))
               for r in completed_streams if not r.get('count_only') and
               any(f.get('label')=='encoded' for f in r.get('files',[]))}
    checks={
        'jpeg_work_acknowledged':bool(jpeg.get('jobs',0)>0 and not jpeg.get('requested',True)
            and not jpeg.get('pending',1) and not jpeg.get('core',1)
            and jpeg.get('acks')==jpeg.get('core_acks')==jpeg.get('jobs')),
        'raw_work_acknowledged':bool(side.get('jobs',0)>0 and not side.get('pending',True)
            and side.get('acks')==side.get('jobs')),
        # Preview can resume after the main JPEG while middle/thumbnail
        # encoding still owns the capture. A momentarily idle codec alone
        # does not establish that the whole image graph is finished.
        'all_nef_previews_committed':{tuple(main_geometry),(1620,1080),(160,120)}<=committed,
    }
    if baseline is not None:
        count=side.get('jobs',0)-baseline['raw_jobs']
        enough=count==1 if minimum_captures==1 else count>=minimum_captures
        checks['new_raw_capture_acknowledged']=bool(enough
            and side.get('acks')==side.get('jobs') and not side.get('pending',True))
        checks['new_codec_jobs_completed']=jpeg.get('jobs',0)>baseline['jpeg_jobs']
        if minimum_captures>1:
            # Every actual RAW job needs the full preview set before menus.
            # Count unique acknowledged jobs, not duplicate observations.
            geometry_jobs={geometry:set() for geometry in (tuple(main_geometry),(1620,1080),(160,120))}
            for entry in completed_streams:
                if entry.get('count_only') or not any(f.get('label')=='encoded' for f in entry.get('files',[])):continue
                geometry=tuple(entry['observation']['jpeg'][k] for k in ('width','height'))
                if geometry in geometry_jobs:geometry_jobs[geometry].add(entry['job'])
            checks['all_burst_preview_jobs_committed']=bool(enough and all(len(jobs)>=count for jobs in geometry_jobs.values()))
    return dict(ready=all(checks.values()),checks=checks,jpeg_jobs=jpeg.get('jobs'),
                raw_jobs=side.get('jobs'),baseline=baseline,
                committed_geometries=sorted(committed),
                scope='completed image work only; liveview, menu and card acceptance remain separate')


def evaluate(released, raw, lcd, jpeg, side, completed_streams=()):
    work=image_work(jpeg,side,completed_streams,(8256,5504))
    checks=dict(work['checks'],
        new_raw_frames=raw.get('frames',0)>released.get('raw',{}).get('frames',raw.get('frames',0)),
        new_visible_video=bool(lcd.get('last_frame_has_video') and
            lcd.get('video_frames',0)>released.get('lcd',{}).get('video_frames',lcd.get('video_frames',0))))
    return dict(ready=all(checks.values()),checks=checks,raw_frames=raw.get('frames'),
                lcd_video_frames=lcd.get('video_frames'),jpeg_jobs=jpeg.get('jobs'),
                committed_geometries=work['committed_geometries'],
                scope='observed original work and fresh liveview; card audit still required')
