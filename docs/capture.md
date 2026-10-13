# Full RAW capture and recovery

[中文](capture.zh-CN.md) · [Usage](usage.md) · [Validation](testing.md)

The capture command runs **one** original Z9 C5.32 shutter sequence, writes a
full-resolution NEF to a new virtual card, waits for newly produced live view,
and verifies two PHOTO-menu returns after the photograph. It reuses the
firmware's key decoder, capture tasks, file writer and original display.
The host does not create a replacement NEF or draw a replacement camera UI.

## Run the complete workflow

Install the normal build/Python dependencies, plus `libjpeg-dev` and
`exfatprogs`. `libjpeg` provides the emulator's functional baseline JPEG
encoder; `exfatprogs` formats a new regular-file virtual card and checks its
filesystem after shutdown. For independent RAW decoding:

```sh
python -m pip install -r requirements-capture.txt
python tools/build.py --work-dir "$HOME/wonderlantern-z9-build" --jobs 2
python tools/make_cmos.py --width 8256 --height 5504 --bits 14 \
    --output .local/z9-14bit.raw
python tools/capture.py --firmware /absolute/path/to/z9-main-payload.bin \
    --output "$HOME/wonderlantern-z9-runs/capture-001" --audit
```

Use `--image /path/to/your/photo.jpg` with `make_cmos.py` for your own scene.
The generator stretches/resamples RGB, removes the sRGB transfer curve,
samples RGGB and scales linear values to 0..16383. The resulting local input
is **90,882,080 bytes**: a 32-byte NZ9RAW1 header and 45,441,024 little-endian
u16 samples. The emulator packs 14-bit sensor/capture transport internally;
the input file itself is not packed RAW14. Floating-point intermediates are
bounded to 32 rows; full-size generation still needs several hundred MB.
Generate it before starting QEMU.

Provide your own compatible MAIN payload as described in [firmware.md](firmware.md).
Stop the browser preview process before running capture. Builds and captures
should use an ext4 Linux filesystem with several GB of available memory.
The output directory must not exist. A run creates an **8 GiB sparse card**;
its logical size is not its initial disk allocation. Saved images and derived
audit volumes still consume disk space. No existing card image or device is
formatted. Repeated experiments need new output directories.

`--seconds 600` is the default host deadline after boot. Guest key delays and
hardware events follow QEMU virtual time. Preparation, capture and recovery
can take several minutes; `--seconds` is a deadline, not a speed setting.
Create `stop.request` inside the active output directory to request a bounded
stop of that owned run. Interrupted runs are retained and fail acceptance.

The recipe in `tools/capture-profile.json` first wakes the shooting display,
uses original QUAL/dial and menu inputs to select the verified RAW capture
profile, then performs half/full/release contacts. It waits for completed
RAW and all three JPEG jobs plus new visible RAW-derived frames before
opening the first post-shot menu. It recognizes actual PHOTO-menu pixels,
returns through half-shutter, repeats, and finishes on fresh frames.
The advanced `capture_sequence.py` retains additional diagnostic switches;
only the supplied complete recipe is the accepted capture configuration.

## Outputs and independent verification

| Local output | What it establishes |
| --- | --- |
| `result.json` | Build/firmware/input fingerprints, consumed contacts, device acknowledgements, new frame counts and two actual post-shot menus |
| `capture-card.raw` | Card sectors actually written by the guest NVMe/file-writing path |
| `capture-card.audit.json` and catalog | Read-only filesystem check, unchanged source card and initialized file entry |
| `DSC_0001.NEF` and extraction receipt | Bytes read from the actual card file, without host substitution |
| `native-nef-audit.json` with `--audit` | LibRaw decode of every RAW sample, full producer-buffer comparison and byte-identical embedded JPEG previews |
| Screenshots and RAM/codec snapshots | Local evidence only; may contain firmware-derived data and must not be committed |

