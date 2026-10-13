# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate a local linear RGGB input from synthetic bars or the user's image."""
import argparse
from pathlib import Path
import struct
import numpy as np
from PIL import Image

def generate(width=640,height=480,image=None,bits=12):
    if width%2 or height%2 or not 2<=width<=16384 or not 2<=height<=16384 or width*height>64*1024*1024:
        raise ValueError('Even dimensions, at most 16384 per axis and 64 million samples required')
    if bits not in (12,14):raise ValueError('12-bit or 14-bit linear input required')
    white=(1<<bits)-1
    if image:
        with Image.open(image) as im:rgb_image=np.asarray(im.convert('RGB').resize((width,height),Image.Resampling.LANCZOS),dtype=np.uint8)
    else:
        bars=np.array([[1,1,1],[1,1,0],[0,1,1],[0,1,0],[1,0,1],[1,0,0],[0,0,1],[0,0,0]],dtype=np.float64)
        bar_row=bars[np.arange(width)*8//width]
        luminance=np.linspace(.25,1,height)
    raw=np.empty((height,width),dtype='<u2')
    # Bound float intermediates to 32 rows; full-size input need not allocate
    # several complete RGB float images alongside the emulator.
    for start in range(0,height,32):
        end=min(height,start+32)
        rgb=(rgb_image[start:end].astype(np.float64)/255 if image else
             bar_row[None,:,:]*luminance[start:end,None,None])
        linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
        block=raw[start:end]
        for y,x,ch in ((0,0,0),(0,1,1),(1,0,1),(1,1,2)):
            block[y::2,x::2]=np.rint(linear[y::2,x::2,ch]*white).astype('<u2')
    return struct.pack('<8s6I',b'NZ9RAW1\0',width,height,bits,0,0,white)+raw.tobytes()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--image',type=Path)
    p.add_argument('--width',type=int,default=640);p.add_argument('--height',type=int,default=480)
    p.add_argument('--bits',type=int,choices=(12,14),default=12)
    p.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'.local/input.raw')
    a=p.parse_args();data=generate(a.width,a.height,a.image,a.bits)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(data)
    print(a.output)

if __name__=='__main__':main()
