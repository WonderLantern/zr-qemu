# SPDX-License-Identifier: GPL-2.0-or-later
"""Check actual camera-written NEF previews and every decoded RAW sample.

Run with a Python environment containing rawpy/LibRaw. The NEF must first
be extracted read-only from the stopped guest's audited card.
"""
import argparse
import hashlib
import io
import json
import re
from pathlib import Path
import struct
import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
MODELS = {
    'z9':dict(firmware_sha256='6380ded18395ce11cb327c766721274c85127d2cf1a1e887ee60e3d156810bdd',
              raw_size=(8280,5520),preview_size=(8256,5504)),
    'zr':dict(firmware_sha256='9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f',
              raw_size=(6064,4040),preview_size=(6048,4032)),
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def image_ifds(data):
    if data[:4] != b'II*\0':
        raise ValueError('Expected actual little-endian TIFF NEF')
    seen, rows = set(), []

    def visit(offset):
        if not offset or offset in seen:
            return
        if len(seen) >= 32 or not 0 <= offset <= len(data)-2:
            raise ValueError('Native IFD bound reached')
        seen.add(offset)
        n = struct.unpack_from('<H', data, offset)[0]
        if n > 1024 or offset+2+12*n+4 > len(data):
            raise ValueError('Native IFD truncated')
        tags = {}
        for i in range(n):
            at = offset+2+12*i
            tag, kind, count, pointer = struct.unpack_from('<HHII', data, at)
            if tag not in (254,256,257,258,259,262,273,278,279,330,513,514) or kind not in (3,4):
                continue
            unit, fmt = (2,'H') if kind == 3 else (4,'I')
            if not 0 < count <= 1024:
                raise ValueError('Native image tag count invalid')
            start = at+8 if unit*count <= 4 else pointer
            if start+unit*count > len(data):
                raise ValueError('Native image tag payload outside file')
            tags[tag] = list(struct.unpack_from('<'+fmt*count, data, start))
        rows.append(dict(offset=offset, tags=tags))
        for child in tags.get(330, []):
            visit(child)
        visit(struct.unpack_from('<I', data, offset+2+12*n)[0])

    visit(struct.unpack_from('<I', data, 4)[0])
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True, help='Stopped capture run directory')
    p.add_argument('--audit-name', help='Fresh receipt name for a repeat audit; preserve earlier evidence')
    a = p.parse_args()
    run = a.output.resolve()
    rp = run/'result.json'
    native = json.loads(rp.read_text(encoding='utf-8'))
    model = 'z9'
    if model not in MODELS:
        raise ValueError('Fingerprinted Z9/ZR capture required')
    contract = MODELS[model]
    if native.get('firmware_sha256',native.get('main_sha256')) != contract['firmware_sha256']:
        raise ValueError('Native RAW geometry contract belongs to another firmware')
    nef = run/'DSC_0001.NEF'
    extraction = json.loads(nef.with_suffix('.NEF.extraction.json').read_text(encoding='utf-8'))
    if not native['owned_qemu_stopped'] or native['cpu_register_redirection']:
        raise ValueError('Stopped original native capture required')
    if nef.stat().st_size != extraction['bytes'] or sha(nef) != extraction['sha256']:
        raise ValueError('Actual extracted NEF changed')
    data = nef.read_bytes()
    ifds = image_ifds(data)
    checks, previews = [], []
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
    contacts = (native.get('capture_sequence', {}).get('all_inputs_consumed', False) if model=='z9'
                else native.get('mode_key_waveform', {}).get('all_consumed', False))
    check('all original external contacts consumed', contacts)
    streams = {entry['job']:next((f for f in entry['files'] if f['label']=='encoded'), None)
               for entry in native['jpeg_completed_native_dumps']}
    for row in ifds:
        tags = row['tags']
        if 513 not in tags or 514 not in tags:
            continue
        offset, length = tags[513][0], tags[514][0]
        if not 0 < length or offset+length > len(data):
            raise ValueError('Native preview outside actual file')
        blob = data[offset:offset+length]
        digest = hashlib.sha256(blob).hexdigest()
        matching = [job for job,f in streams.items() if f and f['sha256']==digest and f['bytes']==length
                    and sha(run/f['file'])==digest]
        with Image.open(io.BytesIO(blob)) as im:
            im.load()
            size = list(im.size)
        check('actual NEF preview at '+hex(offset)+' equals complete original codec output', len(matching)==1)
        previews.append(dict(ifd=row['offset'],offset=offset,bytes=length,sha256=digest,
                             decoded_size=size,native_jobs=matching))
    check('original main, middle and bordered thumbnail all reach the actual card file',
          all(list(size) in [x['decoded_size'] for x in previews]
              for size in (contract['preview_size'],(1620,1080),(160,120))))
    preview_passed = all(x['passed'] for x in checks)
    raw_rows = [x for x in ifds if x['tags'].get(254)==[0] and x['tags'].get(262)==[32803]]
    check('one actual full RAW image descriptor',len(raw_rows)==1)
    raw_result = {}
    if len(raw_rows)==1:
        tags = raw_rows[0]['tags']
        width, height, bits = tags[256][0], tags[257][0], tags[258][0]
        counts, offsets = tags.get(279, []), tags.get(273, [])
        available = bool(counts and len(counts)==len(offsets) and all(n>0 and o+n<=len(data) for o,n in zip(offsets,counts)))
        raw_result.update(width=width,height=height,bits=bits,compression=tags.get(259),strip_offsets=offsets,strip_bytes=counts)
        check('full 14-bit RAW geometry matches actual RAW producer',
              (width,height)==contract['raw_size'] and bits==14)
        check('all declared RAW strips contain actual initialized file bytes',available)
        if available:
            import rawpy
            raw_result.update(rawpy=rawpy.__version__,libraw=list(rawpy.libraw_version))
            try:
                with rawpy.imread(str(nef)) as raw:
                    decoded = raw.raw_image
                    raw_result['decoded_shape']=list(decoded.shape)
                    equal = decoded.shape==(height,width)
                    side = native['engine151_raw_output_final']
                    source = run/'engine151-raw-side-target.bin'
                    if side['jobs']!=1 or side['pending'] or side['acks']!=1:
                        raise ValueError('One acknowledged complete actual RAW producer required')
                    pitch = side['bytes']//height
                    if pitch*height != source.stat().st_size or pitch < width*14//8:
                        raise ValueError('Actual complete producer span differs')
                    actual = np.memmap(source, mode='r', dtype=np.uint8, shape=(height,pitch))
                    if equal:
                        for y in range(height):
                            groups = actual[y,:width*14//8].reshape(-1,7).astype(np.uint64)
                            words = sum(groups[:,b] << (8*b) for b in range(7))
                            expected = np.stack([(words >> (14*b)) & 16383 for b in range(4)],axis=1).reshape(-1)
                            if not np.array_equal(decoded[y],expected):
                                equal=False;raw_result['first_mismatching_row']=y;break
                    raw_result.update(decoded_shape=list(decoded.shape),whole_raw_equal=bool(equal),actual_producer_sha256=sha(source))
                    check('every independently decoded RAW sample equals actual guest producer RAM',equal)
            except FileNotFoundError as error:
                # Extraction was already verified above. A missing producer
                # snapshot after a host capture timeout is not a codec failure.
                raw_result['producer_snapshot_error']=repr(error)
                check('complete actual producer snapshot available',False)
            except Exception as error:
                raw_result['decode_error']=repr(error)
                check('independent whole RAW decode succeeds',False)
    result=dict(run=run.name,model=model,firmware_sha256=contract['firmware_sha256'],
                result_sha256=sha(rp),file_sha256=sha(nef),tool_sha256=sha(Path(__file__)),
                checks=checks,previews=previews,raw=raw_result,previews_accepted=preview_passed,
                full_raw_accepted=all(x['passed'] for x in checks),physical_sensor_or_codec_verified=False,
                scope='actual native NEF/card bytes, embedded original JPEG streams and independent whole RAW pixel oracle; no host file substitution')
    receipt_name=a.audit_name or 'native-nef-audit'
    if not re.fullmatch(r'[a-z0-9-]+',receipt_name):
        raise ValueError('Simple fresh audit receipt name required')
    (run/(receipt_name+'.json')).open('x',encoding='utf-8').write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    if not result['full_raw_accepted']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
