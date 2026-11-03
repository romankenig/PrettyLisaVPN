#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d Vendor/PrettyLisaEngine.xcframework ]; then bash scripts/build-engine.sh; fi
xcodegen generate
swift test
platform=${1:-simulator}
case "$platform" in
  simulator) scheme=PrettyLisaVPN-iOS; destination='generic/platform=iOS Simulator';;
  ios) scheme=PrettyLisaVPN-iOS; destination='generic/platform=iOS';;
  macos) scheme=PrettyLisaVPN-macOS; destination='platform=macOS';;
  *) echo 'Usage: build.sh simulator|ios|macos'; exit 2;;
esac
shift || true
xcodebuild -project PrettyLisaVPN.xcodeproj -scheme "$scheme" -configuration Debug \
  -destination "$destination" -derivedDataPath DerivedData build "$@"
