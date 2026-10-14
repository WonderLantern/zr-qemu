# shared146 development snapshot

Both repositories now include the shared146b device implementation. The
shared C overlay is identical between Z9 and ZR; Z7 is unchanged. Compatible
firmware and ZR's fingerprinted captured resources remain user-supplied.
This snapshot contains authored source, tools and documentation only.

## Changes since shared144

Two new machine properties default to **off** and are immutable after
realization. Preview and photo recipes retain their previous option defaults.

| Property | Device contract and limit |
| --- | --- |
| `video-primary-boundaries-model` | After an owned internal RAW input and all six real Y/UV transfers, posts primary input/output causes. IRQ masks remain live; separate native W1C acknowledgements retire each cause. Pending ownership prevents buffer reuse, and reset cancels it. The combined physical stage/timing remains unverified. |
| `engine151-active-program-model` | An admitted ISP START retains its complete parameter-valid bitmap with its configuration. The running secondary route uses that accepted snapshot while a next program is prepared. New START still validates the new configuration completely; STOP, hold/reset, source ownership and output checks remain required. Physical register staging and Nikon ISP arithmetic are unverified. |

Read-only `video-primary-boundaries-state` reports pending causes, masks,
frames, acknowledgements and cancellation. `engine151-active-program-state`
separates `running_ready` from `next_start_ready` and shows admitted versus
current configuration. `video-secondary-sensor-state` additionally reports
the actual descriptor, clock, source and pending-ownership gates. A
write-only command register's zero readback is not proof that its gate is off.

ZR's `--profile main10` and `--profile r3d` select the updated experimental
recipes and enable these two options. The earlier failed C0/source0 END
experiments stay off. Factory VIDEO controls remain held HALF+FULL for START
and a later FULL for STOP; HALF focuses. ZR stays landscape with the documented
English cached preference. ZR native addresses are not qualified for Z9 VIDEO.

The read-only observer binds the original primary image events, preparation
wait/return and modulo-31 source wait. The modulo-31 wait uses a different
event object from the image preparation flags; equal bit values do not prove
equal ownership. Missing observation bindings mean unobserved activity.
Neither device model nor observer writes firmware PCs, task flags, OS return
values or successful callbacks.

## Verification and current native outcome

The exact private reference build passed **22 stopped QTest guests / 214
checks** across both model identities: 10/108 active-program checks and
12/106 primary-boundary checks. These compare actual input generations,
all six Y/UV spans and padding, strict next-START rejection, partial
acknowledgements, masks, held sources and incomplete outputs. They execute
no original firmware instructions and do not qualify camera recording.

One test correction is reusable: a deliberately invalid START requests QEMU
debug stop. A QTest-only negative fixture must explicitly verify that pause
and resume its dummy clock before testing a later valid request. The model
does not automatically resume native faults or weaken admission rules.

The unchanged original ZR firmware completed both latest bounded experiments.
Main10 timed out at the second START (state98); R3D timed out waiting for STOP
(state82). Both owned guests exited and reported **zero codec image input and
zero encoded pictures**. R3D advanced beyond its previous three-input stall:
during the first REC interval its original preparation task and frame-bridge
entry executed nine times, but the bridge's enable field remained zero.
This is partial pipeline progress, not an encoded movie or R3D acceptance.

Full two START/STOP cycles, real card files, independent whole-movie decoding,
fresh live view and menu recovery remain required. Historical repeated-photo
and lossless14 results retain their original build scopes. The new public
binary has not been requalified with a complete native photo/movie workflow.
Current public build and firmware-free checks are recorded in
`source-snapshot.json`; private raw evidence is not published.

## Algorithm and publication boundaries

Original Nikon ISP, DSP, H.265, RAW compression and JPEG remain unaccepted.
Functional Bayer processing, FAST9/SAD, x265/x264, open F0 lossless14,
WLVR/zlib and libjpeg are substitute backends. **WLVR is not REDCODE/R3D.**
XM6 documentation exists locally, but SDK/firmware version equivalence is
unverified. Full NeuPro documentation is missing and local neural-network
reproduction is **inconclusive**.

A qualified recording release still requires both H.265 Main10 and R3D.
This is an explicitly requested source development snapshot. Firmware,
decrypted proprietary code, microcode, ROM/resource/calibration bytes,
fonts/icons, vendor SDKs, user photographs, screenshots, recordings, cards,
raw traces and private Git history are excluded. Publication auditing checks
the reviewed inventory and reachable blobs; it is not a copyright oracle.

## Public package validation

Both build entrypoints used the same verified upstream cache. All 19 overlay
and 16 compiled-source hashes and the output binaries match:
`e2946a488e90cb7fc022acb575c81ea8fb5acdd9c2ad5ac54e0e544791966c2f`. This package passed 16
Python tests, C pixel checks, four stopped-CPU two-model realizations with
96 default/off/on/immutability checks and 13 authored service-core checks.
No Nikon firmware was executed by these public package checks.

## Host log-read correction

A current public Z9 two-photo run exited on host `ENODATA` while reading its
append-only QEMU log on the Windows-mounted workspace. The shared host guard
now scans a finite append snapshot in 64 KiB chunks, retries only transient
ENODATA/EAGAIN/EINTR within a bounded second, and reopens at the last committed
byte offset. Failed reads cannot skip consumed fault-marker bytes; split
markers remain detectable. Persistent unavailability, other errors, log
truncation and unexpected EOF still abort. This changes host file handling;
QEMU devices, firmware, clocks and camera success conditions are unchanged.

Eight fault-integrity tests cover partial-consumption errors, bounded chunks,
split markers, persistent failure, unrelated errors, cursor-preserving reopen,
concurrent append and truncation. Full Python suites now pass 21 tests in Z9
and 24 in ZR. This host correction does not qualify the camera workflow;
the actual two-photo/full-file/menu/live-view rerun remains separate.
