from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from idx_screener.indicators import adjusted_bars, build_feature_rows, finite
from idx_screener.providers import TradingViewProvider
from idx_screener.scoring import (
    MIN_AVERAGE_TRADED_VALUE,
    eligible,
    percentile_ranks,
    rank_stocks,
)


@dataclass(frozen=True)
class UniverseEntry:
    symbol: str
    sector: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    def active(self, session: str) -> bool:
        return bool(
            (not self.start_date or self.start_date <= session)
            and (not self.end_date or session <= self.end_date)
        )


def read_universe_csv(path: Path) -> List[UniverseEntry]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"symbol", "sector", "start_date", "end_date"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                "Universe CSV must contain symbol,sector,start_date,end_date."
            )
        return [
            UniverseEntry(
                symbol=str(row["symbol"]).strip().upper().removesuffix(".JK"),
                sector=str(row["sector"]).strip() or "Unclassified",
                start_date=str(row["start_date"]).strip() or None,
                end_date=str(row["end_date"]).strip() or None,
            )
            for row in reader
            if str(row.get("symbol") or "").strip()
        ]


def read_price_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "open", "high", "low", "close", "adj_close", "volume"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                f"{path.name} must contain date,open,high,low,close,adj_close,volume."
            )
        return [
            {
                "date": str(row["date"]),
                "open": finite(row["open"]),
                "high": finite(row["high"]),
                "low": finite(row["low"]),
                "close": finite(row["close"]),
                "adjustedClose": finite(row["adj_close"]),
                "volume": finite(row["volume"]),
            }
            for row in reader
        ]


def _candidate_price_paths(directory: Path, symbol: str) -> Iterable[Path]:
    safe = symbol.removeprefix("^").removesuffix(".JK")
    for name in [f"{symbol}.csv", f"{safe}.csv", f"{safe}.JK.csv"]:
        yield directory / name


def load_imported_data(
    universe_path: Path, prices_directory: Path
) -> Tuple[List[UniverseEntry], Dict[str, List[Dict[str, Any]]], List[str]]:
    universe = read_universe_csv(universe_path)
    histories: Dict[str, List[Dict[str, Any]]] = {}
    missing: List[str] = []
    for entry in universe:
        price_path = next(
            (path for path in _candidate_price_paths(prices_directory, entry.symbol) if path.exists()),
            None,
        )
        if not price_path:
            missing.append(entry.symbol)
            continue
        histories[entry.symbol] = read_price_csv(price_path)

    benchmark_path = next(
        (
            path
            for name in ["^JKSE.csv", "JKSE.csv", "COMPOSITE.csv"]
            if (path := prices_directory / name).exists()
        ),
        None,
    )
    if not benchmark_path:
        raise ValueError("Price directory must include ^JKSE.csv, JKSE.csv, or COMPOSITE.csv.")
    histories["^JKSE"] = read_price_csv(benchmark_path)
    return universe, histories, missing


