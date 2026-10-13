# Service-core events and the runtime clock

This is an optional functional scheduling model for the Z9 C5.32 service
core. It is not a general implementation of ARM event architecture or a
measurement of EXPEED timing. `service-core-event-model` defaults to off in
the board. The supplied camera profile enables it with four CPUs,
single-thread TCG and `-icount shift=0,sleep=on`.

## Why the model exists

Upstream QEMU 10.2.4 treats AArch64 WFE as a yield in single-thread TCG and
as a hint in parallel TCG. The service core repeatedly checks a mailbox
around WFE. With instruction counting, this busy loop can prevent idle
clock advancement and severely delay useful work. With the earlier parallel
profile, MENU return was also unstable: native frame release could precede
construction, followed by a terminal runtime loop. Merely moving periodic
inputs to virtual time passed one run and failed on the next cold boot.

The current profile combines the service-core wait model, instruction time,
virtual-time external status/key delivery and nonzero synthetic timing ROM
inputs. Successful runs validate this combination. They do not prove that
any single change independently repairs all observed lifetime failures.

## Implemented contract

- Only CPU3 can block at AArch64 WFE. CPU0–2 keep upstream WFE scheduling;
  all four CPUs can send SEV. SEVL affects only its sender.
- An event delivered before WFE is retained. Repeated events coalesce.
  A waiting CPU consumes a new event and resumes without a fabricated guest
  IRQ. An ordinary interrupt also wakes it through QEMU's existing path.
- SEV does not wake a CPU waiting in WFI. Event state is part of the CPU's
  reset-cleared fields, while the board's opt-in configuration is retained.
- The board rejects enabling this model without four CPUs and instruction
  counting. Runtime changes to this startup option are rejected.
- `runtime-clock-state` is read-only. It reports virtual time, run state,
  CPU halt state and event sleep/wake counters. It never advances time.

The CPU patch modifies only upstream QEMU code. It contains no Nikon code,
guest instruction replacement, PC redirection, OS flag write or changed
firmware timeout. Build preparation verifies the patch in both fresh and
already-applied source trees and rejects unexpected partial states.

Exclusive-monitor events, AArch32 event instructions, migration, measured
latencies and general multicore event correctness are outside this model.
Whole-board warm reset is unsupported: QMP `system_reset` has not reproduced
a cold boot. Start a new emulator process for acceptance or recovery.

## Input clocks and timing assumptions

The external boundary peer uses QEMU virtual time, with a 33 ms minimum
interval. Host polling can delay delivery; missed periods are dropped rather
than replayed in a burst. Paused virtual time cannot create new inputs.
The first 4,096 delivery records are saved, while total counters and delivery
continue after that recording limit. Automatic MENU key spacing and MENU
acceptance durations use the same virtual clock. Browser capture and the
`--seconds` run bound remain host-time operations.

`tools/z9_timing_input.py` creates two two-byte ROM inputs with a coefficient
of 1,200. The original arithmetic interprets it as 16.667 microseconds per
line. This is a chosen functional input for two observed selectors, not
recovered calibration or a claim about physical sensor timing. The original
duration calculation and waits remain intact. Input bytes and hashes are
recorded in each private run directory.

## Reproducing validation

After building, run the firmware-free execution test:

```sh
python tools/check_service_events.py \
  --qemu /your/build/build/qemu-system-aarch64 \
  --output /your/private/run/service-events
```

Its 100-byte AArch64 program is authored here and assembled from documented
instruction encodings. Thirteen checks cover cold event state, retention,
coalescing, blocking, repeated SEV, SEVL, IRQ wake and WFI isolation. No
Nikon firmware is needed. Output directories must be new.

Camera acceptance remains separate. Use your compatible local firmware with
`tools/run.py --menu-test --headless --seconds 360`. It requires three native
MENU returns, new RAW and LCD frames after each return, and independent
NV12-to-LCD comparisons. See [testing](testing.md) for actual run outcomes.
CI's synthetic tests cannot establish camera UI acceptance.
