# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only original15e2 arguments, result/IRQ and actual encoded RAM."""
import hashlib
import json
import struct
from pathlib import Path


def observe(guest,driver_address=None):
    row=dict(scope='read-only original15e2 ISR/callback; functional codec units provisional')
    row['jpeg']=json.loads(guest.qmp.command('qom-get',path='/machine',property='engine15e2-jpeg-state'))
    # ISR entry X0 is the actual original driver. Do not infer a second
    # object from its neighbor or keep reading port0 after port1 starts.
    addresses=guest.data.setdefault('engine15e2_observed_drivers',[])
    address=driver_address if driver_address is not None else (addresses[-1] if addresses else 0xa02808638)
    if not 0xa00000000<=address<=0xa40000000-40:
        raise ValueError('Original JPEG driver must remain in bounded RAM')
    raw=guest.read_bytes(address,40)
    ident,port,arg,_,_=struct.unpack('<5Q',raw)
    if port not in (0x15e20000,0x15e21000):
        raise ValueError('Original JPEG driver port differs from the shared contract')
    if driver_address is not None and address not in addresses:addresses.append(address)
    row.update(driver_address=hex(address),descriptor_id=ident,port=hex(port),bank=(port-0x15e20000)//0x1000)
    row['driver_hex']=raw.hex(); arg=struct.unpack_from('<Q',raw,16)[0]
    if 0xa00000000<=arg<=0xa40000000-0xc0:
        packet=guest.read_bytes(arg,0xc0)
        row['program0_address']=hex(arg);row['program0_hex']=packet.hex()
        row['callback']=hex(struct.unpack_from('<Q',packet,0xa8)[0])
    return row


def capture(guest, *, model='zr'):
    report=dict(scope='read-only original driver arguments; physical codec layout/units unproved',model=model,banks=[])
    guest.data['engine15e2_native_observation']=report
    (guest.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    addresses=guest.data.get('engine15e2_observed_drivers') or [0xa02808638]
    for driver_address in addresses:
      item=dict(driver_address=hex(driver_address));report['banks'].append(item)
      try:
        raw=guest.read_bytes(driver_address,40);item['driver_hex']=raw.hex()
        ident,port,arg0,arg1,flags=struct.unpack('<5Q',raw)
        item.update(descriptor_id=ident,port=hex(port),flags=hex(flags))
        for name,address in [('program0',arg0),('program1',arg1)]:
            if not address:continue
            if not 0xa00000000<=address<=0xa40000000-0xc0:
                item[name+'_unreadable_address']=hex(address);continue
            packet=guest.read_bytes(address,0xc0)
            item[name+'_address']=hex(address);item[name+'_hex']=packet.hex()
            target=struct.unpack_from('<Q',packet)[0]
            if 0xa00000000<=target<=0xa40000000-0x40:
                item[name+'_image_descriptor_address']=hex(target)
                item[name+'_image_descriptor_hex']=guest.read_bytes(target,0x40).hex()
      except Exception as exc:item['capture_error']=repr(exc)
    state=json.loads(guest.qmp.command('qom-get',path='/machine',property='engine15e2-jpeg-state'))
    report['jpeg']=state
    bank=0
    if guest.data.get('engine15e2_observed_drivers'):
        bank=observe(guest)['bank']
    elif guest.data.get('probe_arguments',{}).get('capture_transition_batch'):
        ports=json.loads(guest.qmp.command('qom-get',path='/machine',property='engine15e2-alternate-bank-state'))
        bank=ports['active_bank']
        report['configured_request_bank_source']='actual shared codec active-bank state'
    fields=json.loads(guest.qmp.command('qom-get',path='/machine',property='engine15e2-config-state'))['banks'][bank]['fields']
    current=dict(width=fields[0x418//4],height=fields[0x41c//4],y_stride=fields[0x410//4],
        uv_stride=fields[0x414//4],y=fields[0x430//4]<<4,uv=fields[0x434//4]<<4,
        output=fields[0x440//4]<<4,capacity=fields[0x458//4]*512,core_control=fields[0x404//4])
    report['last_configured_request']=current
    # The second original request is thumbnail-sized. Preserve its actual
    # input without admitting an unsupported codec request or changing RAM.
    if (guest.data.get('probe_arguments',{}).get('engine15e2_jpeg') and
            0<current['width']<=1024 and 0<current['height']<=1024):
        current['planes']=[]
        for label in ('y','uv'):
            try:
                size=current[label+'_stride']*current['height'];address=current[label]
                if not 0<size<=4*1024*1024 or not 0x800000000<=address<=0x900000000-size:
                    raise ValueError('bounded current thumbnail input required')
                file=guest.out/('engine15e2-next-input-'+label+'.bin')
                reply=guest.qmp.hmp(f'pmemsave {address:#x} {size:#x} "{file}"')
                if reply.strip():raise RuntimeError(reply)
                data=file.read_bytes()
                current['planes'].append(dict(label=label,file=file.name,bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),nonzero_bytes=sum(v!=0 for v in data),
                    min=min(data),max=max(data),distinct_values=len(set(data))))
            except Exception as exc:current[label+'_capture_error']=repr(exc)
    count_only=False
    if (guest.data.get('probe_arguments',{}).get('engine15e2_preflight')
            or guest.data.get('probe_arguments',{}).get('capture_pipeline')):
        report['preflight']=json.loads(guest.qmp.command('qom-get',path='/machine',property='engine15e2-preflight-state'))
        count_only=report['preflight']['last_count_only']
    if state['jobs'] and not count_only:
        try:
            address,size=state['output'],state['last_bytes']
            if not 0<size<=128*1024*1024 or not 0x800000000<=address<=0x900000000-size:
                raise ValueError('bounded actual JPEG output required')
            output=guest.out/'engine15e2-native-output.jpg'
            reply=guest.qmp.hmp(f'pmemsave {address:#x} {size:#x} "{output}"')
            if reply.strip():raise RuntimeError(reply)
            data=output.read_bytes()
            if len(data)!=size:raise ValueError('actual JPEG RAM dump truncated')
            report['output']=dict(file=output.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                scope='actual device-generated guest RAM; not host-encoded and not camera-saved file')
            from PIL import Image
            with Image.open(output) as im:
                im.load();report['output'].update(decoded_width=im.width,decoded_height=im.height,independent_decode=True)
        except Exception as exc:report['jpeg_capture_error']=repr(exc)
    (guest.out/'engine15e2-native-observation.json').write_text(json.dumps(report,indent=2)+'\n')
