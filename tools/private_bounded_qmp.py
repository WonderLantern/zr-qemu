# SPDX-License-Identifier: GPL-2.0-or-later
"""Private control transport: bounded I/O, no firmware or device changes."""
import json
import socket

class QMP:
    def __init__(self,path):
        self.sock=socket.socket(socket.AF_UNIX)
        self.sock.settimeout(15)
        self.sock.connect(str(path))
        self.fp=self.sock.makefile('rwb',buffering=0)
        self.events=[]
        self.broken=False
        self.greeting=json.loads(self.fp.readline())
        self.command('qmp_capabilities')
        self.sock.settimeout(3)

    def command(self,name,**args):
        if self.broken:
            raise ConnectionError('QMP stream failed; reconnect or stop owned process')
        timeout=15 if name in ('screendump','qmp_capabilities') else 3
        if name=='human-monitor-command' and args.get('command-line','').startswith('pmemsave '):
            timeout=30
        self.sock.settimeout(timeout)
        try:
            self.fp.write(json.dumps({'execute':name,'arguments':args}).encode()+b'\n')
            while True:
                line=self.fp.readline()
                if not line:raise EOFError('QMP disconnected')
                item=json.loads(line)
                if 'event' in item:self.events.append(item)
                elif 'error' in item:raise RuntimeError(item['error'])
                elif 'return' in item:return item['return']
        except (OSError,EOFError,json.JSONDecodeError):
            self.broken=True
            raise
        finally:self.sock.settimeout(3)

    def hmp(self,command,cpu=0):
        return self.command('human-monitor-command',**{'command-line':command,'cpu-index':cpu})