The NEF RAW descriptor is **8280×5520, 14-bit**. Its preview dimensions are
**8256×5504**, **1620×1080** and **160×120**. Full RAW geometry and main JPEG
geometry differ; LCD resolution is a third, separate interface. The small
640×480/12-bit preview fixture is not the capture geometry or a physical CMOS
interface specification. The verified host input is 8256×5504; the sensor
model resamples RGGB cells into the firmware's 8280×5520 capture request.
An 8280×5520 input is also admitted, but does not establish real border pixels.

Without `--audit`, capture still exports the actual NEF but has not passed the
full independent image oracle. Audit a stopped run later with:

```sh
python tools/export_card.py --output /path/to/capture-001
python tools/audit_native_nef.py --output /path/to/capture-001
```

The card exporter can verify an existing unchanged extraction. The pixel
auditor preserves earlier evidence; use `--audit-name another-audit` for a
new receipt. Its RAW comparison uses the actual guest producer, not the host
source file, so it checks saved-file integrity separately from sensor fidelity.
Tool success or a file entry alone is not complete camera acceptance.

## Hardware model and limits

The opt-in capture profile adds bounded sensor-frame DMA, packed-14 transport,
neutral in-place processing, generic cropped NV16 conversion, stream/thumbnail
resampling, functional libjpeg encoding, PCIe address translation, NVMe and
normal pending/mask/W1C acknowledgement. Completion follows actual data work.
It does not write guest task flags, return fabricated OS wait results, change
PC or patch firmware instructions. Read-only breakpoints observe lifecycle
and coordinate the incomplete external MCU/GPIO peer.

The CCOMP request-bound ACK and request/feedback GPIO lifecycle are necessary
to finish the original capture controller. Post-shot recovery also needs
correct source stop/refill and independently gated secondary-source timing.
Menus reached before image work finishes are not counted as post-shot menus.
See [architecture.md](architecture.md) for ownership and scanout behavior.

The NEF metadata and file structure are written by the user's firmware. The
model's RAW route is functional packed-14 transport. A TIFF Compression tag
of 34713 and successful LibRaw decoding **do not establish implementation of
Nikon's proprietary lossless/high-efficiency compression**. NR is a neutral
identity model; resampling, statistics, JPEG settings and sensor timing are
functional assumptions, not recovered factory algorithms or calibration.

This update does **not** establish movie start/stop, a playable recorded movie,
RAW pre-capture, burst stability, physical shutter behavior, AE/AF/PDAF or real
CMOS programming. `lcd.video_frames` means live-view scanout. REC/key delivery
does not prove recording. Firmware comparisons suggesting a RawRecord setting
for pre-capture remain a research direction, not a shipped feature.

ZR-specific source/ISP completion experiments remain default-off in the
shared board; they are not part of the accepted Z9 recipe and do not make ZR
supported by this repository. Z7 is unchanged.


## Current opt-in lossless14 / repeated-photo workflow

The shared136 snapshot also includes the newer two-photo workflow:

```sh
python tools/capture.py --firmware /absolute/path/to/z9-main-payload.bin \
    --raw .local/z9-14bit.raw --profile lossless14 \
    --output "$HOME/wonderlantern-z9-runs/lossless14-001" --audit
```

This drives two complete released-shutter/menu/live-view cycles. The open-source
F0 lossless14 entropy encoder consumes actual guest Bayer data; it is not
Nikon microcode, HE/HE*, continuous burst or pre-capture. `--audit` extracts and
independently decodes every actual NEF, matches every RAW sample and each
photo's completed JPEG jobs, and requires post-shot/menu recovery. The older
default compatibility profile remains one photo and is transport evidence;
its packed-size fallback is not F0 entropy-codec acceptance.

The research two-model whole-file result is described in the current snapshot.
The public host port must be qualified separately after substantive changes;
source compilation and synthetic tests do not establish native camera success.
ZR uses `tools/run_zr.py --profile photo` and its own private inputs. After a
stopped successful ZR run, audit `capture-card.raw` with the virtual-card helper,
save a read-only catalog, then run `tools/audit_repeated_capture.py --output RUN`.
