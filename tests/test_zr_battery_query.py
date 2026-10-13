# SPDX-License-Identifier: GPL-2.0-or-later
"""Reject malformed status requests and prevent unintended control replies."""
import sys
from pathlib import Path
import struct
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/zr'))
from zr_battery_query_peer import reply_for

def request():
    wire = bytearray(256)
    wire[:8] = bytes((4, 2, 8, 0, 0, 0, 0, 0))
    wire[8:16] = struct.pack('<II', 2, 1)
    wire[252:255] = bytes((1, 1, 0))
    wire[255] = (255 - sum(wire)) & 255
    return bytes(wire)

class StatusPeerTests(unittest.TestCase):
    def test_declared_status_variants(self):
        for variant in (0, 1):
            with self.subTest(variant=variant):
                body = bytearray(112); body[0] = 3; body[4] = variant
                payload, frame = reply_for(request(), bytes(body))
                self.assertEqual(payload, bytes(body))
                self.assertEqual(sum(frame) & 255, 255)

    def test_every_request_byte_is_checked(self):
        status = bytes((3,)) + bytes(111)
        for offset in range(256):
            with self.subTest(offset=offset):
                wire = bytearray(request()); wire[offset] ^= 1
                if offset != 255:
                    wire[255] = (255 - sum(wire[:255])) & 255
                self.assertIsNone(reply_for(bytes(wire), status))
        for wire in (b'', request()[:-1], request() + b'\0', bytearray(request())):
            self.assertIsNone(reply_for(wire, status))

    def test_status_bytes_are_not_invented(self):
        for offset in range(112):
            body = bytearray(112); body[0] = 3; body[offset] = 2
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                reply_for(request(), bytes(body))
        for body in (b'', bytes(113), bytearray(112)):
            with self.assertRaises(ValueError):
                reply_for(request(), body)
