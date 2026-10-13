# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only bounded Z9 scheduler/task candidates after ordinary boot.

The 0x78 stride and base pointer come from native 401895e8 task-ID arithmetic.
The scan is bounded, not a claim that every slot belongs to a live task.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import time

from probe_graphics_image import save


def ram(a,n):
    return 0xa00000000 <= a and 0 < n <= 0xa20000000-a


def capture(g,label='tasks',*,bindings=None):
    source=Path(__file__).read_bytes()
    (g.out/(label+'-observer-source.py')).write_bytes(source)
    # Explicit sample bindings; defaults preserve the established Z9 probe.
    binding=bindings or dict(globals=0xa04c51600,task_pointer=0xa04c516e0,
        code_end=0x41600020,thread_wrapper=0x40d315fc,resume_pc=0x401898b4)
    if bindings is not None and binding['globals'] == 0xa057e2200:
        from zr_sequence_resources import capture as capture_resources
        capture_resources(g, label)
    save(g,label+'-globals',binding['globals'],0x200)
    pointer=struct.unpack('<Q',g.read_bytes(binding['task_pointer'],8))[0]
    if not ram(pointer,512*0x78):
        raise ValueError('task array pointer outside modeled RAM')
    array=save(g,label+'-array',pointer,512*0x78)
    candidates=[]
    rejected=[]
    for index in range(512):
        raw=array[index*0x78:(index+1)*0x78]
        desc,sp,pc=(struct.unpack_from('<Q',raw,x)[0] for x in (0x10,0x28,0x30))
        if not ram(desc,0x40) or not ram(sp,0x100) or not 0x40160000 <= pc < binding['code_end']:
            continue
        info=save(g,f'{label}-{index+1:03d}-descriptor',desc,0x40)
        stack_size,stack_base=struct.unpack_from('<QQ',info,0x20)
        if not (ram(stack_base,stack_size) and stack_base <= sp < stack_base+stack_size):
            # This is a bounded candidate scan, not proof that every retained
            # slot is a live task. Preserve the mismatch without discarding
            # all later task evidence or presenting it as a valid unwind.
            rejected.append(dict(slot=index+1,descriptor=hex(desc),stack=hex(sp),
                stack_base=hex(stack_base),stack_size=stack_size,
                reason='saved task SP is outside original stack descriptor'))
            continue
        stack=save(g,f'{label}-{index+1:03d}-stack',sp,min(0x2000,stack_base+stack_size-sp))
        words=[struct.unpack_from('<Q',stack,o)[0] for o in range(0,len(stack)-7,8)]
        returns=[dict(offset=hex(i*8),pc=hex(v)) for i,v in enumerate(words) if 0x40160000<=v<binding['code_end'] and not v%4]
        candidate=dict(slot=index+1,tcb=hex(pointer+index*0x78),descriptor=hex(desc),
                               stack=hex(sp),resume=hex(pc),raw_tcb_hex=raw.hex(),
                               descriptor_hex=info.hex(),stack_code_candidates=returns)
        argument,entry=struct.unpack_from('<QQ',info,8)
        candidate['entry']=hex(entry)
        if entry==binding['thread_wrapper'] and ram(argument,0x38):
            wrapper=save(g,f'{label}-{index+1:03d}-wrapper',argument,0x38)
            candidate.update(wrapper=hex(argument),wrapper_hex=wrapper.hex(),
                             worker=hex(struct.unpack_from('<Q',wrapper,8)[0]),
                             argument=hex(struct.unpack_from('<Q',wrapper,0x28)[0]))
        if pc==binding['resume_pc'] and len(stack)>=0x270:
            candidate['saved_registers']={'X'+str(19+i):hex(struct.unpack_from('<Q',stack,0x210+8*i)[0]) for i in range(12)}
        candidates.append(candidate)
    g.data[label]=dict(pointer=hex(pointer),stride=0x78,scanned_slots=512,candidates=candidates,
                       rejected_candidates=rejected,all_candidate_stacks_valid=not rejected,
                       observer_source_sha256=hashlib.sha256(source).hexdigest(),
                       bindings={k:hex(v) for k,v in binding.items()},
                       caveat='Filtered raw TCB candidates; stack code words are not a validated unwind')
    g.data[label+'-registers']=[g.qmp.hmp('info registers',cpu) for cpu in range(4)]
    g.data[label+'-runtime-clock']=json.loads(g.qmp.command(
        'qom-get',path='/machine',property='runtime-clock-state'))
    # RSP memory reads use the selected CPU's actual debug translation.
    # A static ROM offset alone cannot establish the instruction at a
    # secondary CPU's virtual PC. Selecting a debug thread changes no
    # guest register or scheduler state.
    code=[]
    try:
        for cpu,text in enumerate(g.data[label+'-registers']):
            found=re.search(r'PC=([0-9a-fA-F]+)',text)
            if not found:continue
            pc=int(found.group(1),16)
            if not 0x40160040<=pc<binding['code_end']-0xc0:continue
            g.rsp('Hg'+format(cpu+1,'x'))
            value=g.rsp(f'm{pc-0x40:x},100',expect_ok=False)
            row=dict(cpu=cpu,virtual_pc=hex(pc),virtual_start=hex(pc-0x40),
                     scope='read-only actual per-CPU GDB virtual code; no register redirection')
            if value.startswith('E'):
                row['read_error']=value
            else:
                raw=bytes.fromhex(value)
                if len(raw)!=0x100:raise ValueError('Native CPU code snapshot truncated')
                name=f'{label}-cpu{cpu}-virtual-code.bin'
                (g.out/name).write_bytes(raw)
                row.update(file=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            code.append(row)
    finally:
        g.rsp('Hg1')
    g.data[label+'-cpu-virtual-code']=code
    g.data[label+'-graphics']=json.loads(g.qmp.command('qom-get',path='/machine',property='graphics-state'))
    if bindings is None:
        g.data[label+'-timing-devices']={name:json.loads(g.qmp.command(
            'qom-get',path='/machine',property=name)) for name in (
            'multi-io-counter-state','event1508-channel-state',
            'event1508-global0-state','event1508-global1-state',
            'event1508-aux0-state','primary-parameter-control-state')}
        g.data[label+'-capture-words']={hex(address):g.read_bytes(address,size).hex()
            for address,size in ((0xa03d98524,4),(0xa03d98d54,8),
                (0xa03d98950,4),(0xa03d99300,0x40),(0xa03d91fbc,8))}
    print(json.dumps(dict(label=label,base=hex(pointer),candidate_count=len(candidates))),flush=True)


def settle(g,seconds):
    g.qmp.command('cont')
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if not g.qmp.command('query-status')['running']:
            early=getattr(g,'early_shutdown_observer',None)
            if 'Z9_UNKNOWN' in g.log() or not early or not early.handle():
                break
            g.qmp.command('cont')
        time.sleep(.05)
    g.qmp.command('stop')


def main():
    # Keep the read-only capture helper importable by the standalone runner.
    # Its probe module deliberately does not expose private boot constants.
    from contract_guest import ContractGuest
    from probe import sha
    from probe_graphics_image import FIXTURES
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--name',required=True)
    ap.add_argument('--seconds',type=float,default=20)
    args=ap.parse_args()
    if not 0<args.seconds<=60:
        ap.error('seconds must be in (0,60]')
    g=ContractGuest(args.name,FIXTURES+',graphics-image-model=on,adc-fixture=on,adc-input=256:512:768:1023',intercept_irq=False)
    g.command[g.command.index('-smp')+1]='4'
    with g:
        g.data.update(source_sha256=sha(Path(__file__)),classification='system_emulated_read_only_snapshot',
                      diagnostic=__doc__,cpu_register_redirection=False,ram_patches=[])
        g.rsp('z1,40160000,4')
        settle(g,args.seconds)
        capture(g)
        g.check('bounded boot has no unknown MMIO','Z9_UNKNOWN' not in g.log())


if __name__=='__main__':
    main()
