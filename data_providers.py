"""Read-only market-data provider adapters.

No adapter imports a trading client or calls an order method.
"""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from signal_monitor import calculate_levels


class ProviderWorker(threading.Thread):
    provider_label = "行情"

    def __init__(self, symbols: list[str], events: queue.Queue):
        super().__init__(daemon=True)
        self.symbols = symbols
        self.events = events
        self.stop_requested = threading.Event()
        self.last_emitted: dict[str, float] = {}

    def emit_trade(self, symbol: str, price: float, timestamp) -> None:
        now = time.monotonic()
        if now - self.last_emitted.get(symbol, 0.0) < 0.25:
            return
        self.last_emitted[symbol] = now
        self.events.put(("trade", symbol, float(price), timestamp))

    def emit_snapshot(self, symbol: str, history: pd.DataFrame, price: float, timestamp) -> None:
        normalized = history.rename(columns={column: str(column).lower() for column in history.columns})
        values = calculate_levels(normalized, float(price))
        self.events.put(("snapshot", symbol, values, timestamp))

    def stop(self) -> None:
        self.stop_requested.set()


class AlpacaWorker(ProviderWorker):
    provider_label = "Alpaca IEX"

    def __init__(self, api_key: str, api_secret: str, symbols: list[str], events: queue.Queue):
        super().__init__(symbols, events)
        self.api_key = api_key
        self.api_secret = api_secret
        self.stream = None

    def run(self) -> None:
        from alpaca.data.enums import DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.live import StockDataStream
        from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
        from alpaca.data.timeframe import TimeFrame

        try:
            self.events.put(("connection", "Alpaca：正在加载历史日线…"))
            client = StockHistoricalDataClient(self.api_key, self.api_secret)
            now = datetime.now(timezone.utc)
            bars = client.get_stock_bars(
                StockBarsRequest(
                    symbol_or_symbols=self.symbols,
                    timeframe=TimeFrame.Day,
                    start=now - timedelta(days=420),
                    end=now - timedelta(minutes=16),
                    feed=DataFeed.IEX,
                )
            ).df
            latest = client.get_stock_latest_trade(
                StockLatestTradeRequest(symbol_or_symbols=self.symbols, feed=DataFeed.IEX)
            )
            for symbol in self.symbols:
                try:
                    history = bars.xs(symbol, level="symbol") if getattr(bars.index, "nlevels", 1) > 1 else bars
                    self.emit_snapshot(symbol, history, float(latest[symbol].price), latest[symbol].timestamp)
                except Exception as exc:
                    self.events.put(("symbol_error", symbol, str(exc)))
            if self.stop_requested.is_set():
                return

            self.stream = StockDataStream(self.api_key, self.api_secret, feed=DataFeed.IEX)

            async def on_trade(trade) -> None:
                self.emit_trade(trade.symbol, trade.price, trade.timestamp)

            self.stream.subscribe_trades(on_trade, *self.symbols)
            self.events.put(("connection", "Alpaca IEX 流式行情已连接"))
            self.stream.run()
        except Exception as exc:
            if not self.stop_requested.is_set():
                self.events.put(("error", f"Alpaca 连接失败：{exc}"))
        finally:
            self.events.put(("stopped",))

    def stop(self) -> None:
        super().stop()
        if self.stream is not None:
            try:
                self.stream.stop()
            except Exception:
                pass


