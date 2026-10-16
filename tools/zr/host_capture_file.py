# SPDX-License-Identifier: GPL-2.0-or-later
"""Stage QEMU capture output on its native filesystem before checked archival."""
import errno
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from probe import sha


def _link(source,target):
    try:os.link(source,target)
    except OSError as error:
        if error.errno in (errno.EXDEV,errno.EPERM,errno.ENOTSUP,errno.EMLINK):return False
        raise
    return True


def publish(guest, source, target, *, expected_size=None):
    source,target=Path(source),Path(target)
    if source.parent.resolve()!=guest.runtime.resolve() or target.parent.resolve()!=guest.out.resolve():
        raise ValueError('Capture must stay in this owned run')
    if target.exists():raise ValueError('Preserve previous capture evidence')
    if not source.is_file() or (expected_size is not None and source.stat().st_size!=expected_size):
        raise ValueError('Incomplete native capture')
    digest=sha(source);started=time.monotonic()
    # Each producer dump still comes from a new completed pmemsave. These
    # unique RAW/key-state plane names are immutable after publication;
    # mutable LCD/control captures and arbitrary files stay outside the cache.
    raw=bool(re.fullmatch(r'engine151-raw-side-(?:job\d+-)?(?:source|target)\.bin',target.name))
    lcd=bool(re.fullmatch(r'zr-key-state-\d{3}-(?:video-y|video-uv|alpha|color)\.bin',target.name))
    immutable=raw or lcd
    cache=getattr(guest,'_immutable_capture_archives',None)
    if cache is None:cache={};guest._immutable_capture_archives=cache
    key=(source.stat().st_size,digest);prior=cache.get(key) if immutable else None
    archive_linked=native_linked=False
    if prior:
        native,archive=prior
        if (native.parent.resolve()!=guest.runtime.resolve() or archive.parent.resolve()!=guest.out.resolve() or
                sha(native)!=digest or sha(archive)!=digest):
            raise ValueError('Previous immutable RAW evidence changed')
        archive_linked=_link(archive,target)
        temporary=source.with_name(source.name+'.hardlink-'+uuid.uuid4().hex)
        try:
            if _link(native,temporary):
                if sha(temporary)!=digest:raise ValueError('Native RAW hard link differs')
                os.replace(temporary,source);native_linked=True
        finally:
            if temporary.exists():temporary.unlink()
    if not archive_linked:
        with source.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
    if sha(target)!=digest:raise ValueError('Native capture archive differs')
    if immutable and sha(source)!=digest:raise ValueError('Actual native capture changed')
    if immutable:
        cache.setdefault(key,(source,target))
        record='immutable_raw_capture_storage' if raw else 'immutable_lcd_capture_storage'
        guest.data.setdefault(record,[]).append(dict(file=target.name,
            bytes=key[0],sha256=digest,native_linked=native_linked,archive_linked=archive_linked,
            prior_file=prior[1].name if prior else None,
            scope='New actual full pmemsave verified before lossless same-run storage deduplication; no frame replay'))
    elapsed=time.monotonic()-started
    state=guest.data.setdefault('host_capture_archive',dict(files=0,bytes=0,seconds=0,max_seconds=0,
        native_filesystem_first=True,scope='Host capture IO only; identical stopped guest bytes, no image transformation'))
    state['files']+=1;state['bytes']+=target.stat().st_size;state['seconds']+=elapsed
    state['max_seconds']=max(state['max_seconds'],elapsed)
    archive=guest.out/Path(__file__).name
    if not archive.exists():archive.write_bytes(Path(__file__).read_bytes())


def memory(guest, address, amount, target):
    if not 0<amount<=128*1024*1024:raise ValueError('Bounded capture required')
    target=Path(target);staged=guest.runtime/(target.name+'.capture')
    if staged.exists() or target.exists():raise ValueError('Preserve previous native capture')
    reply=guest.qmp.hmp(f'pmemsave {address:#x} {amount:#x} "{staged}"')
    if reply:raise RuntimeError(reply)
    publish(guest,staged,target,expected_size=amount)
