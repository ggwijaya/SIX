from app import create_app
from idx_screener.providers import ProviderError, YahooProvider


def stock(symbol="BBCA"):
    return {
        "symbol": symbol,
        "company": "Bank Central Asia Tbk",
        "instrumentType": "stock",
        "sector": "Finance",
        "price": 9000,
        "change": 1.2,
        "volume": 10_000_000,
        "averageVolume10d": 8_000_000,
        "relativeVolume": 1.2,
        "marketCap": 1_000_000_000_000,
        "rsi": 58,
        "macd": 10,
        "macdSignal": 8,
        "ema20": 8800,
        "ema50": 8500,
        "ema200": 8000,
        "return1m": 4,
        "return3m": 12,
        "volatility": 2,
    }


class FakeTradingView:
    source_name = "Fixture TradingView"

    def __init__(self, fails=False):
        self.fails = fails

    def fetch_stocks(self):
        if self.fails:
            raise ProviderError("fixture outage")
        return [stock()]


class FakeYahoo:
    source_name = "Fixture Yahoo"

    def fetch_history(self, symbol):
        return [{"date": "2026-06-12", "open": 8900, "high": 9100, "low": 8850, "close": 9000, "volume": 1_000_000}]


def client(tv=None):
    app = create_app(tv or FakeTradingView(), FakeYahoo())
    app.config["TESTING"] = True
    return app.test_client()


def test_homepage_uses_hexinc_branding():
    response = client().get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "<title>HexInc</title>" in html
    assert 'aria-label="HexInc home"' in html
    assert '<span class="brand-mark">HEX</span>' in html
    assert "<span><strong>Hex</strong>Inc</span>" in html


def test_screener_api_shape():
    response = client().get("/api/screener?limit=200")
    body = response.get_json()
    assert response.status_code == 200
    assert body["source"] == "Fixture TradingView"
    assert body["returnedCount"] == 1
    assert body["stocks"][0]["symbol"] == "BBCA"
    assert "s-maxage=900" in response.headers["Cache-Control"]


def test_invalid_limit():
    response = client().get("/api/screener?limit=nope")
    assert response.status_code == 400
    body = response.get_json()
    assert body["source"] == "HexInc"
    assert body["error"]["code"] == "INVALID_LIMIT"


def test_upstream_outage_without_cache():
    response = client(FakeTradingView(fails=True)).get("/api/screener")
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"


def test_refresh_is_rate_limited():
    test_client = client()
    assert test_client.post("/api/refresh").status_code == 200
    response = test_client.post("/api/refresh")
    assert response.status_code == 429
    assert response.get_json()["error"]["code"] == "RATE_LIMITED"


def test_stock_detail_and_symbol_normalization():
    response = client().get("/api/stocks/bbca.jk")
    assert response.status_code == 200
    assert response.get_json()["stock"]["symbol"] == "BBCA"
    assert "s-maxage=3600" in response.headers["Cache-Control"]
    assert YahooProvider.normalize_symbol("../bad") is None


def test_public_assets_are_available_locally():
    test_client = client()
    assert test_client.get("/styles.css").status_code == 200
    assert test_client.get("/app.js").status_code == 200


def test_refresh_uses_stale_cache_during_outage():
    provider = FakeTradingView()
    test_client = client(provider)
    assert test_client.get("/api/screener").status_code == 200
    provider.fails = True
    response = test_client.post("/api/refresh")
    body = response.get_json()
    assert response.status_code == 200
    assert body["stale"] is True
    assert body["error"]["details"]["usingCachedData"] is True
