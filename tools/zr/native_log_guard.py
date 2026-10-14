# SPDX-License-Identifier: GPL-2.0-or-later
"""Incremental fault scan of one owned, append-only QEMU stderr log.

The complete original file remains available for final evidence capture. This
only avoids repeatedly decoding the whole file during host polling; it does
not change guest clocks, instructions, data, devices or completion conditions.
"""
import errno
from pathlib import Path
import time


class NativeLogGuard:
    TOKEN=b'Z9_UNKNOWN'

    def __init__(self,path):
        self.path=Path(path)
        self.reader=None
        self.suffix=b''
        self.failed=False
        self.polls=0
        self.bytes_scanned=0
        self.position=0
        self.transient_retries=0

    def read_chunk(self,size):
        deadline=time.monotonic()+1
        while True:
            try:
                if self.reader is None:self.reader=self.path.open('rb',buffering=0)
                # Only committed reads advance the cursor. A failed read can
                # consume bytes internally; reopening must not lose them.
                self.reader.seek(self.position)
                return self.reader.read(size)
            except OSError as error:
                if error.errno not in (errno.EAGAIN,errno.EINTR,getattr(errno,'ENODATA',61)):
                    raise
                self.transient_retries+=1
                self.close()
                if time.monotonic()>=deadline:raise
                time.sleep(.005)

    def poll(self):
        self.polls+=1
        if self.failed:return True
        end=self.path.stat().st_size
        if end<self.position:raise RuntimeError('Owned append-only log was truncated')
        while self.position<end:
            chunk=self.read_chunk(min(65536,end-self.position))
            if not chunk:raise RuntimeError('Owned log became unreadable before its captured end')
            self.position+=len(chunk)
            self.bytes_scanned+=len(chunk)
            combined=self.suffix+chunk
            self.failed=self.TOKEN in combined
            self.suffix=combined[-(len(self.TOKEN)-1):]
            if self.failed:break
        return self.failed

    def close(self):
        if self.reader is not None:
            self.reader.close()
            self.reader=None

    def receipt(self):
        return dict(polls=self.polls,bytes_scanned=self.bytes_scanned,position=self.position,
                    transient_retries=self.transient_retries,
                    fault_found=self.failed,scope='owned append-only log polling; full original log retained')
