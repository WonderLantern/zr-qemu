# SPDX-License-Identifier: GPL-2.0-or-later
"""Local firmware-dependent acceptance; no firmware or image assets included."""
import hashlib
import json
import time
import numpy as np
from PIL import Image
from boot import key_body

MENU_RGB_SHA256='d77e66fffd29e09d3282ebe36f8d15afeb8f0845eac9b00b706753fda2aa715c'

def state(g,name):return json.loads(g.qmp.command('qom-get',path='/machine',property=name))

def verify_pixels(g,label,lcd):
    """Independently decode the guest's current NV12 plane at clear-alpha pixels."""
    w,h=lcd['width'],lcd['height']
    source=state(g,'engine1548-source-state')
    stride=source['units'][1]['direct'][3]
    if not (w>0 and h>0 and w%2==h%2==0 and stride>=w and stride*h<=16*1024*1024):
        raise ValueError('Unsupported video geometry for independent validation')
    before=dict(lcd)
    target=g.out/(label+'.ppm');g.qmp.command('screendump',filename=str(target))
    with Image.open(target) as im:
        frame=np.asarray(im.convert('RGB'));im.save(g.out/(label+'.png'))
    arrays={}
    for name,address,size in (('y',lcd['video_y'],stride*h),('uv',lcd['video_uv'],stride*h//2),('alpha',lcd['alpha'],w*h)):
        path=g.out/(label+'-'+name+'.bin')
        reply=g.qmp.hmp(f'pmemsave {address:#x} {size:#x} '+json.dumps(str(path)))
        if reply or path.stat().st_size!=size:raise RuntimeError('Guest plane capture failed')
        arrays[name]=np.fromfile(path,np.uint8)
    if state(g,'engine1548-scanout-state')!=before:raise RuntimeError('Paused display changed during capture')
    y=arrays['y'].reshape(h,stride)[:,:w].astype(float)
    uv=arrays['uv'].reshape(h//2,stride)[:,:w]
    u=uv[:,0::2].repeat(2,0).repeat(2,1).astype(float)-128
    v=uv[:,1::2].repeat(2,0).repeat(2,1).astype(float)-128
    rgb=np.clip(np.stack((y+1.402*v,y-.344136*u-.714136*v,y+1.772*u),axis=-1),0,255)
    clear=arrays['alpha'].reshape(h,w)==0
    if int(clear.sum())<=w*h//4:raise AssertionError('No sufficiently exposed live-view area')
    error=np.abs(frame.astype(float)[clear]-rgb[clear])
    record=dict(label=label,clear_pixels=int(clear.sum()),mean_rgb_error=float(error.mean()),
        max_rgb_error=float(error.max()),luma_std=float(y[clear].std()),video_frames=lcd['video_frames'])
    record['passed']=record['mean_rgb_error']<1 and record['luma_std']>10
    g.data.setdefault('independent_pixel_checks',[]).append(record)
    if not record['passed']:raise AssertionError('LCD does not match non-flat guest video: '+label)
    return record

class MenuAcceptance:
    """Three original MENU/half-shutter round trips in the same running guest."""
    def __init__(self,g,peer,progress,*,virtual_clock=False):
        self.g,self.peer,self.progress=g,peer,progress
        self.stage='video';self.cycle=0;self.baseline=0;self.video_baseline=0;self.stable=None
        self.since=time.monotonic();self.done=False;self.menu_presses=0
        self.virtual_clock=virtual_clock
        if virtual_clock:self.since=state(g,'runtime-clock-state')['virtual_ns']/1e9
        self.record=dict(passed=False,cycles=3,stages=[],
            menu_entry_sequence=['release half-shutter','MENU press/release',
                'wait for native MENU; one further press/release if needed'],
            menu_attempts=[],
            acceptance_timebase='QEMU_CLOCK_VIRTUAL' if virtual_clock else 'host monotonic',
            scope='functional emulation; not physical camera acceptance')
        g.data['menu_acceptance']=self.record
    def send(self,*,menu=False,half=False):self.peer.enqueue_external(key_body(menu=menu,half=half),2)
    def transition(self,stage,now):self.stage=stage;self.since=now;self.stable=None
    def tick(self,now,raw,lcd,screen):
        if self.virtual_clock:now=state(self.g,'runtime-clock-state')['virtual_ns']/1e9
        if self.done:return
        if now-self.since>120:raise AssertionError('Timed out during MENU acceptance: '+self.stage)
        idle=self.peer.tx is None and self.peer.rx is None and not self.peer.rx_retiring and not self.peer.pending
        if self.stage=='video':
            source=state(self.g,'engine1518-state')['instances'][2]
            processing=state(self.g,'engine151-control-state')['instances'][1]
            active=source['config'][12]==1 and processing['active']
            if (not active or raw['frames']<self.baseline+8 or
                lcd.get('video_frames',0)<=self.video_baseline or
                not lcd.get('last_frame_has_video',False)):
                self.stable=None;return
            if self.stable is None:self.stable=(now,raw['frames'],lcd['video_frames']);return
            if (now-self.stable[0]<2 or raw['frames']<=self.stable[1] or
                lcd['video_frames']<=self.stable[2]):return
            label='initial-liveview' if not self.cycle else 'return-'+str(self.cycle)
            verify_pixels(self.g,label,lcd)
            self.record['stages'].append(dict(label=label,raw_frames=raw['frames'],lcd_video_frames=lcd['video_frames']))
            if self.cycle==3:
                self.record['passed']=self.done=True;self.progress('Three MENU round trips and pixel checks passed');return
            self.cycle+=1;self.menu_presses=0;self.send();self.transition('release-before-menu',now)
        elif self.stage=='release-before-menu' and idle and now-self.since>=2:
            self.menu_presses+=1
            self.record['menu_attempts'].append(dict(cycle=self.cycle,press=self.menu_presses))
            self.send(menu=True);self.transition('release-menu-primer',now)
        elif self.stage=='release-menu-primer' and idle and now-self.since>=.4:
            self.send();self.transition('menu',now)
        elif self.stage=='menu':
            with Image.open(screen) as im:digest=hashlib.sha256(im.convert('RGB').tobytes()).hexdigest()
            self.record['last_menu_rgb_sha256']=digest
            if digest!=MENU_RGB_SHA256:
                # Let the original UI and capture drain finish before another
                # key. Two unconditional presses can leave a menu that has
                # already opened. Transport retirement alone is not UI readiness.
                if idle and now-self.since>=10 and self.menu_presses<2:
                    with Image.open(screen) as im:im.save(self.g.out/('before-menu-retry-'+str(self.cycle)+'.png'))
                    self.menu_presses+=1
                    self.record['menu_attempts'].append(dict(cycle=self.cycle,press=self.menu_presses,
                        previous_rgb_sha256=digest))
                    self.send(menu=True);self.transition('release-menu-primer',now)
                return
            source=state(self.g,'engine1518-state')['instances'][2]
            processing=state(self.g,'engine151-control-state')['instances'][1]
            if source['config'][12] or processing['active']:return
            with Image.open(screen) as im:im.save(self.g.out/('menu-'+str(self.cycle)+'.png'))
            self.record['stages'].append(dict(label='menu-'+str(self.cycle),raw_frames=raw['frames'],menu_rgb_sha256=digest))
            self.baseline=raw['frames'];self.video_baseline=lcd['video_frames']
            self.transition('release-in-menu',now)
        # The peer serializes external keys behind an in-flight MCU TX/RX.
        # Waiting for a two-second fully idle window can starve this input
        # while the camera's original transport continuously polls.
        elif self.stage=='release-in-menu' and now-self.since>=2:
            self.send(half=True);self.transition('video',now)
