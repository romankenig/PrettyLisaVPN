#!/bin/bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
out="$root/apps/apple/Vendor"
mkdir -p "$out/headers"
cd "$root/engines/managed"
python3 prepare_core.py
go version
build_slice() {
  local sdk=$1 arch=$2 goos=$3 target=$4
  local dir="$out/$sdk-$arch"
  mkdir -p "$dir"
  local sdkroot
  sdkroot=$(xcrun --sdk "$sdk" --show-sdk-path)
  CGO_ENABLED=1 GOOS="$goos" GOARCH="$arch" CC="$(xcrun --sdk "$sdk" --find clang)" \
    CGO_CFLAGS="-isysroot $sdkroot -target $target" CGO_LDFLAGS="-isysroot $sdkroot -target $target" \
    go build -trimpath -buildmode=c-archive -ldflags=-checklinkname=0 -o "$dir/libPrettyLisaEngine.a" ./cmd/pl-apple
}
build_slice iphoneos arm64 ios arm64-apple-ios17.0
build_slice iphonesimulator arm64 ios arm64-apple-ios17.0-simulator
build_slice iphonesimulator amd64 ios x86_64-apple-ios17.0-simulator
build_slice macosx arm64 darwin arm64-apple-macos14.0
build_slice macosx amd64 darwin x86_64-apple-macos14.0
for sdk in iphonesimulator macosx; do
  mkdir -p "$out/$sdk-universal"
  lipo -create "$out/$sdk-arm64/libPrettyLisaEngine.a" "$out/$sdk-amd64/libPrettyLisaEngine.a" -output "$out/$sdk-universal/libPrettyLisaEngine.a"
done
cp "$out/iphoneos-arm64/libPrettyLisaEngine.h" "$out/headers/PrettyLisaEngine.h"
cat > "$out/headers/module.modulemap" <<'EOF'
module PrettyLisaEngine {
  header "PrettyLisaEngine.h"
  export *
}
EOF
# xcodebuild refuses to overwrite an existing XCFramework; remove only this known generated output.
if [ -d "$out/PrettyLisaEngine.xcframework" ]; then rm -rf "$out/PrettyLisaEngine.xcframework"; fi
xcodebuild -create-xcframework \
  -library "$out/iphoneos-arm64/libPrettyLisaEngine.a" -headers "$out/headers" \
  -library "$out/iphonesimulator-universal/libPrettyLisaEngine.a" -headers "$out/headers" \
  -library "$out/macosx-universal/libPrettyLisaEngine.a" -headers "$out/headers" \
  -output "$out/PrettyLisaEngine.xcframework"
