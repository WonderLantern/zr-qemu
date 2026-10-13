# SPDX-License-Identifier: GPL-2.0-or-later
"""Execute authored AArch64 WFE/SEV/IRQ tests without Nikon firmware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time

from guest import Guest
from guest_transport import Transport


def program():
    words=[];labels={};fixups=[]
    def label(s):labels[s]=len(words)
    def emit(w):words.append(w)
    def branch(base,target,kind):
        fixups.append((len(words),base,target,kind));emit(0)
    emit(0xd53800a0)  # mrs x0, mpidr_el1
    emit(0xd3400400)  # ubfx x0, x0, #0, #2
    emit(0xd2820001)  # movz x1, #0x1000
    emit(0xf2c00141)  # movk x1, #0xa, lsl #32
    branch(0xb5000000,'gate','cond')
    label('primary');emit(0xb9400022)  # ldr w2, [x1]
    branch(0x34000002,'primary','cond')
    emit(0xb900003f);emit(0xd503209f)  # str wzr, [x1]; sev
    branch(0x14000000,'primary','b')
    label('gate');emit(0xb9400c23)  # ldr w3, [x1, #12]
    branch(0x35000003,'gate','cond')
    emit(0xb9400822)  # ldr w2, [x1, #8]
    branch(0x34000002,'kind','cond')
    emit(0xb900083f);emit(0xd50320bf)  # str wzr, [x1, #8]; sevl
    label('kind');emit(0xb9401022)  # ldr w2, [x1, #16]
    branch(0x34000002,'wait','cond')
    emit(0xd503207f)  # wfi
    branch(0x14000000,'count','b')
    label('wait');emit(0xd503205f)  # wfe
    label('count');emit(0xb9400422);emit(0x11000442);emit(0xb9000422)
    branch(0x14000000,'gate','b')
    for index,base,target,kind in fixups:
        delta=labels[target]-index
        words[index]=base|((delta&0x3ffffff) if kind=='b' else (delta&0x7ffff)<<5)
    return struct.pack('<'+'I'*len(words),*words)


class SyntheticGuest(Transport):
    def __init__(self,binary,out):
        if os.name=='nt' or os.environ.get('WSL_DISTRO_NAME')=='ubuntu-noble':
            raise ValueError('Use Linux or the explicitly selected Nikon distribution')
        binary=Path(binary).resolve()
        self.out=Path(out).resolve()
        self.out.mkdir(parents=True,exist_ok=False)
        self.temp=tempfile.TemporaryDirectory(prefix='wl-wfe-unit-')
        self.runtime=Path(self.temp.name)
        self.log_path=self.out/'stderr.log';self.qtest_log_path=Path('/dev/null')
        self.accelerator=None;self.intercept_irq=False
        self.proc=self.qmp=self.qt=self.fp=self.gdb=None;self.irq={}
        code=program();kernel=self.out/'authored-wfe-test.bin';kernel.write_bytes(code)
        self.command=[str(binary),'-M','nikon-z9-lab,bootstrap-fixtures=on,low-service-ram-model=on,service-core-event-model=on',
            '-kernel',str(kernel),'-smp','4','-m','1024M','-display','none','-serial','none',
            '-monitor','none','-S','-accel','tcg,thread=single','-icount','shift=4,sleep=on',
            '-qmp',f'unix:{self.runtime}/qmp.sock,server=on,wait=off',
            '-gdb',f'unix:{self.runtime}/gdb.sock,server=on,wait=off',
            '-qtest',f'unix:{self.runtime}/qtest.sock,server=on,wait=off','-qtest-log','/dev/null']
        self.data=dict(checks=[],irq_events=[],firmware_used=False,camera_acceptance=False,
            classification='authored_AArch64_execution_test',command=self.command,
            qemu_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            kernel_sha256=hashlib.sha256(code).hexdigest())
    __exit__=Guest.__exit__


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--warm-reset',action='store_true',help='separate board-reset coverage; currently unsupported')
    args=parser.parse_args()
    with SyntheticGuest(args.qemu,args.output) as g:
        base=0xa00001000
        def state():return json.loads(g.qmp.command('qom-get',path='/machine',property='runtime-clock-state'))
        def core():return state()['cpus'][3]
        def count():return g.rd(base+4)
        def wait(condition):
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if condition():return
                time.sleep(.005)
            raise TimeoutError('Synthetic condition did not arrive; '+json.dumps(state()))
        def send():
            g.wr(base,1);wait(lambda:g.rd(base)==0)
        g.check('cold CPU starts with empty event state',not core()['event_pending'] and
            not core()['event_waiting'] and core()['event_sleeps']==core()['event_wakes']==0)
        g.wr(base+12,1)
        g.qt_command('writeq 0x0821ffe8 0x40160000')
        g.wr(0x0d154244,8)
        g.rsp('z1,40160000,4')
        g.qmp.command('cont')
        send();wait(lambda:core()['event_pending'])
        g.check('SEV before WFE is retained while receiver is running',count()==0 and not core()['event_waiting'])
        send();wait(lambda:core()['event_pending'])
        g.wr(base+12,0)
        wait(lambda:count()==1 and core()['halted'])
        g.check('multiple pre-wait events coalesce into one consumption',count()==1 and not core()['event_pending'])
        time.sleep(.05)
        g.check('WFE without a new event remains halted',count()==1 and core()['event_waiting'])
        send();wait(lambda:count()==2 and core()['halted'])
        g.check('SEV resumes a blocked WFE exactly once',count()==2 and not core()['event_pending'])
        g.wr(base+8,1)
        send();wait(lambda:count()==4 and core()['halted'])
        g.check('SEVL consumes the next WFE without blocking',count()==4)
        for expected in (5,6,7):
            send();wait(lambda:count()==expected and core()['halted'])
            g.check('repeated wake '+str(expected),count()==expected and core()['event_waiting'])
        g.qt_command('set_irq_in /machine/cpu3 unnamed-gpio-in 0 1')
        wait(lambda:count()>7)
        g.qt_command('set_irq_in /machine/cpu3 unnamed-gpio-in 0 0')
        wait(lambda:core()['halted'] and core()['event_waiting'])
        before_wfi=count()
        g.check('ordinary IRQ wakes an already blocked WFE',before_wfi>7)
        g.wr(base+16,1)
        send();wait(lambda:count()==before_wfi+1 and core()['halted'] and not core()['event_waiting'])
        send();wait(lambda:core()['event_pending'])
        time.sleep(.05)
        g.check('SEV does not wake WFI',count()==before_wfi+1 and core()['halted'] and not core()['event_waiting'])
        g.wr(base+16,0)
        g.qt_command('set_irq_in /machine/cpu3 unnamed-gpio-in 0 1')
        wait(lambda:count()>before_wfi+1)
        g.qt_command('set_irq_in /machine/cpu3 unnamed-gpio-in 0 0')
        wait(lambda:core()['halted'] and core()['event_waiting'])
        g.check('ordinary IRQ wakes WFI and later WFE can sleep',count()>before_wfi+1)
        g.data['final_clock']=state()
        g.qmp.command('stop')
        g.check('no unknown MMIO in authored program','Z9_UNKNOWN' not in g.log_path.read_text())
        g.data['warm_reset_tested']=args.warm_reset
        if args.warm_reset:
            g.qmp.command('system_reset')
            wait(lambda:core()['event_sleeps']==0)
            g.check('CPU reset clears retained event and wait state',
                not core()['event_pending'] and not core()['event_waiting'] and core()['event_wakes']==0)
        g.data['passed']=True
        print(json.dumps(dict(passed=True,checks=len(g.data['checks']),core3=core())),flush=True)


if __name__=='__main__':main()
