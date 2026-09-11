# Apple 原生版本

该目录包含共用一套信号算法与行情服务的 macOS 14+、iOS/iPadOS 17+ 原生 SwiftUI 客户端。两端均为只读行情监控器，代码中不包含创建、修改、取消或提交订单的能力。

## 功能

- 自选股添加、删除、搜索和刷新
- 买入/突破加仓点、风险减仓点、2R/3R 盈利减仓点
- 平均成本、持股数量与风险参数输入
- Alpaca、Yahoo Finance、Massive/Polygon 行情适配
- macOS 通过本机 TWS Socket API 自动同步只读持仓
- macOS 独立自选列表会合并 TWS 持仓股票，并显示持仓数量、均价与市值
- macOS 概览支持显示全部/只显示持仓、重新读取 TWS 持仓和清除本地持仓
- 根据历史日线数量自动使用标准、降级或仅观察模型
- iPhone/iPad 的标签式导航与 macOS 原生侧栏、设置窗口、菜单和快捷键

> macOS 客户端直接连接已登录的 Trader Workstation，不需要 Client Portal Gateway。TWS 中须启用 ActiveX and Socket Clients，并保持 Read-Only API 开启。默认 Paper 端口为 7497，Live 端口为 7496。iOS 版本仍保留 Client Portal Gateway 行情适配。

> TWS Socket API 不提供读取 Mosaic/Classic TWS 自选页的接口。macOS 的“自选列表”读取应用本机保存的自选股票，并在每次同步时自动合并当前 TWS 持仓股票。

## 工程结构

- `Shared/`：跨平台模型、信号算法、只读行情客户端与状态 Store
- `Tests/SharedTests/`：共享算法和配置测试
- `macOS/`：macOS SwiftUI 客户端
- `iOS/`：iPhone/iPad SwiftUI 客户端
- `Package.swift`：共享核心 Swift Package
- `project.yml`：XcodeGen 工程定义
- `scripts/`：生成、构建和测试入口

## 在 macOS 上生成工程

要求：Xcode 16、Swift 5.9+、XcodeGen。

```bash
brew install xcodegen
./apple/scripts/bootstrap.sh
open apple/StockSignalMonitorApple.xcodeproj
```

生成后可在 Xcode 中选择：

- `StockSignalMonitorMac`
- `StockSignalMonitorIOS`

## 验证

```bash
./apple/scripts/test_apple.sh
```

该脚本依次运行共享核心单元测试、macOS 构建和 iOS Simulator 通用构建。项目根目录的 `./script/build_and_run.sh` 是 Codex Run 按钮使用的 macOS 构建启动入口，支持 `--debug`、`--logs`、`--telemetry` 和 `--verify`。

## 配置安全

API Key 仅保存在 Apple 平台的 Keychain 中；非敏感偏好保存在本机。不要把实际密钥写入源码、`project.yml` 或示例文件。TWS 应保持 Read-Only API 开启；macOS 客户端只实现连接、持仓请求和取消持仓订阅，没有实现任何订单请求。

本工具只提供技术分析辅助，不构成投资建议。
