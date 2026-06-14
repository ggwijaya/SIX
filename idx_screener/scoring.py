from __future__ import annotations

import math
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple


MIN_AVERAGE_TRADED_VALUE = 500_000_000
MIN_SECTOR_SIZE = 5
MODEL = {
    "name": "HexInc Conservative Signal Model",
    "version": "2.0",
    "label": "Conservative v2",
    "falseSignalDefinition": (
        "A new Strong signal whose 20-session adjusted return, after 0.5% "
        "costs, does not beat the matching IDX Composite return."
    ),
}


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


def _series(stock: Dict[str, Any], key: str) -> List[Optional[float]]:
    return [
        finite_number(stock.get(key)),
        finite_number(stock.get(f"{key}Prev1")),
        finite_number(stock.get(f"{key}Prev2")),
    ]


def _complete(values: Iterable[Optional[float]]) -> bool:
    return all(value is not None for value in values)


def _aligned(
    prices: List[Optional[float]],
    ema20: List[Optional[float]],
    ema50: List[Optional[float]],
    ema200: List[Optional[float]],
    index: int,
) -> bool:
    values = [prices[index], ema20[index], ema50[index], ema200[index]]
    return bool(
        _complete(values)
        and values[0] > values[1] > values[2] > values[3]  # type: ignore[operator]
    )


def _rising(values: List[Optional[float]]) -> bool:
    return bool(
        _complete(values)
        and values[0] > values[1] > values[2]  # type: ignore[operator]
    )


