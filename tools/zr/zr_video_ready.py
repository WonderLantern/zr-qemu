# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only video readiness for external buttons; never an acceptance oracle."""
from PIL import Image


def visible_video_ready(path,raw,scanout):
    if (type(raw.get('video_frames'))is not int or raw['video_frames']<1 or
            scanout.get('enabled')is not True or scanout.get('active')is not True or
            scanout.get('last_frame_has_video')is not True or
            (scanout.get('width'),scanout.get('height'))!=(1280,800)):
        return None
    with Image.open(path)as im:
        if im.mode!='RGB' or im.size!=(1280,800):raise ValueError('Native landscape RGB PPM required')
        # Exclude the HUD and panel margins. Black startup covers and grey
        # warnings alone do not meet this coarse scheduling observation.
        colors=[im.getpixel((x,y))for y in range(160,680,40)for x in range(80,1200,40)]
    bright=sum(max(c)>60 for c in colors)
    chromatic=sum(max(c)-min(c)>12 for c in colors)
    if bright<len(colors)//3 or chromatic<len(colors)//4:return None
    return dict(classification='read-only host video visibility gate for external keys',
        video_frames=raw['video_frames'],sample_count=len(colors),bright_samples=bright,
        chromatic_samples=chromatic,guest_state_modified=False,
        scope='Source frame and visible colored scene; source identity, continuous video, recording and files require separate acceptance')


def visible_video_menu(raw):
    """Native English root menu: the selected left tab remains yellow even
    when the focused row is disabled and grey (audio sensitivity at OFF)."""
    from zr_key_sequence import menu_tab_matches
    return any(menu_tab_matches(raw,tab) for tab in range(7))
