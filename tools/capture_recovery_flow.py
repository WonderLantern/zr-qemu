# SPDX-License-Identifier: GPL-2.0-or-later
"""Whole native Z9 shutter-to-live-view workflow, with read-only transitions.

Bindings are specific to the pinned C5.32 image. No firmware, scheduler flags,
device status or pixels are changed by the observer. External key contacts
reuse the already verified Z9 MCU payloads.
"""
from pathlib import Path
import json
import struct

POINTS={
    0x40f53e50:'ccomp_command_wait_return',
    0x40f4b19c:'ccomp_completion_wait_return',
    0x4117fbf8:'ccomp_command_reply_callback',
    0x411802b0:'ccomp_gpio_request',
    0x4118046c:'ccomp_gpio_callback',
    0x40fc4f6c:'capture_control_fault_entry',
    0x40fc5480:'capture_control_fault_latch',
    0x40fd808c:'capture_control_permission_clear',
    0x40fad57c:'capture_control_block_producer',
    0x40fd6648:'capture_control_readiness_convert',
    0x40ed207c:'capture_control_error_report',
    0x40fd7bc4:'capture_control_permission_set',
    0x41162ae4:'source_prepare_first_wait',0x41162b5c:'source_prepare_aux_wait',
    0x41162bb8:'source_prepare_second_wait',
    0x41162de8:'source_first_wait',0x41162e78:'source_second_wait',
    0x41162ed4:'source_third_wait',0x41166b34:'source_stop_request',
    0x41166bfc:'source_stop_wait',0x40f5419c:'sequence_request',
    0x40f7adf0:'capture_fsm',0x40394418:'app_state',
    0x41032070:'capture_completion',0x40f4904c:'sequence_stop_callback',
    0x40c2aef4:'receiver_control_write',
    0x40c2c764:'output_group_start',0x40c2c784:'output_group_stop',
    0x41159e0c:'input_channel_zero',0x4115a060:'input_channel_one',
    0x411634bc:'source_restart_result',0x4117d138:'source_diagnostic',
    0x41162f18:'source_setup_a_result',0x41162f28:'source_setup_b_result',
    0x41162f3c:'source_setup_c_result',0x41162f4c:'source_setup_d_result',
    0x41162f5c:'source_setup_e_result',0x41162f74:'source_setup_f_result',
    0x41162f80:'source_setup_g_result',0x41162f88:'source_setup_h_result',
}

# Reuse the pinned pipeline bindings from observe_z9_sequence_sync.py. Arm
# these after the first capture source stop, so preview-frame callbacks do
# not exhaust the bounded observation budget before the recovery begins.
DEFERRED={
    0x40f5ca18:'pipeline_sequence_callback',0x40f58f00:'pipeline_stream_start_return',
    0x40f5f234:'pipeline_error_result',0x40f5f300:'pipeline_error_reason9',
    0x40f4f598:'pipeline_error_table',0x40f571d4:'pipeline_error_descriptor',
    0x40f57274:'pipeline_error_display',0x40f5c7f4:'pipeline_watchdog_expired',
    0x40f5eb78:'pipeline_wait_entry',0x40f595c4:'pipeline_boundary_gate',
    0x40f596b8:'pipeline_refresh_return',
    0x41037900:'application_stop_request',0x40f52688:'sequence_stop_request',
    0x40f60634:'pipeline_stop_request',
}
for _pc in (0x40f7adf0,0x40394418,0x41159e0c,0x4115a060,0x4117d138):
    DEFERRED[_pc]=POINTS[_pc]
POINTS.update(DEFERRED)
# Rare failure paths must be armed before full press. Deferring them until
# source_stop hid549's fault at63.474s, before the recovery stop was requested.
for _pc in (0x40f5f300,0x40f4f598,0x40f571d4,0x40f57274,0x40f5c7f4):
    DEFERRED.pop(_pc)


