# SPDX-License-Identifier: GPL-2.0-or-later
"""One explicit missing-ROM selector input for the Z9 capture experiment.

Selects the same placeholder record used by the preview input. The original
firmware must copy/consume it. No RAM/CPU/error flag changes are made, and the
record coefficients remain missing. This cannot establish capture geometry.
"""
import json
from pathlib import Path
from probe import sha


def attach(g):
    firmware=g.firmware
    if sha(firmware)!='6380ded18395ce11cb327c766721274c85127d2cf1a1e887ee60e3d156810bdd':
        raise ValueError('pinned Z9 firmware required')
    file=g.out/'diagnostic-capture-selector2.bin';file.write_bytes(b'\x01')
    record=dict(classification='explicit missing-ROM selector input; not recovered calibration',
        address='0x47f5af42',bytes=1,hex='01',selector=2,selected_record=1,
        source_sha256=sha(Path(__file__)),input_origin='explicit synthetic selector; not factory calibration',file=file.name,sha256=sha(file),
        original_firmware_unchanged=True,guest_ram_patch=False,cpu_patch=False,
        physical_calibration=False,geometry_verified=False,camera_acceptance=False,
        scope='Select placeholder record1; record body remains missing. Original copy/lookup must be observed.')
    (g.out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    (g.out/'capture-processing-input.json').write_text(json.dumps(record,indent=2)+'\n')
    g.command+=['-device',f'loader,file={file},addr=0x47f5af42,force-raw=on']
    g.data['capture_processing_selector_input']=record
