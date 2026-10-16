# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit virtual-time stereo silence input; rates are experimental inputs.

Each whole block waits its duration, then follows the original pending DMA.
No guest callback, CPU register, instruction or software event is changed.
"""
import json


def parse_rates(value):
    rates={}
    for item in value.split(','):
        channel,rate=(int(v) for v in item.split(':'))
        if channel in rates or not 0<=channel<5 or not 8000<=rate<=384000:
            raise ValueError('Distinct channels0..4 and explicit rates8000..384000 required')
        rates[channel]=rate
    if not rates:raise ValueError('At least one explicit input rate required')
    return rates


class AudioPCMInput:
    def __init__(self,g,rates):
        self.g=g;self.rates=parse_rates(rates);self.pending={};self.next_poll=0
        self.record=dict(rates=self.rates,blocks=0,bytes=0,stale_retries=0,history=[],
            physical_clock_verified=False,physical_packing_verified=False,
            scope='Explicit stereoLE32 zero input paced in virtual time; actual original DMA/IRQ, no original DSP/codec claim')
        g.data['external_pcm_input']=self.record

    def tick(self,clock):
        if not clock.running or clock.seconds<self.next_poll:return
        now=clock.seconds;self.next_poll=now+.002
        state=json.loads(self.g.qmp.command('qom-get',path='/machine',property='serial5-pcm-state'))
        self.record['last_state']=state
        for r in state['channels']:
            ch=r['channel']
            if ch not in self.rates:continue
            if not r['ready']:
                self.pending.pop(ch,None);continue
            token=(r['phase'],r['local'],r['words'],r['blocks'],r['dma_channel'])
            old=self.pending.get(ch)
            if old is None or old[0]!=token:
                self.pending[ch]=(token,now+r['words']/(2*self.rates[ch]));continue
            if now<old[1]:continue
            if self.record['blocks']>=4096:raise RuntimeError('Explicit PCM input budget exhausted')
            try:
                self.g.qmp.command('qom-set',path='/machine',property='serial5-pcm-input',
                    value=f"{ch}:{r['phase']}:{r['local']:x}:{r['words']:x}:0:0")
            except RuntimeError as error:
                if 'PCM input does not match' not in str(error):raise
                self.record['stale_retries']+=1;self.pending.pop(ch,None);continue
            self.record['blocks']+=1;self.record['bytes']+=r['words']*4
            if len(self.record['history'])<64:
                self.record['history'].append(dict(channel=ch,phase=r['phase'],local=r['local'],
                    words=r['words'],virtual_seconds=now))
            self.pending.pop(ch,None)
