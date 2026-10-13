# Debugging

Start with the local run directory and the pinned firmware/binary hashes.
`stderr.log` contains the first unknown hardware transaction. `result.json`
records input assumptions, transport checks, key inputs and final counters.
The latter may also contain proprietary RAM bytes; do not publish it wholesale.

If boot fails, inspect the first failure instead of the final black screen.
Record CPU, PC, LR, MMIO address, width and value. Identify the original writer,
the matching status reader and ISR, then determine who owns the pending bit.
Do not convert an unknown access into a generic zero read or immediate success.

The launcher owns QMP, qtest and GDB Unix sockets in a temporary directory.
Do not connect a second GDB client to the host peer's socket while it runs.
That peer relies on multiple original instruction boundaries and serialized
request/reply traffic. For a separate diagnostic client, build a dedicated
harness with explicit socket ownership and suspend peer servicing coherently.

Useful QOM properties include `raw-pipeline-state`, `engine1548-scanout-state`,
`engine1548-source-state`, `engine1518-state`, `engine151-control-state`,
`engine150c-state`, `serial-state` and `graphics-state`.

| Symptom | Inspect first |
| --- | --- |
| No RAW frames | Source gate, processing active state, complete output bank |
| RAW frames but black LCD | Submitted video addresses, video enable and alpha |
| Menu opens but no video on return | Source drain acknowledgement, reset and new start counters |
| Wait expires after command success | Whether any actual FIFO bytes were transmitted |
| Wrong no-card color | Pixel channel order at GPU output and LCD input |
| Missing black outline | Alpha/coverage handling; black is not automatically transparent |
| Slow interactive response | Host stop/capture frequency, growing logs, filesystem location |

CPU registers and guest RAM are observations, not a shortcut to readiness.
Use minimal bounded probes, preserve failed runs and label function-level tests
separately from whole-system behavior. The emulator has no supported VMState
snapshot/resume format; source commits and reproducible fresh runs are the
current recovery mechanism.
