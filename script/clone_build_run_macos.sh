#!/usr/bin/env bash
# Clone (optional), generate Xcode project, build and launch the macOS app.
# Requires: macOS 14+, Xcode 16+, XcodeGen (`brew install xcodegen`).
set -euo pipefail

BRANCH="${BRANCH:-cursor/holding-diagnosis-engine}"
REPO_URL="${REPO_URL:-https://github.com/Mars9399/StockSignalMonitor.git}"
MODE="${1:-run}"
WORK_DIR="${WORK_DIR:-}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "此脚本只能在 macOS 上运行（当前：$(uname -s)）。" >&2
  exit 1
fi

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "缺少 Xcode / xcodebuild。请先安装 Xcode 16。" >&2
  exit 1
fi

if ! command -v xcodegen >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "正在安装 XcodeGen…"
    brew install xcodegen
  else
    echo "缺少 XcodeGen。请先运行：brew install xcodegen" >&2
    exit 1
  fi
fi

if [[ -z "$WORK_DIR" ]]; then
  if [[ -f "$(pwd)/script/build_and_run.sh" ]]; then
    WORK_DIR="$(pwd)"
  else
    WORK_DIR="${TMPDIR:-/tmp}/StockSignalMonitor-${BRANCH//\//-}"
    if [[ ! -d "$WORK_DIR/.git" ]]; then
      echo "克隆 $REPO_URL @ $BRANCH → $WORK_DIR"
      git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$WORK_DIR"
    else
      echo "更新已有克隆 $WORK_DIR"
      git -C "$WORK_DIR" fetch origin "$BRANCH"
      git -C "$WORK_DIR" checkout "$BRANCH"
      git -C "$WORK_DIR" pull --ff-only origin "$BRANCH"
    fi
  fi
fi

cd "$WORK_DIR"
echo "工作目录：$WORK_DIR"
exec ./script/build_and_run.sh "$MODE"
