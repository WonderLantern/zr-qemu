# SPDX-License-Identifier: GPL-2.0-or-later
"""Deterministic external RTC status sample, pinned to the Z9 family7 parser.

This is an opt-in functional input, not a measured physical MCU protocol.
ZR binding and clock-set/periodic behavior require separate verification.
"""
from datetime import datetime


def status_body(timestamp, *, reset_flag=0, auxiliary_status=0):
    if not isinstance(timestamp, datetime) or not 2000 <= timestamp.year <= 2255:
        raise ValueError('RTC year must fit the observed unsigned offset from 2000')
    if reset_flag not in (0, 1) or auxiliary_status not in range(4):
        raise ValueError('bounded observed RTC status inputs required')
    body = bytearray(14)
    body[0] = 1
    body[4:10] = bytes((timestamp.year-2000, timestamp.month-1, timestamp.day-1,
                        timestamp.hour, timestamp.minute, timestamp.second))
    body[12], body[13] = reset_flag, auxiliary_status
    return bytes(body)


def diagnostic_status():
    return status_body(datetime(2026, 10, 10, 12, 34, 56))
