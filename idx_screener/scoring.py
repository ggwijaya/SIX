from __future__ import annotations

import math
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple


MIN_AVERAGE_TRADED_VALUE = 500_000_000


def finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def percentile_ranks(values: Iterable[float]) -> Dict[float, float]:
    unique = sorted(set(values))
    if not unique:
        return {}
    if len(unique) == 1:
        return {unique[0]: 1.0}
    return {value: index / (len(unique) - 1) for index, value in enumerate(unique)}


def eligible(stock: Dict[str, Any]) -> bool:
    symbol = str(stock.get("symbol") or "").upper()
    instrument_type = str(stock.get("instrumentType") or "").lower()
    price = finite_number(stock.get("price"))
    avg_value = finite_number(stock.get("averageTradedValue"))
    if not symbol or symbol.endswith(("-W", "-R")):
        return False
    if instrument_type and instrument_type not in {"stock", "common_stock"}:
        return False
    return bool(price and price > 0 and avg_value and avg_value >= MIN_AVERAGE_TRADED_VALUE)


def score_stock(stock: Dict[str, Any], liquidity_percentile: float) -> Dict[str, Any]:
    price = finite_number(stock.get("price"))
    relative_volume = finite_number(stock.get("relativeVolume"))
    rsi = finite_number(stock.get("rsi"))
    macd = finite_number(stock.get("macd"))
    macd_signal = finite_number(stock.get("macdSignal"))
    ema20 = finite_number(stock.get("ema20"))
    ema50 = finite_number(stock.get("ema50"))
    ema200 = finite_number(stock.get("ema200"))
    return1m = finite_number(stock.get("return1m"))
    return3m = finite_number(stock.get("return3m"))
    volatility = finite_number(stock.get("volatility"))

    liquidity = liquidity_percentile * 25
    if relative_volume is not None:
        liquidity += clamp(relative_volume / 2, 0, 1) * 10
    else:
        liquidity += 4

    trend = 0.0
    positives: List[str] = []
    risks: List[str] = []
    for ema, points, label in [
        (ema20, 7.5, "Above EMA20"),
        (ema50, 7.5, "Above EMA50"),
        (ema200, 7.5, "Above EMA200"),
    ]:
        if price is not None and ema is not None and price > ema:
            trend += points
            positives.append(label)
    if ema20 is not None and ema50 is not None and ema20 > ema50:
        trend += 7.5
        positives.append("EMA20 leads EMA50")

    momentum = 0.0
    if rsi is not None:
        if 50 <= rsi <= 65:
            momentum += 7
            positives.append("Healthy RSI momentum")
        elif 40 <= rsi < 50 or 65 < rsi <= 72:
            momentum += 4
        elif rsi > 75:
            risks.append("RSI is overbought")
        elif rsi < 35:
            risks.append("RSI is weak")
    if macd is not None and macd_signal is not None and macd > macd_signal:
        momentum += 6
        positives.append("MACD is bullish")
    if return1m is not None:
        momentum += clamp((return1m + 5) / 20, 0, 1) * 5
        if return1m > 0:
            positives.append("Positive 1-month return")
    if return3m is not None:
        momentum += clamp((return3m + 10) / 40, 0, 1) * 7
        if return3m > 0:
            positives.append("Positive 3-month return")

    if volatility is None:
        risk_score = 4.0
    elif 1 <= volatility <= 4:
        risk_score = 10.0
    elif volatility < 1:
        risk_score = 7.0
    elif volatility <= 6:
        risk_score = 6.0
        risks.append("Elevated daily volatility")
    elif volatility <= 9:
        risk_score = 3.0
        risks.append("High daily volatility")
    else:
        risk_score = 0.0
        risks.append("Extreme daily volatility")

    if relative_volume is not None and relative_volume >= 1.2:
        positives.append("Above-average participation")
    if price is not None and ema200 is not None and price < ema200:
        risks.append("Price is below EMA200")
    if return3m is not None and return3m < -10:
        risks.append("Negative 3-month trend")

    breakdown = {
        "liquidity": round(clamp(liquidity, 0, 35), 1),
        "trend": round(clamp(trend, 0, 30), 1),
        "momentum": round(clamp(momentum, 0, 25), 1),
        "risk": round(clamp(risk_score, 0, 10), 1),
    }
    total = round(clamp(sum(breakdown.values()), 0, 100), 1)
    signal = "Strong" if total >= 75 else "Constructive" if total >= 60 else "Mixed"
    return {
        **stock,
        "score": total,
        "signal": signal,
        "scoreBreakdown": breakdown,
        "positiveSignals": positives[:6],
        "riskFlags": risks[:5],
    }


def rank_stocks(raw_stocks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    prepared: List[Dict[str, Any]] = []
    for raw in raw_stocks:
        stock = dict(raw)
        price = finite_number(stock.get("price"))
        avg_volume = finite_number(stock.get("averageVolume10d"))
        stock["averageTradedValue"] = (
            price * avg_volume if price is not None and avg_volume is not None else None
        )
        if eligible(stock):
            prepared.append(stock)

    values = [
        finite_number(stock["averageTradedValue"])
        for stock in prepared
        if finite_number(stock["averageTradedValue"]) is not None
    ]
    ranks = percentile_ranks(value for value in values if value is not None)
    scored = [
        score_stock(stock, ranks.get(float(stock["averageTradedValue"]), 0.0))
        for stock in prepared
    ]
    scored.sort(
        key=lambda stock: (
            -stock["score"],
            -float(stock["averageTradedValue"]),
            stock["symbol"],
        )
    )
    for index, stock in enumerate(scored, start=1):
        stock["rank"] = index

    return scored, {
        "universe": len(raw_stocks),
        "qualifying": len(scored),
        "excluded": len(raw_stocks) - len(scored),
    }


def median_score(stocks: List[Dict[str, Any]]) -> Optional[float]:
    return round(median([stock["score"] for stock in stocks]), 1) if stocks else None
