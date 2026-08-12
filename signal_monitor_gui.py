"""Desktop GUI for read-only, multi-provider US-stock signal monitoring."""

from __future__ import annotations

import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, ttk

from dotenv import load_dotenv
import yfinance as yf

from data_providers import AlpacaWorker, IBKRWorker, MassiveWorker, ProviderWorker, YahooWorker
import signal_monitor as signal_core
from signal_monitor import calculate_levels, load_state, record_alert, save_state, send_discord


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
BASE_DIR = (
    Path(os.getenv("LOCALAPPDATA", APP_DIR)) / "StockSignalMonitor"
    if getattr(sys, "frozen", False)
    else APP_DIR
)
BASE_DIR.mkdir(parents=True, exist_ok=True)
signal_core.BASE_DIR = BASE_DIR
signal_core.STATE_FILE = BASE_DIR / "signal_state.json"
signal_core.ALERT_FILE = BASE_DIR / "signal_alerts.csv"
WATCHLIST_FILE = BASE_DIR / "watchlist.json"
POSITIONS_FILE = BASE_DIR / "positions.json"
SETTINGS_FILE = BASE_DIR / "risk_settings.json"
NAMES_FILE = BASE_DIR / "stock_names.json"
PROVIDER_FILE = BASE_DIR / "data_provider.txt"
DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
DEFAULT_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corp.",
    "NVDA": "NVIDIA Corp.",
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
}
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,11}$")


def read_watchlist() -> list[str]:
    if WATCHLIST_FILE.exists():
        try:
            values = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
            symbols = [str(value).strip().upper() for value in values]
            valid = list(dict.fromkeys(value for value in symbols if SYMBOL_PATTERN.fullmatch(value)))
            if valid:
                return valid
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    env_symbols = [
        value.strip().upper()
        for value in os.getenv("WATCH_SYMBOLS", "").split(",")
        if value.strip()
    ]
    return env_symbols or DEFAULT_SYMBOLS.copy()


def write_watchlist(symbols: list[str]) -> None:
    WATCHLIST_FILE.write_text(json.dumps(symbols, indent=2), encoding="utf-8")


