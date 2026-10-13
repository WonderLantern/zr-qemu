# SPDX-License-Identifier: GPL-2.0-or-later
"""Compact whole-workflow result; delivery, native faults, file and LCD stay separate."""
import argparse
import hashlib
import json
from pathlib import Path
from nef_codec_profile import verified_f0_profile

HERE=Path(__file__).resolve().parent


def native_fault_observations(data):
    """Retain native faults even when optional exception capture failed."""
    names={'sequence_flow_watchdog_expired','fault_reason9_report',
           'fault_list_append','fault_cpu_exception_context'}
    fields=('name','pc','failure_mask','fault_code','producer_return',
            'context_address','context_bytes','context_capture_error')
    observations=[]
    for phase,record in data.items():
        if not phase.endswith('observer') or not isinstance(record,dict):continue
        rows=record.get('stops',[])
        if not isinstance(rows,list):continue
        for row in rows:
            if isinstance(row,dict) and row.get('name') in names:
                observations.append(dict(phase=phase,**{k:row[k] for k in fields if k in row}))
    for row in data.get('fault_capture_failures',[]):
        if (isinstance(row,dict) and row.get('name')=='fault_cpu_exception_context'
                and row.get('context_capture_error') and not any(
                    old.get('name')==row['name'] and old.get('pc')==row.get('pc')
                    for old in observations)):
            observations.append(dict(phase='fault_capture_failures',
                **{k:row[k] for k in fields if k in row}))
    return observations


