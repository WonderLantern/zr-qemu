# Research and rights notice

WonderLantern develops this independent emulator for research and learning.
Nikon has not sponsored, endorsed or supplied this project. Nikon and Z9
identify the interoperability target; their owners retain their rights.

We respect Nikon's rights and do not publish its private code. This repository
distributes original emulator/tool source and the accompanying open-source
license notices. Users provide their own compatible local firmware. A source
license here does not grant rights to Nikon firmware or other third-party
material. Firmware-derived local files are excluded from publication.

No camera updater, flashing tool, USB memory access or physical-device payload
is included. The model is incomplete and its synthetic inputs must not be
mistaken for recovered factory data or a hardware specification.

The overlay/tools use GPL-2.0-or-later. QEMU retains its upstream licensing;
see COPYING and LICENSES/QEMU-LICENSE.txt. No proprietary firmware is relicensed
under the source license.

The lossless14 functional encoder retains Copyright (C) 2026 RdWing and GPL-2.0-or-later, adapted from RdWing/z8-qemu. Public x265/x264 encode diagnostic data and are not Nikon/RED implementations. No RED, Resolve, CEVA or NeuPro SDK or private code is included.

## Public HE inverse and authored forward codec

`qemu/nikon-he-public/` retains the copyright of its public LibRaw authors,
including Dmitri Sotnikov. It is pinned to commit
`499bfd4cbf802c2fb5eac4c9a6f53bbeb776cad1` from the public LibRaw PR826 work.
The upstream files offer LGPL2.1 or CDDL1.0; this integration selects
**LGPL version 2.1**. Complete license texts, baseline/source hashes, dated
modification notices and reproducible patches are included. The functional
forward encoder and C API bridge are authored GPL-2.0-or-later code. The
bridge uses a public integer transfer rather than the unused approximate
breakpoint-table endpoint path. No installed RED decoder, camera microcode,
firmware, SDK or source image is linked or distributed. Compatibility does
not imply Nikon/RED endorsement or original algorithm equivalence.
