# SPDX-License-Identifier: GPL-2.0-or-later
"""ZR original boot plus an explicit diagnostic MCU frame over shared PIO.

The MagicLamp input is read only. No firmware patches or CPU redirection.
The optional English startup preference explicitly records one guest cache edit.
GPIO inputs and GIC pulses are external lab fixtures, not measured MCU traffic.
"""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import re
import struct
import time
from contract_guest import ContractGuest
from probe import HERE, sha
from probe_zr_boot import MAIN, MAIN_SHA
from probe_graphics_image import FIXTURES, save
from deliver_mcu_frame import deliver
from probe_adc_capture import at
from mcu_frames import frames, status_body
from zr_mcu_bindings import BINDINGS


class ZRGuest(ContractGuest):
    """Reuse existing socket lifecycle and read-only debug transport."""
    def __exit__(self,kind,error,traceback):
        try:
            # Preserve independent MMIO diagnostics even if an optional
            # final capture fails before the later task snapshot.
            self.data['unknown_transactions']=[s for s in self.log().splitlines() if 'Z9_UNKNOWN' in s]
            if self.qmp and self.proc and self.proc.poll() is None:
                self.qmp.command('stop')
                if self.data.get('probe_arguments',{}).get('capture_transition_batch'):
                    for prop in ('primary-preview-reset-state','engine153-alternate-bank-state',
                                 'capture-stream-rearm-state','engine1540-alternate-bank-state',
                                 'engine15e2-alternate-bank-state'):
                        self.data[prop.replace('-state','').replace('-','_')+'_final']=json.loads(
                            self.qmp.command('qom-get',path='/machine',property=prop))
                if self.data.get('probe_arguments',{}).get('yuvcmp_config'):
                    self.data['yuvcmp_config_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='yuvcmp-config-state'))
                if self.data.get('probe_arguments',{}).get('capture_raw_pipeline'):
                    for prop in ('engine151-raw-output-state','engine1540-frame-pass-state',
                                 'engine1540-control-state','engine1544-neutral-copy-state',
                                 'engine152c-request-state','engine153-inplace-identity-state'):
                        self.data[prop.replace('-state','').replace('-','_')+'_final']=json.loads(
                            self.qmp.command('qom-get',path='/machine',property=prop))
                    side=self.data['engine151_raw_output_final']
                    if side.get('jobs') and not self.data.get('raw_side_native_dumps'):
                        amount=side['bytes']
                        if not 0<amount<=128*1024*1024:raise ValueError('Bounded full native RAW producer required')
                        # Whole 43/80 MiB dumps to the Windows mount can exceed
                        # the ordinary three-second QMP query deadline. Keep
                        # the owned guest stopped; preserve normal timeouts
                        # outside this bounded read-only capture operation.
                        previous_timeout=self.qmp.sock.gettimeout()
                        self.qmp.sock.settimeout(30)
                        self.data['raw_snapshot_qmp_timeout_seconds']=30
                        try:
                            for key in ('source','target'):
                                address=side[key]
                                if not 0x800000000<=address<=0x900000000-amount:
                                    raise ValueError('Actual RAW span outside image RAM')
                                path=self.out/f'engine151-raw-side-{key}.bin'
                                reply=self.qmp.hmp(f'pmemsave {address:#x} {amount:#x} "{path}"')
                                if reply:raise RuntimeError(reply)
                                if path.stat().st_size!=amount:
                                    raise ValueError('Incomplete actual RAW producer snapshot')
                        finally:
                            self.qmp.sock.settimeout(previous_timeout)
                if self.data.get('probe_arguments',{}).get('capture_pipeline'):
                    for prop in ('capture-nv16-pipeline-state','capture-thumbnail-nv16-state',
                                 'engine1542-ram-input-control-state','engine15e2-deferred-input-state',
                                 'engine15e2-preflight-state','engine15e2-limit-disabled-state',
                                 'primary-reset-parameter-retention-state'):
                        self.data[prop.replace('-state','').replace('-','_')+'_final']=json.loads(
                            self.qmp.command('qom-get',path='/machine',property=prop))
                if self.data.get('probe_arguments',{}).get('video_peripheral_control'):
                    for prop in ('video-peripheral-control-state','engine1530-config-state'):
                        self.data[prop.replace('-','_')+'_final']=json.loads(self.qmp.command(
                            'qom-get',path='/machine',property=prop))
                if self.data.get('probe_arguments',{}).get('engine152c_stream_receiver'):
                    for prop in ('engine152c-stream-receiver-state','engine152c-config-state'):
                        self.data[prop.replace('-','_')+'_final']=json.loads(self.qmp.command(
                            'qom-get',path='/machine',property=prop))
                if self.data.get('probe_arguments',{}).get('video_raw_transport'):
                    self.data['video_raw_transport_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='video-raw-transport-state'))
                if self.data.get('probe_arguments',{}).get('task1500_global_pulses'):
                    self.data['task1500_global_pulses_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='task1500-global-pulse-state'))
                if self.data.get('probe_arguments',{}).get('serial5_audio_idle_drain'):
                    self.data['serial5_audio_idle_drain_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='serial5-audio-idle-drain-state'))
                if self.data.get('probe_arguments',{}).get('video_forced_stops'):
                    self.data['video_forced_stops_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='video-forced-stop-state'))
                if self.data.get('probe_arguments',{}).get('video_backend_drains'):
                    self.data['video_backend_drains_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='video-backend-drain-state'))
                if self.data.get('probe_arguments',{}).get('backend_program_epochs'):
                    self.data['backend_program_epochs_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='backend-program-epoch-state'))
                if self.data.get('probe_arguments',{}).get('video_nr_resets'):
                    self.data['video_nr_resets_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='video-nr-reset-state'))
                if self.data.get('probe_arguments',{}).get('video_initial_resets'):
                    self.data['video_initial_reset_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='video-initial-reset-state'))
                if self.data.get('probe_arguments',{}).get('video_processing_config'):
                    self.data['video_processing_config_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='video-processing-config-state'))
                if self.data.get('probe_arguments',{}).get('dsp_boot_mailbox'):
                    self.data['dsp_boot_mailbox_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='dsp-boot-mailbox-state'))
                if self.data.get('probe_arguments',{}).get('dsp_motion_functional'):
                    self.data['dsp_motion_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='dsp-motion-state'))
                if self.data.get('probe_arguments',{}).get('dsp_correction_init'):
                    self.data['dsp_correction_init_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='dsp-correction-state'))
                if self.data.get('probe_arguments',{}).get('dsp_ram_aperture'):
                    self.data['dsp_ram_aperture_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='dsp-ram-aperture-state'))
                if self.data.get('probe_arguments',{}).get('capture_dsp_job_inputs'):
                    try:
                        from capture_dsp_job_inputs import capture
                        capture(self)
                    except Exception as capture_error:
                        self.data['dsp_source_input_capture_error']=repr(capture_error)
                        print('DSP input capture failed: '+repr(capture_error),flush=True)
                if self.data.get('probe_arguments',{}).get('capture_dsp_correction_inputs'):
                    try:
                        from capture_dsp_correction_inputs import capture as capture_correction
                        capture_correction(self)
                    except Exception as capture_error:
                        self.data['dsp_correction_input_capture_error']=repr(capture_error)
                        print('DSP correction capture failed: '+repr(capture_error),flush=True)
                if self.data.get('probe_arguments',{}).get('wave5_vpu'):
                    self.data['multi_io_counter_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='multi-io-counter-state'))
                    self.data['wave5_vpu_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='wave5-vpu-state'))
                    wave=self.data['wave5_vpu_final']
                    if wave.get('original_execution_required') and wave.get('boot_bytes'):
                        address=wave['boot_physical'];amount=wave['boot_bytes']
                        if not (0<amount<=4*1024*1024 and
                            (0xa00000000<=address<=0xa40000000-amount or 0x800000000<=address<=0x900000000-amount)):
                            raise ValueError('Original VPU code outside checked work/image RAM')
                        target=self.out/'zr-wave5-original-code-private.bin'
                        reply=self.qmp.hmp(f'pmemsave {address:#x} {amount:#x} "{target}"')
                        if reply or target.stat().st_size!=amount:raise RuntimeError('Original VPU code capture failed')
                        import zlib
                        if zlib.crc32(target.read_bytes())!=wave['boot_crc']:
                            raise ValueError('Original VPU code changed before capture')
                        self.data['wave5_original_code_capture']=dict(file=target.name,
                            sha256=sha(target),bytes=amount,physical_address=address,
                            private_vendor_input=True,instructions_executed=False,
                            scope='Actual code DMA submitted by original driver; virtual bus mapping, not physical ISA proof')
                if self.data.get('probe_arguments',{}).get('capture_processor_ram'):
                    from capture_processor_ram import capture as capture_processors
                    capture_processors(self)
                if self.data.get('probe_arguments',{}).get('engine151_capture_pixels'):
                    self.data['engine151_capture_pixels_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='engine151-capture-pixels-state'))
                    self.data['engine151_average_result_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='engine151-average-result-state'))
                    from capture_engine151_pixels import capture
                    capture(self)
                if self.data.get('probe_arguments',{}).get('engine15e2_config'):
                    self.data['engine15e2_config_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='engine15e2-config-state'))
                    from capture_engine15e2 import capture
                    capture(self)
                    self.data['engine15e2_jpeg_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='engine15e2-jpeg-state'))
                if self.data.get('probe_arguments',{}).get('engine153_config'):
                    self.data['engine153_config_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='engine153-config-state'))
                    self.data['engine153_frame_pass_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='engine153-frame-pass-state'))
                    from capture_engine153 import capture
                    capture(self,model='zr')
                if self.data.get('trace_capture_gpio'):
                    from capture_zr_gpio import capture
                    capture(self)
                if self.data.get('rtc_status_input'):
                    from capture_zr_rtc import capture
                    capture(self)
                if self.data.get('capture_gpio_model'):
                    self.data['capture_gpio_state_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='capture-gpio-state'))
                self.data['registers']=[self.qmp.hmp('info registers',cpu) for cpu in range(4)]
                if self.data.get('shared_z9_build'):
                    self.data['runtime_clock_final']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='runtime-clock-state'))
                self.data['device_states']={k:json.loads(self.qmp.command('qom-get',path='/machine',property=k))
                    for k in ('serial-state','graphics-state','multi-io-counter-state',
                              'engine1548-state','engine1548-scanout-state','zr-dsi-state','zr-lcd-control-state',
                              'zr-orientation-state','zr-secondary-state','event1508-front-state',
                              'control1380-state','engine150c-state','event1508-channel-state',
                              'event1508-aux0-state','event1508-aux1-state','zr-primary-bank1-state',
                              'event1508-global0-state','event1508-global1-state',
                              'event1508-group-state',
                              'event1508-command-state',
                              'event1508-aux-config-state','event1508-aux-status-state','stream154c-state',
                              'config150d-state','config150d-latched','engine150d-readback-state',
                              'engine1542-state','engine1543-control-state','engine151-state',
                              'engine1518-state','engine1548-source-state')}
                if self.data.get('probe_arguments',{}).get('audio_control_batch_clock'):
                    self.data['device_states']['serial-write-clock-state']=json.loads(
                        self.qmp.command('qom-get',path='/machine',property='serial-write-clock-state'))
                if self.data.get('probe_arguments',{}).get('audio_register_retention'):
                    self.data['device_states']['serial-audio-register-state']=json.loads(
                        self.qmp.command('qom-get',path='/machine',property='serial-audio-register-state'))
                if self.data.get('probe_arguments',{}).get('serial5_audio_config'):
                    self.data['device_states']['serial5-audio-config-state']=json.loads(
                        self.qmp.command('qom-get',path='/machine',property='serial5-audio-config-state'))
                if self.data.get('probe_arguments',{}).get('serial5_audio_input'):
                    self.data['device_states']['serial5-audio-sample-state']=json.loads(
                        self.qmp.command('qom-get',path='/machine',property='serial5-audio-sample-state'))
                if self.data.get('probe_arguments',{}).get('stream_isp_completion'):
                    self.data['device_states']['raw-pipeline-1514-completion-state']=json.loads(
                        self.qmp.command('qom-get',path='/machine',property='raw-pipeline-1514-completion-state'))
                if self.data.get('probe_arguments',{}).get('stream_source_completion'):
                    self.data['device_states']['raw-pipeline-151c-completion-state']=json.loads(
                        self.qmp.command('qom-get',path='/machine',property='raw-pipeline-151c-completion-state'))
                if self.data.get('probe_arguments',{}).get('stream_input_pair'):
                    self.data['device_states']['raw-pipeline-input-pair-state']=json.loads(
                        self.qmp.command('qom-get',path='/machine',property='raw-pipeline-input-pair-state'))
                if self.data.get('probe_arguments',{}).get('source_front_boundary'):
                    self.data['device_states']['event1508-front-boundary-state']=json.loads(
                        self.qmp.command('qom-get',path='/machine',property='event1508-front-boundary-state'))
                if self.data.get('nor_model'):
                    self.data['device_states']['nor-state']=json.loads(
                        self.qmp.command('qom-get',path='/machine',property='nor-state'))
                if self.data.get('raw_source'):
                    for property_name in ('raw-pipeline-state','statistics-state','engine151-control-state',
                                          'primary-reset-state','raw-source-boundary-state',
                                          'engine1524-state','config1524-state'):
                        self.data['device_states'][property_name]=json.loads(self.qmp.command(
                            'qom-get',path='/machine',property=property_name))
                if self.data.get('probe_arguments',{}).get('d980_config'):
                    self.data['device_states']['primary-d980-state']=json.loads(self.qmp.command(
                        'qom-get',path='/machine',property='primary-d980-state'))
                    if self.data.get('probe_arguments',{}).get('single_frame_input'):
                        self.data['device_states']['primary-d980-single-frame-state']=json.loads(self.qmp.command(
                            'qom-get',path='/machine',property='primary-d980-single-frame-state'))
                        for name in ('primary-d980-source-notify-state','primary-d980-prepared-start-state',
                                     'primary-d980-channel-boundary-state','event1508-channel-state',
                                     'primary-capture-direct-stop-state'):
                            self.data['device_states'][name]=json.loads(self.qmp.command('qom-get',path='/machine',property=name))
                        self.data['primary_irq_final']={hex(off):self.rd(0x150c0000+off) for off in
                            (0x200,0x204,0x208,0x20c,0x210,0x214,0x218,0x21c,0x220)}
                        self.data['source_control_final']={hex(off):self.rd(0x15080000+off) for off in
                            (0x10,0x18,0x20,0x28)}
                        self.data['channel_driver_final_hex']=self.read_bytes(0xa0280d968,0xa8).hex()
                    d980=self.data['device_states']['primary-d980-state']
                    if d980['frames']:
                        # QOM reports an already validated physical image-RAM
                        # DMA destination; read_bytes is deliberately reserved
                        # for CPU0 work-RAM virtual captures below.
                        address=d980['last_physical']
                        if not 0x800000000<=address<=0x900000000-256:
                            raise ValueError('D980 prefix outside physical image RAM')
                        self.data['primary_d980_output_head_hex']=ContractGuest.read_bytes(self,address,256).hex()
                        self.data['primary_d980_output_scope']='physical image-RAM DMA prefix; no CPU MMU translation'
                # Read the actual six read/write aperture pairs. A native
                # buffer may span a slot boundary; geometry alone cannot
                # establish whether the physical mapping is continuous.
                self.data['graphics_bus_windows']=[dict(
                    entry=entry,address=hex(0x140d0040+entry*0x20),
                    words=[int(self.qt_command(
                        f'readq {0x140d0040+entry*0x20+word*8:#x}')[0],0)
                        for word in range(3)]) for entry in range(12)]
                from observe_zr_startup import capture_ready_bitmap,capture_ready_state
                self.data['ready_bitmap_final']=capture_ready_bitmap(self,'zr-ready-bitmap-final')
                self.data['ready_state_final']=capture_ready_state(self,'zr-ready-state-final')
                app=save(self,'zr-app-control-final',0xa0282f4b8,0x748)
                self.data['app_state_final']=dict(current=struct.unpack_from('<I',app,0x2d0)[0],
                    previous=struct.unpack_from('<I',app,0x2d4)[0],
                    selected_object=hex(struct.unpack_from('<Q',app,0x2c8)[0]),raw_hex=app.hex())
                if self.data.get('diagnostic_mode_key_input'):
                    self.data['mode_key_final']=dict(
                        property280c_hex=save(self,'zr-mode-key-final-property280c',0xa03fea6d0,4).hex(),
                        property2906_hex=save(self,'zr-mode-key-final-property2906',0xa03feaa50,1).hex(),
                        key_state_hex=save(self,'zr-mode-key-final-status',0xa034141f4,52).hex())
                    # Observe the original mode abstraction as one bounded
                    # snapshot. Its backend need not be the MCU button body.
                    # No replacement callback, setting or switch is supplied.
                    pointer=struct.unpack('<Q',save(self,'zr-mode-interface-pointer',0xa030f9fe8,8))[0]
                    binding=dict(address='0xa030f9fe8',object=hex(pointer),
                        context_hex=save(self,'zr-shooting-context-final',0xa0343d880,48).hex(),
                        recording_hex=save(self,'zr-recording-state-final',0xa03e3d5a8,96).hex(),
                        timer_hex=save(self,'zr-recording-timer-final',0xa03e3d7a0,64).hex(),
                        scope='bounded original mode interface/context/recording RAM at owned guest stop; no physical role or recording acceptance')
                    if 0xa00000000<=pointer<=0xa40000000-80:
                        table=save(self,'zr-mode-interface-object',pointer,80)
                        binding.update(object_hex=table.hex(),
                            getter=hex(struct.unpack_from('<Q',table,0x30)[0]),
                            setter=hex(struct.unpack_from('<Q',table,0x38)[0]))
                    binding['configuration']=dict(
                        capability4b00_hex=save(self,'zr-mode-capability4b00-final',0xa03ff2220,4).hex(),
                        rec_roles1561_1562_hex=save(self,'zr-mode-rec-roles-final',0xa03fc7380,8).hex(),
                        config124_hex=save(self,'zr-mode-configuration124-final',0xa036ce84c,1).hex(),
                        config9_flags_hex=save(self,'zr-mode-configuration9-flags-final',0xa036a0d90,4).hex(),
                        mode_override_hex=save(self,'zr-mode-override-final',0xa034e71f8,1).hex(),
                        scope='C1.11 original setting pointers resolved from pinned DSID descriptors and configuration getter; read-only')
                    self.data['mode_interface_final']=binding
                self.data['ui_render_final_hex']=save(self,'zr-ui-render-final',0xa0305b7b0,0x400).hex()
                if self.data.get('ui_language_preference'):
                    from zr_ui_language_input import CACHE,LOCALE
                    self.data['ui_language_preference']['final_cache_hex']=save(self,'zr-language-final-cache',CACHE,4).hex()
                    self.data['ui_language_preference']['final_locale_hex']=save(self,'zr-language-final-locale',LOCALE,4).hex()
                ring=self.data['device_states']['graphics-state']['ring']
                if ring['fault'] and ring['command_phys']:
                    words=ring['descriptor'][0]+1
                    if 0<words<=4096:
                        save(self,'zr-failed-graphics-command',ring['command_phys'],words*4)
                if self.data.get('display_model'):
                    # Both shared units are observed; Z9's active unit is not
                    # evidence for which unit the ZR application will select.
                    offsets=(0x1200,0x1280,0x1210,0x2100,0x3100,0x2400,
                             0x2440,0x2444,0x2500,0x2504,0x2580,0x25c0,
                             0x2600,0x2640,0x2864,0x2868,0x286c)
                    self.data['display_unit_config']={str(unit):{
                        hex(off):self.rd(0x15480000+unit*0x4000+off)
                        for off in offsets} for unit in range(2)}
                    from observe_z9_display import capture_console
                    capture_console(self,'zr-console')
                    if self.data.get('capture_display_flow'):
                        if self.data.get('display_storage_scope')=='latched-lcd':
                            from capture_zr_lcd import capture_latched as capture_final
                        elif self.data.get('display_storage_scope')=='current-lcd':
                            from capture_zr_lcd import capture_final
                        else:
                            from capture_zr_secondary import capture_final
                        self.data['display_flow_final']=capture_final(self)
                        self.check('requested stopped display storage capture completes',True)
                if self.data.get('capture_tasks'):
                    from probe_tasks import capture
                    # Native 40189618/630 uses a057e2300 and the inverse
                    # arithmetic for 0x78-byte TCBs; 401899e4/ec saves SP/PC
                    # at +28/+30 and 401898cc restores the saved frame.
                    # 40f42204 loads worker/argument from wrapper +8/+28.
                    capture(self,'zr-tasks',bindings=dict(globals=0xa057e2200,
                        task_pointer=0xa057e2300,code_end=0x41490000,
                        thread_wrapper=0x40f42204,resume_pc=0x401898cc))
            self.data['unknown_transactions']=[s for s in self.log().splitlines() if 'Z9_UNKNOWN' in s]
            if self.data['unknown_transactions'] and self.qmp:
                regs={k:int(v,16) for k,v in re.findall(r'\b(X\d\d|PC|SP)=([0-9a-fA-F]+)',
                    self.qmp.hmp('info registers',0))}
                if 0xa00000000 <= regs['SP'] < 0xa40000000-0x200:
                    self.data['native_fault_stack_hex']=save(self,'native-fault-stack',regs['SP'],0x200).hex()
        except Exception as exc:
            self.data['final_capture_error']=repr(exc)
            if self.data.get('capture_display_flow'):
                self.data['checks'].append(dict(name='requested stopped display storage capture completes',passed=False))
        # An optional final MMU capture may fail after a strict stop on another
        # CPU. It must not suppress the independent read-only input receipt.
        from native_workflow_status import native_fault_observations
        faults=native_fault_observations(self.data)
        self.data['native_fault_reports_observed']=faults
        self.data['native_outcome']='fault reported' if faults else 'no fault report observed; acceptance pending'
        self.data['passed_scope']='harness and device assertions; camera_acceptance is separate'
        if self.data.get('raw_source'):
            self.data['raw_input_unchanged']=sha(Path(self.data['raw_source']['path']))==self.data['raw_source']['sha256']
        self.data['original_input_unchanged']=(sha(MAIN)==MAIN_SHA and
            MAIN.stat().st_mtime_ns==self.data['input_mtime_ns'])
        return super().__exit__(kind,error,traceback)

    def read_bytes(self, address, size):
        lower, upper = 0xa00000000, 0xa00000000+self.ram_mib*1024*1024
        if size < 1 or size > 1024*1024 or not lower <= address <= upper-size:
            raise ValueError('bounded work RAM capture required')
        virtuals = sorted({address,address+size-1,
            *range((address+0xfff)&~0xfff,address+size,0x1000)})
        responses = [self.qmp.hmp(f'gva2gpa {v:#x}',0) for v in virtuals]
        matches = [re.fullmatch(r'gpa: (0x[0-9a-f]+)\s*',s) for s in responses]
        if not all(matches): raise ValueError('CPU0 MMU translation failed')
        physicals = [int(m.group(1),16) for m in matches]
        physical = physicals[0]
        if not lower <= physical <= upper-size or any(
                p!=physical+v-address for p,v in zip(physicals,virtuals)):
            raise ValueError('noncontiguous or non-RAM MMU result')
        self.data.setdefault('memory_translations',[]).append(dict(
            virtual=hex(address),physical=hex(physical),bytes=size,cpu=0,
            responses=responses))
        return super().read_bytes(physical,size)

    def call(self,*args): raise RuntimeError('no CPU redirection in original boot probe')
    def write_bytes(self,*args): raise RuntimeError('no guest RAM writes in original boot probe')
    def wr(self,address,value):
        if address not in (0xd15100c,0xd151010):
            raise ValueError('only explicit external GPIO input levels may be written')
        return super().wr(address,value)

    def read_rom_bytes(self,address,size):
        if not 0<size<=0x2000 or not 0x40000000<=address<=0x48000000-size:
            raise ValueError('bounded physical ROM window required')
        for virtual in sorted({address,address+size-1,
                *range((address+0xfff)&~0xfff,address+size,0x1000)}):
            response=self.qmp.hmp(f'gva2gpa {virtual:#x}',0)
            if response.strip()!=f'gpa: {virtual:#x}':
                raise ValueError('ROM observation requires identity translation')
        self.data.setdefault('rom_observations',[]).append(dict(address=hex(address),bytes=size,cpu=0))
        return super().read_bytes(address,size)


def settle(g, seconds, *, observer=None):
    g.qmp.command('cont')
    deadline = time.monotonic()+seconds
    while time.monotonic()<deadline:
        if not g.qmp.command('query-status')['running']:
            if 'Z9_UNKNOWN' in g.log() or observer is None or not observer.handle():
                raise RuntimeError('unexpected original boot stop: '+g.log()[-500:])
            g.qmp.command('cont')
        time.sleep(.05)
    g.qmp.command('stop')


def validate_gpio(g):
    result = {}
    # Pointer globals are encoded by the ZR native MCU driver, not Z9 offsets.
    for name,slot,group,pin in (('tx_ready',0xa0304f740,3,2),
            ('tx_ack',0xa0304f748,4,3),('rx_ready',0xa0304f700,3,3)):
        ptr = struct.unpack('<Q',save(g,name+'-handle-pointer',slot,8))[0]
        raw = save(g,name+'-handle',ptr,0x28)
        actual_group,actual_pin = struct.unpack_from('<II',raw,4)
        table = save(g,name+'-input-map',0xa02e611c0+8*actual_group,8)
        base = struct.unpack('<Q',table)[0]
        result[name] = dict(slot=hex(slot),pointer=hex(ptr),group=actual_group,
            pin=actual_pin,read_enabled=raw[0xc],mmio=hex(base),raw_hex=raw.hex())
        g.check(name+' follows original ZR GPIO input mapping',actual_group==group and
            actual_pin==pin and raw[0xc]==1 and base==0xd151000+4*group)
    g.data['gpio_bindings']=result


def submit_primary_status(g, before, *, bank1=False, bit6=False):
    """Preserve the model's atomic stop gate across a host query/set race.

    A rejected status is not retried. Only the exact gate rejection followed
    by a closed gate and unchanged input count is recorded as a dropped pulse.
    All other errors remain fatal; no guest pause, state write or PC trigger.
    """
    source = g.data['external_bank1_status_input' if bank1 else
                    'external_primary_bit6_status_input' if bit6 else 'external_primary_status_input']
    state_property = 'zr-primary-bank1-state' if bank1 else 'engine150c-state'
    input_property = 'zr-primary-bank1-input' if bank1 else 'engine150c-bit6-input' if bit6 else 'engine150c-bit2-input'
    counter = 'inputs' if bank1 else 'bit6_inputs' if bit6 else 'bit2_inputs'
    expected = ('zr-primary-bank1-input requires active realized ZR model and 0x20/0x40/0x60'
                if bank1 else f'{input_property} requires an active realized bit{6 if bit6 else 2} model and value 1')
    try:
        g.qmp.command('qom-set',path='/machine',property=input_property,value='0x60' if bank1 else '1')
    except RuntimeError as exc:
        if not exc.args or exc.args[0] != dict(**{'class':'GenericError'}, desc=expected):
            raise
        after = json.loads(g.qmp.command('qom-get',path='/machine',property=state_property))
        if after[counter] != before[counter] or (after['active']&2 and not after['stop_requested']&2):
            raise
        source.setdefault('gate_rejections',[]).append(dict(
            input_count=after[counter],active_before=before['active'],active_after=after['active'],
            stop_requested_before=before['stop_requested'],stop_requested_after=after['stop_requested'],
            error=exc.args[0]))
        return
    source['pulses']+=1


def mode_input_ready(g,stage,waveform):
    """Pace user input by its original view consumption, never by sensor PC."""
    if waveform['pacing']=='host-gap' or stage==0:return dict(kind='host-gap')
    if waveform.get('sequence')=='keys':
        if waveform['pacing']=='consumer-return':
            from zr_key_sequence import consumed_by_native_key,consumer_rows
            previous=waveform['stages'][stage-1]
            evidence=consumed_by_native_key(waveform['input_states'],stage-1,
                consumer_rows(g.data),after_call=previous['after_consumer_call'])
            if evidence:previous['consumption_evidence']=evidence
            return evidence
        from zr_key_sequence import consumed,view_rows
        previous=waveform['stages'][stage-1]
        menu=g.data.get('mode_ready_screen_gate',{}).get('matched')
        evidence=consumed(waveform['input_states'],stage-1,view_rows(g.data),
                          after_call=previous['after_view_call'],
                          after_menu_call=previous.get('after_menu_call') if menu else None)
        if evidence:previous['consumption_evidence']=evidence
        return evidence
    rows=[x for key,observer in g.data.items() if key.endswith('observer') for x in observer.get('stops',[])]
    if waveform.get('sequence')=='fn2-left-center':
        previous=waveform['input_states'][stage-1]
        before=waveform['input_states'][stage-2] if stage>1 else dict(switches=[0x200,0,0],dials=[0,0,0,0])
        expected=tuple((now,old,now^old,now&~old,old&~now)
                       for now,old in zip(previous['switches'],before['switches']))
        returned={x['call_number']:x for x in rows if x['name']=='ui_mode_view_return'}
        for row in rows:
            if row['name']!='ui_mode_view_dispatch' or row['call_number'] not in returned:continue
            data=bytes.fromhex(row['normalized_key_hex'])
            if all(struct.unpack_from('<5I',data,8+index*20)==values for index,values in enumerate(expected)) and \
                    struct.unpack_from('<4i',data,0x58)==tuple(previous['dials']):
                return dict(kind='original-view-return',pc=returned[row['call_number']]['pc'],
                    call_number=row['call_number'],normalized_key_hex=row['normalized_key_hex'])
        return None
    if stage==3:
        matches=[x for x in rows if x['name']=='ui_mode_key_handler_done' and x['call_number']==3]
        if not matches:return None
        return dict(kind='original-hold-handler-completed',pc=matches[-1]['pc'],call_number=3)
    group,mask=waveform.get('switch_group',0),waveform.get('switch_mask',0x800)
    expected_sw=[]
    for index in range(3):
        base=0x200 if index==0 else 0
        if index==group:
            expected_sw.append((base|mask,base,mask,mask,0) if stage==1 else (base|mask,base|mask,0,0,0))
        else:expected_sw.append((base,base,0,0,0))
    expected_dials=tuple(waveform['dial_step'] if stage==2 and k==waveform['dial_index'] else 0 for k in range(4))
    returned={x['call_number']:x for x in rows if x['name']=='ui_mode_view_return'}
    for row in rows:
        if row['name']!='ui_mode_view_dispatch' or row['call_number'] not in returned:continue
        data=bytes.fromhex(row['normalized_key_hex'])
        if all(struct.unpack_from('<5I',data,8+index*20)==values for index,values in enumerate(expected_sw)) and \
                struct.unpack_from('<4i',data,0x58)==expected_dials:
            return dict(kind='original-view-return',pc=returned[row['call_number']]['pc'],
                call_number=row['call_number'],normalized_key_hex=row['normalized_key_hex'])
    return None


def service_mcu(g,seconds,*,observer=None,key_input=False):
    from service_z9_mcu import Peer
    if g.data.get('battery_query_peer'):
        class BatteryQueryPeer(Peer):
            def queue_reply(self,wire):
                from zr_battery_query_peer import queue_reply
                if queue_reply(self,wire):return
                super().queue_reply(wire)
        Peer=BatteryQueryPeer
    peer = Peer(g,bindings=BINDINGS,config_reply=True,all_mode_replies=True)
    if g.data.get('rtc_status_input'):
        from rtc_mcu_input import diagnostic_status
        body=diagnostic_status()
        peer.pending.append((7,body,frames(body,family=7)[0]))
        g.data['rtc_status_input'].update(body_hex=body.hex(),family=7,
            timestamp='2026-10-10T12:34:56',periodic_clock=False,
            decoder_evidence='expeed7-rtc-decoder-244.json')
        (g.out/'rtc_mcu_input.py').write_bytes((HERE/'rtc_mcu_input.py').read_bytes())
    if g.data.get('capture_gpio_model'):
        from capture_zr_gpio import ShutterInput
        shutter=ShutterInput(g)
        enqueue=peer.enqueue_external
        def with_shutter(body,family):
            shutter.apply(body,family)
            return enqueue(body,family)
        peer.enqueue_external=with_shutter
    peripheral_peers=[]
    if g.data.get('display_model'):
        from service_serial8 import WritePeer
        peripheral_peers=[WritePeer(g,channel=c,wire_bits=c,object_base=BINDINGS['serial_objects'],
            allow_dummy_rx=(c==9),
            max_batches=g.data['probe_arguments'].get('serial_write_batches',1024),
            max_words=16*g.data['probe_arguments'].get('serial_write_batches',1024),
            compact_observations=g.data['probe_arguments'].get('compact_serial_writes',False)) for c in (8,9)]
    if g.data['probe_arguments'].get('audio_control_clock'):
        from service_serial8 import WritePeer
        peripheral_peers.append(WritePeer(g,channel=2,wire_bits=16,
            object_base=BINDINGS['serial_objects'],allow_dummy_rx=False,
            max_batches=g.data['probe_arguments'].get('serial_write_batches',1024),
            max_words=16*g.data['probe_arguments'].get('serial_write_batches',1024),
            compact_observations=g.data['probe_arguments'].get('compact_serial_writes',False)))
    if key_input:
        body=bytearray(124);body[0]=1;body[4]=1
        for offset,value in g.data.get('mode_initial_selectors',{}).items():body[offset]=value
        if g.data.get('diagnostic_selector36') is not None:
            body[0x36]=g.data['diagnostic_selector36']
        g.data['key_input_candidate']=dict(family=2,body_hex=body.hex(),physical_semantics_verified=False)
        peer.enqueue_external(body,2)
    mode_waveform=None;mode_stage=0;mode_next=0
    initial_input_ready_next=0
    if g.data.get('diagnostic_mode_key_input'):
        step=g.data['diagnostic_mode_key_input']
        dial_index=g.data.get('mode_dial_index',1)
        control=g.data.get('mode_key_control','exp-mode')
        button,group,mask={'exp-mode':(14,0,0x800),'fn2':(60,2,0x4000),'menu':(67,1,0x8000)}[control]
        mode_waveform=dict(classification='diagnostic external '+control+' and signed dial',
            control=control,switch_group=group,switch_mask=mask,
            body_bytes=dict(exp_mode=14,button=button,dial=11+dial_index),dial_index=dial_index,dial_step=step,stages=[],
            pacing=g.data.get('mode_key_pacing','host-gap'),
            gate='observed original lens-mode modal; host scheduling only',
            physical_semantics_verified=False,guest_state_modified=False)
        if g.data.get('mode_key_sequence')=='fn2-left-center':
            mode_waveform.update(classification='diagnostic external Fn2, left and center presses/releases',
                sequence='fn2-left-center',input_states=[])
            for label,offset,group,mask in (('fn2-press',60,2,0x4000),('fn2-release',None,0,0),
                    ('left-press',35,0,0x40),('left-release',None,0,0),
                    ('center-press',42,0,0x8000),('center-release',None,0,0)):
                body=bytearray(124);body[0]=body[4]=1
                if offset is not None:body[offset]=1
                switches=[0x200,0,0];switches[group]|=mask
                mode_waveform['input_states'].append(dict(label=label,body_hex=body.hex(),switches=switches,dials=[0,0,0,0]))
        if g.data.get('mode_key_sequence')=='keys':
            from zr_key_sequence import input_states
            mode_waveform.update(classification='diagnostic external bounded key presses/releases',
                sequence='keys',input_states=input_states(g.data['mode_keys'],
                    continuous_shutter=g.data.get('mode_continuous_shutter',False),
                    initial_selectors=g.data.get('mode_initial_selectors',{})),
                initial_selectors={hex(k):v for k,v in g.data.get('mode_initial_selectors',{}).items()},
                repeated_states_require_fresh_consumption=True)
        g.data['mode_key_waveform']=mode_waveform
        if g.data.get('mode_start_gate')=='initial-consumer-lcd':
            mode_waveform['gate']='original complete initial MCU state returned and active LCD scanout; visible image acceptance separate'
    mode_stage_limit=6 if g.data.get('mode_key_sequence')=='fn2-left-center' else 4
    if g.data.get('mode_key_sequence')=='keys':mode_stage_limit=len(mode_waveform['input_states'])
    recording_pacing=None
    if g.data.get('mode_video_dispatch_pacing'):
        from zr_recording_pacing import RecordingPacing
        recording_pacing=RecordingPacing(g,mode_waveform['input_states'],
            g.data['mode_video_clip_seconds'],g.data['mode_video_dispatch_timeout_seconds'],
            observer=observer,peer=peer)
    live_keys=g.data.get('mode_keys_file')
    live_keys_finished=False
    live_keys_next=0
    live_preview_next=0
    if live_keys:
        mode_waveform['external_navigation_queue']=dict(path=live_keys,
            scope='bounded append-only original MCU keys; no guest setting edits',
            updates=[],finished=False)
    if g.data.get('diagnostic_selector36') is not None and mode_waveform:
        for state in mode_waveform.get('input_states',[]):
            body=bytearray.fromhex(state['body_hex']);body[0x36]=g.data['diagnostic_selector36']
            state['body_hex']=body.hex()
        mode_waveform['selector36_input']=dict(value=g.data['diagnostic_selector36'],
            classification='persistent external MCU selector candidate; physical meaning not yet proven')
    capture_ready_next=0
    capture_ready_gates={}
    liveview_return_next=0
    liveview_return_gates={}
    workflow_progress_next=0
    precapture_liveview_next=0
    precapture_liveview_gates={}
    if g.data.get('mode_precapture_liveview'):
        g.data['pre_capture_liveview_gates']=precapture_liveview_gates
    if g.data.get('mode_post_capture_ready'):
        from capture_workflow_ready import image_work
        (g.out/'capture_workflow_ready.py').write_bytes((HERE/'capture_workflow_ready.py').read_bytes())
        g.data['post_capture_image_gates']=capture_ready_gates
        g.data['post_capture_liveview_gates']=liveview_return_gates
    menu_ready=None;menu_ready_next=0
    if g.data.get('mode_ready_after_state') is not None:
        menu_ready=dict(classification='host screen observation gate; no guest modification',
            after_state=g.data['mode_ready_after_state'],expected_ppm_sha256=g.data['mode_ready_ppm_sha256'],
            matched=False,samples=[],guest_pc_trigger=False)
        g.data['mode_ready_screen_gate']=menu_ready
    video_ready_next=0
    if g.data.get('mode_video_ready_after_state')is not None:
        g.data['mode_video_visibility_gate']=dict(after_state=g.data['mode_video_ready_after_state'],
            matched=False,samples=[],guest_state_modified=False)
    focus_gates=g.data.get('mode_focus_after_state',{})
    tab_gates=g.data.get('mode_tab_after_state',{})
    focus_receipts={};tab_receipts={};focus_next=0;completion_deadline=None
    if focus_gates:g.data['mode_focus_screen_gates']=focus_receipts
    if tab_gates:g.data['mode_tab_screen_gates']=tab_receipts
    completion_screen=None;completion_screen_next=0
    if g.data.get('mode_completion_ppm_sha256'):
        completion_screen=dict(expected_ppm_sha256=g.data['mode_completion_ppm_sha256'],matched=False,samples=[],
            classification='host final native display observation; no guest edits')
        g.data['mode_completion_screen_gate']=completion_screen
    g.data['peer_reply_scope']='synthetic candidate replies to actual requests; no lens-status input'
    deadline = time.monotonic()+seconds
    from native_log_guard import NativeLogGuard
    fault_guard=NativeLogGuard(g.log_path)
    for peripheral in peripheral_peers:peripheral.fault_guard=fault_guard
    (g.out/'native_log_guard.py').write_bytes((HERE/'native_log_guard.py').read_bytes())
    from zr_input_clock import InputClock
    input_clock=InputClock(g,virtual=g.data.get('input_clock')=='virtual')
    primary_period=g.data.get('diagnostic_primary_input_period_ms')
    primary_next=input_clock.seconds
    bank1_period=g.data.get('diagnostic_bank1_input_period_ms')
    bank1_next=input_clock.seconds
    aux_period=g.data.get('diagnostic_aux0_input_period_ms')
    aux_next=input_clock.seconds
    aux1_period=g.data.get('diagnostic_aux1_input_period_ms')
    aux1_next=input_clock.seconds
    global26_period=g.data.get('diagnostic_global0_bit26_input_period_ms')
    global26_next=input_clock.seconds
    global10_period=g.data.get('diagnostic_global0_bit10_input_period_ms')
    global10_next=input_clock.seconds
    global26_gate=g.data.get('diagnostic_global0_bit26_input_gate','group-channel')
    aux_variant=g.data.get('diagnostic_aux0_input_variant','bit1')
    aux_bits=3 if aux_variant=='masked-bit0-and-bit1' else 2
    global_period=g.data.get('diagnostic_global0_input_period_ms')
    global_next=input_clock.seconds
    global_bits=0x90 if g.data.get('diagnostic_global0_input_variant')=='bit4-and-bit7' else 0x80
    drain=None
    if g.data.get('diagnostic_source_stop_drain'):
        from zr_source_stop_drain import SourceStopDrain
        drain=SourceStopDrain(g,g.data['diagnostic_source_stop_drain_kind'],g.data['diagnostic_source_stop_drain_limit'])
    channel_period=g.data.get('diagnostic_channel0_input_period_ms')
    channel_next=input_clock.seconds
    if global_period:
        g.data['external_global0_status_input']=dict(
            classification='host monotonic external global0 bit7; physical source unverified',
            period_ms=global_period,pulses=0,
            gate='native global0 mask bit7, group0 bit0 and channel0 bit0',
            status_input=str(global_bits),paired_boundary=global_bits==0x90,
            required_status_mask=global_bits,
            guest_pc_trigger=False,pixel_bytes=0)
    if channel_period:
        g.data['external_channel0_status_input']=dict(
            classification='host monotonic external channel0 status; physical source unverified',
            period_ms=channel_period,pulses=0,
            gate='native channel mask bit0, group0 bit0 and channel0 bit0',
            guest_pc_trigger=False,pixel_bytes=0)
    if aux_period:
        g.data['external_aux0_status_input']=dict(
            classification='host monotonic external auxiliary status; physical source unverified',
            period_ms=aux_period,pulses=0,gate='native auxiliary interrupt mask intersect allowed status bits',
            variant=aux_variant,allowed_bits=aux_bits,bit0_pulses=0,bit1_pulses=0,
            guest_pc_trigger=False,pixel_bytes=0)
    for key,period,gate in (
            ('external_aux1_status_input',aux1_period,'native second auxiliary mask bit0'),
            ('external_global0_bit10_status_input',global10_period,'native global0 bit10 mask only'),
            ('external_global0_bit26_status_input',global26_period,
             'native global0 bit26 mask'+(', group0 bit0 and channel0 bit0' if global26_gate=='group-channel' else ' only'))):
        if period:
            g.data[key]=dict(classification='host monotonic diagnostic status; physical source unverified',
                period_ms=period,pulses=0,gate=gate,guest_pc_trigger=False,pixel_bytes=0)
    if bank1_period:
        g.data['external_bank1_status_input']=dict(
            classification='host monotonic external bank1 bits5/6; physical source unverified',
            period_ms=bank1_period,pulses=0,gate='native primary active bit1, no stop request',
            guest_pc_trigger=False,pixel_bytes=0)
    if primary_period:
        g.data['external_primary_status_input']=dict(
            classification='host monotonic external bit2 status input; not sensor timing',
            period_ms=primary_period,pulses=0,gate='native primary active bit1, no stop request',
            guest_pc_trigger=False,pixel_bytes=0)
        if g.data.get('diagnostic_primary_bit6'):
            g.data['external_primary_bit6_status_input']=dict(
                classification='diagnostic external bit6; original ZR412aa44c routes041d0005; no pixels',
                period_ms=primary_period,pulses=0,gate='native primary active bit1, no stop request',
                guest_pc_trigger=False,pixel_bytes=0)
    for name,record in g.data.items():
        if name.startswith('external_') and name.endswith('_status_input'):
            record['clock']=input_clock.record['clock']
            if g.data.get('input_clock')=='virtual':
                record['classification']=record['classification'].replace('host monotonic','QEMU virtual time')
    try:
        g.qmp.command('cont')
        while time.monotonic()<deadline:
            if (g.runtime/'stop.request').exists():
                g.data['operator_stop_requested']=True
                print('Owned ZR stop requested; preserving incomplete workflow',flush=True)
                break
            if live_keys and time.monotonic()>=live_keys_next:
                from zr_key_sequence import parse_keys,input_states
                try:
                    request=json.loads(Path(live_keys).read_text())
                except json.JSONDecodeError:
                    # The external writer may be replacing the small file.
                    # No partial input is ever enqueued.
                    request=None
                if request is not None:
                    keys=request.get('keys')
                    if not isinstance(keys,list) or any(not isinstance(key,str) for key in keys):
                        raise ValueError('Live navigation requires an explicit bounded key list')
                    keys=parse_keys(','.join(keys))
                    current=g.data['mode_keys']
                    if keys[:len(current)]!=current or len(keys)<len(current):
                        raise ValueError('Live navigation may only append to the original key prefix')
                    finished=request.get('finished',False)
                    if not isinstance(finished,bool):raise ValueError('Navigation finished must be boolean')
                    if live_keys_finished and (keys!=current or not finished):
                        raise ValueError('Finished original navigation is immutable')
                    if keys!=current or finished!=live_keys_finished:
                        g.data['mode_keys']=keys
                        mode_waveform['input_states']=input_states(keys,
                            initial_selectors=g.data.get('mode_initial_selectors',{}))
                        mode_stage_limit=len(mode_waveform['input_states'])
                        live_keys_finished=finished
                        queue=mode_waveform['external_navigation_queue']
                        queue.update(finished=finished)
                        queue['updates'].append(dict(keys=list(keys),finished=finished,
                            queued_states=mode_stage,host_elapsed_seconds=seconds-(deadline-time.monotonic())))
                live_keys_next=time.monotonic()+.25
            if (live_keys and not live_keys_finished and mode_stage==mode_stage_limit
                    and time.monotonic()>=live_preview_next):
                g.qmp.command('screendump',filename=str(g.out/'live-navigation.ppm'))
                (g.out/'live-navigation-progress.json').write_text(json.dumps(dict(
                    queued_states=mode_stage,requested_states=mode_stage_limit,
                    finished=False,pacing=mode_waveform['pacing'],
                    scope='actual native screen and external queue progress; file acceptance separate'))+'\n')
                live_preview_next=time.monotonic()+1
            unknown=fault_guard.poll()
            g.data['host_log_guard']=fault_guard.receipt()
            if unknown:raise RuntimeError('unimplemented device during MCU service')
            status = g.qmp.command('query-status')
            if not status['running']:
                handled=observer.handle() if observer else False
                handled=peer.handle() or handled
                if not handled:raise RuntimeError('unrecognized MCU debug stop')
                g.qmp.command('cont')
            input_clock.sample()
            if (mode_waveform and g.data.get('mode_start_gate')=='initial-consumer-lcd' and
                    not g.data.get('mode_key_input_gate') and time.monotonic()>=initial_input_ready_next):
                from zr_key_sequence import consumer_rows
                from zr_input_start import initial_consumer_lcd_ready
                scanout=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1548-scanout-state'))
                ready=initial_consumer_lcd_ready(consumer_rows(g.data),
                    g.data['key_input_candidate']['body_hex'],scanout)
                if ready:g.data['mode_key_input_gate']=ready
                initial_input_ready_next=time.monotonic()+.5
            gate=mode_input_ready(g,mode_stage,mode_waveform) if mode_waveform and mode_stage<mode_stage_limit else None
            if gate and recording_pacing and not recording_pacing.advance(mode_stage,input_clock):
                gate=None
            visibility=g.data.get('mode_video_visibility_gate')
            if gate and visibility and mode_stage==visibility['after_state'] and not visibility['matched']:
                if time.monotonic()>=video_ready_next:
                    from zr_video_ready import visible_video_ready
                    candidate=g.runtime/'video-ready-candidate.ppm'
                    g.qmp.command('screendump',filename=str(candidate))
                    raw=json.loads(g.qmp.command('qom-get',path='/machine',property='raw-pipeline-state'))
                    lcd=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1548-scanout-state'))
                    ready=visible_video_ready(candidate,raw,lcd)
                    visibility['samples'].append(dict(ppm_sha256=sha(candidate),raw_frames=raw['frames'],
                        visible=bool(ready),host_elapsed_seconds=seconds-(deadline-time.monotonic())))
                    if ready:
                        target=g.out/'zr-video-ready.ppm'
                        with target.open('xb')as f:f.write(candidate.read_bytes())
                        visibility.update(matched=True,file=target.name,sha256=sha(target),evidence=ready)
                    video_ready_next=time.monotonic()+1
                if not visibility['matched']:gate=None
            if (gate and g.data.get('mode_precapture_liveview') and mode_stage and
                    mode_stage+1<mode_stage_limit and
                    mode_waveform['input_states'][mode_stage-1]['label']=='half-press' and
                    mode_waveform['input_states'][mode_stage+1]['label']=='full-press'):
                key=str(mode_stage)
                previous=precapture_liveview_gates.get(key,{})
                if time.monotonic()>=precapture_liveview_next and not previous.get('ready'):
                    raw=json.loads(g.qmp.command('qom-get',path='/machine',property='raw-pipeline-state'))
                    lcd=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1548-scanout-state'))
                    if g.data.get('probe_arguments',{}).get('lifecycle_observer'):
                        from capture_stream_progress import observe as observe_stream, due as stream_snapshot_due
                        records=g.data.setdefault('stream_progress_snapshots',[])
                        if stream_snapshot_due(records,raw,input_clock.seconds):
                            records.append(observe_stream(g,raw,input_clock.seconds))
                            (g.out/'stream-progress.json').write_text(json.dumps(records,indent=2)+'\n')
                    baseline=previous.get('baseline_raw_frames',raw['frames'])
                    needed=g.data.get('mode_precapture_liveview_frames',8)
                    ready=(raw['frames']>=baseline+needed and lcd['last_frame_has_video'])
                    precapture_liveview_gates[key]=dict(ready=bool(ready),raw_frames=raw['frames'],
                        baseline_raw_frames=baseline,required_fresh_frames=needed,lcd_video_frames=lcd['video_frames'],
                        virtual_seconds=input_clock.seconds,
                        first_virtual_seconds=previous.get('first_virtual_seconds',input_clock.seconds),
                        scope='hold original half contact until fresh liveview before full exposure')
                    precapture_liveview_next=time.monotonic()+.5
                    if ready:print('ZR fresh pre-shot RAW/LCD; allowing full exposure',flush=True)
                    limit=g.data.get('mode_liveview_timeout_seconds')
                    if limit and not ready and input_clock.seconds-precapture_liveview_gates[key]['first_virtual_seconds']>=limit:
                        raise TimeoutError(f'pre-shot liveview did not produce {needed} fresh frames within {limit} virtual seconds')
                if not precapture_liveview_gates.get(key,{}).get('ready'):gate=None
            if (gate and g.data.get('mode_post_capture_ready') and mode_stage and
                    mode_waveform['input_states'][mode_stage-1]['label']=='full-release'):
                previous=capture_ready_gates.get(str(mode_stage),{})
                if time.monotonic()>=capture_ready_next and not previous.get('settled'):
                    def device_state(name):
                        return json.loads(g.qmp.command('qom-get',path='/machine',property=name))
                    baseline=g.data['capture_cycles'][-1]['baseline']
                    receipt=image_work(device_state('engine15e2-jpeg-state'),
                        device_state('engine151-raw-output-state'),
                        g.data.get('jpeg_completed_native_dumps',[]),(6048,4032),baseline=baseline)
                    receipt['virtual_seconds']=input_clock.seconds
                    if receipt['ready']:
                        first=previous.get('first_ready_virtual_seconds',input_clock.seconds)
                        receipt['first_ready_virtual_seconds']=first
                        receipt['settled']=input_clock.seconds-first>=2
                    capture_ready_gates[str(mode_stage)]=receipt
                    capture_ready_next=time.monotonic()+.5
                if not capture_ready_gates.get(str(mode_stage),{}).get('settled'):gate=None
            if (gate and g.data.get('mode_post_capture_ready') and mode_stage>=2 and
                    mode_waveform['input_states'][mode_stage-1]['label']=='half-press' and
                    mode_waveform['input_states'][mode_stage-2]['label']=='menu-release' and
                    any(x.get('settled') for x in capture_ready_gates.values())):
                key=str(mode_stage)
                prior=liveview_return_gates.get(key,{})
                if time.monotonic()>=liveview_return_next and not prior.get('ready'):
                    baseline=next(s for s in reversed(g.data['display_console_captures'])
                                  if s['file']=='zr-key-state-%03d.ppm'%(mode_stage-1))
                    raw=json.loads(g.qmp.command('qom-get',path='/machine',property='raw-pipeline-state'))
                    lcd=json.loads(g.qmp.command('qom-get',path='/machine',property='engine1548-scanout-state'))
                    ready=(raw['frames']>=baseline['raw']['frames']+8 and lcd['last_frame_has_video'] and
                           lcd['video_frames']>baseline['scanout']['video_frames'])
                    liveview_return_gates[key]=dict(ready=bool(ready),raw_frames=raw['frames'],
                        baseline_raw_frames=baseline['raw']['frames'],lcd_video_frames=lcd['video_frames'],
                        virtual_seconds=input_clock.seconds,
                        first_virtual_seconds=prior.get('first_virtual_seconds',input_clock.seconds),
                        scope='hold external half contact until original menu return produces fresh RAW/LCD')
                    liveview_return_next=time.monotonic()+.5
                    if ready:print('ZR fresh RAW/LCD after post-shot menu; releasing half contact',flush=True)
                current=liveview_return_gates.get(key,{})
                if time.monotonic()>=workflow_progress_next:
                    (g.out/'workflow-progress.json').write_text(json.dumps(dict(
                        stage=mode_stage,pre_capture=g.data.get('pre_capture_liveview_gates',{}),
                        image_work=capture_ready_gates,menu_return=liveview_return_gates),indent=2)+'\n')
                    workflow_progress_next=time.monotonic()+2
                if not current.get('ready'):
                    limit=g.data.get('mode_liveview_timeout_seconds')
                    if limit and input_clock.seconds-current.get('first_virtual_seconds',input_clock.seconds)>=limit:
                        raise TimeoutError(f'post-shot liveview did not resume within {limit} virtual seconds')
                    gate=None
            if gate and menu_ready and mode_stage==menu_ready['after_state'] and not menu_ready['matched']:
                if time.monotonic()>=menu_ready_next:
                    candidate=g.runtime/'mode-ready-candidate.ppm'
                    g.qmp.command('screendump',filename=str(candidate))
                    digest=sha(candidate)
                    menu_ready['samples'].append(dict(ppm_sha256=digest,
                        host_elapsed_seconds=seconds-(deadline-time.monotonic())))
                    menu_ready['matched']=digest==menu_ready['expected_ppm_sha256']
                    if menu_ready['matched']:
                        target=g.out/'zr-mode-ready.ppm'
                        with target.open('xb') as f:f.write(candidate.read_bytes())
                        menu_ready.update(file=target.name,sha256=sha(target))
                    menu_ready_next=time.monotonic()+1
                if not menu_ready['matched']:gate=None
            if gate and (mode_stage in focus_gates or mode_stage in tab_gates):
                from zr_key_sequence import menu_focus_matches,menu_tab_matches
                is_tab=mode_stage in tab_gates
                gates,receipts=(tab_gates,tab_receipts) if is_tab else (focus_gates,focus_receipts)
                kind='tab' if is_tab else 'focus'
                receipt=receipts.setdefault(str(mode_stage),dict(
                    classification='host native menu highlight observation; no guest state edits',
                    after_state=mode_stage,matched=False,samples=[],
                    **{('visible_tab' if is_tab else 'visible_row'):gates[mode_stage]}))
                if not receipt['matched']:
                    if time.monotonic()>=focus_next:
                        candidate=g.runtime/'mode-focus-candidate.ppm'
                        g.qmp.command('screendump',filename=str(candidate));raw=candidate.read_bytes()
                        matched=(menu_tab_matches if is_tab else menu_focus_matches)(raw,gates[mode_stage])
                        receipt['samples'].append(dict(ppm_sha256=sha(candidate),matched=matched,
                            host_elapsed_seconds=seconds-(deadline-time.monotonic())))
                        if matched:
                            target=g.out/f'zr-{kind}-ready-{mode_stage:03d}.ppm'
                            with target.open('xb') as f:f.write(raw)
                            receipt.update(matched=True,file=target.name,sha256=sha(target))
                        focus_next=time.monotonic()+.5
                    if not receipt['matched']:gate=None
            if gate and g.data.get('mode_key_input_gate') and input_clock.running and input_clock.seconds>=mode_next:
                # enqueue_external may install a GDB breakpoint. RSP command
                # transport is synchronous and requires a stopped guest.
                # Preserve any real observer/peer stop before adding input.
                g.qmp.command('stop')
                if fault_guard.poll():raise RuntimeError('strict device fault before key input')
                if observer:observer.handle()
                peer.handle()
                if mode_waveform.get('sequence')=='keys' and mode_stage:
                    from observe_z9_display import capture_console
                    capture_console(g,f'zr-key-state-{mode_stage:03d}')
                if mode_waveform.get('sequence') in ('fn2-left-center','keys'):
                    body=bytes.fromhex(mode_waveform['input_states'][mode_stage]['body_hex'])
                else:
                    body=bytearray(124);body[0]=1;body[4]=1
                    if mode_stage<3:body[mode_waveform['body_bytes']['button']]=1
                    if mode_stage==1:body[mode_waveform['body_bytes']['dial']]=mode_waveform['dial_step']&255
                if (g.data.get('mode_post_capture_ready') and observer and
                        mode_waveform['input_states'][mode_stage]['label']=='full-press'):
                    cycles=g.data.setdefault('capture_cycles',[])
                    raw_state=json.loads(g.qmp.command('qom-get',path='/machine',property='engine151-raw-output-state'))
                    jpeg_state=json.loads(g.qmp.command('qom-get',path='/machine',property='engine15e2-jpeg-state'))
                    cycles.append(dict(cycle=len(cycles)+1,press_sequence=mode_stage+1,
                        release_sequence=mode_stage+2,baseline=dict(raw_jobs=raw_state['jobs'],jpeg_jobs=jpeg_state['jobs']),
                        queued_while_stopped=True,virtual_seconds=input_clock.seconds,
                        scope='actual device counters before enqueueing a new original full contact'))
                    observer.begin_capture_recovery()
                if (g.data.get('mode_post_capture_ready') and observer and mode_stage and
                        mode_waveform['input_states'][mode_stage]['label']=='half-press' and
                        mode_waveform['input_states'][mode_stage-1]['label']=='menu-release' and
                        any(x.get('settled') for x in capture_ready_gates.values())):
                    observer.begin_capture_recovery('postshot-menu-return')
                peer.enqueue_external(body,2)
                mode_waveform['stages'].append(dict(index=mode_stage,body_hex=body.hex(),
                    queued_while_stopped=True,pacing_evidence=gate,
                    input_clock=input_clock.record['clock'],queued_input_clock_seconds=input_clock.seconds,
                    queued_host_elapsed_seconds=seconds-(deadline-time.monotonic())))
                if mode_waveform.get('sequence')=='keys':
                    from zr_key_sequence import watermark,menu_watermark,consumer_watermark
                    mode_waveform['stages'][-1].update(sequence_id=mode_stage+1,
                        after_view_call=watermark(g.data),after_menu_call=menu_watermark(g.data),
                        after_consumer_call=consumer_watermark(g.data))
                mode_stage+=1;mode_next=input_clock.seconds+g.data.get('mode_key_gap_seconds',1)
                if (mode_waveform.get('sequence')=='keys' and
                        mode_waveform['input_states'][mode_stage-1]['key'].startswith('selector')):
                    mode_next=max(mode_next,input_clock.seconds+2)
                if (mode_waveform.get('sequence')=='keys' and
                        mode_waveform['input_states'][mode_stage-1]['label'].endswith('-release')):
                    mode_next=max(mode_next,input_clock.seconds+g.data.get('mode_key_release_gap_ms',0)/1000)
                if (mode_waveform.get('sequence')=='keys' and mode_stage==mode_stage_limit-1 and
                        g.data.get('mode_final_press_seconds') and
                        (not live_keys or mode_waveform['input_states'][mode_stage-1]['key']=='full')):
                    hold=g.data['mode_final_press_seconds']
                    mode_next=max(mode_next,input_clock.seconds+hold)
                    mode_waveform['stages'][-1]['minimum_press_seconds']=hold
                    if not input_clock.virtual:
                        mode_waveform['stages'][-1]['minimum_press_host_seconds']=hold
                if (mode_waveform.get('sequence')=='keys' and
                        mode_waveform['input_states'][mode_stage-1]['label']=='full-press' and
                        g.data.get('mode_full_press_seconds')):
                    # A following menu/half key must not move the shutter's
                    # requested hold to the end of the whole navigation list.
                    hold=g.data['mode_full_press_seconds']
                    mode_next=max(mode_next,input_clock.seconds+hold)
                    mode_waveform['stages'][-1]['minimum_full_press_seconds']=hold
                if (mode_waveform.get('sequence')=='keys' and
                        mode_waveform['input_states'][mode_stage-1]['label']=='movie-release' and
                        g.data.get('mode_movie_release_gap_seconds')):
                    gap=g.data['mode_movie_release_gap_seconds']
                    mode_next=max(mode_next,input_clock.seconds+gap)
                    mode_waveform['stages'][-1]['minimum_movie_release_gap_seconds']=gap
                g.qmp.command('cont')
            if (mode_waveform and mode_waveform.get('sequence')=='keys' and mode_stage==mode_stage_limit and
                    (not live_keys or live_keys_finished) and
                    g.data.get('mode_completion_settle_seconds') is not None):
                from zr_key_sequence import consumed,view_rows
                last=mode_waveform['stages'][-1]
                evidence=mode_input_ready(g,mode_stage,mode_waveform)
                if evidence and completion_screen and not completion_screen['matched']:
                    if time.monotonic()>=completion_screen_next:
                        candidate=g.runtime/'mode-completion-candidate.ppm'
                        g.qmp.command('screendump',filename=str(candidate));digest=sha(candidate)
                        completion_screen['samples'].append(dict(ppm_sha256=digest,
                            host_elapsed_seconds=seconds-(deadline-time.monotonic())))
                        if digest==completion_screen['expected_ppm_sha256']:
                            target=g.out/'zr-mode-completion-ready.ppm'
                            with target.open('xb') as f:f.write(candidate.read_bytes())
                            completion_screen.update(matched=True,file=target.name,sha256=sha(target))
                        completion_screen_next=time.monotonic()+.5
                if evidence and completion_deadline is None and (not completion_screen or completion_screen['matched']):
                    last['consumption_evidence']=evidence
                    completion_deadline=time.monotonic()+g.data['mode_completion_settle_seconds']
                if completion_deadline is not None and time.monotonic()>=completion_deadline:
                    mode_waveform['ended_after_all_consumption']=True
                    break
            if primary_period and input_clock.running and input_clock.seconds>=primary_next:
                primary=json.loads(g.qmp.command('qom-get',path='/machine',property='engine150c-state'))
                if primary['active']&2 and not primary['stop_requested']&2:
                    submit_primary_status(g,primary)
                    if g.data.get('diagnostic_primary_bit6'):
                        submit_primary_status(g,primary,bit6=True)
                # Coalesce time spent paused by observers, never burst missed
                # pulses or trigger from a guest PC / event-wait location.
                primary_next=input_clock.seconds+primary_period/1000
            if bank1_period and input_clock.running and input_clock.seconds>=bank1_next:
                bank1=json.loads(g.qmp.command('qom-get',path='/machine',property='zr-primary-bank1-state'))
                if bank1['active']&2 and not bank1['stop_requested']&2:
                    submit_primary_status(g,bank1,bank1=True)
                bank1_next=input_clock.seconds+bank1_period/1000
            if aux_period and input_clock.running and input_clock.seconds>=aux_next:
                aux=json.loads(g.qmp.command('qom-get',path='/machine',property='event1508-aux0-state'))
                bits=aux['mask']&aux_bits
                if bits:
                    g.qmp.command('qom-set',path='/machine',property='event1508-aux0-input',value=str(bits))
                    receipt=g.data['external_aux0_status_input']
                    receipt['pulses']+=1
                    receipt['bit0_pulses']+=int(bool(bits&1))
                    receipt['bit1_pulses']+=int(bool(bits&2))
                aux_next=input_clock.seconds+aux_period/1000
            if aux1_period and input_clock.running and input_clock.seconds>=aux1_next:
                aux1=json.loads(g.qmp.command('qom-get',path='/machine',property='event1508-aux1-state'))
                if aux1['mask']&1:
                    g.qmp.command('qom-set',path='/machine',property='event1508-aux1-input',value='1')
                    g.data['external_aux1_status_input']['pulses']+=1
                aux1_next=input_clock.seconds+aux1_period/1000
            if global26_period and input_clock.running and input_clock.seconds>=global26_next:
                global0=json.loads(g.qmp.command('qom-get',path='/machine',property='event1508-global0-state'))
                if global0['mask']&0x4000000 and (global26_gate=='mask-only' or
                        (g.rd(0x15080010)&1 and g.rd(0x15080028)&1)):
                    g.qmp.command('qom-set',path='/machine',property='event1508-global0-input',value='67108864')
                    g.data['external_global0_bit26_status_input']['pulses']+=1
                global26_next=input_clock.seconds+global26_period/1000
            if global10_period and input_clock.running and input_clock.seconds>=global10_next:
                global0=json.loads(g.qmp.command('qom-get',path='/machine',property='event1508-global0-state'))
                if global0['mask']&0x400:
                    g.qmp.command('qom-set',path='/machine',property='event1508-global0-bit10-input',value='1024')
                    g.data['external_global0_bit10_status_input']['pulses']+=1
                global10_next=input_clock.seconds+global10_period/1000
            if global_period and input_clock.running and input_clock.seconds>=global_next:
                global0=json.loads(g.qmp.command('qom-get',path='/machine',property='event1508-global0-state'))
                if global0['mask']&global_bits==global_bits and g.rd(0x15080010)&1 and g.rd(0x15080028)&1:
                    g.qmp.command('qom-set',path='/machine',property='event1508-global0-input',value=str(global_bits))
                    g.data['external_global0_status_input']['pulses']+=1
                global_next=input_clock.seconds+global_period/1000
            if drain:drain.tick(input_clock)
            if channel_period and input_clock.running and input_clock.seconds>=channel_next:
                channel=json.loads(g.qmp.command('qom-get',path='/machine',property='event1508-channel-state'))
                if channel['mask']&1 and g.rd(0x15080010)&1 and g.rd(0x15080028)&1:
                    g.qmp.command('qom-set',path='/machine',property='event1508-channel-input',value='1')
                    g.data['external_channel0_status_input']['pulses']+=1
                channel_next=input_clock.seconds+channel_period/1000
            channels = json.loads(g.qmp.command('qom-get',path='/machine',property='serial-state'))
            if g.data['probe_arguments'].get('audio_control_batch_clock'):
                audio=json.loads(g.qmp.command('qom-get',path='/machine',property='serial-write-clock-state'))
                if audio['fault']:
                    g.data['audio_batch_clock_rejection']=audio
                    raise RuntimeError('original audio write clock rejected: '+audio['fault'])
            clock_stop=peer.clock_if_ready(channels)
            for peripheral in peripheral_peers:
                clock_stop=peripheral.clock_if_ready(channels[peripheral.channel],resume=False) or clock_stop
            if clock_stop:
                if fault_guard.poll():raise RuntimeError('strict device fault during peripheral service')
                if observer:observer.handle()
                peer.handle()
                g.qmp.command('cont')
            time.sleep(.005)
        g.qmp.command('stop')
        if mode_waveform and mode_waveform.get('sequence')=='keys':
            from zr_key_sequence import consumed,view_rows
            if observer:observer.handle()
            if mode_stage:
                last=mode_waveform['stages'][-1]
                evidence=mode_input_ready(g,mode_stage,mode_waveform)
                if evidence:last['consumption_evidence']=evidence
                from observe_z9_display import capture_console
                capture_console(g,f'zr-key-state-{mode_stage:03d}')
            mode_waveform['all_consumed']=(mode_stage==mode_stage_limit and
                (not live_keys or live_keys_finished) and
                all('consumption_evidence' in item for item in mode_waveform['stages']))
            g.check('bounded key sequence consumed by distinct original handlers',mode_waveform['all_consumed'])
        peer.handle()
    finally:
        g.qmp.command('stop')
        fault_guard.close()
        peer.close()
        if observer:observer.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--name',required=True)
    ap.add_argument('--lifecycle-observer',
                    help='fingerprinted read-only non-stopping lifecycle bindings JSON')
    ap.add_argument('--source-front-boundary', action='store_true',
                    help='Opt-in idle FRONT0 request/one channel boundary; no DMA completion')
    ap.add_argument('--source-front-global-end', action='store_true',
                    help='Pair the same idle request with global end status; no image-ready event')
    ap.add_argument('--source-output0-boundary', action='store_true',
                    help='Keep explicit output-group lane0 running independently during input pause')
    ap.add_argument('--shared-z9-build',action='store_true',
                    help='use the isolated, fingerprinted build of published Z9 plus the ZR subclass')
    ap.add_argument('--service-core-events',action='store_true',
                    help='explicit Z9 CPU3 WFE/SEV model with four CPUs and instruction clock')
    ap.add_argument('--input-clock',choices=('host','virtual'),default='host',
                    help='clock for peripheral status periods and key hold times; host run limit stays bounded')
    ap.add_argument('--status',choices=('zero','enum2'),default='enum2')
    ap.add_argument('--post-seconds',type=int,choices=(0,10,20,30,60,90,180,360,600,900),default=0)
    ap.add_argument('--mcu-peer',action='store_true',help='explicit bounded synthetic peer for actual requests')
    ap.add_argument('--rtc-status',action='store_true',
                    help='explicit deterministic family7 RTC sample; independently verified ZR decoder')
    ap.add_argument('--nor',action='store_true',help='existing volatile shared NOR model; original input file stays read only')
    ap.add_argument('--sd-empty',action='store_true',help='explicit inactive card-detect input; no media model')
    ap.add_argument('--battery',action='store_true',help='synthetic family4/type3 112-byte source1 status')
    ap.add_argument('--battery-query-peer',action='store_true',help='request-bound declared status; no image/codec completion')
    ap.add_argument('--retained-header-start',action='store_true',help='retired selected video header START; pixel readiness stays strict')
    ap.add_argument('--battery-input',choices=('zero','source1'),default='source1',
                    help='explicit byte4 variant; source1 is a label, not verified battery semantics')
    ap.add_argument('--key-input',action='store_true',help='candidate family2/type1 complete state; requires peer')
    ap.add_argument('--stream-isp-completion',action='store_true',
                    help='experimental 1514 completion after actual streaming RAW pixel DMA')
    ap.add_argument('--stream-source-completion',action='store_true',
                    help='functional 151c source completion after actual streaming RAW pixel DMA')
    ap.add_argument('--stream-input-pair',action='store_true',
                    help='functional primary input pair notification after actual streaming RAW pixel DMA')
    ap.add_argument('--secondary-source-timing',action='store_true',
                    help='optional independent channel-one timing input; physical timing unverified')
    ap.add_argument('--diagnostic-selector36',type=int,choices=(0,1),
                    help='persistent external body[0x36] selector candidate; no guest property edits')
    ap.add_argument('--mode-initial-selectors',
                    help='explicit initial hex-field:enum pairs, retained until selector keys change them; physical wiring unverified')
    ap.add_argument('--mode-start-gate',choices=('photo-modal','initial-consumer-lcd'),default='photo-modal',
                    help='external key readiness only: legacy photo modal or original initial MCU return plus active LCD scanout')
    ap.add_argument('--audio-control-clock',action='store_true',
                    help='opt-in ZR channel2/16bit clock for exact native writes with discarded RX; no PCM or codec identity replies')
    ap.add_argument('--audio-control-batch-clock',action='store_true',
                    help='default-off QEMU clock for bounded original audio write-only descriptors, every FIFO word validated; no codec/PCM')
    ap.add_argument('--serial5-audio-input',choices=('silence',),
                    help='explicit zero-amplitude RX/TX captured sample input; no PCM DMA or audio recording claimed')
    ap.add_argument('--serial5-audio-config',action='store_true',
                    help='default-off five-channel audio configuration and request readback, without PCM/DMA/IRQ completion')
    ap.add_argument('--serial5-audio-idle-drain',action='store_true',
                    help='explicit disabled-channel empty drain, not enabled PCM/FIFO completion')
    ap.add_argument('--audio-register-retention',action='store_true',
                    help='explicit neutral-reset register retention through original serial FIFO/IRQ; no DSP/PCM or physical reset claim')
    ap.add_argument('--mode-key-input',type=int,choices=(-1,1),
                    help='explicit EXP_MODE press/dial/hold/release after the original lens-mode modal')
    ap.add_argument('--mode-key-control',choices=('exp-mode','fn2','menu'),default='exp-mode',
                    help='original decoder EXP_MODE, Fn2 or MENU input; physical wiring unverified')
    ap.add_argument('--mode-key-sequence',choices=('dial','fn2-left-center','keys'),default='dial',
                    help='explicit Fn2 release then left and center, each with an original-view gate')
    ap.add_argument('--mode-keys',help='bounded comma-separated keys; each press/release waits for a fresh view return')
    ap.add_argument('--mode-ready-after-state',type=int,
                    help='optional diagnostic wait for a known native screen before the next state')
    ap.add_argument('--mode-ready-ppm-sha256',help='exact reference native PPM digest for the explicit host screen gate')
    ap.add_argument('--mode-video-ready-after-state',type=int,
                    help='wait for actual original video pixels after warmup contacts, before mode/menu keys')
    ap.add_argument('--video-forced-stops',action='store_true',
                    help='original video request/hold/kick and unused decoded-frame cancellation; default off')
    ap.add_argument('--video-backend-drains',action='store_true',
                    help='held receiver/decoder stop IRQ, independent W1C and fresh restart; default off')
    ap.add_argument('--backend-program-epochs',action='store_true',
                    help='opaque core program retention/replacement after frontend reset; no codec execution claim')
    ap.add_argument('--video-nr-resets',action='store_true',
                    help='empty REC NR reset lifecycle after source/backend owners retire; default off')
    ap.add_argument('--video-initial-resets',action='store_true',
                    help='explicit unarmed-target setup/fresh NR release and observed empty reset15; preserves upstream owners')
    ap.add_argument('--video-processing-config',action='store_true',
                    help='original global/two-port/eight-slot processing initialization; no processing results')
    ap.add_argument('--wave5-vpu',action='store_true',
                    help='explicit virtual 5210-compatible HEVC backend; physical identity and microcode execution unverified')
    ap.add_argument('--wave5-host-codec-diagnostic',action='store_true',
                    help='explicit x265 functional recording backend; original VPU microcode is not executed')
    ap.add_argument('--dsp-boot-mailbox',action='store_true',
                    help='opt-in functional DSP startup reply through original ARM mailbox/IRQ; no DSP instruction execution')
    ap.add_argument('--dsp-ram-aperture',action='store_true',
                    help='explicit bootloader input covering work RAM in each first DSP bus aperture; physical mapping unmeasured')
    ap.add_argument('--dsp-session-init',action='store_true',
                    help='explicit functional workspace/module initialization backend; no DSP instruction or inference execution')
    ap.add_argument('--capture-dsp-job-inputs',action='store_true',
                    help='read pending original DSP image input/workspace/result RAM at owned stop; no job completion')
    ap.add_argument('--capture-dsp-correction-inputs',action='store_true',
                    help='read bounded pending DSP0 correction parameter RAM at owned stop; no initialization supplied')
    ap.add_argument('--dsp-motion-functional',action='store_true',
                    help='explicit host FAST9/SAD motion through original image-job ABI; no original CEVA arithmetic')
    ap.add_argument('--dsp-correction-init',action='store_true',
                    help='explicit actual calibration context and generic same-CFA plan; no original ISA or pixel correction')
    ap.add_argument('--wave5-irq',type=int,default=0,
                    help='explicit original-driver GIC SPI binding; 0 retains polling, physical silicon identity unverified')
    ap.add_argument('--raw-lossless14',action='store_true',
                    help='explicit shared F0 entropy encoder for verified 14-bit/2048-seed NEF profile; physical codec unverified')
    ap.add_argument('--capture-processor-ram',action='store_true',
                    help='private read-only modeled processor load RAM at owned stop; no code or completion supplied')
    ap.add_argument('--mode-key-gap-seconds',type=int,choices=(0,1,3,5),default=1,
                    help='minimum host gap between completed input states; asynchronous menus may still be busy')
    ap.add_argument('--mode-final-press-seconds',type=int,choices=(2,10,30,60),
                    help='hold final external key before release; host timing, no guest state edits')
    ap.add_argument('--mode-full-press-seconds',type=int,choices=(1,2,5,10),
                    help='hold every full shutter press on the selected input clock, including before later menu keys')
    ap.add_argument('--mode-precapture-liveview',action='store_true',
                    help='hold the half contact preceding full exposure until new RAW/LCD exists')
    ap.add_argument('--mode-precapture-liveview-frames',type=int,choices=(8,30,60),default=8,
                    help='fresh native preview frames required before sending full shutter')
    ap.add_argument('--mode-continuous-shutter',action='store_true',
                    help='retain HALF while FULL is pressed/released in one half/full/half sequence')
    ap.add_argument('--mode-video-dispatch-pacing',action='store_true',
                    help='wait for original VIDEO next-start/stop selector after each complete shutter release; not file acceptance')
    ap.add_argument('--mode-video-clip-seconds',type=int,choices=(5,10,30),default=5,
                    help='minimum selected-input-clock interval in native stop-selectable state before next shutter')
    ap.add_argument('--mode-video-dispatch-timeout-seconds',type=int,choices=(30,60,90),default=60,
                    help='bounded selected-input-clock deadline for original VIDEO dispatch selector transitions')
    ap.add_argument('--mode-liveview-timeout-seconds',type=int,choices=(10,15,30,60),
                    help='bounded virtual deadline for fresh post-shot menu-return frames')
    ap.add_argument('--mode-post-capture-ready',action='store_true',
                    help='before post-shot keys, wait for the complete native RAW/JPEG graph and two virtual seconds')
    ap.add_argument('--mode-movie-release-gap-seconds',type=int,choices=(2,5,10),
                    help='wait on the selected input clock after each REC release before later keys; no recording completion assumed')
    ap.add_argument('--mode-focus-after-state',help='diagnostic native highlight gates, e.g.4:2,6:3,8:4,10:5')
    ap.add_argument('--mode-tab-after-state',help='native tab highlight gates, e.g.20:0,22:1,24:2')
    ap.add_argument('--ui-language',choices=('english',),help='explicit four-byte lab cached preference before original language initialization; not persistent NVM')
    ap.add_argument('--mode-completion-ppm-sha256',help='wait for this actual native final screen before completion settlement')
    ap.add_argument('--mode-completion-settle-seconds',type=int,choices=(5,10,20),
                    help='end after every original input consumption and this bounded display settlement')
    ap.add_argument('--mode-dial-index',type=int,choices=(0,1),default=1,
                    help='decoder dial0/body11 or dial1/body12; physical dial identity unverified')
    ap.add_argument('--mode-key-pacing',choices=('host-gap','view-return','consumer-return'),default='host-gap',
                    help='original view or complete native key-receiver return; UI/file checks remain separate')
    ap.add_argument('--trace-mode-key-dispatch',action='store_true',
                    help='bounded read-only key difference and selected application callbacks')
    ap.add_argument('--trace-mode-view-dispatch',action='store_true',
                    help='bounded original UI kind3 view dispatch; requires mode key tracing')
    ap.add_argument('--trace-mode-view-controls',action='store_true',
                    help='observe original kind3 control queue gate and decoded key action')
    ap.add_argument('--trace-mode-property-writes',action='store_true',
                    help='bounded original property280c stores; no RAM or CPU writes')
    ap.add_argument('--mode-property-watch',choices=('280c','2423'),default='280c',
                    help='output exposure mode or pinned upstream source property; requires tracing')
    ap.add_argument('--display',action='store_true',help='shared functional display setup/scanout candidates')
    ap.add_argument('--capture-display-flow',action='store_true',help='read-only final source/color/alpha and original UI selectors; requires secondary model')
    ap.add_argument('--display-storage-scope',choices=('last-secondary','current-lcd','latched-lcd'),default='last-secondary',
                    help='explicit independent current LCD capture after later native graphics')
    ap.add_argument('--front',action='store_true',help='shared 150c arming/empty stop candidate; no pixels')
    ap.add_argument('--event-front',action='store_true',
                    help='shared 1508 bank request latch; no pixel or completion event')
    ap.add_argument('--control1380-idle',action='store_true',
                    help='shared request/apply/release contract with explicit zero busy status input')
    ap.add_argument('--diagnostic-primary-timing',type=int,metavar='NANOSECONDS',
                    help='explicit shared functional 1508 clock and primary bit2 status; no pixel input')
    ap.add_argument('--diagnostic-primary-input-period-ms',type=int,metavar='MILLISECONDS',
                    help='explicit independent host monotonic bit2 status source; no pixel input')
    ap.add_argument('--diagnostic-primary-bit6',action='store_true',
                    help='also provide explicit bit6 at the same host cadence; no pixels or physical timing claim')
    ap.add_argument('--tasks',action='store_true',help='bounded read-only original ZR scheduler snapshot')
    ap.add_argument('--lcd-control-peer',action='store_true',help='explicit I2C0/address11 write-only lab slave')
    ap.add_argument('--display-input',choices=('hardware-reconstructed','zero-first-length'),
                    help='explicit partial parameter ROM derived from existing V1.10 capture')
    ap.add_argument('--device-input',choices=('hardware-captured','zero-version'),
                    help='explicit runtime resource 0x64 from existing V1.10 capture')
    ap.add_argument('--orientation-input',choices=('hardware-captured',),
                    help='explicit runtime items 0x18/0x43 from existing capture')
    ap.add_argument('--orientation-peer',action='store_true',
                    help='explicit unidentified I2C3/address68 stationary LE16 lab input')
    ap.add_argument('--orientation-sample',
                    help='six LE16 sensor bytes as 12 hex digits; shared Z9-derived build only')
    ap.add_argument('--raw-input',
                    help='external NZ9RAW1 frame; enables shared functional RAW/statistics and 151/1543 image models')
    ap.add_argument('--shared-parameter-models',action='store_true',
                    help='reuse Z9 parameter config/submission, primary controller and task1500 models; ZR compatibility experiment')
    ap.add_argument('--shared-sensor-timing',action='store_true',
                    help='reuse Z9 virtual boundary timer and empty-source stop notification; retain separately declared auxiliary inputs')
    ap.add_argument('--raw-source-boundaries',action='store_true',
                    help='functional input boundaries before preview DMA; requires shared RAW source timing')
    ap.add_argument('--stopped-source-reset',action='store_true',
                    help='explicit source-clock-gated RAW and primary reset contract candidate')
    ap.add_argument('--capture-transition-batch',action='store_true',
                    help='Acknowledged real-preview reset plus shared alternating NR/RAW/JPEG ports and capture rearm')
    ap.add_argument('--d980-config',action='store_true',
                    help='shared sparse 150d9800 configuration/submission model; no processing/results')
    ap.add_argument('--d980-stream',action='store_true',
                    help='functional packed12 external Bayer DMA; physical packing/native save unproven')
    ap.add_argument('--single-frame-input',action='store_true',
                    help='candidate source transition queues one bounded external frame; timing hypothesis')
    ap.add_argument('--single-source-notify',action='store_true',
                    help='existing source boundary after actual full DMA; timing hypothesis')
    ap.add_argument('--single-channel-boundary',action='store_true',
                    help='existing channel0 input after complete full DMA; timing hypothesis')
    ap.add_argument('--capture-direct-stop',action='store_true',
                    help='bounded observed401e direct drain after full input and channel ACK; functional hypothesis')
    ap.add_argument('--engine1543-video-control',action='store_true',
                    help='default-off native383 continuous video header admission; no pixels or completion generated by control')
    ap.add_argument('--engine151-video-stream',action='store_true',
                    help='route original continuous-video ISP to checked RAW-derived RAM outputs')
    ap.add_argument('--video-peripheral-control',action='store_true',
                    help='default-off native peripheral command and1530 source/start/stop control')
    ap.add_argument('--engine152c-stream-receiver',action='store_true',
                    help='native receiver-before-supplier order and complete output ring admission')
    ap.add_argument('--engine152c-stream-copy',action='store_true',
                    help='explicit opaque RAM byte transport; no Nikon compression algorithm')
    ap.add_argument('--video-raw-transport',action='store_true',
                    help='explicit functional internal RAW/packet RAM/decoder/ISP transport; simulator codec, not Nikon compression')
    ap.add_argument('--task1500-global-pulses',action='store_true',
                    help='explicit three native global1-to0 task controller pulse words; no invented data or IRQ')
    ap.add_argument('--engine1543-capture-control',action='store_true',
        help='Opt-in observed single-capture header control; no image/results/IRQ producer')
    ap.add_argument('--engine15e2-config',action='store_true',
        help='Original15e2 config and explicit idle reset; processing unsupported')
    ap.add_argument('--engine15e2-jpeg',action='store_true',
        help='Actual151 NV16 RAM to baseline JPEG; physical codec conventions provisional')
    ap.add_argument('--capture-pipeline',action='store_true',
        help='Reuse the shared actual capture resize/thumbnail/JPEG lifecycle; requires existing native capture inputs')
    ap.add_argument('--capture-raw-pipeline',action='store_true',
        help='Opt-in shared packed14 RAW/receiver/1540/1544 transport; original geometry/requests remain authoritative, actual file acceptance separate')
    ap.add_argument('--mode-keys-file',type=Path,
        help='Bounded append-only JSON keys/finished queue for native view-return pacing; no guest setting edits')
    ap.add_argument('--mode-key-release-gap-ms',type=int,choices=range(1001),default=0,
        help='Explicit external button release cooldown in the selected input clock; no firmware timing edits')
    ap.add_argument('--nvme-card',action='store_true',
        help='Fresh private exFAT NVMe recording medium over shared PCIe; actual file/decode acceptance remains separate')
    ap.add_argument('--engine151-capture-pixels',action='store_true',
        help='Actual completed D980 RAM to cropped functional NV16; ISP algorithm/bit1 timing approximate')
    ap.add_argument('--engine151-average-result',action='store_true',
        help='Provisional actual cropped Bayer green means; physical statistic/ROI unknown')
    ap.add_argument('--engine153-config',action='store_true',
                    help='sparse original1534/1538 configuration retention; processing/start remains strict')
    ap.add_argument('--yuvcmp-config',action='store_true',help='whole original YUVCMP configuration/address banks; codec jobs unsupported')
    ap.add_argument('--yuvcmp-channels',action='store_true',help='empty YUVCMP arm/idle/status/stop/reset; requires configuration model')
    ap.add_argument('--serial-write-batches',type=int,default=1024,choices=range(1,16385),help='bounded whole-session peripheral write budget')
    ap.add_argument('--compact-serial-writes',action='store_true',help='retain exact descriptor and wire bytes inline, omit duplicate tiny files')
    ap.add_argument('--engine153-frame-pass',action='store_true',
                    help='opt-in neutral actual D980-frame copy; multiscale algorithm is unsupported')
    ap.add_argument('--prepared-single-start',action='store_true',
                    help='retain post-reset preparation before original full-unit start; timing hypothesis')
    ap.add_argument('--reset-idle-stop',action='store_true',
                    help='provenance-bounded request to stop idle units after stopped-source reset')
    ap.add_argument('--shared-primary-status',action='store_true',
                    help='clock existing primary bit2/bit6 diagnostic status from shared sensor timing, without a host pulse loop')
    ap.add_argument('--primary-metadata14c',type=int,choices=range(128),metavar='0..127',
                    help='explicit opaque seven-bit metadata input, using the shared Z9 model; physical meaning unverified')
    ap.add_argument('--pipeline-aux-zero',action='store_true',
                    help='explicit shared Z9 zero-result fixtures for bounded auxiliary readers; not computed image results')
    ap.add_argument('--primary-results-zero',action='store_true',
                    help='explicit shared 19bc zero-result input; not computed image statistics')
    ap.add_argument('--shared-mvd-model',action='store_true',
                    help='reuse functional Z9 motion adapter; original ZR config/ISR checked separately, physical algorithm unverified')
    ap.add_argument('--trace-sequence-resources',action='store_true',
                    help='bounded original sequence resource-completion callback and notification observations')
    ap.add_argument('--trace-sequence-watchdog',action='store_true',
                    help='bounded repeated original watchdog arm/cancel calls and original returns')
    ap.add_argument('--diagnostic-source-stop-drain',action='store_true',
                    help='bounded final global0 boundary input after source stop; hypothesis only')
    ap.add_argument('--diagnostic-source-stop-drain-kind',choices=('global0','channel','both'),default='global0',
                    help='explicit diagnostic boundary channels; meaningful only with stop-drain enabled')
    ap.add_argument('--diagnostic-source-stop-drain-limit',type=int,choices=(4,16,32),default=4,
                    help='bounded number of source falling edges eligible for a diagnostic tail frame')
    ap.add_argument('--trace-sequence-waits',action='store_true',
                    help='bounded repeated original sensor/sequence waits and their returns')
    ap.add_argument('--trace-sequence-callbacks',action='store_true',
                    help='bounded original sequence event masks, state snapshots and returns')
    ap.add_argument('--trace-capture-gpio',action='store_true',
                    help='read original ZR GPIO binding tables without supplying new inputs')
    ap.add_argument('--capture-gpio',action='store_true',
                    help='mirror explicit half/full contacts to validated ZR GPIO pins')
    ap.add_argument('--sequence-resource-input',choices=('captured-primary-with-framing',),
                    help='captured resource0c with explicit primary-bank Flash padding/generation/trailer')
    ap.add_argument('--secondary-model',action='store_true',
                    help='explicit functional secondary Q11 affine RGBA to YYUV/alpha path')
    ap.add_argument('--resource-group-input',choices=('captured-content','diagnostic-ENDM'),
                    help='complete captured group13; optional explicitly synthetic four-byte flash trailer')
    ap.add_argument('--resource-integrity-input',choices=('diagnostic-ENDM','diagnostic-ENDM-video-capability'),
                    help='six ROM resources with explicit diagnostic framing; optional synthetic video capability in configuration resource9')
    ap.add_argument('--diagnostic-bank1-input-period-ms',type=int,
                    help='explicit host-clock bank1 bits5/6 input, not measured sensor events')
    ap.add_argument('--diagnostic-aux0-input-period-ms',type=int,
                    help='explicit host-clock auxiliary bit1 input gated by native interrupt mask')
    ap.add_argument('--diagnostic-aux0-input',choices=('bit1','masked-bit0-and-bit1'),default='bit1',
                    help='explicit allowed auxiliary status bits, intersected with native mask')
    ap.add_argument('--diagnostic-aux1-input-period-ms',type=int,
                    help='explicit independent auxiliary bank1 bit0 status, no pixels')
    ap.add_argument('--diagnostic-global0-bit26-input-period-ms',type=int,
                    help='explicit independent global0 bit26 status, no pixels')
    ap.add_argument('--diagnostic-global0-bit10-input-period-ms',type=int,
                    help='independent mask-only diagnostic bit10 source for original flag80; no pixels')
    ap.add_argument('--diagnostic-global0-bit26-input-gate',choices=('group-channel','mask-only'),
                    default='group-channel',help='explicit bit26 gate hypothesis, never a guest PC trigger')
    ap.add_argument('--diagnostic-global0-input-period-ms',type=int,
                    help='explicit global0 bit7 input gated by original group/channel controls')
    ap.add_argument('--diagnostic-global0-input',choices=('bit7','bit4-and-bit7'),default='bit7',
                    help='explicit global status; pairing bit4 and bit7 is a diagnostic timing assumption')
    ap.add_argument('--diagnostic-channel0-input-period-ms',type=int,
                    help='explicit host-clock channel0 status with native control/mask gates; no pixels')
    ap.add_argument('--config150d',action='store_true',
                    help='reuse bounded shared 150d configuration retention; no DMA or readback input')
    ap.add_argument('--control150d',action='store_true',
                    help='reuse selector8 latch/start; requires --config150d --front, no data work')
    ap.add_argument('--readback150d',choices=('zero',),
                    help='explicit five zero diagnostic result words; no image statistics or pixels')
    ap.add_argument('--output-group1508',action='store_true',
                    help='reuse output-group bitmap snapshot with explicit idle-command readback hypothesis')
    ap.add_argument('--command1508',action='store_true',
                    help='record three exact write-only requests; physical reset semantics unknown')
    ap.add_argument('--stream-stop154c',action='store_true',
                    help='reuse explicitly empty three-channel stop/reset/getter model; no active data')
    ap.add_argument('--aux-status1508',choices=('zero',),
                    help='explicit eight zero polling-status words; no error IRQ or pixel claim')
    ap.add_argument('--aux-config1508',action='store_true',
                    help='retain two-bank auxiliary control and byte-packed fields; no pixels')
    args = ap.parse_args()
    if args.mode_keys_file and not (args.mode_key_sequence=='keys' and args.mode_key_pacing in ('view-return','consumer-return')):
        ap.error('Live key queue requires the original bounded keys and view-return pacing')
    if args.service_core_events and not args.shared_z9_build:
        ap.error('service core events require the isolated published Z9 build')
    if args.input_clock=='virtual' and not args.shared_z9_build:
        ap.error('virtual input clock requires the shared runtime clock interface')
    raw_source=None
    if args.shared_parameter_models and not args.raw_input:
        ap.error('shared parameter models require explicit RAW input')
    if args.pipeline_aux_zero and (not args.shared_z9_build or not args.raw_input):
        ap.error('auxiliary result fixture requires explicit shared RAW profile')
    if args.primary_results_zero and (not args.shared_z9_build or not args.raw_input):
        ap.error('primary result fixture requires explicit shared RAW profile')
    if args.shared_mvd_model and (not args.shared_z9_build or not args.raw_input):
        ap.error('shared MVD requires explicit shared RAW profile')
    if args.trace_sequence_resources and not args.shared_z9_build:
        ap.error('sequence observation requires shared virtual-clock interface')
    if args.raw_source_boundaries and not args.shared_sensor_timing:
        ap.error('RAW source boundaries require shared sensor timing and RAW source')
    if args.shared_primary_status and (not args.shared_sensor_timing or
            args.diagnostic_primary_input_period_ms is not None or args.diagnostic_primary_bit6):
        ap.error('shared primary status requires sensor timing and no duplicate host primary inputs')
    if args.shared_sensor_timing and (not args.shared_z9_build or not args.raw_input or
            args.diagnostic_primary_timing is not None or
            args.diagnostic_global0_input_period_ms is not None or
            args.diagnostic_channel0_input_period_ms is not None):
        ap.error('shared sensor timing requires shared RAW build and no duplicate global/channel timer')
    if args.raw_input:
        if not (args.shared_z9_build and args.front and args.config150d and args.control150d):
            ap.error('RAW input requires shared build, front, config150d and control150d models')
        raw_path=Path(args.raw_input).resolve()
        if ',' in str(raw_path) or not raw_path.is_file():
            ap.error('existing RAW input without a comma in its path required')
        with raw_path.open('rb') as f:header=f.read(32)
        if len(header)!=32 or header[:8]!=b'NZ9RAW1\0':ap.error('NZ9RAW1 frame header required')
        width,height,bits,cfa,black,white=struct.unpack('<6I',header[8:])
        raw_source=dict(path=str(raw_path),sha256=sha(raw_path),bytes=raw_path.stat().st_size,
            width=width,height=height,bits=bits,cfa=cfa,black=black,white=white,
            scope='external host frame; native DMA consumption not assumed')
    build_options={}
    shared_manifest=None
    if args.shared_z9_build:
        from shared_z9_build import WORK as shared_work,validate
        shared_manifest=validate()
        build_options=dict(build_work=shared_work,
                           board_source=shared_work/'qemu-10.2.4/hw/arm/nikon-z9-lab.c')
    if not re.fullmatch(r'zr-[a-z0-9-]+',args.name):ap.error('fresh safe zr- run name required')
    if args.capture_display_flow and (not args.display or not args.secondary_model):
        ap.error('display flow capture requires --display --secondary-model')
    if args.display_storage_scope!='last-secondary' and not args.capture_display_flow:
        ap.error('current LCD storage scope requires explicit display capture')
    if args.mcu_peer and not args.post_seconds:ap.error('peer requires bounded post observation')
    if args.key_input and not args.mcu_peer:ap.error('key input requires peer')
    if args.audio_control_clock and not args.mcu_peer:
        ap.error('audio control clock requires the bounded native peer session')
    if args.audio_control_batch_clock and (not args.mcu_peer or not args.shared_z9_build or args.audio_control_clock):
        ap.error('batched audio clock requires shared build and peer, and excludes the per-write host clock')
    if args.engine151_video_stream and not (args.engine1543_video_control and args.capture_raw_pipeline):
        ap.error('video ISP stream requires original video headers and RAW output pipeline')
    if args.video_peripheral_control and not (args.shared_z9_build and args.engine151_video_stream and args.engine153_config):
        ap.error('video peripheral control requires declared video ISP and original1530 config')
    if args.engine152c_stream_receiver and not (args.shared_z9_build and args.capture_raw_pipeline):
        ap.error('native stream receiver requires the declared RAW receiver profile')
    if args.engine152c_stream_copy and not (args.engine152c_stream_receiver and args.shared_sensor_timing):
        ap.error('opaque byte transport requires stream receiver and explicit source timing')
    if args.video_raw_transport and not (args.engine152c_stream_receiver and args.video_peripheral_control and
            args.engine151_video_stream and not args.engine152c_stream_copy):
        ap.error('internal video RAW requires source/receiver/decoder/ISP and excludes opaque byte copy')
    if args.engine1543_video_control and (not args.shared_z9_build or not args.engine1543_capture_control):
        ap.error('video headers require shared build and original1543 capture control')
    if args.serial5_audio_input and not args.serial5_audio_config:
        ap.error('captured audio sample input needs the five-channel config model')
    if args.serial5_audio_idle_drain and not args.serial5_audio_config:
        ap.error('disabled audio drain requires explicit five-channel configuration')
    if args.video_forced_stops and not args.video_raw_transport:
        ap.error('video forced stops require the declared internal RAW pipeline')
    if args.video_backend_drains and not args.video_raw_transport:
        ap.error('video backend drains require the declared internal RAW pipeline')
    if args.backend_program_epochs and not args.video_backend_drains:
        ap.error('program epochs require both declared backend lifetimes')
    if args.video_nr_resets and not args.video_backend_drains:
        ap.error('video NR reset requires both declared backend lifetimes')
    if args.video_processing_config and not args.video_nr_resets:
        ap.error('processing config requires declared NR/source/backend ownership')
    if args.serial5_audio_config and not args.shared_z9_build:
        ap.error('serial5 configuration requires the declared shared build')
    if args.audio_register_retention and not args.audio_control_batch_clock:
        ap.error('functional audio register input requires the bounded in-QEMU FIFO clock')
    if args.diagnostic_selector36 is not None and (not args.key_input or args.mode_key_sequence!='keys'):
        ap.error('selector candidate requires explicit bounded key sequence and peer')
    from zr_key_sequence import parse_initial_selectors
    try:initial_selectors=parse_initial_selectors(args.mode_initial_selectors)
    except ValueError as exc:ap.error(str(exc))
    if initial_selectors and (not args.key_input or not args.mode_key_input or args.mode_key_sequence!='keys'):
        ap.error('initial selectors require explicit bounded key input and sequence')
    if args.diagnostic_selector36 is not None and 0x36 in initial_selectors:
        ap.error('initial selector36 and legacy persistent selector36 cannot be combined')
    if args.mode_start_gate=='initial-consumer-lcd' and (not args.key_input or not args.mode_key_input or
            args.mode_key_sequence!='keys' or args.mode_key_pacing!='consumer-return'):
        ap.error('initial consumer gate requires original bounded keys and native consumer-return pacing')
    if args.mode_key_input and (not args.key_input or not args.secondary_model):
        ap.error('mode waveform requires original key input and secondary observer')
    if args.mode_key_control!='exp-mode' and not args.mode_key_input:
        ap.error('alternate control selection requires the explicit mode waveform')
    if args.mode_key_sequence=='fn2-left-center' and (args.mode_key_control!='fn2' or args.mode_key_pacing!='view-return'):
        ap.error('Fn2/left/center requires Fn2 input and original-view pacing')
    if args.mode_key_sequence=='keys':
        from zr_key_sequence import parse_keys
        if not args.mode_keys or args.mode_key_pacing not in ('view-return','consumer-return') or not args.mode_key_input:
            ap.error('key sequence requires --mode-keys, explicit mode waveform and original native consumption pacing')
        try:mode_keys=parse_keys(args.mode_keys)
        except ValueError as exc:ap.error(str(exc))
    elif args.mode_keys:ap.error('--mode-keys requires --mode-key-sequence keys')
    if args.mode_final_press_seconds and args.mode_key_sequence!='keys':
        ap.error('final key hold requires a bounded key sequence')
    if args.mode_full_press_seconds and args.mode_key_sequence!='keys':
        ap.error('full shutter hold requires a bounded key sequence')
    if args.mode_precapture_liveview and (args.mode_key_sequence!='keys' or not args.raw_input or
                                        'half,full' not in ','.join(mode_keys)):
        ap.error('pre-shot liveview requires RAW and consecutive half/full keys')
    if args.mode_continuous_shutter:
        if args.mode_key_sequence!='keys' or args.mode_keys_file:
            ap.error('continuous shutter requires a fixed key sequence')
        from zr_key_sequence import input_states
        input_states(mode_keys,continuous_shutter=True)
    if args.mode_video_dispatch_pacing:
        if not args.mode_continuous_shutter or args.mode_post_capture_ready or args.mode_keys_file:
            ap.error('VIDEO dispatch pacing requires fixed continuous shutter and no PHOTO file gates')
        if mode_keys.count('full')%2 or not args.wave5_vpu:
            ap.error('VIDEO dispatch pacing requires paired full contacts and the modeled video interface')
    if args.mode_liveview_timeout_seconds and not args.mode_post_capture_ready:
        ap.error('liveview deadline requires post-shot image/menu readiness gates')
    if args.mode_post_capture_ready and (args.mode_key_sequence!='keys' or not args.capture_raw_pipeline):
        ap.error('post-shot image gate requires a full RAW key recipe')
    if args.mode_post_capture_ready and not 1<=mode_keys.count('full')<=8:
        ap.error('post-shot image evidence requires 1..8 bounded full shutter presses')
    if args.mode_ready_after_state is not None or args.mode_ready_ppm_sha256 is not None:
        if (args.mode_key_sequence!='keys' or not args.display or
            args.mode_ready_after_state is None or not 1<=args.mode_ready_after_state<2*len(mode_keys) or
            not args.mode_ready_ppm_sha256 or len(args.mode_ready_ppm_sha256)!=64 or
            any(c not in '0123456789abcdef' for c in args.mode_ready_ppm_sha256)):
            ap.error('screen gate requires keys/display, an interior state number and a lowercase SHA-256')
    if args.mode_video_ready_after_state is not None:
        if (args.mode_key_sequence!='keys' or not args.display or not args.video_raw_transport or
                not 1<=args.mode_video_ready_after_state<2*len(mode_keys)):
            ap.error('video readiness requires full internal video pipeline and an interior key state')
    if args.mode_focus_after_state:
        from zr_key_sequence import parse_focus_gates
        if args.mode_key_sequence!='keys' or args.mode_ready_after_state is None:
            ap.error('focus gates require keys and an explicit native menu screen gate')
        try:focus_gates=parse_focus_gates(args.mode_focus_after_state,2*len(mode_keys))
        except ValueError as exc:ap.error(str(exc))
    if args.mode_tab_after_state:
        from zr_key_sequence import parse_focus_gates
        if args.mode_key_sequence!='keys' or args.mode_ready_after_state is None:
            ap.error('tab gates require keys and an explicit native menu screen gate')
        try:tab_gates=parse_focus_gates(args.mode_tab_after_state,2*len(mode_keys))
        except ValueError as exc:ap.error(str(exc))
        if args.mode_focus_after_state and focus_gates.keys()&tab_gates.keys():
            ap.error('a release state cannot have both row and tab gates')
    if args.mode_completion_settle_seconds is not None and args.mode_key_sequence!='keys':
        ap.error('completion settlement requires a bounded key sequence')
    if args.mode_completion_ppm_sha256 and (args.mode_completion_settle_seconds is None or not args.display or
            len(args.mode_completion_ppm_sha256)!=64 or
            any(c not in '0123456789abcdef' for c in args.mode_completion_ppm_sha256)):
        ap.error('completion screen requires settlement/display and a lowercase SHA-256')
    if args.trace_mode_key_dispatch and not args.mode_key_input:
        ap.error('mode dispatch tracing requires the explicit mode waveform')
    if args.trace_mode_view_dispatch and not args.trace_mode_key_dispatch:
        ap.error('view dispatch tracing requires mode key tracing')
    if args.trace_mode_view_controls and not args.trace_mode_view_dispatch:
        ap.error('view control tracing requires original view dispatch tracing')
    if args.mode_key_pacing=='view-return' and not args.trace_mode_view_dispatch:
        ap.error('view-return input pacing requires view dispatch tracing')
    if args.trace_mode_property_writes and (not args.battery or not args.mcu_peer):
        ap.error('mode property tracing requires all early/power/post observer windows')
    if args.mode_property_watch!='280c' and not args.trace_mode_property_writes:
        ap.error('upstream source selection requires mode property tracing')
    if args.resource_group_input and args.display_input:
        ap.error('complete group13 replaces the partial display ROM candidate')
    if args.resource_integrity_input and (args.resource_group_input!='diagnostic-ENDM' or args.device_input!='hardware-captured'):
        ap.error('resource integrity input requires diagnostic group13 and matching captured device input')
    if args.diagnostic_primary_timing is not None and (
            not args.front or not 1000000<=args.diagnostic_primary_timing<=1000000000):
        ap.error('diagnostic primary timing requires --front and 1000000..1000000000 ns')
    if args.diagnostic_primary_input_period_ms is not None and (
            not args.front or not args.mcu_peer or args.diagnostic_primary_timing is not None or
            not 1<=args.diagnostic_primary_input_period_ms<=1000):
        ap.error('independent primary input requires --front --mcu-peer, 1..1000 ms and no shared timing')
    before = MAIN.stat().st_mtime_ns
    if args.diagnostic_bank1_input_period_ms is not None and (
            not args.front or not args.mcu_peer or not 1<=args.diagnostic_bank1_input_period_ms<=1000):
        ap.error('bank1 input requires --front --mcu-peer and 1..1000 ms')
    if args.diagnostic_aux0_input_period_ms is not None and (
            not args.front or not args.mcu_peer or not 1<=args.diagnostic_aux0_input_period_ms<=1000):
        ap.error('auxiliary input requires --front --mcu-peer and 1..1000 ms')
    if args.diagnostic_aux0_input!='bit1' and args.diagnostic_aux0_input_period_ms is None:
        ap.error('auxiliary bit0 input requires an explicit input period')
    if args.diagnostic_global0_input_period_ms is not None and (
            not args.front or not args.mcu_peer or args.diagnostic_primary_timing is not None or
            not 1<=args.diagnostic_global0_input_period_ms<=1000):
        ap.error('global0 input requires --front --mcu-peer, 1..1000 ms and no shared timing')
    for label,period in (('aux1',args.diagnostic_aux1_input_period_ms),
            ('global0-bit10',args.diagnostic_global0_bit10_input_period_ms),
            ('global0-bit26',args.diagnostic_global0_bit26_input_period_ms)):
        if period is not None and (not args.front or not args.mcu_peer or
                args.diagnostic_primary_timing is not None or not 1<=period<=1000):
            ap.error(label+' input requires --front --mcu-peer, 1..1000 ms and no shared timing')
    if args.diagnostic_global0_bit26_input_gate!='group-channel' and args.diagnostic_global0_bit26_input_period_ms is None:
        ap.error('bit26 gate hypothesis requires explicit bit26 period')
    if args.control150d and (not args.config150d or not args.front):
        ap.error('150d control requires --config150d --front')
    if args.diagnostic_channel0_input_period_ms is not None and (
            not args.front or not args.mcu_peer or args.diagnostic_primary_timing is not None or
            not 1<=args.diagnostic_channel0_input_period_ms<=1000):
        ap.error('channel0 input requires --front --mcu-peer, 1..1000 ms and no shared timing')
    if args.diagnostic_global0_input!='bit7' and args.diagnostic_global0_input_period_ms is None:
        ap.error('paired global0 input requires an explicit input period')
    if args.readback150d and not args.config150d:
        ap.error('150d diagnostic readback requires --config150d')
    props = (FIXTURES+',graphics-image-model=on,graphics-path-model=on,graphics-clear-model=on,'
        'multi-io-counter-model=on,adc-fixture=on,adc-input=256:512:768:1023')
    if args.audio_control_batch_clock:
        props+=f',serial-write-clock-peer=2:{BINDINGS["serial_objects"]+2*0x68:x}:{16*args.serial_write_batches}'
    if args.sd_empty:props+=',zr-sd-empty-fixture=on'
    if args.display:props+=(',engine1548-config-model=on,engine1548-control-model=on,'
                            'engine1548-scanout-model=on,zr-dsi-command-model=on')
    if args.front:props+=',engine150c-control-model=on,engine150c-stop-model=on'
    if args.event_front:props+=',event1508-front-model=on'
    if args.source_front_boundary:
        if not args.shared_z9_build or not args.shared_sensor_timing or not args.event_front:
            ap.error('idle front boundary requires shared build, sensor timing and event front')
        props+=',event1508-front-boundary-model=on'
    if args.source_front_global_end:
        if not args.source_front_boundary:
            ap.error('front global end requires the idle front boundary model')
        props+=',event1508-front-global-end-model=on'
    if args.source_output0_boundary:
        if not args.source_front_global_end or not args.output_group1508:
            ap.error('output0 boundary requires paired front end and output group model')
        props+=',event1508-output0-boundary-model=on'
    if args.control1380_idle:props+=',control1380-model=on,control1380-busy-input=0'
    if args.diagnostic_primary_timing is not None:
        props+=(',event1508-channel-model=on,event1508-aux-model=on,event1508-timing-model=on,'
                f'event1508-timing-period-ns={args.diagnostic_primary_timing},engine150c-bit2-model=on')
    if args.diagnostic_primary_input_period_ms is not None:props+=',engine150c-bit2-model=on'
    if args.diagnostic_primary_bit6:
        if args.diagnostic_primary_input_period_ms is None:
            ap.error('primary bit6 requires the independent host status period')
        props+=',engine150c-bit6-model=on'
    if args.diagnostic_bank1_input_period_ms is not None:props+=',zr-primary-bank1-model=on'
    if args.diagnostic_aux0_input_period_ms is not None and args.diagnostic_primary_timing is None:
        props+=',event1508-aux-model=on'
    if args.diagnostic_aux1_input_period_ms is not None:props+=',event1508-aux1-model=on'
    if any(p is not None for p in (args.diagnostic_global0_input_period_ms,
            args.diagnostic_global0_bit26_input_period_ms,args.diagnostic_global0_bit10_input_period_ms)):
        props+=',event1508-global0-model=on'
    if args.diagnostic_global0_bit10_input_period_ms is not None:props+=',event1508-global0-bit10-model=on'
    if args.diagnostic_global0_bit26_input_period_ms is not None:props+=',event1508-global0-bit26-model=on'
    if args.diagnostic_channel0_input_period_ms is not None:props+=',event1508-channel-model=on'
    if args.config150d:props+=',config150d-model=on'
    if args.control150d:props+=',engine150d-control-model=on'
    if args.readback150d:props+=',engine150d-readback-input=0:0:0:0:0'
    if args.output_group1508:props+=',event1508-group-model=on'
    if args.command1508:props+=',event1508-command-model=on'
    if args.aux_config1508:props+=',event1508-aux-config-model=on'
    if args.aux_status1508:props+=',event1508-aux-status-input=0:0:0:0:0:0:0:0'
    if args.stream_stop154c:props+=',stream154c-stop-model=on'
    if args.lcd_control_peer:props+=',zr-lcd-control-fixture=on'
    if args.orientation_sample:
        if not args.shared_z9_build or not args.orientation_peer or len(args.orientation_sample)!=12 or any(
                c not in '0123456789abcdefABCDEF' for c in args.orientation_sample):
            ap.error('orientation sample requires shared build, orientation peer and six hex bytes')
        props+=',zr-orientation-input='+args.orientation_sample
    if args.orientation_peer:props+=',zr-orientation-fixture=on'
    if raw_source:
        props+=(',image-bank-model=on,engine1543-control-model=on,engine151-control-model=on'
                ',raw-pipeline-model=on,statistics-model=on,primary-empty-end-model=on'
                ',event1508-front-address-model=on'
                ',statistics-raw='+raw_source['path'])
    if args.shared_parameter_models:
        props+=(',primary19d-config-model=on,primary19bc-config-model=on,primary194-config-model=on'
                ',primary194-submit-model=on,primary19bc-submit-model=on,primary19d-submit-model=on'
                ',secondary150d-submit-model=on,primary-parameter-control-model=on'
                ',task1500-control-model=on,engine152-control-model=on')
    if args.shared_sensor_timing:
        props+=(',event1508-channel-model=on,event1508-aux-model=on,event1508-global0-model=on'
                ',event1508-timing-model=on,event1508-timing-period-ns=33333333'
                ',event1508-global0-paired-boundary=on,event1508-stop-model=on')
    if args.secondary_model:props+=',zr-secondary-resample-model=on'
    if args.raw_source_boundaries:props+=',raw-source-boundary-model=on'
    if args.stream_isp_completion:
        if not (args.shared_z9_build and args.raw_input):ap.error('stream ISP completion requires shared RAW build')
        props+=',raw-pipeline-1514-completion-model=on'
    if args.stream_source_completion:
        if not (args.shared_z9_build and args.raw_input):ap.error('stream source completion requires shared RAW build')
        props+=',raw-pipeline-151c-completion-model=on'
    if args.stream_input_pair:
        if not (args.shared_z9_build and args.raw_input):ap.error('stream input pair requires shared RAW build')
        props+=',raw-pipeline-input-pair-model=on'
    if args.secondary_source_timing:
        if not args.shared_sensor_timing:ap.error('secondary source timing requires shared sensor timing')
        props+=',event1508-secondary-timing-model=on'
    if args.d980_config:
        if not (args.shared_z9_build and args.raw_input):
            ap.error('D980 configuration requires shared RAW build')
        props+=',primary-d980-config-model=on'
    if args.d980_stream:
        if not (args.d980_config and args.shared_sensor_timing):
            ap.error('D980 stream requires configuration and source timing')
        props+=',primary-d980-stream-model=on'
    if args.single_frame_input:
        if not args.d980_stream:
            ap.error('single frame input requires D980 stream')
        props+=',primary-d980-single-frame-model=on'
    if args.single_source_notify or args.single_channel_boundary or args.prepared_single_start:
        if not args.single_frame_input:
            ap.error('single input extensions require single frame input')
        if args.single_source_notify:props+=',primary-d980-source-notify-model=on'
        if args.prepared_single_start:props+=',primary-d980-prepared-start-model=on'
        if args.single_channel_boundary:props+=',primary-d980-channel-boundary-model=on'
    if args.capture_direct_stop:
        if not args.single_channel_boundary:ap.error('capture direct stop requires full-frame channel boundary')
        props+=',primary-capture-direct-stop-model=on'
    if args.engine1543_capture_control:
        if not args.shared_parameter_models:ap.error('1543 capture control requires shared parameter models')
        props+=',engine1543-capture-control-model=on'
    if args.engine1543_video_control:
        props+=',engine1543-video-control-model=on'
    if args.engine151_video_stream:
        props+=',engine151-video-stream-model=on'
    if args.video_peripheral_control:
        props+=',video-peripheral-control-model=on'
    if args.engine152c_stream_receiver:
        props+=',engine152c-stream-receiver-model=on'
    if args.engine152c_stream_copy:
        props+=',engine152c-stream-copy-model=on'
    if args.video_raw_transport:
        props+=',video-raw-transport-model=on'
    if args.task1500_global_pulses:
        if not args.shared_z9_build:ap.error('task global pulses require the declared shared build')
        props+=',task1500-global-pulse-model=on'
    if args.serial5_audio_idle_drain:
        props+=',serial5-audio-idle-drain-model=on'
    if args.video_forced_stops:
        props+=',video-forced-stop-model=on'
    if args.video_backend_drains:
        props+=',video-backend-drain-model=on'
    if args.backend_program_epochs:
        props+=',backend-program-epoch-model=on'
    if args.video_nr_resets:
        props+=',video-nr-reset-model=on'
    if args.video_initial_resets:
        if not args.video_nr_resets or not args.video_processing_config:
            ap.error('Video initialization resets require explicit NR resets and processing configuration')
        props+=',video-initial-reset-model=on'
    if args.video_processing_config:
        props+=',video-processing-config-model=on'
    if args.dsp_boot_mailbox:
        if not args.shared_z9_build:ap.error('DSP boot mailbox requires the source-bound shared build')
        props+=',dsp-boot-mailbox-model=on'
    if args.dsp_ram_aperture:
        if not args.dsp_boot_mailbox:ap.error('DSP RAM aperture requires the explicit DSP mailbox')
        props+=',dsp-ram-aperture-fixture=on'
    if args.dsp_session_init:
        if not args.dsp_ram_aperture:ap.error('DSP session initialization requires explicit RAM aperture input')
        props+=',dsp-session-init-model=on'
    if args.capture_dsp_job_inputs and not args.dsp_session_init:
        ap.error('DSP job input readback requires the explicit session initialization backend')
    if args.capture_dsp_correction_inputs and not args.dsp_session_init:
        ap.error('DSP correction input readback requires explicit functional startup and aperture')
    if args.dsp_motion_functional:
        if not args.dsp_session_init:ap.error('Functional DSP motion requires explicit session initialization')
        props+=',dsp-motion-functional-model=on'
    if args.dsp_correction_init:
        if not args.dsp_session_init:ap.error('Correction initialization requires explicit DSP session initialization')
        props+=',dsp-correction-init-model=on'
    if args.wave5_vpu:
        if not args.shared_z9_build:ap.error('Wave5 requires the source-bound shared build')
        props+=',wave5-vpu-model=on'
    if args.wave5_host_codec_diagnostic:
        if not args.wave5_vpu:ap.error('Host codec diagnostic requires the explicit Wave5 device')
        props+=',wave5-host-codec-diagnostic=on'
    if args.wave5_irq:
        if not args.wave5_vpu or not 32<=args.wave5_irq<512:
            ap.error('Wave5 IRQ requires its explicit device and a GIC SPI in 32..511')
        props+=',wave5-irq='+str(args.wave5_irq)
    if args.engine15e2_config:
        props+=',engine15e2-config-model=on'
    if args.engine151_capture_pixels:
        if not (args.shared_parameter_models and args.d980_stream):
            ap.error('151 capture pixels require shared parameters and actual D980 stream')
        props+=',engine151-capture-pixels-model=on'
    if args.engine151_average_result:
        if not args.engine151_capture_pixels:ap.error('151 average requires actual151 capture pixels')
        props+=',engine151-average-result-model=on'
    if args.engine15e2_jpeg:
        if not (args.engine15e2_config and args.engine151_capture_pixels):ap.error('15e2 JPEG requires config and actual151 pixels')
        props+=',engine15e2-jpeg-model=on'
    if args.capture_pipeline:
        if not (args.shared_z9_build and args.engine15e2_jpeg and
                (args.engine153_frame_pass or args.capture_raw_pipeline)
                and args.stopped_source_reset and args.single_channel_boundary):
            ap.error('Capture pipeline requires shared build, actual151/JPEG/153, stopped reset and full-frame channel inputs')
        props+=''.join(','+name+'-model=on' for name in (
            'low-service-ram','primary-reset-parameter-retention','primary20-empty-reset',
            'engine15e2-deferred-input','engine15e2-limit-disabled','engine15e2-result474',
            'engine15e2-preflight','capture-nv16-pipeline','engine1542-ram-input-control','capture-thumbnail-nv16'))
        if args.nvme_card:
            # ZR's card-present path runs the original relocated service
            # helper. Its complete0x400-byte image at40195000 is identical
            # in both fingerprinted samples. Reuse the explicit functional
            # Z9 boot/service inputs rather than modifying software state.
            props+=(',low-service-status-input=6,service-controller-model=on'
                    ',service-controller-status-input=32,service-cluster-inputs=16:0:1')
    if args.capture_raw_pipeline:
        if not (args.capture_pipeline and args.nvme_card and args.engine151_capture_pixels
                and args.engine153_config and not args.engine153_frame_pass):
            ap.error('RAW pipeline requires the complete card pipeline, actual151 and153 configuration; select in-place identity instead ofD8 frame pass')
        props+=''.join(','+name+'-model=on' for name in (
            'primary-d980-packed14','engine153-inplace-identity','engine151-raw-output',
            'engine152c-config','engine152c-request','engine1544-config','engine1544-neutral-copy',
            'engine1540-descriptors','engine1540-parameters','engine1540-control','engine1540-frame-pass'))
    if args.raw_lossless14:
        if not args.capture_raw_pipeline:ap.error('F0 lossless14 requires the complete actual RAW/card pipeline')
        props+=',engine1540-lossless14-model=on'
    if args.capture_transition_batch:
        if not (args.shared_z9_build and args.capture_raw_pipeline and args.stopped_source_reset):
            ap.error('Capture transition batch requires complete shared RAW pipeline and stopped-source reset')
        props+=''.join(','+name+'-model=on' for name in (
            'primary-preview-reset','engine153-alternate-bank','capture-stream-rearm',
            'engine1540-alternate-bank','engine15e2-alternate-bank','primary-d980-live-single'))
    if args.yuvcmp_config:
        props+=',yuvcmp-config-model=on'
    if args.yuvcmp_channels:
        if not args.yuvcmp_config:ap.error('YUVCMP channels require the configuration model')
        props+=',yuvcmp-channels-model=on'
    if args.engine153_config:
        if not args.shared_z9_build:ap.error('153 configuration requires the shared build')
        props+=',engine153-config-model=on'
    if args.engine153_frame_pass:
        if not (args.engine153_config and args.d980_stream):ap.error('neutral153 pass requires configuration and D980 stream')
        props+=',engine153-frame-pass-model=on'
    if args.reset_idle_stop:
        if not args.stopped_source_reset:
            ap.error('reset idle stop requires stopped-source reset')
        props+=',primary-reset-idle-stop-model=on'
    if args.stopped_source_reset:
        if not (args.shared_z9_build and args.raw_input and args.shared_parameter_models and
                args.shared_sensor_timing and args.raw_source_boundaries):
            ap.error('stopped-source reset requires shared RAW, parameters, timing and boundaries')
        props+=',primary-stopped-source-reset-model=on'
    if args.shared_primary_status:props+=',engine150c-bit2-model=on,engine150c-bit6-model=on'
    if args.primary_metadata14c is not None:props+=',primary-metadata14c-input='+str(args.primary_metadata14c)
    if args.pipeline_aux_zero:props+=',pipeline-aux-zero-input=on'
    if args.primary_results_zero:props+=',primary19bc-zero-results-input=on'
    if args.shared_mvd_model:
        props+=',config1524-model=on,config1524-control100-input=0,engine1524-control-model=on,engine1524-mvd-model=on'
    if args.nor:props+=',nor-model=on'
    if args.retained_header_start:
        if not (args.shared_z9_build and args.engine1543_video_control):
            ap.error('retained header START requires shared video header control')
        props+=',engine1543-retained-start-model=on'
    if args.service_core_events:props+=',service-core-event-model=on'
    g = ZRGuest(args.name,props,intercept_irq=False,ram_mib=1024,
        machine='nikon-zr-lab',firmware=MAIN,firmware_sha=MAIN_SHA,runtime_log=True,**build_options)
    g.command[g.command.index('-smp')+1]='4'
    if args.lifecycle_observer:
        from native_lifecycle_plugin import attach
        attach(g,args.lifecycle_observer)
    if args.nvme_card:
        if not (args.shared_z9_build and args.capture_pipeline):
            ap.error('Recording card requires the shared complete capture pipeline')
        from virtual_recording_card import create
        card=g.runtime/'capture-card.raw'
        g.data['private_virtual_card']=create(card,'exfat')
        g.command[g.command.index('-M')+1]+=(',pcie-link-diagnostic-mask=4,'
            'pcie-dbi-model=on,pcie-ram-dma-input=on,pcie-image-ram-dma-input=on,pcie-intx-model=on')
        events=g.runtime/'storage-dma.events'
        events.write_text('pci_nvme_map_prp\npci_nvme_map_addr\npci_nvme_write\n')
        g.command+=['-trace',f'events={events},file={g.runtime}/storage-dma.log']
        g.command+=['-drive',f'file={card},if=none,id=card,format=raw',
                    '-device','nvme,drive=card,serial=WL-ZR-CAPTURE,bus=dw-pcie,addr=0']
        (g.out/'virtual_recording_card.py').write_bytes((HERE/'virtual_recording_card.py').read_bytes())
    if args.service_core_events:
        g.command+=['-accel','tcg,thread=single','-icount','shift=0,sleep=on']
    g.data['probe_arguments']=vars(args)
    if args.mode_keys_file:
        g.data['mode_keys_file']=str(args.mode_keys_file.resolve())
        g.data['probe_arguments']['mode_keys_file']=str(args.mode_keys_file.resolve())
    g.data['input_clock']=args.input_clock
    g.data['diagnostic_selector36']=args.diagnostic_selector36
    g.data['mode_initial_selectors']=initial_selectors
    g.data['mode_start_gate']=args.mode_start_gate
    if args.mode_video_ready_after_state is not None:
        g.data['mode_video_ready_after_state']=args.mode_video_ready_after_state
    if raw_source:g.data['raw_source']=raw_source
    g.data.update(model='zr-c1.11',classification='original_EG_external_MCU_diagnostic',
        diagnostic=__doc__,source_sha256=sha(Path(__file__)),
        input_mtime_ns=before,main_input_read_only=True,
        ram_patches=[],firmware_patches=[],cpu_register_redirection=False,
        physical_mcu_protocol_verified=False,status_fixture=args.status,sd_empty_fixture=args.sd_empty,
        display_model=args.display,battery_input=args.battery,front_model=args.front,
        event_front_model=args.event_front,
        control1380_idle_input=args.control1380_idle,
        capture_display_flow=args.capture_display_flow,
        display_storage_scope=args.display_storage_scope,
        nor_model=args.nor,
        nor_scope='emulated_volatile_guest_flash_only' if args.nor else 'disabled',
        diagnostic_primary_timing_ns=args.diagnostic_primary_timing,
        diagnostic_primary_input_period_ms=args.diagnostic_primary_input_period_ms,
        diagnostic_primary_bit6=args.diagnostic_primary_bit6,
        diagnostic_aux0_input_period_ms=args.diagnostic_aux0_input_period_ms,
        diagnostic_aux0_input_variant=args.diagnostic_aux0_input,
        diagnostic_aux1_input_period_ms=args.diagnostic_aux1_input_period_ms,
        diagnostic_global0_bit26_input_period_ms=args.diagnostic_global0_bit26_input_period_ms,
        diagnostic_global0_bit10_input_period_ms=args.diagnostic_global0_bit10_input_period_ms,
        diagnostic_global0_bit26_input_gate=args.diagnostic_global0_bit26_input_gate,
        diagnostic_global0_input_period_ms=args.diagnostic_global0_input_period_ms,
        diagnostic_global0_input_variant=args.diagnostic_global0_input,
        diagnostic_channel0_input_period_ms=args.diagnostic_channel0_input_period_ms,
        config150d_model=args.config150d,
        control150d_model=args.control150d,
        diagnostic_readback150d_input=args.readback150d,
        output_group1508_model=args.output_group1508,
        command1508_model=args.command1508,
        aux_config1508_model=args.aux_config1508,
        diagnostic_aux_status1508_input=args.aux_status1508,
        stream154c_stop_model=args.stream_stop154c,
        diagnostic_bank1_input_period_ms=args.diagnostic_bank1_input_period_ms,
        capture_tasks=args.tasks,lcd_control_peer=args.lcd_control_peer,
        orientation_peer=args.orientation_peer,secondary_model=args.secondary_model)
    if args.battery_query_peer and not (args.battery and args.mcu_peer):
        ap.error('battery query peer requires boot battery input and MCU peer')
    g.data['battery_query_peer']=args.battery_query_peer
    g.data['battery_input_variant']=args.battery_input if args.battery else None
    g.data['trace_sequence_resources']=args.trace_sequence_resources
    g.data['trace_sequence_watchdog']=args.trace_sequence_watchdog
    g.data['trace_sequence_waits']=args.trace_sequence_waits
    g.data['trace_sequence_callbacks']=args.trace_sequence_callbacks
    g.data['trace_capture_gpio']=args.trace_capture_gpio
    if args.rtc_status:
        if not args.mcu_peer:ap.error('RTC input requires original MCU peer')
        g.data['rtc_status_input']=dict(classification='deterministic external MCU status sample',
            physical_protocol_verified=False,guest_state_patched=False)
    if args.capture_gpio:
        if not (args.shared_z9_build and args.trace_capture_gpio and args.mcu_peer):
            ap.error('ZR shutter GPIO requires shared build, MCU peer and binding observations')
        g.command[g.command.index('-M')+1]+=',capture-gpio-model=on'
    g.data['capture_gpio_model']=args.capture_gpio
    if args.diagnostic_source_stop_drain and not (args.shared_sensor_timing and args.input_clock=='virtual'):
        ap.error('diagnostic drain requires shared timing and virtual input clock')
    g.data['diagnostic_source_stop_drain']=args.diagnostic_source_stop_drain
    g.data['diagnostic_source_stop_drain_kind']=args.diagnostic_source_stop_drain_kind
    g.data['diagnostic_source_stop_drain_limit']=args.diagnostic_source_stop_drain_limit
    g.data['diagnostic_mode_key_input']=args.mode_key_input
    if args.mode_key_input:g.data['mode_key_control']=args.mode_key_control
    if args.mode_key_input:g.data['mode_key_sequence']=args.mode_key_sequence
    if args.mode_key_input:g.data['mode_key_step_count']=6 if args.mode_key_sequence=='fn2-left-center' else 4
    if args.mode_key_sequence=='keys':
        g.data.update(mode_keys=mode_keys,mode_key_step_count=2*len(mode_keys),
            mode_view_call_limit=2*len(mode_keys)+8)
        if args.mode_keys_file:
            from zr_key_sequence import MAX_KEYS
            g.data.update(mode_key_step_count=2*MAX_KEYS,mode_view_call_limit=2*MAX_KEYS+8)
        g.data['mode_key_release_gap_ms']=args.mode_key_release_gap_ms
        (g.out/'zr_key_sequence.py').write_bytes((HERE/'zr_key_sequence.py').read_bytes())
    if args.mode_ready_after_state is not None:
        g.data.update(mode_ready_after_state=args.mode_ready_after_state,
            mode_ready_ppm_sha256=args.mode_ready_ppm_sha256)
    if args.mode_key_input:g.data['mode_key_gap_seconds']=args.mode_key_gap_seconds
    if args.mode_final_press_seconds:g.data['mode_final_press_seconds']=args.mode_final_press_seconds
    if args.mode_full_press_seconds:g.data['mode_full_press_seconds']=args.mode_full_press_seconds
    if args.mode_precapture_liveview:
        g.data['mode_precapture_liveview']=True
        g.data['mode_precapture_liveview_frames']=args.mode_precapture_liveview_frames
    if args.mode_continuous_shutter:g.data['mode_continuous_shutter']=True
    if args.mode_video_dispatch_pacing:
        g.data.update(mode_video_dispatch_pacing=True,mode_video_clip_seconds=args.mode_video_clip_seconds,
            mode_video_dispatch_timeout_seconds=args.mode_video_dispatch_timeout_seconds)
    if args.mode_liveview_timeout_seconds:g.data['mode_liveview_timeout_seconds']=args.mode_liveview_timeout_seconds
    if args.mode_post_capture_ready:g.data['mode_post_capture_ready']=True
    if args.mode_movie_release_gap_seconds:g.data['mode_movie_release_gap_seconds']=args.mode_movie_release_gap_seconds
    if args.mode_focus_after_state:g.data['mode_focus_after_state']=focus_gates
    if args.mode_tab_after_state:g.data['mode_tab_after_state']=tab_gates
    if args.mode_completion_ppm_sha256:g.data['mode_completion_ppm_sha256']=args.mode_completion_ppm_sha256
    if args.mode_completion_settle_seconds is not None:
        g.data['mode_completion_settle_seconds']=args.mode_completion_settle_seconds
    if args.mode_key_input:g.data['mode_dial_index']=args.mode_dial_index
    if args.mode_key_input:g.data['mode_key_pacing']=args.mode_key_pacing
    if args.trace_mode_key_dispatch:g.data['trace_mode_key_dispatch']=True
    if args.trace_mode_view_dispatch:g.data['trace_mode_view_dispatch']=True
    if args.trace_mode_view_controls:g.data['trace_mode_view_controls']=True
    if args.trace_mode_property_writes:
        g.data.update(trace_mode_property_writes=True,mode_property_watch=args.mode_property_watch)
    for name in ('probe_zr_mcu.py','zr_mcu_bindings.py','contract_guest.py',
            'deliver_mcu_frame.py','observe_serial_channel.py','mcu_frames.py','service_z9_mcu.py','service_serial8.py','probe_tasks.py','capture_virtual_ram.py'):
        (g.out/name).write_bytes((HERE/name).read_bytes())
    for name in ('nikon-z9-lab.c','nikon-zr-lab.c'):
        (g.out/name).write_bytes((HERE.parents[1]/'qemu'/name).read_bytes())
    if shared_manifest is not None:
        from shared_z9_build import archive
        archive(g,shared_manifest)
    if args.display_input:
        from zr_display_input import attach
        attach(g,args.display_input)
    if args.device_input:
        from zr_device_parameter_input import attach
        attach(g,args.device_input)
    if args.resource_group_input:
        from zr_resource_group_input import attach
        attach(g,args.resource_group_input)
    if args.resource_integrity_input:
        from zr_resource_integrity_input import attach
        attach(g,args.resource_integrity_input)
    if args.sequence_resource_input:
        from zr_resource0c_input import attach
        attach(g,args.sequence_resource_input)
    if args.orientation_input:
        from zr_orientation_input import attach
        attach(g,args.orientation_input)
    if args.ui_language:
        from zr_ui_language_input import prepare
        prepare(g,args.ui_language)
    try:
        with g:
            # QEMU orders -machine property setters independently of CLI order.
            # Set this dependent input after realization, before CPUs run.
            if args.audio_register_retention:
                g.qmp.command('qom-set',path='/machine',property='serial-audio-register-retention',value=True)
            if args.serial5_audio_config:
                g.qmp.command('qom-set',path='/machine',property='serial5-audio-config-model',value=True)
            if args.serial5_audio_input=='silence':
                for channel in range(5):
                    g.qmp.command('qom-set',path='/machine',property='serial5-audio-sample-input',
                        value=f'{channel}:0:0:0:0')
            g.rsp('z1,40160000,4')
            if args.trace_mode_property_writes:
                from observe_zr_mode_writes import Observer,delivery_window
            else:
                from observe_zr_startup import Observer
                delivery_window=lambda guest,phase:nullcontext()
            early_observer=Observer(g,early=True)
            try:settle(g,20,observer=early_observer)
            finally:early_observer.close()
            validate_gpio(g)
            # Arguments independently recovered from the ZR native TCBs;
            # the generic worker 40e00040 calls +58/+60/+68/+78.
            g.data['generic_worker_objects']={}
            for label,address in (('app',0xa02835600),('ui',0xa02835730)):
                raw=save(g,'zr-generic-'+label+'-object',address,0xd0)
                g.data['generic_worker_objects'][label]=dict(address=hex(address),raw_hex=raw.hex(),
                    callbacks={hex(off):hex(struct.unpack_from('<Q',raw,off)[0])
                               for off in (0x48,0x58,0x60,0x68,0x78)})
            body = status_body({0x1c:2} if args.status=='enum2' else {})
            frame = frames(body)[0]
            event_pc = BINDINGS['power_event_consumer']
            with delivery_window(g,'power-status-delivery'):
                deliver(g,frame,prefix='zr-status-',bindings=BINDINGS)
                cpu,regs = at(g,event_pc)
                g.data['power_event'] = dict(cpu=cpu,registers=regs)
                event = save(g,'power-event',regs['X01'],12)
                g.check('original ZR power event consumes diagnostic status',
                    regs['X00']==0x05020101)
                g.data['power_event']['payload_hex']=event.hex()
            observer=None
            if args.battery:
                power_observer=Observer(g,phase='power')
                try:settle(g,1,observer=power_observer)
                finally:power_observer.close()
                body=bytearray(112);body[0]=3;body[4]=int(args.battery_input=='source1')
                g.data['battery_status_input_body_hex']=body.hex()
                with delivery_window(g,'battery-status-delivery'):
                    deliver(g,frames(body,family=4)[0],prefix='zr-battery-',bindings=BINDINGS)
                    cpu,regs=at(g,0x40ed141c)
                    payload=save(g,'zr-battery-native',regs['X01'],0x94)
                    g.data['battery_native']=dict(cpu=cpu,registers=regs,payload_hex=payload.hex())
                    g.check('original ZR battery driver receives candidate byte4 variant',
                        regs['X00']==0x430e0001 and payload[:8]==struct.pack('<II',1,body[4]))
                observer=Observer(g)
            if args.post_seconds:
                if args.mcu_peer:service_mcu(g,args.post_seconds,observer=observer,key_input=args.key_input)
                else:settle(g,args.post_seconds)
            g.check('original EG input remains unchanged',sha(MAIN)==MAIN_SHA and MAIN.stat().st_mtime_ns==before)
    finally:
        # ContractGuest saves the result even if a native observation fails.
        pass


if __name__=='__main__':main()