def read_positions() -> dict[str, dict[str, float]]:
    if not POSITIONS_FILE.exists():
        return {}
    try:
        raw = json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))
        return {
            str(symbol).upper(): {
                "avg_cost": max(0.0, float(values.get("avg_cost", 0))),
                "quantity": max(0, int(values.get("quantity", 0))),
            }
            for symbol, values in raw.items()
            if isinstance(values, dict)
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def write_positions(positions: dict[str, dict[str, float]]) -> None:
    POSITIONS_FILE.write_text(json.dumps(positions, indent=2), encoding="utf-8")


def read_risk_settings() -> dict[str, float]:
    defaults = {"account_value": 100000.0, "risk_pct": 1.0, "max_position_pct": 10.0}
    if not SETTINGS_FILE.exists():
        return defaults
    try:
        values = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return {
            "account_value": max(1.0, float(values.get("account_value", defaults["account_value"]))),
            "risk_pct": min(10.0, max(0.1, float(values.get("risk_pct", defaults["risk_pct"])))),
            "max_position_pct": min(100.0, max(1.0, float(values.get("max_position_pct", defaults["max_position_pct"])))),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return defaults


def write_risk_settings(settings: dict[str, float]) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def read_stock_names() -> dict[str, str]:
    names = DEFAULT_NAMES.copy()
    if NAMES_FILE.exists():
        try:
            cached = json.loads(NAMES_FILE.read_text(encoding="utf-8"))
            names.update({str(key).upper(): str(value) for key, value in cached.items() if value})
        except (OSError, TypeError, json.JSONDecodeError):
            pass
    return names


def write_stock_names(names: dict[str, str]) -> None:
    NAMES_FILE.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")


def read_provider() -> str:
    allowed = {"Alpaca IEX", "Yahoo Finance", "Massive / Polygon", "IBKR Gateway"}
    if PROVIDER_FILE.exists():
        try:
            value = PROVIDER_FILE.read_text(encoding="utf-8").strip()
            if value in allowed:
                return value
        except OSError:
            pass
    return os.getenv("DATA_PROVIDER", "Alpaca IEX")


def display_status(values: dict, price: float) -> tuple[str, str]:
    if not values.get("signal_ready", True):
        return f"数据不足 {int(values.get('history_days', 0))}日", "DATA_SHORT"
    if values["status"] == "NO_SIGNAL":
        return "趋势不符", "NO_SIGNAL"
    if values["status"] == "BUY_ALERT":
        return "买入提示", "BUY_ALERT"
    gap_pct = (float(values["buy_point"]) / price - 1) * 100 if price > 0 else 999
    if gap_pct <= 3:
        return f"接近买点 {gap_pct:.1f}%", "NEAR"
    return f"等待突破 {gap_pct:.1f}%", "WATCH"


def build_position_plan(
    values: dict,
    position: dict[str, float],
    account_value: float,
    risk_pct: float,
    max_position_pct: float,
) -> dict[str, float | int | str]:
    if not values.get("signal_ready", True):
        return {
            "position_stop": 0.0,
            "target_2r": 0.0,
            "target_3r": 0.0,
            "max_shares": 0,
            "action": "历史不足：暂停买卖与仓位意见",
        }
    price = float(values["price"])
    buy_point = float(values["buy_point"])
    entry_stop = float(values["stop_point"])
    atr = max(0.01, float(values["atr14"]))
    sma50 = float(values["sma50"])
    quantity = int(position.get("quantity", 0))
    avg_cost = float(position.get("avg_cost", 0))

    # A held position uses a volatility-aware trailing risk line that always
    # remains below the current market price. A new position uses entry_stop.
    if quantity > 0 and avg_cost > 0:
        trailing_candidate = max(price - 2 * atr, sma50 if sma50 < price else 0.01)
        position_stop = min(trailing_candidate, price - 0.5 * atr)
        position_stop = max(0.01, position_stop)
        initial_risk = max(avg_cost - position_stop, atr)
        target_2r = avg_cost + 2 * initial_risk
        target_3r = avg_cost + 3 * initial_risk
        sizing_price = price
        sizing_stop = position_stop
    else:
        position_stop = entry_stop
        initial_risk = max(buy_point - entry_stop, atr)
        target_2r = buy_point + 2 * initial_risk
        target_3r = buy_point + 3 * initial_risk
        sizing_price = buy_point
        sizing_stop = entry_stop

    risk_budget = account_value * (risk_pct / 100)
    risk_per_share = max(sizing_price - sizing_stop, atr * 0.5, 0.01)
    max_by_risk = math.floor(risk_budget / risk_per_share)
    max_by_value = math.floor((account_value * max_position_pct / 100) / max(sizing_price, 0.01))
    max_shares = max(0, min(max_by_risk, max_by_value))

    if quantity > 0 and avg_cost > 0:
        if price <= position_stop:
            action = f"风控线触发：规则减 {quantity} 股"
        elif quantity > max_shares:
            action = f"超风险上限：规则减 {quantity - max_shares} 股"
        elif price >= target_3r:
            action = f"达到3R：规则减 {max(1, math.ceil(quantity * 0.50))} 股"
        elif price >= target_2r:
            action = f"达到2R：规则减 {max(1, math.ceil(quantity * 0.25))} 股"
        elif values["status"] == "BUY_ALERT" and quantity < max_shares:
            action = f"突破确认：规则最多加 {max_shares - quantity} 股"
        else:
            action = "持有观察，不追价"
    elif values["status"] == "BUY_ALERT":
        action = f"突破确认：风险上限 {max_shares} 股"
    else:
        action = f"等待信号：候选上限 {max_shares} 股"

    return {
        "position_stop": position_stop,
        "target_2r": target_2r,
        "target_3r": target_3r,
        "max_shares": max_shares,
        "action": action,
    }


class SignalMonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("美股买卖点与仓位监控 · 只读模式")
        self.root.geometry("1420x790")
        self.root.minsize(1120, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.events: queue.Queue = queue.Queue()
        self.worker: ProviderWorker | None = None
        self.running = False
        self.symbols = read_watchlist()
        self.levels: dict[str, dict] = {}
        self.alert_state = load_state()
        self.positions = read_positions()
        self.risk_settings = read_risk_settings()
        self.stock_names = read_stock_names()
        self.last_log_at: dict[str, float] = {}
        self.last_logged_status: dict[str, str] = {}
        load_dotenv(BASE_DIR / ".env")
        self.provider_var = tk.StringVar(value=read_provider())
        self.feed_var = tk.StringVar(value=self.provider_var.get())

        self._configure_style()
        self._build_ui()
        self._populate_symbols()
        self._resolve_missing_names(self.symbols)
        self.root.after(100, self._process_events)

    def _configure_style(self) -> None:
        self.root.configure(bg="#0b1220")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("App.TFrame", background="#0b1220")
        style.configure("Card.TFrame", background="#111b2e")
        style.configure("Title.TLabel", background="#0b1220", foreground="#f4f7fb", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Sub.TLabel", background="#0b1220", foreground="#93a4bd", font=("Microsoft YaHei UI", 9))
        style.configure("Card.TLabel", background="#111b2e", foreground="#dbe6f4", font=("Microsoft YaHei UI", 10))
        style.configure("Hint.TLabel", background="#111b2e", foreground="#7f93af", font=("Microsoft YaHei UI", 8))
        style.configure("Safe.TLabel", background="#123627", foreground="#65e6a2", padding=(10, 5), font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Feed.TLabel", background="#26324a", foreground="#b8c7db", padding=(10, 5), font=("Microsoft YaHei UI", 9))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(14, 8), background="#3b82f6", foreground="white")
        style.map("Accent.TButton", background=[("active", "#2563eb"), ("disabled", "#334155")])
        style.configure("Secondary.TButton", font=("Microsoft YaHei UI", 10), padding=(12, 8), background="#24324a", foreground="#e2e8f0")
        style.map("Secondary.TButton", background=[("active", "#334155")])
        style.configure("Treeview", background="#111b2e", fieldbackground="#111b2e", foreground="#e5edf7", rowheight=34, borderwidth=0, font=("Consolas", 10))
        style.configure("Treeview.Heading", background="#1b2940", foreground="#aebdd0", relief="flat", font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#254b7c")])

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=22)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text="美股买卖点与仓位监控", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="只读 · 永不下单", style="Safe.TLabel").pack(side="right", padx=(8, 0))
        ttk.Label(header, textvariable=self.feed_var, style="Feed.TLabel").pack(side="right")

        controls = ttk.Frame(outer, style="Card.TFrame", padding=14)
        controls.pack(fill="x", pady=(0, 14))
        ttk.Label(controls, text="股票代码", style="Card.TLabel").pack(side="left", padx=(0, 8))
        self.symbol_entry = tk.Entry(
            controls,
            width=14,
            bg="#0b1324",
            fg="#f4f7fb",
            insertbackground="white",
            relief="flat",
            font=("Consolas", 12),
        )
        self.symbol_entry.pack(side="left", ipady=7, padx=(0, 8))
        self.symbol_entry.bind("<Return>", lambda _event: self.add_symbol())
        ttk.Button(controls, text="添加", style="Secondary.TButton", command=self.add_symbol).pack(side="left", padx=3)
        ttk.Button(controls, text="移除所选", style="Secondary.TButton", command=self.remove_selected).pack(side="left", padx=3)
        ttk.Button(controls, text="配置密钥", style="Secondary.TButton", command=self.open_api_config).pack(side="left", padx=3)
        ttk.Label(controls, text="数据源", style="Card.TLabel").pack(side="left", padx=(16, 6))
        self.provider_combo = ttk.Combobox(
            controls,
            textvariable=self.provider_var,
            values=("Alpaca IEX", "Yahoo Finance", "Massive / Polygon", "IBKR Gateway"),
            width=18,
            state="readonly",
        )
        self.provider_combo.pack(side="left", padx=(0, 6), ipady=5)
        self.provider_combo.bind("<<ComboboxSelected>>", self.on_provider_selected)
        self.stop_button = ttk.Button(controls, text="停止", style="Secondary.TButton", command=self.stop_monitoring, state="disabled")
        self.stop_button.pack(side="right", padx=(6, 0))
        self.start_button = ttk.Button(controls, text="启动流式监控", style="Accent.TButton", command=self.start_monitoring)
        self.start_button.pack(side="right")

        position_card = ttk.Frame(outer, style="Card.TFrame", padding=14)
        position_card.pack(fill="x", pady=(0, 14))
        self.selected_symbol_var = tk.StringVar(value="先在下方选择股票")
        ttk.Label(position_card, textvariable=self.selected_symbol_var, style="Card.TLabel").pack(side="left", padx=(0, 12))
        ttk.Label(position_card, text="持仓均价", style="Hint.TLabel").pack(side="left")
        self.avg_cost_entry = self._dark_entry(position_card, 10)
        self.avg_cost_entry.pack(side="left", padx=(5, 12), ipady=5)
        ttk.Label(position_card, text="持股数量", style="Hint.TLabel").pack(side="left")
        self.quantity_entry = self._dark_entry(position_card, 8)
        self.quantity_entry.pack(side="left", padx=(5, 12), ipady=5)
        ttk.Button(position_card, text="保存持仓", style="Secondary.TButton", command=self.save_position).pack(side="left", padx=(0, 18))

        ttk.Label(position_card, text="账户规模", style="Hint.TLabel").pack(side="left")
        self.account_entry = self._dark_entry(position_card, 11)
        self.account_entry.insert(0, f"{self.risk_settings['account_value']:.0f}")
        self.account_entry.pack(side="left", padx=(5, 10), ipady=5)
        ttk.Label(position_card, text="风险%", style="Hint.TLabel").pack(side="left")
        self.risk_entry = self._dark_entry(position_card, 5)
        self.risk_entry.insert(0, f"{self.risk_settings['risk_pct']:g}")
        self.risk_entry.pack(side="left", padx=(5, 10), ipady=5)
        ttk.Label(position_card, text="单股上限%", style="Hint.TLabel").pack(side="left")
        self.max_position_entry = self._dark_entry(position_card, 5)
        self.max_position_entry.insert(0, f"{self.risk_settings['max_position_pct']:g}")
        self.max_position_entry.pack(side="left", padx=(5, 10), ipady=5)
        ttk.Button(position_card, text="保存风控", style="Secondary.TButton", command=self.save_risk_settings).pack(side="left")

        table_card = ttk.Frame(outer, style="Card.TFrame", padding=1)
        table_card.pack(fill="both", expand=True)
        columns = ("symbol", "name", "price", "buy", "stop", "avg", "qty", "sell", "status", "quality", "action", "updated")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="extended")
        headings = {
            "symbol": "股票",
            "name": "股票名称",
            "price": "实时价格",
            "buy": "买入/突破加仓点",
            "stop": "风险减仓点",
            "avg": "持仓均价",
            "qty": "股数",
            "sell": "盈利减仓点 2R / 3R",
            "status": "状态",
            "quality": "数据/模型",
            "action": "到价后加/减多少股",
            "updated": "最近成交",
        }
        widths = {"symbol": 65, "name": 160, "price": 90, "buy": 110, "stop": 100, "avg": 90, "qty": 50, "sell": 170, "status": 130, "quality": 150, "action": 230, "updated": 145}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="center")
        self.tree.tag_configure("BUY_ALERT", foreground="#63e6a4")
        self.tree.tag_configure("NEAR", foreground="#7dd3fc")
        self.tree.tag_configure("WATCH", foreground="#f8cf67")
        self.tree.tag_configure("NO_SIGNAL", foreground="#91a3bb")
        self.tree.tag_configure("DATA_SHORT", foreground="#ff9f7a")
        self.tree.tag_configure("ERROR", foreground="#ff7b87")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        footer = ttk.Frame(outer, style="App.TFrame")
        footer.pack(fill="x", pady=(14, 0))
        self.connection_var = tk.StringVar(value="已停止 · 添加股票后点击“启动流式监控”")
        ttk.Label(footer, textvariable=self.connection_var, style="Sub.TLabel").pack(side="left")
        self.count_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.count_var, style="Sub.TLabel").pack(side="right")

        log_header = ttk.Frame(outer, style="App.TFrame")
        log_header.pack(fill="x", pady=(10, 4))
        ttk.Label(log_header, text="后台实时日志", style="Sub.TLabel").pack(side="left")
        ttk.Button(log_header, text="清空日志", style="Secondary.TButton", command=self.clear_log).pack(side="right")

        self.alert_text = tk.Text(
            outer,
            height=8,
            bg="#0a1020",
            fg="#c9d6e7",
            relief="flat",
            state="disabled",
            font=("Microsoft YaHei UI", 9),
            padx=10,
            pady=8,
        )
        self.alert_text.pack(fill="x")
        self._append_log("准备就绪。监控器仅使用市场数据接口，不具备交易能力。")

    def _dark_entry(self, parent, width: int) -> tk.Entry:
        return tk.Entry(
            parent,
            width=width,
            bg="#0b1324",
            fg="#f4f7fb",
            insertbackground="white",
            relief="flat",
            justify="center",
            font=("Consolas", 10),
        )

    def open_api_config(self) -> None:
        env_path = BASE_DIR / ".env"
        if not env_path.exists():
            env_path.write_text(
                "# Select: Alpaca IEX, Yahoo Finance, Massive / Polygon, IBKR Gateway\n"
                "DATA_PROVIDER=Alpaca IEX\n\n"
                "# Alpaca credentials\n"
                "ALPACA_API_KEY=replace_with_your_key\n"
                "ALPACA_API_SECRET=replace_with_your_secret\n\n"
                "# Massive / Polygon credentials and feed\n"
                "MASSIVE_API_KEY=replace_with_your_key\n"
                "MASSIVE_DELAYED=true\n\n"
                "# IB Gateway: Paper 4002, Live 4001. Data type: 1 live, 2 frozen, 3 delayed, 4 delayed-frozen\n"
                "IBKR_HOST=127.0.0.1\n"
                "IBKR_PORT=4002\n"
                "IBKR_CLIENT_ID=17\n"
                "IBKR_MARKET_DATA_TYPE=3\n\n"
                "DISCORD_WEBHOOK_URL=\n",
                encoding="utf-8",
            )
        try:
            subprocess.Popen(["notepad.exe", str(env_path)])
            self._append_log(f"已打开密钥配置：{env_path}")
        except OSError as exc:
            messagebox.showerror("无法打开配置", f"请手动编辑：\n{env_path}\n\n{exc}")

    def on_provider_selected(self, _event=None) -> None:
        provider = self.provider_var.get()
        self.feed_var.set(provider)
        PROVIDER_FILE.write_text(provider, encoding="utf-8")
        self._append_log(f"数据源已切换为 {provider}；点击启动后生效。")

    def _resolve_missing_names(self, symbols: list[str]) -> None:
        missing = [symbol for symbol in symbols if symbol not in self.stock_names]
        if not missing:
            return

        def worker() -> None:
            for symbol in missing:
                name = symbol
                try:
                    info = yf.Ticker(symbol).get_info()
                    name = str(info.get("shortName") or info.get("longName") or symbol)
                except Exception:
                    pass
                self.events.put(("stock_name", symbol, name))

        threading.Thread(target=worker, daemon=True).start()

    def _populate_symbols(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for symbol in self.symbols:
            position = self.positions.get(symbol, {})
            avg_cost = float(position.get("avg_cost", 0))
            quantity = int(position.get("quantity", 0))
            self.tree.insert(
                "", "end", iid=symbol,
                values=(symbol, self.stock_names.get(symbol, "查询中…"), "—", "—", "—", f"${avg_cost:,.2f}" if avg_cost else "—", quantity or "—", "—", "待启动", "—", "—", "—"),
            )
        self.count_var.set(f"监控 {len(self.symbols)} 只股票")

    def add_symbol(self) -> None:
        symbol = self.symbol_entry.get().strip().upper()
        if not SYMBOL_PATTERN.fullmatch(symbol):
            messagebox.showwarning("代码无效", "请输入有效的美股代码，例如 AAPL、SPY 或 BRK.B。")
            return
        if symbol in self.symbols:
            self.tree.selection_set(symbol)
            return
        self.symbols.append(symbol)
        write_watchlist(self.symbols)
        self.tree.insert("", "end", iid=symbol, values=(symbol, self.stock_names.get(symbol, "查询中…"), "—", "—", "—", "—", "—", "—", "待启动", "—", "—", "—"))
        self.symbol_entry.delete(0, "end")
        self.count_var.set(f"监控 {len(self.symbols)} 只股票")
        self._resolve_missing_names([symbol])
        if self.running:
            self._append_log(f"已添加 {symbol}；停止并重新启动后应用新的订阅。")

    def remove_selected(self) -> None:
        selected = list(self.tree.selection())
        if not selected:
            return
        self.symbols = [symbol for symbol in self.symbols if symbol not in selected]
        for symbol in selected:
            self.tree.delete(symbol)
            self.levels.pop(symbol, None)
        write_watchlist(self.symbols)
        self.count_var.set(f"监控 {len(self.symbols)} 只股票")
        if self.running:
            self._append_log("监控列表已改变；停止并重新启动后应用新的订阅。")

    def on_tree_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        symbol = selected[0]
        position = self.positions.get(symbol, {"avg_cost": 0, "quantity": 0})
        self.selected_symbol_var.set(f"所选：{symbol}")
        self.avg_cost_entry.delete(0, "end")
        self.quantity_entry.delete(0, "end")
        if float(position.get("avg_cost", 0)) > 0:
            self.avg_cost_entry.insert(0, f"{float(position['avg_cost']):.4f}")
        if int(position.get("quantity", 0)) > 0:
            self.quantity_entry.insert(0, str(int(position["quantity"])))

    def save_position(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("未选择股票", "请先在表格中选择一只股票。")
            return
        symbol = selected[0]
        try:
            avg_cost = float(self.avg_cost_entry.get().strip() or "0")
            quantity = int(self.quantity_entry.get().strip() or "0")
            if avg_cost < 0 or quantity < 0 or (quantity > 0 and avg_cost <= 0):
                raise ValueError
        except ValueError:
            messagebox.showwarning("持仓输入无效", "均价必须大于0，股数必须是非负整数；清仓可把两项都填0。")
            return

        if quantity == 0:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = {"avg_cost": avg_cost, "quantity": quantity}
        write_positions(self.positions)
        if symbol in self.levels:
            self._render_row(symbol, float(self.levels[symbol]["price"]), datetime.now().astimezone())
        else:
            self._populate_symbols()
            self.tree.selection_set(symbol)
        self._append_log(f"已保存 {symbol} 持仓：均价 ${avg_cost:.2f}，{quantity} 股。")

    def save_risk_settings(self) -> None:
        try:
            account_value = float(self.account_entry.get().replace(",", "").strip())
            risk_pct = float(self.risk_entry.get().strip())
            max_position_pct = float(self.max_position_entry.get().strip())
            if account_value <= 0 or not 0.1 <= risk_pct <= 10 or not 1 <= max_position_pct <= 100:
                raise ValueError
        except ValueError:
            messagebox.showwarning("风控输入无效", "账户规模需大于0；风险为0.1%–10%；单股上限为1%–100%。")
            return

        self.risk_settings = {
            "account_value": account_value,
            "risk_pct": risk_pct,
            "max_position_pct": max_position_pct,
        }
        write_risk_settings(self.risk_settings)
        for symbol, values in self.levels.items():
            self._render_row(symbol, float(values["price"]), datetime.now().astimezone())
        self._append_log(
            f"风控已保存：账户 ${account_value:,.0f}，单笔风险 {risk_pct:g}%，单股资金上限 {max_position_pct:g}%。"
        )

    def start_monitoring(self) -> None:
        if self.running:
            return
        if not self.symbols:
            messagebox.showwarning("没有股票", "请先添加至少一只需要监控的股票。")
            return

        load_dotenv(BASE_DIR / ".env", override=True)
        provider = self.provider_var.get()

        if provider == "Alpaca IEX":
            api_key = os.getenv("ALPACA_API_KEY", "").strip()
            api_secret = os.getenv("ALPACA_API_SECRET", "").strip()
            if not api_key or not api_secret or api_key.startswith("replace_") or api_secret.startswith("replace_"):
                messagebox.showerror("缺少密钥", "请点击“配置密钥”填写 Alpaca API Key 和 Secret。")
                return
            worker: ProviderWorker = AlpacaWorker(api_key, api_secret, self.symbols.copy(), self.events)
        elif provider == "Yahoo Finance":
            worker = YahooWorker(self.symbols.copy(), self.events)
        elif provider == "Massive / Polygon":
            api_key = os.getenv("MASSIVE_API_KEY", os.getenv("POLYGON_API_KEY", "")).strip()
            if not api_key or api_key.startswith("replace_"):
                messagebox.showerror("缺少密钥", "请点击“配置密钥”填写 MASSIVE_API_KEY。")
                return
            delayed = os.getenv("MASSIVE_DELAYED", "true").strip().lower() not in {"false", "0", "no"}
            worker = MassiveWorker(api_key, delayed, self.symbols.copy(), self.events)
        elif provider == "IBKR Gateway":
            try:
                host = os.getenv("IBKR_HOST", "127.0.0.1").strip()
                port = int(os.getenv("IBKR_PORT", "4002"))
                client_id = int(os.getenv("IBKR_CLIENT_ID", "17"))
                market_data_type = int(os.getenv("IBKR_MARKET_DATA_TYPE", "3"))
                if market_data_type not in {1, 2, 3, 4}:
                    raise ValueError
            except ValueError:
                messagebox.showerror("IBKR 配置错误", "请检查端口、Client ID 和行情类型（必须为1、2、3或4）。")
                return
            worker = IBKRWorker(host, port, client_id, market_data_type, self.symbols.copy(), self.events)
        else:
            messagebox.showerror("数据源错误", f"不支持的数据源：{provider}")
            return

        self.levels.clear()
        self.running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.connection_var.set("正在连接…")
        self.feed_var.set(provider)
        self.provider_combo.configure(state="disabled")
        self._append_log(f"开始使用 {provider} 加载历史数据并连接行情。")
        self.worker = worker
        self.worker.start()

    def stop_monitoring(self) -> None:
        if self.worker is not None:
            self.connection_var.set("正在停止…")
            self.worker.stop()
        else:
            self._set_stopped()

    def _set_stopped(self) -> None:
        self.running = False
        self.worker = None
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.provider_combo.configure(state="readonly")
        self.connection_var.set("已停止")

    def _process_events(self) -> None:
        latest_trades: dict[str, tuple[float, object]] = {}
        try:
            for _ in range(2000):
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "trade":
                    latest_trades[event[1]] = (event[2], event[3])
                elif kind == "snapshot":
                    self._apply_snapshot(event[1], event[2], event[3])
                elif kind == "connection":
                    self.connection_var.set(event[1])
                    self._append_log(event[1])
                elif kind == "symbol_error":
                    self._show_symbol_error(event[1], event[2])
                elif kind == "stock_name":
                    symbol, name = event[1], event[2]
                    self.stock_names[symbol] = name
                    write_stock_names(self.stock_names)
                    if self.tree.exists(symbol):
                        current = list(self.tree.item(symbol, "values"))
                        if len(current) >= 2:
                            current[1] = name
                            self.tree.item(symbol, values=current)
                elif kind == "error":
                    self.connection_var.set(event[1])
                    self._append_log(event[1])
                elif kind == "stopped":
                    self._set_stopped()
        except queue.Empty:
            pass

        for symbol, (price, timestamp) in latest_trades.items():
            self._apply_trade(symbol, price, timestamp)
        self.root.after(100, self._process_events)

    def _apply_snapshot(self, symbol: str, values: dict, timestamp) -> None:
        self.levels[symbol] = values
        self._render_row(symbol, float(values["price"]), timestamp)
        if values["status"] == "BUY_ALERT":
            self._trigger_alert(symbol, values)

    def _apply_trade(self, symbol: str, price: float, timestamp) -> None:
        if symbol not in self.levels:
            return
        values = self.levels[symbol]
        old_status = str(values["status"])
        signal_ready = bool(values.get("signal_ready", True))
        trend_ok = (
            signal_ready
            and price > float(values.get("trend_slow", values["sma200"]))
            and float(values.get("trend_fast", values["sma50"])) > float(values.get("trend_slow", values["sma200"]))
        )
        if not signal_ready:
            values["status"] = "DATA_SHORT"
        elif trend_ok and price >= float(values["buy_point"]):
            values["status"] = "BUY_ALERT"
        elif trend_ok:
            values["status"] = "WATCH"
        else:
            values["status"] = "NO_SIGNAL"
        values["price"] = price
        self._render_row(symbol, price, timestamp)

        status_text, _status_tag = display_status(values, price)
        now_monotonic = time.monotonic()
        status_changed = self.last_logged_status.get(symbol) != status_text
        if status_changed or now_monotonic - self.last_log_at.get(symbol, 0.0) >= 10:
            position = self.positions.get(symbol, {"avg_cost": 0, "quantity": 0})
            plan = build_position_plan(
                values,
                position,
                self.risk_settings["account_value"],
                self.risk_settings["risk_pct"],
                self.risk_settings["max_position_pct"],
            )
            if signal_ready:
                log_text = (
                    f"行情 {symbol} {self.stock_names.get(symbol, '')} | ${price:,.2f} | "
                    f"{status_text} | 买点 ${float(values['buy_point']):,.2f} | "
                    f"风控 ${float(plan['position_stop']):,.2f} | {plan['action']}"
                )
            else:
                log_text = (
                    f"行情 {symbol} {self.stock_names.get(symbol, '')} | ${price:,.2f} | "
                    f"仅有 {int(values.get('history_days', 0))} 根日线，暂停买卖点与仓位意见"
                )
            self._append_log(log_text)
            self.last_log_at[symbol] = now_monotonic
            self.last_logged_status[symbol] = status_text

        if values["status"] == "BUY_ALERT" and old_status != "BUY_ALERT":
            self._trigger_alert(symbol, values)

    def _render_row(self, symbol: str, price: float, timestamp) -> None:
        values = self.levels[symbol]
        status_text, status_tag = display_status(values, price)
        position = self.positions.get(symbol, {"avg_cost": 0, "quantity": 0})
        avg_cost = float(position.get("avg_cost", 0))
        quantity = int(position.get("quantity", 0))
        plan = build_position_plan(
            values,
            position,
            self.risk_settings["account_value"],
            self.risk_settings["risk_pct"],
            self.risk_settings["max_position_pct"],
        )
        if hasattr(timestamp, "astimezone"):
            updated = timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        else:
            updated = str(timestamp)
        signal_ready = bool(values.get("signal_ready", True))
        buy_text = f"${float(values['buy_point']):,.2f}" if signal_ready else "—"
        stop_text = f"${float(plan['position_stop']):,.2f}" if signal_ready else "—"
        sell_text = (
            f"${float(plan['target_2r']):,.2f} / ${float(plan['target_3r']):,.2f}"
            if signal_ready else "—"
        )
        quality_text = (
            f"{values.get('signal_quality', '标准')} · {int(values.get('history_days', 0))}日 · "
            f"{values.get('signal_model', '')}"
        )
        row = (
            symbol,
            self.stock_names.get(symbol, "—"),
            f"${price:,.2f}",
            buy_text,
            stop_text,
            f"${avg_cost:,.2f}" if avg_cost > 0 else "—",
            quantity if quantity > 0 else "—",
            sell_text,
            status_text,
            quality_text,
            str(plan["action"]),
            updated,
        )
        if self.tree.exists(symbol):
            self.tree.item(symbol, values=row, tags=(status_tag,))

    def _trigger_alert(self, symbol: str, values: dict) -> None:
        now = datetime.now(timezone.utc)
        alert_key = f"{symbol}:{now.date().isoformat()}"
        if self.alert_state.get(symbol) == alert_key:
            return
        message = (
            f"买入点提示（只读观察） {symbol} | 现价 ${float(values['price']):.2f} | "
            f"买入点 ${float(values['buy_point']):.2f} | 止损点 ${float(values['stop_point']):.2f}"
        )
        self.root.bell()
        self._append_log(message)
        record_alert(symbol, values, now)
        self.alert_state[symbol] = alert_key
        save_state(self.alert_state)
        threading.Thread(target=self._send_discord_safely, args=(message,), daemon=True).start()

    def _send_discord_safely(self, message: str) -> None:
        try:
            send_discord(message)
        except Exception as exc:
            self.events.put(("connection", f"Discord 提示发送失败：{exc}"))

    def _show_symbol_error(self, symbol: str, error: str) -> None:
        if self.tree.exists(symbol):
            self.tree.item(symbol, values=(symbol, self.stock_names.get(symbol, "—"), "—", "—", "—", "—", "—", "—", "数据错误", "—", error[:32], "—"), tags=("ERROR",))
        self._append_log(f"{symbol}：{error}")

    def _append_log(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.alert_text.configure(state="normal")
        self.alert_text.insert("end", f"[{timestamp}] {text}\n")
        self.alert_text.see("end")
        self.alert_text.configure(state="disabled")

    def clear_log(self) -> None:
        self.alert_text.configure(state="normal")
        self.alert_text.delete("1.0", "end")
        self.alert_text.configure(state="disabled")

    def on_close(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    SignalMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
