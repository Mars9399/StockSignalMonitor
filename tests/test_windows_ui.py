"""Run actual Tk widgets on the Windows build runner, with isolated local data."""
import sys
import tempfile
import unittest
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
                                    TWS_IMPORT_FILE=Path(folder)/"imported.json"), \
                     patch.object(gui.SignalMonitorApp, "_resolve_missing_names"), \
                     patch.object(gui, "load_state", return_value={}), \
                     patch.object(gui, "read_positions", return_value={}), \
                     patch.object(gui, "read_watchlist", return_value=["MSFT"]), \
                     patch.object(gui.messagebox, "askyesno", return_value=True):
                    app = gui.SignalMonitorApp(root)
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
            finally:
                root.destroy()
