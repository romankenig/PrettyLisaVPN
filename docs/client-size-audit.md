# Client size audit

Baseline: develop `6177e2e53da41413f60385686d9f1f8e425b0492`.
This task changes packaging only; account, billing, DEMO, routing, protocol and
privacy behavior are preserved. No backend migration or follow-up is required.

| Component | Before | After | Change |
| --- | --- | --- | --- |
| Windows | 0.28.2 | 0.28.3 | Brotli-packed engine and lossless WOFF2 |
| Android | 0.27.4 / code 54 | 0.27.5 / code 55 | Remove unused Compose preview and tooling dependencies |
| Chrome Extension | 0.3.0 | 0.3.1 | Replace bundled TTF with lossless WOFF2 |
| iOS | 0.3.0 | 0.3.1 | Strip local symbols from Release app/extension |
| macOS | 0.2.2 | 0.2.3 | Strip local symbols from Release app/extension |
| Backend, managed engine, website | unchanged | unchanged | No delivered behavior change |

Linux desktop and Android TV have no distributable client in this repository.
The Linux node engine is infrastructure, not a desktop application.

## Removed payload

Android ships a development-signed debug APK. Its Compose tooling and preview
dependencies were unused: there are no Preview annotations or ComposeViewAdapter
calls. Removing both also removes their otherwise unneeded transitive runtime
code. Keep UI tests, the debug fixture adapter, all four standalone ABIs, all
locales, both VPN engines and licenses. The APK packaging check rejects accidental
reintroduction of the preview adapter/annotation in both debug and release DEX.

Windows and Chrome each replace a 359,804-byte TTF with a 122,000-byte WOFF2:
237,804 bytes (66.09%) less font payload. This is not the installer/ZIP saving.
Conversion used fonttools 4.60.2 / Brotli 1.2.1 with no table transforms or
subsetting. Every font table, glyph order and cmap was compared after decoding;
only the WOFF2 head flag and checksum differ. All weights, glyphs, hinting and
layout data remain. OFL notices remain. Native Android/iOS retain TTF support.
The website copies the identical existing iOS TTF, preserving its output URL
and bytes; its version is unchanged. Its CI now watches that source too.

Windows replaces its embedded GZip engine with Brotli at build time, using the
already locked permissive Brotli library. It embeds the original EXE's SHA-256
separately and verifies it before execution. The 64 MiB decompression bound,
private extraction directory/ACLs, signed Wintun and service lifecycle remain.
Corrupt/truncated payloads, a wrong digest, a non-PE file and excessive output
are rejected by native tests. The engine code, protocols and dependencies do
not change; the same bytes are restored before launch. Compression work runs
at build time, not at connection time. Brotli decompression still occurs on
connection, like the former GZip decompression.

Apple's ordinary Release `xcodebuild build` previously left local symbol names
in the distributed app and tunnel binaries. Enable deployment postprocessing
with `STRIP_STYLE=non-global` and Swift export stripping disabled: retain external
symbols and executable code.
Debug/Simulator builds retain diagnostic symbols. Packaging inspects the actual
Release Mach-O symbol tables directly (nm also synthesizes dyld records), rejects
local/debug symbols, checks all three exported engine C entry points in every
architecture and records installed bundle bytes. The source/license
archives remain separate downloads. Unsigned device/Mac labels remain unchanged.

## Measurement and verification

Compare identical artifact kinds: Windows NSIS installer, Android ARM64 debug
APK, Chrome installable ZIP, unsigned Release iOS device and macOS ZIPs.
Do not count GitHub artifact ZIPs containing corresponding source archives,
screenshots or Simulator builds as the application's download size.
Unpacked size and compressed download size are separate measurements.

Fresh unmodified baseline builds:

- [Android run 43690765823, attempt 1](https://github.com/romankenig/PrettyLisaVPN/actions/runs/43690765823)
- [Apple run 43690768395, attempt 1](https://github.com/romankenig/PrettyLisaVPN/actions/runs/43690768395)
- [Windows run 43690059958, attempt 1](https://github.com/romankenig/PrettyLisaVPN/actions/runs/43690059958)

Chrome before/after can additionally be built locally from the same lockfile.
The task PR records final product HEAD, actual build/merge SHA, run/attempt,
artifact bytes/digests, measured deltas and every CI result after the final push.
This document does not claim that pending checks or publication have completed.

Required evidence: frontend lint/typecheck/unit tests/build; Chrome installed
browser and billing portal review including font loading; Windows native review
including Rubik loading, Rust tests/clippy and installer acceptance; Android
unit/lint/ABI/packaging and API 26/35/36 emulator checks; Swift contracts,
device/Mac compilation, symbol inspection and native UI checks. No protocol code
changed; these checks are not a new live VPN or signed physical-iPhone acceptance.

Rejected cuts: VPN engines/protocols, offline languages, licenses, required
native architectures, Rust panic unwinding and backend/client contracts. Existing
Windows release/LTO and Android ABI splitting are retained. Caches, node_modules
and source archives are not installed app bloat.

Merge, signing, release publication and production deployment are separate tasks.
After an approved merge, existing successful develop workflows publish the new
verified binaries to stable dashboard URLs; verify that publication then.
