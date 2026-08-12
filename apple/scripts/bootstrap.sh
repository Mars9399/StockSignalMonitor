#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v xcodegen >/dev/null 2>&1; then
  echo "缺少 XcodeGen。请先运行：brew install xcodegen" >&2
  exit 1
fi
cd "$ROOT_DIR"
xcodegen generate --spec project.yml
echo "已生成：$ROOT_DIR/StockSignalMonitorApple.xcodeproj"