class YahooWorker(ProviderWorker):
    provider_label = "Yahoo Finance"

    def __init__(self, symbols: list[str], events: queue.Queue):
        super().__init__(symbols, events)
        self.stream = None

    def run(self) -> None:
        try:
            self.events.put(("connection", "Yahoo：正在加载历史日线…"))
            data = yf.download(
                self.symbols,
                period="2y",
                interval="1d",
                auto_adjust=False,
                group_by="ticker",
                threads=True,
                progress=False,
                timeout=20,
            )
            for symbol in self.symbols:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        history = data[symbol].copy()
                    else:
                        history = data.copy()
                    history.columns = [str(column).lower() for column in history.columns]
                    history = history.dropna(subset=["close"])
                    price = float(history["close"].iloc[-1])
                    self.emit_snapshot(symbol, history, price, history.index[-1].to_pydatetime())
                except Exception as exc:
                    self.events.put(("symbol_error", symbol, str(exc)))
            if self.stop_requested.is_set():
                return

            self.stream = yf.WebSocket(verbose=False)
            self.stream.subscribe(self.symbols)

            def on_message(message: dict) -> None:
                symbol = str(message.get("id", "")).upper()
                price = message.get("price")
                raw_time = message.get("time")
                if symbol not in self.symbols or price is None:
                    return
                if raw_time:
                    divisor = 1000 if float(raw_time) > 10_000_000_000 else 1
                    timestamp = datetime.fromtimestamp(float(raw_time) / divisor, timezone.utc)
                else:
                    timestamp = datetime.now(timezone.utc)
                self.emit_trade(symbol, float(price), timestamp)

            self.events.put(("connection", "Yahoo Finance 流式行情已连接（个人研究用途）"))
            self.stream.listen(on_message)
        except Exception as exc:
            if not self.stop_requested.is_set():
                self.events.put(("error", f"Yahoo Finance 连接失败：{exc}"))
        finally:
            self.events.put(("stopped",))

    def stop(self) -> None:
        super().stop()
        if self.stream is not None:
            try:
                self.stream.close()
            except Exception:
                pass


class MassiveWorker(ProviderWorker):
    provider_label = "Massive / Polygon"

    def __init__(self, api_key: str, delayed: bool, symbols: list[str], events: queue.Queue):
        super().__init__(symbols, events)
        self.api_key = api_key
        self.delayed = delayed
        self.stream = None

    def run(self) -> None:
        from polygon import RESTClient, WebSocketClient
        from polygon.websocket.models import Feed, Market

        try:
            self.events.put(("connection", "Massive/Polygon：正在加载历史日线…"))
            rest = RESTClient(self.api_key)
            today = datetime.now(timezone.utc).date()
            start = today - timedelta(days=420)
            for symbol in self.symbols:
                try:
                    aggs = list(rest.list_aggs(symbol, 1, "day", start, today, adjusted=True, limit=50000))
                    history = pd.DataFrame(
                        [{"open": item.open, "high": item.high, "low": item.low, "close": item.close, "volume": item.volume} for item in aggs]
                    )
                    last_trade = rest.get_last_trade(symbol)
                    price = float(last_trade.price)
                    timestamp = datetime.fromtimestamp(float(last_trade.timestamp) / 1_000_000_000, timezone.utc)
                    self.emit_snapshot(symbol, history, price, timestamp)
                except Exception as exc:
                    self.events.put(("symbol_error", symbol, str(exc)))
            if self.stop_requested.is_set():
                return

            feed = Feed.Delayed if self.delayed else Feed.RealTime
            self.stream = WebSocketClient(api_key=self.api_key, feed=feed, market=Market.Stocks)
            self.stream.subscribe(*[f"T.{symbol}" for symbol in self.symbols])

            def on_messages(messages) -> None:
                for message in messages:
                    symbol = getattr(message, "symbol", None)
                    price = getattr(message, "price", None)
                    raw_time = getattr(message, "timestamp", None)
                    if symbol and price is not None:
                        timestamp = datetime.fromtimestamp(float(raw_time) / 1000, timezone.utc) if raw_time else datetime.now(timezone.utc)
                        self.emit_trade(symbol, float(price), timestamp)

            label = "延迟" if self.delayed else "实时"
            self.events.put(("connection", f"Massive/Polygon {label}流式行情已连接"))
            self.stream.run(on_messages)
        except Exception as exc:
            if not self.stop_requested.is_set():
                self.events.put(("error", f"Massive/Polygon 连接失败：{exc}"))
        finally:
            self.events.put(("stopped",))

    def stop(self) -> None:
        super().stop()
        if self.stream is not None:
            try:
                self.stream.close()
            except Exception:
                pass


