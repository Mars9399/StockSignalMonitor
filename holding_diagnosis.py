"""Deterministic, offline holding diagnosis and action-plan engine.

This is a rule-based, read-only analysis aid. It never creates orders, never
calls a network service and no LLM participates in any decision. The Swift
port in apple/Shared/HoldingDiagnosis.swift must stay numerically identical;
both sides are checked against apple/Tests/SharedTests/Fixtures/holding_diagnosis.json.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from sector_map import sector_for, sector_name


DISCLAIMER = "规则化分析辅助，非投资建议；只读监控，不会创建或提交任何订单。"

DEFAULT_DIAGNOSIS_SETTINGS = {
    "diagnosis_portfolio_risk_pct": 6.0,
    "diagnosis_max_average_down_count": 2.0,
    "diagnosis_average_down_fraction": 0.5,
    "diagnosis_average_down_max_loss_pct": 15.0,
    "diagnosis_add_pullback_atr": 0.5,
    "diagnosis_reduce_fraction": 0.5,
    "diagnosis_scale_out_fraction": 0.33,
    "diagnosis_rs_stable_tolerance_pct": 0.5,
    "diagnosis_switch_min_gap_pct": 5.0,
    "diagnosis_event_window_days": 7.0,
    "diagnosis_max_sector_pct": 35.0,
    "diagnosis_breakeven_atr": 1.5,
    "diagnosis_max_leverage_pct": 100.0,
    "diagnosis_deleverage_min_weight_pct": 10.0,
    "diagnosis_watch_days": 10.0,
    "diagnosis_watch_line_breach_days": 2.0,
    "diagnosis_rs_deterioration_pp": 5.0,
    "diagnosis_average_down_tranches": 2.0,
}
SMALL_RISK_RATIO = 0.5
MEDIUM_TERM_LEADER_PP = 10.0
MIN_CHANNEL_STOP_ATR = 0.5

PLAN_NAMES = {
    "stop_exit": "止损离场",
    "hold_watch": "持有观察",
    "average_down": "分批补仓摊低",
    "add_on_strength": "顺势加仓",
    "reduce_risk": "减仓降风险",
    "rally_reduce": "反弹减仓",
    "scale_out": "分批止盈",
    "switch": "换仓同板块更强标的",
}
PROFIT_PLAN_NAMES = {
    "stop_exit": "保护利润离场",
    "hold_watch": "持有并上移保护线",
}
# Tie-break: risk-reducing plans win equal scores.
PLAN_PRIORITY = [
    "stop_exit", "reduce_risk", "rally_reduce", "scale_out",
    "hold_watch", "switch", "average_down", "add_on_strength",
]
LOSS_PLAN_ORDER = ["stop_exit", "hold_watch", "average_down", "reduce_risk", "rally_reduce", "switch"]
PROFIT_PLAN_ORDER = ["hold_watch", "add_on_strength", "scale_out", "reduce_risk", "stop_exit", "switch"]

TREND_LABELS = {"intact": "趋势完好", "weakening": "趋势走弱", "broken": "趋势破位", "unknown": "数据不足"}
SOURCE_LABELS = {
    "idio": "个股走弱",
    "sector": "板块拖累",
    "market": "大盘回撤",
    "cost": "建仓成本偏高（近20日未走弱）",
    "unknown": "数据不足（缺基准）",
}

_EPS = 1e-9


def _floor(value: float) -> float:
    return float(math.floor(value + _EPS)) if math.isfinite(value) else 0.0


def _valid(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


@dataclass
class DiagnosisSettings:
    account_value: float = 100000.0
    risk_pct: float = 1.0
    max_position_pct: float = 10.0
    atr_stop_multiplier: float = 2.0
    take_profit_atr_multiple: float = 3.0
    portfolio_risk_pct: float = 6.0
    max_average_down_count: int = 2
    average_down_fraction: float = 0.5
    average_down_max_loss_pct: float = 15.0
    add_pullback_atr: float = 0.5
    reduce_fraction: float = 0.5
    scale_out_fraction: float = 0.33
    rs_stable_tolerance_pct: float = 0.5
    switch_min_gap_pct: float = 5.0
    event_window_days: int = 7
    max_sector_pct: float = 35.0
    breakeven_atr: float = 1.5
    max_leverage_pct: float = 100.0
    deleverage_min_weight_pct: float = 10.0
    watch_days: int = 10
    watch_line_breach_days: int = 2
    rs_deterioration_pp: float = 5.0
    average_down_tranches: int = 2

    @classmethod
    def from_configs(cls, risk_settings: dict | None = None, monitor_settings: dict | None = None) -> "DiagnosisSettings":
        risk = risk_settings or {}
        monitor = dict(DEFAULT_DIAGNOSIS_SETTINGS)
        monitor.update(monitor_settings or {})

        def num(source: dict, key: str, default: float, lower: float, upper: float) -> float:
            try:
                value = float(source.get(key, default))
            except (TypeError, ValueError):
                value = default
            if not math.isfinite(value):
                value = default
            return min(upper, max(lower, value))

        return cls(
            account_value=num(risk, "account_value", 100000.0, 1.0, 1e12),
            risk_pct=num(risk, "risk_pct", 1.0, 0.1, 10.0),
            max_position_pct=num(risk, "max_position_pct", 10.0, 1.0, 100.0),
            atr_stop_multiplier=num(monitor, "atr_stop_multiplier", 2.0, 0.5, 5.0),
            take_profit_atr_multiple=num(monitor, "take_profit_atr_multiple", 3.0, 1.0, 10.0),
            portfolio_risk_pct=num(monitor, "diagnosis_portfolio_risk_pct", 6.0, 0.5, 50.0),
            max_average_down_count=int(num(monitor, "diagnosis_max_average_down_count", 2.0, 0.0, 10.0)),
            average_down_fraction=num(monitor, "diagnosis_average_down_fraction", 0.5, 0.05, 2.0),
            average_down_max_loss_pct=num(monitor, "diagnosis_average_down_max_loss_pct", 15.0, 1.0, 80.0),
            add_pullback_atr=num(monitor, "diagnosis_add_pullback_atr", 0.5, 0.0, 3.0),
            reduce_fraction=num(monitor, "diagnosis_reduce_fraction", 0.5, 0.05, 0.95),
            scale_out_fraction=num(monitor, "diagnosis_scale_out_fraction", 0.33, 0.05, 0.95),
            rs_stable_tolerance_pct=num(monitor, "diagnosis_rs_stable_tolerance_pct", 0.5, 0.0, 10.0),
            switch_min_gap_pct=num(monitor, "diagnosis_switch_min_gap_pct", 5.0, 0.0, 50.0),
            event_window_days=int(num(monitor, "diagnosis_event_window_days", 7.0, 0.0, 60.0)),
            max_sector_pct=num(monitor, "diagnosis_max_sector_pct", 35.0, 5.0, 100.0),
            breakeven_atr=num(monitor, "diagnosis_breakeven_atr", 1.5, 0.0, 10.0),
            max_leverage_pct=num(monitor, "diagnosis_max_leverage_pct", 100.0, 10.0, 400.0),
            deleverage_min_weight_pct=num(monitor, "diagnosis_deleverage_min_weight_pct", 10.0, 0.0, 100.0),
            watch_days=int(num(monitor, "diagnosis_watch_days", 10.0, 3.0, 30.0)),
            watch_line_breach_days=int(num(monitor, "diagnosis_watch_line_breach_days", 2.0, 1.0, 5.0)),
            rs_deterioration_pp=num(monitor, "diagnosis_rs_deterioration_pp", 5.0, 1.0, 20.0),
            average_down_tranches=int(num(monitor, "diagnosis_average_down_tranches", 2.0, 1.0, 3.0)),
        )

    @property
    def position_budget(self) -> float:
        return self.account_value * self.risk_pct / 100.0

    @property
    def portfolio_budget(self) -> float:
        return self.account_value * self.portfolio_risk_pct / 100.0

    @property
    def max_position_value(self) -> float:
        return self.account_value * self.max_position_pct / 100.0


@dataclass
class HoldingMetrics:
    price: float
    atr14: float
    ma20: float | None = None
    ma50: float | None = None
    ma200: float | None = None
    channel_low_10: float | None = None
    swing_low: float | None = None
    ref_close_5: float | None = None
    ref_close_20: float | None = None
    rsi14: float = 50.0
    history_days: int = 0
    ref_close_60: float | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "HoldingMetrics":
        return cls(
            price=float(data["price"]),
            atr14=float(data.get("atr14") or 0.0),
            ma20=_valid(data.get("ma20")),
            ma50=_valid(data.get("ma50")),
            ma200=_valid(data.get("ma200")),
            channel_low_10=_valid(data.get("channel_low_10")),
            swing_low=_valid(data.get("swing_low")),
            ref_close_5=_valid(data.get("ref_close_5")),
            ref_close_20=_valid(data.get("ref_close_20")),
            rsi14=float(data.get("rsi14", 50.0) or 50.0),
            history_days=int(data.get("history_days") or 0),
            ref_close_60=_valid(data.get("ref_close_60")),
        )

    @classmethod
    def from_values(cls, values: dict) -> "HoldingMetrics | None":
        """Build from a calculate_levels() result; None when the price is unusable."""
        price = _valid(values.get("price"))
        if price is None:
            return None
        return cls.from_dict(dict(values, price=price))

    def ret(self, reference: float | None) -> float | None:
        if reference is None or reference <= 0:
            return None
        return (self.price / reference - 1.0) * 100.0

    @property
    def ret5(self) -> float | None:
        return self.ret(self.ref_close_5)

    @property
    def ret20(self) -> float | None:
        return self.ret(self.ref_close_20)

    @property
    def ret60(self) -> float | None:
        return self.ret(self.ref_close_60)


def holding_metric_fields(highs: list[float], lows: list[float], closes: list[float]) -> dict:
    """Daily-bar derived fields (completed bars, oldest first) used by the engine."""
    count = len(closes)

    def mean_tail(values: list[float], period: int) -> float | None:
        if count < period:
            return None
        window = values[count - period:]
        return sum(window) / float(period)

    swing_low = None
    if count >= 30:
        swing_low = min(lows[max(0, count - 60):count - 10])
    return {
        "ma20": mean_tail(closes, 20),
        "ma50": mean_tail(closes, 50),
        "ma200": mean_tail(closes, 200),
        "channel_low_10": min(lows[count - min(10, count):]) if count else None,
        "swing_low": swing_low,
        "ref_close_5": closes[count - 5] if count >= 5 else None,
        "ref_close_20": closes[count - 20] if count >= 20 else None,
        "ref_close_60": closes[count - 60] if count >= 60 else None,
    }


@dataclass
class DiagnosisContext:
    market: HoldingMetrics | None = None
    sector: HoldingMetrics | None = None
    peers: dict[str, HoldingMetrics] = field(default_factory=dict)
    earnings_days: int | None = None
    # Gross long market value / account net liquidation, in percent.
    leverage_pct: float | None = None


@dataclass
class ActionPlan:
    id: str
    name: str
    allowed: bool
    blocked_reason: str = ""
    action: str = "hold"  # sell | buy | hold | switch
    trigger: str = ""
    price: float | None = None
    quantity_change: float = 0.0
    quantity_after: float = 0.0
    avg_cost_after: float | None = None
    stop_after: float | None = None
    worst_loss: float = 0.0
    realized_pnl: float = 0.0
    budget_pct: float = 0.0
    portfolio_budget_pct: float = 0.0
    score: int = 0
    target_symbol: str = ""
    # Executable legs: {side, quantity, price, label} — filled even when allowed=False so math is visible.
    steps: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HoldingDiagnosis:
    symbol: str
    mode: str  # loss | profit
    data_ready: bool
    price: float
    avg_cost: float
    quantity: float
    pnl_pct: float
    pnl_amount: float
    market_value: float
    weight_pct: float
    trend_state: str
    trend_label: str
    trend_flags: list[str]
    loss_source: str
    loss_source_label: str
    attribution: dict
    rs5: float | None
    rs20: float | None
    rs60: float | None
    rs_stable: bool | None
    leverage_pct: float | None
    over_leveraged: bool
    sector_symbol: str | None
    sector_label: str
    atr: float
    atr_pct: float
    volatility_label: str
    earnings_days: int | None
    event_near: bool
    stop: float
    stop_basis: str
    stop_hit: bool
    hold_risk: float
    position_budget: float
    budget_ratio: float
    overweight: bool
    plans: list[ActionPlan]
    recommended: str
    confidence: str
    switch_conditions: list[dict]
    summary: str
    watch_line: float | None = None
    hard_stop: float | None = None
    watch_days: int = 0
    # Best non-sell plan among hold_watch / average_down / rally_reduce (loss mode).
    non_sell_plan: str = ""
    non_sell_summary: str = ""
    disclaimer: str = DISCLAIMER

    def plan(self, plan_id: str) -> ActionPlan | None:
        return next((item for item in self.plans if item.id == plan_id), None)

    @property
    def recommended_plan(self) -> ActionPlan:
        return self.plan(self.recommended)  # type: ignore[return-value]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["plans"] = [plan.to_dict() for plan in self.plans]
        return data

    def explain_text(self) -> str:
        rec = self.recommended_plan
        lines = [
            f"【持仓诊断】{self.symbol} · 推荐：{rec.name}（置信度 {self.confidence}，评分 {rec.score}）",
            f"现价 ${self.price:,.2f} · 成本 ${self.avg_cost:,.2f} · {self.quantity:g} 股 · "
            f"浮动盈亏 {self.pnl_pct:+.2f}%（${self.pnl_amount:,.2f}）· 占账户 {self.weight_pct:.1f}%",
            f"趋势：{self.trend_label}" + (f"（{'；'.join(self.trend_flags)}）" if self.trend_flags else ""),
            f"亏损来源：{self.loss_source_label} · 20日分解 {_attribution_text(self.attribution)}",
            f"相对强弱：5日 {_pp(self.rs5)} · 20日 {_pp(self.rs20)} · 60日 {_pp(self.rs60)} · 板块 {self.sector_label}",
            f"波动：ATR ${self.atr:,.2f}（{self.atr_pct:.1f}%，{self.volatility_label}）"
            + (f" · 财报约 {self.earnings_days} 天后" if self.earnings_days is not None else ""),
            f"硬止损 ${self.stop:,.2f}（{self.stop_basis}）· 持有最坏亏损 ${self.hold_risk:,.2f}"
            f" = 单票预算 {self.budget_ratio * 100:.0f}%",
        ]
        if self.watch_line is not None:
            lines.append(
                f"观察线 ${self.watch_line:,.2f} · 观察 {self.watch_days} 个交易日"
                + (f" · 若不卖出优先：{self.non_sell_summary}" if self.non_sell_summary else "")
            )
        if self.leverage_pct is not None:
            lines.append(f"账户杠杆：{self.leverage_pct:.0f}%" + ("（超上限，优先降杠杆）" if self.over_leveraged else ""))
        lines.append("方案对比：")
        for plan in self.plans:
            if plan.allowed:
                lines.append(
                    f"  - {plan.name}｜评分 {plan.score}｜{plan.trigger}｜最坏亏损 ${plan.worst_loss:,.2f}"
                    f"（预算 {plan.budget_pct:.0f}%）"
                )
            else:
                lines.append(f"  - {plan.name}｜不可用：{plan.blocked_reason}")
            for step in plan.steps:
                side = step.get("side", "")
                qty = step.get("quantity")
                px = step.get("price")
                label = step.get("label", "")
                if px is None:
                    continue
                lines.append(
                    f"      · {side} {qty:g} @ ${float(px):,.2f}"
                    + (f"（{label}）" if label else "")
                )
            if plan.id == "average_down" and plan.avg_cost_after is not None:
                lines.append(
                    f"      · 补后股数 {plan.quantity_after:g} · 新成本 ${plan.avg_cost_after:,.2f}"
                    f" · 到保护线最坏 ${plan.worst_loss:,.2f}"
                )
        if self.switch_conditions:
            lines.append("切换条件：")
            lines.extend(f"  - {item['condition']} → {item['target_name']}" for item in self.switch_conditions)
        lines.append(self.disclaimer)
        return "\n".join(lines)


def _pp(value: float | None) -> str:
    return "—" if value is None else f"{value:+.2f}pp"


def _attribution_text(attribution: dict) -> str:
    if attribution.get("stock") is None:
        return "—"
    return (
        f"个股 {attribution['stock']:+.2f}% = 大盘 {attribution['market']:+.2f} + 板块 {attribution['sector']:+.2f}"
        f" + 特质 {attribution['idio']:+.2f}"
    )


def trend_state(metrics: HoldingMetrics) -> tuple[str, list[str]]:
    price = metrics.price
    if metrics.history_days < 20 or metrics.ma20 is None:
        return "unknown", ["历史日线不足 20 根"]
    mid = metrics.ma50 if metrics.ma50 is not None else metrics.ma20
    below20 = price < metrics.ma20
    below_mid = price < mid
    # Without MA200 (young listings) a mid-MA break alone is only "weakening".
    below_long = metrics.ma200 is not None and price < metrics.ma200
    broke_channel = metrics.channel_low_10 is not None and price <= metrics.channel_low_10
    broke_swing = metrics.swing_low is not None and price < metrics.swing_low
    flags: list[str] = []
    flags.append(f"{'低于' if below20 else '站上'}MA20 ${metrics.ma20:,.2f}")
    if metrics.ma50 is not None:
        flags.append(f"{'低于' if price < metrics.ma50 else '站上'}MA50 ${metrics.ma50:,.2f}")
    if metrics.ma200 is not None:
        flags.append(f"{'低于' if price < metrics.ma200 else '站上'}MA200 ${metrics.ma200:,.2f}")
    if broke_channel:
        flags.append(f"触及/跌破10日通道下沿 ${metrics.channel_low_10:,.2f}")
    if broke_swing:
        flags.append(f"跌破前低 ${metrics.swing_low:,.2f}")
    if broke_swing or (below_mid and below_long) or (broke_channel and below_mid):
        return "broken", flags
    if below20 or below_mid or broke_channel:
        return "weakening", flags
    return "intact", flags


def _attribution(metrics: HoldingMetrics, context: DiagnosisContext) -> tuple[str, dict]:
    stock20 = metrics.ret20
    market20 = context.market.ret20 if context.market else None
    sector20 = context.sector.ret20 if context.sector else None
    empty = {"stock": stock20, "market": None, "sector": None, "idio": None}
    if stock20 is None or market20 is None:
        return "unknown", empty
    sector_component = sector20 - market20 if sector20 is not None else 0.0
    idio_component = stock20 - (sector20 if sector20 is not None else market20)
    attribution = {"stock": stock20, "market": market20, "sector": sector_component, "idio": idio_component}
    if stock20 >= 0:
        return "cost", attribution
    source, lowest = "idio", idio_component
    for name, value in (("sector", sector_component), ("market", market20)):
        if value < lowest:
            source, lowest = name, value
    return source, attribution


def _relative_strength(metrics: HoldingMetrics, context: DiagnosisContext) -> tuple[float | None, float | None, float | None]:
    def reference(attr: str) -> float | None:
        if context.sector is not None:
            value = getattr(context.sector, attr)
            if value is not None:
                return value
        return getattr(context.market, attr) if context.market is not None else None

    def spread(attr: str) -> float | None:
        stock, ref = getattr(metrics, attr), reference(attr)
        return stock - ref if stock is not None and ref is not None else None

    return spread("ret5"), spread("ret20"), spread("ret60")


def _clamp_score(value: float) -> int:
    return int(max(0, min(100, value)))


def diagnose_holding(
    symbol: str,
    holding: dict,
    metrics: HoldingMetrics,
    context: DiagnosisContext | None = None,
    settings: DiagnosisSettings | None = None,
) -> HoldingDiagnosis | None:
    """Diagnose one long position. Returns None for empty positions."""
    context = context or DiagnosisContext()
    settings = settings or DiagnosisSettings()
    symbol = symbol.strip().upper()
    quantity = float(holding.get("quantity") or 0.0)
    cost = float(holding.get("avg_cost") or 0.0)
    price = metrics.price
    if quantity <= 0 or cost <= 0 or not price > 0:
        return None
    adds = int(holding.get("average_down_count") or 0)
    initial_stop = _valid(holding.get("initial_stop"))

    pnl_pct = (price / cost - 1.0) * 100.0
    pnl_amount = (price - cost) * quantity
    mode = "loss" if pnl_pct < 0 else "profit"
    atr = metrics.atr14 if metrics.atr14 > 0 else price * 0.01
    atr_pct = atr / price * 100.0
    volatility = "低" if atr_pct < 2.0 else "中" if atr_pct < 4.0 else "高"
    high_vol = atr_pct >= 4.0

    trend, flags = trend_state(metrics)
    data_ready = trend != "unknown"
    source, attribution = _attribution(metrics, context)
    rs5, rs20, rs60 = _relative_strength(metrics, context)
    tolerance = settings.rs_stable_tolerance_pct
    rs_stable = None if rs5 is None else rs5 >= -tolerance
    earnings_days = context.earnings_days
    event_near = earnings_days is not None and 0 <= earnings_days <= settings.event_window_days
    leverage_pct = context.leverage_pct
    over_leveraged = leverage_pct is not None and leverage_pct > settings.max_leverage_pct
    leverage_reason = (f"账户杠杆 {leverage_pct:.0f}% > {settings.max_leverage_pct:g}%，先降杠杆，禁止补仓/加仓/建仓"
                       if over_leveraged else "")

    k = settings.atr_stop_multiplier
    stop_hit = initial_stop is not None and price <= initial_stop
    atr_stop = price - k * atr
    channel = metrics.channel_low_10
    candidates: list[tuple[float, str]] = []
    if mode == "loss":
        # A saved stop is the hard line; a channel low hugging the price is only a watch line.
        if initial_stop is not None and initial_stop < price:
            candidates.append((initial_stop, "已保存保护线"))
        elif channel is not None and channel < price - MIN_CHANNEL_STOP_ATR * atr:
            candidates.append((channel, "10日通道下沿"))
    else:
        if initial_stop is not None and initial_stop < price:
            candidates.append((initial_stop, "已保存保护线"))
        if channel is not None and channel < price:
            candidates.append((channel, "10日通道下沿"))
        if atr_stop > 0:
            candidates.append((atr_stop, f"现价−{k:g}×ATR 跟踪"))
        if price - cost >= settings.breakeven_atr * atr and cost < price:
            candidates.append((cost, "成本保本线"))
    if candidates:
        stop, stop_basis = candidates[0]
        for value, basis in candidates[1:]:
            if value > stop:
                stop, stop_basis = value, basis
    elif atr_stop > 0:
        stop, stop_basis = atr_stop, f"现价−{k:g}×ATR"
    else:
        stop, stop_basis = price * 0.9, "现价−10%"

    budget = settings.position_budget
    portfolio_budget = settings.portfolio_budget
    max_value = settings.max_position_value
    hold_risk = (price - stop) * quantity
    budget_ratio = hold_risk / budget
    over_budget = budget_ratio > 1.0
    market_value = quantity * price
    weight_pct = market_value / settings.account_value * 100.0
    overweight = weight_pct > settings.max_position_pct
    deep = pnl_pct <= -settings.average_down_max_loss_pct
    intact, weakening, broken = trend == "intact", trend == "weakening", trend == "broken"
    names = dict(PLAN_NAMES)
    if mode == "profit":
        names.update(PROFIT_PLAN_NAMES)

    def finish(plan: ActionPlan) -> ActionPlan:
        plan.budget_pct = plan.worst_loss / budget * 100.0
        plan.portfolio_budget_pct = plan.worst_loss / portfolio_budget * 100.0
        return plan

    def blocked(plan_id: str, reason: str) -> ActionPlan:
        return ActionPlan(id=plan_id, name=names[plan_id], allowed=False, blocked_reason=reason)

    # Watch line (soft) vs hard stop — used by loss-mode hold / average-down playbooks.
    mid_ma = metrics.ma50 if metrics.ma50 is not None else metrics.ma20
    watch_line: float | None = None
    if mode == "loss" and channel is not None and stop < channel < price:
        watch_line = channel
    elif mode == "loss" and mid_ma is not None and stop < mid_ma < price:
        watch_line = mid_ma
    watch_days = settings.watch_days if mode == "loss" else 0

    plans: dict[str, ActionPlan] = {}
    plans["stop_exit"] = finish(ActionPlan(
        id="stop_exit", name=names["stop_exit"], allowed=True, action="sell",
        trigger=f"现价附近卖出全部 {quantity:g} 股；或收盘跌破硬止损 ${stop:,.2f}",
        price=price, quantity_change=-quantity, quantity_after=0.0,
        worst_loss=0.0, realized_pnl=(price - cost) * quantity,
        steps=[{"side": "SELL", "quantity": quantity, "price": price, "label": "现价离场"}],
    ))

    hold_steps: list[dict] = []
    if mode == "loss":
        half = _floor(quantity / 2.0) if quantity >= 2 else 0.0
        if watch_line is not None and half >= 1:
            hold_steps.append({
                "side": "SELL", "quantity": half, "price": watch_line,
                "label": f"连续{settings.watch_line_breach_days}日收盘低于观察线则减半",
            })
            hold_steps.append({
                "side": "SELL", "quantity": quantity - half, "price": stop, "label": "硬止损",
            })
        else:
            hold_steps.append({
                "side": "SELL", "quantity": quantity, "price": stop, "label": "硬止损",
            })
        hold_trigger = (
            (f"观察线 ${watch_line:,.2f}" + ("（10日通道下沿）" if channel == watch_line else "（中期均线）")
             + f"，硬止损 ${stop:,.2f}；观察 {watch_days} 个交易日；"
             if watch_line is not None else f"硬止损 ${stop:,.2f}；观察 {watch_days} 个交易日；")
            + (f"连续 {settings.watch_line_breach_days} 日收盘低于观察线减半，" if watch_line is not None and half >= 1 else "")
            + f"触及硬止损或近5日相对强弱再走弱 {settings.rs_deterioration_pp:g}pp 全部止损"
        )
    else:
        hold_trigger = f"保护线上移至 ${stop:,.2f}，收盘跌破则离场"
        hold_steps = [{"side": "SELL", "quantity": quantity, "price": stop, "label": "上移后保护线"}]

    plans["hold_watch"] = finish(ActionPlan(
        id="hold_watch", name=names["hold_watch"], allowed=True, action="hold",
        trigger=hold_trigger,
        price=stop if mode == "profit" else (watch_line or stop),
        quantity_after=quantity, avg_cost_after=cost, stop_after=stop,
        worst_loss=hold_risk, steps=hold_steps,
    ))

    def size_add(entry: float, *, open_qty: float, open_risk: float, cap_fraction: float) -> float:
        if entry <= stop:
            return 0.0
        room = budget - open_risk
        by_risk = _floor(room / (entry - stop)) if room > 0 else 0.0
        headroom = max_value - open_qty * price
        by_value = _floor(headroom / entry) if headroom > 0 else 0.0
        return _floor(min(quantity * cap_fraction, by_risk, by_value))

    if mode == "loss":
        # Build tranche prices even when blocked so the user can still read the math.
        tranche_levels: list[tuple[float, str]] = []
        pullback = price - settings.add_pullback_atr * atr
        first = None
        first_label = ""
        if mid_ma is not None and stop < mid_ma < price:
            first, first_label = mid_ma, ("MA50" if metrics.ma50 is not None else "MA20")
        elif pullback > stop:
            first, first_label = pullback, f"现价−{settings.add_pullback_atr:g}×ATR"
        if first is not None:
            tranche_levels.append((first, first_label))
            if settings.average_down_tranches >= 2:
                second = first - atr
                if second > stop:
                    tranche_levels.append((second, f"{first_label}−1×ATR"))

        add_reasons: list[str] = []
        if over_leveraged:
            add_reasons.append(leverage_reason)
        if not data_ready:
            add_reasons.append("历史不足，无法确认趋势")
        elif broken:
            add_reasons.append("趋势已破位，禁止摊低")
        if rs_stable is None:
            add_reasons.append("缺少基准/板块数据，无法确认相对强弱")
        elif not rs_stable:
            add_reasons.append(f"近5日相对强弱 {rs5:+.2f}pp 未企稳")
        if adds >= settings.max_average_down_count:
            add_reasons.append(f"已补仓 {adds} 次，达到上限 {settings.max_average_down_count}")
        if deep:
            add_reasons.append(f"浮亏 {pnl_pct:.1f}% 超过 {settings.average_down_max_loss_pct:g}%，不再摊低")
        if event_near:
            add_reasons.append(f"约 {earnings_days} 天后财报，事件前不补仓")
        if not tranche_levels:
            add_reasons.append("无可用回踩价位（均线/ATR 回踩不高于保护线）")

        # Size as paper math so blocked plans still show price/qty/new cost.
        remaining_batches = max(1, settings.max_average_down_count - adds)
        n_levels = max(1, min(len(tranche_levels) or 1, remaining_batches, settings.average_down_tranches))
        tranche_cap = settings.average_down_fraction / n_levels
        steps: list[dict] = []
        running_qty = quantity
        running_cost_value = cost * quantity
        running_risk = hold_risk
        for index, (level, label) in enumerate(tranche_levels[:n_levels]):
            qty = size_add(level, open_qty=running_qty, open_risk=running_risk, cap_fraction=tranche_cap)
            if qty < 1:
                # Fall back to a 1-share illustration when budget is tight but levels exist.
                qty = 1.0 if level > stop and (max_value - running_qty * price) >= level else 0.0
            if qty < 1:
                continue
            steps.append({
                "side": "BUY", "quantity": qty, "price": level,
                "label": f"限价第{len(steps) + 1}批·{label}",
            })
            running_risk += (level - stop) * qty
            running_cost_value += level * qty
            running_qty += qty

        if tranche_levels and not steps and "风险预算或单股上限剩余不足" not in add_reasons:
            add_reasons.append("风险预算或单股上限剩余不足")
        reason = "；".join(add_reasons)
        add_qty = sum(step["quantity"] for step in steps)
        add_price = steps[0]["price"] if steps else (tranche_levels[0][0] if tranche_levels else None)
        new_qty = running_qty if steps else quantity
        new_avg = (running_cost_value / new_qty) if steps else cost
        worst_after = running_risk if steps else hold_risk
        price_text = "/".join(f"${level:,.2f}" for level, _ in tranche_levels[:n_levels]) if tranche_levels else "—"
        trigger = (
            f"仅在价格回踩 {price_text} 且收盘不破 ${stop:,.2f}、近5日相对强弱不再恶化时执行"
            + (f"（计划 {len(steps)} 批，累计第 {adds + 1}/{settings.max_average_down_count} 轮）" if steps else "")
        )
        plans["average_down"] = finish(ActionPlan(
            id="average_down", name=names["average_down"], allowed=not bool(reason) and bool(steps),
            blocked_reason=reason, action="buy", trigger=trigger,
            price=add_price, quantity_change=add_qty, quantity_after=new_qty,
            avg_cost_after=new_avg, stop_after=stop, worst_loss=worst_after, steps=steps,
        ))
    else:
        reason = ""
        if over_leveraged:
            reason = leverage_reason
        elif not data_ready:
            reason = "历史不足，无法确认趋势"
        elif not intact:
            reason = f"{TREND_LABELS[trend]}，不顺势加仓"
        elif rs20 is None:
            reason = "缺少基准/板块数据，无法确认相对强弱"
        elif rs20 <= 0:
            reason = f"20日相对强弱 {rs20:+.2f}pp 未转正"
        elif metrics.rsi14 >= 70:
            reason = f"RSI {metrics.rsi14:.0f} 超买"
        elif metrics.ma20 is not None and price > metrics.ma20 + 2.0 * atr:
            reason = "偏离 MA20 超过 2×ATR，追高风险"
        elif event_near:
            reason = f"约 {earnings_days} 天后财报，事件前不加仓"
        add_qty = 0.0 if reason else size_add(
            price, open_qty=quantity, open_risk=hold_risk, cap_fraction=settings.average_down_fraction
        )
        if not reason and add_qty < 1:
            reason = "风险预算或单股上限剩余不足"
        if reason:
            plans["add_on_strength"] = blocked("add_on_strength", reason)
        else:
            new_qty = quantity + add_qty
            plans["add_on_strength"] = finish(ActionPlan(
                id="add_on_strength", name=names["add_on_strength"], allowed=True, action="buy",
                trigger=f"现价附近加 {add_qty:g} 股，统一保护线 ${stop:,.2f}",
                price=price, quantity_change=add_qty, quantity_after=new_qty,
                avg_cost_after=(cost * quantity + price * add_qty) / new_qty, stop_after=stop,
                worst_loss=hold_risk + (price - stop) * add_qty,
                steps=[{"side": "BUY", "quantity": add_qty, "price": price, "label": "顺势加仓"}],
            ))

    if quantity < 2:
        plans["reduce_risk"] = blocked("reduce_risk", "持股不足 2 股，无法分批")
    else:
        keep = min(
            _floor(quantity * (1.0 - settings.reduce_fraction)),
            _floor(budget / (price - stop)),
            _floor(max_value / price),
        )
        if keep <= 0:
            plans["reduce_risk"] = blocked("reduce_risk", "需全部卖出才能回到预算/上限内，等同离场")
        else:
            sell = quantity - keep
            plans["reduce_risk"] = finish(ActionPlan(
                id="reduce_risk", name=names["reduce_risk"], allowed=True, action="sell",
                trigger=f"现价附近卖出 {sell:g} 股，保留 {keep:g} 股，保护线 ${stop:,.2f}",
                price=price, quantity_change=-sell, quantity_after=keep, avg_cost_after=cost,
                stop_after=stop, worst_loss=(price - stop) * keep, realized_pnl=(price - cost) * sell,
            ))

    if mode == "loss":
        if quantity < 2:
            plans["rally_reduce"] = blocked("rally_reduce", "持股不足 2 股，无法分批")
        else:
            ma20 = metrics.ma20
            if ma20 is not None and price < ma20 <= price + 2.0 * atr:
                rebound, rebound_basis = ma20, "MA20"
            else:
                rebound, rebound_basis = price + atr, "现价+1×ATR"
            keep = _floor(quantity * (1.0 - settings.reduce_fraction))
            sell = quantity - keep
            plans["rally_reduce"] = finish(ActionPlan(
                id="rally_reduce", name=names["rally_reduce"], allowed=True, action="sell",
                trigger=(f"反弹至 ${rebound:,.2f}（{rebound_basis}）附近卖出 {sell:g} 股；"
                         f"未反弹先跌破 ${stop:,.2f} 则止损（仍属不主动清仓路径）"),
                price=rebound, quantity_change=-sell, quantity_after=keep, avg_cost_after=cost,
                stop_after=stop, worst_loss=hold_risk, realized_pnl=(rebound - cost) * sell,
                steps=[
                    {"side": "SELL", "quantity": sell, "price": rebound, "label": f"反弹·{rebound_basis}"},
                    {"side": "SELL", "quantity": keep, "price": stop, "label": "余仓硬止损"},
                ],
            ))
    else:
        take_profit = cost + settings.take_profit_atr_multiple * atr
        reached = price >= take_profit
        if quantity < 2:
            plans["scale_out"] = blocked("scale_out", "持股不足 2 股，无法分批")
        else:
            keep = _floor(quantity * (1.0 - settings.scale_out_fraction))
            sell = quantity - keep
            level = price if reached else take_profit
            plans["scale_out"] = finish(ActionPlan(
                id="scale_out", name=names["scale_out"], allowed=True, action="sell",
                trigger=(f"已达止盈参考 ${take_profit:,.2f}，现价附近卖出 {sell:g} 股" if reached
                         else f"价格达到 ${take_profit:,.2f}（成本+{settings.take_profit_atr_multiple:g}×ATR）时卖出 {sell:g} 股"),
                price=level, quantity_change=-sell, quantity_after=keep, avg_cost_after=cost,
                stop_after=stop, worst_loss=(price - stop) * keep if reached else hold_risk,
                realized_pnl=(level - cost) * sell,
            ))

    sector_symbol = sector_for(symbol)
    stock20 = metrics.ret20
    best: tuple[str, HoldingMetrics, float] | None = None
    if sector_symbol is not None and stock20 is not None:
        for peer_symbol in sorted(context.peers):
            peer = context.peers[peer_symbol]
            if peer_symbol == symbol or sector_for(peer_symbol) != sector_symbol or peer_symbol == sector_symbol:
                continue
            peer20 = peer.ret20
            if peer20 is None or trend_state(peer)[0] != "intact":
                continue
            gap = peer20 - stock20
            if gap >= settings.switch_min_gap_pct and (best is None or gap > best[2]):
                best = (peer_symbol, peer, gap)
    switch_gap = 0.0
    if over_leveraged:
        plans["switch"] = blocked("switch", leverage_reason)
    elif sector_symbol is None:
        plans["switch"] = blocked("switch", "未识别所属板块")
    elif best is None:
        plans["switch"] = blocked("switch", "监控列表中无同板块、趋势完好且明显更强的标的")
    else:
        peer_symbol, peer, switch_gap = best
        peer_atr = peer.atr14 if peer.atr14 > 0 else peer.price * 0.01
        risk_per_share = k * peer_atr
        buy = min(_floor(quantity * price / peer.price), _floor(budget / risk_per_share))
        if buy < 1:
            plans["switch"] = blocked("switch", f"{peer_symbol} 单价过高或风险预算不足")
        else:
            plans["switch"] = finish(ActionPlan(
                id="switch", name=names["switch"], allowed=True, action="switch",
                trigger=(f"卖出 {quantity:g} 股 {symbol}，换入约 {buy:g} 股 {peer_symbol}"
                         f"（同板块近20日强 {switch_gap:+.1f}pp）"),
                price=peer.price, quantity_change=-quantity, quantity_after=buy,
                avg_cost_after=peer.price, stop_after=peer.price - risk_per_share,
                worst_loss=buy * risk_per_share, realized_pnl=(price - cost) * quantity,
                target_symbol=peer_symbol,
            ))

    if not data_ready:
        for plan_id in ("reduce_risk", "rally_reduce", "scale_out", "switch"):
            if plan_id in plans and plans[plan_id].allowed:
                plans[plan_id] = blocked(plan_id, "历史不足，仅给出持有/离场")

    not_intact = weakening or broken
    deleverage = over_leveraged and weight_pct >= settings.deleverage_min_weight_pct
    small_risk = budget_ratio <= SMALL_RISK_RATIO and not broken
    leader = rs60 is not None and rs60 >= MEDIUM_TERM_LEADER_PP and not broken
    scores: dict[str, float] = {}
    if mode == "loss":
        scores["stop_exit"] = (25 + 40 * broken + 10 * weakening + 15 * (source == "idio" and not_intact)
                               + 15 * deep + 20 * stop_hit + 10 * over_budget
                               + 5 * (event_near and not_intact) - 20 * intact
                               - 10 * small_risk - 10 * leader)
        scores["reduce_risk"] = (30 + 25 * over_budget + 15 * overweight + 15 * weakening + 10 * broken
                                 + 10 * event_near + 5 * high_vol + 20 * deleverage
                                 - 10 * (intact and not over_budget and not overweight)
                                 - 10 * (small_risk and not overweight))
        scores["rally_reduce"] = (25 + 20 * weakening + 10 * (broken and not deep)
                                  + 10 * (source in ("sector", "market")) - 10 * intact - 15 * stop_hit
                                  - 10 * small_risk)
        scores["hold_watch"] = (40 + 20 * intact + 10 * (source == "market") + 5 * (source == "cost")
                                + 5 * (rs_stable is True) - 30 * broken - 10 * weakening - 20 * over_budget
                                - 10 * overweight - 10 * event_near - 25 * stop_hit
                                + 10 * small_risk + 5 * leader - 10 * deleverage)
        scores["average_down"] = (35 + 15 * intact + 10 * (source == "market") + 5 * (source == "sector")
                                  - 10 * (pnl_pct <= -8.0) - 5 * adds - 10 * high_vol)
        scores["switch"] = 30 + 20 * (source == "idio" and not_intact) + 10 * (switch_gap >= 10.0) - 15 * intact
    else:
        take_profit = cost + settings.take_profit_atr_multiple * atr
        scores["hold_watch"] = (50 + 15 * intact - 25 * broken - 10 * weakening - 10 * overweight
                                - 10 * over_budget - 10 * deleverage)
        scores["add_on_strength"] = (30 + 15 * intact + 5 * (rs20 is not None and rs20 >= 3.0)
                                     - 10 * (pnl_pct >= 20.0))
        scores["scale_out"] = (25 + 25 * (price >= take_profit) + 15 * (metrics.rsi14 >= 70) + 10 * weakening
                               + 10 * overweight + 5 * event_near)
        scores["reduce_risk"] = (20 + 25 * overweight + 20 * over_budget + 10 * event_near + 5 * high_vol
                                 + 20 * deleverage)
        scores["stop_exit"] = 10 + 40 * broken + 15 * stop_hit + 10 * (weakening and price - cost < atr)
        scores["switch"] = 20 + 10 * (source == "idio" and not_intact)

    order = LOSS_PLAN_ORDER if mode == "loss" else PROFIT_PLAN_ORDER
    ordered = [plans[plan_id] for plan_id in order]
    for plan in ordered:
        plan.score = _clamp_score(scores[plan.id]) if plan.allowed else 0
    ranked = sorted(
        (plan for plan in ordered if plan.allowed),
        key=lambda item: (-item.score, PLAN_PRIORITY.index(item.id)),
    )
    recommended = ranked[0]
    margin = recommended.score - ranked[1].score if len(ranked) > 1 else 100
    confidence = "高" if margin >= 15 else "中" if margin >= 7 else "低"

    conditions: list[dict] = []

    def condition(target: str, text: str) -> None:
        conditions.append({"target": target, "target_name": names[target], "condition": text})

    rec = recommended.id
    if rec != "stop_exit":
        condition("stop_exit", f"收盘跌破保护线 ${stop:,.2f}")
    if mode == "loss":
        if rec in ("stop_exit", "reduce_risk", "rally_reduce", "switch") and metrics.ma20 is not None:
            condition("hold_watch", f"重新站上 MA20 ${metrics.ma20:,.2f} 且近5日相对强弱 ≥ -{tolerance:g}pp")
        mid = metrics.ma50 if metrics.ma50 is not None else metrics.ma20
        avg_plan = plans["average_down"]
        if rec != "average_down" and mid is not None and adds < settings.max_average_down_count and not deep:
            label = "MA50" if metrics.ma50 is not None else "MA20"
            pull = avg_plan.price
            pull_txt = f"回踩 ${pull:,.2f}" if pull is not None else f"回踩 {label} ${mid:,.2f}"
            gate = "且杠杆回到上限内、" if over_leveraged else "且"
            condition("average_down", f"相对强弱企稳并{pull_txt}{gate}收盘不破 ${stop:,.2f} 后可评估补仓")
        if rec != "rally_reduce" and plans["rally_reduce"].allowed:
            condition("rally_reduce", f"反弹至 ${plans['rally_reduce'].price:,.2f} 附近（不主动清仓）")
        if watch_line is not None:
            condition("stop_exit", f"连续 {settings.watch_line_breach_days} 日收盘低于观察线 ${watch_line:,.2f} 后仍走弱，或触及硬止损 ${stop:,.2f}")
    else:
        if rec != "scale_out" and plans["scale_out"].allowed:
            condition("scale_out", f"价格达到止盈参考 ${cost + settings.take_profit_atr_multiple * atr:,.2f} 或 RSI ≥ 70")
        if (rec != "add_on_strength" and not plans["add_on_strength"].allowed and not broken
                and metrics.ma20 is not None and not over_leveraged):
            condition("add_on_strength", f"回踩 MA20 ${metrics.ma20:,.2f} 不破且20日相对强弱转正")
    if over_leveraged:
        if rec != "reduce_risk" and plans["reduce_risk"].allowed:
            condition("reduce_risk", f"账户杠杆 {leverage_pct:.0f}% 未降到 {settings.max_leverage_pct:g}% 以内前，优先执行减仓")
        condition("hold_watch", f"杠杆回到 {settings.max_leverage_pct:g}% 以内后，再重新评估补仓/加仓/换仓")
    elif rec != "reduce_risk" and plans["reduce_risk"].allowed and not (over_budget or overweight):
        condition("reduce_risk", f"最坏亏损超过单票预算 ${budget:,.0f} 或仓位超过 {settings.max_position_pct:g}%")
    if event_near:
        condition("hold_watch", f"财报（约 {earnings_days} 天后）落地后重新评估全部方案")

    source_label = SOURCE_LABELS[source] if mode == "loss" or source == "unknown" else (
        "近20日" + ("走弱：" + SOURCE_LABELS[source] if source != "cost" else "未走弱")
    )
    summary = f"{recommended.name}（{confidence}）· {TREND_LABELS[trend]} · {source_label}"

    non_sell_id = ""
    non_sell_summary = ""
    if mode == "loss":
        # Prefer an allowed non-sell plan; fall back to hold_watch (always allowed) with its playbook.
        candidates = [
            plans[pid] for pid in ("hold_watch", "average_down", "rally_reduce")
            if pid in plans and (plans[pid].allowed or pid == "hold_watch")
        ]
        if candidates:
            pick = max(
                candidates,
                key=lambda item: (item.allowed, item.score if item.allowed else -1, -PLAN_PRIORITY.index(item.id)),
            )
            # If the engine recommends selling, surface hold_watch as the explicit "若不卖出" path.
            if rec in ("stop_exit", "reduce_risk", "switch"):
                pick = plans["hold_watch"]
            non_sell_id = pick.id
            if pick.id == "hold_watch":
                non_sell_summary = (
                    f"持有观察：守{'观察线 $' + f'{watch_line:,.2f}' if watch_line is not None else '硬止损'}"
                    f" / 硬止损 ${stop:,.2f}，{watch_days} 个交易日；到止损最坏 ${hold_risk:,.0f}"
                    f"（预算 {budget_ratio * 100:.0f}%）"
                )
            elif pick.id == "average_down":
                non_sell_summary = (
                    f"分批补仓：{pick.trigger}；补后成本 ${pick.avg_cost_after:,.2f}，"
                    f"到保护线最坏 ${pick.worst_loss:,.0f}"
                    if pick.avg_cost_after is not None else pick.trigger
                )
            else:
                non_sell_summary = pick.trigger

    return HoldingDiagnosis(
        symbol=symbol, mode=mode, data_ready=data_ready, price=price, avg_cost=cost, quantity=quantity,
        pnl_pct=pnl_pct, pnl_amount=pnl_amount, market_value=market_value, weight_pct=weight_pct,
        trend_state=trend, trend_label=TREND_LABELS[trend], trend_flags=flags,
        loss_source=source, loss_source_label=source_label, attribution=attribution,
        rs5=rs5, rs20=rs20, rs60=rs60, rs_stable=rs_stable,
        leverage_pct=leverage_pct, over_leveraged=over_leveraged,
        sector_symbol=sector_symbol, sector_label=f"{sector_name(sector_symbol)}" + (f"({sector_symbol})" if sector_symbol else ""),
        atr=atr, atr_pct=atr_pct, volatility_label=volatility,
        earnings_days=earnings_days, event_near=event_near,
        stop=stop, stop_basis=stop_basis, stop_hit=stop_hit, hold_risk=hold_risk,
        position_budget=budget, budget_ratio=budget_ratio, overweight=overweight,
        plans=ordered, recommended=rec, confidence=confidence, switch_conditions=conditions,
        summary=summary,
        watch_line=watch_line, hard_stop=stop, watch_days=watch_days,
        non_sell_plan=non_sell_id, non_sell_summary=non_sell_summary,
    )


@dataclass
class PortfolioDiagnosis:
    holdings: list[HoldingDiagnosis]
    sector_exposure: list[dict]
    top_weight_pct: float
    top3_weight_pct: float
    total_hold_risk: float
    portfolio_budget: float
    notes: list[str]
    leverage_pct: float = 0.0
    over_leveraged: bool = False
    deleverage_amount: float = 0.0
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict:
        data = asdict(self)
        data["holdings"] = [item.to_dict() for item in self.holdings]
        return data


def diagnose_portfolio(
    positions: dict[str, dict],
    metrics: dict[str, HoldingMetrics],
    settings: DiagnosisSettings | None = None,
    *,
    benchmark_symbol: str = "SPY",
    earnings_days: dict[str, int] | None = None,
    net_liquidation: float | None = None,
    gross_position_value: float | None = None,
) -> PortfolioDiagnosis:
    """Diagnose every held symbol; `metrics` may include benchmark, sector ETFs and peers.

    Leverage = gross long value / net liquidation. Defaults: gross from held quantity × price
    (average cost when no quote), net liquidation = settings.account_value.
    """
    settings = settings or DiagnosisSettings()
    earnings_days = earnings_days or {}
    market = metrics.get(benchmark_symbol.upper())
    net = _valid(net_liquidation) or settings.account_value
    gross = _valid(gross_position_value)
    if gross is None:
        gross = 0.0
        for symbol in sorted(positions):
            quantity = float(positions[symbol].get("quantity") or 0.0)
            if quantity <= 0:
                continue
            held = metrics.get(symbol)
            unit = held.price if held is not None else float(positions[symbol].get("avg_cost") or 0.0)
            gross += quantity * unit
    leverage_pct = gross / net * 100.0
    over_leveraged = leverage_pct > settings.max_leverage_pct
    diagnoses: list[HoldingDiagnosis] = []
    for symbol in sorted(positions):
        held = metrics.get(symbol)
        if held is None:
            continue
        sector_symbol = sector_for(symbol)
        sector = metrics.get(sector_symbol) if sector_symbol and sector_symbol != symbol else None
        context = DiagnosisContext(
            market=market if symbol != benchmark_symbol.upper() else None,
            sector=sector,
            peers=metrics,
            earnings_days=earnings_days.get(symbol),
            leverage_pct=leverage_pct,
        )
        result = diagnose_holding(symbol, positions[symbol], held, context, settings)
        if result is not None:
            diagnoses.append(result)

    exposure: dict[str, float] = {}
    for item in diagnoses:
        key = item.sector_symbol or ""
        exposure[key] = exposure.get(key, 0.0) + item.weight_pct
    sector_rows = [
        {"sector_symbol": key or None, "sector_label": sector_name(key or None), "weight_pct": value}
        for key, value in sorted(exposure.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    weights = sorted((item.weight_pct for item in diagnoses), reverse=True)
    top_weight = weights[0] if weights else 0.0
    top3 = sum(weights[:3])
    total_risk = sum(item.hold_risk for item in diagnoses)
    budget = settings.portfolio_budget

    notes: list[str] = []
    deleverage_amount = max(0.0, gross - net * settings.max_leverage_pct / 100.0)
    if over_leveraged:
        released = sum(
            -plan.quantity_change * (plan.price or 0.0)
            for item in diagnoses
            for plan in item.plans
            if plan.id == "reduce_risk" and plan.allowed
        )
        notes.append(
            f"杠杆优先：持仓市值 ${gross:,.0f} = 净值的 {leverage_pct:.0f}%，"
            f"降到 {settings.max_leverage_pct:g}% 需卖出约 ${deleverage_amount:,.0f}；"
            f"各票减仓方案合计可释放约 ${released:,.0f}。杠杆回到上限内前不执行任何补仓/加仓/建仓。"
        )
    for row in sector_rows:
        if row["sector_symbol"] and row["weight_pct"] > settings.max_sector_pct:
            notes.append(
                f"行业暴露：{row['sector_label']}({row['sector_symbol']}) 约 {row['weight_pct']:.0f}%"
                f" > {settings.max_sector_pct:g}%"
            )
    for item in sorted(diagnoses, key=lambda value: (-value.weight_pct, value.symbol)):
        if item.overweight:
            notes.append(f"单票集中：{item.symbol} 占 {item.weight_pct:.1f}% > 上限 {settings.max_position_pct:g}%")
    if len(diagnoses) >= 3 and top3 >= 60.0:
        notes.append(f"前三持仓合计约 {top3:.0f}%，组合集中度偏高。")
    if diagnoses:
        if total_risk > budget:
            notes.append(f"合计最坏亏损 ${total_risk:,.0f} 超过组合风险预算 ${budget:,.0f}（{settings.portfolio_risk_pct:g}%）。")
        else:
            notes.append(f"合计最坏亏损 ${total_risk:,.0f}，占组合风险预算 {total_risk / budget * 100:.0f}%。")
    broken_losers = [item.symbol for item in diagnoses if item.mode == "loss" and item.trend_state == "broken"]
    if broken_losers:
        notes.append(f"{len(broken_losers)} 只亏损仓趋势破位：{'、'.join(broken_losers)}。")
    if not diagnoses:
        notes.append("暂无可诊断的持仓（需要持仓数量、成本与行情）。")
    return PortfolioDiagnosis(
        holdings=diagnoses,
        sector_exposure=sector_rows,
        top_weight_pct=top_weight,
        top3_weight_pct=top3,
        total_hold_risk=total_risk,
        portfolio_budget=budget,
        notes=notes,
        leverage_pct=leverage_pct,
        over_leveraged=over_leveraged,
        deleverage_amount=deleverage_amount,
    )


def context_symbols(positions: dict[str, dict], benchmark_symbol: str = "SPY") -> list[str]:
    """Extra symbols (benchmark + sector ETFs of holdings) the engine needs quotes for."""
    extra = [benchmark_symbol.upper()]
    for symbol, position in sorted(positions.items()):
        if float(position.get("quantity") or 0) <= 0:
            continue
        sector_symbol = sector_for(symbol)
        if sector_symbol and sector_symbol not in extra:
            extra.append(sector_symbol)
    return extra
