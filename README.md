# WonderLantern ZR QEMU

**2026-10-23: shared441 development source update.** See [current changes, whole-workflow evidence and limitations](docs/shared441.md) for 1/1000 bursts, ZR Main10/R3D, the receiver fix and the still-failing pre-release path. This portable rebuild does not inherit older camera qualifications. Bring your own firmware; original ISP/DSP/codec algorithms remain unimplemented.

## Historical shared221 and earlier usage/qualification


[Historical shared221 ZR recording qualification / 旧版录制验收](docs/recording-qualification221.json)

[中文](README.zh-CN.md) · [Results and limitations](docs/shared221.md) · [Local inputs](docs/zr-inputs.md) · [Build](docs/build.md) · [Rights and licenses](NOTICE.md)

Experimental **Nikon ZR C1.11** emulation on QEMU10.2.4, sharing the EXPEED7
device implementation with [WonderLantern Z9](https://github.com/WonderLantern/z9-qemu).
Original ARM menus, the shooting HUD, landscape LCD, shutter contacts and
file writing run from user-supplied firmware. Research and learning only;
Nikon/RED do not sponsor or endorse this project.

**Bring your own compatible firmware and resources.** This repository contains
authored/open-source code, licenses, profiles and documentation. It supplies
no firmware, decrypted proprietary program, ROM/calibration/font/icon payload,
SDK, source photograph or recorded movie. MAIN alone is currently insufficient:
the native profile also needs the user's fingerprinted captured resources.
Read [exact local input requirements](docs/zr-inputs.md) before building a
native camera workflow. Missing inputs fail explicitly.

## Historical shared221 recording results

| Format, original C1.11 application | First clip | Second clip |
| --- | --- | --- |
|4K HEVC Main10,29.97fps|909frames /30.3303s|909frames /30.3303s|
|6K R3D NE,59.94fps|1803frames /30.08005s|1806frames /30.13010s|

The same local shared221 build passed two START/STOP pairs and two fresh
MENU/live-view returns for each format. All1818Main10 frames,3609RAW packets
and3609AVC proxy frames were checked. Independent RED rendered first/middle/last
of both original R3D containers. The input picture is static: duplicate RAW
frames reuse one independently decoded full frame only after complete byte
identity. Public-package native regression is reported separately in the
source snapshot; a build or START callback alone never qualifies recording.

**Arithmetic remains functional.** HE is authored forward coding plus a pinned
public LibRaw inverse; HEVC/AVC use x265/x264; ISP/JPEG use functional host
implementations. Original Nikon ISP/DSP/codec algorithms are not executed or
qualified. R3D dark/color clipping is uncalibrated. The shared221 Main10 source
has8bit-effective precision even though the actual HEVC syntax is10bit.
See [complete scopes, tests and remaining work](docs/shared221.md).

## Build

Use Linux, Python3.12+, C/C++17, GDB and a Linux build filesystem. On this
Windows research host select `ubuntu-noble-nikon` explicitly; the coursework
`ubuntu-noble` distribution is excluded. Keep runtime output outside tracked
source. Standard two-clip R3D output needs about28GB plus evidence/headroom;
plan at least40GiB free, or install/use the optional lossless card storage.

```sh
git clone https://github.com/WonderLantern/zr-qemu.git
cd zr-qemu
sudo apt-get install build-essential ninja-build patch pkg-config python3-venv \
    libglib2.0-dev libpixman-1-dev zlib1g-dev libfdt-dev libjpeg-dev \
    libx265-dev libx264-dev exfatprogs
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python tools/build.py --work-dir "$HOME/wonderlantern-zr-build" --jobs 2
```

The builder checks the original upstream archive and every declared overlay,
builds the functional C++ codec archive and links it into both board identities.
It does not fetch camera firmware or a vendor SDK. The public inverse retains
its LGPL version2.1/CDDL notices, dated changes and pinned-source receipts.

## Supply CMOS input and run

The synthetic source is local `NZ9RAW1` RGGB/u16. Its14bit/full-frame convention
is not a measured CMOS wire protocol. To derive Bayer from your own photograph:

```sh
python tools/make_cmos.py --width 6016 --height 4016 --bits 14 \
    --image /absolute/path/to/your-image.jpg --output .local/zr-14bit.raw
python tools/run_zr.py --firmware /absolute/path/to/zr-main-payload.bin \
    --resources /absolute/path/to/your-compatible/captures \
    --raw .local/zr-14bit.raw --output "$HOME/zr-runs/preview-001" --profile preview
```

Use a fresh `--output` directory every time. Profiles save original LCD images,
input-consumption receipts and a private virtual card; run output may contain
proprietary data and must stay local. This launcher is scripted; a ZR browser
controller is not yet provided. English is an explicitly recorded cached
preference and orientation defaults to landscape.

For recording, change to `--profile main10` or `--profile r3d` and a fresh output.
Each profile selects VIDEO, performs two complete30-second recordings, then
two menus and fresh returns. HALF focuses; held HALF+FULL starts, a later FULL
stops. The camera firmware renders ISO/shutter and its own graphics.
`video-recording-live.json` reports current encoded pictures; boundary snapshots
and quiet card writes can be stale/buffered. Let the complete workflow finish.

Optional `--deduplicated-card` uses lossless SQLite4KiB page sharing on a private
FUSE file, keeping actual guest-written bytes. Install your distribution's
libfuse2 and Python fusepy first. Keep the initial image/database/service receipt
together for later remount; [storage details](docs/shared221.md#storage-and-progress-lessons)
explain limitations. This never opens a physical SD/CFexpress card.

`--profile photo` retains the experimental repeated-photo path;
`--audit` currently audits photos only. Full held-burst recovery remains open.
After a recording exits, read the actual `private_virtual_card.path` in
`result.json`. Export original files with the exFAT helpers, then independently
decode the entire movie. The inherited Z9-only `tools/export_card.py` expects
one NEF and is not a movie auditor. R3D needs a compatible independent decoder
such as a licensed installed RED/Resolve implementation. No such decoder is
redistributed here. See [verification](docs/shared221.md).

## Reuse and limitations

Both repositories contain the same board/header sources and codec archive.
ZR is a small QOM subclass; its native control/observer profiles remain
fingerprinted to C1.11. Z9 addresses are not ZR aliases, and C1.10 recording
is not qualified by C1.11 evidence. Original algorithms, calibrated AE/AF/PDAF,
physical SD/CFE identity, pre-capture, complete burst recovery and indefinite
stability remain open. Detailed NeuPro documentation is missing; local neural
reproduction is inconclusive. Z7 stays frozen.

Run `bash tests/run.sh` for firmware-free tests and pixel checks. The two-model
option/service checks use stopped authored CPUs, never original camera
instructions. Read CONTRIBUTING.md before sharing any research output.
