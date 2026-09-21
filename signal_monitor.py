"""Read-only US-stock entry/stop monitor using Alpaca market data.

This module intentionally imports no Alpaca trading client and contains no
order creation or submission code.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
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
from reliability import NEW_YORK, observation_reason


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "signal_state.json"
ALERT_FILE = BASE_DIR / "signal_alerts.csv"
SIGNAL_LOOKBACK_DAYS = 10
MIN_SIGNAL_HISTORY_DAYS = 20


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def estimate_action_probabilities(
    values: dict,
    position: dict,
    account_value: float,
    max_position_pct: float,
    portfolio_value: float = 0.0,
    available_funds: float | None = None,
) -> dict[str, int | str]:
    """Return bounded short-term action scores, not empirical win probabilities.

    The market component is intentionally derived from data already used by
    the read-only monitor. Position and account pressure can lower the buy
    score or raise the reduction score, but never alter the channel signals.
    """
    if not values.get("signal_ready", False):
        return {
            "buy_probability": 0,
            "reduce_probability": 0,
            "buy_label": "数据不足",
            "reduce_label": "数据不足",
        }

    price = max(0.01, float(values.get("price", 0.01)))
    buy_point = max(0.01, float(values.get("buy_point", price)))
    stop_point = max(0.01, float(values.get("stop_point", price)))
    atr = max(0.01, float(values.get("atr14", price * 0.01)))
    trend_fast = float(values.get("trend_fast", price))
    trend_slow = float(values.get("trend_slow", price))
    momentum_5d = float(values.get("momentum_5d_pct", 0.0))
    momentum_10d = float(values.get("momentum_10d_pct", 0.0))
    rsi14 = float(values.get("rsi14", 50.0))
    volume_ratio = float(values.get("volume_ratio", 1.0))
    status = str(values.get("status", "WATCH"))

    span = max(0.01, buy_point - stop_point)
    channel_position = _clamp((price - stop_point) / span, 0.0, 1.0)
    buy_score = 12.0 + channel_position * 32.0

    if status == "BUY_ALERT":
        extension_pct = max(0.0, (price / buy_point - 1.0) * 100.0)
        buy_score += 20.0
        if extension_pct <= 3.0:
            buy_score += 5.0
        else:
            buy_score -= min(30.0, (extension_pct - 3.0) * 5.0)
    elif status == "SELL_ALERT":
        buy_score = min(buy_score, 10.0)
    else:
        gap_atr = (buy_point - price) / atr
        if 0.0 <= gap_atr <= 1.0:
            buy_score += 8.0

    buy_score += 8.0 if price >= trend_fast else -8.0
    buy_score += 10.0 if trend_fast >= trend_slow else -9.0
    buy_score += _clamp(momentum_5d, -5.0, 5.0) * 1.4
    buy_score += _clamp(momentum_10d, -8.0, 8.0) * 0.55
    if 48.0 <= rsi14 <= 68.0:
        buy_score += 8.0
    elif rsi14 >= 78.0:
        buy_score -= 13.0
    elif rsi14 < 35.0:
        buy_score -= 8.0
    if volume_ratio >= 1.5:
        buy_score += 7.0
    elif volume_ratio >= 1.15:
        buy_score += 3.0
    elif volume_ratio < 0.55:
        buy_score -= 4.0
    channel_risk_pct = span / buy_point * 100.0
    if channel_risk_pct <= 12.0:
        buy_score += 5.0
    elif channel_risk_pct >= 22.0:
        buy_score -= 9.0

    quantity = max(0.0, float(position.get("quantity", 0.0)))
    avg_cost = max(0.0, float(position.get("avg_cost", 0.0)))
    safe_account = max(1.0, float(account_value))
    position_value = quantity * price
    position_ratio = position_value / safe_account
    allocation_limit = max(0.01, float(max_position_pct) / 100.0)
    allocation_load = position_ratio / allocation_limit
    portfolio_ratio = max(0.0, float(portfolio_value)) / safe_account
    available_ratio = None if available_funds is None else float(available_funds) / safe_account

    if allocation_load >= 1.0:
        buy_score -= 28.0
    elif allocation_load >= 0.8:
        buy_score -= 14.0
    if portfolio_ratio >= 1.0:
        buy_score -= 12.0
    elif portfolio_ratio >= 0.9:
        buy_score -= 7.0
    if available_ratio is not None and available_ratio < 0.05:
        buy_score -= 14.0
    # Keep ready-data scores away from false 0%/100% certainty.
    buy_probability = int(round(_clamp(buy_score, 5.0, 95.0)))

    if quantity <= 0.0 or avg_cost <= 0.0:
        reduce_probability = 0
    else:
        reduce_score = 8.0
        saved_stop = position.get("initial_stop")
        if isinstance(saved_stop, (int, float)) and math.isfinite(float(saved_stop)) and float(saved_stop) > 0:
            position_stop = max(stop_point, float(saved_stop))
        else:
            position_stop = stop_point

        if status == "SELL_ALERT":
            reduce_score += 48.0
        if price <= position_stop:
            reduce_score += 36.0
        reduce_score += 10.0 if price < trend_fast else -3.0
        reduce_score += 9.0 if trend_fast < trend_slow else -3.0
        if momentum_5d < 0:
            reduce_score += min(14.0, abs(momentum_5d) * 1.8)
        if momentum_10d < 0:
            reduce_score += min(10.0, abs(momentum_10d) * 0.8)

        pnl_pct = (price / avg_cost - 1.0) * 100.0
        if pnl_pct <= -8.0:
            reduce_score += 18.0
        elif pnl_pct <= -3.0:
            reduce_score += 10.0
        if pnl_pct >= 10.0 and rsi14 >= 70.0:
            reduce_score += 12.0
        if price > buy_point and (price / buy_point - 1.0) * 100.0 > 5.0:
            reduce_score += 10.0

        if allocation_load >= 1.25:
            reduce_score += 27.0
        elif allocation_load >= 1.0:
            reduce_score += 19.0
        elif allocation_load >= 0.8:
            reduce_score += 9.0
        if portfolio_ratio >= 1.0:
            reduce_score += 13.0
        elif portfolio_ratio >= 0.9:
            reduce_score += 8.0
        if available_ratio is not None and available_ratio < 0.05:
            reduce_score += 11.0
        if status == "BUY_ALERT" and trend_fast >= trend_slow and allocation_load < 0.8:
            reduce_score -= 14.0

        reduce_probability = int(round(_clamp(reduce_score, 5.0, 95.0)))
        if price <= position_stop:
            reduce_probability = max(reduce_probability, 90)

    def label(score: int) -> str:
        if score >= 75:
            return "高"
        if score >= 55:
            return "中高"
        if score >= 35:
            return "观察"
        return "低"

    return {
        "buy_probability": buy_probability,
        "reduce_probability": reduce_probability,
        "buy_label": label(buy_probability),
        "reduce_label": "无持仓" if quantity <= 0 else label(reduce_probability),
    }


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
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("历史日线缺少交易日期")
    dates = frame.index.strftime('%Y-%m-%d')
    frame = frame[dates < datetime.now(NEW_YORK).date().isoformat()]
    frame = frame[~frame.index.duplicated(keep='last')]
    frame = frame[(frame['low'] > 0) & (frame['high'] >= frame['low']) & (frame['close'] >= frame['low']) & (frame['close'] <= frame['high'])]
    if not pd.notna(live_price) or not 0 < live_price < float('inf'):
        raise ValueError("价格无效")
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

    fast_period = min(5, history_days)
    slow_period = min(20, history_days)
    signal_ready = history_days >= MIN_SIGNAL_HISTORY_DAYS
    signal_quality = "实时价格通道" if signal_ready else "不足·仅观察"
    signal_model = f"{SIGNAL_LOOKBACK_DAYS}日高低点"

    trend_fast = float(frame["close"].rolling(fast_period).mean().iloc[-1])
    trend_slow = float(frame["close"].rolling(slow_period).mean().iloc[-1])
    close = frame["close"].astype(float)

    def momentum(period: int) -> float:
        if len(close) <= period:
            return 0.0
        base = float(close.iloc[-(period + 1)])
        return (float(close.iloc[-1]) / base - 1.0) * 100.0 if base > 0 else 0.0

    deltas = close.diff().dropna().tail(min(14, max(1, history_days - 1)))
    average_gain = float(deltas.clip(lower=0).mean()) if not deltas.empty else 0.0
    average_loss = float((-deltas.clip(upper=0)).mean()) if not deltas.empty else 0.0
    if average_gain == 0 and average_loss == 0:
        rsi14 = 50.0
    elif average_loss == 0:
        rsi14 = 100.0
    else:
        relative_strength = average_gain / average_loss
        rsi14 = 100.0 - 100.0 / (1.0 + relative_strength)

    volume_ratio = 1.0
    if "volume" in frame.columns:
        volumes = pd.to_numeric(frame["volume"], errors="coerce").dropna()
        volumes = volumes[volumes > 0].tail(min(20, history_days))
        if not volumes.empty and float(volumes.mean()) > 0:
            volume_ratio = float(volumes.iloc[-1] / volumes.mean())
    signal_window = frame.tail(min(SIGNAL_LOOKBACK_DAYS, history_days))
    buy_point = float(signal_window["high"].max()) if signal_ready else 0.0
    stop_point = float(signal_window["low"].min()) if signal_ready else 0.0

    if not signal_ready:
        status = "DATA_SHORT"
    elif live_price >= buy_point:
        status = "BUY_ALERT"
    elif live_price <= stop_point:
        status = "SELL_ALERT"
    else:
        status = "WATCH"

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
        "momentum_5d_pct": momentum(5),
        "momentum_10d_pct": momentum(10),
        "rsi14": rsi14,
        "volume_ratio": volume_ratio,
        "history_days": history_days,
        "history_date": frame.index[-1].strftime('%Y-%m-%d'),
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
    extended_fields = ["observed_at_utc", "signal", "symbol", "price", "buy_point", "sell_point", "risk_pct"]
    legacy_fields = ["observed_at_utc", "symbol", "price", "buy_point", "stop_point", "risk_pct"]
    fieldnames = extended_fields
    if not new_file:
        try:
            with ALERT_FILE.open("r", encoding="utf-8-sig") as existing:
                first_line = existing.readline().strip().split(",")
            if first_line == legacy_fields:
                fieldnames = legacy_fields
        except OSError:
            pass
    with ALERT_FILE.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if new_file:
            writer.writeheader()
        row = {
            "observed_at_utc": observed_at.isoformat(),
            "signal": str(values.get("status", "")),
            "symbol": symbol,
            "price": round(float(values["price"]), 4),
            "buy_point": round(float(values["buy_point"]), 4),
            "sell_point": round(float(values["stop_point"]), 4),
            "stop_point": round(float(values["stop_point"]), 4),
            "risk_pct": round(float(values["risk_pct"]), 2),
        }
        writer.writerow({field: row[field] for field in fieldnames})


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
            reason = observation_reason(live_price, latest[symbol].timestamp, values['history_date'])
            if reason:
                status = 'OBSERVATION_ONLY'
            print(
                f"{symbol:<8} {live_price:>9.2f} {values['buy_point']:>11.2f} "
                f"{values['stop_point']:>11.2f} {values['risk_pct']:>8.2f}  {status}"
            )

            state_key = f"{symbol}:{status}"
            alert_key = f"{state_key}:{now.date().isoformat()}"
            if status in {"BUY_ALERT", "SELL_ALERT"} and state.get(state_key) != alert_key:
                side = "买入" if status == "BUY_ALERT" else "卖出"
                trigger = values["buy_point"] if status == "BUY_ALERT" else values["stop_point"]
                message = (
                    f"{side}点提示（仅供观察） {symbol}\n"
                    f"现价: ${live_price:.2f}\n"
                    f"{side}触发点: ${float(trigger):.2f}\n"
                    f"价格通道: ${float(values['stop_point']):.2f} - ${float(values['buy_point']):.2f}"
                )
                print("\n" + message)
                record_alert(symbol, values, now)
                try:
                    send_discord(message)
                except requests.RequestException as exc:
                    print(f"Discord 提示发送失败：{exc}", file=sys.stderr)
                state[state_key] = alert_key
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
