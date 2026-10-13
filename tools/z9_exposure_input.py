# SPDX-License-Identifier: GPL-2.0-or-later
"""External MODE/main-dial inputs for the fingerprinted Z9 C5.32 decoder.

Original decoder: MODE byte0e -> SW0 bit11; signed dial byte0b -> word4.
Only input delivery is specified here. Read the native LCD to verify exposure.
"""
import struct


def state(label, mode=False, dial=0, hold_ns=500_000_000):
    if type(mode) is not bool or type(dial) is not int or not -64 <= dial <= 64:
        raise ValueError('boolean MODE and bounded signed dial required')
    body = bytearray(124)
    body[0] = body[4] = 1
    body[0x0e] = int(mode)
    body[0x0b] = dial & 255
    expected = struct.pack('<11I', 0x200 | (0x800 if mode else 0),
                           0, 0, 0, dial & 0xffffffff, 0, 0, 0, 0, 0, 0)
    return dict(label=label, body_hex=body.hex(), expected_hex=expected.hex(),
                hold_ns=hold_ns, workflow_phase='native-exposure-selection')


def states(mode_steps=0, shutter_steps=0):
    if type(mode_steps) is not int or not -3 <= mode_steps <= 3:
        raise ValueError('bounded mode steps required')
    if type(shutter_steps) is not int or not -64 <= shutter_steps <= 64:
        raise ValueError('bounded shutter steps required')
    rows = []
    if mode_steps:
        rows += [state('exposure-mode-press', True),
                 state('exposure-mode-dial', True, mode_steps),
                 state('exposure-mode-release', hold_ns=2_000_000_000)]
    if shutter_steps:
        rows += [state('exposure-shutter-dial', dial=shutter_steps),
                 state('exposure-shutter-release', hold_ns=2_000_000_000)]
    return rows
