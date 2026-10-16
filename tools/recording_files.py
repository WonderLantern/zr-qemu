# SPDX-License-Identifier: GPL-2.0-or-later
"""Inspect/export/view exact movies from a stopped owned emulator card.

Metadata inspection is not codec acceptance. A read-only FUSE view preserves
all original file bytes and avoids extracting multi-gigabyte R3D recordings.
"""
import argparse
import errno
import json
import os
from pathlib import Path
import stat

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True,help='Completed native run output directory')
    p.add_argument('--extract-file',help='Exact card-relative path from the listing')
    p.add_argument('--destination',type=Path)
    p.add_argument('--mount',type=Path,help='Fresh empty local directory for read-only FUSE files')
    a=p.parse_args()
    if os.name=='nt' or os.environ.get('WSL_DISTRO_NAME')=='ubuntu-noble':p.error('Use Linux or explicitly selected Nikon WSL')
    output=a.output.resolve();native=json.loads((output/'result.json').read_text())
    waveform=native.get('mode_key_waveform',{})
    if (not native.get('owned_qemu_stopped') or native.get('error') or
        native.get('cpu_register_redirection') or not native.get('original_input_unchanged') or
        not waveform.get('all_consumed') or native.get('native_fault_reports_observed') or
        not all(row.get('passed') for row in native.get('checks',[]))):
        raise ValueError('Complete stopped fault-free original-control workflow required')
    # The declared English cached-data preference is permitted, as in the
    # photo auditor. Arbitrary RAM/code/OS/task modifications remain refused.
    patches=native.get('ram_patches',[]);preference=native.get('ui_language_preference',{})
    baseline={'9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f':'1d000000',
              'd495cce73462a51b971ad25941a2deea92ccc667f127b930da00949101a51b82':'1a000000'}
    if patches:
        expected=dict(kind='ui_language_preference',address='0xa03fd1768',bytes=4,
            before_hex=baseline.get(native.get('main_sha256')),after_hex='04000000',pc='0x403fd95c',cpu=0)
        if (patches!=[expected] or preference.get('patch')!=expected or
            preference.get('firmware_sha256')!=native.get('main_sha256') or
            not preference.get('applied') or preference.get('final_cache_hex')!='04000000'):
            raise ValueError('Unexpected guest RAM modification')
    build=native.get('public_build',native.get('shared_z9_build',{}))
    binary=Path(build['binary']).resolve();work=binary.parents[1]
    card=Path(native['private_virtual_card']['path']).absolute()
    if card.name!='capture-card.raw' or not card.is_relative_to(work/'runs') or not card.is_file():
        raise ValueError('Declared owned generated regular card required')
    os.environ['WL_ZR_WORK']=str(work)
    from virtual_exfat_window import fsck_private_card
    from inspect_virtual_exfat import catalog
    from virtual_exfat_file import VirtualExfatFile
    from extract_virtual_exfat import extract
    checked=fsck_private_card(card)
    if checked['fsck_exit'] or not checked['source_unchanged']:raise ValueError('Read-only filesystem check failed')
    checked['declared_source_card']=str(card)
    (output/'recording-card.audit.json').write_text(json.dumps(checked,indent=2)+'\n')
    inventory=catalog(card)
    (output/'recording-card.catalog.json').write_text(json.dumps(inventory,indent=2)+'\n')
    entries=[r for r in inventory['files'] if not r['directory'] and Path(r['path']).suffix.upper() in ('.R3D','.NEV','.MOV','.MP4')]
    if not entries:raise ValueError('No actual initialized movie files')
    if bool(a.extract_file)!=bool(a.destination):p.error('--extract-file and --destination must be supplied together')
    if a.extract_file:
        row=next((r for r in entries if r['path']==a.extract_file),None)
        if row is None:raise ValueError('Choose an exact listed movie')
        dest=a.destination.resolve()
        if dest.is_relative_to(ROOT) and not dest.is_relative_to(ROOT/'.local'):
            raise ValueError('Private exported media must stay outside tracked source')
        extract(card,row['path'],dest,max_bytes=card.stat().st_size)
    readers={};details=[]
    try:
        for row in entries:
            name='/'+Path(row['path']).name
            if name in readers:raise ValueError('Ambiguous movie basename')
            reader=VirtualExfatFile(card,row['path']);readers[name]=reader
            item=dict(file=row['path'],bytes=reader.size,initialized=True)
            if Path(row['path']).suffix.upper() in ('.R3D','.NEV'):
                from isobmff_raw_index import raw_packets
                packets=raw_packets(reader)
                item.update(frames=len(packets),packet_index=packets,
                    scope='Bounded metadata only; complete payload/codec decoding still required')
            details.append(item)
        report=dict(files=details,original_bytes_replaced=0,read_only=True,full_codec_decode_performed=False)
        (output/'recording-files.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(files=[{k:r[k] for k in ('file','bytes','frames') if k in r} for r in details],
            filesystem_clean=True,full_codec_decode_performed=False)),flush=True)
        if a.mount:
            mount=a.mount.resolve()
            if mount.is_relative_to(ROOT) and not mount.is_relative_to(ROOT/'.local'):
                raise ValueError('Private movie mounts must stay outside tracked source')
            if not mount.is_dir() or list(mount.iterdir()):raise ValueError('Fresh empty mount directory required')
            try:from fuse import FUSE,Operations,FuseOSError
            except ImportError:from fusepy import FUSE,Operations,FuseOSError
            stamp=card.stat().st_mtime
            class View(Operations):
                def getattr(self,path,fh=None):
                    if path=='/':return dict(st_mode=stat.S_IFDIR|0o555,st_nlink=2,st_uid=os.getuid(),st_gid=os.getgid())
                    if path not in readers:raise FuseOSError(errno.ENOENT)
                    return dict(st_mode=stat.S_IFREG|0o444,st_nlink=1,st_size=readers[path].size,
                        st_uid=os.getuid(),st_gid=os.getgid(),st_atime=stamp,st_mtime=stamp,st_ctime=stamp)
                def readdir(self,path,fh):return ['.','..']+[name[1:] for name in readers]
                def open(self,path,flags):
                    if path not in readers:raise FuseOSError(errno.ENOENT)
                    if flags&os.O_ACCMODE!=os.O_RDONLY:raise FuseOSError(errno.EROFS)
                    return 0
                def read(self,path,size,offset,fh):
                    reader=readers[path];size=min(size,max(0,reader.size-offset))
                    return reader.read_at(offset,size) if size else b''
            print('Read-only original movie view: '+str(mount),flush=True)
            FUSE(View(),str(mount),foreground=True,ro=True,nothreads=True)
    finally:
        for reader in readers.values():reader.close()


if __name__=='__main__':main()
