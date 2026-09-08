# THYSMY Fundamental Web V2.2

V2 automatically reads the next important US economic release and no longer requires manual Forecast/Previous entry.

## Data sources

- Economic calendar: BiQuote public API (no API key)
- Live XAUUSD quote: BiQuote public API (no API key)
- Global headline context: GDELT DOC 2.0 (no API key)

## Features

- Auto-detect next recognized USD high-impact event
- Auto Forecast / Previous
- Groups simultaneous releases (e.g. NFP + unemployment + wages)
- 14-day macro context using released Actual vs Forecast
- XAU BUY / SELL / NEUTRAL
- Context Strength %
- Spike Potential %
- ONE-WAY %
- TWO-WAY / WHIPSAW %
- Live XAUUSD quote
- Countdown to next release
- GDELT global context + 429 cooldown/cache
- Mobile responsive
- Read-only analysis; no trade execution

## Run

Python 3.11+ recommended.

Windows:
1. Extract ZIP
2. Double-click `start_windows.bat`
3. Open http://127.0.0.1:8000

Or terminal:

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Phone on same Wi-Fi

Open your computer LAN IP on port 8000, for example:

```text
http://192.168.1.20:8000
```

## Docker

```bash
docker build -t thysmy-v2 .
docker run --rm -p 8000:8000 thysmy-v2
```

Then open http://127.0.0.1:8000

## Notes

The percentages are heuristic context scores, not calibrated probabilities or guarantees.
For production/public hosting, add authentication, persistent database, monitoring and a fallback calendar provider.


## V2.2 fix
- Uses `/api/calendar/upcoming` for next-news detection.
- Falls back to the date-range calendar.
- XAU price/global status render even if news lookup fails.
- `/api/diagnostics` shows source status and row counts.


## V2.2 fix

The app now creates the `data` cache folder automatically, preventing `FileNotFoundError` on fresh ZIP extraction.


## V2.3 Fast Start fix

Windows starter has been rewritten:
- skips `pip install` when FastAPI/Uvicorn/Requests are already installed;
- uses `python -m uvicorn` instead of `uvicorn.exe`;
- removes `uvicorn[standard]` to avoid unnecessary compiled extras;
- opens the browser automatically;
- keeps the command window open if startup fails;
- includes `QUICK_START_WINDOWS.bat` as an emergency fast launcher.

Normal use: double-click `start_windows.bat`.


## V2.4 Windows Python launcher fix

This version prefers the working `python` command first.
It only falls back to `python3` / `py -3` if needed.
This avoids the broken `py` launcher error:
`The system cannot execute the specified program.`
