# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed original-algorithm scope from the run's archived build sources."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def assess(run):
    run=Path(run)
    policy_file=HERE/'algorithm_execution_policy.json'
    policy=json.loads(policy_file.read_text(encoding='utf-8'))
    manifest_file=run/'shared-z9-build-manifest.json'
    sources={};missing=[]
    if manifest_file.exists():
        manifest=json.loads(manifest_file.read_text())
        for name,expected in manifest['compiled_sources'].items():
            f=run/name
            if not f.exists():
                missing.append(name)
                continue
            content=f.read_bytes()
            actual=hashlib.sha256(content).hexdigest()
            if actual!=expected:raise ValueError('Archived algorithm source changed: '+name)
            sources[name]=dict(sha256=actual,text=content.decode(errors='replace'))
    def evidence(name,marker):
        source=sources.get(name)
        if not source or marker not in source['text']:return None
        return dict(file=name,sha256=source['sha256'],marker=marker)
    observations={
        'isp':('functional simplified Bayer/ISP',evidence('nikon-raw-pixels.h','nikon_raw_pixels_yuv')),
        'dsp':('configuration retained; no CEVA instruction core',evidence('nikon-z9-lab.c','no DSP execution')),
        'h265':('host x265 encoder; vendor microcode not executed',evidence('nikon-wave5-codec.h','x265_api_get')),
        'raw_compression':('WLVR/zlib simulation transport; original compression not executed',
                           evidence('nikon-z9-video-raw.h','compress2')),
        'jpeg':('host libjpeg encoder using submitted quantizers',evidence('nikon-z9-jpeg.h','jpeg_create_compress')),
    }
    algorithms={}
    for algorithm in policy['required_algorithms']:
        description,source=observations[algorithm]
        algorithms[algorithm]=dict(original_algorithm_accepted=False,
            compiled_implementation=description if source else 'No verified original execution evidence',
            source=source,reason='A source/code load or native driver completion does not prove original arithmetic execution')
    algorithms['raw_compression']['functional_still_f0_source']=evidence(
        'nikon-expeed-lossless.h','nikon_z8_lossless14_encode')
    algorithms['raw_compression']['functional_still_f0_scope']=(
        'Opt-in open-source F0/14-bit entropy encoder; its presence is not original Nikon codec execution or video compression proof')
    avc = evidence('nikon-wave5-codec.h', 'x264_encoder_encode')
    if avc:
        algorithms['h265']['separate_functional_avc_source'] = avc
        algorithms['h265']['separate_functional_avc_scope'] = (
            'Typed AVC8/AVC10 source DMA uses the public host x264 API. It is not HEVC, '
            'REDCODE/R3D encoding or original vendor microcode execution.')
    dsp_boot = evidence('nikon-expeed-dsp-boot.h', 'dsp_boot_complete')
    if dsp_boot:
        algorithms['dsp']['compiled_implementation'] = (
            'Optional functional boot, power and message transport; no CEVA instruction core')
        algorithms['dsp']['functional_boot_interface_source'] = dsp_boot
        algorithms['dsp']['functional_boot_scope'] = (
            'Original ARM driver can use modeled boot/power/message delivery; this does not execute '
            'vendor DSP instructions or prove ISP/NN/codec arithmetic')
        session = evidence('nikon-expeed-dsp-boot.h', 'dsp_session_initialize')
        if session:
            algorithms['dsp']['functional_session_source'] = session
            algorithms['dsp']['functional_session_scope'] = (
                'Optional host workspace clearing, opaque program retention and owned initialization '
                'reply. This does not execute vendor DSP instructions or neural inference.')
        motion = evidence('nikon-expeed-motion.h', 'motion_track')
        if motion:
            algorithms['dsp']['functional_motion_source'] = motion
            algorithms['dsp']['functional_motion_scope'] = (
                'Opt-in generic FAST9 and integer SAD/median translation with real point records and '
                'owned image-job results. This is not original KRAN/KLT/CEVA arithmetic or inference.')
        correction = evidence('nikon-expeed-correction.h', 'correction_initialize')
        if correction:
            algorithms['dsp']['functional_correction_source'] = correction
            algorithms['dsp']['functional_correction_scope'] = (
                'Actual calibration copy/context initialization, generic same-CFA neighbor '
                'plan and functional stripe descriptors. Vendor map transforms, pixel '
                'correction and original CEVA instructions remain unsupported.')
    # No current run has a verified original ISA/hardware arithmetic receipt.
    # Keep functional file/transport acceptance separate in the caller.
    return dict(required=policy['require_original_algorithms'],
        policy_sha256=hashlib.sha256(policy_file.read_bytes()).hexdigest(),
        archived_sources_verified=bool(sources) and not missing,
        missing_archived_sources=missing,verified_source_count=len(sources),algorithms=algorithms,
        supporting_materials=policy.get('supporting_materials',{}),
        original_algorithm_suite_accepted=False,
        scope='Original-algorithm execution requirement; diagnostic functional workflows remain separate')
