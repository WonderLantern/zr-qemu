# User-supplied ZR inputs

All inputs remain private. This source repository provides no payloads,
decryptor, keys, automatic firmware download, vendor SDK or extraction service.
It is a snapshot of a fingerprinted research configuration, not support for
arbitrary camera firmware. Runtime outputs can contain proprietary bytes.

MAIN payload: ZR C1.11, **88,157,349 bytes**, SHA256
`9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f`.
Supply its absolute local path through `--firmware`. Firmware is opened read-only.

Supply a local captures root through `--resources`, with these existing
private resource observations (the directory structure is checked by peers):

| Relative path | SHA256 / purpose |
| --- | --- |
| `base-bank-composite-20261009-01/a00000000-a16bff000.nonatomic-composite.bin` | `966d6f64d75aba3ba8e2b2fa289666ffb0db4321a66ba32f5c8be184ba725f87`; resource item/group metadata |
| `base-bank-composite-20261009-01/composite-manifest.json` | `410ce78505fbee1dbcb409380e8c63eac87327c7369f5230059b780f5bc34274`; verified received spans and gaps |
| `eg-extension-alias-20261009-01/000-e16c00000-e2a874400.bin` | `a65ef7a7732fc93cf8a61d09fb5d00beceb6fbd749b919a326d2b897e4286230`; captured resource content |
| `eg-extension-alias-20261009-01/result.json` | Receipt identifying the complete captured range, file, hash, received length and absence of holes |
| `nonlinux-dram-20261008-01/001-a02cc5000-a063de000.bin.partial` | Optional older display reconstruction input, hash `90b77eede9e0d3f285e0a9b307031dea0fa13dc051ff0798a25facdd45b9f41d`; not required when a profile uses complete group resources |
| `nonlinux-dram-20261008-01/result.json` | Optional display capture receipt |

These are local V1.10-derived observations supplied to the C1.11 research
profile, **not a complete flash dump or proof of cross-version calibration**.
Content is checked against C1.11 static resource descriptors. Missing or
mismatched resources are rejected; the repository does not supply substitutes
for these copyrighted/private data. If you do not own compatible observations,
you can build and run synthetic tests, but the current native profile cannot
reproduce its shooting UI from MAIN alone. A future portable per-resource
input format is open work. Do not upload captures to issues or PRs.

Profiles declare synthetic Flash padding/ENDM, external MCU/RTC/battery inputs,
audio silence and orientation. The English preference is a recorded cached
setting edit. No instruction patches, CPU redirection, fake OS wakeups or
forced recording success are used by the native runner.

CMOS input is `NZ9RAW1` RGGB/u16, generated locally by `tools/make_cmos.py`.
6016×4016/14-bit is a functional full-size ZR input convention, not a measured
physical link/protocol. The guest's RAW request geometry determines actual
capture output. To use a local photograph add `--image /path/to/image.jpg`.

The Z9 tools in the shared base remain Z9-bound and require Z9 C5.32 firmware;
they do not substitute for the ZR launcher or its separately pinned addresses.
