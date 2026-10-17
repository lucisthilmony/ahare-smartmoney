# -*- coding: utf-8 -*-
"""影子账户的纯账务层。

本模块不决定买什么，只把影子执行器已经决定的交易转换为可核对的
现金、持仓、费用和净值。函数尽量保持无外部数据依赖，便于单元测试。
"""
from __future__ import annotations

import math


STATE_VERSION = 2


def _new_account(initial_capital):
    capital = float(initial_capital)
    return {
        "cash": capital,
        "base": None,
        "last_equity": capital,
        "peak_equity": capital,
    }


def ensure_state(state, initial_capital):
    """把旧版仅有持仓队列的状态原位迁移到 v2 账本结构。"""
    state = state if isinstance(state, dict) else {}
    for stream in ("A", "C", "R"):
        s = state.setdefault(stream, {})
        s.setdefault("open", [])
        s.setdefault("pending_entry", None)
        s.setdefault("pending_exit", [])
        s.setdefault("cum_r", 0.0)
        s.setdefault("cum_actual_r", 0.0)
        for pos in s["open"]:
            # 旧状态没有股数，不能凭空回填成交。继续管理其规则出场，
            # 但不把它混入真实净值；当前线上状态为空，因此正常升级无损。
            if "shares" not in pos:
                pos["shares"] = 0
                pos["entry_shares"] = 0
                pos["accounted"] = False
    accounts = state.setdefault("accounts", {})
    for name in ("base", "A", "C", "R"):
        acc = accounts.setdefault(name, _new_account(initial_capital))
        acc.setdefault("cash", float(initial_capital))
        acc.setdefault("base", None)
        acc.setdefault("last_equity", float(initial_capital))
        acc.setdefault("peak_equity", float(initial_capital))
    state.setdefault("accounting_start", None)
    state["state_version"] = STATE_VERSION
    return state


def validate_state(state):
    """关键账务字段缺失或现金/股数异常时失败关闭。"""
    errors = []
    for stream in ("A", "C", "R"):
        s = state.get(stream) or {}
        positions = s.get("open") or []
        codes = [p.get("code") for p in positions]
        if len(codes) != len(set(codes)):
            errors.append(f"{stream}流存在重复持仓代码")
        pending = s.get("pending_entry")
        if pending and pending.get("code") in set(codes):
            errors.append(f"{stream}流待入场与现有持仓重复")
        if pending:
            for field in ("code", "board", "stop_price", "decide_date", "cap"):
                if pending.get(field) is None:
                    errors.append(f"{stream}流待入场缺少{field}")
        for pos in positions:
            shares = pos.get("shares", 0)
            if not isinstance(shares, int) or shares < 0:
                errors.append(f"{stream}流{pos.get('code')}股数异常")
            if pos.get("accounted", True):
                for field in ("entry", "stop", "target", "entry_date", "cost_basis", "actual_risk_amt"):
                    if pos.get(field) is None:
                        errors.append(f"{stream}流{pos.get('code')}缺少{field}")
    for name in ("base", "A", "C", "R"):
        account = (state.get("accounts") or {}).get(name) or {}
        cash = account.get("cash")
        if cash is None or not math.isfinite(float(cash)) or float(cash) < -0.01:
            errors.append(f"{name}账户现金异常")
        base = account.get("base") or {}
        if int(base.get("shares", 0)) < 0:
            errors.append(f"{name}账户底仓股数异常")
    if errors:
        raise ValueError("影子账务一致性检查失败：" + "；".join(errors))
    return True


def stock_fee(market_value, side, date, comm_rate, comm_min, stamp_rate):
    market_value = max(0.0, float(market_value))
    fee = max(float(comm_min), market_value * float(comm_rate)) if market_value else 0.0
    if side == "sell" and market_value:
        fee += market_value * float(stamp_rate(date))
    return fee


def mark_satellite(positions):
    return sum(
        float(p.get("shares", 0)) * float(p.get("last_px", p.get("entry", 0)) or 0)
        for p in positions
        if p.get("accounted", True)
    )


