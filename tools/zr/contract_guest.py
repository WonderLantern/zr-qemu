# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded diagnostic guest for new EXPEED7 device contracts, Nikon WSL only.

CPU redirection is explicit and recorded; it is not a native boot receipt.
Does not start, attach to or terminate any guest owned by another process.
"""
import json
import os
from pathlib import Path
import socket
import shutil
import struct
import subprocess
import time
from probe import HERE, WORK, MAIN, MAIN_SHA, sha
from buffered_qemu_transport import QMP, BUFFER_BYTES


class ContractGuest:
    def __init__(self, name, properties, *, intercept_irq=True, accelerator=None, ram_mib=512,
                 machine='nikon-z9-lab', firmware=MAIN, firmware_sha=MAIN_SHA,
                 runtime_log=False, build_work=None, board_source=None):
        if ram_mib not in (512, 1024):
            raise ValueError('supported work RAM sizes: 512 or 1024 MiB')
        self.ram_mib = ram_mib
        if accelerator not in (None, 'qtest'):
            raise ValueError('unsupported diagnostic accelerator')
        self.accelerator = accelerator
        if (os.name=='nt' or os.environ.get('WSL_DISTRO_NAME')=='ubuntu-noble'):
            raise RuntimeError('only ubuntu-noble-nikon is authorized')
        firmware = Path(firmware)
        if machine not in ('nikon-z9-lab', 'nikon-zr-lab'):
            raise ValueError('explicit EXPEED7 lab machine required')
        if not name.replace('-', '').replace('_', '').isalnum() or sha(firmware) != firmware_sha:
            raise ValueError('invalid slug or firmware fingerprint')
        work = Path(build_work) if build_work is not None else WORK
        board_source = Path(board_source) if board_source is not None else HERE/'qemu/nikon-z9-lab.c'
        self.out, self.runtime = Path(os.environ['WL_ZR_OUTPUT']).resolve(), work/'runs'/name
        self.out.mkdir(parents=True, exist_ok=False)
        self.runtime.mkdir(parents=True, exist_ok=False)
        self.log_path=(self.runtime if runtime_log else self.out)/'stderr.log'
        self.qtest_log_path=(self.runtime if runtime_log else self.out)/'qtest.log'
        exe = work/'build/qemu-system-aarch64'
        self.command = [str(exe), '-M', machine+properties,
                        '-kernel', str(firmware), '-smp', '1', '-display', 'none',
                        '-serial', 'none', '-monitor', 'none', '-S', '-no-reboot',
                        '-qmp', f'unix:{self.runtime}/qmp.sock,server=on,wait=off',
                        '-gdb', f'unix:{self.runtime}/gdb.sock,server=on,wait=off',
                        '-qtest', f'unix:{self.runtime}/qtest.sock,server=on,wait=off',
                        '-qtest-log', str(self.qtest_log_path)]
        if accelerator == 'qtest':
            # QTest dummy CPUs execute no instructions. Its clock advances
            # only through explicit clock_step/clock_set protocol requests.
            self.command.remove('-S')
            index = self.command.index('-gdb')
            del self.command[index:index+2]
            self.command += ['-accel', 'qtest']
        if ram_mib != 512:
            self.command += ['-m', str(ram_mib)+'M']
        self.data = dict(passed=False, camera_acceptance=False, command=self.command,
                         work_ram_mib=ram_mib,
                         machine=machine, main_sha256=firmware_sha, qemu_sha256=sha(exe),
                         board_sha256=sha(board_source),
                         harness_sha256=sha(Path(__file__)), checks=[], calls=[], irq_events=[],
                         diagnostic='native external inputs; no CPU call redirection')
        transport=HERE/'buffered_qemu_transport.py'
        (self.out/transport.name).write_bytes(transport.read_bytes())
        self.data['host_transport']=dict(qmp_read_buffer_bytes=BUFFER_BYTES,qtest_read_buffer_bytes=BUFFER_BYTES,
            source_sha256=sha(transport),scope='Flushed commands and buffered reply reads; same protocol, virtual time and guest inputs')
        self.data['board_includes']={}
        for filename in ('nikon-raw-pixels.h','nikon-z9-pixels.h'):
            source=work/'qemu-10.2.4/hw/arm'/filename
            if source.is_file():
                archived=self.out/filename
                archived.write_bytes(source.read_bytes())
                self.data['board_includes'][filename]=sha(archived)
        if accelerator == 'qtest':
            self.data['diagnostic'] = 'qtest MMIO and virtual clock; no guest instructions executed'
        self.proc = self.qmp = self.qt = self.fp = self.gdb = None
        self.irq = {}
        self.intercept_irq = intercept_irq
        self.data['irq_interception'] = intercept_irq

    def __enter__(self):
        try:
            with self.log_path.open('wb') as log:
                self.proc = subprocess.Popen(self.command, stdout=subprocess.DEVNULL, stderr=log)
            deadline = time.monotonic()+10
            while not (self.runtime/'qtest.sock').exists():
                if self.proc.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('QEMU startup failed')
                time.sleep(.02)
            # Listening sockets can precede full RAW/model initialization.
            # Allow only the startup handshake extra time; ordinary commands
            # keep their existing three-second bound.
            self.qmp = QMP(self.runtime/'qmp.sock',startup_timeout=15)
            self.data['qmp_command_timing'] = self.qmp.command_timing
            self.data['qmp_startup_timeout_seconds']=15
            self.qt = socket.socket(socket.AF_UNIX)
            self.qt.settimeout(3)
            self.qt.connect(str(self.runtime/'qtest.sock'))
            self.fp = self.qt.makefile('rwb', buffering=BUFFER_BYTES)
            if self.accelerator != 'qtest':
                self.gdb = socket.socket(socket.AF_UNIX)
                self.gdb.settimeout(3)
                self.gdb.connect(str(self.runtime/'gdb.sock'))
            if self.intercept_irq:
                children = self.qmp.command('qom-list', path='/machine/unattached')
                gics = [x for x in children if x['type'] == 'child<arm-gicv3>']
                if len(gics) != 1:
                    raise RuntimeError('GIC object not unique')
                self.qt_command('irq_intercept_in /machine/unattached/'+gics[0]['name'])
            if self.accelerator != 'qtest':
                self.rsp('Z1,40160000,4')
            return self
        except BaseException as exc:
            self.__exit__(type(exc), exc, None)
            raise

    def qt_command(self, command):
        self.fp.write(command.encode()+b'\n')
        self.fp.flush()
        while True:
            reply = self.fp.readline().decode().strip()
            if not reply.startswith('IRQ '):
                break
            _, action, number = reply.split()
            self.irq[int(number)] = action == 'raise'
            self.data['irq_events'].append(reply)
        if not reply.startswith('OK'):
            raise RuntimeError(f'{command}: {reply}')
        return reply.split()[1:]

    def rd(self, address):
        return int(self.qt_command(f'readl {address:#x}')[0], 0)

    def wr(self, address, value):
        self.qt_command(f'writel {address:#x} {value:#x}')

    def write_bytes(self, address, value):
        self.qt_command(f'write {address:#x} {len(value):#x} 0x{value.hex()}')

    def read_bytes(self, address, size):
        return bytes.fromhex(self.qt_command(f'read {address:#x} {size:#x}')[0][2:])

    def log(self):
        return self.log_path.read_text()

    def check(self, name, condition):
        self.data['checks'].append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise AssertionError(name)

    def rsp(self, command, *, expect_ok=True, accept_stop=False):
        body = command.encode()
        self.gdb.sendall(b'$'+body+b'#'+f'{sum(body)&255:02x}'.encode())
        while True:
            char = self.gdb.recv(1)
            while char != b'$':
                if not char:
                    raise EOFError('GDB disconnected')
                char = self.gdb.recv(1)
            reply = bytearray()
            while True:
                char = self.gdb.recv(1)
                if char == b'#':
                    break
                if not char:
                    raise EOFError('GDB disconnected in packet')
                reply += char
            checksum = b''
            while len(checksum) < 2:
                char = self.gdb.recv(2-len(checksum))
                if not char:
                    raise EOFError('GDB disconnected at checksum')
                checksum += char
            if checksum != f'{sum(reply)&255:02x}'.encode():
                raise RuntimeError('bad GDB checksum')
            self.gdb.sendall(b'+')
            if reply.startswith((b'T', b'S')) and not accept_stop:
                if hasattr(self, 'rsp_stop_packets'):
                    self.rsp_stop_packets.append(reply.decode('ascii'))
                continue
            if expect_ok and reply != b'OK':
                raise RuntimeError(f'{command}: {reply!r}')
            return None if expect_ok else reply.decode('ascii')


    def __exit__(self, kind, error, traceback):
        if error:
            self.data['error'] = repr(error)
            if self.qmp and self.proc and self.proc.poll() is None and getattr(self,'failure_properties',None):
                try:
                    self.qmp.command('stop')
                    self.data['failure_device_states']={name:json.loads(self.qmp.command(
                        'qom-get',path='/machine',property=name)) for name in self.failure_properties}
                    raw_state=self.data['failure_device_states'].get('raw-pipeline-state',{})
                    if raw_state.get('frames',0):
                        for ch,plane in enumerate(raw_state['outputs']):
                            n=plane['stride']*plane['height']
                            for label,amount in [('y',n),('uv',n//(2 if plane['format']=='NV12' else 1))]:
                                if not 0 < amount <= 16*1024*1024:raise ValueError('pixel capture bounds')
                                file=self.out/f'pipeline{ch}-{label}.bin'
                                reply=self.qmp.hmp(f'pmemsave {plane[label]:#x} {amount:#x} "{file}"')
                                if reply:raise RuntimeError(reply)
                        self.qmp.command('screendump',filename=str(self.out/'pipeline-lcd.ppm'))
                except Exception as capture_error:
                    self.data['failure_device_capture_error']=repr(capture_error)
        if self.proc and self.proc.poll() is None:
            try:
                if self.qmp:
                    self.qmp.command('quit')
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait()
        self.data['owned_qemu_stopped'] = self.proc is None or self.proc.poll() is not None
        self.data['owned_qemu_pid'] = self.proc.pid if self.proc else None
        self.data['owned_qemu_exit_status'] = self.proc.poll() if self.proc else None
        archive_errors = []
        result_path = self.out/'result.json'
        try:
            for source, destination in ((self.log_path, self.out/'stderr.log'),
                                        (self.qtest_log_path, self.out/'qtest.log')):
                if source == destination or not source.exists():
                    continue
                try:
                    # Runtime logs can be large. Preserve every byte without
                    # allocating a second complete log in guest-host memory.
                    shutil.copyfile(source, destination)
                except OSError as archive_error:
                    archive_errors.append(dict(source=str(source), destination=str(destination),
                                               error=repr(archive_error)))
            if archive_errors:
                self.data['artifact_archive_errors'] = archive_errors
                if not self.data.get('error'):
                    self.data['error'] = 'Host evidence archival failed; runtime originals retained'
            self.data['passed'] = error is None and not archive_errors and bool(self.data['checks']) and all(
                check['passed'] for check in self.data['checks'])
            pending = result_path.with_suffix('.json.tmp')
            try:
                pending.write_text(json.dumps(self.data, indent=2)+'\n')
                pending.replace(result_path)
            except OSError as result_error:
                self.data['passed'] = False
                self.data['result_storage_error'] = repr(result_error)
                if not self.data.get('error'):
                    self.data['error'] = 'Host result storage failed; complete acceptance unavailable'
                # This is an explicitly failed recovery receipt, not a second
                # passing result. The owned runtime directory already exists.
                result_path = self.runtime/'result-host-storage-failure.json'
                result_path.write_text(json.dumps(self.data, indent=2)+'\n')
                print(json.dumps(dict(host_storage_recovery_result=str(result_path), passed=False)), flush=True)
        finally:
            for obj in (self.fp, self.qt, self.gdb):
                if obj:
                    obj.close()
            if self.qmp:
                self.qmp.fp.close()
                self.qmp.sock.close()
        print(json.dumps(dict(passed=self.data['passed'], checks=len(self.data['checks']),
                              out=str(self.out))))
