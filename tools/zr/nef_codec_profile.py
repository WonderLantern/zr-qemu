# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only F0 metadata contract; reject the known packed-size false positive."""
import hashlib
import os
from pathlib import Path
import struct
import subprocess


def verified_f0_profile(profile):
    """Require the explicit format contract in a result-bound pixel receipt."""
    return bool(isinstance(profile,dict) and
        profile.get('encoding')=='nikon-f0-lossless14' and
        profile.get('libraw_packed_fallback_excluded') is True and
        profile.get('predictor_seeds')==[2048]*4 and
        isinstance(profile.get('raw_strip_bytes'),int) and
        profile['raw_strip_bytes']>4 and
        profile['raw_strip_bytes']!=profile.get('uncompressed_packed_bytes'))


def require_f0_lossless14(path,tags):
    path=Path(path).resolve()
    width,height,bits=(tags[key][0] for key in (256,257,258))
    if bits!=14 or tags.get(259)!=[34713] or width%4:
        raise ValueError('14-bit Nikon-compressed RAW IFD required')
    sizes=tags.get(279,[])
    fallback=[((width*7*channels//4+15)//16*16)*height for channels in (1,3)]
    if len(sizes)!=1 or sizes[0]<=4 or sizes[0] in fallback:
        raise ValueError('Nikon entropy coding unverified: RAW strip matches packed-size fallback')
    if os.name=='nt':
        if path.drive.upper()!='D:':raise ValueError('Existing D: Nikon evidence required')
        source='/mnt/d'+path.as_posix()[2:]
        command=['wsl','-d','ubuntu-noble-nikon','--','exiftool','-b','-NEFLinearizationTable',source]
    else:
        if (os.name=='nt' or os.environ.get('WSL_DISTRO_NAME')=='ubuntu-noble'):raise ValueError('Nikon WSL only')
        command=['exiftool','-b','-NEFLinearizationTable',str(path)]
    data=subprocess.check_output(command,timeout=30)
    if not data.startswith(b'F0'+struct.pack('<4H',2048,2048,2048,2048)):
        raise ValueError('Verified F0/four2048 metadata profile required')
    return dict(encoding='nikon-f0-lossless14',libraw_packed_fallback_excluded=True,
                predictor_seeds=[2048]*4,linearization_sha256=hashlib.sha256(data).hexdigest(),
                raw_strip_bytes=sizes[0],uncompressed_packed_bytes=fallback[0],
                independent_decoder_required=True,physical_codec_verified=False)
