"""Structured read-only trading suggestions for personal clients."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


DISCLAIMER = (
    "本输出为技术监控与仓位辅助规则结果，不构成投资建议，不保证收益，"
    "也不代表券商指令；请自行判断并在券商端操作。"
)


@dataclass
class Suggestion:
    symbol: str
    side: str  # buy | reduce | hold | observe
    title: str
    triggers: list[str] = field(default_factory=list)
    buy_score: int = 0
    reduce_score: int = 0
    score_label: str = ""
    reduce_label: str = ""
    confidence: str = "low"  # low | medium | high
    risks: list[str] = field(default_factory=list)
    position_hint: str = ""
    alert_tier: str = "silent"  # primary | secondary | silent
    feed_profile: str = ""
    history_date: str = ""
    as_of: str = ""
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict:
        return asdict(self)

    def explain_text(self) -> str:
        lines = [
            f"【建议】{self.symbol} · {self.title}",
            f"方向：{self.side} · 置信度：{self.confidence} · 告警级：{self.alert_tier}",
            f"买入操作评分：{self.buy_score}（{self.score_label}） · 减持评分：{self.reduce_score}（{self.reduce_label}）",
        ]
        if self.triggers:
            lines.append("触发条件：")
            lines.extend(f"  - {item}" for item in self.triggers)
        if self.risks:
            lines.append("风险提示：")
            lines.extend(f"  - {item}" for item in self.risks)
        if self.position_hint:
            lines.append(f"仓位参考：{self.position_hint}")
        if self.feed_profile:
            lines.append(f"行情画像：{self.feed_profile}")
        if self.history_date:
            lines.append(f"通道基准日：{self.history_date}")
        lines.append(self.disclaimer)
        return "\n".join(lines)


def _confidence(
    *,
    observation: str | None,
    suppressed: bool,
    provider: str,
    quote_age: float | None,
    extension: float,
    rs_spread: float | None,
) -> str:
    if observation or suppressed:
        return "low"
    delayed = any(token in (provider or "") for token in ("Yahoo", "Delayed", "延迟", "Massive"))
    stale = quote_age is not None and quote_age > 30
    extended = extension > 3.0
    weak_rs = rs_spread is not None and rs_spread < 0
    if delayed or stale or extended or weak_rs:
        return "medium"
    return "high"


def build_suggestion(
    symbol: str,
    values: dict,
    probabilities: dict,
    plan: dict,
    *,
    observation: str | None = None,
    feed_profile: str = "",
    quote_age_seconds: float | None = None,
    provider: str = "",
) -> Suggestion:
    status = str(values.get("status", "WATCH"))
    raw_status = str(values.get("raw_status", status))
    suppressed = bool(values.get("filter_suppressed"))
    buy_score = int(probabilities.get("buy_probability", 0) or 0)
    reduce_score = int(probabilities.get("reduce_probability", 0) or 0)
    buy_label = str(probabilities.get("buy_label", ""))
    reduce_label = str(probabilities.get("reduce_label", ""))
    action = str(plan.get("action", ""))
    extension = float(values.get("breakout_extension_pct") or 0.0)
    rs_spread = values.get("relative_strength_spread")
    rs_spread_f = float(rs_spread) if isinstance(rs_spread, (int, float)) else None

    triggers: list[str] = []
    risks: list[str] = list(values.get("filter_notes") or [])
    history_date = str(values.get("history_date") or "")

    if values.get("signal_ready"):
        buy_point = float(values.get("buy_point") or 0)
        stop_point = float(values.get("stop_point") or 0)
        price = float(values.get("price") or 0)
        triggers.append(f"10日通道：买入线 ${buy_point:,.2f} / 卖出线 ${stop_point:,.2f}")
        triggers.append(f"现价 ${price:,.2f}")
        if raw_status == "BUY_ALERT":
            triggers.append("现价达到或突破10日最高价")
        if raw_status == "SELL_ALERT":
            triggers.append("现价达到或跌破10日最低价")
        volume_ratio = float(values.get("volume_ratio") or 1.0)
        triggers.append(f"量比 {volume_ratio:.2f} · RSI {float(values.get('rsi14', 50)):.0f}")
        if rs_spread_f is not None:
            triggers.append(f"相对基准差 {rs_spread_f:+.2f}%")

    if observation:
        side = "observe"
        title = f"仅观察：{observation}"
        alert_tier = "silent"
        risks.append(observation)
    elif not values.get("signal_ready"):
        side = "observe"
        title = f"历史不足（{int(values.get('history_days', 0))}日）"
        alert_tier = "silent"
    elif suppressed:
        side = "observe"
        title = "过滤后暂不提示（原触发已降级）"
        alert_tier = "secondary"
    elif status == "BUY_ALERT":
        side = "buy"
        title = "买入提示（通道突破）"
        alert_tier = "primary"
        if extension > 3.0:
            risks.append(f"突破已延伸 +{extension:.1f}%，追高风险升高")
    elif status == "SELL_ALERT" or "卖出提示" in action:
        side = "reduce"
        title = "卖出/减持提示"
        alert_tier = "primary"
    elif reduce_score >= 75:
        side = "reduce"
        title = "建议关注减持（高评分）"
        alert_tier = "secondary"
    elif buy_score >= 75:
        side = "hold"
        title = "买入评分偏高，等待确认"
        alert_tier = "secondary"
    else:
        side = "hold"
        title = action or "持有/等待"
        alert_tier = "silent"

    confidence = _confidence(
        observation=observation,
        suppressed=suppressed,
        provider=provider or feed_profile,
        quote_age=quote_age_seconds,
        extension=extension,
        rs_spread=rs_spread_f,
    )

    return Suggestion(
        symbol=symbol,
        side=side,
        title=title,
        triggers=triggers,
        buy_score=buy_score,
        reduce_score=reduce_score,
        score_label=buy_label,
        reduce_label=reduce_label,
        confidence=confidence,
        risks=risks,
        position_hint=action,
        alert_tier=alert_tier,
        feed_profile=feed_profile,
        history_date=history_date,
        as_of=datetime.now(timezone.utc).isoformat(),
    )
