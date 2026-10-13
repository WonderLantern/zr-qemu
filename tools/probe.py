# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import json
import socket
MAIN_SHA = '6380ded18395ce11cb327c766721274c85127d2cf1a1e887ee60e3d156810bdd'

class QMP:
    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(3)
        self.sock.connect(str(path))
        self.fp = self.sock.makefile('rwb', buffering=0)
        self.events = []
        self.greeting = json.loads(self.fp.readline())
        self.command('qmp_capabilities')

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
