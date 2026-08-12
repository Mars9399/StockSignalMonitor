#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$ROOT_DIR/StockSignalMonitorApple.xcodeproj"
DERIVED_DATA="$ROOT_DIR/.derivedData"
"$ROOT_DIR/scripts/bootstrap.sh"
cd "$ROOT_DIR"
swift test
xcodebuild -project "$PROJECT" -scheme StockSignalMonitorMac -configuration Debug -destination "platform=macOS" -derivedDataPath "$DERIVED_DATA" CODE_SIGNING_ALLOWED=NO build
xcodebuild -project "$PROJECT" -scheme StockSignalMonitorIOS -configuration Debug -destination "generic/platform=iOS Simulator" -derivedDataPath "$DERIVED_DATA" CODE_SIGNING_ALLOWED=NO build
