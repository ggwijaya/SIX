from idx_screener.providers import TradingViewProvider, YahooProvider


class FixtureResponse:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def test_tradingview_fixture_maps_columns(monkeypatch):
    provider = TradingViewProvider()
    raw = {column: index + 1 for index, column in enumerate(provider.columns)}
    raw.update(
        {
            "name": "BBCA",
            "description": "PT Bank Central Asia Tbk",
            "type": "stock",
            "sector": "Finance",
            "close": 5925,
            "close[1]": 5825,
            "close[2]": 5800,
            "average_volume_10d_calc": 602_213_060,
            "EMA200": 5277.4,
            "ATR": 125,
            "ChaikinMoneyFlow": 0.12,
        }
    )
    values = [raw[column] for column in provider.columns]
    monkeypatch.setattr(
        provider,
        "_request",
        lambda *args, **kwargs: FixtureResponse(
            {"totalCount": 1, "data": [{"s": "IDX:BBCA", "d": values}]}
        ),
    )
    result = provider.fetch_stocks()
    assert result[0]["symbol"] == "BBCA"
    assert result[0]["averageVolume10d"] == 602_213_060
    assert result[0]["pricePrev2"] == 5800
    assert result[0]["ema200"] == 5277.4
    assert result[0]["atr"] == 125
    assert result[0]["cmf"] == 0.12


def test_market_context_maps_regime(monkeypatch):
    provider = TradingViewProvider()
    raw = {
        "name": "COMPOSITE",
        "description": "IDX Composite Index",
        "close": 8000,
        "close[1]": 7950,
        "close[2]": 7900,
        "EMA200": 7500,
        "EMA200[1]": 7490,
        "EMA200[2]": 7480,
        "Perf.1M": 4,
        "Perf.3M": 10,
    }
    monkeypatch.setattr(
        provider,
        "_request",
        lambda *args, **kwargs: FixtureResponse(
            {
                "totalCount": 1,
                "data": [
                    {
                        "s": "IDX:COMPOSITE",
                        "d": [raw[column] for column in provider.market_columns],
                    }
                ],
            }
        ),
    )
    context = provider.fetch_market_context()
    assert context["available"] is True
    assert context["bullish"] is True
    assert context["return3m"] == 10


def test_yahoo_fixture_skips_missing_close(monkeypatch):
    provider = YahooProvider()
    monkeypatch.setattr(
        provider,
        "_request",
        lambda *args, **kwargs: FixtureResponse(
            {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1_700_000_000, 1_700_086_400],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [9000, None],
                                        "high": [9100, None],
                                        "low": [8900, None],
                                        "close": [9050, None],
                                        "volume": [1000, None],
                                    }
                                ]
                            },
                        }
                    ]
                }
            }
        ),
    )
    result = provider.fetch_history("bbca.jk")
    assert len(result) == 1
    assert result[0]["close"] == 9050
    assert result[0]["adjustedClose"] == 9050
