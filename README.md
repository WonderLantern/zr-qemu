# WonderLantern ZR QEMU

[中文](README.zh-CN.md) · [Latest scope](docs/development-snapshot.md) · [Local inputs](docs/zr-inputs.md) · [Build](docs/build.md)

Experimental, source-only **Nikon ZR C1.11** emulator on QEMU10.2.4, reusing
the [WonderLantern Z9](https://github.com/WonderLantern/z9-qemu) shared146
EXPEED7 board. Independent research and learning; no Nikon firmware, private
code, ROM resources, fonts, calibration, SDKs or media are distributed.
Users provide their own compatible inputs locally. See NOTICE.md.

**This is a development snapshot. Camera H.265 Main10 and R3D recording are
not accepted or playable.** Original menus, landscape LCD, functional Bayer
live view, full-resolution photo transport and the functional lossless14 NEF
path have native research evidence. The current portable photo launcher passed two full 6064 x 4040,
14-bit NEFs, every one of 48,997,120 RAW samples, per-photo previews,
fresh live view and menu recovery in the same stopped session/card.
Other new options retain their bounded verification limits. See the detailed
[snapshot evidence and outstanding work](docs/development-snapshot.md).

## Build and run

Use Linux / Python3.12+, or explicitly select `ubuntu-noble-nikon` on this
project's Windows host. The separate `ubuntu-noble` coursework distro is
excluded. Build outputs should be on a Linux filesystem.

```sh
git clone https://github.com/WonderLantern/zr-qemu.git
cd zr-qemu
sudo apt-get update
sudo apt-get install build-essential ninja-build patch pkg-config python3-venv \
    libglib2.0-dev libpixman-1-dev zlib1g-dev libfdt-dev libjpeg-dev \
    libx265-dev libx264-dev exfatprogs
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python tools/build.py --work-dir "$HOME/wonderlantern-zr-build" --jobs 2
python tools/make_cmos.py --width 6016 --height 4016 --bits 14 \
    --output .local/zr-14bit.raw
python tools/run_zr.py --firmware /absolute/path/to/zr-main-payload.bin \
    --resources /absolute/path/to/private/captures --raw .local/zr-14bit.raw \
    --output "$HOME/wonderlantern-zr-runs/preview-001" --profile preview
```

Read [local input requirements](docs/zr-inputs.md) first. **The upgrade/main
payload alone is currently insufficient**: the native ZR profile consumes
private captured parameter/resource inputs. No tool fetches them. Missing
inputs fail explicitly; no firmware/resource download, flashing or camera
access is supplied. The profile pins their identities and retains the original
resource checks. Preview is a bounded scripted workflow that saves LCD images
locally; a ZR browser controller is not supplied by this snapshot.

`--profile photo` attempts repeated full RAW/photo/menu recovery; audit actual
card files and decode every sample independently. `--profile main10` and
`--profile r3d` reproduce current failed native VIDEO workflows. In VIDEO,
HALF focuses and held HALF+FULL starts recording; later FULL requests stop.
These profiles do not claim a movie exists when a START callback fires.
Orientation defaults to landscape and language to an explicitly recorded
English cached preference. ISO/shutter/UI rendering is the guest's own code.

## Layout and reuse

`qemu/` is byte-identical to the companion Z9 device overlay. ZR is a small
QOM subclass. `tools/run_zr.py`, `tools/zr/` and pinned JSON profiles are ZR
native peers; their addresses are not Z9 aliases. The inherited Z9 preview,
capture tools and older docs are retained as reusable Z9 reference tools;
use `tools/run_zr.py` for ZR. `tests/` runs firmware-free shared tests.

Do not commit any runtime output. `.local/` and `.build/` are ignored; prefer
external run directories. Read CONTRIBUTING.md before sharing evidence.
The source is GPL-2.0-or-later with retained upstream notices. Z7 is frozen.
Original ISP/DSP/H.265/RAW/JPEG, real lens/AF/PDAF, pre-capture/burst stability,
physical timing, full NeuPro specification and neural inference remain open.

当前 shared146 的共享输入/所有权模型、整轮录像失败结果及复用更正见 [shared146 notes](docs/shared146.md)。H.265／R3D 录像和原机算法仍未验收。


For an independently audited photo workflow, install optional decoding
dependencies and use the same launcher with `--profile photo --audit`:

```sh
python -m pip install -r requirements-capture.txt
python tools/run_zr.py --firmware /absolute/path/to/zr-main-payload.bin \
    --resources /absolute/path/to/private/captures --raw .local/zr-14bit.raw \
    --output "$HOME/wonderlantern-zr-runs/photo-001" --profile photo --audit
```

The result covers released repeated photos, not continuous burst or movies.
