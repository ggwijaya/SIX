from idx_screener.scoring import eligible, rank_stocks, score_stock


def stock(symbol="TEST", **overrides):
    data = {
        "symbol": symbol,
        "company": "Test Company",
        "instrumentType": "stock",
        "sector": "Financials",
        "price": 1000,
        "change": 1,
        "volume": 2_000_000,
        "averageVolume10d": 1_000_000,
        "relativeVolume": 1.3,
        "rsi": 58,
        "macd": 12,
        "macdSignal": 8,
        "ema20": 950,
        "ema50": 900,
        "ema200": 800,
        "return1m": 8,
        "return3m": 18,
        "volatility": 2.5,
    }
    data.update(overrides)
    return data


def test_strong_stock_is_bounded_and_labeled():
    result = score_stock(
        {**stock(), "averageTradedValue": 1_000_000_000},
        liquidity_percentile=1,
    )
    assert 75 <= result["score"] <= 100
    assert result["signal"] == "Strong"
    assert sum(result["scoreBreakdown"].values()) == result["score"]


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