def _download_yahoo_history(symbol: str, period: str) -> List[Dict[str, Any]]:
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={
            "range": period,
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        },
        headers={"User-Agent": "HexInc/2.0"},
        timeout=30,
    )
    response.raise_for_status()
    try:
        result = response.json()["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Yahoo returned invalid history for {symbol}.") from exc

    bars: List[Dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        close = _at(quote.get("close"), index)
        if close is None:
            continue
        bars.append(
            {
                "date": datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat(),
                "open": _at(quote.get("open"), index),
                "high": _at(quote.get("high"), index),
                "low": _at(quote.get("low"), index),
                "close": close,
                "adjustedClose": _at(adjusted, index) or close,
                "volume": _at(quote.get("volume"), index),
            }
        )
    return bars


def _at(values: Optional[List[Any]], index: int) -> Any:
    if not values or index >= len(values):
        return None
    return values[index]


def _cached_yahoo_history(
    symbol: str, period: str, cache_directory: Path
) -> List[Dict[str, Any]]:
    cache_directory.mkdir(parents=True, exist_ok=True)
    safe_symbol = symbol.replace("^", "INDEX-").replace("/", "-")
    path = cache_directory / f"{safe_symbol}-{period}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    bars = _download_yahoo_history(symbol, period)
    path.write_text(json.dumps(bars, separators=(",", ":")), encoding="utf-8")
    return bars


def load_smoke_data(
    limit: int, period: str, cache_directory: Path
) -> Tuple[List[UniverseEntry], Dict[str, List[Dict[str, Any]]], List[str]]:
    stocks = TradingViewProvider().fetch_stocks()
    ranked = sorted(
        stocks,
        key=lambda item: -(
            (finite(item.get("price")) or 0)
            * (finite(item.get("averageVolume10d")) or 0)
        ),
    )
    universe = [
        UniverseEntry(
            symbol=str(item["symbol"]),
            sector=str(item.get("sector") or "Unclassified"),
        )
        for item in ranked[:limit]
    ]
    histories: Dict[str, List[Dict[str, Any]]] = {}
    missing: List[str] = []
    for entry in universe:
        try:
            histories[entry.symbol] = _cached_yahoo_history(
                f"{entry.symbol}.JK", period, cache_directory
            )
        except (requests.RequestException, ValueError):
            missing.append(entry.symbol)
    histories["^JKSE"] = _cached_yahoo_history("^JKSE", period, cache_directory)
    return universe, histories, missing


def _legacy_score(
    stock: Dict[str, Any], liquidity_percentile: float
) -> Dict[str, Any]:
    relative_volume = finite(stock.get("relativeVolume"))
    rsi = finite(stock.get("rsi"))
    macd = finite(stock.get("macd"))
    macd_signal = finite(stock.get("macdSignal"))
    price = finite(stock.get("price"))
    ema20 = finite(stock.get("ema20"))
    ema50 = finite(stock.get("ema50"))
    ema200 = finite(stock.get("ema200"))
    return1m = finite(stock.get("return1m"))
    return3m = finite(stock.get("return3m"))
    volatility = finite(stock.get("volatility"))
    liquidity = liquidity_percentile * 25 + (
        max(0.0, min(relative_volume / 2, 1.0)) * 10
        if relative_volume is not None
        else 4
    )
    trend = sum(
        points
        for average, points in [(ema20, 7.5), (ema50, 7.5), (ema200, 7.5)]
        if price is not None and average is not None and price > average
    )
    if ema20 is not None and ema50 is not None and ema20 > ema50:
        trend += 7.5
    momentum = 0.0
    if rsi is not None:
        momentum += 7 if 50 <= rsi <= 65 else 4 if 40 <= rsi <= 72 else 0
    if macd is not None and macd_signal is not None and macd > macd_signal:
        momentum += 6
    if return1m is not None:
        momentum += max(0.0, min((return1m + 5) / 20, 1.0)) * 5
    if return3m is not None:
        momentum += max(0.0, min((return3m + 10) / 40, 1.0)) * 7
    if volatility is None:
        risk = 4.0
    elif 1 <= volatility <= 4:
        risk = 10.0
    elif volatility < 1:
        risk = 7.0
    elif volatility <= 6:
        risk = 6.0
    elif volatility <= 9:
        risk = 3.0
    else:
        risk = 0.0
    total = round(min(100.0, liquidity + trend + momentum + risk), 1)
    return {
        **stock,
        "score": total,
        "signal": "Strong" if total >= 75 else "Constructive" if total >= 60 else "Mixed",
    }


def _rank_legacy(stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for item in stocks:
        stock = dict(item)
        price = finite(stock.get("price"))
        volume = finite(stock.get("averageVolume10d"))
        stock["averageTradedValue"] = (
            price * volume if price is not None and volume is not None else None
        )
        if eligible(stock):
            prepared.append(stock)
    values = [float(item["averageTradedValue"]) for item in prepared]
    ranks = percentile_ranks(values)
    return [
        _legacy_score(item, ranks.get(float(item["averageTradedValue"]), 0.0))
        for item in prepared
    ]


def _market_context(feature: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not feature:
        return {
            "symbol": "COMPOSITE",
            "name": "IDX Composite Index",
            "available": False,
            "bullish": False,
            "return1m": None,
            "return3m": None,
        }
    price = finite(feature.get("price"))
    ema200 = finite(feature.get("ema200"))
    available = price is not None and ema200 is not None
    return {
        "symbol": "COMPOSITE",
        "name": "IDX Composite Index",
        "price": price,
        "ema200": ema200,
        "return1m": feature.get("return1m"),
        "return3m": feature.get("return3m"),
        "available": available,
        "bullish": bool(available and price > ema200),
    }


def _event_metrics(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    labeled = [event for event in events if event.get("excessReturn") is not None]
    if not labeled:
        return {
            "eventCount": len(events),
            "labeledEventCount": 0,
            "falseSignalRate": None,
            "precision": None,
            "absoluteHitRate": None,
            "meanExcessReturn": None,
            "medianExcessReturn": None,
            "meanAdverseExcursion": None,
        }
    false_count = sum(bool(event["falseSignal"]) for event in labeled)
    absolute_hits = sum((event["netReturn"] or 0) > 0 for event in labeled)
    excess = [float(event["excessReturn"]) for event in labeled]
    excursions = [
        float(event["adverseExcursion"])
        for event in labeled
        if event.get("adverseExcursion") is not None
    ]
    return {
        "eventCount": len(events),
        "labeledEventCount": len(labeled),
        "falseSignalRate": round(false_count / len(labeled), 4),
        "precision": round(1 - false_count / len(labeled), 4),
        "absoluteHitRate": round(absolute_hits / len(labeled), 4),
        "meanExcessReturn": round(mean(excess), 4),
        "medianExcessReturn": round(median(excess), 4),
        "meanAdverseExcursion": round(mean(excursions), 4) if excursions else None,
    }


def _breakdown(events: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(str(event.get(key) or "Unknown"), []).append(event)
    return {name: _event_metrics(items) for name, items in sorted(grouped.items())}


def _label_events(
    events: List[Dict[str, Any]],
    adjusted_histories: Dict[str, List[Dict[str, Any]]],
    holding_period: int,
    costs: float,
) -> None:
    benchmark = adjusted_histories["^JKSE"]
    benchmark_by_date = {str(bar["date"]): finite(bar.get("close")) for bar in benchmark}
    for event in events:
        bars = adjusted_histories.get(event["symbol"], [])
        indices = {str(bar["date"]): index for index, bar in enumerate(bars)}
        start_index = indices.get(event["date"])
        if start_index is None or start_index + holding_period >= len(bars):
            continue
        future_index = start_index + holding_period
        start = finite(bars[start_index].get("close"))
        future = finite(bars[future_index].get("close"))
        future_date = str(bars[future_index]["date"])
        market_start = benchmark_by_date.get(event["date"])
        market_future = benchmark_by_date.get(future_date)
        if None in (start, future, market_start, market_future) or start == 0 or market_start == 0:
            continue
        net_return = future / start - 1 - costs  # type: ignore[operator]
        market_return = market_future / market_start - 1  # type: ignore[operator]
        lows = [
            finite(bar.get("low"))
            for bar in bars[start_index + 1 : future_index + 1]
        ]
        valid_lows = [value for value in lows if value is not None]
        event.update(
            {
                "exitDate": future_date,
                "netReturn": round(net_return, 6),
                "marketReturn": round(market_return, 6),
                "excessReturn": round(net_return - market_return, 6),
                "falseSignal": net_return <= market_return,
                "adverseExcursion": (
                    round(min(valid_lows) / start - 1, 6) if valid_lows else None
                ),
            }
        )


def run_backtest(
    universe: List[UniverseEntry],
    histories: Dict[str, List[Dict[str, Any]]],
    *,
    survivorship_biased: bool,
    missing_symbols: Optional[List[str]] = None,
    holding_period: int = 20,
    costs: float = 0.005,
) -> Dict[str, Any]:
    if "^JKSE" not in histories:
        raise ValueError("IDX Composite history (^JKSE) is required.")
    adjusted_histories = {
        symbol: adjusted_bars(bars) for symbol, bars in histories.items()
    }
    features: Dict[str, Dict[str, Dict[str, Any]]] = {}
    sector_by_symbol = {entry.symbol: entry.sector for entry in universe}
    for symbol, bars in adjusted_histories.items():
        rows = build_feature_rows(
            bars,
            symbol,
            "Market" if symbol == "^JKSE" else sector_by_symbol.get(symbol, "Unclassified"),
        )
        features[symbol] = {str(row["date"]): row for row in rows}

    sessions = sorted(
        {
            session
            for symbol, rows in features.items()
            if symbol != "^JKSE"
            for session in rows
        }
    )
    previous_signals: Dict[str, Dict[str, str]] = {"v1": {}, "v2": {}}
    events: Dict[str, List[Dict[str, Any]]] = {"v1": [], "v2": []}
    entries_by_symbol: Dict[str, List[UniverseEntry]] = {}
    for entry in universe:
        entries_by_symbol.setdefault(entry.symbol, []).append(entry)

    for session in sessions:
        daily: List[Dict[str, Any]] = []
        for symbol, entries in entries_by_symbol.items():
            if not any(entry.active(session) for entry in entries):
                continue
            feature = features.get(symbol, {}).get(session)
            if feature:
                daily.append(feature)
        if not daily:
            continue
        market = _market_context(features.get("^JKSE", {}).get(session))
        v2_ranked, _ = rank_stocks(daily, market)
        v1_ranked = _rank_legacy(daily)
        for model, ranked in [("v1", v1_ranked), ("v2", v2_ranked)]:
            present = {str(stock["symbol"]) for stock in ranked}
            for symbol in list(previous_signals[model]):
                if symbol not in present:
                    previous_signals[model][symbol] = "Mixed"
            for stock in ranked:
                symbol = str(stock["symbol"])
                signal = str(stock["signal"])
                previous = previous_signals[model].get(symbol, "Mixed")
                if signal == "Strong" and previous != "Strong":
                    events[model].append(
                        {
                            "model": model,
                            "date": session,
                            "year": session[:4],
                            "symbol": symbol,
                            "sector": stock.get("sector") or "Unclassified",
                            "regime": "Bullish" if market["bullish"] else "Defensive",
                            "score": stock["score"],
                        }
                    )
                previous_signals[model][symbol] = signal

    for model_events in events.values():
        _label_events(model_events, adjusted_histories, holding_period, costs)

    warnings = []
    if survivorship_biased:
        warnings.append(
            "Current-universe smoke mode is survivorship-biased and is not validation."
        )
    if missing_symbols:
        warnings.append(
            f"Missing usable histories for {len(missing_symbols)} symbol(s)."
        )
    models: Dict[str, Any] = {}
    for model, model_events in events.items():
        models[model] = {
            "metrics": _event_metrics(model_events),
            "byYear": _breakdown(model_events, "year"),
            "byRegime": _breakdown(model_events, "regime"),
            "bySector": _breakdown(model_events, "sector"),
            "events": model_events,
        }
    histories_with_actions = sum(
        any(
            finite(bar.get("adjustedClose")) is not None
            and finite(bar.get("close")) is not None
            and not math.isclose(
                float(bar["adjustedClose"]), float(bar["close"]), rel_tol=1e-9
            )
            for bar in histories.get(symbol, [])
        )
        for symbol in histories
        if symbol != "^JKSE"
    )
    return {
        "model": "HexInc Conservative Signal Model v2",
        "validationClaim": not survivorship_biased and not missing_symbols,
        "falseSignalDefinition": (
            f"{holding_period}-session adjusted stock return minus {costs:.1%} "
            "costs fails to beat the matching IDX Composite return."
        ),
        "universeSource": (
            "current TradingView universe"
            if survivorship_biased
            else "imported historical membership"
        ),
        "survivorshipBiased": survivorship_biased,
        "warnings": warnings,
        "coverage": {
            "universeEntries": len(universe),
            "symbolsWithHistory": len(
                [symbol for symbol in histories if symbol != "^JKSE"]
            ),
            "missingSymbols": sorted(missing_symbols or []),
            "corporateActionAdjustedHistories": histories_with_actions,
            "firstSession": sessions[0] if sessions else None,
            "lastSession": sessions[-1] if sessions else None,
        },
        "models": models,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backtest HexInc v1 versus v2.")
    parser.add_argument("--universe-csv", type=Path)
    parser.add_argument("--prices-dir", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--period", default="5y")
    parser.add_argument("--cache-dir", type=Path, default=Path(".backtest-cache"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".backtest-results") / "report.json",
    )
    parser.add_argument("--holding-period", type=int, default=20)
    parser.add_argument("--costs", type=float, default=0.005)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    imported = bool(args.universe_csv or args.prices_dir)
    if imported and not (args.universe_csv and args.prices_dir):
        raise SystemExit("--universe-csv and --prices-dir must be supplied together.")
    if imported:
        universe, histories, missing = load_imported_data(
            args.universe_csv, args.prices_dir
        )
    else:
        universe, histories, missing = load_smoke_data(
            max(1, args.limit), args.period, args.cache_dir
        )
    report = run_backtest(
        universe,
        histories,
        survivorship_biased=not imported,
        missing_symbols=missing,
        holding_period=max(1, args.holding_period),
        costs=max(0.0, args.costs),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    summary = {
        "output": str(args.output),
        "validationClaim": report["validationClaim"],
        "warnings": report["warnings"],
        "v1": report["models"]["v1"]["metrics"],
        "v2": report["models"]["v2"]["metrics"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
