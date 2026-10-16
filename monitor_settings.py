"""Persisted strategy / filter settings for the read-only monitor."""

from __future__ import annotations

import json
from pathlib import Path

from holding_diagnosis import DEFAULT_DIAGNOSIS_SETTINGS


DEFAULT_MONITOR_SETTINGS = {
    # P0: optional primary-signal filters (all off by default)
    "filter_volume_enabled": False,
    "filter_volume_min_ratio": 1.15,
    "filter_relative_strength_enabled": False,
    "filter_channel_width_enabled": False,
    "filter_channel_width_min_pct": 4.0,
    "filter_channel_width_max_pct": 35.0,
    # Signal modes
    "prefer_pullback_entry": False,  # treat extended breakouts as observe/secondary
    "volatility_adaptive_lookback": False,
    # Protection / take-profit hints
    "atr_stop_multiplier": 2.0,
    "take_profit_atr_multiple": 3.0,
    "enable_take_profit_hint": True,
    # Display
    "score_as_probability_label": False,  # False => 操作评分
    "show_feed_profile": True,
    # Benchmark for relative strength
    "benchmark_symbol": "SPY",
    # Holding diagnosis engine (rule-based, read-only)
    **DEFAULT_DIAGNOSIS_SETTINGS,
}


def read_monitor_settings(path: Path) -> dict:
    settings = dict(DEFAULT_MONITOR_SETTINGS)
    if not path.exists():
        return settings
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings
    if not isinstance(loaded, dict):
        return settings
    for key, default in DEFAULT_MONITOR_SETTINGS.items():
        if key not in loaded:
            continue
        value = loaded[key]
        if isinstance(default, bool):
            settings[key] = bool(value)
        elif isinstance(default, float):
            try:
                settings[key] = float(value)
            except (TypeError, ValueError):
                pass
        elif isinstance(default, str):
            settings[key] = str(value).strip().upper() if key == "benchmark_symbol" else str(value)
    settings["filter_volume_min_ratio"] = min(5.0, max(0.5, float(settings["filter_volume_min_ratio"])))
    settings["filter_channel_width_min_pct"] = min(20.0, max(0.5, float(settings["filter_channel_width_min_pct"])))
    settings["filter_channel_width_max_pct"] = min(80.0, max(5.0, float(settings["filter_channel_width_max_pct"])))
    settings["atr_stop_multiplier"] = min(5.0, max(0.5, float(settings["atr_stop_multiplier"])))
    settings["take_profit_atr_multiple"] = min(10.0, max(1.0, float(settings["take_profit_atr_multiple"])))
    if settings["filter_channel_width_max_pct"] < settings["filter_channel_width_min_pct"]:
        settings["filter_channel_width_max_pct"] = settings["filter_channel_width_min_pct"]
    return settings


def write_monitor_settings(path: Path, settings: dict) -> None:
    merged = read_monitor_settings(path)
    merged.update(settings)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
