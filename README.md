# Stock Signal Monitor

只读美股信号监控工具。支持 Windows、macOS、iPhone 与 iPad，提供 Alpaca IEX、Yahoo Finance、Massive/Polygon 与 IBKR 数据接入，显示突破加仓点、风险减仓点、盈利减仓点和仓位建议，不创建或提交订单。macOS 客户端可直接通过本机 TWS Socket API 同步只读持仓，无需 Client Portal Gateway。

## 目录

- `signal_monitor_gui.py`：图形界面入口
- `signal_monitor.py`：指标和信号计算
- `data_providers.py`：行情接口适配层
- `apple/`：macOS 与 iOS/iPadOS 原生 SwiftUI 版本及共享 Swift 核心
- `docs/`：使用与部署说明
- `dist/`：已经构建好的 Windows 发布包
- `.env.example`：配置模板，不包含真实密钥

## 开发运行

1. 安装 Python 3.11 或更高版本。
2. 在项目目录运行 `setup.ps1` 安装依赖。
3. 将 `.env.example` 复制为 `.env`，按需要填写行情接口配置。
4. 运行 `start.ps1`。

## 构建 Windows 版本

运行 `build.ps1`。构建结果写入项目的 `build-output` 目录。

Windows 版支持“显示全部 / 只显示持仓”、重新读取持仓、清除全部本地持仓及独立自选列表（数量、成本、市值）。选择 `IBKR TWS + Yahoo 行情` 后，启动时从 TWS 读取持仓，行情由 Yahoo 提供。在 `.env` 配置 `TWS_HOST`、`TWS_PORT`（模拟账户 7497，实盘 7496）、`TWS_CLIENT_ID` 和可选的 `TWS_ACCOUNT_ID`。TWS 中启用 Socket API 与 Read-Only API。持仓支持美元股票多头和碎股；已清仓记录会移除，读取失败保留原有数据。

两端的独立自选列表读取应用保存的股票并合并 TWS 持仓；不直接导入 TWS Mosaic/Classic 自选页面。Windows 构建会在推送 main 后由 GitHub Actions 自动执行，成功后在该次运行的 Artifacts 中下载 `StockSignalMonitor-Windows`。

## 构建 Apple 版本

在安装 Xcode 16 与 XcodeGen 的 macOS 上运行：

```bash
./apple/scripts/bootstrap.sh
./apple/scripts/test_apple.sh
```

完整说明见 [`apple/README.md`](apple/README.md)。Codex 的 Run 操作会调用 `./script/build_and_run.sh` 构建并启动 macOS 客户端。

## 数据与安全

`.env`、持仓、风险设置、告警记录、监控状态和缓存均为本机运行数据，已排除在版本控制和发布源码包之外。迁移到其他电脑时，请在目标电脑重新填写 `.env`。

本软件仅用于行情监控和技术分析辅助，不构成投资建议。
