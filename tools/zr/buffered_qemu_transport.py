# SPDX-License-Identifier: GPL-2.0-or-later
"""Buffered EXPEED7 diagnostic QMP, preserving the existing deadline protocol.

The original phase probe and frozen Z7 paths are untouched. SocketIO.readline
with buffering0 performs a recv for each byte; bulk state replies need a real
read buffer. Every command write is explicitly flushed before awaiting a reply.
"""
from probe import QMP as _QMP

BUFFER_BYTES=65536


class _AutoflushFile:
    def __init__(self,fp):self.fp=fp
    def write(self,value):
        count=self.fp.write(value)
        self.fp.flush()
        return count
    def readline(self,*args):return self.fp.readline(*args)
    def close(self):return self.fp.close()
    def flush(self):return self.fp.flush()


class QMP(_QMP):
    def __init__(self,path,startup_timeout=3):
        super().__init__(path,startup_timeout=startup_timeout)
        # The original handshake uses its small unbuffered lines. It has no
        # read-ahead bytes to lose, and both file objects keep the socket alive.
        previous=self.fp
        self.fp=_AutoflushFile(self.sock.makefile('rwb',buffering=BUFFER_BYTES))
        previous.close()
