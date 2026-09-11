"""Shared decision gates: timestamps are facts, receipt time is not quote time."""
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def observation_reason(price, timestamp, history_date, now=None):
    now = now or datetime.now(timezone.utc)
    if not math.isfinite(price) or price <= 0:
        return "价格无效"
    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
        return "行情缺少可信时间戳"
    age = (now - timestamp).total_seconds()
    if age < -30 or age > 120:
        return "行情过期或时间异常（超过 120 秒）"
    local = now.astimezone(NEW_YORK)
    if local.weekday() >= 5 or not 570 <= local.hour * 60 + local.minute < 960:
        return "正常交易时段外"
    expected = local.date() - timedelta(days=1)
    while expected.weekday() >= 5:
        expected -= timedelta(days=1)
    if history_date != expected.isoformat():
        return "日线未更新或交易日待核实"
    return None
