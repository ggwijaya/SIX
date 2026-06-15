# HexInc

HexInc is a no-key technical and liquidity screener for Indonesia Stock Exchange equities.

## Run locally

```powershell
python -m pip install -r requirements-dev.txt
python app.py
```

Open `http://127.0.0.1:5000`.

The app uses TradingView's public Indonesia scanner and Yahoo Finance's chart endpoint. Both are unofficial interfaces and can change. Screener results are cached for 15 minutes; stock histories are cached for one hour. See [METHODOLOGY.md](METHODOLOGY.md) for the complete model rules and limitations.

## Backtest

Run a survivorship-biased smoke comparison using the most liquid stocks in the current TradingView universe:

```powershell
python backtest.py --limit 20 --period 5y
```

The report is written to `.backtest-results/report.json`; downloaded Yahoo histories are cached under `.backtest-cache/`.

For a proper historical-universe test, supply membership and adjusted OHLCV files:

```powershell
python backtest.py --universe-csv data/universe.csv --prices-dir data/prices
```

`universe.csv` must contain `symbol,sector,start_date,end_date`. Each price file must contain `date,open,high,low,close,adj_close,volume`, and the directory must include `^JKSE.csv`, `JKSE.csv`, or `COMPOSITE.csv`.

## Score

- Liquidity and directional participation: 20 points
- Trend: 30 points
- Momentum: 20 points
- Relative strength: 20 points
- Risk profile: 10 points

Explicit risk deductions are subtracted from the 100-point pre-deduction score. Strong signals additionally require a bullish IHSG regime, three-session EMA alignment, rising EMA slopes, positive market and sector relative strength, confirmed money flow, RSI no higher than 75, and ATR no higher than 6% of price.

HexInc also reports an oversold recovery timing setup based on RSI and Stochastic confirmation. This diagnostic does not alter scores, rankings, or Strong and Constructive signals.

Only primary equities with positive prices and at least IDR 500 million in estimated 10-day average traded value qualify. This threshold controls the screening universe; it does not guarantee executable capacity for every investor.
