# 测试版 2.6.0-test · P0–P3 优化

本版本在只读前提下落地优化分析报告中的 P0–P3 能力，供本机验证。

## 如何测试（Windows / Python）

```powershell
cd <repo>
Copy-Item .env.example .env   # 若尚未配置
.\setup.ps1
.\start.ps1
# 或：python signal_monitor_gui.py
```

标题栏应显示 `v2.6.0-test`。

### 建议验证清单

1. **策略设置**：顶部组合摘要栏 →「策略设置」  
   - 默认过滤关闭时，行为应接近旧版突破提示  
   - 打开「买入突破需量比达标」后，低量比突破应显示「过滤降级」  
2. **操作评分**：概览列名改为「买入/减持操作评分*」，不再暗示胜率  
3. **延迟画像**：信号列显示数据源与行情年龄、通道基准日  
4. **组合摘要**：有持仓时显示市值占比 / 超配再平衡提示  
5. **解释建议**：选中股票 →「解释建议」（无 `OPENAI_API_KEY` 时用规则原文）  
6. **告警回放 / 事件观察**：对应按钮  
7. **保护线**：策略里改 ATR 倍数后，新建保护线按新倍数  

## 如何测试（macOS · 本机 Xcode）

仓库已同步 Shared 核心：

- 默认行情轮询改为 **5 秒**（`MonitorStrategySettings.quotePollSeconds`）  
- 过滤引擎 / Suggestion / ATR 倍数保护线  

```bash
./apple/scripts/bootstrap.sh
./apple/scripts/test_apple.sh
# 或用 Xcode 打开生成的工程运行 macOS target
```

## 明确未做 / 降级项

- **P3 SIP 全市场实时**：需付费订阅，本测试版仅展示数据源画像，不切换 SIP  
- **完整前视收益回测**：仅提供本地 `signal_alerts.csv` 频次回放  
- **LLM**：可选；未配置密钥时回退规则解释  

## 合规提示

输出均为技术监控与仓位辅助，**不构成投资建议**，软件不下单。
