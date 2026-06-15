from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from idx_screener.indicators import build_feature_rows


class ProviderError(RuntimeError):
    pass


class BaseProvider:
    timeout = 20
    retries = 1

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HexInc/1.0",
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
        "close[1]",
        "close[2]",
        "change",
        "volume",
        "volume[1]",
        "volume[2]",
        "average_volume_10d_calc",
        "relative_volume_10d_calc",
        "relative_volume_10d_calc[1]",
        "relative_volume_10d_calc[2]",
        "market_cap_basic",
        "RSI",
        "RSI[1]",
        "RSI[2]",
        "RSI[3]",
        "RSI[4]",
        "RSI[5]",
        "Stoch.K",
        "Stoch.K[1]",
        "Stoch.K[2]",
        "Stoch.K[3]",
        "Stoch.K[4]",
        "Stoch.K[5]",
        "Stoch.D",
        "MACD.macd",
        "MACD.macd[1]",
        "MACD.macd[2]",
        "MACD.signal",
        "MACD.signal[1]",
        "MACD.signal[2]",
        "EMA20",
        "EMA20[1]",
        "EMA20[2]",
        "EMA50",
        "EMA50[1]",
        "EMA50[2]",
        "EMA200",
        "EMA200[1]",
        "EMA200[2]",
        "Perf.1M",
        "Perf.3M",
        "ATR",
        "ATR[1]",
        "ATR[2]",
        "ChaikinMoneyFlow",
        "ChaikinMoneyFlow[1]",
        "ChaikinMoneyFlow[2]",
    ]
    market_columns = [
        "name",
        "description",
        "close",
        "close[1]",
        "close[2]",
        "EMA200",
        "EMA200[1]",
        "EMA200[2]",
        "Perf.1M",
        "Perf.3M",
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
                    "pricePrev1": raw.get("close[1]"),
                    "pricePrev2": raw.get("close[2]"),
                    "change": raw.get("change"),
                    "volume": raw.get("volume"),
                    "volumePrev1": raw.get("volume[1]"),
                    "volumePrev2": raw.get("volume[2]"),
                    "averageVolume10d": raw.get("average_volume_10d_calc"),
                    "relativeVolume": raw.get("relative_volume_10d_calc"),
                    "relativeVolumePrev1": raw.get(
                        "relative_volume_10d_calc[1]"
                    ),
                    "relativeVolumePrev2": raw.get(
                        "relative_volume_10d_calc[2]"
                    ),
                    "marketCap": raw.get("market_cap_basic"),
                    "rsi": raw.get("RSI"),
                    "rsiPrev1": raw.get("RSI[1]"),
                    "rsiPrev2": raw.get("RSI[2]"),
                    "rsiPrev3": raw.get("RSI[3]"),
                    "rsiPrev4": raw.get("RSI[4]"),
                    "rsiPrev5": raw.get("RSI[5]"),
                    "stochasticK": raw.get("Stoch.K"),
                    "stochasticKPrev1": raw.get("Stoch.K[1]"),
                    "stochasticKPrev2": raw.get("Stoch.K[2]"),
                    "stochasticKPrev3": raw.get("Stoch.K[3]"),
                    "stochasticKPrev4": raw.get("Stoch.K[4]"),
                    "stochasticKPrev5": raw.get("Stoch.K[5]"),
                    "stochasticD": raw.get("Stoch.D"),
                    "macd": raw.get("MACD.macd"),
                    "macdPrev1": raw.get("MACD.macd[1]"),
                    "macdPrev2": raw.get("MACD.macd[2]"),
                    "macdSignal": raw.get("MACD.signal"),
                    "macdSignalPrev1": raw.get("MACD.signal[1]"),
                    "macdSignalPrev2": raw.get("MACD.signal[2]"),
                    "ema20": raw.get("EMA20"),
                    "ema20Prev1": raw.get("EMA20[1]"),
                    "ema20Prev2": raw.get("EMA20[2]"),
                    "ema50": raw.get("EMA50"),
                    "ema50Prev1": raw.get("EMA50[1]"),
                    "ema50Prev2": raw.get("EMA50[2]"),
                    "ema200": raw.get("EMA200"),
                    "ema200Prev1": raw.get("EMA200[1]"),
                    "ema200Prev2": raw.get("EMA200[2]"),
                    "return1m": raw.get("Perf.1M"),
                    "return3m": raw.get("Perf.3M"),
                    "atr": raw.get("ATR"),
                    "atrPrev1": raw.get("ATR[1]"),
                    "atrPrev2": raw.get("ATR[2]"),
                    "cmf": raw.get("ChaikinMoneyFlow"),
                    "cmfPrev1": raw.get("ChaikinMoneyFlow[1]"),
                    "cmfPrev2": raw.get("ChaikinMoneyFlow[2]"),
                }
            )
        if not stocks:
            raise ProviderError("TradingView returned no eligible IDX instruments.")
        return stocks

    def fetch_market_context(self) -> Dict[str, Any]:
        payload = {
            "markets": ["indonesia"],
            "symbols": {
                "query": {"types": []},
                "tickers": ["IDX:COMPOSITE"],
            },
            "columns": self.market_columns,
            "range": [0, 1],
        }
        response = self._request("POST", self.endpoint, json=payload)
        try:
            body = response.json()
            row = body["data"][0]
            values = row["d"]
            if len(values) != len(self.market_columns):
                raise ValueError("Unexpected market column count")
            raw = dict(zip(self.market_columns, values))
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "TradingView returned invalid IDX Composite context."
            ) from exc

        price = raw.get("close")
        ema200 = raw.get("EMA200")
        available = price is not None and ema200 is not None
        return {
            "symbol": "COMPOSITE",
            "name": raw.get("description") or "IDX Composite Index",
            "price": price,
            "pricePrev1": raw.get("close[1]"),
            "pricePrev2": raw.get("close[2]"),
            "ema200": ema200,
            "ema200Prev1": raw.get("EMA200[1]"),
            "ema200Prev2": raw.get("EMA200[2]"),
            "return1m": raw.get("Perf.1M"),
            "return3m": raw.get("Perf.3M"),
            "available": available,
            "bullish": bool(available and price > ema200),
        }


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
        return self._fetch_history(normalized, "1y")

    def _fetch_history(
        self, normalized: str, range_value: str
    ) -> List[Dict[str, Any]]:
        url = self.endpoint.format(symbol=normalized)
        response = self._request(
            "GET",
            url,
            params={
                "range": range_value,
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
            adjusted = result["indicators"].get("adjclose", [{}])[0].get(
                "adjclose"
            )
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
                    "adjustedClose": self._at(adjusted, index) or close,
                    "volume": self._at(quote.get("volume"), index),
                }
            )
        if not history:
            raise ProviderError(f"No historical data found for {normalized}.")
        return history

    def enrich_reversal_history(
        self,
        stocks: List[Dict[str, Any]],
        market_context: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        enriched = [dict(stock) for stock in stocks]
        if not market_context.get("available") or not market_context.get("bullish"):
            return enriched, []

        candidates: List[Dict[str, Any]] = []
        for stock in enriched:
            price = self._number(stock.get("price"))
            average_volume = self._number(stock.get("averageVolume10d"))
            ema200 = self._number(stock.get("ema200"))
            cmf = self._number(stock.get("cmf"))
            rsi = self._number(stock.get("rsi"))
            stochastic_k = self._number(stock.get("stochasticK"))
            stochastic_d = self._number(stock.get("stochasticD"))
            average_value = (
                price * average_volume
                if price is not None and average_volume is not None
                else None
            )
            if (
                average_value is not None
                and average_value >= 500_000_000
                and price is not None
                and ema200 is not None
                and price > ema200
                and cmf is not None
                and cmf > 0
                and rsi is not None
                and rsi > 30
                and stochastic_k is not None
                and stochastic_k > 20
                and stochastic_d is not None
                and stochastic_k > stochastic_d
            ):
                candidates.append(stock)

        failures: List[str] = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(
                    self._fetch_history, str(stock["symbol"]), "3mo"
                ): stock
                for stock in candidates
            }
            for future in as_completed(futures):
                stock = futures[future]
                try:
                    rows = build_feature_rows(
                        future.result(),
                        str(stock["symbol"]),
                        str(stock.get("sector") or "Unclassified"),
                    )
                    if not rows:
                        raise ProviderError("No reconstructed setup history.")
                    latest = rows[-1]
                    for offset in range(3, 6):
                        stock[f"rsiPrev{offset}"] = latest.get(
                            f"rsiPrev{offset}"
                        )
                        stock[f"stochasticKPrev{offset}"] = latest.get(
                            f"stochasticKPrev{offset}"
                        )
                except (ProviderError, requests.RequestException, ValueError):
                    failures.append(str(stock.get("symbol") or "Unknown"))
        return enriched, sorted(failures)

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number else None

    @staticmethod
    def _at(values: Optional[List[Any]], index: int) -> Any:
        if not values or index >= len(values):
            return None
        return values[index]
