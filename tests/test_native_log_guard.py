# SPDX-License-Identifier: GPL-2.0-or-later
"""Fault-marker integrity across actual append/read boundaries and I/O failures."""
import errno
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from native_log_guard import NativeLogGuard

class LogGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'qemu-stderr.log';self.path.write_bytes(b'')
        self.guard=NativeLogGuard(self.path);self.addCleanup(self.guard.close)

    def append(self,data):
        with self.path.open('ab') as stream:stream.write(data)

    def test_split_marker_across_appends(self):
        self.append(b'ordinary Z9_UNKN');self.assertFalse(self.guard.poll())
        self.append(b'OWN cpu=0\n');self.assertTrue(self.guard.poll())
        self.assertTrue(self.guard.poll())

    def test_marker_across_bounded_chunks(self):
        self.append(b'.'*(65536-5)+b'Z9_UNKNOWN cpu=0')
        self.assertTrue(self.guard.poll())

    def test_failed_read_cannot_skip_consumed_fault_bytes(self):
        self.append(b'prefix Z9_UNKN');self.assertFalse(self.guard.poll())
        self.append(b'OWN cpu=0\n')
        original=self.guard.reader
        class PartialFailure:
            def seek(self,offset):return original.seek(offset)
            def read(self,size):
                original.read(size)
                raise OSError(61,'No data available')
            def close(self):original.close()
        self.guard.reader=PartialFailure()
        self.assertTrue(self.guard.poll());self.assertEqual(self.guard.transient_retries,1)
        self.assertEqual(self.guard.bytes_scanned,self.path.stat().st_size)

    def test_persistent_unavailability_is_not_success(self):
        self.append(b'not yet readable')
        with patch.object(Path,'open',side_effect=OSError(61,'No data available')):
            with patch('native_log_guard.time.monotonic',side_effect=[0,2]):
                with self.assertRaises(OSError):self.guard.poll()
        self.assertEqual(self.guard.position,0)

    def test_unrelated_errors_are_not_suppressed(self):
        self.append(b'not accessible')
        with patch.object(Path,'open',side_effect=OSError(errno.EACCES,'permission denied')):
            with self.assertRaises(PermissionError):self.guard.poll()
        self.assertEqual(self.guard.transient_retries,0)

    def test_close_and_resume_preserve_cursor(self):
        self.append(b'safe prefix');self.assertFalse(self.guard.poll());self.guard.close()
        self.append(b'Z9_UNKNOWN');self.assertTrue(self.guard.poll())
        self.assertEqual(self.guard.bytes_scanned,self.path.stat().st_size)

    def test_poll_reads_a_finite_append_snapshot(self):
        self.append(b'safe');self.guard.reader=self.path.open('rb',buffering=0)
        original=self.guard.reader;outer=self
        class GrowingReader:
            def seek(self,offset):return original.seek(offset)
            def read(self,size):
                chunk=original.read(size);outer.append(b'Z9_UNKNOWN');return chunk
            def close(self):original.close()
        self.guard.reader=GrowingReader()
        self.assertFalse(self.guard.poll());self.assertEqual(self.guard.position,4)
        self.assertTrue(self.guard.poll())

    def test_truncation_is_reported(self):
        self.append(b'long enough');self.assertFalse(self.guard.poll());self.path.write_bytes(b'')
        with self.assertRaises(RuntimeError):self.guard.poll()

if __name__=='__main__':unittest.main()
