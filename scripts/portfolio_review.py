"""Read-only portfolio review: TWS positions + Yahoo daily bars -> Markdown report.

Rule-based technical analysis only; never places orders.

Usage:
    python3 scripts/portfolio_review.py [--port 7496] [--out report.md] [--no-movers]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import plistlib
import socket
import struct
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signal_monitor import calculate_levels  # noqa: E402
from tws_positions import fetch_positions, merge_positions  # noqa: E402

MAC_PLIST = Path.home() / "Library/Containers/com.mars9399.StockSignalMonitor.macOS/Data/Library/Preferences/com.mars9399.StockSignalMonitor.macOS.plist"
LOCAL_DIRS = [ROOT, Path.home() / "Documents/Codex/2026-09-03/new-chat/work/StockSignalMonitor"]
BENCHMARKS = ["SPY", "QQQ"]
SECTOR_ETF = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV",
    "Industrials": "XLI", "Energy": "XLE", "Utilities": "XLU",
    "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
    "Communication Services": "XLC", "Basic Materials": "XLB", "Real Estate": "XLRE",
}
INDUSTRY_ETF = {"Semiconductors": "SMH", "Semiconductor Equipment & Materials": "SMH"}
SECTOR_LEADERS = {
    "XLK": ["MSFT", "AVGO", "NVDA"], "SMH": ["NVDA", "AVGO", "TSM"],
    "XLF": ["JPM", "GS", "V"], "XLV": ["LLY", "ISRG", "ABBV"],
    "XLI": ["GE", "GEV", "CAT"], "XLE": ["XOM", "CVX"], "XLU": ["VST", "CEG"],
    "XLY": ["AMZN", "TSLA"], "XLC": ["META", "GOOGL", "NFLX"], "XLP": ["COST", "WMT"],
    "XLB": ["LIN"], "XLRE": ["PLD"],
}
ACCOUNT_TAGS = "NetLiquidation,TotalCashValue,AvailableFunds,BuyingPower,GrossPositionValue"


# ---------------------------------------------------------------- data in

def _frame(*fields: str) -> bytes:
    payload = ("\0".join(fields) + "\0").encode()
    return struct.pack("!I", len(payload)) + payload


def fetch_account_summary_raw(host="127.0.0.1", port=7496, client_id=918, timeout=15) -> dict:
    """Read-only reqAccountSummary over the raw socket protocol (no ibapi dependency)."""
    deadline = time.monotonic() + timeout
    with socket.create_connection((host, port), timeout=timeout) as conn:
        def read_exact(size):
            data = bytearray()
            while len(data) < size:
                if time.monotonic() > deadline:
                    raise TimeoutError("account summary timeout")
                chunk = conn.recv(size - len(data))
                if not chunk:
                    raise ConnectionError("TWS closed connection")
                data.extend(chunk)
            return bytes(data)

        def read_fields():
            length = struct.unpack("!I", read_exact(4))[0]
            return read_exact(length).decode("utf-8").rstrip("\0").split("\0")

        version = b"v100..157"
        conn.sendall(b"API\0" + struct.pack("!I", len(version)) + version)
        read_fields()
        conn.sendall(_frame("71", "2", str(client_id), ""))
        requested, out = False, {}
        while True:
            f = read_fields()
            if f[0] == "9" and not requested:
                conn.sendall(_frame("62", "1", "9201", "All", ACCOUNT_TAGS))
                requested = True
            elif f[0] == "63" and len(f) >= 7:
                try:
                    out.setdefault(f[3], {})[f[4]] = float(f[5])
                except ValueError:
                    pass
            elif f[0] == "64" and requested:
                conn.sendall(_frame("63", "1", "9201"))
                return out
            elif f[0] == "4" and len(f) >= 5 and int(f[3]) not in {2104, 2106, 2107, 2108, 2158, 2176}:
                raise ConnectionError(f"TWS {f[3]}: {f[4]}")


def load_mac_prefs() -> dict:
    if not MAC_PLIST.exists():
        return {}
    prefs = plistlib.load(MAC_PLIST.open("rb"))
    raw = prefs.get("positions")
    if isinstance(raw, bytes):
        prefs["positions"] = json.loads(raw)
    return prefs


def load_local_json(name: str):
    for base in LOCAL_DIRS:
        path = base / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), path
    return None, None


def load_positions(host: str, port: int) -> tuple[dict, str, dict]:
    prefs = load_mac_prefs()
    mac_positions = {
        s: {"quantity": v.get("quantity"), "avg_cost": v.get("averageCost"),
            "initial_stop": v.get("initialStop"), "risk_reference_price": v.get("riskReferencePrice")}
        for s, v in (prefs.get("positions") or {}).items()
    }
    try:
        snapshot = fetch_positions(host=host, port=port, client_id=917, timeout=20)
        merged, _, _ = merge_positions({}, snapshot, set())
        for sym, pos in merged.items():
            old = mac_positions.get(sym, {})
            if old.get("quantity") == pos["quantity"]:
                pos["initial_stop"] = old.get("initial_stop")
        accounts = sorted({p["account"] for p in snapshot})
        return merged, f"TWS {host}:{port} 只读（账户 {', '.join(accounts)}）", prefs
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] TWS 读取失败: {exc}", file=sys.stderr)
    data, path = load_local_json("positions.json")
    if data:
        return data, f"本地 {path}", prefs
    if mac_positions:
        return mac_positions, f"Mac 应用偏好 {MAC_PLIST}", prefs
    raise SystemExit("无法读取持仓：请启动 TWS/IB Gateway 并开启 Socket API（只读），或提供 positions.json")


def download(symbols: list[str], period="2y", chunk=8, attempts=4) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    pending = sorted(set(symbols))
    for attempt in range(attempts):
        missing = []
        for i in range(0, len(pending), chunk):
            batch = pending[i:i + chunk]
            try:
                raw = yf.download(batch, period=period, interval="1d", auto_adjust=False,
                                  group_by="ticker", threads=False, progress=False)
            except Exception:  # noqa: BLE001
                missing.extend(batch)
                continue
            for sym in batch:
                try:
                    df = raw[sym].copy()
                except KeyError:
                    missing.append(sym)
                    continue
                df.columns = [str(c).lower() for c in df.columns]
                df = df.dropna(subset=["close"])
                if df.empty:
                    missing.append(sym)
                    continue
                df.index = pd.to_datetime(df.index).tz_localize(None)
                out[sym] = df
            time.sleep(0.5)
        if not missing:
            break
        pending = missing
        time.sleep(4 * 2 ** attempt)
    else:
        print(f"[warn] 未取到行情：{', '.join(pending)}", file=sys.stderr)
    return out


STATIC_META = {
    "SKHY": ("Technology", "Semiconductors"), "STM": ("Technology", "Semiconductors"),
    "NVDA": ("Technology", "Semiconductors"), "AAOI": ("Technology", "Communication Equipment"),
    "CRCL": ("Financial Services", "Credit Services"), "TEM": ("Healthcare", "Health Information Services"),
}


def ticker_meta(sym: str, attempts: int = 3) -> dict:
    meta = {}
    for attempt in range(attempts):
        meta = _ticker_meta_once(sym)
        if meta.get("_ok"):
            break
        time.sleep(2 * (attempt + 1))
    if not meta.get("sector") and sym in STATIC_META:
        meta["sector"], meta["industry"] = STATIC_META[sym]
    return meta


def _ticker_meta_once(sym: str) -> dict:
    meta = {"name": sym, "sector": "", "industry": "", "earnings": None, "mcap": None}
    try:
        t = yf.Ticker(sym)
        info = t.info or {}
        meta["_ok"] = bool(info)
        meta.update(name=info.get("shortName") or sym, sector=info.get("sector") or "",
                    industry=info.get("industry") or "", mcap=info.get("marketCap"))
        ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
        if ts:
            meta["earnings"] = datetime.fromtimestamp(ts).date()
        try:
            cal = t.calendar or {}
            dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if dates:
                upcoming = [d for d in dates if d >= datetime.now().date() - timedelta(days=1)]
                if upcoming:
                    meta["earnings"] = min(upcoming)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] {sym} meta: {exc}", file=sys.stderr)
    return meta


def sector_etf(meta: dict) -> str:
    return INDUSTRY_ETF.get(meta["industry"]) or SECTOR_ETF.get(meta["sector"], "SPY")


# ---------------------------------------------------------------- metrics

def ret(close: pd.Series, days: int) -> float | None:
    if len(close) <= days:
        return None
    return (close.iloc[-1] / close.iloc[-days - 1] - 1) * 100


def metrics(df: pd.DataFrame, bench: dict[str, pd.DataFrame], etf: str) -> dict:
    close = df["close"].astype(float)
    price = float(close.iloc[-1])
    lv = calculate_levels(df, price)
    sma = {n: (float(close.rolling(n).mean().iloc[-1]) if len(close) >= n else None) for n in (20, 50, 200)}
    sma50_prev = float(close.rolling(50).mean().iloc[-11]) if len(close) >= 61 else None
    year = close.tail(252)
    hi52, lo52 = float(df["high"].tail(252).max()), float(df["low"].tail(252).min())
    vol20 = float(df["volume"].tail(21).iloc[:-1].mean()) if "volume" in df else 0
    vol5 = float(df["volume"].tail(6).iloc[:-1].mean()) if "volume" in df else 0
    up = close.diff() > 0
    tail = df.tail(21).iloc[:-1]
    upvol = float(tail["volume"][close.diff().reindex(tail.index) > 0].sum())
    dnvol = float(tail["volume"][close.diff().reindex(tail.index) <= 0].sum())
    daily = close.pct_change().dropna()
    rs = {}
    for label, days in (("1m", 21), ("3m", 63), ("6m", 126)):
        r = ret(close, days)
        rs[label] = {
            "abs": r,
            "vs_spy": None if r is None or ret(bench["SPY"]["close"], days) is None else r - ret(bench["SPY"]["close"], days),
            "vs_sector": None if r is None or etf not in bench or ret(bench[etf]["close"], days) is None
            else r - ret(bench[etf]["close"], days),
        }
    atr = float(lv["atr14"])
    return {
        "price": price, "levels": lv, "sma": sma,
        "sma50_rising": None if sma50_prev is None or sma[50] is None else sma[50] > sma50_prev,
        "hi52": hi52, "lo52": lo52,
        "from_hi_pct": (price / hi52 - 1) * 100, "from_lo_pct": (price / lo52 - 1) * 100,
        "atr": atr, "atr_pct": atr / price * 100,
        "vol_ann": float(daily.tail(63).std() * math.sqrt(252) * 100) if len(daily) > 5 else None,
        "vol5_vs20": vol5 / vol20 if vol20 else None,
        "updown_vol": upvol / dnvol if dnvol else None,
        "rs": rs, "history_days": len(close), "first_date": close.index[0].date(),
        "ch_hi": float(lv["buy_point"]), "ch_lo": float(lv["stop_point"]),
        "ext20_atr": (price - sma[20]) / atr if sma[20] and atr else None,
        "ret_1d": ret(close, 1),
        "_up": up,
    }


def trend_score(m: dict) -> int:
    p, s = m["price"], m["sma"]
    score = 0
    for n in (20, 50, 200):
        if s[n] is not None:
            score += 1 if p > s[n] else -1
    if s[50] and s[200]:
        score += 1 if s[50] > s[200] else -1
    if m["sma50_rising"] is not None:
        score += 1 if m["sma50_rising"] else -1
    return score


def rs_score(m: dict) -> float:
    vals = []
    for k, w in (("1m", 0.3), ("3m", 0.4), ("6m", 0.3)):
        v = m["rs"][k]["vs_spy"]
        if v is not None:
            vals.append((v, w))
    if not vals:
        return 0.0
    return sum(v * w for v, w in vals) / sum(w for _, w in vals)


def channel_pos(m: dict) -> float | None:
    hi, lo = m["ch_hi"], m["ch_lo"]
    return None if hi <= lo else (m["price"] - lo) / (hi - lo) * 100


def add_zone(m: dict) -> tuple[float, float, str]:
    p, s, atr = m["price"], m["sma"], m["atr"]
    for n in (20, 50, 200):
        if s[n] and p >= s[n]:
            lo = s[n]
            return lo, min(p, lo + 0.5 * atr), f"回踩 {n} 日均线"
    return m["ch_lo"], m["ch_lo"] + 0.5 * atr, "回踩 10 日通道下沿"


def protective_stop(m: dict, initial: float | None) -> tuple[float, str]:
    p, atr = m["price"], m["atr"]
    atr_line = p - 2 * atr
    candidates = [(atr_line, "现价−2×ATR"), (m["ch_lo"], "10 日通道下沿")]
    # A stop closer than 1×ATR is inside daily noise.
    below = [(v, l) for v, l in candidates if v <= p - atr]
    stop, label = max(below) if below else (atr_line, "现价−2×ATR")
    if initial and initial <= p - atr and initial > stop:
        stop, label = initial, "应用内初始止损"
    return stop, label


def verdict(m: dict, weight: float, max_w: float, pnl_pct: float, initial: float | None) -> dict:
    t, r = trend_score(m), rs_score(m)
    p, s = m["price"], m["sma"]
    status = m["levels"]["status"]
    ext = m["ext20_atr"] or 0
    reasons, risks = [], []
    below_stop = initial is not None and p < initial
    key_ma = s[50] or s[20]
    if below_stop or (status == "SELL_ALERT" and key_ma and p < key_ma and r < 0):
        action = "止损观察"
        reasons.append("已跌破应用内初始止损" if below_stop else "跌破 10 日通道下沿且位于中期均线下方，相对强弱为负")
    elif t <= -2 and r < -5:
        action = "减仓"
        reasons.append(f"趋势分 {t}（均线空头排列），相对 SPY 落后 {r:.1f} pct")
    elif weight > max_w:
        action = "减仓"
        reasons.append(f"单票占比 {weight:.0f}% 超过上限 {max_w:.0f}%")
    elif t >= 2 and r > 0 and ext <= 1.5 and weight < max_w * 0.8:
        action = "加仓"
        reasons.append(f"趋势分 {t}、相对 SPY 领先 {r:.1f} pct，且距 20 日线仅 {ext:.1f}×ATR，未过度延伸")
    else:
        action = "持有"
        if t >= 2 and ext > 1.5:
            reasons.append(f"趋势向上但距 20 日线 {ext:.1f}×ATR，偏延伸，等回踩再加")
        elif t >= 2 and r <= 0:
            reasons.append(f"趋势尚可但相对 SPY 落后 {r:.1f} pct，不追加")
        else:
            reasons.append(f"趋势分 {t}、相对强弱 {r:+.1f} pct，信号不一致")
    agree = sum([t >= 2, r > 0, (m["updown_vol"] or 1) > 1, m["sma50_rising"] is True])
    if action in ("减仓", "止损观察"):
        agree = sum([t <= -1, r < 0, (m["updown_vol"] or 1) < 1, m["sma50_rising"] is False])
    confidence = "高" if agree >= 4 else "中" if agree >= 2 else "低"
    if m["history_days"] < 200:
        risks.append(f"上市/历史仅 {m['history_days']} 个交易日，200 日线不可用，信号可靠性下降")
        confidence = "低" if confidence == "中" else confidence
    if (m["vol_ann"] or 0) > 60:
        risks.append(f"年化波动 {m['vol_ann']:.0f}%，单日波动大")
    if m["from_hi_pct"] > -5:
        risks.append("接近 52 周高点，追高回撤风险")
    return {"action": action, "trend": t, "rs": r, "reasons": reasons, "risks": risks, "confidence": confidence}


# ---------------------------------------------------------------- report

def f(v, fmt="{:.2f}", none="—"):
    return none if v is None or (isinstance(v, float) and math.isnan(v)) else fmt.format(v)


def pct(v):
    return f(v, "{:+.1f}%")


def candidate_score(m: dict) -> float:
    cp = channel_pos(m)
    pullback = 0.0
    ext = m["ext20_atr"]
    if ext is not None:
        pullback = 2.0 if -0.5 <= ext <= 1.0 else 0.5 if ext <= 2 else -1.5
    volume = 1.0 if (m["updown_vol"] or 1) > 1.1 else 0.0
    return trend_score(m) * 1.5 + max(-15, min(15, rs_score(m))) / 3 + pullback + volume - (1 if cp and cp > 95 else 0)


# ---------------------------------------------------------------- playbooks

PER_POSITION_RISK_PCT = 2.0
LOSS_PLAYBOOK_PCT = 0.0
GAIN_PLAYBOOK_PCT = 20.0


def prior_low(df: pd.DataFrame) -> float | None:
    window = df["low"].iloc[-60:-10]
    return float(window.min()) if len(window) >= 20 else None


def diagnose(r: dict, bench: dict, etf: str, earnings) -> dict:
    m = r["m"]
    rs = m["rs"]
    spy1, spy3 = ret(bench["SPY"]["close"], 21), ret(bench["SPY"]["close"], 63)
    sec_vs_spy3 = None
    if etf in bench and etf != "SPY":
        e3 = ret(bench[etf]["close"], 63)
        sec_vs_spy3 = None if e3 is None or spy3 is None else e3 - spy3
    vs_spy = rs["3m"]["vs_spy"] if rs["3m"]["vs_spy"] is not None else rs["1m"]["vs_spy"]
    vs_sec = rs["3m"]["vs_sector"] if rs["3m"]["vs_sector"] is not None else rs["1m"]["vs_sector"]
    if (spy1 or 0) < -3 and (rs["1m"]["vs_spy"] or 0) > -5:
        cause = "大盘回撤"
    elif sec_vs_spy3 is not None and sec_vs_spy3 < -3 and (vs_sec or 0) > -5:
        cause = "板块拖累"
    else:
        cause = "个股走弱" if (vs_spy or 0) < 0 else "个股强于大盘（亏损源于买点偏高/短期回调）"
    pl = prior_low(bench[r["sym"]])
    s200 = m["sma"][200]
    s50 = m["sma"][50]
    broken = {
        "below_50ma": None if s50 is None else m["price"] < s50,
        "below_200ma": None if s200 is None else m["price"] < s200,
        "below_prior_low": None if pl is None else m["price"] < pl,
        "below_channel_low": m["price"] <= m["ch_lo"],
    }
    hits = sum(1 for v in broken.values() if v)
    state = "已破位" if hits >= 3 or (broken["below_200ma"] and broken["below_prior_low"]) else "部分破位" if hits >= 1 else "趋势未破"
    rs_improving = (
        rs["1m"]["vs_spy"] is not None and vs_spy is not None
        and rs["1m"]["vs_spy"] > vs_spy and rs["1m"]["vs_spy"] > -3
    )
    days_to_earn = (earnings - datetime.now().date()).days if earnings else None
    return {
        "cause": cause, "trend_state": state, "breaks": broken, "prior_low": pl,
        "stock_vs_spy_3m": vs_spy, "stock_vs_sector_3m": vs_sec, "sector_vs_spy_3m": sec_vs_spy3,
        "spy_1m": spy1, "spy_3m": spy3, "rs_improving": rs_improving,
        "earnings": str(earnings) if earnings else None, "days_to_earnings": days_to_earn,
        "earnings_soon": days_to_earn is not None and 0 <= days_to_earn <= 14,
    }


def _resistances(m: dict) -> list[tuple[float, str]]:
    p = m["price"]
    levels = [(m["sma"][n], f"{n} 日线") for n in (20, 50, 200) if m["sma"][n] and m["sma"][n] > p * 1.005]
    if m["ch_hi"] > p * 1.005:
        levels.append((m["ch_hi"], "10 日通道上沿"))
    levels.sort()
    if not levels or levels[0][0] > p + 3 * m["atr"]:
        levels.insert(0, (p + 1.5 * m["atr"], "现价+1.5×ATR"))
    out = []
    for v, label in levels:
        if not out or v > out[-1][0] * 1.02:
            out.append((v, label))
    return out or [(p + m["atr"], "现价+1×ATR"), (p + 2 * m["atr"], "现价+2×ATR")]


def build_playbook(r: dict, diag: dict, net_liq: float, max_w: float, swaps: list[dict], leverage: float = 1.0) -> dict:
    m, qty, cost = r["m"], r["qty"], r["cost"]
    p, atr = m["price"], m["atr"]
    stop = r["stop"][0]
    budget = net_liq * PER_POSITION_RISK_PCT / 100
    risk_now = max(0.0, (p - stop) * qty)
    gap_loss = max(0.0, (p - (stop - atr)) * qty)
    loss_at_stop = (stop - cost) * qty
    share = lambda x: round(x / budget * 100, 1)  # noqa: E731
    opts = []

    opts.append({
        "id": "stop_exit", "name": "止损离场",
        "trigger": f"收盘跌破 {stop:.2f}（{r['stop'][1]}）全部卖出；或现在直接离场",
        "orders": [{"side": "SELL", "qty": qty, "price": round(stop, 2), "type": "条件触发"}],
        "now_exit_pnl": round((p - cost) * qty, 0),
        "pnl_at_stop": round(loss_at_stop, 0),
        "additional_risk_from_now": round(risk_now, 0),
        "gap_worst_case": round(gap_loss, 0),
        "risk_budget_pct": share(risk_now),
        "pros": "风险封顶，释放资金换更强标的", "cons": "若属于大盘/板块性回撤，可能卖在低点",
    })

    guard = m["ch_lo"] if stop < m["ch_lo"] < p else stop
    watch_days = 10 if not diag["earnings_soon"] else max(1, diag["days_to_earnings"] + 2)
    opts.append({
        "id": "hold_watch", "name": "持有观察",
        "trigger": (f"观察线 {guard:.2f}（10 日下沿），硬止损 {stop:.2f}；观察 {watch_days} 个交易日；"
                    f"连续 2 日收盘低于观察线减半，触及硬止损或 1 月相对 SPY 再走弱 5pct 全部止损"
                    if guard != stop else
                    f"守住 {stop:.2f}，观察 {watch_days} 个交易日；连续 2 日收盘低于 {stop:.2f} 或 1 月相对 SPY 再走弱 5pct 转为止损"),
        "guard_line": round(guard, 2), "hard_stop": round(stop, 2), "watch_days": watch_days,
        "orders": ([{"side": "SELL", "qty": int(qty // 2), "price": round(guard, 2), "type": "观察线失守减半"},
                    {"side": "SELL", "qty": qty - int(qty // 2), "price": round(stop, 2), "type": "硬止损"}]
                   if guard != stop else
                   [{"side": "SELL", "qty": qty, "price": round(stop, 2), "type": "失守则止损"}]),
        "pnl_at_stop": round(loss_at_stop, 0),
        "additional_risk_from_now": round(risk_now, 0),
        "gap_worst_case": round(gap_loss, 0),
        "risk_budget_pct": share(risk_now),
        "pros": "不在情绪低点割肉，给均值回归时间", "cons": "占用风险预算，走弱时亏损扩大到止损位",
    })

    allowed = (diag["trend_state"] == "趋势未破" and (diag["rs_improving"] or diag["cause"] != "个股走弱")
               and leverage <= 1.0)
    p1 = round(min(p, max(add_zone(m)[0], stop + atr)), 2)
    p2 = round(max(stop + 0.5 * atr, p1 - atr), 2)
    room_risk = budget - risk_now
    per_share = ((p1 - stop) + (p2 - stop)) / 2
    max_by_risk = int(room_risk / per_share) if per_share > 0 and room_risk > 0 else 0
    max_by_weight = int(max(0.0, net_liq * max_w / 100 - qty * p) / max(p1, 0.01))
    add_total = max(0, min(max_by_risk, max_by_weight, int(qty)))
    q1 = add_total // 2
    q2 = add_total - q1
    new_qty = qty + add_total
    new_cost = (qty * cost + q1 * p1 + q2 * p2) / new_qty if new_qty else cost
    dca_risk = risk_now + q1 * (p1 - stop) + q2 * (p2 - stop)
    reason = []
    if diag["trend_state"] != "趋势未破":
        reason.append(f"趋势{diag['trend_state']}")
    if not diag["rs_improving"] and diag["cause"] == "个股走弱":
        reason.append("个股走弱且相对强弱未企稳")
    if add_total == 0:
        reason.append("风险预算/仓位上限已无补仓空间")
    if leverage > 1.0:
        reason.append(f"账户总仓位 {leverage * 100:.0f}% 净值（已用融资），补仓会进一步加杠杆")
    opts.append({
        "id": "scale_in", "name": "分批补仓摊低",
        "eligible": bool(allowed and add_total > 0),
        "ineligible_reason": "；".join(reason) or None,
        "trigger": f"仅在价格回踩 {p1:.2f}/{p2:.2f} 且收盘不破 {stop:.2f}、1 月相对强弱不再恶化时执行"
                   + ("；财报前不执行" if diag["earnings_soon"] else ""),
        "orders": [{"side": "BUY", "qty": q1, "price": p1, "type": "限价第一批"},
                   {"side": "BUY", "qty": q2, "price": p2, "type": "限价第二批"}] if add_total else [],
        "new_qty": new_qty, "new_avg_cost": round(new_cost, 2),
        "pnl_at_stop": round((stop - new_cost) * new_qty, 0),
        "additional_risk_from_now": round(dca_risk, 0),
        "max_risk_cap": round(budget, 0),
        "gap_worst_case": round(dca_risk + atr * new_qty, 0),
        "risk_budget_pct": share(dca_risk),
        "pros": f"成本降至 {new_cost:.2f}，回到成本所需涨幅缩小", "cons": "亏损仓加码；破位时亏损放大",
    })

    in_budget = int(budget / (p - stop)) if p > stop else int(qty)
    half = int(min(qty, max(qty // 2, qty - in_budget)))
    remain = qty - half
    swap_text = "、".join(f"{s['sym']}（3M vs SPY {pct(s['rs3'])}）" for s in swaps) or "暂无同板块更强候选"
    opts.append({
        "id": "reduce_or_swap", "name": "减仓降风险 / 换仓",
        "trigger": f"现价附近卖出 {half} 股（{half / qty * 100:.0f}%，使余仓到止损风险 ≤ 每票预算或至少减半），剩余 {remain:.0f} 股守 {stop:.2f}；释放资金可换到：{swap_text}",
        "orders": [{"side": "SELL", "qty": half, "price": round(p, 2), "type": "限价/市价"}],
        "swap_candidates": swaps,
        "realized_now": round((p - cost) * half, 0),
        "pnl_at_stop": round((p - cost) * half + (stop - cost) * remain, 0),
        "additional_risk_from_now": round((p - stop) * remain, 0),
        "gap_worst_case": round((p - stop + atr) * remain, 0),
        "risk_budget_pct": share((p - stop) * remain),
        "pros": "风险减半，保留反弹参与", "cons": "锁定一半亏损；若快速反弹收益减半",
    })

    res = _resistances(m)[:2]
    t1 = int(qty // 3)
    t2 = int(qty // 3)
    opts.append({
        "id": "bounce_reduce", "name": "反弹减仓",
        "trigger": "；".join(f"反弹至 {v:.2f}（{lab}）卖出 {n} 股" for (v, lab), n in zip(res, (t1, t2)))
                   + f"；期间收盘跌破 {stop:.2f} 余仓止损",
        "orders": [{"side": "SELL", "qty": n, "price": round(v, 2), "type": f"限价·{lab}"} for (v, lab), n in zip(res, (t1, t2))],
        "pnl_at_stop": round(loss_at_stop, 0),
        "pnl_if_filled": round(sum((v - cost) * n for (v, _), n in zip(res, (t1, t2))), 0),
        "additional_risk_from_now": round(risk_now, 0),
        "gap_worst_case": round(gap_loss, 0),
        "risk_budget_pct": share(risk_now),
        "pros": "在阻力位而非低点降仓，减少卖在底部", "cons": "反弹未到阻力位前风险不变",
    })

    cause, state = diag["cause"], diag["trend_state"]
    if state == "已破位" and cause == "个股走弱":
        rec, alt = "stop_exit", "bounce_reduce"
        why = f"个股自身走弱且多条支撑已破，继续持有的期望较差，优先控制亏损：可现价或日内反弹时离场，最迟收盘跌破 {stop:.2f} 执行"
        switch = f"若 3 日内放量收回 20 日线 {f(m['sma'][20])}，改为「反弹减仓」或「持有观察」"
    elif state == "已破位":
        rec, alt = "reduce_or_swap", "stop_exit"
        why = f"亏损主要来自{cause}，但个股已破位：先减半降风险，保留反弹仓位"
        switch = f"收盘跌破 {stop:.2f} 改为「止损离场」；板块/大盘企稳且收回 50 日线改回「持有观察」"
    elif state == "部分破位":
        rec, alt = "bounce_reduce", "stop_exit"
        why = "一条支撑失守、尚未全面破位：等反弹到阻力位降仓，比在低点卖出更合理"
        switch = f"收盘跌破 {stop:.2f} 改为「止损离场」；重新站上 50 日线且相对强弱转正改为「持有观察」"
    elif opts[2]["eligible"] and diag["rs_improving"] and not diag["earnings_soon"]:
        rec, alt = "scale_in", "hold_watch"
        why = "趋势未破、相对强弱企稳且风险预算有余，回踩支撑分批补仓性价比最高"
        switch = f"第一批成交后若收盘跌破 {stop:.2f} 停止补仓并全部止损；相对强弱再转弱则只持有不补"
    else:
        rec, alt = "hold_watch", "scale_in" if opts[2]["eligible"] else "reduce_or_swap"
        why = "趋势未破但相对强弱尚未明确企稳" + ("、财报临近" if diag["earnings_soon"] else "") + "：守线观察，不急于加减"
        switch = (f"相对强弱回升且回踩 {opts[2]['orders'][0]['price'] if opts[2]['orders'] else '支撑'} 企稳改为「分批补仓」；"
                  f"连续 2 日收盘低于 {stop:.2f} 改为「止损离场」")
    if (risk_now > budget * 1.5 and rec in ("hold_watch", "scale_in")) or (risk_now > budget * 3 and rec == "bounce_reduce"):
        rec, alt = "reduce_or_swap", rec
        why += f"；但当前到止损的风险 ${risk_now:,.0f} 已是每票预算 ${budget:,.0f} 的 {risk_now / budget:.1f} 倍，先把仓位降到预算内，余仓再按备选方案处理"
        switch = f"减仓后余仓按「{names_cn(alt)}」执行；" + switch
    return {
        "symbol": r["sym"], "kind": "loss" if r["pnl_pct"] < 0 else "gain",
        "quantity": qty, "avg_cost": round(cost, 4), "price": round(p, 2), "pnl": round(r["pnl"], 0),
        "pnl_pct": round(r["pnl_pct"], 2), "atr14": round(atr, 2), "stop": round(stop, 2), "stop_basis": r["stop"][1],
        "risk_budget_per_position": round(budget, 0), "risk_to_stop_now": round(risk_now, 0),
        "diagnosis": diag, "options": opts,
        "recommended": rec, "fallback": alt, "why": why, "switch_condition": switch,
    }


OPTION_NAMES = {"stop_exit": "止损离场", "hold_watch": "持有观察", "scale_in": "分批补仓摊低",
                "reduce_or_swap": "减仓降风险 / 换仓", "bounce_reduce": "反弹减仓",
                "trail_hold": "移动止损持有", "take_profit": "分批止盈", "pullback_add": "回踩加仓"}
ACTION_FROM_PLAYBOOK = {"stop_exit": "减仓", "hold_watch": "持有", "scale_in": "加仓", "reduce_or_swap": "减仓",
                        "bounce_reduce": "减仓", "trail_hold": "持有", "take_profit": "减仓", "pullback_add": "加仓"}


def names_cn(option_id: str) -> str:
    return OPTION_NAMES.get(option_id, option_id)


def build_gain_playbook(r: dict, diag: dict, net_liq: float) -> dict:
    m, qty, cost = r["m"], r["qty"], r["cost"]
    p, atr = m["price"], m["atr"]
    trail = max(r["stop"][0], p - 3 * atr, m["sma"][20] or 0)
    t = int(qty // 3)
    ext = m["ext20_atr"] or 0
    opts = [
        {"id": "trail_hold", "name": "移动止损持有", "trigger": f"止损上移到 {trail:.2f}（max(现价−3ATR, 20 日线)）",
         "locked_pnl": round((trail - cost) * qty, 0), "pros": "让利润奔跑", "cons": "回撤会吐回部分浮盈"},
        {"id": "take_profit", "name": "分批止盈", "trigger": f"现价/冲高 {p + atr:.2f} 卖出 {t} 股，余仓移动止损",
         "orders": [{"side": "SELL", "qty": t, "price": round(p + atr, 2)}],
         "realized": round((p + atr - cost) * t, 0), "pros": "锁定部分利润、降低集中度", "cons": "强势股可能少赚"},
        {"id": "pullback_add", "name": "回踩加仓", "trigger": f"回踩 {add_zone(m)[0]:.2f}–{add_zone(m)[1]:.2f} 企稳再加",
         "pros": "顺势加码", "cons": "抬高成本，需要严格止损"},
    ]
    rec = "take_profit" if ext > 2 or r["weight"] > 30 else "trail_hold"
    return {"symbol": r["sym"], "kind": "gain", "quantity": qty, "avg_cost": round(cost, 4), "price": round(p, 2),
            "pnl": round(r["pnl"], 0), "pnl_pct": round(r["pnl_pct"], 2), "diagnosis": diag, "options": opts,
            "recommended": rec, "fallback": "trail_hold" if rec == "take_profit" else "take_profit",
            "why": "价格偏离 20 日线较远或仓位偏重，先兑现一部分" if rec == "take_profit" else "趋势健康未过度延伸，移动止损让利润奔跑",
            "switch_condition": f"收盘跌破 {trail:.2f} 执行移动止损"}


def swap_candidates(r: dict, etf: str, bench: dict) -> list[dict]:
    mine = r["m"]["rs"]["3m"]["vs_spy"] or -999
    out = []
    for s in SECTOR_LEADERS.get(etf, []):
        if s == r["sym"] or s not in bench:
            continue
        try:
            m = metrics(bench[s], bench, etf)
        except Exception:  # noqa: BLE001
            continue
        rs3 = m["rs"]["3m"]["vs_spy"]
        if rs3 is not None and rs3 > mine and trend_score(m) >= 1:
            out.append({"sym": s, "price": round(m["price"], 2), "rs3": round(rs3, 1), "trend": trend_score(m)})
    return sorted(out, key=lambda x: -x["rs3"])[:3]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.getenv("TWS_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("TWS_PORT", "7496")))
    ap.add_argument("--out", default=str(Path.home() / "Desktop/portfolio-analysis.md"))
    ap.add_argument("--json-out", default="")
    ap.add_argument("--no-movers", action="store_true")
    args = ap.parse_args()

    positions, pos_source, prefs = load_positions(args.host, args.port)
    risk_json, _ = load_local_json("risk_settings.json")
    max_w = float((risk_json or {}).get("max_position_pct") or prefs.get("risk.maxPositionPercent") or 25)
    watch_json, _ = load_local_json("watchlist.json")
    watchlist = [s.upper() for s in (watch_json or prefs.get("watchlist") or [])]

    account = {}
    try:
        summary = fetch_account_summary_raw(args.host, args.port)
        account = next(iter(summary.values())) if summary else {}
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] account summary: {exc}", file=sys.stderr)

    holdings = sorted(positions)
    meta = {s: ticker_meta(s) for s in holdings}
    etfs = {s: sector_etf(meta[s]) for s in holdings}

    movers = []
    if not args.no_movers:
        try:
            from market_movers import MarketMoverScanner
            for attempt in range(3):
                try:
                    gainers, losers = MarketMoverScanner().scan()
                    break
                except Exception:  # noqa: BLE001
                    if attempt == 2:
                        raise
                    time.sleep(5 * (attempt + 1))
            movers = [(r.side, r.symbol, r.change_pct, r.opportunity, r.tag, r.price) for r in gainers + losers]
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] movers: {exc}", file=sys.stderr)

    held_etfs = set(etfs.values())
    leaders = [x for e, syms in SECTOR_LEADERS.items() if e not in held_etfs for x in syms]
    mover_syms = [m[1] for m in movers if m[4] in ("BUY", "NEAR", "WAIT", "EXTENDED") and m[0] == "gainers"]
    pool = [s for s in dict.fromkeys(watchlist + mover_syms + leaders) if s not in positions]
    held_leaders = [x for e in held_etfs for x in SECTOR_LEADERS.get(e, [])]
    universe = holdings + BENCHMARKS + sorted(set(etfs.values()) | set(SECTOR_LEADERS)) + pool + held_leaders
    bars = download(universe)
    bench = {k: v for k, v in bars.items()}

    # holdings
    rows = []
    for s in holdings:
        if s not in bars:
            continue
        pos = positions[s]
        m = metrics(bars[s], bench, etfs[s])
        qty, cost = float(pos["quantity"]), float(pos["avg_cost"])
        rows.append({"sym": s, "qty": qty, "cost": cost, "value": qty * m["price"],
                     "pnl": qty * (m["price"] - cost), "pnl_pct": (m["price"] / cost - 1) * 100,
                     "initial_stop": pos.get("initial_stop"), "m": m})
    port_value = sum(r["value"] for r in rows)
    net_liq = account.get("NetLiquidation") or float(prefs.get("risk.accountValue") or port_value)
    for r in rows:
        r["weight"] = r["value"] / net_liq * 100
        r["v"] = verdict(r["m"], r["weight"], max_w, r["pnl_pct"], r["initial_stop"])
        r["zone"] = add_zone(r["m"])
        r["stop"] = protective_stop(r["m"], r["initial_stop"])
    leverage = (account.get("GrossPositionValue") or port_value) / net_liq
    playbooks = []
    for r in rows:
        if leverage > 1.0 and r["v"]["action"] == "加仓":
            r["v"]["action"] = "持有"
            r["v"]["reasons"].append(f"技术面允许加仓，但账户总仓位 {leverage * 100:.0f}% 净值（融资中），先降杠杆再考虑")
        diag = diagnose(r, bench, etfs[r["sym"]], meta[r["sym"]]["earnings"])
        if r["pnl_pct"] < LOSS_PLAYBOOK_PCT:
            r["playbook"] = build_playbook(r, diag, net_liq, max_w, swap_candidates(r, etfs[r["sym"]], bench), leverage)
        elif r["pnl_pct"] >= GAIN_PLAYBOOK_PCT:
            r["playbook"] = build_gain_playbook(r, diag, net_liq)
        else:
            continue
        action = ACTION_FROM_PLAYBOOK[r["playbook"]["recommended"]]
        if action != r["v"]["action"]:
            r["v"]["reasons"].append(f"综合操作方案（{names_cn(r['playbook']['recommended'])}），结论由「{r['v']['action']}」调整为「{action}」")
            r["v"]["action"] = action
        playbooks.append(r["playbook"])
    json_out = args.json_out or str(Path(args.out).with_name(Path(args.out).stem.replace("portfolio-analysis", "portfolio-playbooks") + ".json"))
    Path(json_out).parent.mkdir(parents=True, exist_ok=True)
    Path(json_out).write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "disclaimer": "规则化技术分析辅助，非投资建议；不下单。",
        "net_liquidation": round(net_liq, 2),
        "gross_leverage": round(leverage, 3),
        "per_position_risk_budget_pct": PER_POSITION_RISK_PCT,
        "playbooks": playbooks,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"playbooks -> {json_out}")

    # candidates
    cands = []
    for s in pool:
        if s not in bars or len(bars[s]) < 30:
            continue
        try:
            m = metrics(bars[s], bench, "SPY")
        except Exception:  # noqa: BLE001
            continue
        if m["price"] < 3:
            continue
        src = "自选" if s in watchlist else "涨幅榜" if s in mover_syms else "板块龙头"
        cands.append({"sym": s, "src": src, "m": m, "score": candidate_score(m)})
    cands.sort(key=lambda c: c["score"], reverse=True)
    picks = [c for c in cands if trend_score(c["m"]) >= 1 and rs_score(c["m"]) > 0][:8]
    for c in picks:
        c["meta"] = ticker_meta(c["sym"])

    write_report(args.out, pos_source, account, net_liq, port_value, max_w, rows, meta, etfs, bench,
                 picks, cands, movers, watchlist)
    print(f"report -> {args.out}")


def write_report(out, pos_source, account, net_liq, port_value, max_w, rows, meta, etfs, bench,
                 picks, cands, movers, watchlist):
    now = datetime.now()
    spy = bench["SPY"]["close"]
    qqq = bench["QQQ"]["close"]
    last_bar = bench["SPY"].index[-1].date()
    L = []
    w = L.append
    w(f"# 持仓分析报告（{now:%Y-%m-%d %H:%M} 本地时间）\n")
    w("> **免责声明**：本报告为规则化技术分析辅助，基于公开行情与固定规则自动计算，**不构成投资建议**；"
      "未下任何订单。行情可能延迟，盘中价格随时变化，请结合自身判断与风险承受能力决策。\n")
    w("## 数据来源\n")
    w(f"- 持仓：{pos_source}；初始止损来自 StockSignalMonitor Mac 应用偏好。")
    w(f"- 行情：Yahoo Finance 日线（约 2 年），最新一根为 {last_bar}（交易时段内为盘中实时/延迟价）。")
    w(f"- 账户：{'TWS 账户摘要（只读）' if account else '未取到 TWS 账户摘要，使用应用内配置账户规模'}；单票上限 {max_w:.0f}%（应用风控设置）。")
    w(f"- 自选列表：{', '.join(watchlist) or '—'}；当日涨跌榜：{'已扫描 ' + str(len(movers)) + ' 只' if movers else '未取到'}。\n")

    w("## 大盘背景\n")
    for name, c in (("SPY", spy), ("QQQ", qqq)):
        s50, s200 = c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
        w(f"- **{name}** {c.iloc[-1]:.2f}（今日 {pct(ret(c, 1))}，1M {pct(ret(c, 21))}，3M {pct(ret(c, 63))}，6M {pct(ret(c, 126))}）；"
          f"{'站上' if c.iloc[-1] > s50 else '跌破'} 50 日线 {s50:.2f}，{'站上' if c.iloc[-1] > s200 else '跌破'} 200 日线 {s200:.2f}。")
    w("")

    w("## 组合概览\n")
    if account:
        w(f"- 净清算值 ${account.get('NetLiquidation', 0):,.0f}；现金 ${account.get('TotalCashValue', 0):,.0f}；"
          f"可用资金 ${account.get('AvailableFunds', 0):,.0f}；持仓市值 ${port_value:,.0f}（{port_value / net_liq * 100:.0f}% 仓位）。")
    else:
        w(f"- 持仓市值 ${port_value:,.0f}；按账户规模 ${net_liq:,.0f} 计仓位 {port_value / net_liq * 100:.0f}%。")
    total_pnl = sum(r["pnl"] for r in rows)
    w(f"- 浮动盈亏合计 ${total_pnl:,.0f}（{total_pnl / max(1, sum(r['qty'] * r['cost'] for r in rows)) * 100:+.1f}%）。\n")
    w("| 代码 | 名称 | 数量 | 成本 | 现价 | 市值 | 占净值 | 盈亏 | 板块/对标 ETF | 结论 |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---|---|")
    for r in sorted(rows, key=lambda x: -x["value"]):
        s = r["sym"]
        w(f"| {s} | {meta[s]['name']} | {r['qty']:.0f} | {r['cost']:.2f} | {r['m']['price']:.2f} | ${r['value']:,.0f} | "
          f"{r['weight']:.1f}% | {pct(r['pnl_pct'])} (${r['pnl']:,.0f}) | {meta[s]['industry'] or meta[s]['sector'] or '—'} / {etfs[s]} | **{r['v']['action']}** |")
    w("")

    # exposure
    by_etf: dict[str, float] = {}
    for r in rows:
        by_etf[etfs[r["sym"]]] = by_etf.get(etfs[r["sym"]], 0) + r["weight"]
    top = max(rows, key=lambda x: x["weight"]) if rows else None
    w("### 集中度与行业暴露\n")
    w("- 按对标 ETF 暴露：" + "；".join(f"{k} {v:.0f}%" for k, v in sorted(by_etf.items(), key=lambda x: -x[1])) + "。")
    if top:
        w(f"- 最大单票 {top['sym']} 占净值 {top['weight']:.0f}%（上限 {max_w:.0f}%）。")
    if len(rows) >= 2:
        rets = pd.DataFrame({r["sym"]: bench[r["sym"]]["close"].pct_change() for r in rows}).tail(63).dropna()
        if len(rets) > 20:
            corr = rets.corr()
            pairs = [(a, b, corr.loc[a, b]) for i, a in enumerate(corr) for b in list(corr)[i + 1:]]
            w("- 近 3 个月日收益相关系数：" + "；".join(f"{a}-{b} {c:.2f}" for a, b, c in sorted(pairs, key=lambda x: -x[2])) + "。")
    w("")

    w("## 逐只分析\n")
    for r in sorted(rows, key=lambda x: -x["value"]):
        s, m, v = r["sym"], r["m"], r["v"]
        lv = m["levels"]
        z = r["zone"]
        stop, stop_label = r["stop"]
        e = meta[s]["earnings"]
        w(f"### {s} — {meta[s]['name']}：**{v['action']}**（置信度 {v['confidence']}）\n")
        w(f"- 成本 {r['cost']:.2f} → 现价 {m['price']:.2f}，盈亏 {pct(r['pnl_pct'])}（${r['pnl']:,.0f}），占净值 {r['weight']:.1f}%。")
        w(f"- 趋势：20 日线 {f(m['sma'][20])} / 50 日线 {f(m['sma'][50])} / 200 日线 {f(m['sma'][200])}；"
          f"现价{'高于' if m['sma'][20] and m['price'] > m['sma'][20] else '低于'} 20 日线，"
          f"50 日线{'上行' if m['sma50_rising'] else '下行' if m['sma50_rising'] is False else '—'}；趋势分 {v['trend']}（-5~+5）。")
        cp = channel_pos(m)
        w(f"- 10 日通道：上沿 {m['ch_hi']:.2f} / 下沿 {m['ch_lo']:.2f}，现价位于通道 {f(cp, '{:.0f}%')}；信号状态 {lv['status']}；ATR14 {m['atr']:.2f}（{m['atr_pct']:.1f}%），"
          f"ATR 保护线（现价−2×ATR）{m['price'] - 2 * m['atr']:.2f}；RSI14 {lv['rsi14']:.0f}。")
        rs = m["rs"]
        w(f"- 相对强弱（个股 / vs SPY / vs {etfs[s]}）：1M {pct(rs['1m']['abs'])} / {pct(rs['1m']['vs_spy'])} / {pct(rs['1m']['vs_sector'])}；"
          f"3M {pct(rs['3m']['abs'])} / {pct(rs['3m']['vs_spy'])} / {pct(rs['3m']['vs_sector'])}；"
          f"6M {pct(rs['6m']['abs'])} / {pct(rs['6m']['vs_spy'])} / {pct(rs['6m']['vs_sector'])}。")
        w(f"- 量价：近 5 日均量 / 20 日均量 {f(m['vol5_vs20'], '{:.2f}x')}；20 日上涨日/下跌日成交量比 {f(m['updown_vol'], '{:.2f}')}；"
          f"近 3 月年化波动 {f(m['vol_ann'], '{:.0f}%')}。")
        w(f"- 52 周：高 {m['hi52']:.2f}（距 {pct(m['from_hi_pct'])}）/ 低 {m['lo52']:.2f}（距 {pct(m['from_lo_pct'])}）；历史数据自 {m['first_date']}（{m['history_days']} 日）。")
        w(f"- 财报：{e if e else '未取到'}" + (f"（{(e - now.date()).days} 天后）" if e and e >= now.date() else "") + "。")
        w(f"- **判断依据**：{'；'.join(v['reasons'])}。")
        if r.get("playbook"):
            pb = r["playbook"]
            w(f"- **操作**：推荐「{names_cn(pb['recommended'])}」，备选「{names_cn(pb['fallback'])}」，详见下方「操作方案」。")
        elif v["action"] == "加仓":
            w(f"- **触发条件 / 加仓区间**：{z[2]}，{z[0]:.2f}–{z[1]:.2f}，且不跌破 {stop:.2f}；放量突破 10 日上沿 {m['ch_hi']:.2f} 可小幅追加。")
        elif v["action"] == "持有":
            w(f"- **触发条件**：若{z[2]}至 {z[0]:.2f}–{z[1]:.2f} 企稳且相对强弱转正可考虑加仓；收盘跌破 {stop:.2f} 转为减仓。")
        elif v["action"] == "减仓":
            w(f"- **触发条件**：反弹至 20 日线 {f(m['sma'][20])} 附近分批减仓；收盘跌破 {stop:.2f} 进一步减至观察仓或清仓。")
        else:
            w(f"- **触发条件**：收盘仍低于 {stop:.2f} / 10 日下沿则执行止损；重新站回 20 日线 {f(m['sma'][20])} 才解除观察。")
        w(f"- **止损位**：{stop:.2f}（{stop_label}，距现价 {(stop / m['price'] - 1) * 100:+.1f}%）"
          + (f"；应用内初始止损 {r['initial_stop']:.2f}" if r["initial_stop"] else "") + "。")
        risks = list(v["risks"])
        if e and 0 <= (e - now.date()).days <= 21:
            risks.append(f"财报 {e} 临近，跳空风险")
        w(f"- **主要风险**：{'；'.join(risks) or '常规市场风险'}。\n")

    pbs = [r for r in sorted(rows, key=lambda x: x["pnl_pct"]) if r.get("playbook")]
    if pbs:
        w("## 操作方案（亏损 / 大幅浮盈持仓）\n")
        w(f"风险预算口径：每票最大可承受亏损 = 净值 × {PER_POSITION_RISK_PCT:.0f}% = ${net_liq * PER_POSITION_RISK_PCT / 100:,.0f}；"
          "「到止损风险」= (现价 − 止损) × 股数；「跳空最坏」再多算 1×ATR 滑点。\n")
    for r in pbs:
        pb = r["playbook"]
        d = pb["diagnosis"]
        names = {o["id"]: o["name"] for o in pb["options"]}
        w(f"### {pb['symbol']}（{pct(pb['pnl_pct'])}，${pb['pnl']:,.0f}）→ 推荐：**{names[pb['recommended']]}**\n")
        if pb["kind"] == "loss":
            b = d["breaks"]
            yn = lambda v: "—" if v is None else ("是" if v else "否")  # noqa: E731
            w(f"**诊断**：亏损归因 **{d['cause']}**（3M 个股 vs SPY {pct(d['stock_vs_spy_3m'])}，vs 板块 {pct(d['stock_vs_sector_3m'])}，"
              f"板块 vs SPY {pct(d['sector_vs_spy_3m'])}，SPY 1M {pct(d['spy_1m'])}）；趋势 **{d['trend_state']}**"
              f"（跌破 50 日线：{yn(b['below_50ma'])}；跌破 200 日线：{yn(b['below_200ma'])}；跌破前低 {f(d['prior_low'])}：{yn(b['below_prior_low'])}；跌破 10 日下沿：{yn(b['below_channel_low'])}）；"
              f"相对强弱{'正在企稳' if d['rs_improving'] else '未企稳'}；财报 {d['earnings'] or '未取到'}"
              + (f"（{d['days_to_earnings']} 天后，**临近**）" if d["earnings_soon"] else "") + "。\n")
            w(f"止损基准 {pb['stop']:.2f}（{pb['stop_basis']}），ATR14 {pb['atr14']:.2f}；当前到止损风险 ${pb['risk_to_stop_now']:,.0f}"
              f"（占每票预算 {pb['risk_to_stop_now'] / max(1, pb['risk_budget_per_position']) * 100:.0f}%）。\n")
            w("| 方案 | 触发条件 / 价位与数量 | 止损时总盈亏 | 从现价起最大再亏 | 跳空最坏 | 占风险预算 | 优点 | 缺点 |")
            w("|---|---|---:|---:|---:|---:|---|---|")
            for o in pb["options"]:
                extra = ""
                if o["id"] == "scale_in":
                    extra = (f"<br>补后 {o['new_qty']:.0f} 股，新成本 {o['new_avg_cost']:.2f}，风险上限 ${o['max_risk_cap']:,.0f}"
                             if o["eligible"] else f"<br>**不适用**：{o['ineligible_reason']}")
                if o["id"] == "stop_exit":
                    extra = f"<br>现价离场盈亏 ${o['now_exit_pnl']:,.0f}"
                if o["id"] == "bounce_reduce" and o["orders"]:
                    extra = f"<br>两档成交盈亏 ${o['pnl_if_filled']:,.0f}"
                orders = "；".join(f"{x['side']} {x['qty']:.0f}@{x['price']:.2f}" for x in o["orders"] if x["qty"])
                mark = " ⭐" if o["id"] == pb["recommended"] else ""
                w(f"| {o['name']}{mark} | {o['trigger']}<br>`{orders or '—'}`{extra} | ${o['pnl_at_stop']:,.0f} | "
                  f"${o['additional_risk_from_now']:,.0f} | ${o['gap_worst_case']:,.0f} | {o['risk_budget_pct']:.0f}% | {o['pros']} | {o['cons']} |")
        else:
            w(f"**诊断**：浮盈 {pct(pb['pnl_pct'])}，财报 {d['earnings'] or '未取到'}。\n")
            w("| 方案 | 触发条件 | 优点 | 缺点 |")
            w("|---|---|---|---|")
            for o in pb["options"]:
                w(f"| {o['name']}{' ⭐' if o['id'] == pb['recommended'] else ''} | {o['trigger']} | {o['pros']} | {o['cons']} |")
        w(f"\n**推荐理由**：{pb['why']}。  \n**切换条件**：{pb['switch_condition']}（备选：{names[pb['fallback']]}）。\n")

    w("## 组合层面建议\n")
    gross = account.get("GrossPositionValue") or port_value
    if gross > net_liq:
        w(f"- **杠杆优先**：持仓市值 ${gross:,.0f} = 净值的 {gross / net_liq * 100:.0f}%（现金 ${account.get('TotalCashValue', 0):,.0f}，即融资借款）。"
          f"降到 100% 需卖出约 ${gross - net_liq:,.0f}；在杠杆回到 100% 以内前，所有「加仓/补仓」方案都不执行。上面各票的减仓方案合计可完成大部分降杠杆。")
    semis = [r for r in rows if etfs[r["sym"]] == "SMH"]
    if semis:
        semi = sum(r["weight"] for r in semis)
        w(f"- 半导体暴露 {semi:.0f}% 净值（{'、'.join(r['sym'] for r in semis)}），属同一周期、相关度较高，是组合最大的单一风险源；新增资金优先放到非半导体板块。")
    w(f"- 应用内单票上限为 {max_w:.0f}%，对集中持仓偏宽；建议以「单票到止损亏损 ≤ 净值 {PER_POSITION_RISK_PCT:.0f}%（${net_liq * PER_POSITION_RISK_PCT / 100:,.0f}）」反推股数，单票市值 ≤ 净值 30–40%。")
    risk_total = sum(max(0.0, (r["m"]["price"] - r["stop"][0]) * r["qty"]) for r in rows)
    w(f"- 若全部触及上述止损位，组合从现价再回撤约 ${risk_total:,.0f}（{risk_total / net_liq * 100:.1f}% 净值）；建议组合总风险控制在净值 6–8% 以内。\n")

    w("## 建仓候选\n")
    w("筛选池 = 自选列表 + 当日涨幅榜（已过滤跌破卖点者）+ 与持仓互补的板块龙头；要求趋势分 ≥1 且相对 SPY 领先，"
      "按 趋势×1.5 + 相对强弱/3 + 回踩位置 + 量价 打分排序。\n")
    w("| 排名 | 代码 | 来源 | 现价 | 趋势分 | 3M vs SPY | 距20日线(ATR) | 10日通道位置 | 入场区间 | 止损 | 评分 |")
    w("|---:|---|---|---:|---:|---:|---:|---:|---|---:|---:|")
    for i, c in enumerate(picks, 1):
        m = c["m"]
        z = add_zone(m)
        stop, _ = protective_stop(m, None)
        w(f"| {i} | {c['sym']} ({c['meta']['name']}) | {c['src']} | {m['price']:.2f} | {trend_score(m)} | {pct(m['rs']['3m']['vs_spy'])} | "
          f"{f(m['ext20_atr'], '{:+.1f}')} | {f(channel_pos(m), '{:.0f}%')} | {z[0]:.2f}–{z[1]:.2f}（{z[2]}） | {min(stop, z[0] - m['atr']):.2f} | {c['score']:.1f} |")
    w("")
    for c in picks:
        m = c["m"]
        e = c["meta"]["earnings"]
        w(f"- **{c['sym']}**：{c['meta']['industry'] or c['meta']['sector'] or '—'}；1M/3M/6M vs SPY {pct(m['rs']['1m']['vs_spy'])} / {pct(m['rs']['3m']['vs_spy'])} / {pct(m['rs']['6m']['vs_spy'])}；"
          f"距 52 周高 {pct(m['from_hi_pct'])}；年化波动 {f(m['vol_ann'], '{:.0f}%')}；财报 {e or '未取到'}。")
    rejected = [c for c in cands if c["src"] == "自选" and c not in picks]
    if rejected:
        w("\n自选中未入选：" + "；".join(f"{c['sym']}（趋势分 {trend_score(c['m'])}，3M vs SPY {pct(c['m']['rs']['3m']['vs_spy'])}）" for c in rejected) + "。")
    w("\n---\n*脚本：`scripts/portfolio_review.py`，可复跑。规则化技术分析辅助，非投资建议；不下单。*")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
