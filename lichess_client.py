"""
Lichess API client — fetches games and user data.
"""

import requests
import json
from config import LICHESS_BASE


class LichessClient:
    def __init__(self, token=None):
        self.token = token
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def get_user(self, username):
        """Fetch user profile."""
        r = self.session.get(
            f"{LICHESS_BASE}/user/{username}",
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        return r.json()

    def get_games(self, username, max_games=50, speed=None, with_evals=True):
        """
        Fetch recent games with optional analysis data.
        Returns list of game dicts. Only games WITH analysis are
        returned when with_evals=True (others are noted as skipped).
        """
        params = {
            "max": max_games,
            "evals": "true",
            "opening": "true",
            "moves": "true",
            "clocks": "true",
        }
        if speed:
            params["perfType"] = speed

        r = self.session.get(
            f"{LICHESS_BASE}/games/user/{username}",
            params=params,
            headers={"Accept": "application/x-ndjson"},
            stream=True,
        )
        r.raise_for_status()

        games = []
        skipped = 0
        for line in r.iter_lines():
            if line:
                g = json.loads(line)
                if with_evals and "analysis" not in g:
                    skipped += 1
                    continue
                games.append(g)

        return games, skipped

    def get_games_by_ids(self, game_ids):
        """Fetch specific games by ID list."""
        r = self.session.post(
            f"{LICHESS_BASE}/games/export/_ids",
            data=",".join(game_ids),
            params={"evals": "true", "opening": "true", "moves": "true", "clocks": "true"},
            headers={
                "Accept": "application/x-ndjson",
                "Content-Type": "text/plain",
            },
            stream=True,
        )
        r.raise_for_status()

        games = []
        for line in r.iter_lines():
            if line:
                games.append(json.loads(line))
        return games

    def get_rating_history(self, username):
        """Fetch rating history for all time controls."""
        r = self.session.get(
            f"{LICHESS_BASE}/user/{username}/rating-history",
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        return r.json()

    def get_puzzles_by_theme(self, theme, difficulty="normal"):
        """
        Fetch real puzzles from Lichess by theme.
        Returns list of puzzle dicts with id, rating, solution, themes.
        The batch endpoint returns ~15 puzzles personalized to difficulty.
        """
        params = {}
        if difficulty != "normal":
            params["difficulty"] = difficulty
        
        r = self.session.get(
            f"{LICHESS_BASE}/puzzle/batch/{theme}",
            params=params,
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            return []
        
        data = r.json()
        puzzles = []
        for p in data.get("puzzles", []):
            puzzle = p.get("puzzle", {})
            game = p.get("game", {})
            puzzles.append({
                "id": puzzle.get("id", ""),
                "rating": puzzle.get("rating", 0),
                "plays": puzzle.get("plays", 0),
                "solution": puzzle.get("solution", []),
                "themes": puzzle.get("themes", []),
                "fen": game.get("pgn", ""),
                "url": f"https://lichess.org/training/{puzzle.get('id', '')}",
                "moves": len(puzzle.get("solution", [])),
            })
        return puzzles
