#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
APP_NAME="StockSignalMonitorMac"
BUNDLE_ID="com.mars9399.StockSignalMonitor.macOS"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPLE_DIR="$ROOT_DIR/apple"
PROJECT="$APPLE_DIR/StockSignalMonitorApple.xcodeproj"
DERIVED_DATA="$APPLE_DIR/.derivedData"
APP_BUNDLE="$DERIVED_DATA/Build/Products/Debug/$APP_NAME.app"
APP_BINARY="$APP_BUNDLE/Contents/MacOS/$APP_NAME"

pkill -x "$APP_NAME" >/dev/null 2>&1 || true
"$APPLE_DIR/scripts/bootstrap.sh"
xcodebuild -project "$PROJECT" -scheme StockSignalMonitorMac -configuration Debug -destination "platform=macOS" -derivedDataPath "$DERIVED_DATA" build

open_app() { /usr/bin/open -n "$APP_BUNDLE"; }

case "$MODE" in
  run) open_app ;;
  --debug|debug) lldb -- "$APP_BINARY" ;;
  --logs|logs) open_app; /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\"" ;;
  --telemetry|telemetry) open_app; /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\"" ;;
  --verify|verify) open_app; sleep 1; pgrep -x "$APP_NAME" >/dev/null ;;
  *) echo "usage: $0 [run|--debug|--logs|--telemetry|--verify]" >&2; exit 2 ;;
esac
