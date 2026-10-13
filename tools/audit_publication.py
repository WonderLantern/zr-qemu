# SPDX-License-Identifier: GPL-2.0-or-later
"""Check the explicitly reviewed source inventory and every reachable Git blob.

This is a guard against unintended additions, not a license/copyright oracle.
--refresh-manifest is for maintainers after manual content/provenance review.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'publication-manifest.json'
FILES = {'tools/z9_global1_boundary_input.py', 'tools/capture_engine15e2.py', 'tools/virtual_recording_card.py', 'tools/zr/service_serial8.py', 'README.zh-CN.md', 'docs/firmware.md', 'tools/zr/profiles/zr-native-preview.json', 'tools/capture_sequence.py', 'tools/smoke_qemu.py', 'tools/zr/native_log_guard.py', 'tools/zr/nef_codec_profile.py', 'docs/development-snapshot.md', 'tools/z9_timing_input.py', 'tools/zr/capture_lcd_planes.py', 'tools/z9_sequence_resource_input.py', 'tools/zr/check_adc.py', 'tools/private_bounded_qmp.py', 'tools/zr/capture_engine151_pixels.py', 'tools/capture_support.py', 'tools/zr/zr_mcu_bindings.py', 'tools/capture_engine152c.py', 'tools/zr/contract_guest.py', 'tools/receive_mcu_tx.py', 'tools/zr/capture_lcd_direct_candidate.py', 'tools/zr/profiles/zr-native-lossless14-repeated-raw-whole.json', 'tools/zr/zr_key_sequence.py', 'docs/research-notes.md', 'tools/zr/zr_sequence_resources.py', 'tools/capture_engine153.py', 'tools/inspect_virtual_exfat.py', 'tools/capture_frame_conversion.py', 'tools/zr/mcu_frames.py', 'tests/test_capture_contracts.py', 'tools/zr/zr_resource0c_input.py', 'tools/zr/zr_video_ready.py', 'tools/zr/zr_device_parameter_input.py', 'qemu/designware-dma.patch', 'tools/z9_processing_index_input.py', 'tools/observe_serial_channel.py', 'tools/zr/zr_display_input.py', 'tools/extract_virtual_exfat.py', 'tools/capture_thumbnail_route.py', 'qemu/nikon-z9-lab.c', 'qemu/nikon-z9-pixels.h', 'tools/interactive.html', 'tools/zr/capture_zr_rtc.py', 'tools/zr/zr_input_start.py', 'qemu/nikon-z9-pcie.h', 'NOTICE.md', 'tools/capture_workflow_ready.py', 'tools/zr/probe_adc_capture.py', 'tools/zr/probe_zr_mcu.py', 'tools/zr/profiles/zr-native-functional-r3d-source-flow-recording.json', 'qemu/nikon-wave5-codec.h', 'tools/zr/zr_source_stop_drain.py', 'qemu/nikon-raw-pixels.h', 'tools/zr/observe_zr_mode_writes.py', 'tools/capture.py', 'tools/zr/algorithm_execution_provenance.py', 'tools/zr/zr_resource_integrity_input.py', 'tools/zr/algorithm_execution_policy.json', 'docs/architecture.md', 'qemu/arm-service-events.patch', 'tools/native_log_guard.py', 'tools/rtc_mcu_input.py', 'tools/zr/probe.py', 'qemu/nikon-z9-capture-nv16.h', 'tools/z9_quality_input.py', 'tools/zr/capture_repeat_flow.py', 'tools/probe_tasks.py', 'tools/zr/zr_resource_group_input.py', 'tools/zr/zr_recording_pacing.py', 'tests/test_pixels.c', 'tools/audit_repeated_capture.py', 'docs/build.md', 'tools/zr/zr_video_callbacks.py', 'tools/capture-lossless14-profile.json', 'tools/capture-profile.json', 'qemu/nikon-z9-jpeg.h', 'docs/debugging.md', 'tools/zr/service_z9_mcu.py', 'qemu/nikon-expeed-dsp-boot.h', 'tools/z9_navigation_input.py', 'tools/make_cmos.py', 'tools/parameter_input.py', 'tools/native_menu_screen.py', 'tools/zr/capture_engine15e2.py', 'qemu/nikon-z9-d980.h', 'tools/zr/capture_workflow_ready.py', 'tools/zr/profiles/zr-landscape-raw.json', 'qemu/nikon-expeed-correction.h', 'tools/zr/probe_graphics_image.py', 'tools/zr/trace_native_lifecycle.c', 'tools/capture_virtual_ram.py', 'tools/zr/capture_stream_progress.py', 'qemu/nikon-expeed-motion.h', 'requirements-capture.txt', 'qemu/nikon-z9-video-raw.h', 'qemu/nikon-z9-wave5.h', 'tools/validate_run.py', 'tools/zr/observe_serial_channel.py', 'tools/capture_nv16_pipeline.py', 'tools/service_serial8.py', 'tools/zr/deliver_mcu_frame.py', 'README.md', 'CONTRIBUTING.md', 'docs/usage.md', 'tools/guest_transport.py', 'tools/zr/capture_dsp_job_inputs.py', 'qemu/nikon-expeed-lossless.h', 'tools/boot.py', 'tools/zr/native_workflow_status.py', 'tools/zr/virtual_recording_card.py', 'tools/zr/zr_workflow_recovery.py', 'tools/capture_repeat_flow.py', 'tools/check_service_events.py', 'tools/export_card.py', 'tools/probe_graphics_image.py', 'tools/zr/zr_ui_language_input.py', 'tools/capture_native_image_arguments.py', 'tools/capture_thumbnail_nv16.py', 'tools/deliver_mcu_frame.py', 'tools/zr/capture_jpeg_completed.py', 'docs/zr-inputs.md', 'tools/run.py', 'tools/build.py', 'tools/zr/shared_z9_build.py', 'tools/ccomp_command_peer.py', 'tools/capture_recovery_flow.py', 'tools/zr/capture_zr_gpio.py', 'tools/capture_readiness.py', 'tests/run.sh', 'COPYING', 'LICENSES/QEMU-LICENSE.txt', 'tools/guest.py', 'tools/zr/capture_engine153.py', 'docs/capture.md', 'docs/publication.md', 'tools/capture_jpeg_completed.py', 'tools/probe_adc_capture.py', 'tools/service_z9_mcu.py', 'tests/test_inputs.py', 'tools/zr/probe_zr_boot.py', 'tools/capture_engine153_layout.py', 'docs/testing.md', 'tools/init_table_input.py', 'tools/z9_exposure_input.py', 'tools/zr/zr_mode_write_watch.py', 'qemu/nikon-z9-thumbnail-nv16.h', 'qemu/prepare_source.py', 'tools/z9_primary_gate_input.py', 'tools/zr/observe_z9_display.py', 'qemu/nikon-zr-lab.c', 'tools/zr/profiles/zr-landscape-english.json', 'tools/capture_engine151_pixels.py', 'tools/probe.py', 'tools/zr/capture_virtual_ram.py', 'tools/zr/capture_zr_lcd.py', 'tools/zr/rtc_mcu_input.py', 'tools/mcu_frames.py', 'tools/zr/probe_tasks.py', 'tools/zr/capture_processor_ram.py', 'docs/capture.zh-CN.md', 'docs/service-events.md', 'tools/zr/native_lifecycle_plugin.py', 'tools/zr/capture_zr_secondary.py', '.github/workflows/ci.yml', 'tools/audit_native_nef.py', 'tools/zr/zr_orientation_input.py', 'tools/zr/profiles/zr-video-native-source-flow-bindings.json', 'tools/run_zr.py', 'tools/nef_codec_profile.py', '.gitattributes', 'tools/fast_capture_worker.py', 'tools/model-properties.json', 'tools/zr/capture_zr_ui_flow.py', 'tools/audit_publication.py', '.gitignore', 'tools/zr/observe_zr_startup.py', 'source-snapshot.json', 'tools/zr/zr_input_clock.py', 'tools/capture_processing_input.py', 'tools/observe_z9_state8.py', 'tools/zr/capture_dsp_correction_inputs.py', 'tools/zr/profiles/zr-native-functional-main10-source-flow-recording.json', 'requirements.txt'}
IGNORED = {'.git','.local','.build','.venv','__pycache__'}
SECRET_PATTERNS = [
    re.compile(r'gh[opusr]_[A-Za-z0-9]{30,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{30,}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]

def validate(path, data):
    if path not in FILES | {MANIFEST}: raise ValueError('Unreviewed public path: '+path)
    if len(data)>(2*1024*1024 if path == 'qemu/nikon-z9-lab.c' else 512*1024) or b'\0' in data: raise ValueError('Unexpected binary/large content: '+path)
    text = data.decode('utf-8')
    if any(pattern.search(text) for pattern in SECRET_PATTERNS): raise ValueError('Credential pattern in '+path)
    if re.search(r"['\"][0-9a-fA-F]{512,}['\"]",text): raise ValueError('Large embedded hex data needs review: '+path)
    if path.endswith(('.py','.c','.h','.sh')) and 'SPDX-License-Identifier: GPL-2.0-or-later' not in text[:200]:
        raise ValueError('Missing source license: '+path)
    return hashlib.sha256(data).hexdigest()

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--refresh-manifest',action='store_true')
    a = p.parse_args()
    discovered = set()
    for directory,dirs,files in os.walk(ROOT):
        dirs[:] = [name for name in dirs if name not in IGNORED]
        for name in files:
            path = Path(directory)/name
            if path.is_symlink(): raise ValueError('Symlink in public tree: '+str(path))
            discovered.add(path.relative_to(ROOT).as_posix())
    if discovered - {MANIFEST} != FILES:
        raise ValueError('Inventory differs: '+str({'extra':sorted(discovered-FILES-{MANIFEST}),'missing':sorted(FILES-discovered)}))
    hashes = {name:validate(name,(ROOT/name).read_bytes()) for name in sorted(FILES)}
    if a.refresh_manifest:
        (ROOT/MANIFEST).write_text(json.dumps({'schema':1,'scope':'reviewed source-only publication inventory; no runtime artifacts','files':hashes},indent=2)+'\n',encoding='utf-8',newline='\n')
    manifest = json.loads((ROOT/MANIFEST).read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('files') != hashes: raise ValueError('Content changed since reviewed manifest')
    validate(MANIFEST,(ROOT/MANIFEST).read_bytes())
    commits = 0; blobs = set()
    if (ROOT/'.git').exists():
        # Inspect all refs, rather than only the currently visible checkout.
        refs = git('rev-list','--all').decode().splitlines()
        commits = len(refs)
        for ref in refs:
            tree = git('ls-tree','-rz','--full-tree',ref).split(b'\0')
            for row in tree:
                if not row: continue
                meta,name = row.split(b'\t',1)
                mode,kind,oid = meta.decode().split()
                name = name.decode('utf-8')
                if kind != 'blob' or mode not in ('100644','100755'): raise ValueError('Unexpected history object: '+name)
                if (oid,name) not in blobs:
                    validate(name,git('cat-file','blob',oid)); blobs.add((oid,name))
        tracked = set()
        for row in git('ls-files','--stage','-z').split(b'\0'):
            if not row: continue
            meta,name = row.split(b'\t',1)
            mode,oid,stage = meta.decode().split()
            name = name.decode('utf-8')
            if stage != '0' or mode not in ('100644','100755'):
                raise ValueError('Unexpected index entry: '+name)
            staged_hash = validate(name,git('cat-file','blob',oid))
            if staged_hash != hashlib.sha256((ROOT/name).read_bytes()).hexdigest():
                raise ValueError('Staged content differs from reviewed worktree: '+name)
            tracked.add(name)
        if tracked != FILES | {MANIFEST}: raise ValueError('Git index differs from reviewed inventory')
    print(json.dumps({'passed':True,'reviewed_files':len(hashes)+1,'history_commits':commits,'history_blobs':len(blobs),'runtime_data_excluded':True}))

if __name__ == '__main__': main()
