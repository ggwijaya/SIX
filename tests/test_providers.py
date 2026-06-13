from idx_screener.providers import TradingViewProvider, YahooProvider


class FixtureResponse:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def test_tradingview_fixture_maps_columns(monkeypatch):
    provider = TradingViewProvider()
    values = [
        "BBCA",
        "PT Bank Central Asia Tbk",
        "stock",
        "Finance",
        5925,
        1.7,
        415_872_300,
        602_213_060,
        0.71,
        730_404_652_734_375,
        52.3,
        -179.2,
        -216.9,
        5728.2,
        6116.9,
        7277.4,
        -3.2,
        -13.5,
        4.66,
    ]
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
    assert result[0]["ema200"] == 7277.4


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
