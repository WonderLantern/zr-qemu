# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only scheduling after STOP: wait for real live frames and visible menus."""
import hashlib,json,time
from pathlib import Path
from zr_key_sequence import menu_focus_matches
from zr_video_ready import visible_video_ready, visible_video_menu


def fresh_return(baseline,raw,lcd):
    return (raw['frames']>=baseline['raw']['frames']+8 and
        lcd['video_frames']>baseline['scanout']['video_frames'] and lcd['last_frame_has_video'])


class VideoRecoveryPacing:
    def __init__(self,g,states,last_stop,timeout):
        self.g,self.timeout,self.next_poll=g,timeout,0
        self.targets={}
        for i in range(last_stop,len(states)-3):
            if [s['label'] for s in states[i:i+4]]==['menu-press','menu-release','half-press','half-release']:
                self.targets[i+2]='menu';self.targets[i+3]='return'
        if self.targets:self.targets[last_stop]='post-stop'
        self.rows=g.data.setdefault('video_recovery_gates',{})
        (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())

    def advance(self,stage,clock):
        if stage not in self.targets:return True
        row=self.rows.setdefault(str(stage),dict(kind=self.targets[stage],ready=False,begun_seconds=clock.seconds,samples=[]))
        if row['ready']:return True
        if time.monotonic()<self.next_poll:return False
        self.g.qmp.command('stop')
        try:
            raw=json.loads(self.g.qmp.command('qom-get',path='/machine',property='raw-pipeline-state'))
            lcd=json.loads(self.g.qmp.command('qom-get',path='/machine',property='engine1548-scanout-state'))
            baseline=row.setdefault('baseline',dict(raw=raw,scanout=lcd))
            if row['kind']=='return':baseline=self.rows[str(stage-1)]['evidence']
            candidate=self.g.runtime/'video-recovery-candidate.ppm'
            self.g.qmp.command('screendump',filename=str(candidate));pixels=candidate.read_bytes()
            menu=visible_video_menu(pixels)
            visible=bool(visible_video_ready(candidate,raw,lcd)) and not menu
            fresh=fresh_return(baseline,raw,lcd)
            ready=menu if row['kind']=='menu' else fresh and visible
            observation=dict(raw_frames=raw['frames'],lcd_frames=lcd['video_frames'],menu_visible=menu,live_visible=visible,fresh=fresh,virtual_seconds=clock.seconds)
            if len(row['samples'])<32:row['samples'].append(observation)
            row['last_sample']=observation
            if ready:
                target=self.g.out/f'zr-video-recovery-{stage:03d}.ppm';target.write_bytes(pixels)
                row.update(ready=True,evidence=dict(file=target.name,sha256=hashlib.sha256(pixels).hexdigest(),raw=raw,scanout=lcd,virtual_ns=int(clock.seconds*1e9)))
                print('ZR video recovery: '+row['kind']+' visible with real frame evidence',flush=True)
            (self.g.out/'video-recovery-progress.json').write_text(json.dumps(self.rows,indent=2)+'\n')
        finally:self.g.qmp.command('cont')
        self.next_poll=time.monotonic()+.5
        if not row['ready'] and clock.seconds-row['begun_seconds']>=self.timeout:
            raise TimeoutError('Original VIDEO recovery did not show '+row['kind'])
        return row['ready']
