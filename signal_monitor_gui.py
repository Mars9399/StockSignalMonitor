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
from market_directory import MarketDirectoryClient, MarketDirectoryPage
from market_movers import MarketMoverWorker, MoverResult
import signal_monitor as signal_core
from signal_monitor import calculate_levels, estimate_action_probabilities, load_state, record_alert, save_state, send_discord
from tws_data import auxiliary_client_id, fetch_account_summary, fetch_intraday_bars
from tws_positions import fetch_positions, merge_positions
from reliability import observation_reason, NEW_YORK


APP_VERSION = "2.5.2"
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
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
TWS_IMPORT_FILE = BASE_DIR / "tws_imported_symbols.json"
UI_SETTINGS_FILE = BASE_DIR / "ui_settings.json"
TWS_PROVIDER = "IBKR TWS + Yahoo 行情"
DEFAULT_UI_SETTINGS = {
    "window_width": 1420,
    "window_height": 790,
    "ui_font_size": 10,
    "table_font_size": 10,
    "table_row_height": 34,
    "log_height": 8,
    "start_maximized": False,
    "remember_window_size": True,
    "account_visible_default": True,
    "auto_start_movers": True,
    "confirm_exit": False,
}
DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
DEFAULT_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corp.",
    "NVDA": "NVIDIA Corp.",
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
}
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,11}$")
PRICE_UP_COLOR = "#38d982"
PRICE_DOWN_COLOR = "#ff6678"
OVERVIEW_ROW_COLORS = {
    "BUY_ALERT": ("#91f5c4", "#194c3d"),
    "SELL_ALERT": ("#ffadb5", "#572e3a"),
    "NEAR": ("#9be7ff", "#24485a"),
    "WATCH": ("#ffe08a", "#514424"),
    "NO_SIGNAL": ("#c1cddd", "#344158"),
    "DATA_SHORT": ("#ffc3a6", "#563d34"),
    "ERROR": ("#ffc0c6", "#572e3a"),
}
WATCHLIST_ROW_COLORS = {
    "HELD": ("#91f5c4", "#194c3d"),
    "WATCHLIST": ("#f0f5fb", "#24334d"),
}
MOVER_ROW_COLORS = {
    "BUY": ("#91f5c4", "#194c3d"),
    "NEAR": ("#9be7ff", "#24485a"),
    "EXTENDED": ("#ffe08a", "#514424"),
    "WAIT": ("#d6e0ec", "#344158"),
    "AVOID": ("#ffadb5", "#572e3a"),
    "OBSERVE": ("#c1cddd", "#3a465c"),
    "ERROR": ("#ffc3a6", "#563d34"),
}
MARKET_ROW_COLORS = {
    "UP": ("#dffff0", "#245b43"),
    "DOWN": ("#ffe3e7", "#693541"),
    "FLAT": ("#e5edf7", "#344158"),
}
MARKET_LABELS = {"us": "美股", "hk": "港股"}


def configure_directional_row_tags(tree: ttk.Treeview, palette: dict[str, tuple[str, str]]) -> None:
    """Create one concrete tag per base state/direction to avoid Tk tag conflicts."""
    for base_tag, (foreground, background) in palette.items():
        tree.tag_configure(base_tag, foreground=foreground, background=background)
        tree.tag_configure(
            f"{base_tag}_PRICE_UP",
            foreground=PRICE_UP_COLOR,
            background=background,
        )
        tree.tag_configure(
            f"{base_tag}_PRICE_DOWN",
            foreground=PRICE_DOWN_COLOR,
            background=background,
        )


def directional_row_tag(base_tag: str, movement_tag: str) -> str:
    return f"{base_tag}_{movement_tag}" if movement_tag else base_tag


