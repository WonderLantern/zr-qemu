# SPDX-License-Identifier: GPL-2.0-or-later
"""Portable source snapshot runner; local firmware and private ROM inputs required."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--firmware',type=Path,required=True)
    p.add_argument('--resources',type=Path,required=True,help='Private captured-resource directory; see docs/zr-inputs.md')
    p.add_argument('--raw',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--profile',choices=('preview','photo','main10','r3d'),default='preview')
    p.add_argument('--seconds',type=int,choices=(10,20,30,60,90,180,360,600,900),help='Override the native profile observation duration')
    a=p.parse_args()
    if os.name=='nt' or os.environ.get('WSL_DISTRO_NAME')=='ubuntu-noble':p.error('Use Linux or explicitly selected Nikon WSL')
    output=a.output.resolve()
    if output.exists():p.error('Use a fresh output directory')
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT/'.local'):p.error('Repository runtime outputs must be inside ignored .local/')
    firmware=a.firmware.resolve();resources=a.resources.resolve();raw=a.raw.resolve()
    if not firmware.is_file() or not raw.is_file() or not resources.is_dir():p.error('All three local input paths must exist')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',output.name):p.error('Use a simple output directory name')
    manifest=json.loads((ROOT/'.local/build-manifest.json').read_text())
    work=Path(manifest['binary']).resolve().parents[1]
    names=dict(preview='zr-native-preview.json',photo='zr-native-lossless14-repeated-raw-whole.json',
        main10='zr-native-functional-main10-running-isp-recording.json',r3d='zr-native-functional-r3d-running-isp-recording.json')
    profile=ROOT/'tools/zr/profiles'/names[a.profile]
    options=dict(json.loads(profile.read_text())['arguments'],name='zr-'+output.name,
        raw_input=str(raw))
    if a.seconds is not None:options['post_seconds']=a.seconds
    if options.get('lifecycle_observer'):options['lifecycle_observer']=str(profile.parent/options['lifecycle_observer'])
    env=dict(os.environ,WL_ZR_FIRMWARE=str(firmware),WL_ZR_RESOURCES=str(resources),
        WL_ZR_OUTPUT=str(output),WL_ZR_WORK=str(work),PYTHONDONTWRITEBYTECODE='1')
    argv=[sys.executable,'-B',str(ROOT/'tools/zr/probe_zr_mcu.py')]
    for key,value in options.items():
        if value is None or value is False:continue
        argv.append('--'+key.replace('_','-'))
        if value is not True:argv.append(str(value))
    print('Experimental '+a.profile+' workflow; video start callbacks are not recording acceptance.',flush=True)
    completed=subprocess.run(argv,env=env)
    print('Private run output: '+str(output),flush=True)
    raise SystemExit(completed.returncode)

if __name__=='__main__':main()
