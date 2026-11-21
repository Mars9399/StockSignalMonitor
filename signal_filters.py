"""Optional gates applied after the core 10-day channel signal."""

from __future__ import annotations

from monitor_settings import DEFAULT_MONITOR_SETTINGS


def channel_width_pct(values: dict) -> float:
    buy = float(values.get("buy_point") or 0)
    stop = float(values.get("stop_point") or 0)
    if buy <= 0:
        return 0.0
    return max(0.0, (buy - stop) / buy * 100.0)


def relative_strength_ok(
    symbol_change_pct: float | None,
    benchmark_change_pct: float | None,
) -> bool | None:
    """Return True/False when both legs exist; None when comparison unavailable."""
    if symbol_change_pct is None or benchmark_change_pct is None:
        return None
    return float(symbol_change_pct) >= float(benchmark_change_pct)


def apply_signal_filters(
    values: dict,
    settings: dict | None = None,
    *,
    symbol_change_pct: float | None = None,
    benchmark_change_pct: float | None = None,
) -> dict:
    """Return a shallow-copied values dict with optional demotions / annotations.

    Never invents a BUY/SELL when the core channel did not trigger; only demotes
    or annotates. Settings default to all filters off.
    """
    cfg = dict(DEFAULT_MONITOR_SETTINGS)
    if settings:
        cfg.update(settings)

    result = dict(values)
    notes: list[str] = list(values.get("filter_notes") or [])
    blocked: list[str] = []
    status = str(result.get("status", "WATCH"))

    if not result.get("signal_ready", False):
        result["filter_notes"] = notes
        result["filter_blocked"] = blocked
        return result

    width = channel_width_pct(result)
    result["channel_width_pct"] = width

    if cfg.get("filter_channel_width_enabled"):
        min_w = float(cfg["filter_channel_width_min_pct"])
        max_w = float(cfg["filter_channel_width_max_pct"])
        if width < min_w:
            blocked.append(f"通道过窄 {width:.1f}% < {min_w:.1f}%")
        elif width > max_w:
            blocked.append(f"通道过宽 {width:.1f}% > {max_w:.1f}%")

    if status == "BUY_ALERT" and cfg.get("filter_volume_enabled"):
        ratio = float(result.get("volume_ratio") or 1.0)
        need = float(cfg["filter_volume_min_ratio"])
        if ratio < need:
            blocked.append(f"量比不足 {ratio:.2f} < {need:.2f}")

    if status == "BUY_ALERT" and cfg.get("filter_relative_strength_enabled"):
        rs = relative_strength_ok(symbol_change_pct, benchmark_change_pct)
        if rs is False:
            blocked.append("弱于基准（相对强弱未通过）")
        elif rs is None:
            notes.append("相对强弱暂缺基准数据，未强制过滤")
        else:
            notes.append("相对强弱：强于或持平基准")

    price = float(result.get("price") or 0)
    buy_point = float(result.get("buy_point") or 0)
    extension = max(0.0, (price / buy_point - 1.0) * 100.0) if buy_point > 0 else 0.0
    result["breakout_extension_pct"] = extension

    if status == "BUY_ALERT" and cfg.get("prefer_pullback_entry") and extension > 3.0:
        blocked.append(f"突破已延伸 +{extension:.1f}%，偏好回踩确认")
        result["entry_mode"] = "pullback_wait"
    elif status == "BUY_ALERT":
        result["entry_mode"] = "breakout"

    if blocked and status in {"BUY_ALERT", "SELL_ALERT"}:
        # Demote primary alert to watch; keep raw_status for UI transparency.
        result["raw_status"] = status
        result["status"] = "WATCH"
        result["filter_suppressed"] = True
        notes.extend(blocked)
    else:
        result["raw_status"] = status
        result["filter_suppressed"] = False
        notes.extend(blocked)

    if symbol_change_pct is not None and benchmark_change_pct is not None:
        result["symbol_change_pct"] = float(symbol_change_pct)
        result["benchmark_change_pct"] = float(benchmark_change_pct)
        result["relative_strength_spread"] = float(symbol_change_pct) - float(benchmark_change_pct)

    result["filter_notes"] = notes
    result["filter_blocked"] = blocked
    return result


def feed_profile_label(provider: str, quote_age_seconds: float | None = None) -> str:
    provider = (provider or "").strip()
    if "Alpaca" in provider:
        base = "Alpaca IEX（非全市场 SIP）"
    elif "Massive" in provider or "Polygon" in provider:
        base = "Polygon/Massive（可能延迟）"
    elif "Yahoo" in provider:
        base = "Yahoo（研究级流）"
    elif "IBKR" in provider or "TWS" in provider:
        base = "IBKR/TWS（视订阅与类型）"
    else:
        base = provider or "未知数据源"
    if quote_age_seconds is None:
        return base
    if quote_age_seconds < 0:
        return f"{base} · 时间异常"
    if quote_age_seconds <= 5:
        return f"{base} · 约 {quote_age_seconds:.0f}s"
    if quote_age_seconds <= 180:
        return f"{base} · 行情年龄 {quote_age_seconds:.0f}s"
    return f"{base} · 过期 {quote_age_seconds:.0f}s"
