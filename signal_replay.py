"""Lightweight alert replay / scoreboard from local signal_alerts.csv (P3)."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ReplaySummary:
    total_alerts: int
    buy_alerts: int
    sell_alerts: int
    symbols: list[str]
    latest: list[dict]
    note: str

    def to_dict(self) -> dict:
        return asdict(self)

    def as_text(self) -> str:
        lines = [
            f"告警回放摘要：共 {self.total_alerts} 条（买 {self.buy_alerts} / 卖 {self.sell_alerts}）",
            f"涉及标的：{', '.join(self.symbols) if self.symbols else '—'}",
            self.note,
        ]
        if self.latest:
            lines.append("最近记录：")
            for row in self.latest[:8]:
                lines.append(
                    f"  {row.get('observed_at_utc', '')} {row.get('symbol', '')} "
                    f"{row.get('signal', '')} @ {row.get('price', '')}"
                )
        return "\n".join(lines)


def replay_alerts(path: Path, limit: int = 50) -> ReplaySummary:
    if not path.exists():
        return ReplaySummary(
            total_alerts=0,
            buy_alerts=0,
            sell_alerts=0,
            symbols=[],
            latest=[],
            note="尚无 signal_alerts.csv；启动监控并触发提示后可回放。本回放只统计历史提示，不做收益回测。",
        )
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(dict(row))
    counts = Counter(str(row.get("signal", "")).upper() for row in rows)
    symbols = sorted({str(row.get("symbol", "")).upper() for row in rows if row.get("symbol")})
    latest = list(reversed(rows[-limit:]))
    return ReplaySummary(
        total_alerts=len(rows),
        buy_alerts=counts.get("BUY_ALERT", 0),
        sell_alerts=counts.get("SELL_ALERT", 0),
        symbols=symbols,
        latest=latest,
        note=(
            "P3 简易回放：统计本地告警频次与最近触发，不等于收益回测或胜率校准。"
            "完整前视回测需另配历史样本。"
        ),
    )


def event_watch_hints(symbols: list[str]) -> list[str]:
    """Best-effort earnings proximity hints via yfinance; failures become soft notes."""
    if not symbols:
        return []
    hints: list[str] = []
    try:
        import yfinance as yf
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        for symbol in symbols[:20]:
            try:
                cal = yf.Ticker(symbol).calendar
                raw = None
                if isinstance(cal, dict):
                    raw = cal.get("Earnings Date") or cal.get("earningsDate")
                elif hasattr(cal, "empty") and not cal.empty:
                    if "Earnings Date" in cal.index:
                        raw = cal.loc["Earnings Date"]
                if raw is None:
                    continue
                dates = raw if isinstance(raw, (list, tuple)) else [raw]
                for item in dates:
                    try:
                        if hasattr(item, "to_pydatetime"):
                            dt = item.to_pydatetime()
                        else:
                            dt = datetime.fromisoformat(str(item)[:10]).replace(tzinfo=timezone.utc)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        delta = (dt - now).days
                        if -1 <= delta <= 7:
                            hints.append(f"{symbol} 约 {delta} 天后/附近有财报窗口，建议提高观察权重。")
                            break
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception as exc:
        hints.append(f"事件观察暂不可用：{exc}")
    if not hints:
        hints.append("近期自选未见近窗财报标记（或数据源未返回）；事件观察为辅助，不改变通道触发。")
    return hints
