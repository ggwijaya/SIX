from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests


class ProviderError(RuntimeError):
    pass


class BaseProvider:
    timeout = 20
    retries = 1

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IDX-Screener/1.0",
        )
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                response = requests.request(
                    method, url, timeout=self.timeout, headers=headers, **kwargs
                )
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.35)
        raise ProviderError(f"Market data request failed: {last_error}") from last_error


class TradingViewProvider(BaseProvider):
    source_name = "TradingView Indonesia scanner"
    endpoint = "https://scanner.tradingview.com/indonesia/scan"
    columns = [
        "name",
        "description",
        "type",
        "sector",
        "close",
        "change",
        "volume",
        "average_volume_10d_calc",
        "relative_volume_10d_calc",
        "market_cap_basic",
        "RSI",
        "MACD.macd",
        "MACD.signal",
        "EMA20",
        "EMA50",
        "EMA200",
        "Perf.1M",
        "Perf.3M",
        "Volatility.D",
    ]

    def fetch_stocks(self) -> List[Dict[str, Any]]:
        payload = {
            "filter": [
                {"left": "exchange", "operation": "equal", "right": "IDX"},
                {"left": "type", "operation": "equal", "right": "stock"},
                {"left": "is_primary", "operation": "equal", "right": True},
            ],
            "options": {"lang": "en"},
            "markets": ["indonesia"],
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": self.columns,
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
            "range": [0, 9999],
        }
        response = self._request("POST", self.endpoint, json=payload)
        try:
            body = response.json()
            rows = body.get("data", [])
        except (ValueError, AttributeError) as exc:
            raise ProviderError("TradingView returned an invalid response.") from exc

        stocks: List[Dict[str, Any]] = []
        for row in rows:
            values = row.get("d", [])
            if len(values) != len(self.columns):
                continue
            raw = dict(zip(self.columns, values))
            symbol = str(raw.get("name") or row.get("s", "").split(":")[-1]).upper()
            stocks.append(
                {
                    "symbol": symbol,
                    "company": raw.get("description") or symbol,
                    "instrumentType": raw.get("type"),
                    "sector": raw.get("sector") or "Unclassified",
                    "price": raw.get("close"),
                    "change": raw.get("change"),
                    "volume": raw.get("volume"),
                    "averageVolume10d": raw.get("average_volume_10d_calc"),
                    "relativeVolume": raw.get("relative_volume_10d_calc"),
                    "marketCap": raw.get("market_cap_basic"),
                    "rsi": raw.get("RSI"),
                    "macd": raw.get("MACD.macd"),
                    "macdSignal": raw.get("MACD.signal"),
                    "ema20": raw.get("EMA20"),
                    "ema50": raw.get("EMA50"),
                    "ema200": raw.get("EMA200"),
                    "return1m": raw.get("Perf.1M"),
                    "return3m": raw.get("Perf.3M"),
                    "volatility": raw.get("Volatility.D"),
                }
            )
        if not stocks:
            raise ProviderError("TradingView returned no eligible IDX instruments.")
        return stocks


class YahooProvider(BaseProvider):
    source_name = "Yahoo Finance chart API"
    endpoint = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.JK"
    symbol_pattern = re.compile(r"^[A-Z0-9]{1,12}$")

    @classmethod
    def normalize_symbol(cls, symbol: str) -> Optional[str]:
        normalized = symbol.strip().upper()
        if normalized.endswith(".JK"):
            normalized = normalized[:-3]
        if not cls.symbol_pattern.fullmatch(normalized):
            return None
        return normalized

    def fetch_history(self, symbol: str) -> List[Dict[str, Any]]:
        normalized = self.normalize_symbol(symbol)
        if not normalized:
            raise ProviderError("Invalid IDX stock symbol.")
        url = self.endpoint.format(symbol=normalized)
        response = self._request(
            "GET",
            url,
            params={
                "range": "1y",
                "interval": "1d",
                "events": "div,splits",
                "includeAdjustedClose": "true",
            },
        )
        try:
            body = response.json()
            result = body["chart"]["result"][0]
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"No historical data found for {normalized}.") from exc

        history: List[Dict[str, Any]] = []
        for index, timestamp in enumerate(timestamps):
            close = self._at(quote.get("close"), index)
            if close is None:
                continue
            history.append(
                {
                    "date": datetime.fromtimestamp(
                        timestamp, tz=timezone.utc
                    ).date().isoformat(),
                    "open": self._at(quote.get("open"), index),
                    "high": self._at(quote.get("high"), index),
                    "low": self._at(quote.get("low"), index),
                    "close": close,
                    "volume": self._at(quote.get("volume"), index),
                }
            )
        if not history:
            raise ProviderError(f"No historical data found for {normalized}.")
        return history

    @staticmethod
    def _at(values: Optional[List[Any]], index: int) -> Any:
        if not values or index >= len(values):
            return None
        return values[index]
