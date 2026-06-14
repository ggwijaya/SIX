# HexInc Conservative Signal Model v2

HexInc ranks eligible Indonesia Stock Exchange equities using end-of-session technical, liquidity, market-regime, and relative-strength data. It is a research screener, not a return forecast or trading instruction.

## Eligibility

- Primary common equity
- Positive price
- No warrant or rights suffix
- Estimated 10-session average traded value of at least IDR 500 million

Average traded value is the latest price multiplied by 10-session average volume.

## Score

The pre-deduction score is capped at 100:

| Component | Maximum | Inputs |
| --- | ---: | --- |
| Liquidity and participation | 20 | Traded-value percentile, relative volume, Chaikin Money Flow |
| Trend | 30 | Price/EMA20/EMA50/EMA200 alignment, three EMA slopes, three-session persistence |
| Momentum | 20 | RSI14, MACD histogram state and slope, 1M and 3M returns |
| Relative strength | 20 | 1M and 3M excess return versus IHSG and the stock's sector median |
| Risk quality | 10 | ATR14 as a percentage of price |

Sector comparisons require at least five eligible stocks with complete 1M and 3M returns. Otherwise sector points are unavailable and the stock cannot receive a Strong signal.

## Deductions

The model subtracts points for:

- Price below EMA200
- Bearish or unavailable IHSG regime
- RSI above 75, above 80, or below 35
- ATR above 6% or 9% of price
- Trailing IHSG over both 1M and 3M
- Trailing an eligible sector over both 1M and 3M
- Relative volume of at least 1.2 with negative Chaikin Money Flow
- 3M return below -10%

The `penalties` score component is negative and capped so the final score cannot fall below zero.

## Signal Gates

### Strong

All of the following are required:

- Score of at least 75
- IHSG above its EMA200
- `price > EMA20 > EMA50 > EMA200` for the current and previous two sessions
- EMA20, EMA50, and EMA200 each rising for three sessions
- Positive 1M and 3M excess return versus IHSG
- Positive 1M and 3M excess return versus an eligible sector
- Positive Chaikin Money Flow and either relative volume of at least 1.0 or a positive daily return
- RSI between 35 and 75
- ATR no greater than 6% of price
- Complete lagged, benchmark, and volume-confirmation data

### Constructive

- Score of at least 60
- Bullish EMA alignment for the current and previous session
- Available IHSG, lagged, and volume-confirmation inputs
- Price above EMA200, RSI between 35 and 75, and ATR no greater than 6%

All other stocks are Mixed. Missing required data fails closed rather than being interpreted as neutral.

## Market Context

The live screener requests IDX Composite data separately from the stock universe. If that request fails, ranking continues with a warning, the market regime is marked unavailable, and Strong signals are suppressed.

## Backtesting

The local backtester reconstructs indicators chronologically from adjusted OHLCV data and evaluates only transitions into Strong. It compares legacy v1 and conservative v2.

A false signal is a new Strong event whose adjusted 20-session stock return, after 0.5% total costs, does not beat the matching IDX Composite return.

Reports include:

- False-signal rate and precision
- Absolute hit rate
- Mean and median excess return
- Mean adverse excursion
- Event and labeled-event counts
- Breakdowns by year, market regime, and sector
- Coverage, missing histories, adjustment usage, and bias warnings

The default Yahoo smoke mode uses today's listed universe and is survivorship-biased. Its report explicitly sets `validationClaim` to false. A credible validation requires historical membership dates and delisted-stock prices through the CSV import interface.

## Data Limitations

TradingView and Yahoo endpoints are unofficial and can change. Provider calculations may differ slightly from locally reconstructed indicators because of session calendars, adjustment conventions, and initialization rules. Scores should be validated periodically and should not be treated as financial advice.
