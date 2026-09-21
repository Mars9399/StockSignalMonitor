"""Small read-only TWS helpers for account summary and intraday charts."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import threading


INFORMATIONAL_CODES = {2104, 2106, 2107, 2108, 2158, 2176}
ACCOUNT_TAGS = (
    "NetLiquidation",
    "TotalCashValue",
    "BuyingPower",
    "AvailableFunds",
    "ExcessLiquidity",
    "MaintMarginReq",
    "UnrealizedPnL",
    "RealizedPnL",
)


def auxiliary_client_id(base_client_id: int, offset: int) -> int:
    """Return a stable valid client id that will not collide with position sync."""
    return (max(0, int(base_client_id)) + max(1, int(offset))) % 2_147_483_647


def _number(value: str) -> float | None:
    try:
        result = float(str(value).replace(",", ""))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def fetch_account_summary(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 118,
    account_id: str = "",
    timeout: float = 15,
) -> dict:
    """Read a single account's headline balances without placing orders."""
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper

    done = threading.Event()
    ready = threading.Event()
    records: dict[str, dict[str, tuple[str, str]]] = {}
    error_message: list[str] = []

    class AccountApp(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)

        def nextValidId(self, orderId):
            ready.set()

        def accountSummary(self, reqId, account, tag, value, currency):
            if account_id and account.casefold() != account_id.casefold():
                return
            account_values = records.setdefault(account, {})
            existing = account_values.get(tag)
            if existing is None or currency in {"USD", "BASE"}:
                account_values[tag] = (value, currency)

        def accountSummaryEnd(self, reqId):
            done.set()

        def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
            if errorCode in INFORMATIONAL_CODES:
                return
            error_message.append(f"TWS {errorCode}: {errorString}")
            ready.set()
            done.set()

    app = AccountApp()
    try:
        app.connect(host, port, client_id)
        api_thread = threading.Thread(target=app.run, daemon=True)
        api_thread.start()
        if not ready.wait(min(timeout, 10)):
            raise TimeoutError("TWS 账户接口未响应")
        if error_message:
            raise ConnectionError(error_message[-1])
        app.reqAccountSummary(9101, "All", ",".join(ACCOUNT_TAGS))
        if not done.wait(timeout):
            raise TimeoutError("读取 TWS 账户明细超时")
        if error_message:
            raise ConnectionError(error_message[-1])
        if not records:
            if account_id:
                raise ValueError(f"TWS 未返回账户 {account_id} 的明细")
            raise ValueError("TWS 未返回账户明细")
        selected_account = account_id or sorted(records)[0]
        if selected_account not in records:
            matching = next((key for key in records if key.casefold() == selected_account.casefold()), None)
            if matching is None:
                raise ValueError(f"TWS 未返回账户 {selected_account} 的明细")
            selected_account = matching
        raw = records[selected_account]
        result = {"account": selected_account, "currency": "USD"}
        for tag in ACCOUNT_TAGS:
            if tag not in raw:
                continue
            value, currency = raw[tag]
            number = _number(value)
            if number is not None:
                result[tag] = number
            if currency and currency not in {"BASE"}:
                result["currency"] = currency
        return result
    finally:
        try:
            app.cancelAccountSummary(9101)
        except Exception:
            pass
        if app.isConnected():
            app.disconnect()


def _bar_time(raw_value) -> datetime:
    text = str(raw_value).strip()
    try:
        return datetime.fromtimestamp(float(text), timezone.utc)
    except (TypeError, ValueError, OSError):
        normalized = " ".join(text.split())[:17]
        parsed = datetime.strptime(normalized, "%Y%m%d %H:%M:%S")
        return parsed.replace(tzinfo=timezone.utc)


def fetch_intraday_bars(
    symbol: str,
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 119,
    timeout: float = 25,
) -> list[dict]:
    """Fetch two days of 5-minute TWS bars for a local chart."""
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.wrapper import EWrapper

    done = threading.Event()
    ready = threading.Event()
    bars: list[dict] = []
    error_message: list[str] = []

    class ChartApp(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)

        def nextValidId(self, orderId):
            ready.set()

        def historicalData(self, reqId, bar):
            try:
                bars.append(
                    {
                        "time": _bar_time(bar.date),
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": float(bar.volume),
                    }
                )
            except (TypeError, ValueError, OSError):
                return

        def historicalDataEnd(self, reqId, start, end):
            done.set()

        def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
            if errorCode in INFORMATIONAL_CODES:
                return
            error_message.append(f"TWS {errorCode}: {errorString}")
            ready.set()
            done.set()

    app = ChartApp()
    try:
        app.connect(host, port, client_id)
        api_thread = threading.Thread(target=app.run, daemon=True)
        api_thread.start()
        if not ready.wait(min(timeout, 10)):
            raise TimeoutError("TWS 图表接口未响应")
        if error_message:
            raise ConnectionError(error_message[-1])

        contract = Contract()
        contract.symbol = symbol.strip().upper()
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        app.reqHistoricalData(9201, contract, "", "2 D", "5 mins", "TRADES", 0, 2, False, [])
        if not done.wait(timeout):
            raise TimeoutError("读取 TWS 5 分钟图表超时")
        if error_message:
            raise ConnectionError(error_message[-1])
        valid = [
            bar for bar in bars
            if all(math.isfinite(float(bar[key])) and float(bar[key]) > 0 for key in ("open", "high", "low", "close"))
        ]
        if not valid:
            raise ValueError("TWS 未返回可用的 5 分钟行情；请检查市场数据权限")
        valid.sort(key=lambda item: item["time"])
        return valid
    finally:
        try:
            app.cancelHistoricalData(9201)
        except Exception:
            pass
        if app.isConnected():
            app.disconnect()
