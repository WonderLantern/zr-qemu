# Building

Use Linux with Python 3.12+, GCC/Clang, Ninja, patch, pkg-config, GLib, Pixman, zlib
and libfdt/libjpeg development headers. Install `exfatprogs` for the capture
workflow and the optional `requirements-capture.txt` for independent NEF
decoding. Install the Python dependencies from
`requirements.txt` in a virtual environment. See the README for Ubuntu commands.

`python tools/build.py --work-dir /your/linux/path --jobs 2` downloads only
the upstream QEMU 10.2.4 source archive, validates its SHA-256, extracts into
that work directory, installs the source overlay and builds AArch64 TCG.
It writes `.local/build-manifest.json` with the binary and source hashes.

For an existing upstream archive use `--archive /path/qemu-10.2.4.tar.xz`.
The required archive SHA-256 is
`821b545b92f165e57dddccac5077d76d4d436a226595b8813ad59306bbfd0746`.
No Nikon file is downloaded. Configuration may need network access for
QEMU's Python build dependencies; an archive alone does not guarantee a fully
offline first build. Subsequent builds reuse the verified source/build tree.

Use an ext4 Linux path for builds and long runs. Windows-mounted paths can be
slower for the many small files produced by diagnostic peers. On Windows:

```powershell
wsl -d ubuntu-noble-nikon --exec bash
```

Then enter the cloned directory under `/mnt/d/...` and run the Linux commands.
The tools neither create nor select a default WSL distribution. They explicitly
reject `ubuntu-noble`, reserved for unrelated coursework in the development
environment. Linux installations without WSL work normally.

Start with two build jobs if host memory is tight. Stop only the emulator
process you own before replacing its binary. Do not kill unrelated workloads.
The machine reserves several inferred guest RAM windows; resident memory and
host commit use are different. Leave several GB available for QEMU and Python.

`qemu/prepare_source.py` requires the verified extraction marker and the exact
upstream version. It adds this board and QEMU's generic ROM loader, and applies
a narrow TCG GDB fix for global SMP breakpoints: removal visits every vCPU,
ignores `ENOENT` on an individual vCPU, and succeeds only if at least one copy
was removed. A fully absent breakpoint remains an error. This keeps the MCU
observer's breakpoints consistent across the four emulated CPUs. It does not
install a kernel/guest OS image. The separate optional
[service-core event patch](service-events.md) adds limited AArch64 WFE/SEV
behavior, enabled only by the explicit board option. Its source hash is
included in the build manifest. Repeated preparation verifies the applied
patch; an unexpected or partially patched upstream source is rejected.

The capture build also selects upstream DesignWare PCIe, NVMe and its required
SPDM socket support, and links the authored JPEG adapter against system
libjpeg. `qemu/designware-dma.patch` bounds ATU windows above 4 GiB using the
base-high and limit-low fields; it does not provide a physical PCIe PHY or
camera identity. The board exposes only its explicit DMA apertures. All
overlay headers and upstream patches are fingerprinted in the build receipt.

The shared136 overlay also requires public `libx265-dev` and `libx264-dev`. Both machines are built from the same shared board source. No proprietary codec SDK is used. See [snapshot](development-snapshot.md).
