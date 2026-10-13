# SPDX-License-Identifier: GPL-2.0-or-later
import struct
import json
import sys
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from make_cmos import generate
from mcu_frames import frames
from boot import key_body
from service_z9_mcu import Peer
from validate_run import MenuAcceptance
from z9_global1_boundary_input import Peer as BoundaryPeer

class BoundaryClockTests(unittest.TestCase):
    def test_pause_dropped_periods_and_record_cap_do_not_change_delivery(self):
        class QMP:
            def __init__(self):self.ns=0;self.running=True;self.sent=[]
            def command(self,op,**args):
                if op=='qom-get':return json.dumps(dict(virtual_ns=self.ns,running=self.running))
                self.sent.append(args)
        class Guest:
            def __init__(self,path):self.qmp=QMP();self.out=path;self.data={}
        with tempfile.TemporaryDirectory() as directory:
            g=Guest(Path(directory));peer=BoundaryPeer(g,33)
            peer.record['limit']=1
            peer.tick();self.assertEqual(len(g.qmp.sent),1)
            g.qmp.ns=1_000_000_000;g.qmp.running=False;peer.tick()
            self.assertEqual(len(g.qmp.sent),1)
            g.qmp.running=True;peer.tick();peer.tick()
            self.assertEqual(len(g.qmp.sent),2)  # no catch-up burst
            g.qmp.ns+=34_000_000;peer.tick()
            self.assertEqual(len(g.qmp.sent),3)  # recording cap is not a device stop
            self.assertEqual(peer.record['total_deliveries'],3)
            self.assertEqual(len(peer.record['deliveries']),1)
            self.assertTrue(peer.record['record_limit_reached'])

class Inputs(unittest.TestCase):
    def test_raw_header_size_range(self):
        raw=generate(32,24)
        self.assertEqual(struct.unpack_from('<8s6I',raw),(b'NZ9RAW1\0',32,24,12,0,0,4095))
        samples=np.frombuffer(raw[32:],dtype='<u2')
        self.assertEqual(len(samples),32*24)
        self.assertLessEqual(int(samples.max()),4095)
        self.assertGreater(int(samples.max()),3000)

    def test_user_red_image_is_rggb(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'red.png';Image.new('RGB',(4,4),(255,0,0)).save(path)
            raw=np.frombuffer(generate(4,4,path)[32:],dtype='<u2').reshape(4,4)
            self.assertTrue(np.all(raw[::2,::2]==4095))
            self.assertTrue(np.all(raw[1::2]==0))
            self.assertTrue(np.all(raw[:,1::2]==0))

    def test_fragmented_transport_reconstructs_body(self):
        body=bytes(range(251))*3
        packets=frames(body,family=3,channel=3)
        self.assertEqual(len(packets),4)
        self.assertEqual(b''.join(p[8:248] for p in packets)[:len(body)],body)
        for i,p in enumerate(packets):
            self.assertEqual(len(p),256);self.assertEqual(sum(p)&255,255)
            self.assertEqual(p[252:254],bytes((4,i+1)))
            self.assertEqual(struct.unpack_from('<H',p,2)[0],len(body))

    def test_keys_are_separate_complete_inputs(self):
        menu,half,up=key_body(menu=True),key_body(half=True),key_body()
        self.assertEqual(len(menu),124)
        self.assertEqual([i for i in range(124) if menu[i]!=up[i]],[0x43])
        self.assertEqual([i for i in range(124) if half[i]!=up[i]],[7])
        for raw in (menu,half,up):self.assertEqual(sum(frames(raw,family=2)[0])&255,255)

    def test_invalid_input_rejected(self):
        for w,h in ((3,4),(0,4),(16386,4),(16384,16384)):
            with self.assertRaises(ValueError):generate(w,h)
        with self.assertRaises(ValueError):frames(bytes(241),channel=1)
        with self.assertRaises(ValueError):frames(b'')

class ServicePeer(unittest.TestCase):
    def test_smp_snapshot_services_global_breakpoint_once(self):
        pc=0x40c160d8
        class QMP:
            def hmp(self,command,cpu):
                return f'PC={pc:016x} X00=0000000000000000' if cpu in (0,1) else 'PC=0000000040000000 X00=0000000000000000'
        class Guest:
            def __init__(self):self.qmp=QMP();self.rsp_commands=[];self.qt_commands=[]
            def rsp(self,command):self.rsp_commands.append(command)
            def qt_command(self,command):self.qt_commands.append(command)
        guest=Guest();peer=Peer.__new__(Peer)
        peer.g=guest;peer.points={pc:'tx_gpio_isr'};peer.record={'events':[]}
        peer.asserted={25};peer.gic='/machine/gic'
        self.assertTrue(peer.handle())
        self.assertEqual(guest.rsp_commands,[f'z1,{pc:x},4'])
        self.assertEqual(guest.qt_commands,['set_irq_in /machine/gic unnamed-gpio-in 25 0'])
        self.assertEqual(peer.record['events'][0]['simultaneous_cpu_hits'],[0,1])
        self.assertEqual(peer.record['events'][1],{'irq':57,'level':0})

    def test_e22_is_ignored_only_when_qemu_confirms_breakpoint_absent(self):
        pc=0x40c93c48
        class QMP:
            def __init__(self,table):self.table=table
            def hmp(self,command):self.asserted_command=command;return self.table
        class Guest:
            def __init__(self,table):self.qmp=QMP(table)
            def rsp(self,command):raise RuntimeError(f'{command}: bytearray(b\'E22\')')
        peer=Peer.__new__(Peer);peer.record={}
        peer.g=Guest('No breakpoints or watchpoints.')
        self.assertFalse(peer.disarm(pc,'tx_request',[0]))
        diagnostic=peer.record['breakpoint_remove_diagnostics'][0]
        self.assertFalse(diagnostic['address_still_present'])
        self.assertEqual(peer.g.qmp.asserted_command,'info breakpoints')
        peer.record={};peer.g=Guest(f'1 hw breakpoint keep y 0x{pc:x}')
        with self.assertRaisesRegex(RuntimeError,'E22'):
            peer.disarm(pc,'tx_request',[0])
        self.assertTrue(peer.record['breakpoint_remove_diagnostics'][0]['address_still_present'])
        peer.record={};peer.g=Guest("unknown command: 'info breakpoints'")
        with self.assertRaisesRegex(RuntimeError,'E22'):
            peer.disarm(pc,'tx_request',[0])
        self.assertIsNone(peer.record['breakpoint_remove_diagnostics'][0]['address_still_present'])

class MenuAcceptanceTests(unittest.TestCase):
    def test_half_shutter_queues_while_camera_transport_is_busy(self):
        class Peer:
            tx=object();rx=object();rx_retiring=True;pending=[object()]
            def __init__(self):self.sent=[]
            def enqueue_external(self,body,family):self.sent.append((body,family))
        class Guest:
            def __init__(self):self.data={}
        peer=Peer();acceptance=MenuAcceptance(Guest(),peer,lambda _:None)
        acceptance.stage='release-in-menu';acceptance.since=0
        acceptance.tick(3,{}, {},None)
        self.assertEqual(acceptance.stage,'video')
        self.assertEqual(len(peer.sent),1)
        self.assertEqual(peer.sent[0][1],2)

if __name__=='__main__':unittest.main()
