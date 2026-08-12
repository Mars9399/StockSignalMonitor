"""Read-only US-stock entry/stop monitor using Alpaca market data.

This module intentionally imports no Alpaca trading client and contains no
order creation or submission code.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "signal_state.json"
ALERT_FILE = BASE_DIR / "signal_alerts.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读美股买入点和止损点监控")
    parser.add_argument("--once", action="store_true", help="扫描一次后退出")
    parser.add_argument("--interval", type=int, default=None, help="连续监控间隔（秒）")
    return parser.parse_args()


def load_settings() -> tuple[str, str, list[str], int]:
    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    api_secret = os.getenv("ALPACA_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("请先复制 .env.example 为 .env，并填写 Alpaca API Key 和 Secret。")

    symbols = [
        value.strip().upper()
        for value in os.getenv("WATCH_SYMBOLS", "AAPL,MSFT,NVDA,SPY,QQQ").split(",")
        if value.strip()
    ]
    interval = max(60, int(os.getenv("SCAN_INTERVAL_SECONDS", "300")))
    return api_key, api_secret, symbols, interval


def load_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, str]) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def calculate_levels(df: pd.DataFrame, live_price: float) -> dict[str, float | str]:
    required = {"high", "low", "close"}
    if not required.issubset(df.columns):
        raise ValueError("历史数据缺少 high、low 或 close 列")

    frame = df.sort_index().dropna(subset=["high", "low", "close"]).copy()
    history_days = len(frame)
    if history_days == 0:
        raise ValueError("没有可用的历史日线")
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_period = min(14, history_days)
    atr14 = float(true_range.tail(atr_period).mean())

    if history_days >= 205:
        fast_period, slow_period = 50, 200
        signal_quality = "标准"
        signal_model = "SMA50 / SMA200"
        signal_ready = True
    elif history_days >= 65:
        fast_period, slow_period = 20, 50
        signal_quality = "降级·中等"
        signal_model = "SMA20 / SMA50"
        signal_ready = True
    elif history_days >= 35:
        fast_period, slow_period = 10, 30
        signal_quality = "降级·较低"
        signal_model = "SMA10 / SMA30"
        signal_ready = True
    else:
        fast_period = min(10, history_days)
        slow_period = min(30, history_days)
        signal_quality = "不足·仅观察"
        signal_model = f"仅 {history_days} 根日线"
        signal_ready = False

    trend_fast = float(frame["close"].rolling(fast_period).mean().iloc[-1])
    trend_slow = float(frame["close"].rolling(slow_period).mean().iloc[-1])
    buy_point = float(frame["high"].tail(min(20, history_days)).max()) if signal_ready else 0.0
    stop_point = max(0.01, buy_point - 2 * atr14) if signal_ready else 0.0
    trend_ok = signal_ready and live_price > trend_slow and trend_fast > trend_slow

    if not signal_ready:
        status = "DATA_SHORT"
    elif trend_ok and live_price >= buy_point:
        status = "BUY_ALERT"
    elif trend_ok:
        status = "WATCH"
    else:
        status = "NO_SIGNAL"

    return {
        "status": status,
        "price": live_price,
        "buy_point": buy_point,
        "stop_point": stop_point,
        "risk_pct": ((buy_point - stop_point) / buy_point) * 100 if buy_point else 0.0,
        "atr14": atr14,
        "sma50": trend_fast,
        "sma200": trend_slow,
        "trend_fast": trend_fast,
        "trend_slow": trend_slow,
        "history_days": history_days,
        "signal_quality": signal_quality,
        "signal_model": signal_model,
        "signal_ready": signal_ready,
    }


def send_discord(message: str) -> None:
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        return
    response = requests.post(webhook, json={"content": message}, timeout=10)
    response.raise_for_status()


def record_alert(symbol: str, values: dict[str, float | str], observed_at: datetime) -> None:
    new_file = not ALERT_FILE.exists()
    with ALERT_FILE.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["observed_at_utc", "symbol", "price", "buy_point", "stop_point", "risk_pct"],
        )
        if new_file:
            writer.writeheader()
        writer.writerow(
            {
                "observed_at_utc": observed_at.isoformat(),
                "symbol": symbol,
                "price": round(float(values["price"]), 4),
                "buy_point": round(float(values["buy_point"]), 4),
                "stop_point": round(float(values["stop_point"]), 4),
                "risk_pct": round(float(values["risk_pct"]), 2),
            }
        )


def scan(client: StockHistoricalDataClient, symbols: list[str], state: dict[str, str]) -> None:
    now = datetime.now(timezone.utc)
    bars_request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=now - timedelta(days=420),
        end=now - timedelta(minutes=16),
        feed=DataFeed.IEX,
    )
    bars_df = client.get_stock_bars(bars_request).df
    latest = client.get_stock_latest_trade(
        StockLatestTradeRequest(symbol_or_symbols=symbols, feed=DataFeed.IEX)
    )

    print(f"\n扫描时间（UTC）：{now:%Y-%m-%d %H:%M:%S}")
    print("代码      现价       买入点      止损点      风险%     状态")
    print("-" * 66)

    for symbol in symbols:
        try:
            history = bars_df.xs(symbol, level="symbol") if isinstance(bars_df.index, pd.MultiIndex) else bars_df
            live_price = float(latest[symbol].price)
            values = calculate_levels(history, live_price)
            status = str(values["status"])
            print(
                f"{symbol:<8} {live_price:>9.2f} {values['buy_point']:>11.2f} "
                f"{values['stop_point']:>11.2f} {values['risk_pct']:>8.2f}  {status}"
            )

            alert_key = f"{symbol}:{now.date().isoformat()}"
            if status == "BUY_ALERT" and state.get(symbol) != alert_key:
                message = (
                    f"买入点提示（仅供观察） {symbol}\n"
                    f"现价: ${live_price:.2f}\n"
                    f"突破买入点: ${values['buy_point']:.2f}\n"
                    f"参考止损点: ${values['stop_point']:.2f}\n"
                    f"价格风险: {values['risk_pct']:.2f}%"
                )
                print("\n" + message)
                record_alert(symbol, values, now)
                try:
                    send_discord(message)
                except requests.RequestException as exc:
                    print(f"Discord 提示发送失败：{exc}", file=sys.stderr)
                state[symbol] = alert_key
            elif status != "BUY_ALERT":
                state.pop(symbol, None)
        except Exception as exc:
            print(f"{symbol:<8} 数据或计算失败：{exc}", file=sys.stderr)

    save_state(state)


def main() -> int:
    args = parse_args()
    try:
        api_key, api_secret, symbols, configured_interval = load_settings()
        interval = args.interval or configured_interval
        client = StockHistoricalDataClient(api_key, api_secret)
        state = load_state()

        print("只读模式：未载入交易客户端，不会创建或提交订单。")
        print("监控股票：" + ", ".join(symbols))
        while True:
            scan(client, symbols, state)
            if args.once:
                return 0
            print(f"下次扫描约在 {interval} 秒后；按 Ctrl+C 停止。")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n监控已停止。")
        return 0
    except Exception as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