def mark_account(account, positions=()):
    base = account.get("base") or {}
    base_mv = float(base.get("shares", 0)) * float(base.get("last_px", 0) or 0)
    sat_mv = mark_satellite(positions)
    equity = float(account.get("cash", 0)) + base_mv + sat_mv
    return {"equity": equity, "cash": float(account.get("cash", 0)),
            "base_mv": base_mv, "sat_mv": sat_mv}


def size_satellite(account, positions, candidate, entry_raw, stop, cap_pct,
                   risk_pct, boards, exposure_20cm_cap, theme_cap,
                   comm_rate, comm_min):
    """按组合回测同一组上限计算可买股数，返回整手股数。"""
    entry_raw, stop = float(entry_raw), float(stop)
    risk = entry_raw - stop
    if risk <= 0 or entry_raw <= 0 or float(cap_pct or 0) <= 0:
        return 0
    board = candidate.get("board", "main")
    rule = boards[board]
    equity_ref = max(0.0, float(account.get("last_equity", 0)))
    sat_mv = mark_satellite(positions)
    cm20_mv = sum(
        float(p.get("shares", 0)) * float(p.get("last_px", p.get("entry", 0)) or 0)
        for p in positions if p.get("board") in ("chinext", "star") and p.get("accounted", True)
    )
    industry = candidate.get("ind") or candidate.get("sec") or ""
    industry_mv = sum(
        float(p.get("shares", 0)) * float(p.get("last_px", p.get("entry", 0)) or 0)
        for p in positions
        if (p.get("ind") or "") == industry and p.get("accounted", True)
    )
    limits = [
        equity_ref * float(risk_pct) / risk * entry_raw,
        equity_ref * float(rule["cap"]),
        equity_ref * float(cap_pct) / 100.0 - sat_mv,
        max(0.0, float(account.get("cash", 0))),
        equity_ref * float(theme_cap) - industry_mv,
    ]
    if board in ("chinext", "star"):
        limits.append(equity_ref * float(exposure_20cm_cap) - cm20_mv)
    max_value = max(0.0, min(limits))
    lot = int(rule["lot"])
    shares = int(max_value / entry_raw)
    shares = shares if board == "star" and shares >= lot else shares // lot * lot
    slip = float(rule.get("slip", 0))
    while shares > 0:
        buy_value = shares * entry_raw * (1 + slip)
        if buy_value + stock_fee(buy_value, "buy", "", comm_rate, comm_min, lambda _d: 0) <= account["cash"]:
            break
        shares = shares - 1 if board == "star" else shares - lot
    return max(0, shares)


def buy_satellite(account, positions, candidate, entry_raw, stop, date, cap_pct,
                  risk_pct, boards, exposure_20cm_cap, theme_cap,
                  comm_rate, comm_min):
    board = candidate.get("board", "main")
    shares = size_satellite(
        account, positions, candidate, entry_raw, stop, cap_pct, risk_pct,
        boards, exposure_20cm_cap, theme_cap, comm_rate, comm_min,
    )
    if shares <= 0:
        return None
    slip = float(boards[board].get("slip", 0))
    buy_px = float(entry_raw) * (1 + slip)
    market_value = shares * buy_px
    fee = stock_fee(market_value, "buy", date, comm_rate, comm_min, lambda _d: 0)
    account["cash"] -= market_value + fee
    risk_amount = max(0.0, float(account.get("last_equity", 0)) * float(risk_pct))
    return {
        "shares": shares,
        "entry_shares": shares,
        "buy_px": buy_px,
        "last_px": float(entry_raw),
        "cost_basis": market_value + fee,
        "sale_proceeds": 0.0,
        "actual_risk_amt": risk_amount,
        "accounted": True,
    }


def sell_satellite(account, position, quantity, raw_px, date, boards,
                   comm_rate, comm_min, stamp_rate):
    """按滑点和全成本卖出；返回净流入。旧版未记账持仓返回 0。"""
    if not position.get("accounted", True):
        return 0.0
    held = int(position.get("shares", 0))
    quantity = max(0, min(int(quantity), held))
    if quantity <= 0:
        return 0.0
    board = position.get("board", "main")
    slip = float(boards[board].get("slip", 0))
    sell_px = float(raw_px) * (1 - slip)
    market_value = quantity * sell_px
    fee = stock_fee(market_value, "sell", date, comm_rate, comm_min, stamp_rate)
    proceeds = market_value - fee
    account["cash"] += proceeds
    position["shares"] = held - quantity
    position["last_px"] = float(raw_px)
    position["sale_proceeds"] = float(position.get("sale_proceeds", 0)) + proceeds
    position["last_sell_px"] = sell_px
    return proceeds


