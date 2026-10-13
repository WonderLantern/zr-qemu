# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit every original NEF from repeated photos in one stopped Z9/ZR session.

First create a read-only virtual-card audit and catalog in the stopped run directory. This tool uses independent
LibRaw decoding and per-photo original producer/codec snapshots, including
every RAW sample. Repeated released photos are not continuous burst mode.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import numpy as np
from PIL import Image
import rawpy
from audit_native_nef import image_ifds, MODELS
from extract_virtual_exfat import extract
from nef_codec_profile import require_f0_lossless14



def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def original(run,filename):
    if not isinstance(filename,str) or Path(filename).name!=filename:
        raise ValueError('One original run-local filename required')
    path=Path(run)/filename
    if not path.is_file():raise ValueError('Original producer/codec snapshot missing: '+filename)
    return path


def audit(run):
    directory=Path(run).resolve()
    rp=directory/'result.json';native=json.loads(rp.read_text())
    sequence=native.get('capture_sequence',{});repeat=sequence.get('repeated_capture',{})
    digest=native.get('firmware_sha256',native.get('main_sha256'))
    model=next((name for name,contract in MODELS.items() if contract['firmware_sha256']==digest),None)
    if model is None:raise ValueError('Pinned model fingerprint required')
    if model=='zr':
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parent/'zr'))
        from zr_workflow_recovery import evaluate
        recovery=evaluate(native,directory)
        repeat=dict(requested=recovery.get('requested',0),completed=recovery.get('photos',[]),all_cycles_recovered=recovery.get('verified',False))
        sequence=dict(all_inputs_consumed=native.get('mode_key_waveform',{}).get('all_consumed',False))
    requested=repeat.get('requested',0);cycles=repeat.get('completed',[])
    if (native.get('error') or not native.get('owned_qemu_stopped') or native.get('cpu_register_redirection') or
        not sequence.get('all_inputs_consumed') or not repeat.get('all_cycles_recovered') or
        not 2<=requested<=8 or len(cycles)!=requested):
        raise ValueError('Complete stopped same-session repeated RAW/recovery/menu workflow required')
    contract=MODELS[model]
    if native.get('firmware_sha256',native.get('main_sha256'))!=contract['firmware_sha256']:
        raise ValueError('RAW contract belongs to another firmware')
    checked=json.loads((directory/'capture-card.audit.json').read_text())
    if checked['fsck_exit'] or not checked['source_unchanged']:
        raise ValueError('Actual stopped card audit must pass first')
    volume=Path(checked['derived_volume'])
    listing=json.loads((directory/'capture-card.catalog.json').read_text())
    photos=sorted([row for row in listing['files'] if not row['directory'] and
                   Path(row['path']).suffix.upper() in ('.NEF','.JPG')],key=lambda row:row['path'])
    if len(photos)!=requested or any(Path(row['path']).suffix.upper()!='.NEF' for row in photos):
        raise ValueError('Exactly one actual initialized NEF per photo is required')
    dumps=native.get('raw_side_native_dumps',[])
    if len(dumps)!=requested:raise ValueError('Each photo needs its own original RAW producer snapshot')
    results=[]
    for index,(row,cycle) in enumerate(zip(photos,cycles),1):
        if cycle['cycle']!=index or not cycle.get('fresh_liveview_and_menus'):
            raise ValueError('Original ordered photo recovery receipts required')
        baseline=cycle['baseline']
        candidates=[entry for entry in dumps if entry['cycle']==index and entry['job']==baseline['raw_jobs']+1]
        if len(candidates)!=1:raise ValueError('Unique actual RAW producer per photo required')
        producer=candidates[0];side=producer['state']
        if side.get('pending') or side['acks']!=side['jobs']:
            raise ValueError('Actual RAW producer must be acknowledged')
        nef=directory/Path(row['path']).name
        if nef.exists():
            receipt=json.loads(nef.with_suffix('.NEF.extraction.json').read_text())
            if receipt['entry']!=row or receipt['sha256']!=sha(nef):
                raise ValueError('Preserved original file extraction differs')
        else:
            receipt=extract(volume,row['path'],nef)
        data=nef.read_bytes();ifds=image_ifds(data)
        raws=[entry['tags'] for entry in ifds if entry['tags'].get(254)==[0] and entry['tags'].get(262)==[32803]]
        if len(raws)!=1:raise ValueError('One full native RAW descriptor per actual file required')
        tags=raws[0];width,height,bits=tags[256][0],tags[257][0],tags[258][0]
        if (width,height)!=contract['raw_size'] or bits!=14:
            raise ValueError('Native full RAW geometry differs')
        offsets,counts=tags.get(273,[]),tags.get(279,[])
        if not offsets or len(offsets)!=len(counts) or any(n<=0 or o+n>len(data) for o,n in zip(offsets,counts)):
            raise ValueError('All declared RAW strips must be initialized')
        codec_profile=require_f0_lossless14(nef,tags)
        source=original(directory,producer['files']['target'])
        pitch=producer['bytes']//height
        if pitch*height!=source.stat().st_size or pitch<width*14//8:
            raise ValueError('Actual per-photo producer span differs')
        packed=np.memmap(source,mode='r',dtype=np.uint8,shape=(height,pitch))
        with rawpy.imread(str(nef)) as raw:
            if raw.raw_image.shape!=(height,width):raise ValueError('Independent full decode has wrong shape')
            for y in range(height):
                groups=packed[y,:width*14//8].reshape(-1,7).astype(np.uint64)
                words=sum(groups[:,b]<<(8*b) for b in range(7))
                expected=np.stack([(words>>(14*b))&16383 for b in range(4)],axis=1).reshape(-1)
                if not np.array_equal(raw.raw_image[y],expected):
                    raise ValueError('RAW photo '+str(index)+' differs at row '+str(y))
        del packed
        upper=cycles[index]['baseline']['jpeg_jobs'] if index<requested else native['engine15e2_jpeg_final']['jobs']
        streams=[entry for entry in native['jpeg_completed_native_dumps']
                 if baseline['jpeg_jobs']<entry['job']<=upper and not entry.get('count_only')]
        previews=[]
        for entry in ifds:
            values=entry['tags']
            if 513 not in values or 514 not in values:continue
            offset,length=values[513][0],values[514][0]
            if length<=0 or offset+length>len(data):raise ValueError('Native preview outside actual file')
            blob=data[offset:offset+length];digest=hashlib.sha256(blob).hexdigest()
            matches=[item['job'] for item in streams for f in item.get('files',[])
                     if f['label']=='encoded' and f['sha256']==digest and f['bytes']==length and
                     sha(original(directory,f['file']))==digest]
            if len(matches)!=1:raise ValueError('Preview must match this photo\'s unique complete codec job')
            with Image.open(io.BytesIO(blob)) as image:image.load();size=list(image.size)
            previews.append(dict(decoded_size=size,native_job=matches[0],bytes=length,sha256=digest))
        if not all(list(size) in [entry['decoded_size'] for entry in previews]
                   for size in (contract['preview_size'],(1620,1080),(160,120))):
            raise ValueError('All three original previews required per photo')
        results.append(dict(cycle=index,file=row['path'],bytes=len(data),sha256=receipt['sha256'],
            raw_samples=width*height,raw_producer_job=producer['job'],producer_sha256=sha(source),
            codec_profile=codec_profile,
            full_raw_accepted=True,previews=previews,fresh_liveview_and_menus=True))
    result=dict(run=directory.name,result_sha256=sha(rp),tool_sha256=sha(Path(__file__)),
        photos=results,requested=requested,rawpy=rawpy.__version__,libraw=list(rawpy.libraw_version),
        all_raw_samples=sum(photo['raw_samples'] for photo in results),same_session_repeated_raw_accepted=True,
        burst_mode_verified=False,raw_precapture_verified=False,video_recording_verified=False,
        scope='actual same-guest/card repeated released photos; every RAW sample and per-photo JPEG codec bytes')
    receipt_path=directory/'repeated-raw-audit.json'
    receipt_path.open('x',encoding='utf-8').write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(run=directory.name,photos=requested,all_raw_samples=result['all_raw_samples'],
        repeated_raw_accepted=True,burst_mode_verified=False,receipt=str(receipt_path))))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    audit(parser.parse_args().output)
