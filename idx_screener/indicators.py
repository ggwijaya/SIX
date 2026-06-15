from __future__ import annotations

import math
from statistics import pstdev
from typing import Any, Dict, List, Optional


def finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def ema(values: List[Optional[float]], period: int) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(values)
    multiplier = 2 / (period + 1)
    current: Optional[float] = None
    for index, value in enumerate(values):
        if value is None:
            continue
        current = value if current is None else value * multiplier + current * (1 - multiplier)
        if index >= period - 1:
            result[index] = current
    return result


def rsi(values: List[Optional[float]], period: int = 14) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(values)
    gains: List[float] = []
    losses: List[float] = []
    average_gain: Optional[float] = None
    average_loss: Optional[float] = None
    for index in range(1, len(values)):
        current = values[index]
        previous = values[index - 1]
        if current is None or previous is None:
            gains.append(0.0)
            losses.append(0.0)
            continue
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
        if index == period:
            average_gain = sum(gains[-period:]) / period
            average_loss = sum(losses[-period:]) / period
        elif index > period and average_gain is not None and average_loss is not None:
            average_gain = (average_gain * (period - 1) + gains[-1]) / period
            average_loss = (average_loss * (period - 1) + losses[-1]) / period
        if average_gain is None or average_loss is None:
            continue
        if average_loss == 0:
            result[index] = 100.0
        else:
            result[index] = 100 - (100 / (1 + average_gain / average_loss))
    return result


def atr(bars: List[Dict[str, Any]], period: int = 14) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(bars)
    true_ranges: List[Optional[float]] = []
    current_atr: Optional[float] = None
    for index, bar in enumerate(bars):
        high = finite(bar.get("high"))
        low = finite(bar.get("low"))
        previous_close = (
            finite(bars[index - 1].get("close")) if index > 0 else None
        )
        if high is None or low is None:
            true_ranges.append(None)
            continue
        candidates = [high - low]
        if previous_close is not None:
            candidates.extend([abs(high - previous_close), abs(low - previous_close)])
        value = max(candidates)
        true_ranges.append(value)
        if index == period - 1:
            window = [item for item in true_ranges[-period:] if item is not None]
            if len(window) == period:
                current_atr = sum(window) / period
        elif index >= period and current_atr is not None:
            current_atr = (current_atr * (period - 1) + value) / period
        if current_atr is not None:
            result[index] = current_atr
    return result


def chaikin_money_flow(
    bars: List[Dict[str, Any]], period: int = 20
) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(bars)
    money_flow_volumes: List[Optional[float]] = []
    volumes: List[Optional[float]] = []
    for index, bar in enumerate(bars):
        high = finite(bar.get("high"))
        low = finite(bar.get("low"))
        close = finite(bar.get("close"))
        volume = finite(bar.get("volume"))
        if high is None or low is None or close is None or volume is None:
            money_flow_volumes.append(None)
            volumes.append(None)
            continue
        multiplier = 0.0 if high == low else ((close - low) - (high - close)) / (high - low)
        money_flow_volumes.append(multiplier * volume)
        volumes.append(volume)
        if index < period - 1:
            continue
        flow_window = money_flow_volumes[index - period + 1 : index + 1]
        volume_window = volumes[index - period + 1 : index + 1]
        if any(item is None for item in flow_window + volume_window):
            continue
        total_volume = sum(item for item in volume_window if item is not None)
        if total_volume:
            result[index] = (
                sum(item for item in flow_window if item is not None) / total_volume
            )
    return result


def rolling_average(
    values: List[Optional[float]], period: int
) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        if all(value is not None for value in window):
            result[index] = sum(value for value in window if value is not None) / period
    return result


def stochastic(
    bars: List[Dict[str, Any]],
    period: int = 14,
    k_smoothing: int = 3,
    d_smoothing: int = 3,
) -> tuple[List[Optional[float]], List[Optional[float]]]:
    raw_k: List[Optional[float]] = [None] * len(bars)
    for index in range(period - 1, len(bars)):
        close = finite(bars[index].get("close"))
        highs = [
            finite(bar.get("high")) for bar in bars[index - period + 1 : index + 1]
        ]
        lows = [
            finite(bar.get("low")) for bar in bars[index - period + 1 : index + 1]
        ]
        if close is None or any(value is None for value in highs + lows):
            continue
        highest = max(value for value in highs if value is not None)
        lowest = min(value for value in lows if value is not None)
        raw_k[index] = (
            50.0
            if highest == lowest
            else (close - lowest) / (highest - lowest) * 100
        )
    stochastic_k = rolling_average(raw_k, k_smoothing)
    stochastic_d = rolling_average(stochastic_k, d_smoothing)
    return stochastic_k, stochastic_d


def rolling_volatility(
    values: List[Optional[float]], period: int = 20
) -> List[Optional[float]]:
    daily_returns: List[Optional[float]] = [None]
    for index in range(1, len(values)):
        current = values[index]
        previous = values[index - 1]
        daily_returns.append(
            (current / previous - 1) * 100
            if current is not None and previous not in (None, 0)
            else None
        )
    result: List[Optional[float]] = [None] * len(values)
    for index in range(period, len(values)):
        window = daily_returns[index - period + 1 : index + 1]
        if all(value is not None for value in window):
            result[index] = pstdev(value for value in window if value is not None)
    return result


