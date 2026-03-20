"""
blunder.report — web app

Flask server that fetches Lichess games, analyzes blunders,
and renders the report in the browser.
"""

import os
import time
import tempfile
from flask import Flask, render_template, request, Response
from lichess_client import LichessClient
from blunder_detector import analyze_all
from db import save_all, get_db, get_stats, get_blunders_for_report
from report import generate_report_html

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/report", methods=["POST"])
def report():
    username = request.form.get("username", "").strip()
    game_count = int(request.form.get("games", 50))
    difficulty = request.form.get("difficulty", "normal")

    if not username:
        return render_template("index.html", error="Please enter a username.")

    try:
        # Use a temp DB per request so concurrent users don't collide
        db_path = os.path.join(tempfile.gettempdir(), f"blunders_{username}_{int(time.time())}.db")

        # 1. Fetch
        client = LichessClient()
        games, skipped = client.get_games(username, max_games=game_count)

        if not games:
            return render_template(
                "index.html",
                error=f"No analyzed games found for @{username}. "
                      f"({skipped} games were skipped because they lack Lichess analysis.) "
                      f"Try requesting computer analysis on lichess.org for your recent games.",
                username=username,
            )

        # 2. Analyze
        summaries, blunders = analyze_all(games, username)

        # 3. Store
        save_all(summaries, blunders, db_path=db_path)

        # 4. Generate HTML
        html = generate_report_html(username, db_path=db_path, difficulty=difficulty)

        # Clean up temp DB
        try:
            os.remove(db_path)
        except OSError:
            pass

        return Response(html, mimetype="text/html")

    except Exception as e:
        return render_template(
            "index.html",
            error=f"Something went wrong: {str(e)}",
            username=username,
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
