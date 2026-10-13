# User-supplied firmware

The only currently supported input is the extracted Z9 C 5.32 MAIN payload:

| Property | Value |
| --- | --- |
| Length | 81,823,629 bytes |
| SHA-256 | `6380ded18395ce11cb327c766721274c85127d2cf1a1e887ee60e3d156810bdd` |
| Initial load/entry | `0x40160000` |
| CPU family | AArch64 |

The original upgrade container is not this input. Obtain a compatible payload
independently and keep it outside tracked source. This repository does not
provide a decryption key, extraction service or firmware download.
The hash pins a research sample; it is not a vendor signature validation.

The launcher opens the file for reading and rejects mismatches. It derives one
virtual ROM parameter image from defaults inside that local file and records
the derivation. Four-byte format trailers and a few version/selector values
are generated explicitly. These fill only selected gaps in the emulated ROM
address space; they do not reconstruct the missing sensor program, parameter
tables, calibration or physical flash layout.

Generated `.bin`, run JSON, logs and screenshots may contain proprietary
material and remain local. `.gitignore` is a convenience, not a sufficient
publication audit. Never add those artifacts with `git add -f`.

For a different version, do not change the accepted hash alone. Re-establish
entry points, object layouts, peripheral mappings and host peer bindings,
then add a separately tested profile. Shared SoC branding is insufficient.
