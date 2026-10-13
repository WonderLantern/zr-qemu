# SPDX-License-Identifier: GPL-2.0-or-later
"""Request-bound replay of the explicit ZR family4/type3 status input.

The original C1.11 callback serializes class4/type2/count1 to the MCU. Its
type3 response is consumed by the original40ed141c status handler. This peer
supplies the same declared external status as boot, without interpreting
unknown voltage/charge fields, acknowledging control commands, or completing
any image/codec/task operation. Physical battery semantics remain unproved.
"""
import hashlib
import struct
from mcu_frames import frames


def reply_for(wire,status):
    if not isinstance(wire,bytes) or len(wire)!=256 or sum(wire)&255!=255:
        return None
    # Complete native request, including payload length, route and padding.
    if wire[:8]!=bytes((4,2,8,0,0,0,0,0)) or wire[252:255]!=bytes((1,1,0)):
        return None
    if wire[8:248]!=struct.pack('<II',2,1)+bytes(232) or wire[248:252]!=bytes(4):
        return None
    if (not isinstance(status,bytes) or len(status)!=112 or status[0]!=3 or
        status[4] not in (0,1) or any(value for index,value in enumerate(status) if index not in (0,4))):
        raise ValueError('Only the explicitly declared boot status candidate may be repeated')
    return status,frames(status,family=4)[0]


def queue_reply(peer,wire):
    status=bytes.fromhex(peer.g.data['battery_status_input_body_hex'])
    value=reply_for(wire,status)
    if value is None:return False
    body,frame=value
    peer.record.setdefault('battery_query_replies',[]).append(dict(
        tx_index=peer.tx['row']['index'],request_sha256=hashlib.sha256(wire).hexdigest(),
        reply_body_sha256=hashlib.sha256(body).hexdigest(),reply_sha256=hashlib.sha256(frame).hexdigest(),
        classification='request-bound repeated external family4 status candidate',
        physical_battery_verified=False,image_completion=False,codec_completion=False,
        firmware_patch=False,cpu_redirection=False,guest_ram_patch=False))
    peer.pending.append((4,body,frame))
    return True
