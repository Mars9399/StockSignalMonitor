# Stock Signal Monitor

只读美股信号监控工具。支持 Alpaca IEX、Yahoo Finance、Massive/Polygon 与 IBKR Gateway，显示突破加仓点、风险减仓点、盈利减仓点和仓位建议，不创建或提交订单。

## 目录

- `signal_monitor_gui.py`：图形界面入口
- `signal_monitor.py`：指标和信号计算
- `data_providers.py`：行情接口适配层
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

## 数据与安全

`.env`、持仓、风险设置、告警记录、监控状态和缓存均为本机运行数据，已排除在版本控制和发布源码包之外。迁移到其他电脑时，请在目标电脑重新填写 `.env`。

本软件仅用于行情监控和技术分析辅助，不构成投资建议。
