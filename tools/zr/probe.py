# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import json
import socket
import time
import os
from pathlib import Path
HERE=Path(__file__).resolve().parent
WORK=Path(os.environ['WL_ZR_WORK'])
MAIN=Path(os.environ['WL_ZR_FIRMWARE'])
MAIN_SHA='9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f'

class QMP:
    def __init__(self, path, *, startup_timeout=3):
        if not 3<=startup_timeout<=30:
            raise ValueError('bounded QMP startup timeout required')
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(startup_timeout)
        self.sock.connect(str(path))
        self.fp = self.sock.makefile('rwb', buffering=0)
        self.events = []
        self.command_timing = dict(commands=0, slow=[], slow_omitted=0,
                                   max_seconds=0, failed=None)
        self.transport_failed = None
        self.greeting = json.loads(self.fp.readline())
        self.command('qmp_capabilities')
        self.sock.settimeout(3)

    def command(self, name, **args):
        if self.transport_failed is not None:
            raise RuntimeError('QMP transport already failed: ' + self.transport_failed)
        previous = self.sock.gettimeout()
        # Synchronous software image/codec work can hold QEMU's main loop.
        # Pause must finish that work; this is a host deadline, not extra guest
        # recording time. Other commands retain the caller's bounded timeout.
        timeout = max(previous or 3, 30) if name == 'stop' else (previous or 3)
        begun = time.monotonic()
        deadline = begun + timeout
        self.command_timing['commands'] += 1
        try:
            self.sock.settimeout(timeout)
            self.fp.write(json.dumps({'execute': name, 'arguments': args}).encode() + b'\n')
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('QMP command deadline expired')
                self.sock.settimeout(remaining)
                line = self.fp.readline()
                if not line:
                    raise EOFError('QMP disconnected')
                item = json.loads(line)
                if 'event' in item:
                    self.events.append(item)
                elif 'error' in item:
                    raise RuntimeError(item['error'])
                elif 'return' in item:
                    return item['return']
        except (OSError, EOFError, ValueError, KeyboardInterrupt) as error:
            # A timed-out makefile cannot safely consume a late reply. Never
            # retry a command or misattribute that reply to a cleanup command.
            self.transport_failed = f'{name}: {error!r}'
            self.command_timing['failed'] = dict(command=name, error=repr(error),
                                                deadline_seconds=timeout)
            raise
        finally:
            elapsed = time.monotonic() - begun
            self.command_timing['max_seconds'] = max(self.command_timing['max_seconds'], elapsed)
            if elapsed >= 3:
                if len(self.command_timing['slow']) < 128:
                    self.command_timing['slow'].append(dict(command=name, seconds=elapsed))
                else:
                    self.command_timing['slow_omitted'] += 1
            self.sock.settimeout(previous)

    def hmp(self, command, cpu=0):
        return self.command('human-monitor-command', **{'command-line': command, 'cpu-index': cpu})

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def rsp_command(sock, command):
    body = command.encode()
    sock.sendall(b'$' + body + b'#' + f'{sum(body) & 255:02x}'.encode())
    while True:
        byte = sock.recv(1)
        if not byte:
            raise EOFError('GDB disconnected before packet')
        if byte == b'$':
            break
    reply = bytearray()
    while True:
        byte = sock.recv(1)
        if not byte:
            raise EOFError('GDB disconnected')
        if byte == b'#':
            break
        reply += byte
    checksum = b''
    while len(checksum) < 2:
        byte = sock.recv(2 - len(checksum))
        if not byte:
            raise EOFError('GDB disconnected during checksum')
        checksum += byte
    if checksum != f'{sum(reply) & 255:02x}'.encode() or reply != b'OK':
        raise RuntimeError(f'GDB command rejected: {reply!r}, checksum {checksum!r}')
    sock.sendall(b'+')

def rsp_breakpoint(path, address):
    """Install one hardware breakpoint; execution control stays on QMP."""
    sock = socket.socket(socket.AF_UNIX)
    sock.settimeout(3)
    sock.connect(str(path))
    rsp_command(sock, f'Z1,{address:x},4')
    return sock
