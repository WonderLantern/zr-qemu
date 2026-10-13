# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import json
import socket
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
        self.greeting = json.loads(self.fp.readline())
        self.command('qmp_capabilities')
        self.sock.settimeout(3)

    def command(self, name, **args):
        self.fp.write(json.dumps({'execute': name, 'arguments': args}).encode() + b'\n')
        while True:
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
