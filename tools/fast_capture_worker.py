# SPDX-License-Identifier: GPL-2.0-or-later
"""Private headless capture loop with fewer host polls and preview encodes.

The original published boot, peers, guest and functional devices are reused.
No guest instructions, virtual timers, contacts or device flags are altered.
Actual capture checkpoints remain in the capture peer; this loop only reduces
the cadence of the unused interactive preview and idle host queries.
"""
import io
import json
from pathlib import Path
import time
import traceback
from PIL import Image
from native_log_guard import NativeLogGuard


def worker(a, session, runner):
    if a.menu_test:
        raise ValueError('Fast headless worker is scoped to capture diagnostics')
    start = time.monotonic()
    fault_guard = None
    timings = dict(host_poll_interval_seconds=.01, host_preview_interval_seconds=2,
                   physical_camera_speed_verified=False,
                   scope='host control cadence only; original guest clock and device timing retained')
    try:
        with runner.Guest(a.firmware, a.qemu, a.raw, a.output) as g:
            g.data['host_control_profile'] = timings
            fault_guard = NativeLogGuard(g.log_path)
            (g.out/'native_log_guard.py').write_bytes(
                Path(__file__).with_name('native_log_guard.py').read_bytes())
            (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
            runner.boot(g, session.progress)
            timings['boot_host_seconds'] = time.monotonic()-start
            peer = runner.Peer(g, limit_frames=1024, config_reply=True, all_mode_replies=True)
            clock = runner.BoundaryPeer(g, 33, auxiliary_masked=True)
            spi8 = runner.WritePeer(g)
            spi9 = runner.WritePeer(g, channel=9, wire_bits=9, allow_dummy_rx=True)
            next_capture = 0
            deadline = time.monotonic()+a.seconds
            explicit_stop = False
            ready_reported = False
            loops = previews = 0
            g.qmp.command('cont')
            while not session.stop.is_set() and time.monotonic() < deadline:
                if (g.out/'stop.request').exists():
                    g.data['host_requested_stop'] = 'owned diagnostic stop marker; guest state preserved in final observations'
                    session.stop.set()
                    break
                loops += 1
                timings['host_loops'] = loops
                unknown = fault_guard.poll()
                timings['log_guard'] = fault_guard.receipt()
                if unknown:
                    raise RuntimeError('Unmodeled MMIO: inspect the local stderr.log')
                if not g.qmp.command('query-status')['running']:
                    handled = peer.handle()
                    if not handled and not explicit_stop:
                        raise RuntimeError('Guest stopped outside the modeled peer')
                    explicit_stop = False
                    g.qmp.command('cont')
                    continue
                clock.tick()
                now = time.monotonic()
                if now >= next_capture:
                    g.qmp.command('stop')
                    peer.handle()
                    raw = runner.state(g, 'raw-pipeline-state')
                    lcd = runner.state(g, 'engine1548-scanout-state')
                    screen = g.out/'display.ppm'
                    g.qmp.command('screendump', filename=str(screen))
                    with Image.open(screen) as im:
                        buf = io.BytesIO()
                        im.save(buf, format='PNG')
                        session.png = buf.getvalue()
                    previews += 1
                    timings['host_previews'] = previews
                    ready = (raw['frames'] >= 8 and lcd.get('video_frames', 0) >= 8
                             and lcd.get('last_frame_has_video', False))
                    session.status = dict(phase='Running' if ready else 'Waiting for live view', ready=ready,
                                          raw_frames=raw['frames'], raw_bytes=raw['bytes'],
                                          lcd_video_frames=lcd.get('video_frames', 0), output=str(g.out))
                    if ready and not ready_reported:
                        ready_reported = True
                        timings['liveview_host_seconds'] = now-start
                        session.progress('Original LCD is receiving RAW-derived video')
                    g.data['latest_pipeline'] = dict(raw=raw, lcd=lcd)
                    next_capture = now+2
                    g.qmp.command('cont')
                if not session.commands.empty():
                    raise ValueError('Headless fast capture uses only the original capture peer input queue')
                channels = runner.state(g, 'serial-state')
                if peer.clock_if_ready(channels):
                    explicit_stop = True
                    continue
                spi8.clock_if_ready(channels[8])
                spi9.clock_if_ready(channels[9])
                time.sleep(.01)
            g.qmp.command('stop')
            peer.close()
            g.data['final_pipeline'] = dict(raw=runner.state(g, 'raw-pipeline-state'),
                                           lcd=runner.state(g, 'engine1548-scanout-state'))
            g.qmp.command('screendump', filename=str(g.out/'final.ppm'))
            session.progress('Stopped')
            timings.update(host_loops=loops, host_previews=previews)
    except Exception as exc:
        traceback.print_exc()
        session.progress('Error: '+str(exc))
        session.status['error'] = repr(exc)
    finally:
        if fault_guard is not None:
            fault_guard.close()
        timings['host_seconds'] = time.monotonic()-start
        session.stop.set()
