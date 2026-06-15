from datetime import date, timedelta

import idx_screener.backtest as backtest
from idx_screener.backtest import UniverseEntry, load_imported_data, run_backtest
from idx_screener.indicators import adjusted_bars, build_feature_rows


def bars(count=260, daily_gain=1.0):
    start = date(2024, 1, 1)
    result = []
    price = 100.0
    for index in range(count):
        price += daily_gain + (0.8 if index % 5 in {0, 1} else -0.35)
        result.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": price - 0.8,
                "high": price + 1.2,
                "low": price - 1.0,
                "close": price,
                "adjustedClose": price,
                "volume": 1_000_000 + index * 1_000,
            }
        )
    return result


def test_feature_rows_do_not_change_when_future_data_is_appended():
    initial = bars(230)
    extended = bars(260)
    first = build_feature_rows(initial, "TEST", "Finance")
    second = build_feature_rows(extended, "TEST", "Finance")
    assert first[-1] == second[len(first) - 1]
    assert first[-1]["ema200"] is not None
    assert first[-1]["cmf"] is not None
    assert first[-1]["atr"] is not None
    assert first[-1]["stochasticK"] is not None
    assert first[-1]["stochasticD"] is not None


def test_universe_membership_dates_are_inclusive():
    entry = UniverseEntry("TEST", "Finance", "2024-02-01", "2024-02-28")
    assert entry.active("2024-02-01")
    assert entry.active("2024-02-28")
    assert not entry.active("2024-01-31")
    assert not entry.active("2024-02-29")


def test_imported_data_contract_and_missing_history(tmp_path):
    universe_path = tmp_path / "universe.csv"
    prices_path = tmp_path / "prices"
    prices_path.mkdir()
    universe_path.write_text(
        "symbol,sector,start_date,end_date\n"
        "AAA,Finance,2024-01-01,2024-12-31\n"
        "MISSING,Energy,,\n",
        encoding="utf-8",
    )
    price_text = (
        "date,open,high,low,close,adj_close,volume\n"
        "2024-01-02,100,105,95,100,50,1000000\n"
    )
    (prices_path / "AAA.csv").write_text(price_text, encoding="utf-8")
    (prices_path / "JKSE.csv").write_text(price_text, encoding="utf-8")

    universe, histories, missing = load_imported_data(
        universe_path, prices_path
    )

    assert [entry.symbol for entry in universe] == ["AAA", "MISSING"]
    assert histories["AAA"][0]["adjustedClose"] == 50
    assert "^JKSE" in histories
    assert missing == ["MISSING"]


def test_event_label_uses_adjusted_prices_20_sessions_and_costs():
    start = date(2024, 1, 1)
    stock = []
    market = []
    for index in range(21):
        session = (start + timedelta(days=index)).isoformat()
        stock.append(
            {
                "date": session,
                "open": 100 if index == 0 else 60,
                "high": 101 if index == 0 else 61,
                "low": 99 if index == 0 else 59,
                "close": 100 if index == 0 else 60,
                "adjustedClose": 50 if index == 0 else 60,
                "volume": 1_000_000,
            }
        )
        market.append(
            {
                "date": session,
                "open": 100 + index / 2,
                "high": 101 + index / 2,
                "low": 99 + index / 2,
                "close": 100 + index / 2,
                "adjustedClose": 100 + index / 2,
                "volume": 1_000_000,
            }
        )
    events = [{"date": stock[0]["date"], "symbol": "AAA"}]

    backtest._label_events(
        events,
        {"AAA": adjusted_bars(stock), "^JKSE": adjusted_bars(market)},
        holding_period=20,
        costs=0.005,
    )

    event = events[0]
    assert event["exitDate"] == stock[20]["date"]
    assert event["netReturn"] == 0.195
    assert event["marketReturn"] == 0.1
    assert event["excessReturn"] == 0.095
    assert event["falseSignal"] is False


def test_backtest_deduplicates_continuous_strong_events(monkeypatch):
    def always_strong(daily, market):
        return (
            [
                {
                    **item,
                    "averageTradedValue": 1_000_000_000,
                    "score": 90,
                    "signal": "Strong",
                    "reversalSetup": {"status": "Recovery Confirmed"},
                }
                for item in daily
            ],
            {"universe": len(daily), "qualifying": len(daily), "excluded": 0},
        )

    monkeypatch.setattr(backtest, "rank_stocks", always_strong)
    monkeypatch.setattr(
        backtest,
        "_rank_legacy",
        lambda daily: [{**item, "score": 90, "signal": "Strong"} for item in daily],
    )
    histories = {"AAA": bars(260, 1.2), "^JKSE": bars(260, 0.4)}
    report = run_backtest(
        [UniverseEntry("AAA", "Finance")],
        histories,
        survivorship_biased=True,
    )
    assert report["models"]["v1"]["metrics"]["eventCount"] == 1
    assert report["models"]["v2"]["metrics"]["eventCount"] == 1
    assert report["recoverySetup"]["metrics"]["eventCount"] == 1
    event = report["models"]["v2"]["events"][0]
    assert event["exitDate"]
    assert event["falseSignal"] is False
    assert report["survivorshipBiased"] is True
    assert report["validationClaim"] is False


def test_report_schema_handles_no_signals():
    histories = {"AAA": bars(230, 0.2), "^JKSE": bars(230, 0.3)}
    report = run_backtest(
        [UniverseEntry("AAA", "Finance")],
        histories,
        survivorship_biased=False,
    )
    assert set(report["models"]) == {"v1", "v2"}
    assert "coverage" in report
    assert "falseSignalDefinition" in report
    assert "recoverySetup" in report
    assert report["models"]["v2"]["metrics"]["eventCount"] >= 0
