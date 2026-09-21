"""Shared decision gates: timestamps are facts, receipt time is not quote time."""
import math
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def observation_reason(price, timestamp, history_date, now=None, max_age_seconds=180):
    now = now or datetime.now(timezone.utc)
    if not math.isfinite(price) or price <= 0:
        return "价格无效"
    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
        return "行情缺少可信时间戳"
    age = (now - timestamp).total_seconds()
    if age < -30 or age > max_age_seconds:
        return f"行情过期或时间异常（超过 {max_age_seconds} 秒）"
    local = now.astimezone(NEW_YORK)
    if local.weekday() >= 5 or not 240 <= local.hour * 60 + local.minute < 1200:
        return "美股盘前、正常交易及盘后时段外"
    try:
        last_history_day = date.fromisoformat(str(history_date))
    except (TypeError, ValueError):
        return "日线日期无效"
    age_days = (local.date() - last_history_day).days
    if age_days < 1 or age_days > 4:
        return "日线未更新或交易日待核实"
    return None
