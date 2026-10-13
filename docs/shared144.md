# shared144 development snapshot

This updates both public source packages from shared138 to shared144. The
shared board, Bayer input writer and pixel adapter are identical between the
Z9 and ZR repositories. Z7 is unchanged. Users supply compatible firmware
and, for ZR, the separately fingerprinted captured resources. MAIN alone is
insufficient for the current ZR runner. No private inputs are distributed.

## Changes and opt-ins

The new machine properties default to **off**. They are functional research
models, not a complete physical EXPEED specification or original ISP code.

| Property | Behavior and limit |
| --- | --- |
| `video-secondary-isp-model` | Adds a bounded second-ISP route using checked original geometry, source gates and owned RAW input. It writes the six submitted YUV output spans using the functional pixel adapter. |
| `video-secondary-sensor-model` | Supplies a fresh, independently owned CFA-resampled input after the earlier receiver/decoder has retired. Source clock, descriptor, gates and pending ownership remain required. It does not restart a retired decoder or recycle its previous frame. |
| `video-secondary-source-end-model` | Counts three completed secondary input/output transfers, then posts an independently acknowledged source1 END. END blocks reuse until the original acknowledgement; reset cancels pending ownership. The physical grouping and timing remain unverified. |
| `video-receiver-before-supplier-model` | Allows a completely configured receiver to arm while its supplier is configured but not yet enabled. Actual pixel output still requires supplier enable and a real owned input. Pause/resume retains the pending input. |
| `video-yuv-output-events-model` | Earlier experimental C0 completion/ownership model. Diagnostic coverage exists, but its native recording experiment failed. It stays off in the current VIDEO recipes. |
| `video-source-end-model` | Earlier source0 END experiment. Its assumed native client was not established; it stays off in the current VIDEO recipes. |

ZR's `--profile main10` and `--profile r3d` now select the shared144 experimental
recipes. They enable the secondary route/sensor/END and receiver-order models;
the earlier C0/source0 experiments remain off. These are reproduction tools
for an **incomplete** native movie workflow, not playable recording features.
The preview/photo defaults do not enable these new video options. ZR keeps
landscape, the documented English cached preference, and factory VIDEO
controls: HALF focuses; held HALF+FULL starts; a later FULL requests STOP.
ZR addresses and bindings have not been established for Z9 movie operation.

## Validation and native outcome

The private shared144 build passed 34 receiver-order/data-path checks in 10
stopped diagnostic guests across both model identities. Earlier shared143
passed 114 secondary-END checks in 10 guests; shared142 passed 66 new sensor
checks in 10 guests. These counts remain bound to their own builds; they are
not summed into a claim of current full camera qualification. The public
packages are independently rebuilt and tested; their current build and
validation are recorded in `source-snapshot.json`.

The unchanged original ZR firmware was also run through both complete native
VIDEO recipes on shared144. Main10 reached the original START notification
and first STOP, but timed out at the second START (input state98). R3D timed
out waiting for STOP (state82). Both owned guests exited. Both had **zero
codec image input and zero encoded pictures**; neither workflow is accepted.
The full two START/STOP cycles, real card files, complete independent movie
decoding, fresh live view and menu recovery remain required for acceptance.

Earlier native secondary-input audits matched all 20,811,648 samples of a
6064 x 3432 modeled input against independent CFA-cell resampling. This proves
that modeled input's content only. It does not establish the sensor's physical
wire format, a frame reaching the codec, movie recording or original ISP math.
Older repeated-photo/lossless14 acceptance remains scoped to its recorded
research builds; the new public binary has not been fully requalified with
native photo or movie inputs.

The read-only lifecycle observer now supports a declared 64..65536 record
limit and optional, counted X0 filters. The current movie recipes use 32768
records, 64 points and eight bounded memory regions with no periodic filter.
It observes both the generic and alternative frame bridges. A missing binding
is unobserved, not zero activity. Filtered, dropped and recorded events remain
separate, and the observer never changes guest execution or task results.

## Corrections useful for other models

A source-group function formerly named "frame group submit" programs source
DMA buffer tables and bank selection. Calling or returning from it is not
proof that a frame was processed or handed to a movie queue. Its enabled
branch, actual buffer destinations, frame queue ingress and codec picture
submission must be checked separately. The alternate RAW frame bridge's name
also does not prove REDCODE/R3D encoding. The retained table roles and complete
source DMA delivery remain under investigation; no guessed callbacks or
success values are substituted into the firmware.

Model identities, firmware fingerprints, buffer layouts and IRQ clients must
be established per sample. Shared C device code is reusable; ZR's native
firmware bindings must not be copied into a Z9 or another model profile.
The current reusable boundary is the authored device/ownership implementation,
portable build, explicit input contracts, and evidence-aware observation.

## Original algorithms and publication

Original Nikon ISP, DSP, H.265, RAW compression and JPEG remain unaccepted.
Functional Bayer processing, FAST9/SAD, x265/x264, open-source F0 lossless14,
WLVR/zlib and libjpeg are explicitly substitute backends. WLVR is not REDCODE
or R3D. Local XM6 documentation is available, but SDK/firmware version
equivalence is unverified. Full NeuPro programming/arithmetic documentation
is missing and local neural-network reproduction is **inconclusive**.

This is a source development snapshot. A qualified recording release still
requires both H.265 Main10 and R3D to pass. Firmware, decrypted proprietary
code, microcode, ROM/resource/calibration bytes, fonts, icons, vendor SDKs,
photographs, camera screenshots, recordings, cards, raw traces and private
Git history are excluded. The inventory/history/blob audit checks unintended
publication; it does not substitute for provenance review or a legal opinion.


## Current public package checks

Both repository build entrypoints were executed against the same verified
upstream build cache. Their 19 overlay hashes, 16 compiled-source hashes and
resulting binaries match: `8450a987ea4b376f4a9c751de9c017ca8314c02896202c609f7af7040f3d9533`.
Z9 passed 13 Python tests and ZR passed 16; both passed the C pixel checks.
Four firmware-free, stopped-CPU realizations cover both models with all six
new video options off/on: 72 checks verify defaults, explicit values and
post-realization immutability. The authored service-core guest passed 13
checks and exited. The ZR runner help, current observation profile validation
and observer compilation with warnings as errors also passed. These checks
qualify packaging and these contracts only, not full native photo or movies.

Reproduce the option checks after building:

```sh
python tools/check_video_options.py --qemu /absolute/path/to/qemu-system-aarch64 \
    --output .local/video-options-new.json
```

Use a fresh output filename. The CI runs this firmware-free check for each
source change; no Nikon input is fetched or distributed.
