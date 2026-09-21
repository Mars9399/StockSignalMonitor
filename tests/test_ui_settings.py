import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import signal_monitor_gui as gui


class UISettingsTests(unittest.TestCase):
    def test_invalid_values_are_bounded_and_bad_booleans_use_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ui_settings.json"
            path.write_text(json.dumps({
                "window_width": 10,
                "window_height": 9999,
                "ui_font_size": 99,
                "table_font_size": "bad",
                "start_maximized": "yes",
            }), encoding="utf-8")
            with patch.object(gui, "UI_SETTINGS_FILE", path):
                settings = gui.read_ui_settings()
            self.assertEqual(settings["window_width"], 1000)
            self.assertEqual(settings["window_height"], 2160)
            self.assertEqual(settings["ui_font_size"], 18)
            self.assertEqual(settings["table_font_size"], gui.DEFAULT_UI_SETTINGS["table_font_size"])
            self.assertFalse(settings["start_maximized"])

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ui_settings.json"
            expected = dict(gui.DEFAULT_UI_SETTINGS, window_width=1600, ui_font_size=12,
                            confirm_exit=True, auto_start_movers=False)
            with patch.object(gui, "UI_SETTINGS_FILE", path):
                gui.write_ui_settings(expected)
                actual = gui.read_ui_settings()
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
