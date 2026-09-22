"""Run actual Tk widgets on the Windows build runner, with isolated local data."""
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Windows Tk smoke test")
class WindowsUITests(unittest.TestCase):
    def test_sync_filter_watchlist_and_clear(self):
        import tkinter as tk
        import signal_monitor_gui as gui

        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk()
            root.withdraw()
            try:
                with patch.multiple(gui, WATCHLIST_FILE=Path(folder)/"watchlist.json",
                                    POSITIONS_FILE=Path(folder)/"positions.json",
                                    TWS_IMPORT_FILE=Path(folder)/"imported.json",
                                    UI_SETTINGS_FILE=Path(folder)/"ui_settings.json"), \
                     patch.object(gui.SignalMonitorApp, "_resolve_missing_names"), \
                     patch.object(gui, "load_state", return_value={}), \
                     patch.object(gui, "read_positions", return_value={}), \
                     patch.object(gui, "read_watchlist", return_value=["MSFT"]), \
                     patch.object(gui.messagebox, "askyesno", return_value=True):
                    app = gui.SignalMonitorApp(root)
                    style = gui.ttk.Style()
                    selected_font = root.tk.splitlist(
                        style.lookup("TNotebook.Tab", "font", ("selected",))
                    )
                    unselected_font = root.tk.splitlist(
                        style.lookup("TNotebook.Tab", "font", ("!selected",))
                    )
                    self.assertEqual(int(selected_font[1]), app.ui_settings["ui_font_size"] + 2)
                    self.assertIn("bold", selected_font)
                    self.assertEqual(int(unselected_font[1]), app.ui_settings["ui_font_size"])
                    self.assertEqual(str(app.ui_settings_button.cget("text")), "界面设置")
                    app.ui_settings.update(ui_font_size=12, table_font_size=11,
                                           table_row_height=40, log_height=5)
                    app._apply_ui_settings(resize_window=False)
                    self.assertEqual(int(style.lookup("Treeview", "rowheight")), 40)
                    self.assertEqual(int(app.alert_text.cget("height")), 5)
                    self.assertEqual(str(app.mover_refresh_button.cget("text")), "立即刷新")
                    self.assertIn("全市场股票", app.notebook.tab(app.market_directory_card, "text"))
                    self.assertTrue(app.market_directory_tree.bind("<Button-3>"))
                    self.assertTrue(app.tree.bind("<Double-1>"))
                    self.assertIn("buy_probability", app.tree.cget("columns"))
                    self.assertIn("reduce_probability", app.tree.cget("columns"))
                    app.account_summary = {
                        "account": "DU123",
                        "currency": "USD",
                        "NetLiquidation": 123456.78,
                        "AvailableFunds": 45678.9,
                    }
                    app._refresh_account_summary_text()
                    self.assertIn("DU123", app.account_summary_var.get())
                    app.toggle_account_details()
                    self.assertNotIn("DU123", app.account_summary_var.get())
                    app.running = True
                    app.levels["MSFT"] = {
                        "signal_ready": True, "status": "WATCH", "price": 99.0,
                        "buy_point": 100.0, "stop_point": 90.0, "risk_pct": 10.0,
                        "atr14": 2.0, "trend_fast": 97.0, "trend_slow": 95.0,
                        "momentum_5d_pct": 3.0, "momentum_10d_pct": 5.0,
                        "rsi14": 60.0, "volume_ratio": 1.3, "history_days": 40,
                        "history_date": "2026-09-20", "signal_quality": "实时价格通道",
                        "signal_model": "10日高低点",
                    }
                    with patch.object(gui, "observation_reason", return_value=None):
                        app._render_row("MSFT", 99.0, datetime.now(timezone.utc))
                    score_row = app.tree.item("MSFT", "values")
                    self.assertIn("%", score_row[8])
                    self.assertIn("%", score_row[9])
                    app.tree.selection_set("MSFT")
                    app.levels["MSFT"]["price"] = 100.0
                    with patch.object(gui, "observation_reason", return_value=None):
                        app._render_row("MSFT", 100.0, datetime.now(timezone.utc))
                    self.assertIn("PRICE_UP", app.tree.item("MSFT", "tags"))
                    self.assertIn("PRICE_UP", app.watch_tree.item("MSFT", "tags"))
                    self.assertEqual(style.lookup("Overview.Treeview", "foreground", ("selected",)), "#38d982")
                    app.levels["MSFT"]["price"] = 98.0
                    with patch.object(gui, "observation_reason", return_value=None):
                        app._render_row("MSFT", 98.0, datetime.now(timezone.utc))
                    self.assertIn("PRICE_DOWN", app.tree.item("MSFT", "tags"))
                    self.assertEqual(style.lookup("Overview.Treeview", "foreground", ("selected",)), "#ff6678")
                    with patch.object(gui, "observation_reason", return_value=None):
                        app._render_row("MSFT", 98.0, datetime.now(timezone.utc))
                    self.assertIn("PRICE_DOWN", app.tree.item("MSFT", "tags"))
                    self.assertFalse(hasattr(app, "price_flash_jobs"))
                    app.running = False
                    app._apply_tws_positions([dict(symbol="AAPL", quantity=0.5, avg_cost=100,
                                                   account="test", security_type="STK", currency="USD")], "")
                    self.assertEqual(app.positions["AAPL"]["quantity"], 0.5)
                    self.assertIn("AAPL", app.watch_tree.get_children())
                    self.assertEqual(app.watch_tree.item("AAPL", "values")[3], "持仓")
                    app.scope_var.set("positions")
                    app._apply_scope()
                    self.assertEqual(app.tree.get_children(), ("AAPL",))
                    app.scope_var.set("all")
                    app._apply_scope()
                    self.assertEqual(len(app.tree.get_children()), 2)
                    app.clear_positions()
                    self.assertEqual(app.positions, {})
                    self.assertEqual(len(app.watch_tree.get_children()), 2)
                    self.assertEqual(app.watch_tree.item("AAPL", "values")[3], "未持仓")
                    result = gui.MoverResult(
                        side="gainers", rank=1, symbol="NVDA", name="NVIDIA", price=200,
                        change_pct=8.5, volume=1_000_000, buy_point=199, sell_point=180,
                        opportunity="买入机会：突破 +0.5%", tag="BUY", quote_time=datetime.now(timezone.utc),
                    )
                    app._render_movers(app.gainers_tree, [result])
                    self.assertEqual(app.gainers_tree.item("gainers:NVDA", "values")[1], "NVDA")
                    self.assertIn("买入机会", app.gainers_tree.item("gainers:NVDA", "values")[8])
                    changed_result = gui.MoverResult(
                        side="gainers", rank=1, symbol="NVDA", name="NVIDIA", price=201,
                        change_pct=9.0, volume=1_100_000, buy_point=199, sell_point=180,
                        opportunity="买入机会：突破 +1.0%", tag="BUY", quote_time=datetime.now(timezone.utc),
                    )
                    app._render_movers(app.gainers_tree, [changed_result])
                    self.assertIn("PRICE_UP", app.gainers_tree.item("gainers:NVDA", "tags"))
            finally:
                root.destroy()
