# StockDash — streamlined news view (VS Code + Vercel)

The **News** page has been redesigned for fast reading. Each article row shows only the **publication timestamp, clickable headline, and compact Rhea-AI impact/sentiment**. Long Rhea summaries, tags, EOD moves, quote cards, and prominent source debug information no longer clutter the news feed. The article itself remains one click away.

This release changes only `public/index.html` (plus this README). The Python StockTitan scraper, API, Trading Halts, Stock Splits, and deployment setup are unchanged.

The *More options* disclosure retains manual HTML preview, source diagnostics, oldest-first sorting, and optional additional news sources. The default remains **StockTitan ticker page first**, with RSS fallback on failure and 20-second auto-refresh while the tab is visible. Ratings are provided by StockTitan; absence of a rating is displayed as 'Not available' rather than guessed.

## Local use (VS Code on Windows)

1. Open this extracted project folder in VS Code.
2. Run `py -3 launch.py` in its integrated terminal, or double-click `start-stockdash.bat`.
3. Open `http://127.0.0.1:8000/`. Do not open `public/index.html` as a `file://` URL: the page needs the Python API server.

## Vercel

Push the folder contents to a GitHub repository and deploy on Vercel using the **Other** framework preset. The existing `vercel.json`, `api/`, and `public/` routing remain as before. If you already have this StockDash deployed, you can update **just `public/index.html`** and redeploy.

## Tests

Run `py -3 -m unittest discover -p "test_*.py"` on Windows or `python3 -m unittest discover -p "test_*.py"` on other systems. Live StockTitan connectivity and site access restrictions vary.

## Data caveat

The code makes automated requests to StockTitan's public ticker HTML. StockTitan's terms restrict unauthorized scraping, even for personal use; this code does not bypass authentication, CAPTCHAs, or bot protection. When direct requests fail, the backend uses official RSS and may not have Rhea-AI ratings for the ticker.
