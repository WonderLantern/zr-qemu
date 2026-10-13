# SPDX-License-Identifier: GPL-2.0-or-later
import time

def settle(g,seconds):
    g.qmp.command('cont')
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if not g.qmp.command('query-status')['running']:
            early=getattr(g,'early_shutdown_observer',None)
            if 'Z9_UNKNOWN' in g.log() or not early or not early.handle():
                break
            g.qmp.command('cont')
        time.sleep(.05)
    g.qmp.command('stop')
