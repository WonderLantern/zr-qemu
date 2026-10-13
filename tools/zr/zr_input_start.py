# SPDX-License-Identifier: GPL-2.0-or-later
"""Host input readiness from native MCU receipt and active LCD scanout.

This schedules external keys only. It does not establish visible image,
video mode, recording or a valid file, and never changes guest memory.
"""
from zr_key_sequence import SELECTOR_FIELDS,consumed_by_native_key


def initial_consumer_lcd_ready(rows,body_hex,scanout):
    body=bytes.fromhex(body_hex)
    if len(body)!=124 or body[0]!=1 or body[4]!=1 or any(
            value for index,value in enumerate(body) if index not in {0,4,*SELECTOR_FIELDS}):
        raise ValueError('Complete initial released selector-only MCU state required')
    if any(body[field] not in (0,1,2) for field in SELECTOR_FIELDS):
        raise ValueError('Pinned initial selector enum values required')
    initial=dict(sequence_id=0,body_hex=body_hex,switches=[0x200,0,0],dials=[0,0,0,0])
    consumed=consumed_by_native_key([initial],0,rows,after_call=0)
    if not consumed:return None
    if (scanout.get('enabled') is not True or scanout.get('active') is not True or
            type(scanout.get('frames')) is not int or scanout['frames']<1 or
            scanout.get('width')!=1280 or scanout.get('height')!=800):
        return None
    return dict(classification='host initial native-input/LCD observation gate',
        kind='initial-consumer-lcd',native_initial_consumption=consumed,
        lcd_frames=scanout['frames'],lcd_width=1280,lcd_height=800,
        guest_state_modified=False,visible_image_verified=False,
        scope='Complete external MCU state consumed and returned, active scanout; UI/image/REC/file acceptance remains separate')
