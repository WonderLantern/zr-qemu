# Reusable research notes

## Separate claims

An unpacked program, a running RTOS, a drawn menu, a delivered RAW buffer,
processed output and visible LCD pixels are different milestones. Record the
sample hash, machine options, synthetic inputs and observation method for each.
Function emulation that seeds RAM and redirects PC can test a packing rule;
it cannot establish ordinary startup or camera behavior.

The [full RAW capture update](capture.md) adds further separate milestones:
original key consumption, controller completion, producer/codec completion,
initialized card sectors, extracted NEF, independent whole-image decode,
fresh post-shot frames, actual post-shot menus and returned frames. The
accepted Z9 workflow checks all of these; REC input and LCD video counters
still cannot establish a saved movie or RAW pre-capture.

Host scene size, requested sensor transport size, cropped JPEG size and LCD
size are different contracts. The accepted host source is 8256×5504/14-bit,
the NEF RAW is 8280×5520/14-bit and the main JPEG is 8256×5504. The functional
model resamples cells; this is not evidence of physical border pixels.

Reuse functional devices and complete workflow recipes across models, but
revalidate each source gate, descriptor layout, pending bit, callback and
IRQ. A useful ZR source-completion experiment remains default-off in the
shared board because partial graph progress is not whole-camera acceptance.

## Follow data before flags

A command can return success after iterating over an empty transfer table.
One Z9 stop investigation found zero data/length windows: no SPI transaction
was made even though the command function returned zero. A completion input
must be labeled as a substitute until the missing resource body is recovered.

Trace buffer ownership: original allocation → parameter packing → descriptor
submission → bounded write → pending cause → original ISR acknowledgement →
display source. Retain an incomplete replacement separately from the active
bank. A selector write alone is not a complete descriptor submission.

## Stop is a first-class device operation

Getting the first frame is insufficient. Menu transitions stop several units
with distinct normal-stop and drain causes. A downstream error-cleanup access
may be a consequence of an earlier timeout. Observe the first nonzero return
and the actual pending/mask state before changing the final failing register.

One-shot probes can be consumed during startup. Re-arm around the specific
operation and count calls; otherwise an initial successful stop can be
mistaken for evidence about a later MENU stop.

Keep status raw while masked, drive IRQ from the selected causes, and clear
only W1C bits. Test partial acknowledgement and restart. Do not make every
completion bit appear on every write, or fake a wait result inside the guest.

## Test the picture independently

Capture the paused LCD, video planes and overlay alpha. Decode NV12 with an
independent reference and compare pixels where alpha is zero. Check luminance
variation so a uniformly black frame cannot pass by matching another black
buffer. On return from MENU require new RAW frames, not just a preserved old
image or an increasing UI refresh counter.

## Treat scheduling and observers as experimental variables

A qtest socket does not mean the qtest accelerator is active. Check the
running accelerator and measure virtual time rather than assuming that
instruction-clock idle advancement has stopped. A service core looping on
WFE can keep the machine busy even while application CPUs are asleep.

Keep external input timing in the same clock domain as the modeled devices.
Do not replace the firmware's zero-duration waits with invented OS successes:
trace the duration's missing input and supply an explicitly synthetic value.
Keep physical timing claims separate from functional progress.

Repeat a successful cold boot with detailed tracing removed. In this project
one instrumented three-return run was followed by a failing uninstrumented
run. A positive run is evidence for that configuration, not enough to declare
a race fixed. Sparse traces must report coverage and truncation; missing
events cannot prove absence of a lifetime error.

## Reuse across models

Reuse source organization, peripheral abstractions, pixel primitives, evidence
formats and test methods. Establish fresh mappings for the new sample's CPU,
memory, IRQs, object layouts, SPI channels and key tables. Z9 and ZR sharing a
processor generation does not establish identical software bindings.

## Keep research recoverable and publication clean

Use fresh run names and commit small model changes with the reason and checks.
Preserve negative evidence instead of replacing a failed result. Pin the
upstream source and record the compiled binary hash. Keep active process
ownership explicit and bound memory, log growth and probing duration.

Build public releases from an explicit source inventory and fresh Git history.
Review code for embedded program/table bytes even if all filenames are text.
Generate synthetic inputs or derive necessary defaults from the user's local
firmware at runtime. Audit all refs and staged blobs, not only the visible tree.

Current development scope and corrected algorithm/movie claims: [2026-10-13 shared136 snapshot](development-snapshot.md). Earlier test results retain their original revision scope.
