# blunder.report

Track your chess blunders, find patterns, get targeted puzzle recommendations.

Fetches your Lichess games, detects every blunder using Lichess's analysis, groups them by opening and game phase, and links you to the exact puzzles you need to train.

## Deploy to Railway (recommended, free tier)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
3. Railway auto-detects the Dockerfile — no config needed
4. Your app is live at `https://your-app.up.railway.app`

## Deploy to Render (free tier)

1. Push to GitHub
2. Go to [render.com](https://render.com) → New Web Service → connect your repo
3. Set **Build Command**: `pip install -r requirements.txt`
4. Set **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`

## Run locally

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/blunder-report.git
cd blunder-report

# Install
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run
python app.py
```

Open http://localhost:5000 in your browser.

## How it works

1. Enter your Lichess username, pick how many games to analyze, choose puzzle difficulty
2. The server fetches your games from the Lichess API (public, no key needed)
3. Games with Lichess computer analysis are scanned for blunders, mistakes, and inaccuracies
4. A report is generated with:
   - Stats: blunder count, win rate, worst game phase
   - Blunders grouped by opening — each links to the exact move in your Lichess game
   - Your worst blunders ranked by centipawn loss
   - Training recommendations with direct links to Lichess puzzles at your chosen difficulty
   - Full game table with results and error counts

## Limitations

- Only games that have been computer-analyzed on Lichess are included (~46% for most players)
- To increase coverage, click "Request computer analysis" on your recent games at lichess.org
- Future: local Stockfish analysis for 100% coverage

## Project structure

```
app.py              — Flask web server
config.py           — thresholds, puzzle theme mapping
lichess_client.py   — Lichess API wrapper
blunder_detector.py — blunder detection engine
db.py               — SQLite storage
report.py           — HTML report generator
templates/index.html — landing page
Dockerfile          — container build
Procfile            — Railway/Heroku start command
requirements.txt    — Python dependencies
```

## License

MIT