def adjusted_bars(bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    adjusted: List[Dict[str, Any]] = []
    for bar in bars:
        close = finite(bar.get("close"))
        adjusted_close = finite(bar.get("adjustedClose") or bar.get("adj_close"))
        ratio = (
            adjusted_close / close
            if close not in (None, 0) and adjusted_close is not None
            else 1.0
        )
        adjusted.append(
            {
                **bar,
                "open": (
                    finite(bar.get("open")) * ratio
                    if finite(bar.get("open")) is not None
                    else None
                ),
                "high": (
                    finite(bar.get("high")) * ratio
                    if finite(bar.get("high")) is not None
                    else None
                ),
                "low": (
                    finite(bar.get("low")) * ratio
                    if finite(bar.get("low")) is not None
                    else None
                ),
                "close": adjusted_close if adjusted_close is not None else close,
                "adjustedClose": adjusted_close if adjusted_close is not None else close,
                "volume": finite(bar.get("volume")),
            }
        )
    return adjusted


def build_feature_rows(
    bars: List[Dict[str, Any]],
    symbol: str,
    sector: str = "Unclassified",
) -> List[Dict[str, Any]]:
    ordered = sorted(adjusted_bars(bars), key=lambda item: str(item.get("date")))
    closes = [finite(item.get("close")) for item in ordered]
    volumes = [finite(item.get("volume")) for item in ordered]
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    rsi14 = rsi(closes)
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd = [
        fast - slow if fast is not None and slow is not None else None
        for fast, slow in zip(ema12, ema26)
    ]
    macd_signal = ema(macd, 9)
    atr14 = atr(ordered)
    cmf20 = chaikin_money_flow(ordered)
    stochastic_k, stochastic_d = stochastic(ordered)
    average_volume10 = rolling_average(volumes, 10)
    volatility = rolling_volatility(closes)

    rows: List[Dict[str, Any]] = []
    for index, bar in enumerate(ordered):
        if index < 2:
            continue
        price = closes[index]
        average_volume = average_volume10[index]
        relative_volume = (
            volumes[index] / average_volume
            if volumes[index] is not None and average_volume not in (None, 0)
            else None
        )

        def trailing_return(offset: int) -> Optional[float]:
            if index < offset or price is None or closes[index - offset] in (None, 0):
                return None
            return (price / closes[index - offset] - 1) * 100  # type: ignore[operator]

        def lag(values: List[Optional[float]], offset: int) -> Optional[float]:
            return values[index - offset] if index >= offset else None

        rows.append(
            {
                "date": str(bar.get("date")),
                "symbol": symbol,
                "company": symbol,
                "instrumentType": "stock",
                "sector": sector or "Unclassified",
                "price": price,
                "pricePrev1": closes[index - 1],
                "pricePrev2": closes[index - 2],
                "change": trailing_return(1),
                "volume": volumes[index],
                "volumePrev1": volumes[index - 1],
                "volumePrev2": volumes[index - 2],
                "averageVolume10d": average_volume,
                "relativeVolume": relative_volume,
                "relativeVolumePrev1": (
                    volumes[index - 1] / average_volume10[index - 1]
                    if volumes[index - 1] is not None
                    and average_volume10[index - 1] not in (None, 0)
                    else None
                ),
                "relativeVolumePrev2": (
                    volumes[index - 2] / average_volume10[index - 2]
                    if volumes[index - 2] is not None
                    and average_volume10[index - 2] not in (None, 0)
                    else None
                ),
                "rsi": rsi14[index],
                "rsiPrev1": lag(rsi14, 1),
                "rsiPrev2": lag(rsi14, 2),
                "rsiPrev3": lag(rsi14, 3),
                "rsiPrev4": lag(rsi14, 4),
                "rsiPrev5": lag(rsi14, 5),
                "stochasticK": stochastic_k[index],
                "stochasticKPrev1": lag(stochastic_k, 1),
                "stochasticKPrev2": lag(stochastic_k, 2),
                "stochasticKPrev3": lag(stochastic_k, 3),
                "stochasticKPrev4": lag(stochastic_k, 4),
                "stochasticKPrev5": lag(stochastic_k, 5),
                "stochasticD": stochastic_d[index],
                "macd": macd[index],
                "macdPrev1": macd[index - 1],
                "macdPrev2": macd[index - 2],
                "macdSignal": macd_signal[index],
                "macdSignalPrev1": macd_signal[index - 1],
                "macdSignalPrev2": macd_signal[index - 2],
                "ema20": ema20[index],
                "ema20Prev1": ema20[index - 1],
                "ema20Prev2": ema20[index - 2],
                "ema50": ema50[index],
                "ema50Prev1": ema50[index - 1],
                "ema50Prev2": ema50[index - 2],
                "ema200": ema200[index],
                "ema200Prev1": ema200[index - 1],
                "ema200Prev2": ema200[index - 2],
                "return1m": trailing_return(21),
                "return3m": trailing_return(63),
                "atr": atr14[index],
                "atrPrev1": atr14[index - 1],
                "atrPrev2": atr14[index - 2],
                "cmf": cmf20[index],
                "cmfPrev1": cmf20[index - 1],
                "cmfPrev2": cmf20[index - 2],
                "volatility": volatility[index],
            }
        )
    return rows
