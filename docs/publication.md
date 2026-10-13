# Publication boundary

The public repository must start with fresh Git history. Do not push a branch
of the private research repository, even if its latest tree excludes binaries.
Every reachable commit and staged blob belongs in the review.

Included: original emulator/tool source, formulas, interface addresses/masks,
sample-identification hashes, synthetic input generators, tests, documentation
and required open-source license notices.

Excluded: original or decrypted Nikon programs, firmware containers, camera
memory/flash dumps, keys, calibration images, extracted fonts/icons, copied
program instruction arrays, private photos, original UI screenshots and
runtime artifacts. Shader recognition uses hashes. The color knot coordinates
and indirect table selectors use formulas rather than embedded ROM tables.
Register masks and event mappings express interoperability behavior; they are
not a distribution of the original driver implementation.

The capture update includes authored RAW/NV16/JPEG/PCIe adapters, protocol
peers, a source-only workflow profile, read-only extraction/auditing tools and
documentation. Libjpeg, upstream QEMU and exfatprogs remain open-source
dependencies. Quantizers and other runtime tables are read from the user's
guest; they are not embedded camera assets. Full capture output, card images,
NEFs, producer RAM snapshots and lifecycle records remain local and excluded.
The reusable profile contains option names, input actions and interoperability
addresses; it contains no firmware bytes, instruction arrays or secret keys.

`parameter_input.py` reads a default body from the user's local MAIN and creates
an explicit diagnostic ROM image only in the local run directory. No such
image is tracked or downloaded. Small synthetic version/selector/trailer
inputs are identified as assumptions, not recovered factory values.

The allowlist/manifest audit is an additional guard, not an automatic origin
or licensing determination. Maintainers must manually inspect new arrays,
fixtures, documentation and imports before refreshing it. A `.py` or `.c`
extension alone does not establish that a file is safe to publish.

Current development scope and corrected algorithm/movie claims: [2026-10-13 shared136 snapshot](development-snapshot.md). Earlier test results retain their original revision scope.
