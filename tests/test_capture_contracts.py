# SPDX-License-Identifier: GPL-2.0-or-later
"""Firmware-free input, completion and storage ownership regressions."""
import json
import importlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from make_cmos import generate
from mcu_frames import frames
from ccomp_command_peer import reply_for
from capture_workflow_ready import evaluate
from virtual_recording_card import create


class CaptureContracts(unittest.TestCase):
    def test_full_capture_helpers_import_without_research_checkout(self):
        tools=Path(__file__).resolve().parents[1]/'tools'
        for path in sorted(tools.glob('capture_*.py')):
            with self.subTest(module=path.stem):
                importlib.import_module(path.stem)

    def test_14bit_samples_keep_full_range(self):
        data = generate(32, 16, bits=14)
        self.assertEqual(struct.unpack('<8s6I', data[:32]), (b'NZ9RAW1\0',32,16,14,0,0,16383))
        samples = np.frombuffer(data[32:], dtype='<u2')
        self.assertEqual(samples.max(), 16383)
        self.assertEqual(samples.min(), 0)
        with self.assertRaises(ValueError):
            generate(8, 8, bits=16)

    def test_ccomp_ack_requires_exact_complete_request(self):
        body = struct.pack('<3I', 2, 0xf3, 1) + bytes(228)
        valid = frames(body, family=9)[0]
        self.assertIsNotNone(reply_for(valid))
        for bad in (valid[:-1], valid[:20] + bytes((valid[20] ^ 1,)) + valid[21:],
                    frames(struct.pack('<3I', 2, 0xf3, 2)+bytes(228), family=9)[0],
                    frames(body, family=8)[0]):
            self.assertIsNone(reply_for(bad))

    def test_menu_gate_requires_all_image_work_and_fresh_frames(self):
        released = dict(raw=dict(frames=10), lcd=dict(video_frames=10))
        raw, lcd = dict(frames=20), dict(video_frames=20, last_frame_has_video=True)
        jpeg = dict(jobs=3, requested=False, pending=0, core=0, acks=3, core_acks=3)
        side = dict(jobs=1, pending=False, acks=1)
        streams = [dict(observation=dict(jpeg=dict(width=w,height=h)), files=[dict(label='encoded')])
                   for w,h in ((8256,5504),(1620,1080),(160,120))]
        self.assertTrue(evaluate(released,raw,lcd,jpeg,side,streams)['ready'])
        self.assertFalse(evaluate(released,raw,lcd,jpeg,side,streams[:-1])['ready'])
        self.assertFalse(evaluate(released,raw,lcd,dict(jpeg,pending=1),side,streams)['ready'])
        self.assertFalse(evaluate(released,dict(frames=10),lcd,jpeg,side,streams)['ready'])
        self.assertFalse(evaluate(released,raw,dict(lcd,last_frame_has_video=False),jpeg,side,streams)['ready'])

    def test_card_creation_never_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'capture-card.raw'
            path.write_bytes(b'existing user data')
            with self.assertRaises(FileExistsError):
                create(path, 'blank')
            self.assertEqual(path.read_bytes(), b'existing user data')


if __name__ == '__main__':
    unittest.main()
