# SPDX-License-Identifier: GPL-2.0-or-later
"""Pinned Z9 synthetic QUAL/command-dial MCU states, no settings RAM edits.

Original name table: SW1 QUALITY=80000000. Original decoder byte1f,
signed main dial byte0b. Native UI interpretation is audited separately.
"""
import struct


def body(pressed=False, dial=0):
    if not isinstance(pressed,bool) or not -128<=dial<=127:
        raise ValueError('boolean QUAL and signed one-byte dial required')
    data=bytearray(124);data[0]=data[4]=1
    data[0x1f]=int(pressed);data[0xb]=dial&255
    return bytes(data)


def expected(pressed=False,dial=0):
    return struct.pack('<11I',0x200,0x80000000 if pressed else 0,0,0,dial&0xffffffff,0,0,0,0,0,0)


def states(steps):
    if not isinstance(steps,int) or not 1<=abs(steps)<=12:raise ValueError('1..12 signed dial steps required')
    values=[('quality-released',False,0),('quality-pressed',True,0)]
    values += [('quality-dial-'+str(i+1),True,1 if steps>0 else -1) for i in range(abs(steps))]
    values += [('quality-released-after-dial',False,0)]
    return [dict(label=label,body_hex=body(pressed,dial).hex(),expected_hex=expected(pressed,dial).hex()) for label,pressed,dial in values]
