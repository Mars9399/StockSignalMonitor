"""Market-wide top mover discovery and direct buy-opportunity analysis.

The scanner is deliberately independent from the watchlist stream.  Yahoo's
US-market predefined gainers/losers screen supplies the broad-market
candidates; only the twenty displayed symbols need historical-bar downloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import queue
import threading

import pandas as pd
import yfinance as yf

from reliability import observation_reason
from signal_monitor import calculate_levels


@dataclass(frozen=True)
class MoverResult:
    side: str
    rank: int
    symbol: str
    name: str
    price: float
    change_pct: float
    volume: int
    buy_point: float
    sell_point: float
    opportunity: str
    tag: str
    quote_time: datetime | None


def analyze_mover_opportunity(values: dict) -> tuple[str, str]:
    """Return a concise decision label; price-channel state remains primary."""
    if not values.get("signal_ready", False):
        return "仅观察：历史不足", "OBSERVE"

    price = float(values["price"])
    buy_point = float(values["buy_point"])
    status = str(values["status"])
    if status == "SELL_ALERT":
        return "回避：已跌破卖出点", "AVOID"
    if status == "BUY_ALERT":
        extension = max(0.0, (price / max(buy_point, 0.01) - 1) * 100)
        if extension <= 3.0:
            return f"买入机会：突破 +{extension:.1f}%", "BUY"
        return f"等待回踩：高于买点 {extension:.1f}%", "EXTENDED"

    gap = max(0.0, (buy_point / max(price, 0.01) - 1) * 100)
    if gap <= 2.0:
        return f"接近买点：还差 {gap:.1f}%", "NEAR"
    return f"等待突破：还差 {gap:.1f}%", "WAIT"


def _quote_time(raw_value) -> datetime | None:
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo else raw_value.replace(tzinfo=timezone.utc)
    try:
        raw = float(raw_value)
        if not math.isfinite(raw) or raw <= 0:
            return None
        divisor = 1000 if raw > 10_000_000_000 else 1
        return datetime.fromtimestamp(raw / divisor, timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _history_for(data: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if not isinstance(data.columns, pd.MultiIndex):
        history = data.copy()
    elif symbol in data.columns.get_level_values(0):
        history = data[symbol].copy()
    elif symbol in data.columns.get_level_values(-1):
        history = data.xs(symbol, axis=1, level=-1).copy()
    else:
        raise ValueError("未取得历史日线")
    history.columns = [str(column).lower() for column in history.columns]
    return history.dropna(subset=["high", "low", "close"])


def _latest_intraday(data: pd.DataFrame, symbol: str) -> tuple[float, datetime] | None:
    """Extract the newest 1-minute close used to refresh a screener snapshot."""
    if data.empty:
        return None
    if not isinstance(data.columns, pd.MultiIndex):
        frame = data.copy()
    elif symbol in data.columns.get_level_values(0):
        frame = data[symbol].copy()
    elif symbol in data.columns.get_level_values(-1):
        frame = data.xs(symbol, axis=1, level=-1).copy()
    else:
        return None
    frame.columns = [str(column).lower() for column in frame.columns]
    if "close" not in frame:
        return None
    closes = frame["close"].dropna()
    if closes.empty:
        return None
    price = float(closes.iloc[-1])
    if not math.isfinite(price) or price <= 0:
        return None
    stamp = pd.Timestamp(closes.index[-1])
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return price, stamp.to_pydatetime()


class MarketMoverScanner:
    """Fetch the US-market top gainers and losers, then analyze twenty names."""

    def __init__(self, candidates_per_side: int = 50, result_count: int = 10):
        self.candidates_per_side = max(result_count, candidates_per_side)
        self.result_count = result_count

    def scan(self) -> tuple[list[MoverResult], list[MoverResult]]:
        screens = {
            "gainers": yf.screen("day_gainers", count=self.candidates_per_side),
            "losers": yf.screen("day_losers", count=self.candidates_per_side),
        }
        candidates: dict[str, list[dict]] = {}
        symbols: list[str] = []
        for side, payload in screens.items():
            valid: list[dict] = []
            for quote in payload.get("quotes", []):
                symbol = str(quote.get("symbol", "")).strip().upper()
                try:
                    price = float(quote.get("regularMarketPrice", 0))
                    change = float(quote.get("regularMarketChangePercent", 0))
                except (TypeError, ValueError):
                    continue
                if not symbol or not math.isfinite(price) or price <= 0 or not math.isfinite(change):
                    continue
                valid.append(quote)
                if symbol not in symbols:
                    symbols.append(symbol)
                if len(valid) >= self.candidates_per_side:
                    break
            candidates[side] = valid

        if not symbols:
            raise RuntimeError("全市场涨跌榜没有返回可用股票")

        # Yahoo's predefined screen can lag behind its chart endpoint. Refresh
        # the candidate pool with the newest one-minute close, recompute the
        # percentage move, then rank again before selecting the displayed ten.
        try:
            intraday = yf.download(
                symbols,
                period="1d",
                interval="1m",
                auto_adjust=False,
                group_by="ticker",
                threads=True,
                prepost=False,
                progress=False,
                timeout=20,
            )
            for quotes in candidates.values():
                for quote in quotes:
                    symbol = str(quote["symbol"]).upper()
                    latest = _latest_intraday(intraday, symbol)
                    if latest is None:
                        continue
                    price, stamp = latest
                    try:
                        previous_close = float(quote.get("regularMarketPreviousClose", 0))
                    except (TypeError, ValueError):
                        previous_close = 0.0
                    quote["_fresh_price"] = price
                    quote["_fresh_time"] = stamp
                    if previous_close > 0 and math.isfinite(previous_close):
                        quote["_fresh_change"] = (price / previous_close - 1) * 100
        except Exception:
            # A fresh screen is still useful if the intraday endpoint is
            # temporarily unavailable; its source timestamp remains visible.
            pass

        for side, quotes in candidates.items():
            quotes.sort(
                key=lambda quote: float(quote.get("_fresh_change", quote.get("regularMarketChangePercent", 0))),
                reverse=side == "gainers",
            )
            candidates[side] = quotes[: self.result_count]

        symbols = list(
            dict.fromkeys(
                str(quote["symbol"]).upper()
                for quotes in candidates.values()
                for quote in quotes
            )
        )

        history_data = yf.download(
            symbols,
            period="6mo",
            interval="1d",
            auto_adjust=False,
            group_by="ticker",
            threads=True,
            progress=False,
            timeout=20,
        )

        output: dict[str, list[MoverResult]] = {"gainers": [], "losers": []}
        for side, quotes in candidates.items():
            for rank, quote in enumerate(quotes, start=1):
                symbol = str(quote["symbol"]).upper()
                price = float(quote.get("_fresh_price", quote["regularMarketPrice"]))
                change = float(quote.get("_fresh_change", quote["regularMarketChangePercent"]))
                timestamp = _quote_time(quote.get("_fresh_time", quote.get("regularMarketTime")))
                try:
                    history = _history_for(history_data, symbol)
                    values = calculate_levels(history, price)
                    opportunity, tag = analyze_mover_opportunity(values)
                    reason = observation_reason(
                        price,
                        timestamp,
                        values.get("history_date"),
                        max_age_seconds=300,
                    )
                    if reason:
                        opportunity, tag = f"仅观察：{reason}", "OBSERVE"
                    buy_point = float(values["buy_point"])
                    sell_point = float(values["stop_point"])
                except Exception as exc:
                    opportunity, tag = f"分析失败：{str(exc)[:28]}", "ERROR"
                    buy_point = sell_point = 0.0

                try:
                    volume = max(0, int(float(quote.get("regularMarketVolume", 0) or 0)))
                except (TypeError, ValueError):
                    volume = 0
                output[side].append(
                    MoverResult(
                        side=side,
                        rank=rank,
                        symbol=symbol,
                        name=str(quote.get("shortName") or quote.get("longName") or symbol),
                        price=price,
                        change_pct=change,
                        volume=volume,
                        buy_point=buy_point,
                        sell_point=sell_point,
                        opportunity=opportunity,
                        tag=tag,
                        quote_time=timestamp,
                    )
                )
        return output["gainers"], output["losers"]


class MarketMoverWorker(threading.Thread):
    def __init__(self, events: queue.Queue, interval_seconds: int = 60):
        super().__init__(daemon=True)
        self.events = events
        self.interval_seconds = max(30, interval_seconds)
        self.stop_requested = threading.Event()
        self.refresh_requested = threading.Event()
        self.scanner = MarketMoverScanner()

    def run(self) -> None:
        while not self.stop_requested.is_set():
            self.events.put(("mover_status", "正在扫描美股全市场涨跌榜…"))
            try:
                gainers, losers = self.scanner.scan()
                self.events.put(("mover_results", gainers, losers, datetime.now(timezone.utc)))
            except Exception as exc:
                self.events.put(("mover_error", str(exc)))
            self.refresh_requested.wait(self.interval_seconds)
            self.refresh_requested.clear()
            if self.stop_requested.is_set():
                break
        self.events.put(("mover_stopped",))

    def refresh(self) -> None:
        self.refresh_requested.set()

    def stop(self) -> None:
        self.stop_requested.set()
        self.refresh_requested.set()