def rebalance_base(account, target, date, price_lookup, etf_cost, rebalance_band):
    """将单个账户的底仓调到目标权重；返回本次成交列表。"""
    trades = []
    target = target or {}
    target_code = target.get("etf")
    target_weight = max(0.0, float(target.get("weight") or 0) / 100.0)
    holding = account.get("base")

    if holding:
        px = price_lookup(holding["code"], date)
        if px:
            holding["last_px"] = float(px)

    # 换标的时先卖旧底仓。
    if holding and (not target_code or holding.get("code") != target_code):
        px = float(holding.get("last_px") or 0)
        if px <= 0 and holding.get("shares", 0) > 0:
            return trades  # 旧标的没有可核对价格时绝不凭空清掉持仓
        if px > 0 and holding.get("shares", 0) > 0:
            value = int(holding["shares"]) * px
            account["cash"] += value * (1 - float(etf_cost))
            trades.append({"date": date, "side": "sell", "code": holding["code"],
                           "shares": int(holding["shares"]), "price": px,
                           "fee": value * float(etf_cost)})
        account["base"] = None
        holding = None

    if not target_code or target_weight <= 0:
        if holding and holding.get("shares", 0) > 0:
            px = float(holding.get("last_px") or 0)
            if px > 0:
                value = int(holding["shares"]) * px
                account["cash"] += value * (1 - float(etf_cost))
                trades.append({"date": date, "side": "sell", "code": holding["code"],
                               "shares": int(holding["shares"]), "price": px,
                               "fee": value * float(etf_cost)})
                account["base"] = None
        return trades

    px = price_lookup(target_code, date)
    if not px:
        return trades
    px = float(px)
    if account.get("base") is None:
        account["base"] = {"code": target_code, "name": target.get("name", ""),
                           "shares": 0, "last_px": px}
    holding = account["base"]
    holding["last_px"] = px
    current_shares = int(holding.get("shares", 0))
    current_value = current_shares * px
    equity_ref = max(0.0, float(account.get("last_equity", 0)))
    target_value = equity_ref * target_weight
    if current_shares and abs(target_value - current_value) <= float(rebalance_band) * equity_ref:
        return trades
    target_shares = max(0, int(math.floor(target_value / px / 100.0) * 100))
    delta = target_shares - current_shares
    if delta > 0:
        affordable = int(math.floor(account["cash"] / (px * (1 + float(etf_cost))) / 100.0) * 100)
        delta = min(delta, affordable)
        if delta > 0:
            value = delta * px
            account["cash"] -= value * (1 + float(etf_cost))
            holding["shares"] = current_shares + delta
            trades.append({"date": date, "side": "buy", "code": target_code,
                           "shares": delta, "price": px, "fee": value * float(etf_cost)})
    elif delta < 0:
        quantity = -delta
        value = quantity * px
        account["cash"] += value * (1 - float(etf_cost))
        holding["shares"] = current_shares - quantity
        trades.append({"date": date, "side": "sell", "code": target_code,
                       "shares": quantity, "price": px, "fee": value * float(etf_cost)})
    return trades


def snapshot_account(account, positions, initial_capital):
    snap = mark_account(account, positions)
    equity = snap["equity"]
    previous = float(account.get("last_equity", initial_capital))
    peak = max(float(account.get("peak_equity", initial_capital)), equity)
    snap["daily_return"] = equity / previous - 1 if previous else 0.0
    snap["nav"] = equity / float(initial_capital)
    snap["drawdown"] = equity / peak - 1 if peak else 0.0
    snap["base_weight"] = snap["base_mv"] / equity if equity else 0.0
    snap["sat_weight"] = snap["sat_mv"] / equity if equity else 0.0
    account["last_equity"] = equity
    account["peak_equity"] = peak
    return snap
