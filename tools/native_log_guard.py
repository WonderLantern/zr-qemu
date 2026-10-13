# SPDX-License-Identifier: GPL-2.0-or-later
"""Incremental fault scan of one owned, append-only QEMU stderr log.

The complete original file remains available for final evidence capture. This
only avoids repeatedly decoding the whole file during host polling; it does
not change guest clocks, instructions, data, devices or completion conditions.
"""
from pathlib import Path


class NativeLogGuard:
    TOKEN=b'Z9_UNKNOWN'

    def __init__(self,path):
        self.path=Path(path)
        self.reader=None
        self.suffix=b''
        self.failed=False
        self.polls=0
        self.bytes_scanned=0

    def poll(self):
        self.polls+=1
        if self.failed:return True
        if self.reader is None:self.reader=self.path.open('rb')
        chunk=self.reader.read()
        self.bytes_scanned+=len(chunk)
        if chunk:
            combined=self.suffix+chunk
            self.failed=self.TOKEN in combined
            self.suffix=combined[-(len(self.TOKEN)-1):]
        return self.failed

    def close(self):
        if self.reader is not None:
            self.reader.close()
            self.reader=None

    def receipt(self):
        return dict(polls=self.polls,bytes_scanned=self.bytes_scanned,
                    fault_found=self.failed,scope='owned append-only log polling; full original log retained')
