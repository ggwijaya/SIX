from idx_screener.scoring import (
    build_reversal_setup,
    build_sector_context,
    eligible,
    rank_stocks,
    score_stock,
)


def stock(symbol="TEST", **overrides):
    data = {
        "symbol": symbol,
        "company": "Test Company",
        "instrumentType": "stock",
        "sector": "Financials",
        "price": 1000,
        "change": 1,
        "volume": 2_000_000,
        "volumePrev1": 1_800_000,
        "volumePrev2": 1_700_000,
        "averageVolume10d": 1_000_000,
        "relativeVolume": 1.3,
        "relativeVolumePrev1": 1.1,
        "relativeVolumePrev2": 1.0,
        "rsi": 58,
        "rsiPrev1": 56,
        "rsiPrev2": 54,
        "rsiPrev3": 52,
        "rsiPrev4": 50,
        "rsiPrev5": 48,
        "stochasticK": 65,
        "stochasticKPrev1": 60,
        "stochasticKPrev2": 55,
        "stochasticKPrev3": 50,
        "stochasticKPrev4": 45,
        "stochasticKPrev5": 40,
        "stochasticD": 60,
        "macd": 12,
        "macdPrev1": 10,
        "macdPrev2": 8,
        "macdSignal": 8,
        "macdSignalPrev1": 7,
        "macdSignalPrev2": 6,
        "ema20": 950,
        "ema20Prev1": 940,
        "ema20Prev2": 930,
        "ema50": 900,
        "ema50Prev1": 890,
        "ema50Prev2": 880,
        "ema200": 800,
        "ema200Prev1": 790,
        "ema200Prev2": 780,
        "pricePrev1": 990,
        "pricePrev2": 980,
        "return1m": 8,
        "return3m": 18,
        "atr": 25,
        "atrPrev1": 24,
        "atrPrev2": 23,
        "cmf": 0.2,
        "cmfPrev1": 0.18,
        "cmfPrev2": 0.15,
    }
    data.update(overrides)
    return data


def test_strong_stock_is_bounded_and_labeled():
    result = score_stock(
        {**stock(), "averageTradedValue": 1_000_000_000},
        liquidity_percentile=1,
        market_context={
            "available": True,
            "bullish": True,
            "return1m": 2,
            "return3m": 5,
        },
        sector_context={
            "eligible": True,
            "count": 12,
            "medianReturn1m": 3,
            "medianReturn3m": 8,
        },
    )
    assert 75 <= result["score"] <= 100
    assert result["signal"] == "Strong"
    assert sum(result["scoreBreakdown"].values()) == result["score"]
    assert result["strongGate"]["passed"] is True
    assert result["trendPersistence"] == 3
    assert result["volumeConfirmed"] is True


def test_missing_indicators_never_produce_nan():
    data = {
        **stock(),
        "averageTradedValue": 1_000_000_000,
        "rsi": None,
        "macd": None,
        "volatility": float("nan"),
    }
    result = score_stock(data, liquidity_percentile=0.5)
    assert result["score"] == result["score"]
    assert 0 <= result["score"] <= 100


def test_eligibility_rejects_low_liquidity_and_non_stock():
    assert eligible({**stock(), "averageTradedValue": 500_000_000})
    assert not eligible({**stock(), "averageTradedValue": 499_999_999})
    assert not eligible({**stock(), "averageTradedValue": 1_000_000_000, "instrumentType": "fund"})
    assert not eligible({**stock("ABC-W"), "averageTradedValue": 1_000_000_000})


def test_ranking_tie_breaks_by_liquidity_then_symbol():
    ranked, counts = rank_stocks(
        [
            stock("BBBB", price=1000, averageVolume10d=1_000_000),
            stock("AAAA", price=2000, averageVolume10d=1_000_000),
            stock("LOW", price=100, averageVolume10d=1_000),
        ]
    )
    assert counts == {"universe": 3, "qualifying": 2, "excluded": 1}
    assert ranked[0]["symbol"] == "AAAA"
    assert [item["rank"] for item in ranked] == [1, 2]


def test_sector_context_requires_five_members():
    context = build_sector_context(
        [stock(f"S{index}", return1m=index, return3m=index * 2) for index in range(5)]
        + [stock("ONLY", sector="Utilities")]
    )
    assert context["Financials"]["eligible"] is True
    assert context["Financials"]["medianReturn1m"] == 2
    assert context["Utilities"]["eligible"] is False


def test_bearish_market_suppresses_strong_and_applies_penalty():
    result = score_stock(
        stock(),
        liquidity_percentile=1,
        market_context={
            "available": True,
            "bullish": False,
            "return1m": 2,
            "return3m": 5,
        },
        sector_context={
            "eligible": True,
            "count": 10,
            "medianReturn1m": 3,
            "medianReturn3m": 8,
        },
    )
    assert result["signal"] != "Strong"
    assert result["scoreBreakdown"]["penalties"] < 0
    assert any(item["code"] == "MARKET_BEARISH" for item in result["deductions"])
    assert sum(result["scoreBreakdown"].values()) == result["score"]


