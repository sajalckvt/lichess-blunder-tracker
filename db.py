"""
SQLite storage for blunder-tracker.

Two tables:
  - games: one row per analyzed game
  - blunders: one row per blunder/mistake/inaccuracy
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path("blunders.db")


def get_db(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _create_tables(conn)
    return conn


def _create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS games (
            game_id       TEXT PRIMARY KEY,
            date          INTEGER,
            speed         TEXT,
            opening       TEXT,
            opening_eco   TEXT,
            color         TEXT,
            result        TEXT,
            opponent      TEXT,
            opponent_rating INTEGER,
            player_rating INTEGER,
            total_moves   INTEGER,
            blunder_count INTEGER,
            mistake_count INTEGER,
            inaccuracy_count INTEGER,
            game_url      TEXT,
            fetched_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS blunders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id       TEXT NOT NULL,
            opening       TEXT,
            speed         TEXT,
            move_num      INTEGER,
            half_move     INTEGER,
            phase         TEXT,
            color         TEXT,
            played_move   TEXT,
            best_move     TEXT,
            cp_loss       INTEGER,
            eval_before   INTEGER,
            eval_after    INTEGER,
            mate_before   INTEGER,
            mate_after    INTEGER,
            severity      TEXT,
            lichess_judgment TEXT,
            game_result   TEXT,
            game_url      TEXT,
            opponent      TEXT,
            FOREIGN KEY (game_id) REFERENCES games(game_id)
        );

        CREATE INDEX IF NOT EXISTS idx_blunders_game ON blunders(game_id);
        CREATE INDEX IF NOT EXISTS idx_blunders_severity ON blunders(severity);
        CREATE INDEX IF NOT EXISTS idx_blunders_phase ON blunders(phase);
        CREATE INDEX IF NOT EXISTS idx_blunders_opening ON blunders(opening);
    """)
    conn.commit()


def save_game(conn, summary):
    """Insert or replace a game summary."""
    conn.execute("""
        INSERT OR REPLACE INTO games
        (game_id, date, speed, opening, opening_eco, color, result,
         opponent, opponent_rating, player_rating, total_moves,
         blunder_count, mistake_count, inaccuracy_count, game_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        summary.game_id, summary.date, summary.speed, summary.opening,
        summary.opening_eco, summary.color, summary.result, summary.opponent,
        summary.opponent_rating, summary.player_rating, summary.total_moves,
        summary.blunder_count, summary.mistake_count, summary.inaccuracy_count,
        summary.game_url,
    ))


def save_blunders(conn, blunders):
    """Insert blunders for a game (deletes old ones first)."""
    if not blunders:
        return
    # Remove old blunders for these games
    game_ids = set(b.game_id for b in blunders)
    for gid in game_ids:
        conn.execute("DELETE FROM blunders WHERE game_id = ?", (gid,))

    conn.executemany("""
        INSERT INTO blunders
        (game_id, opening, speed, move_num, half_move, phase, color,
         played_move, best_move, cp_loss, eval_before, eval_after,
         mate_before, mate_after, severity, lichess_judgment,
         game_result, game_url, opponent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(
        b.game_id, b.opening, b.speed, b.move_num, b.half_move,
        b.phase, b.color, b.played_move, b.best_move, b.cp_loss,
        b.eval_before, b.eval_after, b.mate_before, b.mate_after,
        b.severity, b.lichess_judgment, b.game_result, b.game_url,
        b.opponent,
    ) for b in blunders])


def save_all(summaries, all_blunders, db_path=None):
    """Persist a full analysis run."""
    conn = get_db(db_path)
    for s in summaries:
        save_game(conn, s)
    save_blunders(conn, all_blunders)
    conn.commit()
    conn.close()


# ── Query helpers ─────────────────────────────────────────

def get_stats(db_path=None):
    """Return aggregate stats from the database."""
    conn = get_db(db_path)

    stats = {}
    stats["total_games"] = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    stats["total_blunders"] = conn.execute(
        "SELECT COUNT(*) FROM blunders WHERE severity='blunder'"
    ).fetchone()[0]
    stats["total_mistakes"] = conn.execute(
        "SELECT COUNT(*) FROM blunders WHERE severity='mistake'"
    ).fetchone()[0]
    stats["total_inaccuracies"] = conn.execute(
        "SELECT COUNT(*) FROM blunders WHERE severity='inaccuracy'"
    ).fetchone()[0]

    # Win/loss/draw
    for result in ("win", "loss", "draw"):
        stats[f"games_{result}"] = conn.execute(
            "SELECT COUNT(*) FROM games WHERE result=?", (result,)
        ).fetchone()[0]

    # Blunders by phase
    for phase in ("opening", "middlegame", "endgame"):
        stats[f"blunders_{phase}"] = conn.execute(
            "SELECT COUNT(*) FROM blunders WHERE severity='blunder' AND phase=?", (phase,)
        ).fetchone()[0]

    # Top blunder openings
    stats["blunders_by_opening"] = conn.execute("""
        SELECT opening, COUNT(*) as cnt 
        FROM blunders WHERE severity='blunder'
        GROUP BY opening ORDER BY cnt DESC LIMIT 10
    """).fetchall()

    # Worst blunders
    stats["worst_blunders"] = conn.execute("""
        SELECT game_id, move_num, played_move, best_move, cp_loss, 
               opening, phase, game_url, opponent
        FROM blunders 
        WHERE severity='blunder' AND cp_loss IS NOT NULL
        ORDER BY cp_loss DESC LIMIT 10
    """).fetchall()

    # Avg blunders per game
    row = conn.execute("""
        SELECT AVG(blunder_count) FROM games WHERE blunder_count IS NOT NULL
    """).fetchone()
    stats["avg_blunders_per_game"] = round(row[0], 1) if row[0] else 0

    conn.close()
    return stats


def get_blunders_for_report(db_path=None):
    """Get all blunders grouped by theme/opening for the report."""
    conn = get_db(db_path)
    
    rows = conn.execute("""
        SELECT b.*, g.player_rating, g.opponent_rating, g.date
        FROM blunders b
        JOIN games g ON b.game_id = g.game_id
        WHERE b.severity = 'blunder'
        ORDER BY b.cp_loss DESC
    """).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]
