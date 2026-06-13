# IDX Signal Desk

A no-key technical and liquidity screener for Indonesia Stock Exchange equities.

## Run locally

```powershell
python -m pip install -r requirements-dev.txt
python app.py
```

Open `http://127.0.0.1:5000`.

The app uses TradingView's public Indonesia scanner and Yahoo Finance's chart endpoint. Both are unofficial interfaces and can change. Screener results are cached for 15 minutes; stock histories are cached for one hour.

## Test

```powershell
python -m pytest -q
```

## Deploy to Vercel

1. Push this directory to a GitHub repository.
2. Sign in to Vercel and choose **Add New > Project**.
3. Import the GitHub repository.
4. Leave the framework and build settings on their detected defaults.
5. Select the Hobby plan and deploy.
6. Confirm `/api/health` returns `{"status": "ok"}` and open the generated `vercel.app` URL.

Vercel detects the root `app.py` as a Flask application. `vercel.json` places the Python function in Singapore, while files under `public/` are served through Vercel's CDN.

Screener responses are cached at the CDN for 15 minutes and stock histories for one hour. The in-process cache and one-minute refresh limiter are best-effort because separate serverless instances do not share memory.

## Score

- Liquidity: 35 points
- Trend: 30 points
- Momentum: 25 points
- Risk profile: 10 points

Only primary equities with positive prices and at least IDR 500 million in estimated 10-day average traded value qualify.