class IBKRWorker(ProviderWorker):
    provider_label = "IBKR Gateway"

    def __init__(self, host: str, port: int, client_id: int, market_data_type: int, symbols: list[str], events: queue.Queue):
        super().__init__(symbols, events)
        self.host = host
        self.port = port
        self.client_id = client_id
        self.market_data_type = market_data_type
        self.app = None

    def run(self) -> None:
        from ibapi.client import EClient
        from ibapi.contract import Contract
        from ibapi.wrapper import EWrapper

        outer = self

        class DataApp(EWrapper, EClient):
            def __init__(self):
                EClient.__init__(self, self)
                self.ready = threading.Event()
                self.history: dict[int, list[dict]] = {}
                self.history_done: dict[int, threading.Event] = {}
                self.req_symbols: dict[int, str] = {}

            def nextValidId(self, orderId):
                self.ready.set()

            def historicalData(self, reqId, bar):
                self.history.setdefault(reqId, []).append(
                    {"open": float(bar.open), "high": float(bar.high), "low": float(bar.low), "close": float(bar.close), "volume": float(bar.volume)}
                )

            def historicalDataEnd(self, reqId, start, end):
                if reqId in self.history_done:
                    self.history_done[reqId].set()

            def tickPrice(self, reqId, tickType, price, attrib):
                # Last, close, delayed-last, delayed-close.
                if tickType in {4, 9, 68, 75} and price and price > 0:
                    symbol = self.req_symbols.get(reqId)
                    if symbol:
                        outer.emit_trade(symbol, float(price), datetime.now(timezone.utc))

            def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
                if errorCode in {2104, 2106, 2158}:
                    return
                outer.events.put(("connection", f"IBKR {errorCode}: {errorString}"))

        def stock_contract(symbol: str):
            contract = Contract()
            contract.symbol = symbol
            contract.secType = "STK"
            contract.exchange = "SMART"
            contract.currency = "USD"
            return contract

        try:
            self.events.put(("connection", f"IBKR：连接 {self.host}:{self.port}…"))
            self.app = DataApp()
            self.app.connect(self.host, self.port, self.client_id)
            api_thread = threading.Thread(target=self.app.run, daemon=True)
            api_thread.start()
            if not self.app.ready.wait(12):
                raise TimeoutError("IB Gateway 未响应；请确认已登录并启用 Socket API")

            self.app.reqMarketDataType(self.market_data_type)
            for index, symbol in enumerate(self.symbols):
                if self.stop_requested.is_set():
                    return
                req_id = 1000 + index
                done = threading.Event()
                self.app.history[req_id] = []
                self.app.history_done[req_id] = done
                self.app.reqHistoricalData(req_id, stock_contract(symbol), "", "2 Y", "1 day", "TRADES", 1, 1, False, [])
                if not done.wait(35):
                    self.events.put(("symbol_error", symbol, "IBKR 历史日线请求超时"))
                    self.app.cancelHistoricalData(req_id)
                    continue
                history = pd.DataFrame(self.app.history.get(req_id, []))
                if history.empty:
                    self.events.put(("symbol_error", symbol, "IBKR 未返回历史日线"))
                    continue
                price = float(history["close"].iloc[-1])
                self.emit_snapshot(symbol, history, price, datetime.now(timezone.utc))

            for index, symbol in enumerate(self.symbols):
                req_id = 2000 + index
                self.app.req_symbols[req_id] = symbol
                self.app.reqMktData(req_id, stock_contract(symbol), "", False, False, [])
            mode = {1: "实时", 2: "冻结", 3: "延迟/自动实时", 4: "延迟冻结"}.get(self.market_data_type, str(self.market_data_type))
            self.events.put(("connection", f"IBKR Gateway 行情已连接 · {mode}"))
            while not self.stop_requested.wait(0.5) and self.app.isConnected():
                pass
        except Exception as exc:
            if not self.stop_requested.is_set():
                self.events.put(("error", f"IBKR Gateway 连接失败：{exc}"))
        finally:
            if self.app is not None and self.app.isConnected():
                self.app.disconnect()
            self.events.put(("stopped",))

    def stop(self) -> None:
        super().stop()
        if self.app is not None:
            try:
                for index in range(len(self.symbols)):
                    self.app.cancelMktData(2000 + index)
                self.app.disconnect()
            except Exception:
                pass
