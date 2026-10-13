# Running and controls

Generate input with `python tools/make_cmos.py`, then run:

```sh
python tools/run.py --firmware /path/to/main.bin \
    --output /your/linux/path/z9-run-001 --port 8789
```

The output directory must be new. Keep it local. The default is a timestamped
directory beneath `.local/`. Open `http://127.0.0.1:8789/`.

The controller starts with half-shutter held to keep the active capture path
running. MENU releases half-shutter and sends one MENU press/release pair.
The current firmware path can consume a first press without opening a menu;
if the shooting overlay remains, wait before pressing MENU again. Half shutter
hold returns from menus through the original firmware's key path. Release
releases half-shutter. All inputs are synthetic MCU messages; they do not
alter application state directly.

The browser receives PNG snapshots of QEMU's actual LCD surface. It does not
render its own ISO, shutter, menu, icons, no-card mark or video background.
The displayed RAW/LCD counters are diagnostic host state. Initial startup
takes time; the service waits for actual video production before showing ready.

The HTTP server binds only to loopback. It has no upload, shell execution,
firmware writing or remote-control endpoint. Do not expose it to a network.
The selected QEMU process and local Unix sockets are owned by this run;
Ctrl+C closes that run without attaching to another emulator.

For bounded acceptance use `--menu-test --headless --seconds 360`.
Startup and all three returns can take several minutes. `--seconds` measures
host time after boot; native key and acceptance delays use virtual time.
`--qemu /path/to/binary`
overrides the build manifest. `--raw /path/to/input.raw` selects a local RAW
input. `--menu-test` observes the native menu after a press and allows one
further press after ten seconds if it has not appeared. It requires three
returns with new RAW and LCD video frames and independent pixel comparison.
The supplied runtime profile has passed this acceptance; see
[recorded results](testing.md). Recovery uses a new process rather than QMP
warm reset. The MCU peer is still a bounded experimental implementation,
not an indefinitely validated camera service.

Input format: 32-byte header, `NZ9RAW1\0`, then six little-endian u32 values
for width, height, bits, CFA=0, black and white; remaining pixels are linear
RGGB unsigned 16-bit little-endian samples. Even dimensions are required.
12-bit or 14-bit values are stored in 16-bit words, not packed RAW12/RAW14. The sample generator
undoes sRGB transfer before Bayer sampling and uses a simple stretch to the
selected dimensions. This is a test fixture, not a physical sensor protocol.

For shutter release, a full NEF on a virtual card, fresh post-shot live view
and two post-shot menu returns, use the separate [capture workflow](capture.md).
The browser preview profile does not attach a card or expose full shutter/REC.
The capture profile uses full-size 8256×5504/14-bit host input (or 8280×5520), opt-in image/storage
models and a request-bound CCOMP MCU/GPIO peer. Do not combine it with another
running preview process or count LCD video as a movie recording.
