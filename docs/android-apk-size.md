# Android APK size — 0.15.1

Android 0.15.0/code28 → 0.15.1/code29 is a packaging patch. Dashboard
0.4.1 → 0.4.2 labels the phone download ARM64. Backend/Windows product versions
are unchanged by this task. Source checks are not evidence of a published build;
the task PR records the final product/build SHA, run/attempt, APK size and digest.

The published 0.15.0 APK was 253155576 bytes. Its four CPU directories contained
238618580 bytes of uncompressed native libraries. The ARM64 managed library alone
was 47995544 bytes, including DWARF and static symbol tables. Device downloads
must not contain code for all four CPUs.

Gradle now produces a complete standalone APK per ABI, without a universal APK.
Each device installs exactly one APK; no companion engine or dynamic download is
required. All engines, locales, private services, debug signing identity and
application ID remain. Go linking removes debug symbols (`-s -w`); native
libraries are compressed in APKs and extracted by Android on installation.
Installed size is therefore distinct from APK download size.

The dashboard's permanent Android URL publishes the ARM64 phone APK. ARM32/x86
standalone artifacts remain in CI; the x86_64 APK is used by API 26/35/36 emulator
jobs from the same source. Each APK records its ABI, build identity and SHA-256.
Exact corresponding source/license archives remain available beside the download.

Packaging checks require all four ABI outputs, exactly one native ABI per APK,
both managed and WireGuard libraries, compression, absence of Go debug sections,
license notices, fixture isolation and a maximum of **40000000 bytes** per APK.
Publication additionally rejects an incorrect phone ABI, size/hash/source
mismatch or an oversized artifact. Failed checks retain the previous download.

Pending: successful CI APK builds and emulator runs, measured artifact size,
authenticated publication/download hash verification and the dashboard label.
