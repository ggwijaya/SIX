from __future__ import annotations

import math
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from flask import Flask, jsonify, render_template, request, send_from_directory

from idx_screener.cache import TTLCache
from idx_screener.providers import ProviderError, TradingViewProvider, YahooProvider
from idx_screener.scoring import MODEL, rank_stocks


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def create_app(
    tradingview: Optional[TradingViewProvider] = None,
    yahoo: Optional[YahooProvider] = None,
) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    tv_provider = tradingview or TradingViewProvider()
    yahoo_provider = yahoo or YahooProvider()
    screener_cache = TTLCache(ttl_seconds=15 * 60)
    history_cache = TTLCache(ttl_seconds=60 * 60)
    refresh_lock = threading.Lock()
    state: Dict[str, Any] = {"last_refresh_attempt": 0.0}

    def error_payload(
        code: str, message: str, status: int, details: Optional[Dict[str, Any]] = None
    ) -> Tuple[Any, int]:
        return (
            jsonify(
                {
                    "asOf": utc_now(),
                    "source": "HexInc",
                    "stale": False,
                    "error": {
                        "code": code,
                        "message": message,
                        "details": details or {},
                    },
                }
            ),
            status,
        )

    def load_screener(force: bool = False) -> Dict[str, Any]:
        cached = screener_cache.get("snapshot", allow_stale=True)
        if cached and not force and not cached.expired:
            return cached.value

        try:
            raw_stocks = tv_provider.fetch_stocks()
            warnings = []
            try:
                market_context = tv_provider.fetch_market_context()
            except (AttributeError, ProviderError) as exc:
                market_context = {
                    "symbol": "COMPOSITE",
                    "name": "IDX Composite Index",
                    "available": False,
                    "bullish": False,
                    "return1m": None,
                    "return3m": None,
                }
                warnings.append(
                    f"IHSG context is unavailable; Strong signals are suppressed. {exc}"
                )
            if not market_context.get("available"):
                warnings.append(
                    "IHSG context is incomplete; Strong signals are suppressed."
                )
            ranked, counts = rank_stocks(raw_stocks, market_context)
            snapshot = {
                "asOf": utc_now(),
                "source": tv_provider.source_name,
                "stale": False,
                "error": None,
                "model": MODEL,
                "marketContext": market_context,
                "warnings": list(dict.fromkeys(warnings)),
                "universeCount": counts["universe"],
                "qualifyingCount": counts["qualifying"],
                "excludedCount": counts["excluded"],
                "stocks": ranked,
            }
            screener_cache.set("snapshot", snapshot)
            return snapshot
        except ProviderError as exc:
            if cached:
                stale = dict(cached.value)
                stale["stale"] = True
                stale["error"] = {
                    "code": "UPSTREAM_UNAVAILABLE",
                    "message": str(exc),
                    "details": {"usingCachedData": True},
                }
                return stale
            raise

    @app.route("/", methods=["GET"])
    def index() -> Any:
        return render_template("index.html")

    @app.route("/styles.css", methods=["GET"])
    def styles() -> Any:
        return send_from_directory("public", "styles.css")

    @app.route("/app.js", methods=["GET"])
    def javascript() -> Any:
        return send_from_directory("public", "app.js")

    @app.route("/api/screener", methods=["GET"])
    def screener() -> Any:
        try:
            limit = int(request.args.get("limit", "200"))
        except ValueError:
            return error_payload("INVALID_LIMIT", "limit must be an integer.", 400)
        if not 1 <= limit <= 500:
            return error_payload("INVALID_LIMIT", "limit must be between 1 and 500.", 400)

        try:
            snapshot = dict(load_screener())
        except ProviderError as exc:
            return error_payload("UPSTREAM_UNAVAILABLE", str(exc), 503)

        stocks = snapshot["stocks"][:limit]
        result = {
            **snapshot,
            "requestedLimit": limit,
            "returnedCount": len(stocks),
            "reducedCountReason": (
                None
                if len(stocks) == limit
                else "Fewer stocks met the IDR 500 million liquidity and equity eligibility rules."
            ),
            "stocks": stocks,
        }
        response = jsonify(clean_json(result))
        response.headers["Cache-Control"] = (
            "public, s-maxage=900, stale-while-revalidate=3600"
        )
        return response

    @app.route("/api/refresh", methods=["POST"])
    def refresh() -> Any:
        now = time.monotonic()
        with refresh_lock:
            elapsed = now - state["last_refresh_attempt"]
            if elapsed < 60:
                retry_after = max(1, math.ceil(60 - elapsed))
                response, status = error_payload(
                    "RATE_LIMITED",
                    "The screener can be refreshed once per minute.",
                    429,
                    {"retryAfterSeconds": retry_after},
                )
                response.headers["Retry-After"] = str(retry_after)
                return response, status
            state["last_refresh_attempt"] = now

        try:
            snapshot = load_screener(force=True)
        except ProviderError as exc:
            return error_payload("UPSTREAM_UNAVAILABLE", str(exc), 503)
        return jsonify(clean_json(snapshot))

    @app.route("/api/stocks/<symbol>", methods=["GET"])
    def stock_detail(symbol: str) -> Any:
        normalized = YahooProvider.normalize_symbol(symbol)
        if not normalized:
            return error_payload("INVALID_SYMBOL", "Use a valid IDX stock symbol.", 400)

        cached = history_cache.get(normalized, allow_stale=True)
        if cached and not cached.expired:
            response = jsonify(clean_json(cached.value))
            response.headers["Cache-Control"] = (
                "public, s-maxage=3600, stale-while-revalidate=86400"
            )
            return response

        snapshot = None
        try:
            snapshot = load_screener()
        except ProviderError:
            pass
        summary = None
        if snapshot:
            summary = next(
                (stock for stock in snapshot["stocks"] if stock["symbol"] == normalized),
                None,
            )

        try:
            history = yahoo_provider.fetch_history(normalized)
            payload = {
                "asOf": utc_now(),
                "source": yahoo_provider.source_name,
                "stale": False,
                "error": None,
                "stock": summary or {"symbol": normalized},
                "history": history,
            }
            history_cache.set(normalized, payload)
            response = jsonify(clean_json(payload))
            response.headers["Cache-Control"] = (
                "public, s-maxage=3600, stale-while-revalidate=86400"
            )
            return response
        except ProviderError as exc:
            if cached:
                stale = dict(cached.value)
                stale["stale"] = True
                stale["error"] = {
                    "code": "UPSTREAM_UNAVAILABLE",
                    "message": str(exc),
                    "details": {"usingCachedData": True},
                }
                return jsonify(clean_json(stale))
            return error_payload("UPSTREAM_UNAVAILABLE", str(exc), 503)

    @app.route("/api/health", methods=["GET"])
    def health() -> Any:
        return jsonify({"status": "ok", "asOf": utc_now()})

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