def summarize(name):
    if not name.startswith(('z9-','zr-')) or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name):
        raise ValueError('A local native run name is required')
    f=HERE/'runs'/name/'result.json';j=json.loads(f.read_text())
    digest=hashlib.sha256(f.read_bytes()).hexdigest()
    fault_rows=native_fault_observations(j)
    faults=sorted(set(r['name']+(':'+str(r.get('failure_mask',r.get('fault_code')))
                    if r.get('failure_mask',r.get('fault_code')) is not None else '') for r in fault_rows))
    if j.get('main_sha256')=='9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f':
        for row in j.get('startup_observer',{}).get('stops',[]):
            if row.get('name')!='device_snapshot_export':continue
            stack=bytes.fromhex(row.get('caller_stack_hex',''))
            # Pinned original fatal handler calls40e01520 at40e03698,
            # then eventually enters the terminal loop40e036dc. A register
            # export alone is not an error: require this saved native caller.
            if len(stack)>=0x60 and int.from_bytes(stack[0x58:0x60],'little')==0x40e0369c:
                faults.append('native_cpu_exception_path')
    # CAPTG error observers do not cover capture-control faults. Original
    # C5.32 40fc5484 sets this latch, and547's actual LCD shows the native
    # "Press shutter-release button to reset" dialog. Empty observer output
    # must not hide a fault retained in the original readiness snapshot.
    readiness=j.get('capture-final-readiness',{}).get('capture-controller',{})
    if (j.get('firmware_sha256')=='6380ded18395ce11cb327c766721274c85127d2cf1a1e887ee60e3d156810bdd'
            and readiness.get('address')=='0xa03d9da00'):
        raw=bytes.fromhex(readiness.get('raw_hex',''))
        if len(raw)>=0x1fc and int.from_bytes(raw[0x1f8:0x1fc],'little')&0x40000000:
            faults.append('capture_control_fault_latched:0x40000000')
    transitions=j.get('capture_recovery_flow',{}).get('transitions',[])
    for row in transitions:
        if row.get('name','').endswith('pipeline_error_descriptor'):
            raw=bytes.fromhex(row.get('fault_payload_hex',''))
            if len(raw)>=12:
                faults.append('native_error_descriptor:'+hex(int.from_bytes(raw[:4],'little')))
    faults=sorted(set(faults))
    c=j.get('capture_sequence',{});w=j.get('mode_key_waveform',{})
    lcd=c.get('after',{}).get('lcd')
    if lcd is None:lcd=(j.get('display_console_captures') or [{}])[-1].get('scanout',{})
    out=dict(run=name,result_sha256=digest,owned_stopped=bool(j.get('owned_qemu_stopped')),
        host_error=j.get('error'),inputs=len(c.get('inputs',w.get('stages',[]))),
        host_failed_checks=[row['name'] for row in j.get('checks',[]) if not row.get('passed',False)],
        all_inputs_consumed=c.get('all_inputs_consumed',w.get('all_consumed',False)),
        observed_native_faults=faults,postshot_liveview=c.get('liveview_after_contacts',False),
        final_lcd_video=bool(lcd.get('last_frame_has_video')),
        full_raw_file=False,full_jpeg_file=False,video_file=False,raw_transport_samples_verified=False,
        scope='Original input delivery, observed faults and independently audited artifacts; no physical-camera acceptance')
    if not c and w:
        # The ZR input consumer can finish before the original screen changes.
        # Require fresh producer AND visible LCD frames after the last contact,
        # using same-guest snapshots. An old video layer proves neither.
        screens=j.get('display_console_captures',[])
        label='zr-key-state-%03d.ppm'%len(w.get('stages',[]))
        released=next((s for s in screens if s.get('file')==label),{})
        final=screens[-1] if screens else {}
        available=bool('raw' in released and 'raw' in final)
        out['postshot_observation_available']=available
        if available:
            delta=final['raw']['frames']-released['raw']['frames']
            out['postshot_raw_frames']=delta
            out['postshot_liveview']=bool(out['all_inputs_consumed'] and delta>0 and
                final['scanout']['last_frame_has_video'] and
                final['scanout']['video_frames']>released['scanout']['video_frames'])
    handshake=[dict(stage=row['name'].replace('capture_app_recovery_observe_',''),
                    virtual_ns=row.get('virtual_ns'),x0=row.get('registers',{}).get('X00'),
                    gpio=row.get('ccomp_gpio')) for row in transitions if 'ccomp_' in row.get('name','')]
    if handshake:out['controller_handshake']=handshake
    audit=HERE/'evidence'/(name+'-whole-file-verification.json')
    if audit.exists():
        a=json.loads(audit.read_text())
        if a['result_sha256']!=digest:raise ValueError('File audit belongs to another result')
        raw_accepted=False
        if a['raw_file_accepted']:
            pixels=HERE/'evidence'/(name+'-native-nef-audit.json')
            if pixels.exists():
                pixel_audit=json.loads(pixels.read_text())
                if pixel_audit['result_sha256']!=digest:raise ValueError('RAW pixel audit belongs to another result')
                raw_accepted=bool(pixel_audit.get('full_raw_accepted') and
                    verified_f0_profile(pixel_audit.get('raw',{}).get('codec_profile')))
            out['raw_transport_samples_verified']=True
        out.update(full_raw_file=raw_accepted,full_jpeg_file=bool(a['jpeg_file_accepted']),
            actual_file=a['file'],file_bytes=a['bytes'],file_sha256=a['file_sha256'])
    repeated=c.get('repeated_capture',{})
    zr_recovery=None
    if not c and w:
        from zr_workflow_recovery import evaluate
        zr_recovery=evaluate(j,f.parent)
        if len(j.get('capture_cycles',[]))>1:
            repeated=dict(requested=len(j['capture_cycles']),completed=zr_recovery.get('photos',[]),
                all_cycles_recovered=zr_recovery.get('verified',False))
    repeated_audit=HERE/'evidence'/(name+'-repeated-raw-audit.json')
    out['same_session_repeated_raw_files']=False
    if repeated_audit.exists():
        a=json.loads(repeated_audit.read_text())
        if a['result_sha256']!=digest:raise ValueError('Repeated file audit belongs to another result')
        requested=repeated.get('requested',0)
        if (not a.get('same_session_repeated_raw_accepted') or a['requested']!=requested or
                len(a['photos'])!=requested or not 2<=requested<=8):
            raise ValueError('Complete independent repeated file receipt required')
        entropy_accepted=all(verified_f0_profile(photo.get('codec_profile')) for photo in a['photos'])
        out.update(full_raw_file=entropy_accepted,same_session_repeated_raw_files=entropy_accepted,
            raw_transport_samples_verified=True,
            actual_files=a['photos'],all_raw_samples=a['all_raw_samples'])
    out['whole_photo_workflow']=bool(out['owned_stopped'] and out['all_inputs_consumed'] and
        not out['host_error'] and not out['host_failed_checks'] and not faults and out['postshot_liveview'] and
        (out['full_raw_file'] or out['full_jpeg_file']))
    out['whole_raw_workflow']=out['whole_photo_workflow'] and out['full_raw_file']
    out['postshot_menu_roundtrips']=bool(c.get('post_capture_recovery',{}).get('two_menu_roundtrips_verified'))
    if not c and w:
        recovery=zr_recovery
        out['zr_postshot_recovery']=recovery
        if recovery['verified']:
            out['postshot_liveview']=True
            out['postshot_raw_frames']=sum(row['new_raw_frames'] for row in recovery['roundtrips'])
            out['postshot_menu_roundtrips']=True
            out['whole_photo_workflow']=bool(out['owned_stopped'] and out['all_inputs_consumed'] and
                not out['host_error'] and not out['host_failed_checks'] and not faults and (out['full_raw_file'] or out['full_jpeg_file']))
            out['whole_raw_workflow']=out['whole_photo_workflow'] and out['full_raw_file']
    out['whole_raw_menu_workflow']=out['whole_raw_workflow'] and out['postshot_menu_roundtrips']
    out['postshot_menu_roundtrip_count']=len(out.get('zr_postshot_recovery',{}).get('roundtrips',[]))
    out['whole_raw_three_menu_workflow']=bool(out['whole_raw_menu_workflow'] and
        out['postshot_menu_roundtrip_count']>=3)
    out['whole_repeated_raw_menu_workflow']=bool(out['whole_raw_menu_workflow'] and
        out['same_session_repeated_raw_files'] and repeated.get('all_cycles_recovered') and
        len(repeated.get('completed',[]))==repeated.get('requested'))
    # REC is accepted only when a future independent native video-file audit
    # binds its frames, container and start/stop lifecycle to this result.
    out['whole_video_workflow']=False
    from algorithm_execution_provenance import assess
    out['algorithm_execution']=assess(f.parent)
    out['whole_original_algorithm_workflow']=False
    log=f.with_name('stderr.log')
    if log.exists():
        with log.open(errors='replace') as stream:
            first=next((line.rstrip('\n') for line in stream if 'Z9_UNKNOWN' in line),None)
        if first:
            out['first_unmodeled_transaction']=first
            # This known START is also the shared pixel admission boundary.
            # Report a concrete rejected route, rather than treating every
            # refusal as a newly discovered register or a firmware failure.
            if 'addr=0x15100008 ' in first:
                configs=j.get('engine151_configuration_final',{}).get('instances',[])
                controls=j.get('engine151_control_final',{}).get('instances',[])
                if configs and controls and controls[0].get('ready'):
                    c=configs[0]['config'];target=c[0x4c0//4]|(c[0x4c4//4]<<32)
                    out['isp_start_rejection']=dict(control_ready=True,
                        raw_side_requested=c[0x21c//4]==3,raw_target=hex(target),
                        internal_stream_target=target==0xe0000000,
                        scope='Observed configuration at rejected START; stream output is not modeled as RAM')
            if ('addr=0x150c000c ' in first and 'value=0x401e' in first and
                    j.get('probe_arguments',{}).get('capture_direct_stop')):
                devices=j.get('device_states',{})
                single=devices.get('primary-d980-single-frame-state',{})
                d980=devices.get('primary-d980-state',{})
                if single.get('enabled'):
                    out['capture_stop_rejection']=dict(known_opt_in_command=True,
                        single_frame_armed=single.get('armed'),input_epoch=single.get('epoch'),
                        completed_epoch=single.get('completed_epoch'),
                        actual_frames=d980.get('frames'),actual_dma_bytes=d980.get('pixel_dma_bytes'),
                        scope='Known401e capture drain requires an actual completed single frame; these observed incomplete prerequisites do not authorize bypassing drain ownership')
    (HERE/'evidence'/(name+'-workflow-status.json')).write_text(json.dumps(out,indent=2)+'\n')
    return out


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run');a=ap.parse_args()
    print(json.dumps(summarize(a.run)))
