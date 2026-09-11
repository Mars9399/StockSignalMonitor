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

### 决策可靠性规则

- 已有持仓须在持仓编辑区保存低于成本的“初始风险线”。空缺时仅观察，不给出具体加减仓建议。
- 当前采用固定风险线，不自动追踪上移。R = 保存的持仓成本 − 初始风险线；2R/3R 目标固定，行情下跌不会降低风险线或抬高目标。
- TWS 同步的成本或数量变化时，风险基准失效，需重新确认。提示不代表实际成交；本阶段未增加自动分批执行或成交归因。
- Windows/macOS/iOS 统一保留碎股。实际建议减仓数量不超过持有数量。
- 指标仅采用纽约当前日期之前的日线，排除当日未完成日线；跨日重新加载历史。
- 操作提示要求行情时间戳不超过 120 秒、非未来异常时间，且处于纽约工作日 09:30–16:00；缺少时间戳、历史未更新或监控停止均降为仅观察。
- 本阶段尚未接入交易所节假日和提前收盘日历；前一工作日日线缺失时保守暂停，不猜测节假日。已有 Gateway 适配未取得可信交易时间戳，因此只展示观察数据。
- “长/中/短周期模型”表示均线组合和历史长度，不是胜率或置信度。跨数据源复权口径、完整交易日历及策略回测仍需后续验证。

`.env`、持仓、风险设置、告警记录、监控状态和缓存均为本机运行数据，已排除在版本控制和发布源码包之外。迁移到其他电脑时，请在目标电脑重新填写 `.env`。

本软件仅用于行情监控和技术分析辅助，不构成投资建议。