def build_sector_context(
    stocks: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for stock in stocks:
        grouped.setdefault(str(stock.get("sector") or "Unclassified"), []).append(
            stock
        )

    result: Dict[str, Dict[str, Any]] = {}
    for sector, members in grouped.items():
        returns1m = [
            value
            for value in (finite_number(item.get("return1m")) for item in members)
            if value is not None
        ]
        returns3m = [
            value
            for value in (finite_number(item.get("return3m")) for item in members)
            if value is not None
        ]
        eligible = (
            len(members) >= MIN_SECTOR_SIZE
            and len(returns1m) >= MIN_SECTOR_SIZE
            and len(returns3m) >= MIN_SECTOR_SIZE
        )
        result[sector] = {
            "sector": sector,
            "count": len(members),
            "eligible": eligible,
            "medianReturn1m": round(median(returns1m), 4) if returns1m else None,
            "medianReturn3m": round(median(returns3m), 4) if returns3m else None,
        }
    return result


def score_stock(
    stock: Dict[str, Any],
    liquidity_percentile: float,
    market_context: Optional[Dict[str, Any]] = None,
    sector_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    price = finite_number(stock.get("price"))
    relative_volume = finite_number(stock.get("relativeVolume"))
    rsi = finite_number(stock.get("rsi"))
    return1m = finite_number(stock.get("return1m"))
    return3m = finite_number(stock.get("return3m"))
    cmf = finite_number(stock.get("cmf"))
    atr = finite_number(stock.get("atr"))
    change = finite_number(stock.get("change"))
    atr_percent = (
        atr / price * 100 if atr is not None and price is not None and price > 0 else None
    )

    prices = _series(stock, "price")
    ema20 = _series(stock, "ema20")
    ema50 = _series(stock, "ema50")
    ema200 = _series(stock, "ema200")
    macd = _series(stock, "macd")
    macd_signal = _series(stock, "macdSignal")
    alignment = [
        _aligned(prices, ema20, ema50, ema200, index) for index in range(3)
    ]
    persistence = sum(alignment)
    slopes = {
        "ema20": _rising(ema20),
        "ema50": _rising(ema50),
        "ema200": _rising(ema200),
    }

    positives: List[str] = []
    risks: List[str] = []
    deductions: List[Dict[str, Any]] = []

    liquidity = liquidity_percentile * 14
    if cmf is not None and cmf > 0:
        liquidity += 3
        positives.append("Positive Chaikin Money Flow")
    volume_confirmation_available = (
        cmf is not None and relative_volume is not None and change is not None
    )
    volume_confirmed = bool(
        volume_confirmation_available
        and cmf > 0
        and (relative_volume >= 1 or change > 0)
    )
    if volume_confirmed:
        liquidity += 3
        positives.append("Directional volume confirmation")

    trend = 12.0 if alignment[0] else 0.0
    if alignment[0]:
        positives.append("Bullish EMA alignment")
    for key, is_rising in slopes.items():
        if is_rising:
            trend += 3
            positives.append(f"{key.upper()} is rising")
    if persistence == 3:
        trend += 9
        positives.append("Trend persisted for 3 sessions")
    elif persistence == 2:
        trend += 4

    momentum = 0.0
    if rsi is not None:
        if 50 <= rsi <= 65:
            momentum += 6
            positives.append("Healthy RSI momentum")
        elif 45 <= rsi < 50 or 65 < rsi <= 70:
            momentum += 3

    histogram = [
        left - right
        if left is not None and right is not None
        else None
        for left, right in zip(macd, macd_signal)
    ]
    if histogram[0] is not None and histogram[0] > 0:
        momentum += 5
        positives.append("MACD is bullish")
    if _rising(histogram):
        momentum += 5
        positives.append("MACD histogram is improving")
    if return1m is not None:
        if return1m > 0:
            momentum += 2
            positives.append("Positive 1-month return")
    if return3m is not None:
        if return3m > 0:
            momentum += 2
            positives.append("Positive 3-month return")

    market_context = market_context or {}
    market_available = bool(market_context.get("available"))
    market_bullish = bool(market_context.get("bullish"))
    market_return1m = finite_number(market_context.get("return1m"))
    market_return3m = finite_number(market_context.get("return3m"))
    market_excess1m = (
        return1m - market_return1m
        if return1m is not None and market_return1m is not None
        else None
    )
    market_excess3m = (
        return3m - market_return3m
        if return3m is not None and market_return3m is not None
        else None
    )

    sector_context = sector_context or {}
    sector_eligible = bool(sector_context.get("eligible"))
    sector_return1m = finite_number(sector_context.get("medianReturn1m"))
    sector_return3m = finite_number(sector_context.get("medianReturn3m"))
    sector_excess1m = (
        return1m - sector_return1m
        if sector_eligible and return1m is not None and sector_return1m is not None
        else None
    )
    sector_excess3m = (
        return3m - sector_return3m
        if sector_eligible and return3m is not None and sector_return3m is not None
        else None
    )

    relative_strength = 0.0
    for value, label in [
        (market_excess1m, "Beating IHSG over 1 month"),
        (market_excess3m, "Beating IHSG over 3 months"),
        (sector_excess1m, "Beating sector over 1 month"),
        (sector_excess3m, "Beating sector over 3 months"),
    ]:
        if value is not None and value > 0:
            relative_strength += 5
            positives.append(label)

    if atr_percent is None:
        risk_score = 0.0
    elif 1 <= atr_percent <= 4:
        risk_score = 10.0
    elif atr_percent < 1:
        risk_score = 7.0
    elif atr_percent <= 6:
        risk_score = 6.0
        risks.append("Elevated ATR")
    elif atr_percent <= 9:
        risk_score = 3.0
        risks.append("High ATR")
    else:
        risk_score = 0.0
        risks.append("Extreme ATR")

    def deduct(code: str, label: str, points: float) -> None:
        deductions.append({"code": code, "label": label, "points": points})
        risks.append(label)

    if price is not None and ema200[0] is not None and price < ema200[0]:
        deduct("BELOW_EMA200", "Price is below EMA200", 10)
    if not market_available:
        deduct("MARKET_UNKNOWN", "IHSG regime is unavailable", 8)
    elif not market_bullish:
        deduct("MARKET_BEARISH", "IHSG is below EMA200", 8)
    if rsi is not None and rsi > 80:
        deduct("RSI_EXTREME", "RSI is extremely overbought", 10)
    elif rsi is not None and (rsi > 75 or rsi < 35):
        deduct(
            "RSI_RISK",
            "RSI is overbought" if rsi > 75 else "RSI is weak",
            6,
        )
    if atr_percent is not None and atr_percent > 9:
        deduct("ATR_EXTREME", "ATR exceeds 9% of price", 10)
    elif atr_percent is not None and atr_percent > 6:
        deduct("ATR_HIGH", "ATR exceeds 6% of price", 5)
    if (
        market_excess1m is not None
        and market_excess3m is not None
        and market_excess1m <= 0
        and market_excess3m <= 0
    ):
        deduct("MARKET_LAG", "Trailing IHSG over 1 and 3 months", 5)
    if (
        sector_eligible
        and sector_excess1m is not None
        and sector_excess3m is not None
        and sector_excess1m <= 0
        and sector_excess3m <= 0
    ):
        deduct("SECTOR_LAG", "Trailing sector over 1 and 3 months", 3)
    if (
        relative_volume is not None
        and relative_volume >= 1.2
        and cmf is not None
        and cmf < 0
    ):
        deduct("DISTRIBUTION_VOLUME", "High volume with negative money flow", 4)
    if return3m is not None and return3m < -10:
        deduct("NEGATIVE_3M", "3-month return is below -10%", 5)

    positive_breakdown = {
        "liquidity": round(clamp(liquidity, 0, 20), 1),
        "trend": round(clamp(trend, 0, 30), 1),
        "momentum": round(clamp(momentum, 0, 20), 1),
        "relativeStrength": round(clamp(relative_strength, 0, 20), 1),
        "risk": round(clamp(risk_score, 0, 10), 1),
    }
    positive_total = round(sum(positive_breakdown.values()), 1)
    penalty_total = min(
        positive_total, round(sum(item["points"] for item in deductions), 1)
    )
    breakdown = {**positive_breakdown, "penalties": -penalty_total}
    total = round(sum(breakdown.values()), 1)

    required_lagged = (
        _complete(prices)
        and _complete(ema20)
        and _complete(ema50)
        and _complete(ema200)
        and _complete(macd)
        and _complete(macd_signal)
    )
    market_relative_positive = bool(
        market_excess1m is not None
        and market_excess1m > 0
        and market_excess3m is not None
        and market_excess3m > 0
    )
    sector_relative_positive = bool(
        sector_eligible
        and sector_excess1m is not None
        and sector_excess1m > 0
        and sector_excess3m is not None
        and sector_excess3m > 0
    )
    benchmark_data_available = bool(
        market_excess1m is not None
        and market_excess3m is not None
        and sector_eligible
        and sector_excess1m is not None
        and sector_excess3m is not None
    )
    strong_checks = {
        "scoreAtLeast75": total >= 75,
        "marketBullish": market_available and market_bullish,
        "threeSessionAlignment": persistence == 3,
        "allEmaSlopesRising": all(slopes.values()),
        "marketRelativeStrength": market_relative_positive,
        "sectorRelativeStrength": sector_relative_positive,
        "directionalVolume": volume_confirmed,
        "rsiWithinLimit": rsi is not None and 35 <= rsi <= 75,
        "atrWithinLimit": atr_percent is not None and atr_percent <= 6,
        "completeLaggedData": required_lagged,
    }
    severe_risk = bool(
        price is None
        or ema200[0] is None
        or price <= ema200[0]
        or rsi is None
        or not 35 <= rsi <= 75
        or atr_percent is None
        or atr_percent > 6
    )
    constructive_gate = bool(
        total >= 60
        and alignment[0]
        and alignment[1]
        and market_available
        and benchmark_data_available
        and required_lagged
        and volume_confirmation_available
        and not severe_risk
    )
    if all(strong_checks.values()):
        signal = "Strong"
    elif constructive_gate:
        signal = "Constructive"
    else:
        signal = "Mixed"

    return {
        **stock,
        "score": total,
        "signal": signal,
        "scoreBreakdown": breakdown,
        "positiveSignals": positives[:8],
        "riskFlags": risks[:8],
        "deductions": deductions,
        "trendPersistence": persistence,
        "emaSlopes": slopes,
        "atrPercent": round(atr_percent, 4) if atr_percent is not None else None,
        "volumeConfirmed": volume_confirmed,
        "relativeStrength": {
            "market1m": (
                round(market_excess1m, 4)
                if market_excess1m is not None
                else None
            ),
            "market3m": (
                round(market_excess3m, 4)
                if market_excess3m is not None
                else None
            ),
            "sector1m": (
                round(sector_excess1m, 4)
                if sector_excess1m is not None
                else None
            ),
            "sector3m": (
                round(sector_excess3m, 4)
                if sector_excess3m is not None
                else None
            ),
            "sectorEligible": sector_eligible,
            "sectorSize": sector_context.get("count", 0),
        },
        "strongGate": {
            "passed": all(strong_checks.values()),
            "checks": strong_checks,
        },
    }


def rank_stocks(
    raw_stocks: List[Dict[str, Any]],
    market_context: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
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
    sector_context = build_sector_context(prepared)
    scored = [
        score_stock(
            stock,
            ranks.get(float(stock["averageTradedValue"]), 0.0),
            market_context,
            sector_context.get(str(stock.get("sector") or "Unclassified")),
        )
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
