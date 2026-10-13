# Contributing

Keep changes source-only. Never attach firmware, extracted program bytes,
keys, memory/flash dumps, private photographs, calibration, embedded fonts,
icons or original camera UI screenshots. Local run JSON can contain original
RAM bytes and is not suitable for an issue attachment without manual review.

Report the firmware fingerprint, emulator commit, explicit model options,
operation sequence, numeric counters and a concise description of the failure.
Use synthetic test inputs. A register address or status observation is useful;
an entire proprietary dump is unnecessary.

For a new device behavior, explain the observed producer, consumer, access
width, mask, IRQ routing and acknowledgement. Identify modeling assumptions.
Test masking, partial W1C, reset, stop/restart and rejected operations where
they affect the change. Do not return success from an unimplemented operation
merely because the guest waits for it.

Add a new model/version profile rather than silently reusing Z9 bindings.
Do not modify the frozen Z7 repository. Public CI must work without firmware.
Update the publication allowlist/manifest only after reviewing new content and
its origin, then audit every reachable Git blob before pushing.