def read_ui_settings() -> dict:
    values = {}
    if UI_SETTINGS_FILE.exists():
        try:
            loaded = json.loads(UI_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                values = loaded
        except (OSError, TypeError, json.JSONDecodeError):
            pass

    def bounded_int(key: str, lower: int, upper: int) -> int:
        try:
            return min(upper, max(lower, int(values.get(key, DEFAULT_UI_SETTINGS[key]))))
        except (TypeError, ValueError):
            return int(DEFAULT_UI_SETTINGS[key])

    result = {
        "window_width": bounded_int("window_width", 1000, 3840),
        "window_height": bounded_int("window_height", 620, 2160),
        "ui_font_size": bounded_int("ui_font_size", 8, 18),
        "table_font_size": bounded_int("table_font_size", 8, 18),
        "table_row_height": bounded_int("table_row_height", 24, 60),
        "log_height": bounded_int("log_height", 3, 20),
    }
    for key in (
        "start_maximized", "remember_window_size", "account_visible_default",
        "auto_start_movers", "confirm_exit",
    ):
        value = values.get(key, DEFAULT_UI_SETTINGS[key])
        result[key] = value if isinstance(value, bool) else bool(DEFAULT_UI_SETTINGS[key])
    return result


def write_ui_settings(settings: dict) -> None:
    UI_SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_watchlist() -> list[str]:
    if WATCHLIST_FILE.exists():
        try:
            values = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
            symbols = [str(value).strip().upper() for value in values]
            valid = list(dict.fromkeys(value for value in symbols if SYMBOL_PATTERN.fullmatch(value)))
            if isinstance(values, list):
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
                "quantity": max(0.0, float(values.get("quantity", 0))),
                "initial_stop": values.get("initial_stop"),
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
    allowed = {"Alpaca IEX", "Yahoo Finance", "Massive / Polygon", "IBKR Gateway", TWS_PROVIDER}
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
    if values["status"] == "BUY_ALERT":
        return "买入提示", "BUY_ALERT"
    if values["status"] == "SELL_ALERT":
        return "卖出提示", "SELL_ALERT"
    buy_gap = (float(values["buy_point"]) / price - 1) * 100 if price > 0 else 999
    sell_gap = (price / max(float(values["stop_point"]), 0.01) - 1) * 100 if price > 0 else 999
    if buy_gap <= sell_gap:
        return f"距上破线 {max(0.0, buy_gap):.1f}%", "NEAR"
    return f"距卖出点 {max(0.0, sell_gap):.1f}%", "WATCH"


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
    quantity = float(position.get("quantity", 0))
    avg_cost = float(position.get("avg_cost", 0))
    status = str(values["status"])

    if quantity > 0 and avg_cost > 0:
        saved_stop = position.get("initial_stop")
        has_saved_stop = isinstance(saved_stop, (int, float)) and math.isfinite(saved_stop) and 0 < saved_stop < avg_cost
        position_stop = max(entry_stop, float(saved_stop)) if has_saved_stop else entry_stop
        risk_entry_price = avg_cost
        risk_reference_stop = float(saved_stop) if has_saved_stop else min(entry_stop, avg_cost - 0.01)
        exposure_price = price
    else:
        position_stop = entry_stop
        risk_entry_price = buy_point
        risk_reference_stop = entry_stop
        exposure_price = buy_point

    risk_budget = account_value * (risk_pct / 100)
    risk_per_share = max(risk_entry_price - risk_reference_stop, atr * 0.5, 0.01)
    max_by_risk = math.floor(risk_budget / risk_per_share)
    max_by_value = math.floor((account_value * max_position_pct / 100) / max(exposure_price, 0.01))
    max_shares = max(0, min(max_by_risk, max_by_value))

    if quantity > 0 and avg_cost > 0:
        if price <= position_stop or status == "SELL_ALERT":
            action = f"卖出提示：参考卖出 {quantity:g} 股"
        elif status == "BUY_ALERT":
            add_shares = max(0, math.floor(max_shares - quantity))
            action = f"买入提示：参考最多加 {add_shares} 股" if add_shares else "买入提示：当前持仓已达参考上限"
        elif quantity > max_shares:
            action = f"持有；仓位高于参考上限 {quantity - max_shares:g} 股"
        else:
            action = f"持有；卖出触发点 ${position_stop:,.2f}"
    elif status == "BUY_ALERT":
        action = f"买入提示：参考上限 {max_shares} 股"
    elif status == "SELL_ALERT":
        action = "卖出提示：当前无持仓"
    else:
        action = f"等待上破 ${buy_point:,.2f} / 跌破卖出 ${position_stop:,.2f}"

    return {
        "position_stop": position_stop,
        "target_2r": 0.0,
        "target_3r": 0.0,
        "max_shares": max_shares,
        "action": action,
    }


class SignalMonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.ui_settings = read_ui_settings()
        self.root.title(f"美股买卖点与仓位监控 · v{APP_VERSION} · Design by Mars · 只读模式")
        self.root.geometry(f"{self.ui_settings['window_width']}x{self.ui_settings['window_height']}")
        self.root.minsize(980, 620)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.app_icons: list[tk.PhotoImage] = []
        icon_ico = RESOURCE_DIR / "assets" / "app_icon.ico"
        if icon_ico.exists():
            try:
                self.root.iconbitmap(default=str(icon_ico))
            except tk.TclError:
                pass
        for size in (16, 20, 24, 32, 40, 48, 64, 96, 128, 256):
            icon_png = RESOURCE_DIR / "assets" / "icons" / f"app_icon_{size}.png"
            if icon_png.exists():
                try:
                    self.app_icons.append(tk.PhotoImage(file=str(icon_png)))
                except tk.TclError:
                    continue
        if self.app_icons:
            self.root.iconphoto(True, *self.app_icons)

        self.events: queue.Queue = queue.Queue()
        self.worker: ProviderWorker | None = None
        self.running = False
        self.syncing_positions = False
        self.resume_after_sync = False
        self.pending_tws_start = False
        self.symbols = read_watchlist()
        self.levels: dict[str, dict] = {}
        self.alert_state = load_state()
        self.positions = read_positions()
        self.risk_settings = read_risk_settings()
        self.stock_names = read_stock_names()
        self.last_log_at: dict[str, float] = {}
        self.last_logged_status: dict[str, str] = {}
        self.last_rendered_prices: dict[str, float] = {}
        self.price_directions: dict[str, str] = {}
        self.mover_last_prices: dict[str, float] = {}
        self.mover_price_directions: dict[str, str] = {}
        self.market_directory_last_prices: dict[str, float] = {}
        self.market_directory_price_directions: dict[str, str] = {}
        self.quote_times = {}
        self.last_market_event_at: float | None = None
        self.manual_stop_requested = False
        self.restart_pending = False
        self.restart_attempts = 0
        self.restart_job = None
        self.mover_worker: MarketMoverWorker | None = None
        self.mover_running = False
        self.mover_started_once = False
        self.mover_title_labels: list[tk.Label] = []
        self.market_directory_page: MarketDirectoryPage | None = None
        self.market_directory_loading = False
        self.chart_windows: dict[str, dict] = {}
        self.tws_request_serial = 0
        self.history_loaded_day = datetime.now(NEW_YORK).date()
        load_dotenv(BASE_DIR / ".env")
        self.provider_var = tk.StringVar(value=read_provider())
        self.feed_var = tk.StringVar(value=self.provider_var.get())
        self.scope_var = tk.StringVar(value="all")
        self.tws_message = tk.StringVar(value="尚未读取 TWS 持仓")
        self.account_summary: dict = {}
        self.account_details_visible = bool(self.ui_settings["account_visible_default"])
        self.account_summary_var = tk.StringVar(value="TWS 当前账户：尚未读取")

        self._configure_style()
        self._build_ui()
        self._refresh_account_summary_text()
        self._populate_symbols()
        self._resolve_missing_names(self.symbols)
        self.root.after(100, self._process_events)
        self.root.after(15000, self._check_freshness)
        if self.provider_var.get() == TWS_PROVIDER:
            self.root.after(500, self.refresh_account_summary)
        if self.ui_settings["start_maximized"]:
            self.root.after(50, self._maximize_window)

    def _configure_style(self) -> None:
        ui_font = int(self.ui_settings["ui_font_size"])
        table_font = int(self.ui_settings["table_font_size"])
        self.root.configure(bg="#18243a")
        self.root.option_add("*TCombobox*Listbox.font", ("Microsoft YaHei UI", ui_font))
        style = ttk.Style()
        self.app_style = style
        style.theme_use("clam")
        style.configure("App.TFrame", background="#18243a")
        style.configure("Card.TFrame", background="#22314a")
        style.configure("Title.TLabel", background="#18243a", foreground="#f7f9fd", font=("Microsoft YaHei UI", ui_font + 8, "bold"))
        style.configure("Sub.TLabel", background="#18243a", foreground="#b4c2d6", font=("Microsoft YaHei UI", max(8, ui_font - 1)))
        style.configure("Card.TLabel", background="#22314a", foreground="#edf3fb", font=("Microsoft YaHei UI", ui_font))
        style.configure("Hint.TLabel", background="#22314a", foreground="#a9bad0", font=("Microsoft YaHei UI", max(8, ui_font - 2)))
        style.configure("Safe.TLabel", background="#1f5a42", foreground="#91f5c4", padding=(10, 5), font=("Microsoft YaHei UI", max(8, ui_font - 1), "bold"))
        style.configure("Feed.TLabel", background="#344763", foreground="#d8e4f3", padding=(10, 5), font=("Microsoft YaHei UI", max(8, ui_font - 1)))
        style.configure("Account.TLabel", background="#22314a", foreground="#dce9f8", font=("Microsoft YaHei UI", max(8, ui_font - 1), "bold"))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", ui_font, "bold"), padding=(14, 8), background="#4f8df7", foreground="white")
        style.map("Accent.TButton", background=[("active", "#6ca2ff"), ("disabled", "#465570")])
        style.configure("Secondary.TButton", font=("Microsoft YaHei UI", ui_font), padding=(12, 8), background="#31435f", foreground="#f0f5fb")
        style.map("Secondary.TButton", background=[("active", "#405678")])
        style.configure("TButton", font=("Microsoft YaHei UI", ui_font))
        style.configure("TLabel", font=("Microsoft YaHei UI", ui_font))
        style.configure("TNotebook", background="#18243a", borderwidth=0)
        style.configure("TNotebook.Tab", background="#2c3c58", foreground="#cbd7e7", padding=(13, 6), font=("Microsoft YaHei UI", ui_font))
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#4b72a8"), ("active", "#3a5275")],
            foreground=[("selected", "#ffffff")],
            font=[("selected", ("Microsoft YaHei UI", ui_font + 2, "bold")), ("!selected", ("Microsoft YaHei UI", ui_font))],
            padding=[("selected", (18, 9)), ("!selected", (13, 6))],
        )
        style.configure("TRadiobutton", background="#22314a", foreground="#e8eff8", font=("Microsoft YaHei UI", ui_font))
        style.map("TRadiobutton", background=[("active", "#22314a")], foreground=[("selected", "#91c4ff")])
        style.configure("TCheckbutton", background="#22314a", foreground="#e8eff8", font=("Microsoft YaHei UI", ui_font))
        style.map("TCheckbutton", background=[("active", "#22314a")])
        style.configure("TEntry", font=("Microsoft YaHei UI", ui_font))
        style.configure("TCombobox", font=("Microsoft YaHei UI", ui_font))
        style.configure("TScrollbar", background="#405678", troughcolor="#1b2940", arrowcolor="#dbe7f5", borderwidth=0)
        style.configure("Treeview", background="#24334d", fieldbackground="#24334d", foreground="#f0f5fb", rowheight=int(self.ui_settings["table_row_height"]), borderwidth=0, font=("Consolas", table_font))
        style.configure("Treeview.Heading", background="#3a4e6c", foreground="#eef4fb", relief="flat", font=("Microsoft YaHei UI", ui_font, "bold"))
        style.map("Treeview", background=[("selected", "#4b72a8")], foreground=[("selected", "#ffffff")])
        style.configure("Overview.Treeview", background="#24334d", fieldbackground="#24334d", foreground="#f0f5fb")
        style.configure("Watchlist.Treeview", background="#24334d", fieldbackground="#24334d", foreground="#f0f5fb")
        style.configure("Mover.Treeview", background="#24334d", fieldbackground="#24334d", foreground="#f0f5fb")
        style.configure("Market.Treeview", background="#24334d", fieldbackground="#24334d", foreground="#f0f5fb")
        style.map("Overview.Treeview", background=[("selected", "#4b72a8")], foreground=[("selected", "#ffffff")])
        style.map("Watchlist.Treeview", background=[("selected", "#4b72a8")], foreground=[("selected", "#ffffff")])
        style.map("Mover.Treeview", background=[("selected", "#4b72a8")], foreground=[("selected", "#ffffff")])
        style.map("Market.Treeview", background=[("selected", "#4b72a8")], foreground=[("selected", "#ffffff")])

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=22)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(
            header,
            text=f"美股买卖点与仓位监控 · v{APP_VERSION} · Design by Mars",
            style="Title.TLabel",
        ).pack(side="left")
        ttk.Label(header, text="只读 · 永不下单", style="Safe.TLabel").pack(side="right", padx=(8, 0))
        ttk.Label(header, textvariable=self.feed_var, style="Feed.TLabel").pack(side="right")

        account_card = ttk.Frame(outer, style="Card.TFrame", padding=(12, 8))
        account_card.pack(fill="x", pady=(0, 10))
        ttk.Label(account_card, textvariable=self.account_summary_var, style="Account.TLabel").pack(side="left", fill="x", expand=True)
        self.account_visibility_button = ttk.Button(
            account_card,
            text="暂时隐藏",
            style="Secondary.TButton",
            command=self.toggle_account_details,
        )
        self.account_visibility_button.pack(side="right")
        self.account_refresh_button = ttk.Button(
            account_card,
            text="刷新账户",
            style="Secondary.TButton",
            command=self.refresh_account_summary,
        )
        self.account_refresh_button.pack(side="right", padx=(0, 6))

        controls = ttk.Frame(outer, style="Card.TFrame", padding=14)
        controls.pack(fill="x", pady=(0, 14))
        ttk.Label(controls, text="股票代码", style="Card.TLabel").pack(side="left", padx=(0, 8))
        self.symbol_entry = tk.Entry(
            controls,
            width=14,
            bg="#1b2940",
            fg="#f4f7fb",
            insertbackground="white",
            relief="flat",
            font=("Consolas", int(self.ui_settings["table_font_size"]) + 2),
        )
        self.symbol_entry.pack(side="left", ipady=7, padx=(0, 8))
        self.symbol_entry.bind("<Return>", lambda _event: self.add_symbol())
        ttk.Button(controls, text="添加", style="Secondary.TButton", command=self.add_symbol).pack(side="left", padx=3)
        ttk.Button(controls, text="移除所选", style="Secondary.TButton", command=self.remove_selected).pack(side="left", padx=3)
        ttk.Button(controls, text="配置密钥", style="Secondary.TButton", command=self.open_api_config).pack(side="left", padx=3)
        self.ui_settings_button = ttk.Button(
            controls,
            text="界面设置",
            style="Secondary.TButton",
            command=self.open_ui_settings,
        )
        self.ui_settings_button.pack(side="left", padx=3)
        ttk.Label(controls, text="数据源", style="Card.TLabel").pack(side="left", padx=(16, 6))
        self.provider_combo = ttk.Combobox(
            controls,
            textvariable=self.provider_var,
            values=("Alpaca IEX", "Yahoo Finance", "Massive / Polygon", "IBKR Gateway", TWS_PROVIDER),
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

        actions = ttk.Frame(outer, style="Card.TFrame", padding=8)
        actions.pack(fill="x", pady=(0, 8))
        ttk.Label(actions, text="所选股票可选保护线", style="Card.TLabel").pack(side="left")
        self.initial_stop_entry = self._dark_entry(actions, 8)
        self.initial_stop_entry.pack(side="left", padx=5)
        for label, scope in (("显示全部", "all"), ("只显示持仓", "positions")):
            ttk.Radiobutton(actions, text=label, variable=self.scope_var, value=scope,
                            command=self._apply_scope).pack(side="left", padx=6)
        self.sync_button = ttk.Button(actions, text="重新读取持仓", command=self.sync_positions)
        self.sync_button.pack(side="left", padx=10)
        self.clear_positions_button = ttk.Button(actions, text="清除全部持仓", command=self.clear_positions)
        self.clear_positions_button.pack(side="left")
        ttk.Label(actions, textvariable=self.tws_message, style="Card.TLabel").pack(side="right", padx=8)

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)
        table_card = ttk.Frame(self.notebook, style="Card.TFrame", padding=1)
        self.notebook.add(table_card, text="监控概览")
        columns = (
            "symbol", "name", "price", "buy", "stop", "avg", "qty", "status",
            "buy_probability", "reduce_probability", "quality", "action", "updated",
        )
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="extended", style="Overview.Treeview")
        headings = {
            "symbol": "股票",
            "name": "股票名称",
            "price": "实时价格",
            "buy": "突破买入线",
            "stop": "卖出触发点",
            "avg": "持仓均价",
            "qty": "股数",
            "status": "状态",
            "buy_probability": "即时买入概率*",
            "reduce_probability": "建议减持概率*",
            "quality": "信号依据",
            "action": "实时买卖建议",
            "updated": "最近成交",
        }
        widths = {
            "symbol": 65, "name": 150, "price": 90, "buy": 105, "stop": 105,
            "avg": 90, "qty": 50, "status": 120, "buy_probability": 115,
            "reduce_probability": 115, "quality": 165, "action": 285, "updated": 145,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="center")
        configure_directional_row_tags(self.tree, OVERVIEW_ROW_COLORS)
        overview_horizontal = ttk.Scrollbar(table_card, orient="horizontal", command=self.tree.xview)
        overview_vertical = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(xscrollcommand=overview_horizontal.set, yscrollcommand=overview_vertical.set)
        overview_horizontal.pack(side="bottom", fill="x")
        overview_vertical.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", self.open_tws_chart_from_event)
        self.watch_card = ttk.Frame(self.notebook)
        self.notebook.add(self.watch_card, text="自选列表")
        watch_columns = ("symbol", "name", "price", "held", "quantity", "cost", "value")
        self.watch_tree = ttk.Treeview(self.watch_card, columns=watch_columns, show="headings", selectmode="extended", style="Watchlist.Treeview")
        for column, title in zip(watch_columns, ("股票", "名称", "最新价", "持仓状态", "数量", "平均成本", "持仓市值")):
            self.watch_tree.heading(column, text=title)
            self.watch_tree.column(column, width=140, anchor="center")
        configure_directional_row_tags(self.watch_tree, WATCHLIST_ROW_COLORS)
        self.watch_tree.pack(fill="both", expand=True)
        self.watch_tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self._build_movers_tab()
        self._build_market_directory_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

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
            height=int(self.ui_settings["log_height"]),
            bg="#172238",
            fg="#e1eaf5",
            relief="flat",
            state="disabled",
            font=("Microsoft YaHei UI", int(self.ui_settings["ui_font_size"])),
            padx=10,
            pady=8,
        )
        self.alert_text.pack(fill="x")
        self._append_log("准备就绪。监控器仅使用市场数据接口，不具备交易能力。")

    def _dark_entry(self, parent, width: int) -> tk.Entry:
        return tk.Entry(
            parent,
            width=width,
            bg="#1b2940",
            fg="#f4f7fb",
            insertbackground="white",
            relief="flat",
            justify="center",
            font=("Consolas", int(self.ui_settings["table_font_size"])),
        )

    def _maximize_window(self) -> None:
        try:
            self.root.state("zoomed")
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)
            except tk.TclError:
                pass

    def _apply_ui_settings(self, resize_window: bool = True) -> None:
        self._configure_style()
        ui_font = int(self.ui_settings["ui_font_size"])
        table_font = int(self.ui_settings["table_font_size"])
        for entry in (
            self.avg_cost_entry,
            self.quantity_entry,
            self.account_entry,
            self.risk_entry,
            self.max_position_entry,
            self.initial_stop_entry,
        ):
            entry.configure(font=("Consolas", table_font))
        self.symbol_entry.configure(font=("Consolas", table_font + 2))
        self.alert_text.configure(font=("Microsoft YaHei UI", ui_font), height=int(self.ui_settings["log_height"]))
        for label in self.mover_title_labels:
            if label.winfo_exists():
                label.configure(font=("Microsoft YaHei UI", ui_font + 1, "bold"))
        for symbol in list(self.chart_windows):
            self._draw_tws_chart(symbol)
        self.account_details_visible = bool(self.ui_settings["account_visible_default"])
        self._refresh_account_summary_text()
        if self.ui_settings["auto_start_movers"]:
            self._on_tab_changed()
        elif not self.mover_running:
            self.mover_status_var.set("自动扫描已关闭 · 可点击“开始自动扫描”")
        if resize_window:
            try:
                self.root.state("normal")
            except tk.TclError:
                pass
            self.root.geometry(f"{self.ui_settings['window_width']}x{self.ui_settings['window_height']}")
            if self.ui_settings["start_maximized"]:
                self.root.after_idle(self._maximize_window)
        self.root.update_idletasks()

    def open_ui_settings(self):
        existing = getattr(self, "ui_settings_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return existing

        dialog = tk.Toplevel(self.root)
        self.ui_settings_window = dialog
        dialog.title(f"界面设置 · v{APP_VERSION} · Design by Mars")
        dialog.geometry("600x610")
        dialog.resizable(False, False)
        dialog.configure(bg="#18243a")
        dialog.transient(self.root)
        if self.app_icons:
            dialog.iconphoto(True, *self.app_icons)

        panel = ttk.Frame(dialog, style="Card.TFrame", padding=20)
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        ttk.Label(panel, text="常规界面设置", style="Card.TLabel", font=("Microsoft YaHei UI", int(self.ui_settings["ui_font_size"]) + 3, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            panel,
            text="尺寸与字体保存后立即应用；窗口启动选项也会在下次启动时继续生效。",
            style="Hint.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 16))

        numeric_specs = (
            ("window_width", "初始窗口宽度", "1000–3840 像素"),
            ("window_height", "初始窗口高度", "620–2160 像素"),
            ("ui_font_size", "界面文字大小", "8–18 号"),
            ("table_font_size", "列表文字大小", "8–18 号"),
            ("table_row_height", "列表行高", "24–60 像素"),
            ("log_height", "日志区域高度", "3–20 行"),
        )
        variables: dict[str, tk.Variable] = {}
        for row, (key, label, hint) in enumerate(numeric_specs, start=2):
            ttk.Label(panel, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=6)
            variable = tk.StringVar(value=str(self.ui_settings[key]))
            variables[key] = variable
            ttk.Entry(panel, textvariable=variable, width=12, justify="center").grid(row=row, column=1, sticky="w", padx=(18, 12), pady=6, ipady=4)
            ttk.Label(panel, text=hint, style="Hint.TLabel").grid(row=row, column=2, sticky="w", pady=6)

        boolean_specs = (
            ("start_maximized", "启动时最大化窗口"),
            ("remember_window_size", "退出时记住当前窗口大小"),
            ("account_visible_default", "启动时显示账户明细"),
            ("auto_start_movers", "打开 TOP10 页时自动开始扫描"),
            ("confirm_exit", "关闭软件前询问确认"),
        )
        start_row = 2 + len(numeric_specs)
        for offset, (key, label) in enumerate(boolean_specs):
            variable = tk.BooleanVar(value=bool(self.ui_settings[key]))
            variables[key] = variable
            ttk.Checkbutton(panel, text=label, variable=variable).grid(
                row=start_row + offset,
                column=0,
                columnspan=3,
                sticky="w",
                pady=5,
            )

        ranges = {
            "window_width": (1000, 3840),
            "window_height": (620, 2160),
            "ui_font_size": (8, 18),
            "table_font_size": (8, 18),
            "table_row_height": (24, 60),
            "log_height": (3, 20),
        }

        def restore_defaults() -> None:
            for key, value in DEFAULT_UI_SETTINGS.items():
                variables[key].set(value)

        def save() -> None:
            updated = {}
            try:
                for key, (lower, upper) in ranges.items():
                    value = int(str(variables[key].get()).strip())
                    if not lower <= value <= upper:
                        raise ValueError
                    updated[key] = value
            except (TypeError, ValueError):
                messagebox.showwarning("界面设置无效", "请按每项右侧标注的范围填写整数。", parent=dialog)
                return
            for key, _label in boolean_specs:
                updated[key] = bool(variables[key].get())
            self.ui_settings = updated
            try:
                write_ui_settings(self.ui_settings)
            except OSError as exc:
                messagebox.showerror("无法保存界面设置", str(exc), parent=dialog)
                return
            self._apply_ui_settings(resize_window=True)
            self._append_log("界面设置已保存并应用。")
            dialog.destroy()

        buttons = ttk.Frame(panel, style="Card.TFrame")
        buttons.grid(row=start_row + len(boolean_specs), column=0, columnspan=3, sticky="ew", pady=(20, 0))
        ttk.Button(buttons, text="恢复默认值", style="Secondary.TButton", command=restore_defaults).pack(side="left")
        ttk.Button(buttons, text="取消", style="Secondary.TButton", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="保存并应用", style="Accent.TButton", command=save).pack(side="right")

        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(2, weight=1)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.grab_set()
        dialog.focus_force()
        return dialog

    def _build_movers_tab(self) -> None:
        self.movers_card = ttk.Frame(self.notebook, style="Card.TFrame", padding=10)
        self.notebook.add(self.movers_card, text="暴涨暴跌 TOP10")

        toolbar = ttk.Frame(self.movers_card, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(0, 8))
        mover_hint = (
            "切换到本页后自动扫描 · 每 60 秒更新"
            if self.ui_settings["auto_start_movers"]
            else "自动扫描已关闭 · 可点击“开始自动扫描”"
        )
        self.mover_status_var = tk.StringVar(value=mover_hint)
        ttk.Label(toolbar, textvariable=self.mover_status_var, style="Card.TLabel").pack(side="left")
        ttk.Button(toolbar, text="加入自选", style="Secondary.TButton", command=self.add_selected_mover).pack(side="right", padx=(6, 0))
        self.mover_refresh_button = ttk.Button(
            toolbar,
            text="立即刷新",
            style="Secondary.TButton",
            command=self.refresh_movers,
        )
        self.mover_refresh_button.pack(side="right", padx=(6, 0))
        self.mover_button = ttk.Button(toolbar, text="开始自动扫描", style="Accent.TButton", command=self.toggle_mover_monitor)
        self.mover_button.pack(side="right")

        tables = ttk.Panedwindow(self.movers_card, orient="horizontal")
        tables.pack(fill="both", expand=True)
        self.gainers_tree = self._create_mover_table(tables, "▲ 暴涨 TOP10", "#91f5c4")
        self.losers_tree = self._create_mover_table(tables, "▼ 暴跌 TOP10", "#ffadb5")
        configure_directional_row_tags(
            self.gainers_tree,
            {"WAIT": ("#d8f3eb", "#29474c"), "OBSERVE": ("#c8e7df", "#304950")},
        )
        configure_directional_row_tags(
            self.losers_tree,
            {"WAIT": ("#f2dce2", "#493843"), "OBSERVE": ("#ebcbd3", "#4d3641")},
        )
        self.gainers_tree.bind("<<TreeviewSelect>>", lambda event: self._on_mover_select(event, self.losers_tree))
        self.losers_tree.bind("<<TreeviewSelect>>", lambda event: self._on_mover_select(event, self.gainers_tree))

    def _create_mover_table(self, parent, title: str, title_color: str) -> ttk.Treeview:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=6)
        parent.add(frame, weight=1)
        title_label = tk.Label(
            frame,
            text=title,
            bg="#22314a",
            fg=title_color,
            font=("Microsoft YaHei UI", int(self.ui_settings["ui_font_size"]) + 1, "bold"),
            anchor="w",
        )
        title_label.pack(fill="x", pady=(0, 5))
        self.mover_title_labels.append(title_label)
        columns = ("rank", "symbol", "name", "price", "change", "volume", "buy", "sell", "advice", "updated")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", height=10, style="Mover.Treeview")
        headings = ("#", "股票", "名称", "现价", "涨跌", "成交量", "突破线", "卖出点", "买入机会分析", "行情时间")
        widths = (34, 62, 125, 72, 67, 82, 76, 76, 205, 72)
        for column, label, width in zip(columns, headings, widths):
            tree.heading(column, text=label)
            tree.column(column, width=width, minwidth=width, anchor="center")
        configure_directional_row_tags(tree, MOVER_ROW_COLORS)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        vertical = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        horizontal.pack(side="bottom", fill="x")
        vertical.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        return tree

    @staticmethod
    def _clear_other_mover(tree: ttk.Treeview) -> None:
        selected = tree.selection()
        if selected:
            tree.selection_remove(*selected)

    def _on_mover_select(self, event, other_tree: ttk.Treeview) -> None:
        self._clear_other_mover(other_tree)
        self._sync_selected_price_styles(event)

    def _on_tab_changed(self, _event=None) -> None:
        if (
            self.ui_settings["auto_start_movers"]
            and self.notebook.select() == str(self.movers_card)
            and not self.mover_started_once
        ):
            self.mover_started_once = True
            self.start_mover_monitor()
        if (
            self.notebook.select() == str(self.market_directory_card)
            and self.market_directory_page is None
            and not self.market_directory_loading
        ):
            self.load_market_directory(0)

    def _build_market_directory_tab(self) -> None:
        self.market_directory_card = ttk.Frame(self.notebook, style="Card.TFrame", padding=10)
        self.notebook.add(self.market_directory_card, text="全市场股票")

        toolbar = ttk.Frame(self.market_directory_card, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(0, 8))
        self.market_directory_status_var = tk.StringVar(value="分页浏览 Yahoo 美股市场；右键所选股票可加入自选")
        ttk.Label(toolbar, textvariable=self.market_directory_status_var, style="Card.TLabel").pack(side="left")
        self.market_directory_market_var = tk.StringVar(value="美股")
        self.market_directory_market_combo = ttk.Combobox(
            toolbar,
            textvariable=self.market_directory_market_var,
            values=tuple(MARKET_LABELS.values()),
            width=6,
            state="readonly",
        )
        self.market_directory_market_combo.pack(side="left", padx=(14, 5), ipady=4)
        self.market_directory_market_combo.bind(
            "<<ComboboxSelected>>",
            self.on_market_directory_market_changed,
        )
        self.market_directory_search_var = tk.StringVar()
        search = self._dark_entry(toolbar, 24)
        search.configure(textvariable=self.market_directory_search_var)
        search.pack(side="left", padx=(5, 5), ipady=4)
        search.bind("<Return>", lambda _event: self.search_market_directory())
        ttk.Button(toolbar, text="搜索代码/名称", style="Secondary.TButton", command=self.search_market_directory).pack(side="left")
        ttk.Button(toolbar, text="加入自选", style="Accent.TButton", command=self.add_selected_market_symbol).pack(side="right", padx=(6, 0))
        self.market_directory_next_button = ttk.Button(toolbar, text="下一页", command=self.next_market_directory_page)
        self.market_directory_next_button.pack(side="right", padx=(6, 0))
        self.market_directory_previous_button = ttk.Button(toolbar, text="上一页", command=self.previous_market_directory_page)
        self.market_directory_previous_button.pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="刷新", command=lambda: self.load_market_directory(self._current_market_page())).pack(side="right", padx=(6, 0))

        columns = ("symbol", "name", "exchange", "price", "change", "volume", "market_cap", "watched")
        self.market_directory_tree = ttk.Treeview(
            self.market_directory_card,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Market.Treeview",
        )
        headings = ("股票", "名称", "交易所", "现价", "涨跌", "成交量", "市值", "自选")
        widths = (90, 260, 145, 100, 90, 120, 135, 70)
        for column, heading, width in zip(columns, headings, widths):
            self.market_directory_tree.heading(column, text=heading)
            self.market_directory_tree.column(column, width=width, anchor="center")
        configure_directional_row_tags(self.market_directory_tree, MARKET_ROW_COLORS)
        horizontal = ttk.Scrollbar(self.market_directory_card, orient="horizontal", command=self.market_directory_tree.xview)
        vertical = ttk.Scrollbar(self.market_directory_card, orient="vertical", command=self.market_directory_tree.yview)
        self.market_directory_tree.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        horizontal.pack(side="bottom", fill="x")
        vertical.pack(side="right", fill="y")
        self.market_directory_tree.pack(fill="both", expand=True)
        self.market_directory_tree.bind("<Button-3>", self.show_market_directory_menu)
        self.market_directory_tree.bind("<Double-1>", lambda _event: self.add_selected_market_symbol())
        self.market_directory_tree.bind("<<TreeviewSelect>>", self._sync_selected_price_styles)
        self.market_directory_menu = tk.Menu(self.root, tearoff=False)
        self.market_directory_menu.add_command(label="加入自选", command=self.add_selected_market_symbol)

    def _current_market_page(self) -> int:
        return self.market_directory_page.page if self.market_directory_page else 0

    def _current_market_code(self) -> str:
        selected_label = self.market_directory_market_var.get()
        return next((code for code, label in MARKET_LABELS.items() if label == selected_label), "us")

    def on_market_directory_market_changed(self, _event=None) -> None:
        self.market_directory_search_var.set("")
        self.market_directory_page = None
        self.load_market_directory(0)

    def load_market_directory(self, page: int = 0, search_text: str = "") -> None:
        if self.market_directory_loading:
            return
        self.market_directory_loading = True
        market = self._current_market_code()
        self.market_directory_status_var.set(f"正在读取{MARKET_LABELS[market]}全市场股票…")
        self.market_directory_market_combo.configure(state="disabled")
        self.market_directory_previous_button.configure(state="disabled")
        self.market_directory_next_button.configure(state="disabled")

        def worker() -> None:
            try:
                client = MarketDirectoryClient(page_size=100, market=market)
                result = client.search(search_text) if search_text else client.fetch_page(page)
                self.events.put(("market_directory_results", result, search_text))
            except Exception as exc:
                self.events.put(("market_directory_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def search_market_directory(self) -> None:
        self.load_market_directory(0, self.market_directory_search_var.get().strip())

    def previous_market_directory_page(self) -> None:
        if self.market_directory_search_var.get().strip():
            self.market_directory_search_var.set("")
        self.load_market_directory(max(0, self._current_market_page() - 1))

    def next_market_directory_page(self) -> None:
        if self.market_directory_search_var.get().strip():
            self.market_directory_search_var.set("")
        self.load_market_directory(self._current_market_page() + 1)

    def _render_market_directory(self, result: MarketDirectoryPage, search_text: str) -> None:
        self.market_directory_market_combo.configure(state="readonly")
        if result.market != self._current_market_code():
            self.load_market_directory(0, self.market_directory_search_var.get().strip())
            return
        self.market_directory_page = result
        for item in self.market_directory_tree.get_children():
            self.market_directory_tree.delete(item)
        for entry in result.entries:
            change_tag = "UP" if entry.change_pct > 0 else "DOWN" if entry.change_pct < 0 else "FLAT"
            previous_price = self.market_directory_last_prices.get(entry.symbol)
            movement_tag = self.market_directory_price_directions.get(entry.symbol, "")
            if previous_price is not None:
                if entry.price > previous_price:
                    movement_tag = "PRICE_UP"
                elif entry.price < previous_price:
                    movement_tag = "PRICE_DOWN"
            self.market_directory_last_prices[entry.symbol] = entry.price
            if movement_tag:
                self.market_directory_price_directions[entry.symbol] = movement_tag
            market_cap = (
                f"{self._currency_prefix(entry.currency)}{entry.market_cap / 1_000_000_000:.1f}B"
                if entry.market_cap >= 1_000_000_000
                else f"{self._currency_prefix(entry.currency)}{entry.market_cap / 1_000_000:.1f}M" if entry.market_cap else "—"
            )
            self.market_directory_tree.insert(
                "", "end", iid=entry.symbol,
                values=(
                    entry.symbol,
                    entry.name,
                    entry.exchange,
                    f"{self._currency_prefix(entry.currency)}{entry.price:,.2f}" if entry.price else "—",
                    f"{entry.change_pct:+.2f}%",
                    f"{entry.volume:,}" if entry.volume else "—",
                    market_cap,
                    "★ 已加入" if entry.symbol in self.symbols else "—",
                ),
                tags=(directional_row_tag(change_tag, movement_tag),),
            )
        market_label = MARKET_LABELS[result.market]
        if search_text:
            self.market_directory_status_var.set(
                f"{market_label}搜索“{search_text}” · 返回 {len(result.entries)} 只 · 右键可加入自选"
            )
        else:
            first = result.page * result.page_size + 1 if result.entries else 0
            last = result.page * result.page_size + len(result.entries)
            self.market_directory_status_var.set(
                f"{market_label}全市场约 {result.total:,} 只 · 当前 {first:,}–{last:,} · 第 {result.page + 1} 页"
            )
        self.market_directory_previous_button.configure(state="normal" if result.page > 0 and not search_text else "disabled")
        has_next = (result.page + 1) * result.page_size < result.total
        self.market_directory_next_button.configure(state="normal" if has_next and not search_text else "disabled")
        self._sync_selected_price_styles()

    @staticmethod
    def _currency_prefix(currency: str) -> str:
        return "HK$" if currency.upper() == "HKD" else "$"

    def show_market_directory_menu(self, event) -> None:
        item = self.market_directory_tree.identify_row(event.y)
        if not item:
            return
        self.market_directory_tree.selection_set(item)
        self.market_directory_tree.focus(item)
        self.market_directory_menu.tk_popup(event.x_root, event.y_root)

    def add_selected_market_symbol(self) -> None:
        selected = self.market_directory_tree.selection()
        if not selected:
            messagebox.showwarning("未选择股票", "请先在全市场股票列表中选择一只股票。")
            return
        symbol = selected[0]
        if symbol not in self.symbols:
            self.symbol_entry.delete(0, "end")
            self.symbol_entry.insert(0, symbol)
            self.add_symbol()
        self.notebook.select(0)
        if self.tree.exists(symbol):
            self.tree.selection_set(symbol)
            self.tree.see(symbol)

    def toggle_mover_monitor(self) -> None:
        if self.mover_running:
            self.stop_mover_monitor()
        else:
            self.start_mover_monitor()

    def refresh_movers(self) -> None:
        if not self.mover_running or self.mover_worker is None:
            self.start_mover_monitor()
            return
        self.mover_status_var.set("已请求立即刷新，正在取得最新 1 分钟行情…")
        self.mover_worker.refresh()

    def start_mover_monitor(self) -> None:
        if self.mover_running:
            return
        self.mover_running = True
        self.mover_started_once = True
        self.mover_button.configure(text="停止自动扫描")
        self.mover_status_var.set("正在启动全市场扫描…")
        self.mover_worker = MarketMoverWorker(self.events, interval_seconds=60)
        self.mover_worker.start()

    def stop_mover_monitor(self) -> None:
        if self.mover_worker is None:
            self._set_mover_stopped()
            return
        self.mover_status_var.set("正在停止全市场扫描…")
        self.mover_button.configure(state="disabled")
        self.mover_worker.stop()

    def _set_mover_stopped(self) -> None:
        self.mover_running = False
        self.mover_worker = None
        self.mover_button.configure(text="开始自动扫描", state="normal")
        self.mover_status_var.set("全市场自动扫描已停止")

    def _render_movers(self, tree: ttk.Treeview, rows: list[MoverResult]) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for result in rows:
            item_id = f"{result.side}:{result.symbol}"
            previous_price = self.mover_last_prices.get(item_id)
            movement_tag = self.mover_price_directions.get(item_id, "")
            if previous_price is not None:
                if result.price > previous_price:
                    movement_tag = "PRICE_UP"
                elif result.price < previous_price:
                    movement_tag = "PRICE_DOWN"
            self.mover_last_prices[item_id] = result.price
            if movement_tag:
                self.mover_price_directions[item_id] = movement_tag
            quote_time = result.quote_time.astimezone(NEW_YORK).strftime("%H:%M:%S") if result.quote_time else "—"
            tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    result.rank,
                    result.symbol,
                    result.name,
                    f"${result.price:,.2f}",
                    f"{result.change_pct:+.2f}%",
                    f"{result.volume:,}" if result.volume else "—",
                    f"${result.buy_point:,.2f}" if result.buy_point else "—",
                    f"${result.sell_point:,.2f}" if result.sell_point else "—",
                    result.opportunity,
                    quote_time,
                ),
                tags=(directional_row_tag(result.tag, movement_tag),),
            )
        self._sync_selected_price_styles()

    def add_selected_mover(self) -> None:
        gainers_selected = self.gainers_tree.selection()
        losers_selected = self.losers_tree.selection()
        selected = gainers_selected or losers_selected
        tree = self.gainers_tree if gainers_selected else self.losers_tree
        if not selected:
            messagebox.showwarning("未选择股票", "请先从暴涨榜或暴跌榜选择一只股票。")
            return
        symbol = str(tree.item(selected[0], "values")[1])
        if symbol in self.symbols:
            self.notebook.select(0)
            self.tree.selection_set(symbol)
            return
        self.symbol_entry.delete(0, "end")
        self.symbol_entry.insert(0, symbol)
        self.add_symbol()
        self.notebook.select(0)

    def open_api_config(self) -> None:
        env_path = BASE_DIR / ".env"
        if not env_path.exists():
            env_path.write_text(
                "# Select: Alpaca IEX, Yahoo Finance, Massive / Polygon, IBKR Gateway, IBKR TWS + Yahoo 行情\n"
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
                "# TWS read-only positions: Paper 7497, Live 7496\n"
                "TWS_HOST=127.0.0.1\nTWS_PORT=7497\nTWS_CLIENT_ID=17\nTWS_ACCOUNT_ID=\n\n"
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
        if provider == TWS_PROVIDER:
            self.refresh_account_summary()

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
            if self.tree.exists(symbol):
                self.tree.delete(symbol)
            position = self.positions.get(symbol, {})
            avg_cost = float(position.get("avg_cost", 0))
            quantity = float(position.get("quantity", 0))
            self.tree.insert(
                "", "end", iid=symbol,
                values=(symbol, self.stock_names.get(symbol, "查询中…"), "—", "—", "—", f"${avg_cost:,.2f}" if avg_cost else "—", f"{quantity:g}" if quantity else "—", "待启动", "—", "—", "—", "—", "—"),
            )
            if symbol in self.levels:
                self._render_row(symbol, self.levels[symbol]["price"], self.quote_times.get(symbol))
        self._apply_scope()
        self._refresh_watchlist()

    def _active_tree(self):
        return self.watch_tree if self.notebook.select() == str(self.watch_card) else self.tree

    def _apply_scope(self):
        for symbol in self.symbols:
            if self.tree.exists(symbol):
                if self.scope_var.get() == "positions" and self.positions.get(symbol, {}).get("quantity", 0) <= 0:
                    self.tree.detach(symbol)
                else:
                    self.tree.move(symbol, "", "end")

    def _refresh_watchlist(self):
        for symbol in self.watch_tree.get_children():
            if symbol not in self.symbols:
                self.watch_tree.delete(symbol)
        for symbol in self.symbols:
            position = self.positions.get(symbol, {})
            quantity = float(position.get("quantity", 0))
            cost = float(position.get("avg_cost", 0))
            price = self.levels.get(symbol, {}).get("price", 0)
            row = (symbol, self.stock_names.get(symbol, "—"), f"${price:,.2f}" if price else "—",
                   "持仓" if quantity > 0 else "未持仓", f"{quantity:g}" if quantity else "—",
                   f"${cost:,.2f}" if quantity else "—", f"${price * quantity:,.2f}" if price and quantity else "—")
            if not self.watch_tree.exists(symbol):
                self.watch_tree.insert("", "end", iid=symbol)
            base_tag = "HELD" if quantity else "WATCHLIST"
            movement_tag = self.price_directions.get(symbol, "")
            self.watch_tree.item(
                symbol,
                values=row,
                tags=(directional_row_tag(base_tag, movement_tag),),
            )
        held = sum(self.positions.get(symbol, {}).get("quantity", 0) > 0 for symbol in self.symbols)
        self.count_var.set(f"自选 {len(self.symbols)} 只 · 持仓 {held} 只")

    def _probability_account_context(self) -> tuple[float, float, float | None]:
        configured_value = float(self.risk_settings["account_value"])
        live_value = self.account_summary.get("NetLiquidation")
        account_value = (
            float(live_value)
            if isinstance(live_value, (int, float)) and math.isfinite(float(live_value)) and float(live_value) > 0
            else configured_value
        )
        portfolio_value = 0.0
        for symbol, position in self.positions.items():
            quantity = max(0.0, float(position.get("quantity", 0.0)))
            reference_price = self.levels.get(symbol, {}).get("price", position.get("avg_cost", 0.0))
            try:
                portfolio_value += quantity * max(0.0, float(reference_price))
            except (TypeError, ValueError):
                continue
        available = self.account_summary.get("AvailableFunds")
        available_funds = (
            float(available)
            if isinstance(available, (int, float)) and math.isfinite(float(available))
            else None
        )
        return account_value, portfolio_value, available_funds

    def _read_tws_config(self) -> tuple[str, int, int, str]:
        load_dotenv(BASE_DIR / ".env", override=True)
        host = os.getenv("TWS_HOST", "127.0.0.1").strip()
        port = int(os.getenv("TWS_PORT", "7497"))
        client_id = int(os.getenv("TWS_CLIENT_ID", "17"))
        account = os.getenv("TWS_ACCOUNT_ID", "").strip()
        if not host or not 1 <= port <= 65535 or not 0 <= client_id <= 2_147_483_647:
            raise ValueError
        return host, port, client_id, account

    @staticmethod
    def _account_money(summary: dict, key: str) -> str:
        value = summary.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return "—"
        currency = str(summary.get("currency", "USD"))
        prefix = "$" if currency == "USD" else f"{currency} "
        return f"{prefix}{float(value):,.2f}"

    def _refresh_account_summary_text(self) -> None:
        if not self.account_details_visible:
            self.account_summary_var.set("TWS 当前账户：••••••（本次运行内暂时隐藏）")
            self.account_visibility_button.configure(text="暂时显示")
            return
        self.account_visibility_button.configure(text="暂时隐藏")
        if not self.account_summary:
            self.account_summary_var.set("TWS 当前账户：尚未读取")
            return
        summary = self.account_summary
        self.account_summary_var.set(
            f"账户 {summary.get('account', '—')}  |  净资产 {self._account_money(summary, 'NetLiquidation')}"
            f"  |  可用资金 {self._account_money(summary, 'AvailableFunds')}"
            f"  |  购买力 {self._account_money(summary, 'BuyingPower')}"
            f"  |  现金 {self._account_money(summary, 'TotalCashValue')}"
            f"  |  未实现盈亏 {self._account_money(summary, 'UnrealizedPnL')}"
        )

    def toggle_account_details(self) -> None:
        self.account_details_visible = not self.account_details_visible
        self._refresh_account_summary_text()

    def refresh_account_summary(self) -> None:
        if self.syncing_positions or str(self.account_refresh_button.cget("state")) == "disabled":
            return
        try:
            host, port, client_id, account = self._read_tws_config()
        except ValueError:
            self.account_summary_var.set("TWS 当前账户：配置无效，请检查主机、端口和 Client ID")
            return
        self.account_refresh_button.configure(state="disabled")
        self.sync_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        if self.account_details_visible:
            self.account_summary_var.set("TWS 当前账户：正在读取…")

        def worker() -> None:
            try:
                summary = fetch_account_summary(
                    host,
                    port,
                    auxiliary_client_id(client_id, 101),
                    account,
                )
                self.events.put(("tws_account_summary", summary))
            except Exception as exc:
                self.events.put(("tws_account_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def open_tws_chart_from_event(self, event) -> None:
        symbol = self.tree.identify_row(event.y)
        if not symbol:
            return
        self.tree.selection_set(symbol)
        self.tree.focus(symbol)
        self.on_tree_select()
        self.open_tws_chart(symbol)

    def open_tws_chart(self, symbol: str) -> None:
        try:
            host, port, base_client_id, _account = self._read_tws_config()
        except ValueError:
            messagebox.showerror("TWS 配置错误", "请检查 TWS_HOST、TWS_PORT 和 TWS_CLIENT_ID。")
            return

        existing = self.chart_windows.get(symbol)
        if existing and existing["window"].winfo_exists():
            existing["window"].destroy()

        window = tk.Toplevel(self.root)
        window.title(f"{symbol} · TWS 5分钟行情图 · v{APP_VERSION} · Design by Mars")
        window.geometry("1040x650")
        window.minsize(760, 480)
        window.configure(bg="#18243a")
        if self.app_icons:
            window.iconphoto(True, *self.app_icons)
        status = tk.StringVar(value=f"正在从 TWS {host}:{port} 读取 {symbol} 最近 2 日的 5 分钟行情…")
        tk.Label(
            window,
            textvariable=status,
            bg="#18243a",
            fg="#dce9f8",
            anchor="w",
            font=("Microsoft YaHei UI", int(self.ui_settings["ui_font_size"]), "bold"),
            padx=16,
            pady=10,
        ).pack(fill="x")
        canvas = tk.Canvas(window, bg="#172238", highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.chart_windows[symbol] = {"window": window, "canvas": canvas, "status": status, "bars": []}
        canvas.bind("<Configure>", lambda _event, stock=symbol: self._draw_tws_chart(stock))
        window.protocol("WM_DELETE_WINDOW", lambda stock=symbol: self._close_chart(stock))

        self.tws_request_serial += 1
        client_id = auxiliary_client_id(base_client_id, 200 + self.tws_request_serial)

        def worker() -> None:
            try:
                bars = fetch_intraday_bars(symbol, host, port, client_id)
                self.events.put(("tws_chart", symbol, bars))
            except Exception as exc:
                self.events.put(("tws_chart_error", symbol, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _close_chart(self, symbol: str) -> None:
        chart = self.chart_windows.pop(symbol, None)
        if chart and chart["window"].winfo_exists():
            chart["window"].destroy()

    def _draw_tws_chart(self, symbol: str) -> None:
        chart = self.chart_windows.get(symbol)
        if not chart or not chart["window"].winfo_exists():
            return
        canvas: tk.Canvas = chart["canvas"]
        bars = list(chart.get("bars", []))[-180:]
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        if not bars or width < 200 or height < 180:
            canvas.create_text(width / 2, height / 2, text="正在读取 TWS 行情…", fill="#a9bad0", font=("Microsoft YaHei UI", int(self.ui_settings["ui_font_size"]) + 1))
            return

        left, right, top, bottom = 72, 22, 24, 48
        plot_width = max(1, width - left - right)
        plot_height = max(1, height - top - bottom)
        levels = self.levels.get(symbol, {})
        marker_values = [
            float(levels[key]) for key in ("buy_point", "stop_point")
            if isinstance(levels.get(key), (int, float)) and float(levels[key]) > 0
        ]
        prices = [float(bar["low"]) for bar in bars] + [float(bar["high"]) for bar in bars] + marker_values
        low, high = min(prices), max(prices)
        padding = max((high - low) * 0.08, high * 0.002, 0.01)
        low -= padding
        high += padding

        def point(index: int, price: float) -> tuple[float, float]:
            x = left + (index / max(1, len(bars) - 1)) * plot_width
            y = top + (high - price) / max(0.000001, high - low) * plot_height
            return x, y

        for line in range(6):
            y = top + line * plot_height / 5
            value = high - line * (high - low) / 5
            canvas.create_line(left, y, width - right, y, fill="#2c3d58", dash=(2, 4))
            canvas.create_text(left - 8, y, text=f"{value:,.2f}", fill="#9fb0c7", anchor="e", font=("Consolas", max(8, int(self.ui_settings["table_font_size"]) - 1)))

        candle_width = max(1, min(5, plot_width / max(1, len(bars)) * 0.55))
        close_points: list[float] = []
        for index, bar in enumerate(bars):
            x, high_y = point(index, float(bar["high"]))
            _, low_y = point(index, float(bar["low"]))
            _, open_y = point(index, float(bar["open"]))
            _, close_y = point(index, float(bar["close"]))
            color = "#58d6a9" if float(bar["close"]) >= float(bar["open"]) else "#ff7485"
            canvas.create_line(x, high_y, x, low_y, fill=color)
            canvas.create_rectangle(x - candle_width, min(open_y, close_y), x + candle_width, max(open_y, close_y) + 1, fill=color, outline=color)
            close_points.extend((x, close_y))
        if len(close_points) >= 4:
            canvas.create_line(*close_points, fill="#7fc7ff", width=2, smooth=False)

        for key, label, color in (("buy_point", "突破买入线", "#58d6a9"), ("stop_point", "卖出触发点", "#ff7485")):
            value = levels.get(key)
            if not isinstance(value, (int, float)) or float(value) <= 0:
                continue
            _x, y = point(0, float(value))
            canvas.create_line(left, y, width - right, y, fill=color, width=2, dash=(7, 4))
            canvas.create_text(left + 8, y - 8, text=f"{label} ${float(value):,.2f}", fill=color, anchor="w", font=("Microsoft YaHei UI", max(8, int(self.ui_settings["ui_font_size"]) - 1), "bold"))

        label_count = min(6, len(bars))
        for number in range(label_count):
            index = round(number * (len(bars) - 1) / max(1, label_count - 1))
            x, _y = point(index, low)
            stamp = bars[index]["time"].astimezone(NEW_YORK)
            canvas.create_text(x, height - 23, text=stamp.strftime("%m-%d %H:%M"), fill="#9fb0c7", font=("Consolas", max(8, int(self.ui_settings["table_font_size"]) - 2)))

        last = bars[-1]
        canvas.create_text(
            left + 8,
            top + 8,
            text=f"{symbol}  最新 ${float(last['close']):,.2f}  O {float(last['open']):,.2f}  H {float(last['high']):,.2f}  L {float(last['low']):,.2f}",
            fill="#f1f6fc",
            anchor="nw",
            font=("Consolas", int(self.ui_settings["table_font_size"]), "bold"),
        )

    def sync_positions(self, start_after=False):
        if self.syncing_positions:
            return
        try:
            host, port, client_id, account = self._read_tws_config()
        except ValueError:
            messagebox.showerror("TWS 配置错误", "请检查 TWS_HOST、TWS_PORT 和 TWS_CLIENT_ID。")
            return
        self.syncing_positions = True
        self.resume_after_sync = start_after
        self.sync_button.configure(state="disabled")
        self.account_refresh_button.configure(state="disabled")
        self.clear_positions_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.tws_message.set("正在读取 TWS 持仓…")

        def worker():
            try:
                snapshots = fetch_positions(host, port, client_id)
                try:
                    summary = fetch_account_summary(
                        host,
                        port,
                        auxiliary_client_id(client_id, 101),
                        account,
                    )
                    self.events.put(("tws_account_summary", summary))
                except Exception as exc:
                    self.events.put(("tws_account_error", str(exc)))
                self.events.put(("tws_positions", snapshots, account))
            except Exception as exc:
                self.events.put(("tws_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_position_sync(self, error=None):
        self.syncing_positions = False
        self.sync_button.configure(state="normal")
        self.account_refresh_button.configure(state="normal")
        self.clear_positions_button.configure(state="normal")
        self.start_button.configure(state="disabled" if self.running else "normal")
        resume = self.resume_after_sync
        self.resume_after_sync = False
        if error:
            self.tws_message.set("持仓同步失败，原有数据已保留")
            self._append_log(f"TWS 持仓同步失败：{error}")
            messagebox.showerror("持仓同步失败", error)
        elif resume:
            self.start_monitoring(sync_tws=False)

    def _apply_tws_positions(self, snapshots, account):
        try:
            previous = json.loads(TWS_IMPORT_FILE.read_text(encoding="utf-8")) if TWS_IMPORT_FILE.exists() else []
            positions, imported, skipped = merge_positions(self.positions, snapshots, previous, account)
            write_positions(positions)
            TWS_IMPORT_FILE.write_text(json.dumps(imported), encoding="utf-8")
            self.positions = positions
            new_symbols = [symbol for symbol in imported if symbol not in self.symbols]
            self.symbols.extend(new_symbols)
            write_watchlist(self.symbols)
            self._populate_symbols()
            self.on_tree_select()
            self._resolve_missing_names(new_symbols)
            message = f"已同步 {len(imported)} 只持仓"
            if skipped:
                message += f" · 跳过 {skipped} 项不支持的持仓"
            self.tws_message.set(message)
            self._append_log(message)
            if new_symbols and self.running:
                self.pending_tws_start = True
                self.stop_monitoring(restart=True)
            self._finish_position_sync()
        except Exception as exc:
            self._finish_position_sync(str(exc))

    def clear_positions(self):
        if self.syncing_positions or not messagebox.askyesno("清除全部本地持仓？", "自选股票会保留，之后可从 TWS 重新读取持仓。"):
            return
        write_positions({})
        TWS_IMPORT_FILE.write_text("[]", encoding="utf-8")
        self.positions.clear()
        self._populate_symbols()
        self.avg_cost_entry.delete(0, "end")
        self.quantity_entry.delete(0, "end")
        self.initial_stop_entry.delete(0, "end")
        self.tws_message.set("本地持仓已清除")

    def add_symbol(self) -> None:
        symbol = self.symbol_entry.get().strip().upper()
        if not SYMBOL_PATTERN.fullmatch(symbol):
            messagebox.showwarning("代码无效", "请输入有效代码，例如 AAPL、BRK.B 或港股 0700.HK。")
            return
        if symbol in self.symbols:
            self.tree.selection_set(symbol)
            return
        self.symbols.append(symbol)
        write_watchlist(self.symbols)
        self.tree.insert("", "end", iid=symbol, values=(symbol, self.stock_names.get(symbol, "查询中…"), "—", "—", "—", "—", "—", "待启动", "—", "—", "—", "—", "—"))
        self.symbol_entry.delete(0, "end")
        self.count_var.set(f"监控 {len(self.symbols)} 只股票")
        self._apply_scope()
        self._refresh_watchlist()
        self._resolve_missing_names([symbol])
        if self.running:
            self._append_log(f"已添加 {symbol}；停止并重新启动后应用新的订阅。")

    def remove_selected(self) -> None:
        selected = list(self._active_tree().selection())
        if not selected:
            return
        self.symbols = [symbol for symbol in self.symbols if symbol not in selected]
        for symbol in selected:
            self.tree.delete(symbol)
            self.levels.pop(symbol, None)
            self.last_rendered_prices.pop(symbol, None)
            self.price_directions.pop(symbol, None)
        write_watchlist(self.symbols)
        self._refresh_watchlist()
        if self.running:
            self._append_log("监控列表已改变；停止并重新启动后应用新的订阅。")

    def on_tree_select(self, _event=None) -> None:
        self._sync_selected_price_styles(_event)
        selected = self._active_tree().selection()
        if not selected:
            return
        symbol = selected[0]
        position = self.positions.get(symbol, {"avg_cost": 0, "quantity": 0})
        self.selected_symbol_var.set(f"所选：{symbol}")
        self.avg_cost_entry.delete(0, "end")
        self.quantity_entry.delete(0, "end")
        self.initial_stop_entry.delete(0, "end")
        if position.get("initial_stop"):
            self.initial_stop_entry.insert(0, str(position["initial_stop"]))
        if float(position.get("avg_cost", 0)) > 0:
            self.avg_cost_entry.insert(0, f"{float(position['avg_cost']):.4f}")
        if float(position.get("quantity", 0)) > 0:
            self.quantity_entry.insert(0, f"{float(position['quantity']):g}")

    def save_position(self) -> None:
        selected = self._active_tree().selection()
        if not selected:
            messagebox.showwarning("未选择股票", "请先在表格中选择一只股票。")
            return
        symbol = selected[0]
        try:
            avg_cost = float(self.avg_cost_entry.get().strip() or "0")
            quantity = float(self.quantity_entry.get().strip() or "0")
            raw_stop = self.initial_stop_entry.get().strip()
            initial_stop = float(raw_stop) if raw_stop else None
            if initial_stop is not None and (not math.isfinite(initial_stop) or not 0 < initial_stop < avg_cost):
                raise ValueError
            if not math.isfinite(avg_cost) or not math.isfinite(quantity) or avg_cost < 0 or quantity < 0 or (quantity > 0 and avg_cost <= 0):
                raise ValueError
        except ValueError:
            messagebox.showwarning("持仓输入无效", "均价必须大于0，股数非负；可选保护线必须低于成本。留空仍会按价格通道给出买卖提示。")
            return

        if quantity == 0:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = {"avg_cost": avg_cost, "quantity": quantity, "initial_stop": initial_stop}
        write_positions(self.positions)
        self._apply_scope()
        self._refresh_watchlist()
        if symbol in self.levels:
            self._render_row(symbol, float(self.levels[symbol]["price"]), self.quote_times.get(symbol))
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
            self._render_row(symbol, float(values["price"]), self.quote_times.get(symbol))
        self._append_log(
            f"风控已保存：账户 ${account_value:,.0f}，单笔风险 {risk_pct:g}%，单股资金上限 {max_position_pct:g}%。"
        )

    def start_monitoring(self, sync_tws=True, is_retry=False) -> None:
        if self.running or self.syncing_positions:
            return
        if self.restart_job is not None:
            self.root.after_cancel(self.restart_job)
            self.restart_job = None
        if self.provider_var.get() == TWS_PROVIDER and sync_tws:
            self.sync_positions(start_after=True)
            return
        if not self.symbols:
            messagebox.showwarning("没有股票", "请先添加至少一只需要监控的股票。")
            return

        self.manual_stop_requested = False
        self.restart_pending = False
        if not is_retry:
            self.restart_attempts = 0

        load_dotenv(BASE_DIR / ".env", override=True)
        provider = self.provider_var.get()

        if provider == "Alpaca IEX":
            api_key = os.getenv("ALPACA_API_KEY", "").strip()
            api_secret = os.getenv("ALPACA_API_SECRET", "").strip()
            if not api_key or not api_secret or api_key.startswith("replace_") or api_secret.startswith("replace_"):
                messagebox.showerror("缺少密钥", "请点击“配置密钥”填写 Alpaca API Key 和 Secret。")
                return
            worker: ProviderWorker = AlpacaWorker(api_key, api_secret, self.symbols.copy(), self.events)
        elif provider in {"Yahoo Finance", TWS_PROVIDER}:
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
        self.quote_times.clear()
        self.history_loaded_day = datetime.now(NEW_YORK).date()
        self.last_market_event_at = time.monotonic()
        self.running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.connection_var.set("正在连接…")
        self.feed_var.set(provider)
        self.provider_combo.configure(state="disabled")
        self._append_log(f"开始使用 {provider} 加载历史数据并连接行情。")
        self.worker = worker
        self.worker.start()

    def stop_monitoring(self, restart=False) -> None:
        self.resume_after_sync = False
        self.manual_stop_requested = not restart
        self.restart_pending = restart
        if self.worker is not None:
            self.connection_var.set("正在停止…")
            self.worker.stop()
        else:
            self._set_stopped()

    def _set_stopped(self) -> None:
        should_restart = self.restart_pending and not self.manual_stop_requested
        self.restart_pending = False
        self.running = False
        self.worker = None
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.provider_combo.configure(state="readonly")
        self.connection_var.set("已停止")
        for symbol, values in list(self.levels.items()):
            self._render_row(symbol, float(values['price']), self.quote_times.get(symbol))
        if self.pending_tws_start:
            self.pending_tws_start = False
            should_restart = True
        if should_restart:
            delay_ms = min(30_000, 1_000 * (2 ** min(self.restart_attempts, 5)))
            self.restart_attempts += 1
            self.connection_var.set(f"行情中断，{delay_ms // 1000} 秒后自动重连…")
            def restart() -> None:
                self.restart_job = None
                self.start_monitoring(sync_tws=False, is_retry=True)
            self.restart_job = self.root.after(delay_ms, restart)

    def _process_events(self) -> None:
        latest_trades: dict[str, tuple[float, object]] = {}
        try:
            for _ in range(2000):
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "trade":
                    latest_trades[event[1]] = (event[2], event[3])
                elif kind == "tws_positions":
                    self._apply_tws_positions(event[1], event[2])
                elif kind == "tws_error":
                    self._finish_position_sync(event[1])
                elif kind == "tws_account_summary":
                    self.account_summary = event[1]
                    self._refresh_account_summary_text()
                    for symbol, values in list(self.levels.items()):
                        self._render_row(symbol, float(values["price"]), self.quote_times.get(symbol))
                    self._append_log(f"已读取 TWS 账户 {self.account_summary.get('account', '—')} 明细。")
                    if not self.syncing_positions:
                        self.account_refresh_button.configure(state="normal")
                        self.sync_button.configure(state="normal")
                        self.start_button.configure(state="disabled" if self.running else "normal")
                elif kind == "tws_account_error":
                    self._append_log(f"TWS 账户明细读取失败：{event[1]}")
                    if not self.account_summary:
                        self.account_summary_var.set("TWS 当前账户：明细读取失败（持仓仍可正常同步）")
                    if not self.syncing_positions:
                        self.account_refresh_button.configure(state="normal")
                        self.sync_button.configure(state="normal")
                        self.start_button.configure(state="disabled" if self.running else "normal")
                elif kind == "tws_chart":
                    symbol, bars = event[1], event[2]
                    chart = self.chart_windows.get(symbol)
                    if chart and chart["window"].winfo_exists():
                        chart["bars"] = bars
                        latest = bars[-1]["time"].astimezone(NEW_YORK).strftime("%Y-%m-%d %H:%M ET")
                        chart["status"].set(f"TWS 只读行情 · 5分钟线 · {len(bars)} 根 · 最新 {latest}")
                        self._draw_tws_chart(symbol)
                elif kind == "tws_chart_error":
                    symbol, error = event[1], event[2]
                    chart = self.chart_windows.get(symbol)
                    if chart and chart["window"].winfo_exists():
                        chart["status"].set(f"TWS 图表读取失败：{error}")
                        chart["canvas"].delete("all")
                        chart["canvas"].create_text(
                            max(1, chart["canvas"].winfo_width()) / 2,
                            max(1, chart["canvas"].winfo_height()) / 2,
                            text=f"无法取得 {symbol} 图表\n{error}\n\n请确认 TWS 已开启 Socket API，并具备该股票行情权限。",
                            fill="#ffadb5",
                            justify="center",
                            font=("Microsoft YaHei UI", int(self.ui_settings["ui_font_size"]) + 1),
                        )
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
                    self._refresh_watchlist()
                elif kind == "mover_status":
                    self.mover_status_var.set(event[1])
                elif kind == "mover_results":
                    self._render_movers(self.gainers_tree, event[1])
                    self._render_movers(self.losers_tree, event[2])
                    scanned_at = event[3].astimezone(NEW_YORK).strftime("%Y-%m-%d %H:%M:%S ET")
                    self.mover_status_var.set(
                        f"Yahoo 全市场筛选 + 1分钟行情校准 · 每 60 秒 · 本次 {len(event[1]) + len(event[2])} 只 · {scanned_at}"
                    )
                elif kind == "mover_error":
                    self.mover_status_var.set(f"全市场扫描失败，将自动重试：{event[1]}")
                    self._append_log(f"全市场涨跌榜扫描失败：{event[1]}")
                elif kind == "mover_stopped":
                    self._set_mover_stopped()
                elif kind == "market_directory_results":
                    self.market_directory_loading = False
                    self._render_market_directory(event[1], event[2])
                elif kind == "market_directory_error":
                    self.market_directory_loading = False
                    self.market_directory_market_combo.configure(state="readonly")
                    self.market_directory_status_var.set(f"全市场股票读取失败：{event[1]}")
                    self.market_directory_previous_button.configure(state="normal" if self._current_market_page() > 0 else "disabled")
                    self.market_directory_next_button.configure(state="normal")
                    self._append_log(f"全市场股票读取失败：{event[1]}")
                elif kind == "error":
                    self.connection_var.set(event[1])
                    self._append_log(event[1])
                elif kind == "stopped":
                    if self.running and not self.manual_stop_requested:
                        self.restart_pending = True
                    self._set_stopped()
        except queue.Empty:
            pass

        for symbol, (price, timestamp) in latest_trades.items():
            self._apply_trade(symbol, price, timestamp)
        self.root.after(100, self._process_events)

    def _apply_snapshot(self, symbol: str, values: dict, timestamp) -> None:
        self.levels[symbol] = values
        self.quote_times[symbol] = timestamp
        self.last_market_event_at = time.monotonic()
        self.restart_attempts = 0
        self._render_row(symbol, float(values["price"]), timestamp)
        if values["status"] in {"BUY_ALERT", "SELL_ALERT"}:
            self._trigger_alert(symbol, values)

    def _apply_trade(self, symbol: str, price: float, timestamp) -> None:
        if symbol not in self.levels:
            return
        values = self.levels[symbol]
        self.quote_times[symbol] = timestamp
        self.last_market_event_at = time.monotonic()
        self.restart_attempts = 0
        old_status = str(values["status"])
        signal_ready = bool(values.get("signal_ready", True))
        if not signal_ready:
            values["status"] = "DATA_SHORT"
        elif price >= float(values["buy_point"]):
            values["status"] = "BUY_ALERT"
        elif price <= float(values["stop_point"]):
            values["status"] = "SELL_ALERT"
        else:
            values["status"] = "WATCH"
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
            reason = observation_reason(price, timestamp, values.get("history_date"))
            if reason:
                plan["action"] = f"仅观察：{reason}"
                status_text = "仅观察"
            if signal_ready:
                log_text = (
                    f"行情 {symbol} {self.stock_names.get(symbol, '')} | ${price:,.2f} | "
                    f"{status_text} | 突破买入线 ${float(values['buy_point']):,.2f} | "
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

        if values["status"] in {"BUY_ALERT", "SELL_ALERT"} and old_status != values["status"]:
            self._trigger_alert(symbol, values)

    def _render_row(self, symbol: str, price: float, timestamp) -> None:
        previous_price = self.last_rendered_prices.get(symbol)
        movement_tag = self.price_directions.get(symbol, "")
        if previous_price is not None:
            if price > previous_price:
                movement_tag = "PRICE_UP"
            elif price < previous_price:
                movement_tag = "PRICE_DOWN"
        self.last_rendered_prices[symbol] = price
        if movement_tag:
            self.price_directions[symbol] = movement_tag
        values = self.levels[symbol]
        status_text, status_tag = display_status(values, price)
        position = self.positions.get(symbol, {"avg_cost": 0, "quantity": 0})
        avg_cost = float(position.get("avg_cost", 0))
        quantity = float(position.get("quantity", 0))
        plan = build_position_plan(
            values,
            position,
            self.risk_settings["account_value"],
            self.risk_settings["risk_pct"],
            self.risk_settings["max_position_pct"],
        )
        account_value, portfolio_value, available_funds = self._probability_account_context()
        probabilities = estimate_action_probabilities(
            values,
            position,
            account_value,
            self.risk_settings["max_position_pct"],
            portfolio_value,
            available_funds,
        )
        reason = observation_reason(price, timestamp, values.get("history_date"))
        if not self.running:
            reason = "监控已停止"
        if reason:
            status_text, status_tag = "仅观察", "DATA_SHORT"
            plan["action"] = f"仅观察：{reason}"
        if hasattr(timestamp, "astimezone"):
            updated = timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        else:
            updated = str(timestamp)
        signal_ready = bool(values.get("signal_ready", True))
        buy_text = f"${float(values['buy_point']):,.2f}" if signal_ready else "—"
        stop_text = f"${float(plan['position_stop']):,.2f}" if signal_ready and plan['position_stop'] > 0 else "—"
        if reason or not signal_ready:
            buy_probability_text = reduce_probability_text = "—"
        else:
            buy_probability_text = f"{int(probabilities['buy_probability'])}% {probabilities['buy_label']}"
            reduce_probability_text = f"{int(probabilities['reduce_probability'])}% {probabilities['reduce_label']}"
        quality_text = (
            f"{values.get('signal_quality', '价格通道')} · {int(values.get('history_days', 0))}日 · "
            f"RSI {float(values.get('rsi14', 50)):.0f} · 5日 {float(values.get('momentum_5d_pct', 0)):+.1f}%"
        )
        row = (
            symbol,
            self.stock_names.get(symbol, "—"),
            f"${price:,.2f}",
            buy_text,
            stop_text,
            f"${avg_cost:,.2f}" if avg_cost > 0 else "—",
            f"{quantity:g}" if quantity > 0 else "—",
            status_text,
            buy_probability_text,
            reduce_probability_text,
            quality_text,
            str(plan["action"]),
            updated,
        )
        if self.tree.exists(symbol):
            self.tree.item(
                symbol,
                values=row,
                tags=(directional_row_tag(status_tag, movement_tag),),
            )
        self._refresh_watchlist()
        self._sync_selected_price_styles()

    def _sync_selected_price_styles(self, _event=None) -> None:
        mappings = (
            (self.tree, "Overview.Treeview", self.price_directions),
            (self.watch_tree, "Watchlist.Treeview", self.price_directions),
            (self.gainers_tree, "Mover.Treeview", self.mover_price_directions),
            (self.losers_tree, "Mover.Treeview", self.mover_price_directions),
            (self.market_directory_tree, "Market.Treeview", self.market_directory_price_directions),
        )
        mover_color = None
        for tree, style_name, directions in mappings:
            selected = tree.selection()
            direction = directions.get(selected[0], "") if selected else ""
            foreground = "#38d982" if direction == "PRICE_UP" else "#ff6678" if direction == "PRICE_DOWN" else "#ffffff"
            if style_name == "Mover.Treeview":
                mover_color = foreground if selected else mover_color
                continue
            self.app_style.map(
                style_name,
                background=[("selected", "#4b72a8")],
                foreground=[("selected", foreground)],
            )
        self.app_style.map(
            "Mover.Treeview",
            background=[("selected", "#4b72a8")],
            foreground=[("selected", mover_color or "#ffffff")],
        )

    def _trigger_alert(self, symbol: str, values: dict) -> None:
        if observation_reason(float(values['price']), self.quote_times.get(symbol), values.get('history_date')):
            return
        status = str(values.get("status", ""))
        if status not in {"BUY_ALERT", "SELL_ALERT"}:
            return
        side = "买入" if status == "BUY_ALERT" else "卖出"
        trigger = float(values["buy_point"] if status == "BUY_ALERT" else values["stop_point"])
        now = datetime.now(timezone.utc)
        state_key = f"{symbol}:{status}"
        alert_key = f"{state_key}:{now.date().isoformat()}"
        if self.alert_state.get(state_key) == alert_key:
            return
        message = (
            f"{side}点提示（只读观察） {symbol} | 现价 ${float(values['price']):.2f} | "
            f"{side}触发点 ${trigger:.2f} | 通道 ${float(values['stop_point']):.2f} - ${float(values['buy_point']):.2f}"
        )
        self.root.bell()
        self._append_log(message)
        record_alert(symbol, values, now)
        self.alert_state[state_key] = alert_key
        save_state(self.alert_state)
        threading.Thread(target=self._send_discord_safely, args=(message,), daemon=True).start()

    def _send_discord_safely(self, message: str) -> None:
        try:
            send_discord(message)
        except Exception as exc:
            self.events.put(("connection", f"Discord 提示发送失败：{exc}"))

    def _show_symbol_error(self, symbol: str, error: str) -> None:
        self.levels.pop(symbol, None)
        self.quote_times.pop(symbol, None)
        if self.tree.exists(symbol):
            position = self.positions.get(symbol, {})
            quantity = float(position.get("quantity", 0))
            cost = float(position.get("avg_cost", 0))
            self.tree.item(symbol, values=(symbol, self.stock_names.get(symbol, "—"), "—", "—", "—", f"${cost:,.2f}" if quantity else "—", f"{quantity:g}" if quantity else "—", "数据错误", "—", "—", "—", error[:32], "—"), tags=("ERROR",))
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
        if self.ui_settings.get("confirm_exit") and not messagebox.askyesno(
            "确认关闭？",
            "确定要关闭 Stock Signal Monitor 吗？",
            parent=self.root,
        ):
            return
        if self.ui_settings.get("remember_window_size"):
            try:
                if self.root.state() == "normal":
                    self.ui_settings["window_width"] = min(3840, max(1000, self.root.winfo_width()))
                    self.ui_settings["window_height"] = min(2160, max(620, self.root.winfo_height()))
                    write_ui_settings(self.ui_settings)
            except (OSError, tk.TclError):
                pass
        if self.restart_job is not None:
            self.root.after_cancel(self.restart_job)
            self.restart_job = None
        if self.worker is not None:
            self.worker.stop()
        if self.mover_worker is not None:
            self.mover_worker.stop()
        self.root.destroy()

    def _check_freshness(self):
        for symbol, values in list(self.levels.items()):
            self._render_row(symbol, float(values['price']), self.quote_times.get(symbol))
        local = datetime.now(NEW_YORK)
        minutes = local.hour * 60 + local.minute
        market_session = local.weekday() < 5 and 240 <= minutes < 1200
        if (self.running and market_session and self.last_market_event_at is not None
                and time.monotonic() - self.last_market_event_at > 180):
            self._append_log("超过 180 秒未收到新行情，正在自动重连。")
            self.stop_monitoring(restart=True)
        if self.running and self.history_loaded_day != datetime.now(NEW_YORK).date():
            self.pending_tws_start = True
            self.history_loaded_day = datetime.now(NEW_YORK).date()
            self.stop_monitoring(restart=True)
        self.root.after(15000, self._check_freshness)


def main() -> None:
    root = tk.Tk()
    SignalMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