def recovery_states():
    from z9_navigation_input import states
    output=[]
    for action in ('half','menu','half','menu','half'):
        if action=='menu':
            rows=states(['menu'])[1:]
            for row in rows:
                row['hold_ns']=60000000 if row['label'].endswith('-press') else 2000000000
        else:
            rows=[]
            for pressed in (1,0):
                body=bytearray(124);body[0]=body[4]=1;body[7]=pressed
                rows.append(dict(label='recovery-half-'+('press' if pressed else 'release'),
                    body_hex=body.hex(),expected_hex=struct.pack('<11I',0x200|(pressed<<31),*([0]*10)).hex(),
                    hold_ns=2000000000))
        for row in rows:row['workflow_phase']='post-capture-recovery'
        output+=rows
    return output


class Observer:
    def __init__(self,g,arm,state,compact=False):
        self.g,self.arm,self.state=g,arm,state
        self.compact=compact
        self.pending=None;self.calls=0;self.source_calls=0
        self.point_counts={}
        self.pipeline_armed=False
        self.record=dict(scope='read-only original C5.32 capture/source lifecycle',
            ram_patches=[],cpu_register_redirection=False,compact=compact,transitions=[])
        g.data['capture_recovery_flow']=self.record
        (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
        if not compact:
            arm(0x40f48378,'capture_app_recovery_sequence_enter')
            arm(0x40c2b734,'capture_app_recovery_source_enter')
        for pc,label in POINTS.items():
            if pc not in DEFERRED and self.keep(label):arm(pc,'capture_app_recovery_observe_'+label)

    def keep(self,label):
        return not self.compact or label.startswith('ccomp_') or label in (
            'capture_control_fault_entry','capture_control_fault_latch','capture_control_error_report',
            'pipeline_error_descriptor','pipeline_error_display','pipeline_watchdog_expired',
            'source_stop_request','source_restart_result','capture_completion')

    def observe(self,row,regs):
        name=row['name'];g=self.g
        if name.startswith('capture_app_recovery_rearm_'):
            pc=int(name.rsplit('_',1)[1],16)
            self.arm(pc,'capture_app_recovery_observe_'+POINTS[pc])
            return
        item=dict(name=name,virtual_ns=row['virtual_ns'],cpu=row['cpu'],
            caller=hex(regs['X30']),source_control={hex(o):g.rd(0x15080000+o) for o in (0x10,0x28)},
            primary_hold=g.rd(0x150c0018),
            raw=self.state(g,'raw-pipeline-state'),lcd=self.state(g,'engine1548-scanout-state'))
        if name.startswith('capture_app_recovery_observe_'):
            pc=regs['PC'];count=self.point_counts.get(pc,0)+1;self.point_counts[pc]=count
            if name.endswith('source_stop_request') and not self.pipeline_armed:
                self.pipeline_armed=True
                for target,label in DEFERRED.items():
                    if self.keep(label):self.arm(target,'capture_app_recovery_observe_'+label)
            if name.endswith('pipeline_wait_entry'):
                target=regs['X30']
                if 0x40160000 <= target < 0x45000000 and target not in POINTS:
                    POINTS[target]='pipeline_wait_return_'+format(target,'x')
                    self.arm(target,'capture_app_recovery_observe_'+POINTS[target])
            item.update(registers={k:hex(regs[k]) for k in
                ('X00','X01','X02','X03','X08','X19','X20','X21','X22','X23','X24','X25','X26','X30','SP')},
                point_call=count,front_state_hex=g.read_bytes(0xa04c22300,0x680).hex())
            if 'ccomp_' in name:
                item['ccomp_gpio']=self.state(g,'ccomp-gpio-state')
                item['ccomp_driver_hex']=g.read_bytes(0xa04c29018,0x60).hex()
            if 'capture_control_' in name or name.endswith(('pipeline_error_descriptor','pipeline_error_table','pipeline_error_display','pipeline_watchdog_expired')):
                item['capture_control_hex']=g.read_bytes(0xa03d9da00,0xc00).hex()
                item['fault_table_hex']=g.read_bytes(0xa03da68d0,0x200).hex()
                if 0xa00000000 <= regs['X00'] <= 0xa20000000-64:
                    item['fault_payload_hex']=g.read_bytes(regs['X00'],64).hex()
                for register in ('X01','X19'):
                    if 0xa00000000 <= regs[register] <= 0xa20000000-64:
                        item['argument_'+register+'_hex']=g.read_bytes(regs[register],64).hex()
                if 0xa00000000 <= regs['SP'] <= 0xa20000000-0x500:
                    item['fault_stack_hex']=g.read_bytes(regs['SP'],0x500).hex()
            if 'source_' in name and 0xa00000000 <= regs['SP'] <= 0xa20000000-0xb0:
                item['source_stack_hex']=g.read_bytes(regs['SP'],0xb0).hex()
            if name.endswith('capture_completion') and 0xa00000000 <= regs['X01'] <= 0xa20000000-64:
                item['completion_payload_hex']=g.read_bytes(regs['X01'],64).hex()
            if name.endswith(('application_stop_request','sequence_stop_request','pipeline_stop_request')):
                pointer=regs['X00']
                if 0xa00000000 <= pointer <= 0xa20000000-64:
                    item['request_payload_hex']=g.read_bytes(pointer,64).hex()
                if 0xa00000000 <= regs['SP'] <= 0xa20000000-0x300:
                    item['request_stack_hex']=g.read_bytes(regs['SP'],0x300).hex()
            if 'pipeline_' in name or name.endswith(('source_stop_request','source_restart_result')):
                item['pipeline_state_hex']=g.read_bytes(0xa03d91b60,0x720).hex()
            if 'wait' in name:
                item['secondary_timing']=self.state(g,'event1508-secondary-timing-state')
            if name.endswith('receiver_control_write'):
                item['receiver_write']=dict(address=hex(regs['X08']+0x10c),
                    value=hex(regs['X09']&0xffffffff))
            if count<32:self.arm(pc+4,'capture_app_recovery_rearm_'+format(pc,'x'))
        elif 'sequence_' in name:
            item['sequence_state_hex']=g.read_bytes(0xa03d90ae0,0x1000).hex()
            if name.endswith('_enter'):
                if self.pending is not None:raise ValueError('Overlapping original CAPSEQ callback')
                self.pending=(regs['SP'],regs['X30'],regs['X00']&0xffffffff);self.calls+=1
                item['event_mask']=hex(self.pending[2])
                self.arm(0x40f4d688,'capture_app_recovery_sequence_return')
            else:
                if self.pending is None or (regs['SP'],regs['X30'])!=self.pending[:2]:
                    raise ValueError('CAPSEQ callback return does not match its original stack')
                item['event_mask']=hex(self.pending[2]);self.pending=None
                if self.calls<256:self.arm(0x40f48378,'capture_app_recovery_sequence_enter')
            item['callback_number']=self.calls
        elif name.endswith('_enter'):
            self.source_calls+=1
            item.update(mask=hex(regs['X01']&0xffffffff),clear=bool(regs['X02']))
            if 0xa00000000<=regs['SP']<=0xa20000000-32:
                item['original_stack_hex']=g.read_bytes(regs['SP'],32).hex()
            item['source_masks']={hex(o):g.rd(0x15080000+o) for o in (0x44,0x50,0x68)}
            item['secondary_timing']=self.state(g,'event1508-secondary-timing-state')
            item['front_state_hex']=g.read_bytes(0xa04c22300,0x680).hex()
            graph=self.state(g,'engine1543-control-state')
            item['resize_controls']=[{k:b[k] for k in ('base','active','held','starts','stops')}
                                     for b in graph['blocks']]
            primary=self.state(g,'engine150c-state')
            item['primary_control']={k:primary[k] for k in ('active','latched','configured',
                'starts','stop_requested','stop_done','stop_pending','direct_stop_done')}
            item['processing_control']=self.state(g,'engine151-control-state')
            self.arm(0x40c2b774,'capture_app_recovery_source_return')
        elif self.source_calls<96:
            self.arm(0x40c2b734,'capture_app_recovery_source_enter')
        self.record['transitions'].append(item)
        with (g.out/'capture-recovery.partial.jsonl').open('a') as f:
            f.write(json.dumps(item)+'\n')
