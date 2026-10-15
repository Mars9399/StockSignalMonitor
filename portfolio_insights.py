"""Portfolio concentration and rebalance hints for personal accounts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class PortfolioInsight:
    account_value: float
    portfolio_value: float
    cash_or_available: float | None
    positions: list[dict] = field(default_factory=list)
    top_concentration_pct: float = 0.0
    overweight: list[str] = field(default_factory=list)
    rebalance_hints: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def build_portfolio_insight(
    positions: dict[str, dict],
    levels: dict[str, dict],
    *,
    account_value: float,
    max_position_pct: float,
    available_funds: float | None = None,
) -> PortfolioInsight:
    safe_account = max(1.0, float(account_value))
    rows: list[dict] = []
    total = 0.0
    for symbol, position in positions.items():
        qty = float(position.get("quantity") or 0)
        if qty <= 0:
            continue
        price = float(levels.get(symbol, {}).get("price") or position.get("avg_cost") or 0)
        value = max(0.0, qty * price)
        total += value
        weight = value / safe_account * 100.0
        limit = float(max_position_pct)
        rows.append(
            {
                "symbol": symbol,
                "quantity": qty,
                "price": price,
                "value": value,
                "weight_pct": weight,
                "limit_pct": limit,
                "over_limit": weight > limit,
            }
        )
    rows.sort(key=lambda item: item["value"], reverse=True)
    top = rows[:3]
    top_pct = sum(item["weight_pct"] for item in top)
    overweight = [f"{item['symbol']} {item['weight_pct']:.1f}% > 上限 {item['limit_pct']:.0f}%" for item in rows if item["over_limit"]]
    hints: list[str] = []
    if overweight:
        hints.append("超配：" + "；".join(overweight) + "。可关注减仓至单股上限内（非自动调仓）。")
    if top_pct >= 60 and len(top) >= 2:
        names = "、".join(item["symbol"] for item in top)
        hints.append(f"前三持仓合计约 {top_pct:.0f}%（{names}），组合集中度偏高。")
    if available_funds is not None and available_funds / safe_account < 0.05:
        hints.append(f"可用资金偏低（约 {available_funds:,.0f}），新增买入空间有限。")
    if total / safe_account >= 0.95:
        hints.append("持仓市值接近账户规模，再平衡时应优先考虑减仓而非加仓。")
    if not hints and rows:
        hints.append("当前未见明显超配；仍请结合个股卖出触发点与账户风险自行判断。")
    if not rows:
        summary = "暂无持仓"
    else:
        summary = (
            f"持仓 {len(rows)} 只 · 市值 ${total:,.0f} · 占账户 {total / safe_account * 100:.0f}%"
            f" · 前三集中度 {top_pct:.0f}%"
        )
    return PortfolioInsight(
        account_value=safe_account,
        portfolio_value=total,
        cash_or_available=available_funds,
        positions=rows,
        top_concentration_pct=top_pct,
        overweight=overweight,
        rebalance_hints=hints,
        summary=summary,
    )
