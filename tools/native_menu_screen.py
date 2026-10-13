# SPDX-License-Identifier: GPL-2.0-or-later
"""Observe the pinned original PHOTO menu raster, without guest state edits."""
from PIL import Image


def photo_menu(path):
    with Image.open(path) as im:
        if im.mode!='RGB' or im.size not in ((1024,682),(1280,800)):
            raise ValueError('Pinned Z9/ZR native RGB display required')
        if im.size==(1280,800):
            # Original ZR landscape UI has a 1200-pixel viewport centered
            # in the 1280-pixel panel; inspect that existing placement.
            im=im.crop((40,0,1240,800))
        w,h=im.size
        # PHOTO tab is green when a row owns focus, yellow when the sidebar
        # owns focus. The remembered row is respectively yellow or grey.
        green=[im.getpixel((int(w*x),int(h*y))) for x,y in
               ((.016,.020),(.080,.020),(.016,.090),(.080,.090))]
        sidebar=[im.getpixel((int(w*.005),int(h*y))) for y in (.25,.45,.75)]
        def yellow(c):
            r,g,b=c
            return r>150 and g>120 and b<100 and r>g>b*2
        selected=(all(g>60 and g>2*r and g>2*b for r,g,b in green) or all(yellow(c) for c in green))
        bands=[im.getpixel((int(w*.86),y)) for y in range(int(h*.11),int(h*.90),2)]
        highlighted=sum(yellow(c) or (max(c)-min(c)<4 and 100<c[0]<190) for c in bands)
        return selected and all(max(c)-min(c)<4 and 25<c[0]<65 for c in sidebar) and highlighted>=10