def test_missing_context_and_volume_data_fail_closed():
    result = score_stock(
        stock(cmf=None),
        liquidity_percentile=1,
        market_context={"available": False, "bullish": False},
        sector_context={
            "eligible": False,
            "count": 2,
            "medianReturn1m": None,
            "medianReturn3m": None,
        },
    )
    assert result["signal"] == "Mixed"
    assert result["strongGate"]["checks"]["directionalVolume"] is False
    assert result["strongGate"]["checks"]["marketBullish"] is False


def test_missing_sector_benchmark_suppresses_constructive():
    result = score_stock(
        stock(),
        liquidity_percentile=1,
        market_context={
            "available": True,
            "bullish": True,
            "return1m": 0,
            "return3m": 0,
        },
        sector_context={
            "eligible": False,
            "count": 4,
            "medianReturn1m": 0,
            "medianReturn3m": 0,
        },
    )
    assert result["score"] >= 60
    assert result["signal"] == "Mixed"
    assert result["strongGate"]["checks"]["sectorRelativeStrength"] is False


def test_explicit_risk_deductions_are_capped_at_zero():
    result = score_stock(
        stock(
            price=500,
            pricePrev1=510,
            pricePrev2=520,
            ema200=800,
            rsi=85,
            atr=60,
            cmf=-0.3,
            relativeVolume=2,
            return1m=-20,
            return3m=-30,
        ),
        liquidity_percentile=0,
        market_context={
            "available": True,
            "bullish": False,
            "return1m": 5,
            "return3m": 10,
        },
        sector_context={
            "eligible": True,
            "count": 10,
            "medianReturn1m": 3,
            "medianReturn3m": 8,
        },
    )
    assert result["score"] >= 0
    assert sum(result["scoreBreakdown"].values()) == result["score"]
    codes = {item["code"] for item in result["deductions"]}
    assert {"BELOW_EMA200", "RSI_EXTREME", "ATR_EXTREME"} <= codes


def bullish_market():
    return {
        "available": True,
        "bullish": True,
        "return1m": 2,
        "return3m": 5,
    }


def recovery_stock(**overrides):
    values = {
        "rsi": 40,
        "rsiPrev1": 29,
        "stochasticK": 30,
        "stochasticKPrev1": 15,
        "stochasticD": 25,
    }
    values.update(overrides)
    return stock(**values)


def test_active_oversold_setup_is_watch():
    setup = build_reversal_setup(
        stock(rsi=28, stochasticK=15, stochasticD=18),
        bullish_market(),
    )
    assert setup["status"] == "Oversold Watch"
    assert setup["checks"]["currentOversold"] is True


def test_recovery_is_confirmed_after_recent_oversold():
    setup = build_reversal_setup(recovery_stock(), bullish_market())
    assert setup["status"] == "Recovery Confirmed"
    assert setup["lookback"]["mostRecentOversoldSessionsAgo"] == 1
    assert all(
        setup["checks"][key]
        for key in [
            "priorOversold",
            "rsiRecovered",
            "stochasticRecovered",
            "stochasticAboveD",
            "priceAboveEma200",
            "cmfPositive",
            "marketBullish",
        ]
    )


def test_expired_oversold_lookback_does_not_confirm_recovery():
    setup = build_reversal_setup(
        stock(
            rsi=40,
            stochasticK=30,
            stochasticD=25,
            rsiPrev6=25,
            stochasticKPrev6=10,
        ),
        bullish_market(),
    )
    assert setup["status"] == "None"
    assert setup["checks"]["priorOversold"] is False


def test_recovery_fails_closed_for_regime_trend_and_money_flow():
    bearish = build_reversal_setup(
        recovery_stock(),
        {**bullish_market(), "bullish": False},
    )
    below_ema200 = build_reversal_setup(
        recovery_stock(price=700, ema200=800),
        bullish_market(),
    )
    negative_cmf = build_reversal_setup(
        recovery_stock(cmf=-0.1),
        bullish_market(),
    )
    assert bearish["status"] == "None"
    assert bearish["checks"]["marketBullish"] is False
    assert below_ema200["status"] == "None"
    assert below_ema200["checks"]["priceAboveEma200"] is False
    assert negative_cmf["status"] == "None"
    assert negative_cmf["checks"]["cmfPositive"] is False


def test_missing_reversal_data_is_unavailable():
    setup = build_reversal_setup(
        recovery_stock(stochasticD=None),
        bullish_market(),
    )
    assert setup["status"] == "Unavailable"
    assert setup["available"] is False


def test_reversal_setup_does_not_change_score_signal_or_rank():
    enriched = stock("AAA")
    unavailable = {
        key: value
        for key, value in stock("AAA").items()
        if not key.startswith("stochastic") and key not in {"rsiPrev3", "rsiPrev4", "rsiPrev5"}
    }
    enriched_ranked, _ = rank_stocks([enriched], bullish_market())
    unavailable_ranked, _ = rank_stocks([unavailable], bullish_market())
    assert enriched_ranked[0]["score"] == unavailable_ranked[0]["score"]
    assert enriched_ranked[0]["signal"] == unavailable_ranked[0]["signal"]
    assert enriched_ranked[0]["rank"] == unavailable_ranked[0]["rank"]
    assert enriched_ranked[0]["reversalSetup"]["status"] == "None"
    assert unavailable_ranked[0]["reversalSetup"]["status"] == "Unavailable"
