# SPDX-License-Identifier: GPL-2.0-or-later
"""Deliver full shutter/REC contacts through the original Z9 MCU path.

This bounded diagnostic records original key-consumer calls/returns and LCD
frames. Key delivery is not capture completion or evidence of a saved file.
Uses the standalone runner and explicit local firmware/RAW inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time
from capture_support import HERE,PUBLIC,validate,archive

CONSUMER=0x40d2939c


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--name',required=True);ap.add_argument('--seconds',type=int,default=120)
    ap.add_argument('--fast-capture',action='store_true',
                    help='retain original contact checks and capture observations; compact preparation snapshots and checkpoint every8 contacts')
    ap.add_argument('--sequence',choices=('shutter','movie'),default='shutter')
    ap.add_argument('--capture-count',type=int,default=1,choices=range(1,9),
                    help='repeat complete external shutter/recovery cycles in the same guest/card; not burst mode')
    ap.add_argument('--exposure-mode-steps',type=int,default=0,choices=range(-3,4),
                    help='external MODE/main-dial steps after preparation; verify actual native LCD')
    ap.add_argument('--exposure-shutter-steps',type=int,default=0,choices=range(-64,65),
                    help='external main-dial steps after MODE release; no setting RAM writes')
    ap.add_argument('--quality-dial-steps',type=int,default=0,choices=range(-12,13),
                    help='original QUAL button plus signed main-dial steps before shutter; UI selection verified separately')
    ap.add_argument('--quality-after-menu',action='store_true',
                    help='navigate first, wait for actual live LCD, then deliver QUAL/dial inputs')
    ap.add_argument('--quality-after-wake',action='store_true',
                    help='half-wake, wait for rendered LCD, choose RAW, set compression, half-exit and wait for video before shutter')
    ap.add_argument('--menu-actions',default='',help='bounded original MCU menu/right/left/up/down/ok prefix, comma-separated')
    ap.add_argument('--menu-only',action='store_true',help='observe navigation without subsequent shutter/REC inputs')
    ap.add_argument('--post-capture-recovery',action='store_true',
                    help='after shutter release, wait10 virtual seconds then half/menu/half/menu/half through original external inputs')
    ap.add_argument('--trace-capture-recovery',action='store_true',
                    help='bounded read-only CAPSEQ/source transitions throughout the whole capture and recovery')
    ap.add_argument('--ccomp-command-replies',action='store_true',
        help='functional MCU ACK for observed family9/type2 F3 command; original receiver and scheduler remain in control')
    ap.add_argument('--ccomp-gpio',action='store_true',help='functional original CCOMP request/feedback GPIO handshake')
    ap.add_argument('--compact-capture-observations',action='store_true',help='retain first faults, MCU/GPIO completion and lifecycle; omit repeated application internals')
    ap.add_argument('--post-capture-ready-menu',action='store_true',help='wait for completed image work and newly resumed RAW/LCD before post-shot menus')
    ap.add_argument('--finish-on-fresh-liveview',action='store_true',
                    help='after both post-shot menus, finish after eight new RAW frames and fresh visible LCD instead of a fixed final delay')
    ap.add_argument('--secondary-source-timing',action='store_true',
                    help='functional channel-one timing follows its own enable/mode; no stopped-source DMA')
    ap.add_argument('--navigation-file',type=Path,help='private append-only JSON actions queue; menu-only waits for finish, optional capture after finish')
    ap.add_argument('--navigation-press-ms',type=int,default=60,choices=range(20,201),help='short external navigation pulse; release waits500ms to avoid native key-repeat')
    ap.add_argument('--engine152c-config',action='store_true',help='original sparse152c/15ac initialization; processing remains strict')
    ap.add_argument('--engine152c-request',action='store_true',help='original receiver command, no data/results/completion; requires config')
    ap.add_argument('--engine151-raw-output',action='store_true',help='candidate neutral full RAW side output alongside NV16; requires packed14 and151 pixels')
    ap.add_argument('--engine1544-config',action='store_true',help='original sparse1544 parameters/interface gates; data request304 remains strict')
    ap.add_argument('--trace-engine1544-input',action='store_true',help='read actual bounded1544 source RAM and target prefix at original data start; no data processing')
    ap.add_argument('--engine1544-neutral-copy',action='store_true',help='actual bounded same-format1544 RAM copy; auxiliary source image remains unverified')
    ap.add_argument('--engine1540-descriptors',action='store_true',help='two original1540 routing parameter leafs only; data/results/IRQ unsupported')
    ap.add_argument('--engine1540-parameters',action='store_true',help='original sparse1540 main parameters/LUT; requires descriptors; data/results/IRQ unsupported')
    ap.add_argument('--engine1540-control',action='store_true',help='original1540 subscription/interface and emptyW1C; requires parameters; data8 stays strict')
    ap.add_argument('--engine1540-frame-pass',action='store_true',help='neutral actual151 full RAW RAM transport, normal bit8 completion; LUT/codec unverified')
    ap.add_argument('--raw-lossless14',action='store_true',help='explicit attributed F0 entropy encoding of actual151 packed RAW DMA; physical codec unverified')
    ap.add_argument('--primary-reset-parameter-retention',action='store_true',help='retain alreadyconfigured upper/E parameter validity across bounded reset; physical reset semantics unverified')
    ap.add_argument('--primary20-empty-reset',action='store_true',help='observed original RAW logical20 reset; no processing/completion')
    ap.add_argument('--icount-shift',type=int,choices=range(4),default=0,help='explicit functional virtual CPU rate; physical timing remains unverified')
    ap.add_argument('--no-icount-sleep',action='store_true',help='explicit host pacing experiment; keep selected instruction clock, remove icount host sleep; native checks still required')
    ap.add_argument('--nvme-card',action='store_true',help='fresh private 8GiB exFAT card with validated Z9 PCIe inputs')
    ap.add_argument('--half-press-seconds',type=int,default=2,choices=range(1,6),
                    help='virtual seconds of half press before full press')
    ap.add_argument('--trace-app-keys',action='store_true',help='bounded original application key gates after each contact')
    ap.add_argument('--capture-gpio',action='store_true',help='also drive independently verified native shutter GPIO contacts')
    ap.add_argument('--rtc-status',action='store_true',
                    help='explicit deterministic external family7 RTC status, original parser verified separately')
    ap.add_argument('--capture-processing-selector',action='store_true',
                    help='explicit missing-ROM selector2 diagnostic input; coefficients/geometry still missing')
    ap.add_argument('--d980-config',action='store_true',
                    help='shared sparse 150d9800 configuration/submission model; no processing/results')
    ap.add_argument('--d980-stream',action='store_true',
                    help='functional packed12 external Bayer DMA; physical packing and native save unproven')
    ap.add_argument('--d980-packed14',action='store_true',help='explicit mode1/14-bit little-endian packing hypothesis; requires stream')
    ap.add_argument('--single-frame-input',action='store_true',
                    help='candidate source transition queues one bounded external frame; timing hypothesis')
    ap.add_argument('--single-source-notify',action='store_true',
                    help='existing source boundary after actual full DMA; timing hypothesis')
    ap.add_argument('--single-channel-boundary',action='store_true',
                    help='existing channel0 input after complete full DMA; timing hypothesis')
    ap.add_argument('--capture-direct-stop',action='store_true',
                    help='bounded observed401e direct drain after full input and channel ACK; functional hypothesis')
    ap.add_argument('--trace-engine153-layout',action='store_true',
        help='Read-only original153 application setup arguments')
    ap.add_argument('--engine1543-capture-control',action='store_true',
        help='Opt-in observed single-capture header control; no image/results/IRQ producer')
    ap.add_argument('--engine15e2-config',action='store_true',
        help='Original15e2 config and explicit idle reset; processing unsupported')
    ap.add_argument('--engine15e2-deferred-input',action='store_true',
        help='Opt-in bounded JPEG request waits for actual fresh matching151 RAM; no source alias or early completion')
    ap.add_argument('--engine15e2-result474',action='store_true',
                    help='opt-in opaque result474 convention: actual completed JPEG bytes; physical units unproved')
    ap.add_argument('--engine15e2-preflight',action='store_true',
                    help='opt-in original count then commit lifecycle; count has no output DMA, real thumbnail source supported')
    ap.add_argument('--engine15e2-limit-disabled',action='store_true',
        help='Opt-in original mode2/limit0 JPEG from actual owned small/mid; complete actual output span validated before DMA')
    ap.add_argument('--engine153-config',action='store_true',
                    help='sparse original1534/1538 configuration retention; processing/start remains strict')
    ap.add_argument('--engine153-frame-pass',action='store_true',
                    help='opt-in neutral actual D980-frame copy; multiscale algorithm is unsupported')
    ap.add_argument('--engine153-inplace-identity',action='store_true',
                    help='diagnostic neutral NR: actual full source RAM rewritten in place; scratch/pyramid unsupported')
    ap.add_argument('--engine151-capture-pixels',action='store_true',
                    help='actual D980 RAM -> cropped functional NV16 capture pixels')
    ap.add_argument('--engine151-average-result',action='store_true',
                    help='provisional actual cropped Bayer green means; physical statistic/ROI unknown')
    ap.add_argument('--engine15e2-jpeg',action='store_true',
                    help='actual151 NV16 RAM to baseline JPEG; physical codec conventions provisional')
    ap.add_argument('--trace-engine15e2-input',action='store_true',help='read actual JPEG request source rows and nested original input descriptors; no source alias or pixel writes')
    ap.add_argument('--trace-frame-conversion',action='store_true',help='read translated original frame-processing requests; no new pixels or completion')
    ap.add_argument('--capture-nv16-pipeline',action='store_true',help='actual owned151 NV16 through semantic internal stream to three RAM outputs; nearest sampling, physical ISP/packing unverified')
    ap.add_argument('--trace-thumbnail-route',action='store_true',help='read original thumbnail frame allocations and request objects; no new data or completion')
    ap.add_argument('--engine1542-ram-input-control',action='store_true',help='observed A2 RAM input start/stop snapshot; no data, result or completion producer')
    ap.add_argument('--capture-thumbnail-nv16',action='store_true',help='actual owned small/mid NV16 through original A2/B4/F4 to finite output planes; nearest and input boundaries, physical filtering unverified')
    ap.add_argument('--prepared-single-start',action='store_true',
                    help='retain post-reset preparation before original full-unit start; timing hypothesis')
    ap.add_argument('--trace-still-source',action='store_true',
                    help='bounded original source control/front mode and aggregate primary observations')
    ap.add_argument('--start-at',choices=('liveview','raw'),default='liveview',
                    help='raw is a diagnostic contact test even if the LCD video path is not ready')
    ap.add_argument('--settle-seconds',type=int,default=5,
                    help='virtual seconds after the last consumed contact before the diagnostic ends')
    ap.add_argument('--firmware',type=Path,required=True)
    ap.add_argument('--raw',type=Path,required=True)
    ap.add_argument('--qemu',type=Path)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();args.lifecycle_observer=None;manifest=validate(args.qemu)
    from z9_navigation_input import parse_actions
    try:menu_actions=parse_actions(args.menu_actions)
    except ValueError as error:ap.error(str(error))
    if args.menu_only and not menu_actions:ap.error('menu-only requires navigation actions')
    if args.finish_on_fresh_liveview and not (args.post_capture_recovery and args.post_capture_ready_menu):
        ap.error('fresh-frame completion requires the two post-shot menu readiness gates')
    if args.capture_count > 1 and not (args.finish_on_fresh_liveview and args.post_capture_ready_menu and args.post_capture_recovery):
        ap.error('repeated photos require completed image work, actual post-shot menus and fresh liveview gates')
    if args.capture_count > 1 and not (args.engine153_inplace_identity and args.engine151_raw_output and args.d980_stream and args.nvme_card):
        ap.error('repeated RAW photos require fresh full DMA, neutral NR, actual RAW output and one owned virtual card')
    if args.post_capture_recovery and (args.menu_only or args.navigation_file or args.sequence!='shutter'):
        ap.error('post-capture recovery requires a fixed shutter recipe')
    if (args.post_capture_recovery or args.trace_capture_recovery) and not args.trace_app_keys:
        ap.error('capture recovery requires original input observations')
    if menu_actions and not args.trace_app_keys:ap.error('navigation requires original key observations')
    if (args.quality_after_menu or args.quality_after_wake) and (not menu_actions or not args.quality_dial_steps or args.navigation_file):
        ap.error('quality readiness requires fixed menu preparation and QUAL/dial inputs')
    if args.quality_after_menu and args.quality_after_wake:
        ap.error('choose one quality preparation order')
    if args.navigation_file and not args.menu_only:ap.error('navigation file requires initially menu-only input')
    if args.engine152c_request and not args.engine152c_config:ap.error('receiver request requires config')
    if args.capture_thumbnail_nv16 and not (args.engine1542_ram_input_control and args.capture_nv16_pipeline):ap.error('thumbnail pixels require A2 control and owned capture NV16 pipeline')
    if args.engine151_raw_output and not (args.d980_packed14 and args.engine151_capture_pixels):ap.error('RAW side output requires packed14 and151 pixels')
    if args.engine1540_parameters and not args.engine1540_descriptors:ap.error('1540 main parameters require descriptors')
    if args.trace_engine1544_input and not args.engine1544_config:ap.error('1544 input observation requires config model')
    if args.engine1544_neutral_copy and not (args.engine1544_config and args.trace_engine1544_input):ap.error('1544 copy requires config and actual input observer')
    if args.engine1540_control and not args.engine1540_parameters:ap.error('1540 control requires main parameters')
    if args.engine1540_frame_pass and not (args.engine1540_control and args.engine151_raw_output):ap.error('1540 frame transport requires control and actual151 RAW side output')
    if args.raw_lossless14 and not args.engine1540_frame_pass:ap.error('F0 lossless14 requires actual RAW request/producer ownership')
    if args.trace_engine15e2_input and not args.engine15e2_jpeg:ap.error('JPEG input observer requires JPEG model')
    if not args.name.startswith('z9-') or not args.name.replace('-','').isalnum():ap.error('fresh z9- name required')
    if not 15<=args.seconds<=600:ap.error('bounded 15..600 seconds required')
    if not 1<=args.settle_seconds<=120:ap.error('bounded 1..120 virtual settle seconds required')
    if args.capture_gpio and (not args.trace_app_keys or args.sequence!='shutter'):
        ap.error('capture GPIO diagnostic requires shutter sequence and native observations')
    if args.quality_dial_steps and (args.sequence!='shutter' or not args.trace_app_keys):
        ap.error('quality inputs require traced original shutter input')
    if args.rtc_status and not args.trace_app_keys:
        ap.error('RTC input requires original notification observations')
    if args.capture_processing_selector and not args.rtc_status:
        ap.error('capture selector experiment requires traced RTC profile')
    if args.d980_stream and not args.d980_config:
        ap.error('D980 stream requires explicit configuration model')
    if args.d980_packed14 and not args.d980_stream:ap.error('packed14 requires D980 stream')
    if args.single_frame_input and not args.d980_stream:
        ap.error('single frame input requires D980 stream')
    if (args.single_source_notify or args.single_channel_boundary or args.prepared_single_start) and not args.single_frame_input:
        ap.error('single input extensions require single frame input')
    if args.trace_still_source and not (args.d980_stream and args.trace_app_keys):
        ap.error('still source observations require traced D980 stream')
    if args.capture_direct_stop and not args.single_channel_boundary:
        ap.error('capture direct stop requires full-frame channel boundary')
    if args.engine153_frame_pass and not (args.engine153_config and args.d980_stream):
        ap.error('neutral153 frame pass requires configuration and real D980 stream')
    if args.engine153_inplace_identity and (args.engine153_frame_pass or not (args.engine153_config and args.d980_stream)):
        ap.error('153 identity requires config/real D980 stream and excludes D8 copy')
    if args.engine151_capture_pixels and not args.d980_stream:ap.error('151 capture pixels require actual D980 stream')
    if args.engine151_average_result and not args.engine151_capture_pixels:ap.error('151 average requires capture pixels')
    if args.engine15e2_jpeg and not (args.engine15e2_config and args.engine151_capture_pixels):ap.error('15e2 JPEG requires config and actual151 pixels')
    if args.engine15e2_deferred_input and not (args.engine15e2_jpeg and args.trace_engine15e2_input):ap.error('deferred JPEG input requires codec and readonly input observations')
    if args.engine15e2_limit_disabled and not (args.engine15e2_jpeg and args.capture_nv16_pipeline and args.trace_engine15e2_input):ap.error('limit-disabled JPEG requires actual capture ownership and read-only codec observations')
    if args.engine15e2_result474 and not args.engine15e2_limit_disabled:ap.error('functional result474 requires actual limit-disabled JPEG')
    if args.engine15e2_preflight and not (args.engine15e2_limit_disabled and args.capture_thumbnail_nv16):ap.error('preflight requires actual capture JPEG and thumbnail producers')
    if args.trace_frame_conversion and not args.trace_engine15e2_input:ap.error('frame conversion observer requires original JPEG input observations')
    if args.capture_nv16_pipeline and not (args.trace_frame_conversion and args.engine1543_capture_control and args.engine151_capture_pixels):ap.error('capture NV16 requires source/receiver and readonly original request observations')
    if args.trace_thumbnail_route and not args.capture_nv16_pipeline:ap.error('thumbnail observations require current validated capture graph profile')
    sys.path.insert(0,str(PUBLIC/'tools'))
    import run as runner
    from PIL import Image
    import guest_transport
    from private_bounded_qmp import QMP
    guest_transport.QMP=QMP
    class CaptureGuest(runner.PreparedGuest):
        def __init__(self,*a):
            super().__init__(*a);archive(self,manifest)
            self.data['probe_arguments']={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()}
            if args.secondary_source_timing:
                self.command[self.command.index('-M')+1]+=',event1508-secondary-timing-model=on'
            sleep_mode='off' if args.no_icount_sleep else 'on'
            self.command[self.command.index('-icount')+1]=f'shift={args.icount_shift},sleep={sleep_mode}'
            self.data['runtime_profile']['clock']=f'icount{args.icount_shift}-sleep-{sleep_mode}'
            self.data['runtime_profile']['icount_sleep']=not args.no_icount_sleep
            self.data['runtime_profile']['icount_shift']=args.icount_shift
            self.data['runtime_profile']['physical_cpu_rate_verified']=False
            self.data['private_qmp_timeouts_seconds']=dict(startup=15,screendump=15,pmemsave=30,normal=3)
            (self.out/'private_bounded_qmp.py').write_bytes((HERE/'private_bounded_qmp.py').read_bytes())
            if args.capture_processing_selector:
                from capture_processing_input import attach
                attach(self)
            if args.capture_gpio:
                self.command[self.command.index('-M')+1]+=',capture-gpio-model=on'
            if args.ccomp_gpio:
                self.command[self.command.index('-M')+1]+=',ccomp-gpio-model=on'
            if args.d980_config:
                self.command[self.command.index('-M')+1]+=',primary-d980-config-model=on'
            if args.d980_stream:
                self.command[self.command.index('-M')+1]+=',primary-d980-stream-model=on'
            if args.engine152c_config:
                self.command[self.command.index('-M')+1]+=',engine152c-config-model=on'
            if args.engine152c_request:
                self.command[self.command.index('-M')+1]+=',engine152c-request-model=on'
            if args.engine151_raw_output:
                self.command[self.command.index('-M')+1]+=',engine151-raw-output-model=on'
            if args.capture_count > 1:
                self.command[self.command.index('-M')+1]+=',engine153-alternate-bank-model=on,capture-stream-rearm-model=on,engine1540-alternate-bank-model=on,engine15e2-alternate-bank-model=on'
            if args.engine1544_config:
                self.command[self.command.index('-M')+1]+=',engine1544-config-model=on'
            if args.engine1544_neutral_copy:
                self.command[self.command.index('-M')+1]+=',engine1544-neutral-copy-model=on'
            if args.engine1540_descriptors:
                self.command[self.command.index('-M')+1]+=',engine1540-descriptors-model=on'
            if args.engine1540_parameters:
                self.command[self.command.index('-M')+1]+=',engine1540-parameters-model=on'
            if args.engine1540_control:
                self.command[self.command.index('-M')+1]+=',engine1540-control-model=on'
            if args.engine1540_frame_pass:
                self.command[self.command.index('-M')+1]+=',engine1540-frame-pass-model=on'
            if args.raw_lossless14:
                self.command[self.command.index('-M')+1]+=',engine1540-lossless14-model=on'
            if args.primary_reset_parameter_retention:
                self.command[self.command.index('-M')+1]+=',primary-stopped-source-reset-model=on,primary-reset-parameter-retention-model=on'
            if args.primary20_empty_reset:
                self.command[self.command.index('-M')+1]+=',primary20-empty-reset-model=on'
            if args.d980_packed14:
                self.command[self.command.index('-M')+1]+=',primary-d980-packed14-model=on'
            if args.single_frame_input:
                self.command[self.command.index('-M')+1]+=',primary-d980-single-frame-model=on'
            if args.single_source_notify:
                self.command[self.command.index('-M')+1]+=',primary-d980-source-notify-model=on,raw-source-boundary-model=on'
                self.data['single_source_boundary_input']=dict(enabled=True,
                    scope='periodic source boundaries and one boundary after complete single-frame DMA; timing hypothesis')
            if args.prepared_single_start:
                self.command[self.command.index('-M')+1]+=',primary-d980-prepared-start-model=on'
            if args.single_channel_boundary:
                self.command[self.command.index('-M')+1]+=',primary-d980-channel-boundary-model=on'
            if args.capture_direct_stop:
                self.command[self.command.index('-M')+1]+=',primary-capture-direct-stop-model=on'
            if args.engine1543_capture_control:
                self.command[self.command.index('-M')+1]+=',engine1543-capture-control-model=on'
            if args.engine15e2_config:
                self.command[self.command.index('-M')+1]+=',engine15e2-config-model=on'
            if args.engine153_config:
                self.command[self.command.index('-M')+1]+=',engine153-config-model=on'
            if args.engine153_frame_pass:
                self.command[self.command.index('-M')+1]+=',engine153-frame-pass-model=on'
            if args.engine153_inplace_identity:
                self.command[self.command.index('-M')+1]+=',engine153-inplace-identity-model=on'
            if args.engine151_capture_pixels:
                self.command[self.command.index('-M')+1]+=',engine151-capture-pixels-model=on'
            if args.engine151_average_result:
                self.command[self.command.index('-M')+1]+=',engine151-average-result-model=on'
            if args.engine15e2_jpeg:
                self.command[self.command.index('-M')+1]+=',engine15e2-jpeg-model=on'
            if args.engine15e2_deferred_input:
                self.command[self.command.index('-M')+1]+=',engine15e2-deferred-input-model=on'
            if args.engine15e2_limit_disabled:
                self.command[self.command.index('-M')+1]+=',engine15e2-limit-disabled-model=on'
            if args.engine15e2_result474:
                self.command[self.command.index('-M')+1]+=',engine15e2-result474-model=on'
            if args.engine15e2_preflight:
                self.command[self.command.index('-M')+1]+=',engine15e2-preflight-model=on'
            if args.capture_nv16_pipeline:
                self.command[self.command.index('-M')+1]+=',capture-nv16-pipeline-model=on'
            if args.engine1542_ram_input_control:
                self.command[self.command.index('-M')+1]+=',engine1542-ram-input-control-model=on'
            if args.capture_thumbnail_nv16:
                self.command[self.command.index('-M')+1]+=',capture-thumbnail-nv16-model=on'
            if args.nvme_card:
                from virtual_recording_card import create
                card=self.out/'capture-card.raw'
                self.data['private_virtual_card']=create(card,'exfat')
                self.command[self.command.index('-M')+1]+=(',pcie-link-diagnostic-mask=4,'
                    'pcie-dbi-model=on,pcie-ram-dma-input=on,pcie-image-ram-dma-input=on,pcie-intx-model=on')
                events=self.out/'storage-dma.events'
                events.write_text('pci_nvme_map_prp\npci_nvme_map_addr\npci_nvme_write\n')
                self.command+=['-trace',f'events={events},file={self.out}/storage-dma.log']
                self.command+=['-drive',f'file={card},if=none,id=card,format=raw',
                    '-device','nvme,drive=card,serial=WL-Z9-CAPTURE,bus=dw-pcie,addr=0']
                (self.out/'virtual_recording_card.py').write_bytes((HERE/'virtual_recording_card.py').read_bytes())
            (self.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
            self.data['capture_recording_acceptance']=False
            if args.lifecycle_observer:
                raise ValueError('Standalone Z9 tool does not load private lifecycle plugins')

        def __exit__(self,kind,error,traceback):
            snapshot_error=None
            try:
                if self.qmp and not getattr(self.qmp,"broken",False) and self.proc and self.proc.poll() is None:
                    self._capture_exit_state(kind,error,traceback)
            except BaseException as exc:
                snapshot_error=exc
                self.data['final_snapshot_error']=repr(exc)
            finally:
                super().__exit__(kind or (type(snapshot_error) if snapshot_error else None),
                                 error or snapshot_error,traceback)
            if snapshot_error and error is None:raise snapshot_error

        def _capture_exit_state(self,kind,error,traceback):
            self.qmp.command('stop')
            self.data['final_native_registers']=[self.qmp.hmp('info registers',cpu) for cpu in range(4)]
            if args.capture_thumbnail_nv16:
                self.qmp.command('stop')
                self.data['capture_thumbnail_nv16_final']=runner.state(self,'capture-thumbnail-nv16-state')
            if args.engine1542_ram_input_control:
                self.qmp.command('stop')
                self.data['engine1542_ram_input_control_final']=runner.state(self,'engine1542-ram-input-control-state')
            if args.capture_nv16_pipeline:
                self.qmp.command('stop')
                self.data['capture_nv16_pipeline_final']=runner.state(self,'capture-nv16-pipeline-state')
                self.data['capture_graph_registers_final']=runner.state(self,'engine1542-state')
                self.data['capture_graph_control_final']=runner.state(self,'engine1543-control-state')
                self.data['capture_source_registers_final']=runner.state(self,'engine1518-state')
            if args.primary_reset_parameter_retention:
                self.qmp.command('stop')
                self.data['primary_reset_parameter_retention_final']=runner.state(self,'primary-reset-parameter-retention-state')
            if args.engine1540_frame_pass:
                self.qmp.command('stop')
                self.data['engine150c_control_final']=runner.state(self,'engine150c-state')
                self.data['primary_reset_final']=runner.state(self,'primary-reset-state')
                self.data['primary_empty_end_final']=runner.state(self,'primary-empty-end-state')
            if args.primary20_empty_reset:
                self.qmp.command('stop')
                self.data['primary20_reset_final']=runner.state(self,'primary20-reset-state')
            if args.engine152c_config:
                self.data['engine152c_config_final']=runner.state(self,'engine152c-config-state')
            if args.engine152c_request:
                self.data['engine152c_request_final']=runner.state(self,'engine152c-request-state')
            if args.engine1544_config:
                self.qmp.command('stop')
                self.data['engine1544_config_final']=runner.state(self,'engine1544-config-state')
            if args.engine1544_neutral_copy:
                self.data['engine1544_neutral_copy_final']=runner.state(self,'engine1544-neutral-copy-state')
            if args.engine1540_descriptors:
                self.qmp.command('stop')
                self.data['engine1540_descriptors_final']=runner.state(self,'engine1540-descriptors-state')
            if args.engine1540_parameters:
                self.qmp.command('stop')
                self.data['engine1540_parameters_final']=runner.state(self,'engine1540-parameters-state')
            if args.engine1540_control:
                self.qmp.command('stop')
                self.data['engine1540_control_final']=runner.state(self,'engine1540-control-state')
            if args.engine1540_frame_pass:
                self.qmp.command('stop')
                self.data['engine1540_frame_pass_final']=runner.state(self,'engine1540-frame-pass-state')
            if args.engine151_capture_pixels and self.qmp and self.proc and self.proc.poll() is None:
                self.qmp.command('stop')
                self.data['engine151_configuration_final']=runner.state(self,'engine151-state')
                self.data['engine151_control_final']=runner.state(self,'engine151-control-state')
                self.data['engine151_capture_pixels_final']=runner.state(self,'engine151-capture-pixels-state')
                if args.engine151_raw_output:
                    self.data['engine151_raw_output_final']=runner.state(self,'engine151-raw-output-state')
                self.data['engine151_average_result_final']=runner.state(self,'engine151-average-result-state')
                from capture_engine151_pixels import capture
                capture(self,model='z9')
            if args.engine153_inplace_identity and self.qmp and self.proc and self.proc.poll() is None:
                self.qmp.command('stop')
                self.data['engine153_inplace_identity_final']=runner.state(self,'engine153-inplace-identity-state')
                if args.capture_count > 1:
                    self.data['engine153_alternate_bank_final']=runner.state(self,'engine153-alternate-bank-state')
                    self.data['capture_stream_rearm_final']=runner.state(self,'capture-stream-rearm-state')
                    self.data['engine1540_alternate_bank_final']=runner.state(self,'engine1540-alternate-bank-state')
                    self.data['engine15e2_alternate_bank_final']=runner.state(self,'engine15e2-alternate-bank-state')
            if args.engine15e2_config and self.qmp and self.proc and self.proc.poll() is None:
                self.qmp.command('stop')
                self.data['engine15e2_config_final']=runner.state(self,'engine15e2-config-state')
                self.data['engine15e2_jpeg_final']=runner.state(self,'engine15e2-jpeg-state')
                if args.engine15e2_limit_disabled:
                    self.data['engine15e2_limit_disabled_final']=runner.state(self,'engine15e2-limit-disabled-state')
                if args.engine15e2_preflight:
                    self.data['engine15e2_preflight_final']=runner.state(self,'engine15e2-preflight-state')
                if args.engine15e2_deferred_input:
                    self.data['engine15e2_deferred_input_final']=runner.state(self,'engine15e2-deferred-input-state')
                from capture_engine15e2 import capture
                capture(self,model='z9')
            if args.engine153_config and self.qmp and self.proc and self.proc.poll() is None:
                self.qmp.command('stop')
                self.data['engine153_config_final']=runner.state(self,'engine153-config-state')
                self.data['engine153_frame_pass_final']=runner.state(self,'engine153-frame-pass-state')
                from capture_engine153 import capture
                capture(self,model='z9')
            if args.d980_stream and self.qmp and self.proc and self.proc.poll() is None:
                self.qmp.command('stop')
                self.data['primary_d980_final']=runner.state(self,'primary-d980-state')
                self.data['primary_irq_final']={hex(off):self.rd(0x150c0000+off) for off in
                    (0x200,0x204,0x208,0x20c,0x210,0x214,0x218,0x21c,0x220)}
                self.data['source_control_final']={hex(off):self.rd(0x15080000+off) for off in
                    (0x10,0x18,0x20,0x28)}
                if args.single_frame_input:
                    self.data['primary_d980_single_frame_final']=runner.state(self,'primary-d980-single-frame-state')
                    self.data['single_source_notify_final']=runner.state(self,'primary-d980-source-notify-state')
                    self.data['prepared_single_start_final']=runner.state(self,'primary-d980-prepared-start-state')
                    self.data['single_channel_boundary_final']=runner.state(self,'primary-d980-channel-boundary-state')
                    self.data['capture_direct_stop_final']=runner.state(self,'primary-capture-direct-stop-state')
                    self.data['channel_boundary_final']=runner.state(self,'event1508-channel-state')
                    self.data['channel_driver_final_hex']=self.read_bytes(0xa0280d8c8,0xa8).hex()
                    self.data['raw_source_boundary_final']=runner.state(self,'raw-source-boundary-state')
                if self.data['primary_d980_final']['frames']:
                    address=self.data['primary_d980_final']['last_physical']
                    self.data['primary_d980_output_head_hex']=self.read_bytes(address,256).hex()
            if (error or not self.data.get('capture_sequence',{}).get('all_inputs_consumed',False)) and self.qmp and self.proc and self.proc.poll() is None:
                try:
                    self.qmp.command('stop')
                    self.data['failure_registers']=[self.qmp.hmp('info registers',cpu) for cpu in range(4)]
                    self.data['failure_clock']=runner.state(self,'runtime-clock-state')
                    self.data['failure_pipeline']={name:runner.state(self,name) for name in
                        ('raw-pipeline-state','engine1548-scanout-state','capture-gpio-state','primary-d980-state')}
                    if args.trace_app_keys:
                        from capture_readiness import capture
                        capture(self,prefix='capture-failure-readiness-')
                except Exception as diagnostic_error:
                    self.data['failure_snapshot_error']=repr(diagnostic_error)

    class CapturePeer(runner.Peer):
        def queue_reply(self,wire):
            if args.ccomp_command_replies:
                from ccomp_command_peer import queue_reply
                if queue_reply(self,wire):return
            super().queue_reply(wire)

        def __init__(self,*a,**kw):
            super().__init__(*a,**kw)
            if args.ccomp_command_replies:
                (self.g.out/'ccomp_command_peer.py').write_bytes((HERE/'ccomp_command_peer.py').read_bytes())
                self.record['ccomp_command_replies_enabled']=True
            contacts=([(0,0,0),(1,0,0),(1,1,0),(1,0,0),(0,0,0)] if args.sequence=='shutter' else
                      [(0,0,0),(0,0,1),(0,0,0)])
            self.states=[]
            if args.quality_dial_steps:
                from z9_quality_input import states
                self.states+=states(args.quality_dial_steps)
                (self.g.out/'z9_quality_input.py').write_bytes((HERE/'z9_quality_input.py').read_bytes())
            self.quality_prefix=len(self.states)
            if menu_actions:
                from z9_navigation_input import states
                self.states+=states(menu_actions)
                (self.g.out/'z9_navigation_input.py').write_bytes((HERE/'z9_navigation_input.py').read_bytes())
            self.preparation_prefix=len(self.states)
            self.quality_start=0
            if args.quality_after_menu:
                quality=self.states[:self.quality_prefix]
                from capture_recovery_flow import recovery_states
                leave_menu=recovery_states()[:2]
                for row in leave_menu:
                    row['label']='pre-quality-'+row['label']
                    row['workflow_phase']='leave-menu-before-quality'
                self.states=self.states[self.quality_prefix:]+leave_menu+quality
                self.preparation_prefix+=len(leave_menu)
                self.quality_start=self.preparation_prefix-self.quality_prefix
            if args.quality_after_wake:
                from capture_recovery_flow import recovery_states
                wake=recovery_states()[:2];leave=recovery_states()[:2]
                for phase,rows in [('wake-before-quality',wake),('leave-compression-menu',leave)]:
                    for row in rows:
                        row['label']=phase+'-'+row['label']
                        row['workflow_phase']=phase
                self.states=wake+self.states+leave
                self.preparation_prefix=len(self.states)
                self.quality_start=len(wake)
            self.exposure_start=len(self.states)
            if args.exposure_mode_steps or args.exposure_shutter_steps:
                from z9_exposure_input import states
                self.states+=states(args.exposure_mode_steps,args.exposure_shutter_steps)
                self.preparation_prefix=len(self.states)
                (self.g.out/'z9_exposure_input.py').write_bytes((HERE/'z9_exposure_input.py').read_bytes())
            self.contact_states=[]
            for half,full,movie in contacts:
                body=bytearray(124);body[0]=body[4]=1
                body[7],body[8],body[9]=half,full,movie
                sw0=0x200|(half<<31)|(full<<30);sw1=movie<<13
                self.contact_states.append(dict(body_hex=body.hex(),expected_hex=struct.pack('<11I',sw0,sw1,*([0]*9)).hex()))
            if not args.menu_only:self.states+=self.contact_states
            self.post_capture_start=len(self.states)
            if args.post_capture_recovery:
                from capture_recovery_flow import recovery_states
                self.states+=recovery_states()
            self.recovery_observer=None
            self.interactive_actions=[];self.interactive_finished=False;self.interactive_ready_at=None
            self.index=0;self.active=None;self.next_probe=0;self.next_virtual=None
            self.capture=dict(sequence=args.sequence,start_at=args.start_at,settle_seconds=args.settle_seconds,
                half_press_seconds=args.half_press_seconds,
                inputs=[],all_inputs_consumed=False,
                capture_complete=False,file_saved=False,video_mode_verified=False,
                scope=('native key consumer and return with fresh host-formatted virtual card' if args.nvme_card
                    else 'native key consumer and return only; no card attached'))
            self.g.data['capture_sequence']=self.capture
            self.capture_cycle=1
            self.capture_baseline=None
            if args.capture_count > 1:
                self.capture['repeated_capture']=dict(requested=args.capture_count,completed=[],
                    all_cycles_recovered=False,all_files_accepted=False,burst_mode_verified=False,
                    scope='repeated released shutter cycles in one guest/card; continuous burst remains separate')
                (self.g.out/'capture_repeat_flow.py').write_bytes((HERE/'capture_repeat_flow.py').read_bytes())
            self.capture['post_capture_recovery']=dict(enabled=args.post_capture_recovery,
                start_state=self.post_capture_start,settle_before_seconds=10,
                wait_for_completed_capture=args.post_capture_ready_menu,
                scope='external half/menu contacts only; no source or task state forced')
            if args.post_capture_ready_menu:
                helper=Path(__file__).with_name('capture_workflow_ready.py')
                (self.g.out/helper.name).write_bytes(helper.read_bytes())
                helper=Path(__file__).with_name('native_menu_screen.py')
                (self.g.out/helper.name).write_bytes(helper.read_bytes())
                self.capture['post_capture_recovery']['visible_menus']={}
                self.capture['post_capture_recovery']['returned_liveviews']={}
            self.capture['app_key_observations']=[]
            self.capture['exposure_input']=dict(mode_steps=args.exposure_mode_steps,
                shutter_steps=args.exposure_shutter_steps,start_state=self.exposure_start,
                states=self.preparation_prefix-self.exposure_start,
                scope='external MODE/main dial; native LCD determines selected mode and shutter')
            self.capture['trace_profile']='compact preparation contacts, full capture observations' if args.fast_capture else 'full contact snapshots'
            self.capture['quality_input']=dict(dial_steps=args.quality_dial_steps,states=self.quality_prefix,
                native_format_verified=False,scope='original external QUAL/dial inputs; no setting RAM edits')
            self.capture['quality_input'].update(start_state=self.quality_start,
                actual_lcd_gate_before_quality=args.quality_after_menu,
                rendered_lcd_gate_before_quality=args.quality_after_wake)
            self.capture['navigation_input']=dict(actions=menu_actions,
                states=self.preparation_prefix-self.quality_prefix,menu_only=args.menu_only,
                native_selection_verified=False,scope='external original decoder inputs; verify native LCD separately')
            self.capture['navigation_queue']=dict(enabled=bool(args.navigation_file),commands=[],snapshots=[])
            self.app_points={0x40d291e4:'changed_status_callback',0x40d5e4ec:'app_key_event',
                0x40d5f6d4:'state_key_event',0x40d5be94:'state_input_dispatch',
                0x40d321e8:'key_outer_gate',0x40d32268:'key_ready_gate',
                0x40d32280:'key_inhibit_gate',0x40d322c8:'key_controller_dispatch',
                0x40c00128:'controller_indirect',0x403fcdbc:'controller_preprocess_return',
                0x403fcdd0:'controller_contact_return',0x403fce0c:'controller_aux_return',
                0x403e02b4:'contact_predicate_return',0x403e02d0:'contact_mode_gate',
                # Reuse the original paths already established by exercise_z9_menu.py.
                0x403e094c:'queue_signal_return',0x403e00ec:'queue_selected_record',
                0x403fc6b0:'ui_state_key_dispatch',0x403e45d0:'ui_key_code_return',
                0x403fe98c:'ui_state_decoded_key',0x403fe9c4:'ui_state_remapped_key',
                0x403ffdb0:'ui_key_permission_result',0x403ffe18:'ui_final_key_code',
                0x403fff38:'ui_key_switch',0x4040077c:'ui_state_handler_exit',
                0x403fff40:'ui_action84_gate',0x403fff5c:'ui_special_mode_gate',
                0x404004d4:'ui_mode_number',0x404006a4:'ui_normal_dispatch',
                0x40437678:'screen_dispatch',0x40437688:'screen_indirect',
                0x40400728:'screen_handler_return',
                0x40fbb084:'native_auto_release_request',0x40fbb098:'native_auto_release_gate',
                0x40fbb0dc:'native_auto_release_return',0x40fbb0e0:'native_auto_release_worker',
                0x4037c824:'native_release_permission_wait',0x4037c9a0:'native_release_permission_result',
                0x40d56508:'capture_half_application',0x40d56554:'capture_full_application',
                0x40fbab38:'capture_half_request',0x40fbabfc:'capture_full_request',
                0x40fd9d78:'capture_half_backend_argument',0x40fd9e58:'capture_half_backend_return',
                0x40fda040:'capture_full_backend_argument',0x40fda0fc:'capture_full_backend_return',
                0x40fdca90:'capture_backend_notification',0x40fda100:'capture_full_worker',
                0x40fda150:'capture_full_worker_gate',0x40fda154:'capture_full_worker_gate_return'}
            # Observe the complete original MENU request path only after the
            # photograph. Reuse the verified menu observer bindings without
            # enabling per-frame capture tracing throughout the exposure.
            self.post_menu_points={
                0x4041ddf8:'post_menu_request_entry',0x4041de00:'post_menu_gate_a',
                0x4041de08:'post_menu_gate_b',0x4041de14:'post_menu_gate_c',
                0x4041de58:'post_menu_gate_d',0x4041de64:'post_menu_gate_e',
                0x4041de74:'post_menu_transition',0x4041de94:'post_menu_ui_post',
                0x4041deb0:'post_menu_request_done',0x4045d2c4:'post_menu_request_return'}
            self.app_points.update(self.post_menu_points)
            if args.engine152c_config:
                self.app_points.update({0x40e8dbac:'capture152c_encoder_configuration',0x40cc04b0:'capture152c_prepare',
                    0x40c316c4:'capture152c_start',0x40c314e0:'capture152c_isr'})
            if args.engine152c_request:
                self.app_points.update({0x40ea7d0c:'capture152c_completion_notice',
                    0x40cc00b8:'capture152c_receiver_armed'})
            if args.engine151_raw_output:
                self.app_points.update({0x41063720:'native_nef_raw_descriptor',
                    0x410637d0:'native_nef_raw_descriptor_done',
                    0x40eae2dc:'native_nef_encoder_bridge',0x40eae338:'native_nef_supplier_bridge',
                    0x40cb6d18:'native_nef_result_forward',0x40e89174:'native_nef_raw_length_store',
                    0x406ea85c:'native_nef_bits',0x406ea8c4:'native_nef_compression',
                    0x406eaa74:'native_nef_strip_count',0x406eaae8:'native_nef_strip_count_done'})
            if args.engine1544_config:
                self.app_points.update({0x40c2546c:'capture1544_configuration',0x40c25888:'capture1544_start'})
                if args.trace_engine1544_input:
                    self.app_points[0x40cb7ad0]='capture1544_request'
            if args.engine1544_neutral_copy:
                self.app_points[0x40c250a0]='capture1544_isr_after_w1c'
            if args.engine1540_descriptors:
                self.app_points.update({0x40c24bac:'capture1540_route1',0x40c24c0c:'capture1540_route2',
                                        0x40c24c6c:'capture1540_configuration'})
            if args.engine1540_control:
                self.app_points.update({0x40c24b78:'capture1540_start',0x40c24558:'capture1540_isr'})
            if args.engine1540_frame_pass:
                self.app_points[0x40c24570]='capture1540_isr_after_w1c'
                self.app_points.update({0x40c1fb40:'primary_original_commit_start',
                                        0x40c1fb54:'primary_original_commit_write'})
            if args.capture_gpio:
                self.app_points.update({0x40fd9518:'capture_gpio_callback',
                    0x40fdffac:'capture_gpio_half_worker',0x40fdcd30:'capture_gpio_full_worker',
                    0x40fdcc58:'capture_gpio_full_release',0x40fdcda8:'capture_gpio_half_release',
                    0x40fabae0:'capture_controller_listener',0x40fac70c:'capture_controller_full_gate',
                    0x40fac828:'capture_controller_full_forward',0x40fac930:'capture_controller_forward',
                    0x40d58ee0:'capture_application_notification',0x40d5c720:'capture_application_event',
                    0x40d5f7bc:'capture_state_event',0x40d5599c:'capture_application_action',
                    0x40fb2d48:'capture_release_action',
                    0x40fdab60:'capture_release_submit',0x40fdabc8:'capture_release_new_request_gate',
                    0x40fdacec:'capture_drive_state_request',0x40fdad2c:'capture_drive_busy_gate',
                    0x40fdad58:'capture_drive_initial_gate',0x40fdad74:'capture_drive_exit',
                    0x40fdaf54:'capture_drive_submit_return',0x40fdaf74:'capture_release_flow',
                    0x40fdb1a0:'capture_release_ready_return',0x40fdb22c:'capture_release_flow_selected',
                    0x40fd8f0c:'capture_inhibit_bitmap_log',0x40fd8f58:'capture_inhibit_mask_log',
                    0x40fdb3e0:'capture_release_state3',0x40fdb474:'capture_release_count_gate',
                    0x40fdb6a4:'capture_release_no_count',0x40fd5414:'capture_release_command',
                    0x40fe0ee0:'capture_drive_external_start_return'})
            if args.trace_still_source:
                self.app_points.update({0x40c2b734:'still_source_control',
                    0x40c2b778:'still_source_read',0x40c2b7bc:'still_front_submit',
                    0x40c2b7dc:'still_source_command',0x40c2bb98:'still_front_mode',
                    0x40c2bcb0:'still_front_mode3',0x40caf478:'still_primary_aggregate_start'})
            if args.trace_capture_recovery:
                # One owner for the repeating source-setter breakpoint.
                self.app_points.pop(0x40c2b734,None)
            if args.engine153_frame_pass or args.engine153_inplace_identity:
                self.app_points.update({0x40c279e0:'frame_pass_isr',0x40cbbc50:'frame_pass_callback'})
            if args.trace_engine153_layout:
                self.app_points[0x40cbb744]='engine153_layout'
            if args.engine151_capture_pixels:
                self.app_points[0x40c0d530]='capture151_isr_after_w1c'
            if args.engine15e2_jpeg:
                self.app_points[0x40c0c498]='capture15e2_isr'
                self.app_points[0x40c9c410]='capture15e2_prepare_call'
                if args.trace_engine15e2_input:
                    self.app_points[0x40c0d1a0]='capture15e2_start'
                    self.app_points[0x40e8617c]='capture15e2_source_request'
                    self.app_points[0x40c9c1d4]='capture15e2_submit_request'
                    self.app_points[0x40c9c5b4]='capture15e2_wait_failure'
                    self.app_points[0x40c0cca4]='capture15e2_clock_cleanup'
                    self.app_points[0x40c9c6b0]='capture15e2_cleanup_return'
            if args.trace_frame_conversion:
                from capture_frame_conversion import POINTS
                self.app_points.update(POINTS)
                for name in ('capture_frame_conversion.py','capture_virtual_ram.py'):
                    (self.g.out/name).write_bytes((HERE/name).read_bytes())
            if args.capture_nv16_pipeline:
                from capture_nv16_pipeline import POINTS
                self.app_points.update(POINTS)
                (self.g.out/'capture_nv16_pipeline.py').write_bytes((HERE/'capture_nv16_pipeline.py').read_bytes())
            if args.trace_thumbnail_route:
                from capture_thumbnail_route import POINTS
                self.app_points.update(POINTS)
                (self.g.out/'capture_thumbnail_route.py').write_bytes((HERE/'capture_thumbnail_route.py').read_bytes())
            self.still_channel_points={0x40c2b190:'still_frame_channel_isr',
                                       0x41159e0c:'still_frame_channel_callback'}
            if args.rtc_status:
                from rtc_mcu_input import diagnostic_status
                from mcu_frames import frames
                body=diagnostic_status()
                self.capture['rtc_input']=dict(classification='deterministic external MCU status sample',
                    timestamp='2026-10-10T12:34:56',family=7,body_hex=body.hex(),
                    periodic_clock=False,physical_protocol_verified=False,
                    parser_evidence='rtc-rx-native-451b',guest_state_patched=False)
                (self.g.out/'rtc_mcu_input.py').write_bytes((HERE/'rtc_mcu_input.py').read_bytes())
                self.pending.append((7,body,frames(body,family=7)[0]))
                self.rtc_points={0x40cc9d94:'rtc_abstract_consumer',
                    0x40cc97e4:'rtc_native_status',0x40cc8ecc:'rtc_native_change_gate',
                    0x40cc8eec:'rtc_native_notification',0x40fab8c0:'rtc_capture_listener',
                    0x40fc4ae4:'rtc_capture_state_update',0x40fc4b30:'rtc_capture_inhibit_clear',
                    0x40fe0ee0:'capture_drive_external_start_return',
                    0x40c07bc0:'native_register_dump',0x40c07d74:'native_conditional_dump',
                    0x40c07d98:'native_type6_dump',0x40cc4790:'native_diagnostic_trigger',
                    0x40c032d0:'native_exception_report',
                    0x4117af04:'native_capture_lookup'}
                for pc,label in self.rtc_points.items():self.arm(pc,'capture_app_'+label)

        def snapshot(self,label):
            g=self.g;screen=g.out/(label+'.ppm')
            g.qmp.command('screendump',filename=str(screen))
            with Image.open(screen) as im:im.save(g.out/(label+'.png'))
            data=dict(raw=runner.state(g,'raw-pipeline-state'),
                lcd=runner.state(g,'engine1548-scanout-state'),
                virtual_ns=runner.state(g,'runtime-clock-state')['virtual_ns'])
            if args.d980_stream:
                data['d980']=runner.state(g,'primary-d980-state')
                if args.single_frame_input:
                    data['single_frame']=runner.state(g,'primary-d980-single-frame-state')
                data['source_timing']=runner.state(g,'event1508-channel-state')
                engine=runner.state(g,'engine150c-state')
                data['primary']={k:engine[k] for k in ('active','latched','configured','stop_requested','stop_done')}
                data['primary_hold']=g.rd(0x150c0018)
                data['primary_irq']={hex(off):g.rd(0x150c0000+off) for off in
                    (0x200,0x204,0x208,0x20c,0x210,0x214,0x218,0x21c,0x220)}
            if args.nvme_card:
                data['block_stats']=g.qmp.command('query-blockstats')
                data['pcie_state']=runner.state(g,'pcie-dbi-state')
            if args.capture_gpio:
                data['capture_gpio']=runner.state(g,'capture-gpio-state')
            if args.trace_app_keys and label in ('capture-before','capture-final'):
                from capture_readiness import capture
                capture(g,prefix=label+'-readiness-')
            return data

        def handle(self):
            captured={}
            if self.active is not None or (args.trace_app_keys and self.index) or args.rtc_status:
                for cpu in range(4):
                    text=self.g.qmp.hmp('info registers',cpu)
                    regs={k:int(v,16) for k,v in re.findall(r'\b(X\d\d|PC|SP)=([0-9a-fA-F]+)',text)}
                    if self.points.get(regs['PC'],'').startswith(('capture_key_','capture_app_')):
                        captured.setdefault(regs['PC'],(cpu,regs,self.points[regs['PC']]))
            handled=super().handle()
            for pc,(cpu,regs,label) in captured.items():
                if label.startswith('capture_app_'):
                    record=dict(name=label,cpu=cpu,pc=hex(pc),registers=regs,
                        most_recent_contact=len(self.capture['inputs']),
                        virtual_ns=runner.state(self.g,'runtime-clock-state')['virtual_ns'])
                    self.capture['app_key_observations'].append(record)
                    if label.startswith('capture_app_recovery_'):
                        self.recovery_observer.observe(record,regs)
                        continue
                    if label.startswith('capture_app_native_nef_'):
                        from capture_native_image_arguments import observe as observe_image_arguments
                        record['native_nef_arguments']=observe_image_arguments(self.g,regs,cpu=cpu,label=label)
                    if args.trace_thumbnail_route and label.startswith('capture_app_thumbnail_'):
                        from capture_thumbnail_route import observe
                        try:
                            observe(self.g,record,regs,runner.state,self.arm,self.points)
                        except ValueError as exc:
                            record['thumbnail_observer_error']=str(exc)
                            record['scope']='partial read-only observation; invalid metadata span skipped, guest unchanged'
                    if args.trace_thumbnail_route and label.endswith(('capture15e2_prepare_call','capture15e2_prepare_method')):
                        record['thumbnail_prepare_graph']=runner.state(self.g,'engine1542-state')
                        record['thumbnail_prepare_source']=runner.state(self.g,'engine1518-state')
                        record['thumbnail_prepare_control']=runner.state(self.g,'engine1543-control-state')
                    if args.capture_nv16_pipeline and label.startswith('capture_app_capture_nv16_'):
                        from capture_nv16_pipeline import observe,POINTS
                        observe(self.g,record,regs,runner.state,self.arm,self.points)
                        if pc==0x40c2599c and record['capture_nv16_pipeline']['jobs']:
                            for checkpoint in (0x40c25a30,0x40c25a3c):
                                if checkpoint not in self.points:self.arm(checkpoint,'capture_app_'+POINTS[checkpoint])
                        pairs={0x40c0a978:0x40c0a984,0x40c0a984:0x40c0a978,
                            0x40c25a30:0x40c25a3c,0x40c25a3c:0x40c25a30}
                        if pc in pairs:
                            other=pairs[pc]
                            count=sum(x['pc']==hex(min(pc,other)) and x.get('capture_nv16_pipeline',{}).get('jobs',0)>0 for x in self.capture['app_key_observations'])
                            if record['capture_nv16_pipeline']['jobs'] and other not in self.points and count<24:self.arm(other,'capture_app_'+POINTS[other])
                    if args.trace_frame_conversion and label.startswith('capture_app_frame_conversion_'):
                        from capture_frame_conversion import observe
                        observe(self.g,record,regs,runner.state)
                        # Pair entry with its original ret instruction; never
                        # re-arm the current PC before the guest advances.
                        pairs={0x40c0acd4:0x40c0ace0,0x40c0ace0:0x40c0acd4,
                            0x40e854fc:0x40e85698,0x40e85698:0x40e854fc,
                            0x40c0ad78:0x40c0b278,0x40c0b278:0x40c0ad78}
                        if pc in pairs:
                            other=pairs[pc]
                            if other not in self.points:
                                count=sum(x['pc']==hex(min(pc,other)) for x in self.capture['app_key_observations'])
                                if count<24:self.arm(other,'capture_app_'+self.app_points[other])
                    if args.engine1540_frame_pass and label.endswith(('primary_original_commit_start','primary_original_commit_write')):
                        record['engine150c_control']=runner.state(self.g,'engine150c-state')
                        record['primary_reset']=runner.state(self.g,'primary-reset-state')
                        record['primary_empty_end']=runner.state(self.g,'primary-empty-end-state')
                        record['request_mask']=hex(regs['X01'])
                        # Re-arm only the OTHER original checkpoint. Re-arming
                        # the current PC before cont would trap the same call.
                        if args.trace_engine15e2_input:
                            other=0x40c1fb54 if pc==0x40c1fb40 else 0x40c1fb40
                            if other not in self.points:
                                self.arm(other,'capture_app_'+self.app_points[other])
                    if label.startswith('capture_app_capture1540_'):
                        record['engine1540_descriptors']=runner.state(self.g,'engine1540-descriptors-state')
                        if args.engine1540_control:
                            record['engine1540_control']=runner.state(self.g,'engine1540-control-state')
                        if args.engine1540_frame_pass:
                            record['engine1540_frame_pass']=runner.state(self.g,'engine1540-frame-pass-state')
                        if label.endswith('capture1540_callback'):
                            record['callback_event']=hex(regs['X00'])
                            record['callback_cause']=hex(regs['X01'])
                            record['scope']='original registered callback event/cause; neither argument is a RAM pointer'
                        elif label.endswith(('capture1540_start','capture1540_isr','capture1540_isr_after_w1c')):
                            obj=regs['X00']
                            if not 0xa00000000<=obj<=0xa40000000-0x30:
                                raise ValueError('native1540 driver outside bounded work RAM')
                            record['native1540_driver_hex']=self.g.read_bytes(obj,0x30).hex()
                            record['engine1540_parameters']=runner.state(self.g,'engine1540-parameters-state')
                            if args.engine1540_frame_pass:
                                callback=struct.unpack_from('<Q',bytes.fromhex(record['native1540_driver_hex']),0x10)[0]
                                if not 0x40160000<=callback<0x41600000 or callback&3:
                                    raise ValueError('native1540 callback outside original executable prefix')
                                if callback not in self.points:self.arm(callback,'capture_app_capture1540_callback')
                                if label.endswith('capture1540_isr_after_w1c'):
                                    frame=record['engine1540_frame_pass'];amount=frame['bytes']
                                    record['isr_cause']=hex(regs['X01'])
                                    if frame['jobs']==1 and not self.g.data.get('engine1540_native_dump'):
                                        if not 0<amount<=128*1024*1024:raise ValueError('bounded actual1540 RAW dump required')
                                        files={}
                                        for key in ('source','target'):
                                            path=self.g.out/('engine1540-raw-'+key+'.bin')
                                            reply=self.g.qmp.hmp(f'pmemsave {frame[key]:#x} {amount:#x} "{path}"')
                                            if reply:raise RuntimeError(reply)
                                            files[key]=path.name
                                        self.g.data['engine1540_native_dump']=dict(bytes=amount,files=files,
                                            scope='complete actual RAW RAM at original1540 ISR afterW1C, before callback; not NEF')
                        else:
                            pointer=regs['X01'];amount=0x90 if label.endswith('configuration') else 0x20
                            if not 0xa00000000<=pointer<=0xa40000000-amount:
                                raise ValueError('native1540 parameters outside bounded work RAM')
                            record['native1540_argument_hex']=self.g.read_bytes(pointer,amount).hex()
                            record['native1540_argument_address']=hex(pointer)
                            if args.engine1540_parameters:
                                record['engine1540_parameters']=runner.state(self.g,'engine1540-parameters-state')
                            if label.endswith('configuration'):
                                arg=bytes.fromhex(record['native1540_argument_hex']);tables={}
                                firmware_end=0x40160000+Path(self.g.command[self.g.command.index('-kernel')+1]).stat().st_size
                                for off,size in ((0x20,512),(0x30,60),(0x38,60),(0x48,60),(0x50,60),(0x58,52)):
                                    source=struct.unpack_from('<Q',arg,off)[0]
                                    if not source:continue
                                    table=dict(address=hex(source),bytes=size)
                                    if (0xa00000000<=source<=0xa40000000-size or
                                        0x40160000<=source<=firmware_end-size):
                                        table['hex']=self.g.read_bytes(source,size).hex()
                                    else:table['unobserved']='outside bounded working RAM/original firmware; optional trace skipped'
                                    tables[hex(off)]=table
                                record['native1540_tables']=tables
                    if label.startswith('capture_app_capture1544_'):
                        record['engine1544_config']=runner.state(self.g,'engine1544-config-state')
                        if args.engine1544_neutral_copy:
                            record['engine1544_neutral_copy']=runner.state(self.g,'engine1544-neutral-copy-state')
                        if label.endswith('capture1544_callback'):
                            record['callback_event']=hex(regs['X00'])
                            record['callback_cause']=hex(regs['X01'])
                            record['scope']='original registered callback event/cause; no argument treated as a RAM pointer'
                        elif label.endswith('capture1544_request'):
                            pointer=regs['X00']
                            if not 0xa00000000<=pointer<=0xa40000000-0x1d0:
                                raise ValueError('native1544 request outside bounded working RAM')
                            record['native1544_request_address']=hex(pointer)
                            record['native1544_request_hex']=self.g.read_bytes(pointer,0x1d0).hex()
                        elif label.endswith('capture1544_isr_after_w1c'):
                            frame=record['engine1544_neutral_copy'];record['isr_cause']=hex(regs['X01'])
                            if frame['jobs']==1 and not self.g.data.get('engine1544_native_output'):
                                amount=frame['bytes']
                                if not 0<amount<=128*1024:raise ValueError('bounded1544 native output required')
                                files={}
                                for key in ('source','target'):
                                    path=self.g.out/('engine1544-copy-'+key+'.bin')
                                    reply=self.g.qmp.hmp(f'pmemsave {frame[key]:#x} {amount:#x} "{path}"')
                                    if reply:raise RuntimeError(reply)
                                    files[key]=path.name
                                self.g.data['engine1544_native_output']=dict(bytes=amount,files=files,
                                    scope='actual source/target at original ISR after W1C, before callback; zero auxiliary input is not RAW image/file proof')
                        elif label.endswith('configuration'):
                            pointer=regs['X01']
                            if not 0xa00000000<=pointer<=0xa40000000-0x200:
                                raise ValueError('native1544 configuration outside bounded work RAM')
                            record['native1544_argument_hex']=self.g.read_bytes(pointer,0x200).hex()
                            record['native1544_argument_address']=hex(pointer)
                        elif args.trace_engine1544_input and label.endswith('capture1544_start'):
                            pointer=regs['X00']
                            if not 0xa00000000<=pointer<=0xa40000000-0x40:
                                raise ValueError('native1544 driver outside bounded working RAM')
                            record['native1544_driver_address']=hex(pointer)
                            record['native1544_driver_hex']=self.g.read_bytes(pointer,0x40).hex()
                            fields=record['engine1544_config']['fields']
                            width,height=(fields[x//4] for x in (0x48,0x4c))
                            pitch=fields[0x60//4]&0x7ff0
                            record['input_pitch_register_word']=fields[0x60//4]
                            source=fields[0x58//4]|(fields[0x5c//4]<<32)
                            target=fields[0x64//4]|(fields[0x68//4]<<32)
                            amount=pitch*height;prefix=512
                            banks=((0x840000000,0x8adf8da00),(0x8adf8dc00,0x8fff47400))
                            def span(addr,size):return any(lo<=addr and size>0 and addr+size<=hi for lo,hi in banks)
                            if not width or not height or not 0<amount<=128*1024 or not span(source,amount) or not span(target,prefix):
                                raise ValueError('native1544 input/prefix outside bounded actual image RAM')
                            if not self.g.data.get('engine1544_native_input'):
                                files={}
                                for key,address,size in (('source',source,amount),('target_prefix',target,prefix)):
                                    path=self.g.out/('engine1544-'+key+'.bin')
                                    reply=self.g.qmp.hmp(f'pmemsave {address:#x} {size:#x} "{path}"')
                                    if reply:raise RuntimeError(reply)
                                    files[key]=path.name
                                self.g.data['engine1544_native_input']=dict(width=width,height=height,pitch=pitch,
                                    source=source,target=target,input_bytes=amount,target_prefix_bytes=prefix,files=files,
                                    physical_format_verified=False,output_capacity_verified=False,
                                    scope='actual source span and target prefix before original1544 data request; no output/codec proof')
                            if args.engine1544_neutral_copy:
                                callback=struct.unpack_from('<Q',bytes.fromhex(record['native1544_driver_hex']),8)[0]
                                if not 0x40160000<=callback<0x41600000 or callback&3:
                                    raise ValueError('native1544 registered callback outside original executable prefix')
                                record['registered_callback']=hex(callback)
                                if callback not in self.points:self.arm(callback,'capture_app_capture1544_callback')
                    if label.startswith('capture_app_capture152c_'):
                        from capture_engine152c import observe as observe_receiver
                        record['native152c_observation']=observe_receiver(self.g,regs,label)
                        record['engine152c_config']=record['native152c_observation']['configuration']
                        observation=record['native152c_observation']
                        if 'argument_hex' in observation:
                            record['native152c_argument_hex']=observation['argument_hex']
                            record['native152c_argument_address']=observation['argument_address']
                        if label.endswith('receiver_armed'):
                            callback=int(observation['start_notice_callback'],16)
                            if callback and callback not in self.points:
                                self.arm(callback,'capture_app_capture152c_start_notice')
                    if label.startswith('capture_app_capture151_'):
                        from capture_engine151_pixels import observe
                        record['engine151_pixels_observation']=observe(self.g,model='z9')
                        if label.endswith('capture151_isr_after_w1c'):
                            side=record['engine151_pixels_observation'].get('raw_side',{})
                            job=side.get('jobs',0)
                            previous=self.g.data.setdefault('raw_side_native_dumps',[])
                            if job and not any(entry['job']==job for entry in previous):
                                from capture_repeat_flow import raw_dump_span
                                amount=raw_dump_span(side,previous)
                                files={}
                                for key in ('source','target'):
                                    prefix='engine151-raw-side-' if job==1 else 'engine151-raw-side-job'+str(job)+'-'
                                    path=self.g.out/(prefix+key+'.bin')
                                    if path.exists():raise ValueError('Preserve each actual RAW producer snapshot')
                                    reply=self.g.qmp.hmp(f'pmemsave {side[key]:#x} {amount:#x} "{path}"')
                                    if reply:raise RuntimeError(reply)
                                    files[key]=path.name
                                entry=dict(job=job,cycle=self.capture_cycle,bytes=amount,files=files,state=side,
                                    scope='actual complete RAM at original ISR afterW1C, before original callback; not native file')
                                previous.append(entry)
                                if job==1:self.g.data['raw_side_native_dump']=entry
                            callback=regs['X02']
                            if not 0x40160000<=callback<0x41600000 or callback&3:
                                raise ValueError('native151 callback outside original executable prefix')
                            if callback not in self.points:self.arm(callback,'capture_app_capture151_callback')
                    if label.startswith('capture_app_capture15e2_'):
                        from capture_engine15e2 import observe
                        item=observe(self.g,driver_address=regs['X00'] if label.endswith('capture15e2_isr') else None)
                        record['engine15e2_observation']=item
                        if args.engine15e2_deferred_input:
                            record['engine15e2_deferred_input']=runner.state(self.g,'engine15e2-deferred-input-state')
                        if args.trace_engine15e2_input and label.endswith('capture15e2_wait_failure'):
                            record['original_wait_error']=regs['X21']&0xffffffff
                            record['scope']='original wait failure branch; no supplied OS flags'
                        if args.trace_engine15e2_input and label.endswith(('capture15e2_source_request','capture15e2_submit_request')):
                            address=regs['X01']
                            size=0x60 if label.endswith('capture15e2_source_request') else 0x120
                            if not 0xa00000000<=address<=0xa40000000-size:
                                raise ValueError('original JPEG request outside bounded work RAM')
                            from capture_virtual_ram import read_virtual_ram
                            read=lambda a,n: read_virtual_ram(self.g,a,n,cpu=cpu) if args.trace_frame_conversion else self.g.read_bytes(a,n)
                            data=read(address,size)
                            record['source_request_address']=hex(address)
                            record['source_request_hex']=data.hex()
                            record['original_caller']=hex(regs['X30'])
                            # The higher wrapper copies 0x28 bytes from request+8;
                            # submit embeds that image descriptor at request+8.
                            if label.endswith('capture15e2_source_request'):
                                frame=struct.unpack_from('<Q',data,8)[0]
                                if 0xa00000000<=frame<=0xa40000000-0x40:
                                    record['source_image_descriptor_address']=hex(frame)
                                    record['source_image_descriptor_hex']=read(frame,0x40).hex()
                                    # Native caller40eb35dc selects +0x30 of
                                    # an original frame object. Read the parent
                                    # only when that exact caller is observed.
                                    if (regs['X30']==0x40eb3640 and
                                        0xa00000000<=frame-0x30<=0xa40000000-0x100):
                                        record['source_parent_frame_address']=hex(frame-0x30)
                                        record['source_parent_frame_hex']=read(frame-0x30,0x100).hex()
                                # At this exact wrapper entry X19 is still the
                                # caller40eb3480 frame context, before its own
                                # prologue replaces X19. Pin that observed call.
                                context=regs['X19']
                                if (regs['X30']==0x40eb3640 and
                                    0xa00000000<=context<=0xa40000000-0x7a0):
                                    parent=read(context,0x7a0)
                                    record['source_context_address']=hex(context)
                                    record['source_context_hex']=parent.hex()
                                    record['source_context_frames']=[]
                                    for offset in [0x688,0x690]:
                                        obj=struct.unpack_from('<Q',parent,offset)[0]
                                        if not 0xa00000000<=obj<=0xa40000000-0x280:
                                            continue
                                        raw=read(obj,0x280)
                                        entry=dict(context_offset=hex(offset),address=hex(obj),frame_hex=raw.hex())
                                        owner=struct.unpack_from('<Q',raw,8)[0]
                                        if 0xa00000000<=owner<=0xa40000000-0x100:
                                            entry['reference_address']=hex(owner)
                                            entry['reference_hex']=read(owner,0x100).hex()
                                            entry['reference_role_verified']=False
                                        record['source_context_frames'].append(entry)
                            record['scope']='read-only original request/caller; buffer producer remains unproved'
                        if args.trace_engine15e2_input and label.endswith('capture15e2_start'):
                            config=runner.state(self.g,'engine15e2-config-state')['banks'][item['bank']]['fields']
                            width,height,stride=config[0x418//4],config[0x41c//4],config[0x410//4]
                            if not 0<width<=16384 or not 0<height<=8192 or not width<=stride<=32768:
                                raise ValueError('bounded actual JPEG input geometry required')
                            banks=((0x840000000,0x8adf8da00),(0x8adf8dc00,0x8fff47400))
                            report=dict(width=width,height=height,stride=stride,planes={},
                                engine151_configuration=runner.state(self.g,'engine151-state'),
                                engine151_control=runner.state(self.g,'engine151-control-state'),
                                primary=runner.state(self.g,'engine150c-state'),
                                scope='read-only actual source rows at original JPEG start; no aliases/source writes or new completion')
                            for key,off in [('y',0x430),('uv',0x434)]:
                                address=config[off//4]<<4;span=stride*height
                                if not any(lo<=address and address+span<=hi for lo,hi in banks):
                                    raise ValueError('actual JPEG input plane outside mapped image banks')
                                plane=dict(address=hex(address),span=span,rows=[])
                                for row in sorted({0,height//2,height-1}):
                                    data=self.g.read_bytes(address+row*stride,stride)
                                    path=self.g.out/f'engine15e2-request-{key}-row-{row}.bin';path.write_bytes(data)
                                    plane['rows'].append(dict(row=row,bytes=len(data),nonzero_bytes=sum(x!=0 for x in data),file=path.name))
                                report['planes'][key]=plane
                            record['jpeg_input_observation']=report
                            self.g.data['engine15e2_request_input']=report
                        if label.endswith('capture15e2_isr') and item['jpeg']['jobs']:
                            if args.engine15e2_limit_disabled:
                                from capture_jpeg_completed import dump_completed
                                record['jpeg_completed_dump']=dump_completed(self.g,item,regs)
                            callback=int(item['callback'],0)
                            if not 0x40160000<=callback<0x41600000 or callback&3:
                                raise ValueError('native15e2 callback outside original executable prefix')
                            if callback not in self.points:self.arm(callback,'capture_app_capture15e2_callback')
                        if label.endswith('capture15e2_callback'):
                            if 0x40c9c410 not in self.points:self.arm(0x40c9c410,'capture_app_capture15e2_prepare_call')
                            if args.engine15e2_limit_disabled and 0x40c0c498 not in self.points:
                                self.arm(0x40c0c498,'capture_app_capture15e2_isr')
                            if args.trace_thumbnail_route:
                                for checkpoint in (0x40e8617c,0x40c9c1d4,0x40c0d1a0):
                                    if checkpoint not in self.points:self.arm(checkpoint,'capture_app_'+self.app_points[checkpoint])
                        if label.endswith('capture15e2_prepare_call'):
                            parameter=regs['X00'];method=regs['X08']
                            if not 0xa00000000<=parameter<=0xa40000000-0x50:
                                raise ValueError('original15e2 prepare argument outside bounded RAM')
                            if not 0x40160000<=method<0x41600000 or method&3:
                                raise ValueError('original15e2 prepare method outside executable prefix')
                            record['prepare_parameter_address']=hex(parameter)
                            record['prepare_parameter_hex']=self.g.read_bytes(parameter,0x50).hex()
                            record['actual_prepare_method']=hex(method)
                            if args.trace_engine15e2_input:
                                descriptor=struct.unpack_from('<Q',bytes.fromhex(record['prepare_parameter_hex']),0x18)[0]
                                if 0xa00000000<=descriptor<=0xa40000000-0x80:
                                    data=self.g.read_bytes(descriptor,0x80)
                                    record['original_input_descriptor_address']=hex(descriptor)
                                    record['original_input_descriptor_hex']=data.hex()
                                    frame=struct.unpack_from('<Q',data,0x20)[0]
                                    if 0xa00000000<=frame<=0xa40000000-0x100:
                                        record['original_input_frame_address']=hex(frame)
                                        record['original_input_frame_hex']=self.g.read_bytes(frame,0x100).hex()
                            if method not in self.points:self.arm(method,'capture_app_capture15e2_prepare_method')
                    if label.endswith('engine153_layout'):
                        from capture_engine153_layout import observe
                        record['engine153_layout']=observe(self.g,regs)
                    if label.startswith('capture_app_frame_pass_'):
                        from capture_engine153 import observe
                        record['engine153_observation']=observe(self.g,model='z9')
                    if label.startswith('capture_app_still_'):
                        record['source_timing']=runner.state(self.g,'event1508-channel-state')
                        record['full_dma']=runner.state(self.g,'primary-d980-state')
                        record['primary_hold']=self.g.rd(0x150c0018)
                        engine=runner.state(self.g,'engine150c-state')
                        record['primary']={k:engine[k] for k in ('active','latched','configured','stop_requested','stop_done')}
                        if label.startswith('capture_app_still_frame_channel_'):
                            record['channel_boundary']=runner.state(self.g,'primary-d980-channel-boundary-state')
                            record['channel_driver_hex']=self.g.read_bytes(0xa0280d8c8,0xa8).hex()
                        if label.endswith('still_return_primary_aggregate_start') and args.single_channel_boundary and engine['active']&0x4000:
                            for point,name in self.still_channel_points.items():
                                if point not in self.points:self.arm(point,'capture_app_'+name)
                        if not label.startswith(('capture_app_still_return_','capture_app_still_frame_channel_')):
                            caller=regs['X30']
                            if 0x40160000<=caller<0x41600000 and caller&3==0 and caller not in self.points:
                                self.arm(caller,'capture_app_still_return_'+label.removeprefix('capture_app_still_'))
                        if label.endswith('still_primary_aggregate_start'):
                            pointer=regs['X01']
                            if 0xa00000000<=pointer<=0xa20000000-20:
                                record['selected_units_hex']=self.g.read_bytes(pointer,20).hex()
                    if label.endswith('native_capture_lookup'):
                        base=regs['X09'];address=regs['X08']+regs['X10']
                        if not 0xa00000000<=base<=0xa20000000-0xf2000:
                            raise ValueError('capture table outside observed original RAM copy')
                        selector=address-base-0xdaf40
                        if not 0<=selector<32:
                            raise ValueError('unexpected original capture selector')
                        record['lookup_table_base']=hex(base)
                        record['lookup_selector']=selector
                        record['lookup_index']=self.g.read_bytes(address,1).hex()
                        record['lookup_table_window']=self.g.read_bytes(base+0xdaf40,0x40).hex()
                    if label.endswith('native_exception_report'):
                        pointer=regs['X19']
                        if not 0xa00000000<=pointer<=0xa20000000-0x140:
                            raise ValueError('native exception context outside work RAM')
                        record['exception_context_address']=hex(pointer)
                        record['exception_context_hex']=self.g.read_bytes(pointer,0x140).hex()
                        record['exception_handler_stack_hex']=self.g.read_bytes(regs['SP'],0x130).hex()
                    if label.endswith(('native_register_dump','native_conditional_dump','native_type6_dump',
                                        'native_diagnostic_trigger')):
                        pointer=regs['SP']
                        if 0xa00000000<=pointer<=0xa20000000-0x200:
                            record['native_stack_hex']=self.g.read_bytes(pointer,0x200).hex()
                        record['native_dump_caller']=hex(regs['X30'])
                        record['native_diagnostic_state_hex']=self.g.read_bytes(0xa02f48000,0x220).hex()
                    if label.endswith('rtc_native_status'):
                        pointer=regs['X00']
                        if not 0xa00000000<=pointer<=0xa20000000-20:
                            raise ValueError('RTC parsed status outside work RAM')
                        record['rtc_status_hex']=self.g.read_bytes(pointer,20).hex()
                    if label.endswith('rtc_capture_state_update'):
                        pointer=regs['X00']
                        if not 0xa00000000<=pointer<=0xa20000000-4:
                            raise ValueError('RTC listener payload outside work RAM')
                        record['rtc_capture_state_hex']=self.g.read_bytes(pointer,4).hex()
                    if label.endswith(('capture_half_backend_argument','capture_full_backend_argument')):
                        pointer=regs['X00']
                        if not 0xa00000000<=pointer<=0xa20000000-12:
                            raise ValueError('capture backend argument outside work RAM')
                        record['backend_argument_hex']=self.g.read_bytes(pointer,12).hex()
                    if 'capture_' in label.removeprefix('capture_app_'):
                        record['capture_input_state_hex']=self.g.read_bytes(0xa03da6a70,0x110).hex()
                        record['release_permission_hex']=self.g.read_bytes(0xa03da68d0,0x1a0).hex()
                    if label.endswith('capture_release_submit'):
                        pointer=regs['X00']
                        if not 0xa00000000<=pointer<=0xa20000000-8:
                            raise ValueError('capture release argument outside work RAM')
                        record['release_argument_hex']=self.g.read_bytes(pointer,8).hex()
                    if label.endswith('changed_status_callback'):
                        record['status_hex']=self.g.read_bytes(regs['X00'],0x178).hex()
                    if label.endswith('app_key_event'):
                        header=self.g.read_bytes(regs['X02'],8);count=struct.unpack_from('<I',header,4)[0]
                        if count>32:raise ValueError('bounded original key event required')
                        record['event_hex']=self.g.read_bytes(regs['X02'],8+count*8).hex()
                    if label.endswith('state_input_dispatch'):
                        handler=regs['X08'];record['handler']=hex(handler)
                        if 0x40160000<=handler<0x41600000 and handler&3==0 and handler not in self.points:
                            self.arm(handler,'capture_app_actual_state_handler')
                    if label.endswith('controller_indirect'):
                        handler=regs['X02'];record['handler']=hex(handler)
                        if 0x40160000<=handler<0x41600000 and handler&3==0 and handler not in self.points:
                            self.arm(handler,'capture_app_actual_controller_handler')
                    if label.endswith('screen_indirect'):
                        handler=regs['X02'];record['handler']=hex(handler)
                        if 0x40160000<=handler<0x41600000 and handler&3==0 and handler not in self.points:
                            self.arm(handler,'capture_app_actual_screen_handler')
                    if label.endswith('screen_dispatch'):
                        record['screen_index']=int.from_bytes(self.g.read_bytes(0xa0330de30,4),'little')
                        pointer=regs['X00']
                        if 0xa00000000<=pointer<=0xa20000000-0x60:
                            record['screen_object_hex']=self.g.read_bytes(pointer,0x60).hex()
                    if label.endswith(('controller_preprocess_return','controller_contact_return','controller_aux_return')):
                        record['status_after_hex']=self.g.read_bytes(regs['X19'],0x180).hex()
                    if label.endswith(('queue_signal_return','queue_selected_record')):
                        record['queue_control_hex']=self.g.read_bytes(0xa032d9800,0x20).hex()
                        pointer=regs['X21']
                        if not (0xa032d9820<=pointer<0xa032d9820+16*0x188 and (pointer-0xa032d9820)%0x188==0):
                            raise ValueError('original key queue record outside its sixteen-slot ring')
                        record['queued_key_record_hex']=self.g.read_bytes(pointer,0x188).hex()
                    if label.endswith('ui_key_code_return'):
                        pointer=regs['X19']
                        if not 0xa00000000<=pointer<=0xa20000000-12:
                            raise ValueError('decoded key output outside work RAM')
                        record['key_code_output_hex']=self.g.read_bytes(pointer,12).hex()
                    if label.endswith('key_outer_gate'):
                        record['controller_hex']=self.g.read_bytes(0xa0323f480,0x390).hex()
                        record['app_hex']=self.g.read_bytes(0xa0282e310,0x720).hex()
                    continue
                row=self.active
                if label=='capture_key_consumer':
                    actual=self.g.read_bytes(regs['X00'],44)
                    row.update(consumer_cpu=cpu,consumer_pc=hex(pc),parsed_hex=actual.hex(),
                        return_pc=hex(regs['X30']))
                    self.g.check('complete requested contact state reaches original consumer',actual.hex()==row['expected_hex'])
                    self.arm(regs['X30'],'capture_key_return')
                elif label=='capture_key_return':
                    after=(dict(virtual_ns=runner.state(self.g,'runtime-clock-state')['virtual_ns'],
                                scope='compact preparation checkpoint; original contact payload and return retained')
                           if args.fast_capture and self.index<self.preparation_prefix
                           else self.snapshot('capture-contact-'+str(self.index)))
                    row.update(consumer_returned=True,after=after)
                    self.index+=1;self.active=None
                    gap=args.half_press_seconds*1000000000 if args.sequence=='shutter' and self.index==self.preparation_prefix+2 else 500000000
                    if row.get('label','').startswith('navigation-') and row.get('label','').endswith('-press'):
                        gap=args.navigation_press_ms*1000000
                    if row.get('label') in ('navigation-menu-release','navigation-ok-release'):
                        gap=2000000000
                    if args.post_capture_recovery and self.index==self.post_capture_start:
                        gap=10000000000
                    if 'hold_ns' in row:gap=row['hold_ns']
                    self.next_virtual=runner.state(self.g,'runtime-clock-state')['virtual_ns']+gap
                    if self.index==len(self.states):self.capture['all_inputs_consumed']=True
                    if not args.fast_capture or self.index%8==0 or self.index in (self.preparation_prefix,len(self.states)):
                        (self.g.out/'capture-sequence.partial.json').write_text(json.dumps(self.capture,indent=2)+'\n')
                    print('Original contact consumer returned: '+str(self.index),flush=True)
                    if self.index==len(self.states):self.capture['all_inputs_consumed']=True
            return handled

        def clock_if_ready(self,channels):
            if super().clock_if_ready(channels):return True
            now=time.monotonic()
            if now<self.next_probe or self.active is not None:return False
            self.next_probe=now+.25
            if self.index==len(self.states):
                virtual=runner.state(self.g,'runtime-clock-state')['virtual_ns']
                if args.navigation_file and not self.interactive_finished:
                    if virtual<self.next_virtual+2000000000:return False
                    if self.interactive_ready_at!=self.index:
                        self.g.qmp.command('stop')
                        label='navigation-ready-'+str(self.index)
                        item=self.snapshot(label);item['label']=label
                        self.capture['navigation_queue']['snapshots'].append(item)
                        self.interactive_ready_at=self.index
                        self.g.qmp.command('cont')
                        print('Original menu LCD ready: '+label,flush=True)
                    command=json.loads(args.navigation_file.read_text())
                    if set(command)-{'actions','finish','capture'} or not isinstance(command.get('actions'),list):
                        raise ValueError('bounded navigation JSON actions/finish/capture required')
                    if any(type(x) is not str or x not in ('menu','right','left','up','down','ok') for x in command['actions']) or len(command['actions'])>32:
                        raise ValueError('bounded navigation actions required')
                    if any(type(command.get(k,False)) is not bool for k in ('finish','capture')):
                        raise ValueError('navigation finish/capture must be booleans')
                    actions=command['actions']
                    if actions[:len(self.interactive_actions)]!=self.interactive_actions:
                        raise ValueError('navigation queue must preserve already consumed prefix')
                    extra=actions[len(self.interactive_actions):]
                    if extra:
                        from z9_navigation_input import states
                        self.states+=states(extra);self.preparation_prefix=len(self.states)
                        self.interactive_actions=list(actions)
                        self.capture['navigation_queue']['commands'].append(dict(actions=extra,virtual_ns=virtual))
                        self.capture['navigation_input']['actions']=menu_actions+actions
                        self.capture['navigation_input']['states']=self.preparation_prefix-self.quality_prefix
                        self.capture['all_inputs_consumed']=False
                        self.next_virtual=virtual+500000000
                    elif command.get('finish',False):
                        self.interactive_finished=True
                        self.capture['navigation_queue']['capture_requested']=command.get('capture',False)
                        if command.get('capture',False):
                            self.states+=self.contact_states;self.capture['all_inputs_consumed']=False
                            self.next_virtual=virtual+500000000
                    else:
                        # Preserve virtual menu state while the operator reads
                        # the LCD. No firmware timers/flags are changed. Poll
                        # in bounded15s windows and resume only between windows
                        # or when the append-only external queue changes.
                        self.g.qmp.command('stop');self.handle()
                        deadline=time.monotonic()+15
                        while time.monotonic()<deadline:
                            queued=json.loads(args.navigation_file.read_text())
                            if queued!=command:break
                            time.sleep(.1)
                        self.g.qmp.command('cont')
                    return False
                if args.finish_on_fresh_liveview:
                    recovery=self.capture['post_capture_recovery']
                    released=self.capture['inputs'][-1]['after']
                    raw=runner.state(self.g,'raw-pipeline-state')
                    lcd=runner.state(self.g,'engine1548-scanout-state')
                    ready=(len(recovery.get('visible_menus',{}))==2 and
                           len(recovery.get('returned_liveviews',{}))>=1 and
                           raw['frames']>=released['raw']['frames']+8 and
                           lcd['last_frame_has_video'] and
                           lcd['video_frames']>released['lcd']['video_frames'])
                    self.capture['final_liveview_gate']=dict(ready=bool(ready),
                        raw_frames=raw['frames'],released_raw_frames=released['raw']['frames'],
                        lcd_video_frames=lcd['video_frames'],virtual_ns=virtual)
                    if ready:
                        if args.capture_count > 1:
                            from capture_repeat_flow import completed, recovery as new_recovery
                            final=self.snapshot('capture-cycle-'+str(self.capture_cycle)+'-recovered')
                            self.capture['repeated_capture']['completed'].append(completed(
                                self.capture_cycle,self.capture_baseline,recovery,final,self.index))
                            print('Whole native photo cycle recovered: '+str(self.capture_cycle),flush=True)
                            if self.capture_cycle < args.capture_count:
                                from capture_recovery_flow import recovery_states
                                self.preparation_prefix=len(self.states)
                                self.states += [dict(row) for row in self.contact_states]
                                self.post_capture_start=len(self.states)
                                self.states += recovery_states()
                                self.capture['post_capture_recovery']=new_recovery(self.post_capture_start)
                                self.capture_cycle+=1
                                self.capture_baseline=None
                                self.capture['all_inputs_consumed']=False
                                self.next_virtual=virtual+500000000
                                return False
                            self.capture['repeated_capture']['all_cycles_recovered']=True
                        self.capture['settled_after_contacts']=True
                        session.stop.set()
                    return False
                if virtual>=self.next_virtual+args.settle_seconds*1000000000:
                    self.capture['settled_after_contacts']=True
                    session.stop.set()
                return False
            latest=self.g.data.get('latest_pipeline',{})
            if latest.get('raw',{}).get('frames',0)<8:return False
            preparation_in_progress=0<self.index<=self.preparation_prefix
            # A blackout after shutter press must not block the external
            # release/wake/menu inputs needed to recover from that blackout.
            if args.start_at=='liveview' and self.index<=self.preparation_prefix and not preparation_in_progress and (latest.get('lcd',{}).get('video_frames',0)<8 or
                    not latest.get('lcd',{}).get('last_frame_has_video',False)):return False
            if (args.quality_after_menu and self.index==self.quality_start and
                    not latest.get('lcd',{}).get('last_frame_has_video',False)):return False
            if (args.quality_after_wake and self.index==self.quality_start and
                    latest.get('lcd',{}).get('frames',0)<1):return False
            if (args.quality_after_wake and self.index==self.preparation_prefix and
                    not latest.get('lcd',{}).get('last_frame_has_video',False)):return False
            if (self.capture['exposure_input']['states'] and self.index==self.exposure_start and
                    not latest.get('lcd',{}).get('last_frame_has_video',False)):return False
            virtual=runner.state(self.g,'runtime-clock-state')['virtual_ns']
            if self.next_virtual is not None and virtual<self.next_virtual:return False
            if args.post_capture_ready_menu and self.index>self.post_capture_start:
                recovery=self.capture['post_capture_recovery']
                previous=self.states[self.index-1]['label']
                if previous=='navigation-menu-release':
                    from native_menu_screen import photo_menu
                    key=str(self.index)
                    if key not in recovery['visible_menus']:
                        candidate=self.g.out/'postshot-menu-candidate.ppm'
                        self.g.qmp.command('screendump',filename=str(candidate))
                        if not photo_menu(candidate):return False
                        recovery['visible_menus'][key]=self.snapshot('postshot-menu-ready-'+key)
                        print('Actual post-shot PHOTO menu visible',flush=True)
                if previous=='recovery-half-release' and recovery['visible_menus']:
                    key=str(self.index)
                    if key not in recovery['returned_liveviews']:
                        menu=list(recovery['visible_menus'].values())[-1]
                        raw=runner.state(self.g,'raw-pipeline-state')
                        lcd=runner.state(self.g,'engine1548-scanout-state')
                        if not (raw['frames']>=menu['raw']['frames']+8 and
                                lcd['last_frame_has_video'] and lcd['video_frames']>menu['lcd']['video_frames']):
                            return False
                        recovery['returned_liveviews'][key]=self.snapshot('postshot-liveview-ready-'+key)
                        print('Fresh RAW and LCD after post-shot menu return',flush=True)
            if args.post_capture_ready_menu and args.post_capture_recovery and self.index==self.post_capture_start:
                from capture_workflow_ready import evaluate
                released=self.capture['inputs'][-1]['after']
                receipt=evaluate(released,
                    runner.state(self.g,'raw-pipeline-state'),
                    runner.state(self.g,'engine1548-scanout-state'),
                    runner.state(self.g,'engine15e2-jpeg-state'),
                    runner.state(self.g,'engine151-raw-output-state'),
                    self.g.data.get('jpeg_completed_native_dumps',[]))
                receipt['virtual_ns']=virtual
                if args.capture_count > 1:
                    from capture_repeat_flow import ready as repeat_ready
                    receipt=repeat_ready(released,
                        runner.state(self.g,'raw-pipeline-state'),
                        runner.state(self.g,'engine1548-scanout-state'),
                        runner.state(self.g,'engine15e2-jpeg-state'),
                        runner.state(self.g,'engine151-raw-output-state'),
                        self.g.data.get('jpeg_completed_native_dumps',[]),self.capture_baseline)
                    receipt['virtual_ns']=virtual
                prior=self.capture['post_capture_recovery'].get('ready_gate',{})
                if receipt['ready']:
                    first=prior.get('first_ready_virtual_ns',virtual)
                    receipt['first_ready_virtual_ns']=first
                    receipt['ready']=virtual-first>=2000000000
                    receipt['settle_after_complete_graph_ns']=2000000000
                self.capture['post_capture_recovery']['ready_gate']=receipt
                if not receipt['ready']:return False
                print('Capture work complete and fresh RAW/LCD resumed; beginning post-shot menu roundtrips',flush=True)
            self.g.qmp.command('stop');self.handle()
            # Capture-control errors can precede release and the source stop.
            # Observe before the first shutter contact, not after full press.
            if args.trace_capture_recovery and self.recovery_observer is None and self.index>=self.preparation_prefix:
                from capture_recovery_flow import Observer
                self.recovery_observer=Observer(self.g,self.arm,runner.state,compact=args.compact_capture_observations)
            if self.index==0:self.capture['before']=self.snapshot('capture-before')
            if (args.quality_after_wake and self.states[self.index].get('label') in
                    ('navigation-ok-press','navigation-up-press')):
                # Observe the settled screen from the preceding operation,
                # before submitting the next key. This binds compression
                # selection to the actual original menu, not a recipe name.
                label='raw-setup-before-'+str(self.index)
                self.capture.setdefault('setup_screens',[]).append(dict(
                    state=self.index,label=label,snapshot=self.snapshot(label)))
            if args.capture_gpio and self.index==0:
                observed=self.g.data['capture-before-readiness']['capture_gpio_bindings'][:2]
                for item,bit,intid in zip(observed,(4,5),(59,60)):
                    irq=bytes.fromhex(item['irq_descriptor_hex'])
                    if (item['bank'],item['bit'],item['input_register'],
                        struct.unpack_from('<III',irq,4),struct.unpack_from('<Q',irq,0x18)[0]) != (
                        3,bit,'0xd15100c',(0,bit,intid),0x40fd9518):
                        raise ValueError('current native shutter GPIO binding differs from run446')
            row=dict(self.states[self.index],queued_virtual_ns=virtual,consumer_returned=False)
            if args.capture_count > 1 and self.index==self.preparation_prefix and self.capture_baseline is None:
                self.capture_baseline=dict(
                    raw_jobs=runner.state(self.g,'engine151-raw-output-state')['jobs'],
                    jpeg_jobs=runner.state(self.g,'engine15e2-jpeg-state')['jobs'],
                    start_contact=self.index,virtual_ns=virtual)
            row['capture_cycle']=self.capture_cycle
            self.capture['inputs'].append(row);self.active=row
            self.arm(CONSUMER,'capture_key_consumer')
            if args.trace_app_keys:
                for pc,label in self.app_points.items():
                    post_menu=(args.post_capture_recovery and self.index>=self.post_capture_start and
                               (label.startswith(('post_menu_','ui_')) or label in
                                ('screen_dispatch','screen_indirect','screen_handler_return')))
                    if label.startswith('post_menu_') and not post_menu:continue
                    # These low-frequency points own the actual RAW/JPEG
                    # snapshots and registered-callback evidence. Keep them
                    # even when repetitive application tracing is disabled.
                    if args.compact_capture_observations and not post_menu and label not in (
                            'changed_status_callback','app_key_event','ui_key_code_return','ui_final_key_code',
                            'capture151_isr_after_w1c','capture15e2_isr','capture15e2_prepare_call'):
                        continue
                    is_quality=self.quality_start<=self.index<self.quality_start+self.quality_prefix
                    if self.index<self.preparation_prefix and not is_quality and label!='ui_key_code_return':
                        continue
                    if self.index<self.preparation_prefix and label not in ('changed_status_callback','app_key_event','ui_key_code_return','ui_final_key_code','ui_state_remapped_key','screen_handler_return'):
                        continue
                    self.arm(pc,'capture_app_'+label)
            if args.capture_gpio:
                body=bytes.fromhex(row['body_hex'])
                levels=body[7]|(body[8]<<1)
                self.g.qmp.command('qom-set',path='/machine',property='capture-gpio-input',value=str(levels))
                row['capture_gpio_levels']=levels
            self.enqueue_external(bytes.fromhex(row['body_hex']),2)
            print('Queued original '+args.sequence+' contact state '+str(self.index+1),flush=True)
            self.g.qmp.command('cont')
            return False

        def close(self):
            self.capture['after']=self.snapshot('capture-final')
            before=self.capture.get('before',{})
            after=self.capture['after']
            released=(self.capture['inputs'][-1].get('after',{}) if self.capture['inputs'] else {})
            self.capture['post_release_raw_frames']=after['raw']['frames']-released.get('raw',{}).get('frames',after['raw']['frames'])
            self.capture['progress_from_first_contact']=bool(
                after['raw']['frames']>before.get('raw',{}).get('frames',after['raw']['frames']))
            self.capture['liveview_after_contacts']=bool(self.capture['all_inputs_consumed'] and
                after['lcd']['last_frame_has_video'] and
                after['lcd']['video_frames']>released.get('lcd',{}).get('video_frames',after['lcd']['video_frames']) and
                self.capture['post_release_raw_frames']>0)
            if args.post_capture_ready_menu:
                recovery=self.capture['post_capture_recovery']
                menus=recovery.get('visible_menus',{})
                if self.capture['all_inputs_consumed'] and menus:
                    menu=list(menus.values())[-1]
                    if (after['raw']['frames']>=menu['raw']['frames']+8 and after['lcd']['last_frame_has_video'] and
                            after['lcd']['video_frames']>menu['lcd']['video_frames']):
                        recovery['returned_liveviews'][str(self.index)]=after
                recovery['two_menu_roundtrips_verified']=bool(len(menus)==2 and
                    len(recovery.get('returned_liveviews',{}))==2 and self.capture['all_inputs_consumed'])
            self.capture['final_device_states']={name:runner.state(self.g,name) for name in
                ('engine1548-source-state','engine1548-state','engine1518-state','engine151-control-state')}
            super().close()

    runner.Guest=CaptureGuest;runner.Peer=CapturePeer
    output=args.output.resolve()
    options=argparse.Namespace(firmware=args.firmware,qemu=Path(manifest['binary']),
        raw=args.raw,output=output,seconds=args.seconds,menu_test=False)
    session=runner.Session()
    if args.fast_capture:
        from fast_capture_worker import worker
        worker(options,session,runner)
    else:runner.worker(options,session)
    record=json.loads((output/'result.json').read_text())
    sequence=record.get('capture_sequence',{})
    recovery=sequence.get('post_capture_recovery',{})
    print(json.dumps(dict(error=record.get('error'),result=str(output/'result.json'),
        contacts_consumed=sequence.get('all_inputs_consumed',False),
        two_postshot_menus=bool(recovery.get('two_menu_roundtrips_verified')),
        repeated_recovery=sequence.get('repeated_capture'),file_and_pixel_audit_required=True)))
    if record.get('error') or not sequence.get('all_inputs_consumed'):raise SystemExit(1)
    if args.post_capture_ready_menu and not recovery.get('two_menu_roundtrips_verified'):raise SystemExit(1)

if __name__=='__main__':main()
