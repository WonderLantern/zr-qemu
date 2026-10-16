# SPDX-License-Identifier: GPL-2.0-or-later
"""Lossless storage for private virtual cards. Never opens a physical drive.

The QEMU guest sees its exact original block bytes. SQLite stores changed
4 KiB pages by SHA-256; repeated video frames share storage. Compression and
deduplication are host storage operations, not camera codecs or acceptance.
"""
import argparse
from collections import OrderedDict
import errno
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import time
import zlib

PAGE=4096
ROOT=Path(os.environ['WL_ZR_WORK']).resolve()/'runs'


def attach(card):
    """Replace one fresh owned regular image with its lossless virtual view."""
    card=Path(card).resolve()
    if (os.name=='nt' or os.environ.get('WSL_DISTRO_NAME')=='ubuntu-noble') or not card.is_relative_to(ROOT):
        raise ValueError('private Nikon run card only')
    if not card.is_file() or card.is_symlink():raise ValueError('fresh regular card required')
    base=card.with_name('capture-card.initial.raw');database=card.with_name('capture-card.blocks.sqlite')
    mount=card.with_name('card-mount');mount.mkdir(exist_ok=False)
    if base.exists() or database.exists():raise ValueError('fresh virtual storage required')
    card.rename(base)
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'--base',str(base),
        '--database',str(database),'--mount',str(mount)]
    with card.with_name('card-service.log').open('xb') as log:
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    deadline=time.monotonic()+10
    while not (mount/'card.raw').is_file():
        if proc.poll() is not None or time.monotonic()>deadline:
            raise RuntimeError('Owned virtual card mount failed; initial image preserved')
        time.sleep(.05)
    card.symlink_to(mount/'card.raw')
    record=dict(pid=proc.pid,command=command,card=str(card),base=str(base),database=str(database),
        mount=str(mount),lossless=True,guest_card_bytes=base.stat().st_size,
        recovery='Remount with recorded command before opening the symlink; fusermount -u only after all guest/audit readers close')
    card.with_name('card-service.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


class Store:
    def __init__(self,base,database):
        self.base=Path(base);self.size=self.base.stat().st_size
        self.fd=os.open(base,os.O_RDONLY);self.cache=OrderedDict()
        self.db=sqlite3.connect(database)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS blocks (sha BLOB PRIMARY KEY, body BLOB NOT NULL) WITHOUT ROWID')
        self.db.execute('CREATE TABLE IF NOT EXISTS pages (page INTEGER PRIMARY KEY, sha BLOB NOT NULL)')
        self.mapping=dict(self.db.execute('SELECT page,sha FROM pages'))
        self.known={r[0] for r in self.db.execute('SELECT sha FROM blocks')}
        self.written=self.read_bytes=self.flushes=0

    def page(self,index):
        digest=self.mapping.get(index)
        if digest is None:return os.pread(self.fd,PAGE,index*PAGE)
        data=self.cache.get(digest)
        if data is None:
            row=self.db.execute('SELECT body FROM blocks WHERE sha=?',(digest,)).fetchone()
            if row is None:raise OSError('missing content-addressed block')
            data=zlib.decompress(row[0])
            if len(data)!=PAGE or hashlib.sha256(data).digest()!=digest:raise OSError('card block integrity failure')
            self.remember(digest,data)
        else:self.cache.move_to_end(digest)
        return data

    def remember(self,digest,data):
        self.cache[digest]=data;self.cache.move_to_end(digest)
        while len(self.cache)>32768:self.cache.popitem(last=False)

    def read(self,size,offset):
        if offset<0 or size<0:raise ValueError('negative card read')
        size=min(size,max(0,self.size-offset));end=offset+size;parts=[]
        while offset<end:
            page,at=divmod(offset,PAGE);take=min(PAGE-at,end-offset)
            parts.append(self.page(page)[at:at+take]);offset+=take
        self.read_bytes+=size;return b''.join(parts)

    def write(self,data,offset):
        if offset<0 or offset>self.size-len(data):raise ValueError('card write range')
        count=len(data);pos=0
        while pos<count:
            index,at=divmod(offset,PAGE);take=min(PAGE-at,count-pos)
            body=data[pos:pos+take]
            if at or take!=PAGE:
                old=self.page(index);body=old[:at]+body+old[at+take:]
            if len(body)!=PAGE:raise ValueError('unaligned image capacity')
            digest=hashlib.sha256(body).digest()
            if self.mapping.get(index)!=digest:
                if digest not in self.known:
                    self.db.execute('INSERT INTO blocks VALUES (?,?)',(digest,zlib.compress(body,3)))
                    self.known.add(digest)
                self.db.execute('INSERT OR REPLACE INTO pages VALUES (?,?)',(index,digest))
                self.mapping[index]=digest
            self.remember(digest,body);offset+=take;pos+=take
        self.written+=count;return count

    def flush(self):
        self.db.commit();self.flushes+=1

    def close(self):
        self.flush();self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)');self.db.close();os.close(self.fd)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--mount',type=Path,required=True);a=p.parse_args()
    if (os.name=='nt' or os.environ.get('WSL_DISTRO_NAME')=='ubuntu-noble'):raise ValueError('Nikon WSL only')
    for path in (a.base,a.database,a.mount):
        if not path.resolve().is_relative_to(ROOT):raise ValueError('owned private run paths required')
    if not a.base.is_file() or a.base.is_symlink() or list(a.mount.iterdir()):raise ValueError('regular base and fresh empty mount required')
    try:from fuse import FUSE,Operations,FuseOSError
    except ImportError:from fusepy import FUSE,Operations,FuseOSError
    store=Store(a.base,a.database);initial=a.base.stat();stamp=time.time()
    def receipt():
        r=dict(pid=os.getpid(),base=str(a.base),mount=str(a.mount),database=str(a.database),
            bytes=store.size,unique_blocks=len(store.known),mapped_pages=len(store.mapping),
            guest_bytes_written=store.written,bytes_read=store.read_bytes,flushes=store.flushes,
            classification='lossless private virtual block storage; no camera codec or file modifications')
        a.database.with_suffix('.status.json').write_text(json.dumps(r,indent=2)+'\n');return r
    class Card(Operations):
        def init(self,path):receipt();print('private virtual card ready',flush=True)
        def getattr(self,path,fh=None):
            if path=='/':return dict(st_mode=stat.S_IFDIR|0o700,st_nlink=2,st_uid=os.getuid(),st_gid=os.getgid())
            if path!='/card.raw':raise FuseOSError(errno.ENOENT)
            return dict(st_mode=stat.S_IFREG|0o600,st_nlink=1,st_size=store.size,
                st_uid=os.getuid(),st_gid=os.getgid(),st_atime=stamp,st_ctime=stamp,st_mtime=stamp)
        def readdir(self,path,fh):return ['.','..','card.raw']
        def open(self,path,flags):
            if path!='/card.raw':raise FuseOSError(errno.ENOENT)
            if flags&os.O_TRUNC:raise FuseOSError(errno.EPERM)
            return 0
        def read(self,path,size,offset,fh):return store.read(size,offset)
        def write(self,path,data,offset,fh):
            try:return store.write(data,offset)
            except ValueError:raise FuseOSError(errno.ENOSPC)
        def flush(self,path,fh):store.flush();receipt();return 0
        def fsync(self,path,datasync,fh):return self.flush(path,fh)
        def truncate(self,path,length,fh=None):
            if length!=store.size:raise FuseOSError(errno.EPERM)
        def release(self,path,fh):return self.flush(path,fh)
    try:FUSE(Card(),str(a.mount),foreground=True,nothreads=True,direct_io=True)
    finally:
        receipt();store.close();after=a.base.stat()
        assert (initial.st_size,initial.st_mtime_ns)==(after.st_size,after.st_mtime_ns)


if __name__=='__main__':main()
