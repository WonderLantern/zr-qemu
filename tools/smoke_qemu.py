# SPDX-License-Identifier: GPL-2.0-or-later
"""Realize the board with a synthetic zero input and CPUs stopped."""
import argparse,json
from pathlib import Path
import subprocess,tempfile

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('binary',type=Path);a=p.parse_args()
    with tempfile.TemporaryDirectory() as folder,tempfile.TemporaryFile() as errors:
        stub=Path(folder)/'synthetic-zero-input.bin';stub.write_bytes(bytes(4))
        proc=subprocess.Popen([str(a.binary.resolve()),'-M','nikon-z9-lab','-kernel',str(stub),
            '-smp','4','-display','none','-serial','none','-monitor','none','-S','-qmp','stdio'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True)
        requests=''.join(json.dumps({'execute':x})+'\n' for x in ('qmp_capabilities','query-status','quit'))
        try:output,_=proc.communicate(requests,timeout=30)
        except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
        messages=[json.loads(x) for x in output.splitlines()]
        states=[m['return'] for m in messages if isinstance(m.get('return'),dict) and 'running' in m['return']]
        if proc.returncode or any('error' in m for m in messages) or len(states)!=1 or states[0]['running']:
            errors.seek(0);raise RuntimeError(errors.read().decode(errors='replace'))
        print(json.dumps(dict(passed=True,proprietary_firmware=False,cpu_execution=False,machine='nikon-z9-lab')))

if __name__=='__main__':main()
