# shared138 development snapshot

This source update includes the current shared Z9/ZR board and the ZR
request-bound MCU status peer. It is a development snapshot: camera-written
H.265 Main10 and R3D recording are still incomplete. A qualified recording
release continues to require both formats, complete independent decoding,
two START/STOP cycles, fresh live view and menu recovery.

## Changes since shared136

- The optional `engine1543-retained-start-model` accepts START for a previously
  strictly accepted, now retired video header while adjacent configuration
  changes. Metadata and selected descriptor words must match the accepted
  program. Inactive stale descriptor words are ignored without changing their
  stored bytes. Cold, changed, active, held and owned-backend cases remain
  rejected. This changes header control only; pixel/DMA readiness is unchanged.
- The ZR `--battery-query-peer` repeats the declared boot status input only
  after an exact checked family4/type2 request. It does not acknowledge other
  commands or finish image, codec or task operations. The response was consumed
  by the original status handler in local native runs. Physical battery
  semantics remain unverified. This contract has not been established for Z9.
- Main10 and R3D profiles include these opt-ins and the corrected observation
  bindings. ZR keeps English, landscape and factory main-shutter VIDEO controls:
  held HALF+FULL starts and a later FULL stops; HALF alone focuses.

## Evidence and limits

The fingerprinted private shared138 build passed 214 header/geometry checks
across 60 stopped diagnostic guests. The separate status-peer contract passed
134 host checks and the factory shutter recipe passed 82 checks. Diagnostic
calls and successful control replies do not demonstrate native image delivery.
The standalone public package is rebuilt and checked separately; its build
fingerprint and current validation are recorded in `source-snapshot.json`.
The earlier standalone shared136 package checks remain historical evidence.

Current native Main10 run 513 times out at the second START after 98 input
states; R3D run 514 times out waiting for STOP after 82 input states. Both
owned QEMU processes exited, with zero codec image input, zero encoded
pictures and zero retained START events. The new guarded path has diagnostic
coverage but did not resolve these native recordings. No successful full native movie
or new full native photo qualification is claimed for this source update.
Earlier four-file lossless14 results cover their recorded research builds;
they are not automatically transferred to a new public binary.

Important identity correction: family4 request forwarding is MCU status
polling, not a CMOS/image DMA path. Some earlier source/acquisition hook names
were actually configuration or buffer-capacity queries. A returned success
value from these calls does not prove a frame reached the encoder. Unbound
observations are unobserved, not zero activity.

Original Nikon ISP, DSP, H.265, RAW compression and JPEG algorithms remain
unaccepted. The functional Bayer, FAST9/SAD, x265/x264, open-source lossless14,
WLVR/zlib and libjpeg paths are explicitly substitutes. WLVR is not REDCODE
or R3D. XM6 documentation is available locally, but its SDK/firmware version
equivalence remains unverified. Full NeuPro programming/arithmetic documents
are missing and local neural-network reproduction remains **inconclusive**.

## Inputs and publication

Users supply all compatible firmware locally. ZR additionally requires its
fingerprinted captured resources; MAIN alone is insufficient. Resources and
firmware are read-only inputs. The English preference is the documented
four-byte cache change, not a claim of untouched NVM.

The public repositories contain authored emulator/tools/docs and public
upstream material only. No Nikon firmware, decrypted proprietary code,
microcode, fonts, icons, calibration/resource bytes, vendor SDKs, photographs,
camera screenshots, recordings, virtual cards, raw traces or private Git
history are included. Z7 is unchanged. The publication audit checks inventory,
hashes and reachable history; it is not a legal opinion.


## Standalone public package checks

Both repositories independently ran the public builder; their 19 overlay
source hashes and resulting binaries match. The compiled binary is
`09b5406f045bbd32a306983955a419a3ea02cb623cc0f8ba4830e5c0f2863025`.
Z9 passed 13 Python tests; ZR passed 16, including malformed status requests
and all checked request/status byte boundaries. Both passed the C pixel
checks. Four firmware-free realizations cover both model identities with
the retained START option off/on and verify that it cannot change after
realization. The authored service-core program passed 13 checks and its
owned guest exited. These checks cover packaging and device contracts;
they do not qualify a complete native photo or movie workflow.
