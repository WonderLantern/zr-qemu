# SPDX-License-Identifier: GPL-2.0-or-later
"""Scoped GDB write observation of the ZR C1.11 property 280c storage.

The asynchronous-stop transport follows the proven Z9 read-watch helper.
The address and write access are ZR-specific; no Z9 default is inherited.
Removing the observation for one original instruction writes no guest state.
"""
import re

ADDRESS = 0xa03fea6d0


def query_stop(g):
    current = g.rsp('qC', expect_ok=False)
    packets = list(g.rsp_stop_packets)
    g.rsp_stop_packets.clear()
    reply = packets[-1] if packets else ''
    fields = reply[3:] if reply.startswith('T') else ''
    match = re.search(r'(?:^|;)watch:([0-9a-f]+);', fields)
    thread = re.search(r'(?:^|;)thread:([0-9a-fp.]+);', fields)
    tid = thread.group(1) if thread else None
    return dict(current=current, reply=reply, packets=packets,
        write_address=hex(int(match.group(1), 16)) if match else None,
        thread=tid, cpu=int(tid.split('.')[-1], 16)-1 if tid else None)


def enable(g, address=ADDRESS):
    if address not in (ADDRESS, 0xa03fea274):
        raise ValueError('only the two pinned ZR C1.11 mode descriptor words are supported')
    if not hasattr(g, 'mode_watch_original_command'):
        if getattr(g, 'rsp_stop_packets', []):
            raise ValueError('unconsumed asynchronous stops before write observation')
        g.rsp_stop_packets = []
        g.mode_watch_original_command = g.qmp.command

        def command(name, **args):
            if name != 'cont':
                return g.mode_watch_original_command(name, **args)
            if args:
                raise ValueError('unexpected continuation arguments')
            g.rsp('qC', expect_ok=False)
            body = getattr(g, 'mode_watch_next_resume', 'c').encode()
            if hasattr(g, 'mode_watch_next_resume'):
                del g.mode_watch_next_resume
            g.gdb.sendall(b'$'+body+b'#'+f'{sum(body)&255:02x}'.encode())
            if g.gdb.recv(1) != b'+':
                raise RuntimeError('GDB continue not acknowledged')
            return {}

        g.qmp.command = command
    if hasattr(g, 'mode_watch_address') and g.mode_watch_address != address:
        raise ValueError('write observation address changed before retirement')
    g.mode_watch_address = address
    g.rsp(f'Z2,{address:x},4')


def disable(g):
    g.rsp(f'z2,{g.mode_watch_address:x},4')


def step(g, thread):
    if not isinstance(thread, str) or not re.fullmatch(r'(?:p[0-9a-f]+\.)?[0-9a-f]+', thread):
        raise ValueError('concrete GDB thread required')
    if hasattr(g, 'mode_watch_next_resume'):
        raise ValueError('unconsumed single step')
    g.mode_watch_next_resume = 'vCont;s:'+thread


def restore(g):
    g.rsp('qC', expect_ok=False)
    g.data.setdefault('mode_watch_retired_stop_packets', []).append(list(g.rsp_stop_packets))
    del g.rsp_stop_packets
    g.qmp.command = g.mode_watch_original_command
    del g.mode_watch_original_command
    del g.mode_watch_address
    if hasattr(g, 'mode_watch_next_resume'):
        del g.mode_watch_next_resume
