"""
blunder.report — HTML report generator.

Reads from SQLite and produces a single static HTML file
with the dark editorial chess aesthetic.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict
from db import get_db, get_stats, get_blunders_for_report
from config import THEME_MAP


def generate_report(username, db_path=None, output_path=None, difficulty="normal"):
    """Generate a static HTML report from the blunder database."""
    
    conn = get_db(db_path)
    
    # Gather all data
    stats = get_stats(db_path)
    blunders = get_blunders_for_report(db_path)
    
    games = conn.execute("""
        SELECT * FROM games ORDER BY date DESC
    """).fetchall()
    games = [dict(g) for g in games]
    
    # Group blunders by opening
    by_opening = defaultdict(list)
    for b in blunders:
        by_opening[b["opening"]].append(b)
    # Sort openings by blunder count desc
    opening_groups = sorted(by_opening.items(), key=lambda x: -len(x[1]))
    
    # Phase stats
    phase_counts = Counter(b["phase"] for b in blunders)
    
    # Blunders per game distribution
    blunders_per_game = [g["blunder_count"] for g in games]
    avg_blunders = sum(blunders_per_game) / len(blunders_per_game) if blunders_per_game else 0
    
    # Win rate
    total_games = len(games)
    wins = sum(1 for g in games if g["result"] == "win")
    losses = sum(1 for g in games if g["result"] == "loss")
    draws = sum(1 for g in games if g["result"] == "draw")
    win_rate = round(100 * wins / total_games) if total_games else 0
    
    # Worst 10 blunders
    worst = sorted([b for b in blunders if b["cp_loss"] is not None], key=lambda b: -b["cp_loss"])[:10]
    
    # Recent games for the table
    recent_games = games[:20]
    
    # Get ratings
    ratings = [g["player_rating"] for g in games if g["player_rating"]]
    current_rating = ratings[0] if ratings else "?"
    
    conn.close()
    
    # Generate puzzle recommendations based on blunder patterns
    recommendations = _get_recommendations(opening_groups, phase_counts, difficulty)
    worst_phase = phase_counts.most_common(1)[0][0] if phase_counts else "middlegame"
    
    # Fetch real puzzles (deduplicated, max 3 themes)
    from lichess_client import LichessClient
    puzzle_client = LichessClient()
    all_themes = set()
    for rec in recommendations:
        for label, url in rec.get("links", []):
            if "lichess.org/training/" in url:
                all_themes.add(url.split("/training/")[-1].split("?")[0])
    theme_cache = {}
    for theme in list(all_themes)[:3]:
        try:
            theme_cache[theme] = puzzle_client.get_puzzles_by_theme(theme)
        except Exception:
            theme_cache[theme] = []
    for rec in recommendations:
        rec_puzzles, seen = [], set()
        for label, url in rec.get("links", []):
            if "lichess.org/training/" in url:
                for p in theme_cache.get(url.split("/training/")[-1].split("?")[0], []):
                    if p["id"] not in seen and len(rec_puzzles) < 10:
                        rec_puzzles.append(p)
                        seen.add(p["id"])
        rec["puzzles"] = rec_puzzles
    
    # Build HTML
    html = _build_html(
        username=username,
        current_rating=current_rating,
        total_games=total_games,
        wins=wins, losses=losses, draws=draws, win_rate=win_rate,
        total_blunders=len(blunders),
        avg_blunders=avg_blunders,
        phase_counts=phase_counts,
        opening_groups=opening_groups,
        worst=worst,
        recent_games=recent_games,
        recommendations=recommendations,
        difficulty=difficulty,
        worst_phase=worst_phase,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    
    out = Path(output_path or f"report_{username}_{datetime.now().strftime('%Y%m%d')}.html")
    out.write_text(html, encoding="utf-8")
    print(f"  Report saved to: {out}")
    return out




def generate_report_html(username, db_path=None, difficulty="normal"):
    """Return HTML string directly (for web app)."""
    conn = get_db(db_path)
    stats = get_stats(db_path)
    blunders = get_blunders_for_report(db_path)
    games = conn.execute('SELECT * FROM games ORDER BY date DESC').fetchall()
    games = [dict(g) for g in games]
    by_opening = defaultdict(list)
    for b in blunders:
        by_opening[b["opening"]].append(b)
    opening_groups = sorted(by_opening.items(), key=lambda x: -len(x[1]))
    phase_counts = Counter(b["phase"] for b in blunders)
    blunders_per_game = [g["blunder_count"] for g in games]
    avg_blunders = sum(blunders_per_game) / len(blunders_per_game) if blunders_per_game else 0
    total_games = len(games)
    wins = sum(1 for g in games if g["result"] == "win")
    losses = sum(1 for g in games if g["result"] == "loss")
    draws = total_games - wins - losses
    win_rate = round(100 * wins / total_games) if total_games else 0
    worst = sorted([b for b in blunders if b["cp_loss"] is not None], key=lambda b: -b["cp_loss"])[:10]
    recent_games = games[:20]
    ratings = [g["player_rating"] for g in games if g["player_rating"]]
    current_rating = ratings[0] if ratings else "?"
    conn.close()
    max_phase = max(phase_counts.values()) if phase_counts else 1
    recommendations = _get_recommendations(opening_groups, phase_counts, difficulty)
    
    # Fetch real puzzles for recommended themes (deduplicated, max 3 themes)
    from lichess_client import LichessClient
    puzzle_client = LichessClient()
    all_themes = set()
    for rec in recommendations:
        for label, url in rec.get("links", []):
            if "lichess.org/training/" in url:
                theme = url.split("/training/")[-1].split("?")[0]
                all_themes.add(theme)
    
    # Fetch only top 3 themes to keep it fast
    theme_cache = {}
    for theme in list(all_themes)[:3]:
        try:
            theme_cache[theme] = puzzle_client.get_puzzles_by_theme(theme)
        except Exception:
            theme_cache[theme] = []
    
    # Distribute puzzles to recommendations
    for rec in recommendations:
        rec_puzzles = []
        seen_ids = set()
        for label, url in rec.get("links", []):
            if "lichess.org/training/" in url:
                theme = url.split("/training/")[-1].split("?")[0]
                for p in theme_cache.get(theme, []):
                    if p["id"] not in seen_ids and len(rec_puzzles) < 10:
                        rec_puzzles.append(p)
                        seen_ids.add(p["id"])
        rec["puzzles"] = rec_puzzles
    
    worst_phase = phase_counts.most_common(1)[0][0] if phase_counts else "middlegame"
    return _build_html(
        username=username, current_rating=current_rating,
        total_games=total_games, wins=wins, losses=losses, draws=draws,
        win_rate=win_rate, total_blunders=len(blunders),
        avg_blunders=avg_blunders, phase_counts=phase_counts,
        opening_groups=opening_groups, worst=worst,
        recent_games=recent_games, recommendations=recommendations,
        difficulty=difficulty, worst_phase=worst_phase,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

def _puzzle_url(theme, difficulty="normal"):
    """Build a Lichess puzzle URL with optional difficulty."""
    base = THEME_MAP.get(theme, f"https://lichess.org/training/{theme}")
    if difficulty == "normal":
        return base
    return f"{base}?difficulty={difficulty}"


def _get_recommendations(opening_groups, phase_counts, difficulty="normal"):
    """Generate puzzle training recommendations from blunder patterns."""
    recs = []
    
    # Phase-based
    phases = sorted(phase_counts.items(), key=lambda x: -x[1])
    if phases:
        worst_phase = phases[0][0]
        if worst_phase == "endgame":
            recs.append({
                "title": "Endgame training",
                "reason": f"{phase_counts['endgame']} blunders in the endgame — your biggest leak",
                "links": [
                    ("Endgame puzzles", _puzzle_url("endgame", difficulty)),
                    ("Pawn endgames", _puzzle_url("pawnEndgame", difficulty)),
                    ("Rook endgames", _puzzle_url("rookEndgame", difficulty)),
                ],
            })
        elif worst_phase == "middlegame":
            recs.append({
                "title": "Middlegame tactics",
                "reason": f"{phase_counts['middlegame']} blunders in the middlegame",
                "links": [
                    ("Middlegame puzzles", _puzzle_url("middlegame", difficulty)),
                    ("Forks", _puzzle_url("fork", difficulty)),
                    ("Pins", _puzzle_url("pin", difficulty)),
                    ("Discovered attacks", _puzzle_url("discoveredAttack", difficulty)),
                ],
            })
        elif worst_phase == "opening":
            recs.append({
                "title": "Opening preparation",
                "reason": f"{phase_counts['opening']} blunders in the opening",
                "links": [
                    ("Opening puzzles", _puzzle_url("opening", difficulty)),
                ],
            })
        
        # Add secondary phase if significant
        if len(phases) >= 2 and phases[1][1] >= 5:
            sec_phase, sec_count = phases[1]
            if sec_phase == "opening" and sec_count >= 5:
                recs.append({
                    "title": "Opening preparation",
                    "reason": f"{sec_count} opening blunders — also worth addressing",
                    "links": [("Opening puzzles", _puzzle_url("opening", difficulty))],
                })
            elif sec_phase == "endgame" and sec_count >= 5:
                recs.append({
                    "title": "Endgame training",
                    "reason": f"{sec_count} endgame blunders — secondary weakness",
                    "links": [("Endgame puzzles", _puzzle_url("endgame", difficulty)), ("Rook endgames", _puzzle_url("rookEndgame", difficulty))],
                })
    
    # Opening-based: top 3 blunder-prone openings with specific links
    for opening_name, opening_blunders in opening_groups[:3]:
        opening_slug = opening_name.replace(' ', '_').replace(':', '').replace("'", "")
        opening_phases = Counter(b["phase"] for b in opening_blunders)
        links = [("Study opening", f"https://lichess.org/opening/{opening_slug}")]
        # Add phase-relevant puzzle links for this opening's blunders
        if opening_phases.get("middlegame", 0) >= 2:
            links.append(("Forks", _puzzle_url("fork", difficulty)))
            links.append(("Pins", _puzzle_url("pin", difficulty)))
        if opening_phases.get("endgame", 0) >= 2:
            links.append(("Endgame", _puzzle_url("endgame", difficulty)))
        if opening_phases.get("opening", 0) >= 2:
            links.append(("Opening puzzles", _puzzle_url("opening", difficulty)))
        recs.append({
            "title": opening_name,
            "reason": f"{len(opening_blunders)} blunders across your games in this opening",
            "links": links,
        })
    
    # Mate awareness if there are mate-related blunders
    mate_blunders = [b for b in sum([v for _, v in opening_groups], []) if b.get("mate_after") is not None]
    if len(mate_blunders) >= 2:
        recs.append({
            "title": "Mate awareness",
            "reason": f"{len(mate_blunders)} blunders involved missing or allowing checkmate",
            "links": [
                ("Mate in 1", _puzzle_url("mateIn1", difficulty)),
                ("Mate in 2", _puzzle_url("mateIn2", difficulty)),
                ("Back rank mate", _puzzle_url("backRankMate", difficulty)),
            ],
        })
    
    return recs


def _build_html(*, username, current_rating, total_games, wins, losses, draws,
                win_rate, total_blunders, avg_blunders, phase_counts,
                opening_groups, worst, recent_games, recommendations, 
                difficulty, generated_at, worst_phase="middlegame"):
    """Build the complete HTML string."""
    
    # Phase bar widths
    max_phase = max(phase_counts.values()) if phase_counts else 1
    
    # ── Chart data ──────────────────────────────────
    all_blunders = sum([v for _, v in opening_groups], [])
    
    mh = {}
    for b in all_blunders:
        if b.get("cp_loss") is not None:
            mn = b["move_num"]
            if mn not in mh: mh[mn] = {"cnt": 0, "total": 0, "worst_cp": 0, "worst_url": ""}
            mh[mn]["cnt"] += 1
            mh[mn]["total"] += b["cp_loss"]
            if b["cp_loss"] > mh[mn]["worst_cp"]:
                mh[mn]["worst_cp"] = b["cp_loss"]
                mh[mn]["worst_url"] = f"https://lichess.org/{b['game_id']}#{b.get('half_move', '')}"
    move_chart = [{"m": m, "cnt": d["cnt"], "avg": round(d["total"] / d["cnt"]), "url": d["worst_url"]} for m, d in sorted(mh.items())]
    
    tl_data = [{"id": g["game_id"], "b": g["blunder_count"], "r": g["result"], "url": f"https://lichess.org/{g['game_id']}"} for g in sorted(recent_games, key=lambda x: x.get("date", 0))]
    
    op_ph = defaultdict(lambda: {"opening": 0, "middlegame": 0, "endgame": 0})
    for b in all_blunders:
        op_ph[b["opening"]][b["phase"]] += 1
    top_ops = [n for n, _ in opening_groups[:8]]
    def _sn(n):
        for o, nw in [("Nimzo-Larsen Attack", "NLA"), ("Caro-Kann Defense", "CK"), ("Queen's Pawn Game", "QP"), ("Blackmar-Diemer Gambit Accepted", "BDG")]:
            n = n.replace(o, nw)
        return n[:22]
    op_chart = {"labels": [_sn(n) for n in top_ops], "opening": [op_ph[n]["opening"] for n in top_ops], "middlegame": [op_ph[n]["middlegame"] for n in top_ops], "endgame": [op_ph[n]["endgame"] for n in top_ops]}
    
    pr_data = {"opening": {"win": 0, "loss": 0, "draw": 0}, "middlegame": {"win": 0, "loss": 0, "draw": 0}, "endgame": {"win": 0, "loss": 0, "draw": 0}}
    for b in all_blunders:
        r = b.get("game_result", "draw")
        if r in pr_data[b["phase"]]:
            pr_data[b["phase"]][r] += 1
    
    pm2 = {"K": "King", "Q": "Queen", "R": "Rook", "B": "Bishop", "N": "Knight"}
    pcc = Counter()
    pccp = defaultdict(list)
    for b in all_blunders:
        m = b.get("played_move", "")
        if not m or m == "?": continue
        if m.startswith("O-O"): p = "King"
        elif m[0] in pm2: p = pm2[m[0]]
        else: p = "Pawn"
        pcc[p] += 1
        if b.get("cp_loss") is not None: pccp[p].append(b["cp_loss"])
    po = ["Bishop", "Knight", "Pawn", "Rook", "King", "Queen"]
    piece_chart = {"labels": po, "counts": [pcc.get(p, 0) for p in po], "avg_cp": [round(sum(pccp.get(p, [0])) / max(len(pccp.get(p, [1])), 1)) for p in po]}
    
    chart_json = json.dumps({"move": move_chart, "tl": tl_data, "op": op_chart, "pr": pr_data, "piece": piece_chart})
    
    # Opening cards HTML
    opening_cards_html = ""
    for opening_name, opening_blunders in opening_groups[:8]:
        blunder_rows = ""
        for b in sorted(opening_blunders, key=lambda x: -(x["cp_loss"] or 0))[:5]:
            cp = f"−{b['cp_loss']}cp" if b["cp_loss"] is not None else f"mate"
            blunder_rows += f"""
            <div class="blunder-row">
                <span class="move-tag">m{b['move_num']} {b['played_move']}</span>
                <span class="vs-text">vs {b['opponent']}</span>
                <span class="cp-loss">{cp}</span>
                <a class="game-link" href="{b['game_url']}#{b['half_move']}" target="_blank">{b['game_id']}</a>
            </div>"""
        
        phase_breakdown = Counter(b["phase"] for b in opening_blunders)
        phase_tags = " ".join(
            f'<span class="phase-tag phase-{p}">{p}</span>'
            for p, _ in phase_breakdown.most_common()
        )
        
        opening_cards_html += f"""
        <div class="theme-card">
            <div class="theme-head">
                <span class="count-badge">{len(opening_blunders)}</span>
                <span class="theme-name">{opening_name}</span>
                {phase_tags}
            </div>
            <div class="blunder-list">{blunder_rows}
            </div>
        </div>"""
    
    # Worst blunders HTML
    worst_html = ""
    for i, b in enumerate(worst):
        cp = f"−{b['cp_loss']}cp" if b["cp_loss"] is not None else "mate"
        worst_html += f"""
        <tr>
            <td class="rank">#{i+1}</td>
            <td class="move-cell">m{b['move_num']} {b['played_move']}</td>
            <td class="cp-cell">{cp}</td>
            <td class="phase-cell">{b['phase']}</td>
            <td class="opening-cell">{b['opening'][:35]}</td>
            <td class="link-cell"><a href="{b['game_url']}#{b['half_move']}" target="_blank">{b['game_id']}</a></td>
        </tr>"""
    
    # Recommendations HTML
    recs_html = ""
    for rec in recommendations:
        links = " ".join(
            f'<a class="rec-link" href="{url}" target="_blank">{label}</a>'
            for label, url in rec["links"]
        )
        
        # Build puzzle grid if we have real puzzles
        puzzle_grid = ""
        puzzles = rec.get("puzzles", [])
        if puzzles:
            puzzle_items = ""
            for p in puzzles:
                themes_str = ", ".join(p["themes"][:3])
                puzzle_items += f"""<a class="puzzle-item" href="{p['url']}" target="_blank">
                    <span class="puzzle-rating">{p['rating']}</span>
                    <span class="puzzle-moves">{p['moves']} moves</span>
                    <span class="puzzle-themes">{themes_str}</span>
                </a>"""
            puzzle_grid = f"""
            <div style="margin-top:12px;font-family:var(--mono);font-size:10px;letter-spacing:1px;color:var(--faint);margin-bottom:8px">PUZZLES FOR YOU</div>
            <div class="puzzle-grid">{puzzle_items}</div>"""
        
        recs_html += f"""
        <div class="rec-card">
            <div class="rec-title">{rec['title']}</div>
            <div class="rec-reason">{rec['reason']}</div>
            <div class="rec-links">{links}</div>
            {puzzle_grid}
        </div>"""
    
    # Recent games HTML
    games_html = ""
    for g in recent_games:
        result_class = g["result"]
        result_label = g["result"].upper()
        date_str = datetime.fromtimestamp(g["date"] / 1000).strftime("%b %d") if g["date"] else "?"
        games_html += f"""
        <tr>
            <td class="date-cell">{date_str}</td>
            <td><span class="result-badge result-{result_class}">{result_label}</span></td>
            <td class="opening-cell">{g['opening'][:40]}</td>
            <td class="color-cell">{g['color']}</td>
            <td class="opp-cell">{g['opponent']}</td>
            <td class="num-cell">{g['blunder_count']}</td>
            <td class="num-cell">{g['mistake_count']}</td>
            <td class="link-cell"><a href="{g['game_url']}" target="_blank">{g['game_id']}</a></td>
        </tr>"""
    
    # Per-game cards HTML (Layout B)
    all_blunders_by_game = defaultdict(list)
    for og_name, og_blunders in opening_groups:
        for b in og_blunders:
            all_blunders_by_game[b["game_id"]].append(b)
    
    game_cards_html = ""
    for g in recent_games:
        gid = g["game_id"]
        g_blunders = sorted(all_blunders_by_game.get(gid, []), key=lambda x: x["move_num"])
        date_str = datetime.fromtimestamp(g["date"] / 1000).strftime("%b %d") if g["date"] else "?"
        
        blunder_rows = ""
        if g_blunders:
            for b in g_blunders:
                cp = f"&minus;{b['cp_loss']}cp" if b["cp_loss"] is not None else "mate"
                blunder_rows += f"""<div class="gb-row">
                    <span class="gb-move">m{b['move_num']} {b['played_move']}</span>
                    <span class="gb-best">best: {b['best_move']}</span>
                    <span class="gb-cp">{cp}</span>
                    <span class="gb-phase">{b['phase']}</span>
                </div>"""
        else:
            blunder_rows = '<div class="gb-row" style="color:var(--teal)">No blunders</div>'
        
        puzzle_links = ""
        g_phases = set(b["phase"] for b in g_blunders)
        
        # Always add opening-specific study link if there are blunders
        if g_blunders:
            opening_slug = g['opening'].replace(' ', '_').replace(':', '').replace("'", "")
            puzzle_links += f'<a class="gp-link" href="https://lichess.org/opening/{opening_slug}" target="_blank">Study {g["opening"].split(":")[0]}</a>'
        
        # Add phase-specific puzzle links (no generic "Opening puzzles")
        phase_themes = {
            "middlegame": [("Forks", THEME_MAP["fork"]), ("Pins", THEME_MAP["pin"])],
            "endgame": [("Endgame", THEME_MAP["endgame"]), ("Rook endgames", THEME_MAP["rookEndgame"])],
        }
        for ph in g_phases:
            for label, url in phase_themes.get(ph, []):
                puzzle_links += f'<a class="gp-link" href="{url}" target="_blank">{label}</a>'
        
        game_cards_html += f"""
        <div class="game-card">
            <div class="gc-head">
                <span class="result-badge result-{g['result']}">{g['result'].upper()}</span>
                <span class="gc-opening">{g['opening']}</span>
                <span class="gc-meta">{date_str} &middot; {g['color']} &middot; vs {g['opponent']}</span>
                <a class="gc-link" href="{g['game_url']}" target="_blank">{gid}</a>
            </div>
            <div class="gc-blunders">{blunder_rows}</div>
            {'<div class="gc-puzzles">' + puzzle_links + '</div>' if puzzle_links else ''}
        </div>"""
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>blunder.report — @{username}</title>
<meta name="description" content="Blunder analysis for @{username} on Lichess. {total_blunders} blunders across {total_games} games. Rating: {current_rating}.">
<meta property="og:title" content="blunder.report — @{username}">
<meta property="og:description" content="{total_blunders} blunders found across {total_games} games. {worst_phase} is the weakest phase. Rating: {current_rating}.">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="blunder.report — @{username}">
<meta name="twitter:description" content="{total_blunders} blunders in {total_games} games. Worst phase: {worst_phase}.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Instrument+Serif&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root {{
    --bg:        #0b0b0f;
    --surface:   #111116;
    --surface2:  #18181f;
    --border:    #222230;
    --text:      #c8c8d0;
    --text-dim:  #66667a;
    --text-faint:#3a3a4a;
    --accent:    #d4443e;
    --accent2:   #e8956a;
    --teal:      #3eb8a0;
    --blue:      #5b8ad4;
    --mono:      'JetBrains Mono', monospace;
    --serif:     'Instrument Serif', Georgia, serif;
    --sans:      'DM Sans', system-ui, sans-serif;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
}}

.container {{
    max-width: 900px;
    margin: 0 auto;
    padding: 48px 24px 80px;
}}

/* ── Header ─────────────────────────────────── */
.header {{
    border-bottom: 1px solid var(--border);
    padding-bottom: 40px;
    margin-bottom: 48px;
}}

.brand {{
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 16px;
}}

.title {{
    font-family: var(--serif);
    font-size: 48px;
    font-weight: 400;
    color: #fff;
    line-height: 1.1;
    margin-bottom: 8px;
}}

.subtitle {{
    font-size: 15px;
    color: var(--text-dim);
}}

.subtitle a {{
    color: var(--blue);
    text-decoration: none;
}}

/* ── Stat Grid ──────────────────────────────── */
.stat-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 48px;
}}

.stat-cell {{
    background: var(--surface);
    padding: 20px;
}}

.stat-label {{
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-bottom: 8px;
}}

.stat-value {{
    font-family: var(--mono);
    font-size: 28px;
    font-weight: 700;
    color: #fff;
}}

.stat-value.accent {{ color: var(--accent); }}
.stat-value.teal {{ color: var(--teal); }}

.stat-sub {{
    font-size: 12px;
    color: var(--text-dim);
    margin-top: 4px;
}}

/* ── Section ────────────────────────────────── */
.section {{
    margin-bottom: 48px;
}}

.section-label {{
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--text-faint);
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
}}

/* ── Phase Bars ─────────────────────────────── */
.phase-bars {{
    display: flex;
    flex-direction: column;
    gap: 10px;
}}

.phase-bar-row {{
    display: grid;
    grid-template-columns: 100px 40px 1fr;
    align-items: center;
    gap: 12px;
}}

.phase-name {{
    font-family: var(--mono);
    font-size: 12px;
    color: var(--text-dim);
    text-align: right;
}}

.phase-count {{
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 700;
    color: #fff;
    text-align: right;
}}

.phase-track {{
    height: 6px;
    background: var(--surface2);
    border-radius: 3px;
    overflow: hidden;
}}

.phase-fill {{
    height: 100%;
    border-radius: 3px;
    transition: width 0.6s ease;
}}

.phase-fill.opening {{ background: var(--accent2); }}
.phase-fill.middlegame {{ background: var(--accent); }}
.phase-fill.endgame {{ background: var(--teal); }}

/* ── Theme Cards (Openings) ─────────────────── */
.theme-cards {{
    display: flex;
    flex-direction: column;
    gap: 12px;
}}

.theme-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
}}

.theme-head {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 16px;
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
}}

.count-badge {{
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    color: var(--accent);
    background: rgba(212, 68, 62, 0.12);
    padding: 2px 10px;
    border-radius: 4px;
    min-width: 32px;
    text-align: center;
}}

.count-badge::after {{
    content: '×';
    margin-left: 1px;
}}

.theme-name {{
    font-size: 14px;
    font-weight: 500;
    color: #fff;
    flex: 1;
}}

.phase-tag {{
    font-family: var(--mono);
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 3px;
    letter-spacing: 0.5px;
}}

.phase-tag.phase-opening {{ color: var(--accent2); background: rgba(232, 149, 106, 0.1); }}
.phase-tag.phase-middlegame {{ color: var(--accent); background: rgba(212, 68, 62, 0.1); }}
.phase-tag.phase-endgame {{ color: var(--teal); background: rgba(62, 184, 160, 0.1); }}

.blunder-list {{
    padding: 8px 16px 12px;
}}

.blunder-row {{
    display: grid;
    grid-template-columns: 90px 1fr 70px 80px;
    gap: 8px;
    padding: 6px 0;
    align-items: center;
    border-bottom: 1px solid rgba(255,255,255,0.03);
    font-size: 13px;
}}

.blunder-row:last-child {{ border-bottom: none; }}

.move-tag {{
    font-family: var(--mono);
    font-size: 12px;
    color: #fff;
}}

.vs-text {{
    color: var(--text-dim);
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}

.cp-loss {{
    font-family: var(--mono);
    font-size: 12px;
    color: var(--accent);
    text-align: right;
}}

.game-link {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--blue);
    text-decoration: none;
    text-align: right;
}}

.game-link:hover {{ text-decoration: underline; }}

/* ── Worst Blunders Table ───────────────────── */
.worst-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}

.worst-table th {{
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--text-faint);
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
}}

.worst-table td {{
    padding: 10px;
    border-bottom: 1px solid rgba(255,255,255,0.03);
}}

.rank {{ color: var(--text-faint); font-family: var(--mono); font-size: 12px; width: 36px; }}
.move-cell {{ font-family: var(--mono); color: #fff; }}
.cp-cell {{ font-family: var(--mono); color: var(--accent); font-weight: 700; }}
.phase-cell {{ color: var(--text-dim); }}
.opening-cell {{ color: var(--text-dim); font-size: 12px; }}
.link-cell a {{ font-family: var(--mono); font-size: 11px; color: var(--blue); text-decoration: none; }}
.link-cell a:hover {{ text-decoration: underline; }}

/* ── Recommendations ────────────────────────── */
.rec-cards {{
    display: flex;
    flex-direction: column;
    gap: 12px;
}}

.rec-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--teal);
    border-radius: 8px;
    padding: 16px 20px;
}}

.rec-title {{
    font-weight: 700;
    color: #fff;
    margin-bottom: 4px;
}}

.rec-reason {{
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 12px;
}}

.rec-links {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}}

.rec-link {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--teal);
    background: rgba(62, 184, 160, 0.08);
    border: 1px solid rgba(62, 184, 160, 0.2);
    padding: 5px 14px;
    border-radius: 4px;
    text-decoration: none;
    transition: background 0.15s;
}}

.rec-link:hover {{
    background: rgba(62, 184, 160, 0.15);
}}

/* ── Games Table ────────────────────────────── */
.games-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}

.games-table th {{
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--text-faint);
    text-align: left;
    padding: 8px 8px;
    border-bottom: 1px solid var(--border);
}}

.games-table td {{
    padding: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.03);
}}

.date-cell {{ color: var(--text-dim); font-family: var(--mono); font-size: 12px; }}
.color-cell {{ color: var(--text-dim); font-size: 12px; }}
.opp-cell {{ color: var(--text-dim); font-size: 12px; }}
.num-cell {{ font-family: var(--mono); text-align: center; color: var(--text-dim); }}

.result-badge {{
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 3px;
    letter-spacing: 0.5px;
}}

.result-win {{ color: var(--teal); background: rgba(62, 184, 160, 0.1); }}
.result-loss {{ color: var(--accent); background: rgba(212, 68, 62, 0.1); }}
.result-draw {{ color: var(--accent2); background: rgba(232, 149, 106, 0.1); }}

/* ── Footer ─────────────────────────────────── */
.footer {{
    margin-top: 64px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-faint);
}}

.footer-dot {{
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--accent);
}}

/* ── Puzzle Grid ─────────────────────────── */
.puzzle-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 6px;
}}

.puzzle-item {{
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px 10px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    text-decoration: none;
    transition: border-color 0.15s;
}}

.puzzle-item:hover {{
    border-color: var(--teal);
}}

.puzzle-rating {{
    font-family: var(--mono);
    font-size: 14px;
    font-weight: 700;
    color: #fff;
}}

.puzzle-moves {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--teal);
}}

.puzzle-themes {{
    font-size: 10px;
    color: var(--faint);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}

/* ── Per-game cards (Layout B) ───────────── */
.game-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 8px;
}}

.gc-head {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    flex-wrap: wrap;
}}

.gc-opening {{
    font-size: 13px;
    font-weight: 500;
    color: #fff;
    flex: 1;
    min-width: 120px;
}}

.gc-meta {{
    font-size: 12px;
    color: var(--dim);
}}

.gc-link {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--blue);
    text-decoration: none;
}}

.gc-link:hover {{ text-decoration: underline; }}

.gc-blunders {{
    padding: 4px 16px 8px;
    border-top: 1px solid var(--border);
}}

.gb-row {{
    display: grid;
    grid-template-columns: 100px 120px 80px 90px;
    gap: 8px;
    padding: 5px 0;
    font-size: 12px;
    border-bottom: 1px solid rgba(255,255,255,.03);
}}

.gb-row:last-child {{ border-bottom: none; }}
.gb-move {{ font-family: var(--mono); color: #fff; }}
.gb-best {{ color: var(--dim); font-family: var(--mono); }}
.gb-cp {{ font-family: var(--mono); color: var(--accent); text-align: right; }}
.gb-phase {{ color: var(--dim); }}

.gc-puzzles {{
    padding: 8px 16px 12px;
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    border-top: 1px solid var(--border);
}}

.gp-link {{
    font-family: var(--mono);
    font-size: 10px;
    color: var(--teal);
    background: rgba(62,184,160,.06);
    border: 1px solid rgba(62,184,160,.15);
    padding: 3px 10px;
    border-radius: 3px;
    text-decoration: none;
}}

.gp-link:hover {{ background: rgba(62,184,160,.12); }}

/* ── Responsive ─────────────────────────────── */
@media (max-width: 700px) {{
    .stat-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .title {{ font-size: 32px; }}
    .blunder-row {{ grid-template-columns: 80px 1fr 60px; }}
    .blunder-row .game-link {{ display: none; }}
}}
</style>
</head>
<body>
<div class="container">

    <div class="header">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
            <div>
                <div class="brand">blunder.report</div>
                <h1 class="title">@{username}</h1>
                <div class="subtitle">
                    Rapid {current_rating} · {total_games} games analyzed ·
                    <a href="https://lichess.org/@/{username}" target="_blank">lichess.org/@/{username}</a>
                </div>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <a href="/" style="font-family:var(--mono);font-size:12px;color:var(--dim);border:1px solid var(--border);padding:8px 16px;border-radius:6px;text-decoration:none;display:inline-block">Analyze again</a>
                <button onclick="navigator.clipboard.writeText(window.location.href).then(()=>this.textContent='Copied!').catch(()=>{{}})" style="font-family:var(--mono);font-size:12px;color:var(--teal);background:transparent;border:1px solid rgba(62,184,160,.3);padding:8px 16px;border-radius:6px;cursor:pointer">Share link</button>
            </div>
        </div>
    </div>

    <div class="stat-grid">
        <div class="stat-cell">
            <div class="stat-label">Blunders</div>
            <div class="stat-value accent">{total_blunders}</div>
            <div class="stat-sub">{avg_blunders:.1f} per game</div>
        </div>
        <div class="stat-cell">
            <div class="stat-label">Win rate</div>
            <div class="stat-value teal">{win_rate}%</div>
            <div class="stat-sub">{wins}W / {losses}L / {draws}D</div>
        </div>
        <div class="stat-cell">
            <div class="stat-label">Worst phase</div>
            <div class="stat-value">{''.join(p for p, _ in sorted(phase_counts.items(), key=lambda x: -x[1])[:1])}</div>
            <div class="stat-sub">{max(phase_counts.values()) if phase_counts else 0} blunders</div>
        </div>
        <div class="stat-cell">
            <div class="stat-label">Games</div>
            <div class="stat-value">{total_games}</div>
            <div class="stat-sub">with Lichess analysis</div>
        </div>
    </div>

    <!-- LAYOUT A: Puzzle recommendations at top -->
    <div class="section">
        <div class="section-label">Train these</div>
        <div class="rec-cards">
            {recs_html}
        </div>
        <div style="margin-top:12px;font-size:12px;color:var(--faint);font-family:var(--mono)">
            Set puzzle difficulty on Lichess once you open the training page
        </div>
    </div>

    <div class="section">
        <div class="section-label">Blunders by phase</div>
        <div class="phase-bars">
            <div class="phase-bar-row">
                <span class="phase-name">opening</span>
                <span class="phase-count">{phase_counts.get('opening', 0)}</span>
                <div class="phase-track">
                    <div class="phase-fill opening" style="width: {100 * phase_counts.get('opening', 0) / max_phase:.0f}%"></div>
                </div>
            </div>
            <div class="phase-bar-row">
                <span class="phase-name">middlegame</span>
                <span class="phase-count">{phase_counts.get('middlegame', 0)}</span>
                <div class="phase-track">
                    <div class="phase-fill middlegame" style="width: {100 * phase_counts.get('middlegame', 0) / max_phase:.0f}%"></div>
                </div>
            </div>
            <div class="phase-bar-row">
                <span class="phase-name">endgame</span>
                <span class="phase-count">{phase_counts.get('endgame', 0)}</span>
                <div class="phase-track">
                    <div class="phase-fill endgame" style="width: {100 * phase_counts.get('endgame', 0) / max_phase:.0f}%"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- Charts -->
    <div class="section">
        <div class="section-label">Your blunder patterns</div>
        <div style="margin-bottom:24px">
            <div style="font-size:13px;font-weight:500;color:#fff;margin-bottom:4px">Blunder heatmap by move number</div>
            <div style="font-size:12px;color:var(--dim);margin-bottom:12px">Your danger zone is the opening-to-middlegame transition. Click a bar to view the worst blunder at that move.</div>
            <div style="position:relative;width:100%;height:180px;cursor:pointer"><canvas id="ch_heat"></canvas></div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px">
            <div>
                <div style="font-size:13px;font-weight:500;color:#fff;margin-bottom:4px">Blunders per game</div>
                <div style="font-size:12px;color:var(--dim);margin-bottom:12px">Green=win, red=loss, amber=draw</div>
                <div style="position:relative;width:100%;height:220px;cursor:pointer"><canvas id="ch_tl"></canvas></div>
            </div>
            <div>
                <div style="font-size:13px;font-weight:500;color:#fff;margin-bottom:4px">Which piece do you blunder with?</div>
                <div style="font-size:12px;color:var(--dim);margin-bottom:12px">Count and average centipawn loss</div>
                <div style="position:relative;width:100%;height:220px"><canvas id="ch_piece"></canvas></div>
                <div id="leg_piece" style="display:flex;gap:14px;font-size:11px;color:var(--dim);margin-top:6px"></div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px">
            <div>
                <div style="font-size:13px;font-weight:500;color:#fff;margin-bottom:4px">Blunders by opening</div>
                <div style="font-size:12px;color:var(--dim);margin-bottom:12px">Stacked by game phase</div>
                <div style="position:relative;width:100%;height:260px"><canvas id="ch_op"></canvas></div>
                <div id="leg_op" style="display:flex;gap:14px;font-size:11px;color:var(--dim);margin-top:6px"></div>
            </div>
            <div>
                <div style="font-size:13px;font-weight:500;color:#fff;margin-bottom:4px">Do blunders cause losses?</div>
                <div style="font-size:12px;color:var(--dim);margin-bottom:12px">Opening blunders hurt most</div>
                <div style="position:relative;width:100%;height:260px"><canvas id="ch_pr"></canvas></div>
                <div id="leg_pr" style="display:flex;gap:14px;font-size:11px;color:var(--dim);margin-top:6px"></div>
            </div>
        </div>
        <div style="margin-bottom:24px">
            <div style="font-size:13px;font-weight:500;color:#fff;margin-bottom:4px">White vs black</div>
            <div style="font-size:12px;color:var(--dim);margin-bottom:12px">Blunders and wins by color</div>
            <div style="position:relative;width:100%;height:120px"><canvas id="ch_color"></canvas></div>
            <div id="leg_color" style="display:flex;gap:14px;font-size:11px;color:var(--dim);margin-top:6px"></div>
        </div>
    </div>

    <div class="section">
        <div class="section-label">Blunders by opening</div>
        <div class="theme-cards">
            {opening_cards_html}
        </div>
    </div>

    <div class="section">
        <div class="section-label">Worst blunders</div>
        <table class="worst-table">
            <thead>
                <tr>
                    <th></th>
                    <th>Move</th>
                    <th>Loss</th>
                    <th>Phase</th>
                    <th>Opening</th>
                    <th>Game</th>
                </tr>
            </thead>
            <tbody>
                {worst_html}
            </tbody>
        </table>
    </div>

    <div class="section">
        <div class="section-label">Game by game</div>
        {game_cards_html}
    </div>

    <div class="footer">
        <div class="footer-dot"></div>
        generated {generated_at} · {total_games} games · blunder-tracker v0.2
        <span style="margin-left:auto;display:flex;gap:16px">
            
            <a href="https://linkedin.com/in/chakravartysajal" target="_blank" style="color:var(--dim);text-decoration:none">LinkedIn</a>
            <a href="https://github.com/sajalckvt/lichess-blunder-tracker" target="_blank" style="color:var(--dim);text-decoration:none">GitHub</a>
        </span>
    </div>

</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const D={chart_json};
const g='rgba(255,255,255,0.05)',R='#d4443e',T='#3eb8a0',A='#e8956a',C='#D85A30';
Chart.defaults.color='#999';Chart.defaults.font.size=11;
function mkLeg(id,items){{const e=document.getElementById(id);if(!e)return;e.innerHTML=items.map(([c,l])=>'<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;border-radius:2px;background:'+c+'"></span>'+l+'</span>').join('');}}

new Chart(document.getElementById('ch_heat'),{{type:'bar',data:{{labels:D.move.map(d=>'m'+d.m),datasets:[{{data:D.move.map(d=>d.cnt),backgroundColor:D.move.map(d=>{{const i=Math.min(d.avg/800,1);return'rgb('+Math.round(212*i+50*(1-i))+','+Math.round(68*i+50*(1-i))+','+Math.round(62*i+80*(1-i))+')';}}),borderRadius:2}}]}},options:{{responsive:true,maintainAspectRatio:false,onClick:(e,el)=>{{if(el.length){{const u=D.move[el[0].index].url;if(u)window.open(u,'_blank');}}}},plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>D.move[c.dataIndex].cnt+' blunders, avg '+D.move[c.dataIndex].avg+'cp',afterLabel:c=>D.move[c.dataIndex].url?'Click to view worst blunder':''}}}}}},scales:{{y:{{grid:{{color:g}},ticks:{{stepSize:1}}}},x:{{grid:{{display:false}},ticks:{{maxRotation:90,font:{{size:9}}}}}}}}}}}});

new Chart(document.getElementById('ch_tl'),{{type:'bar',data:{{labels:D.tl.map((_,i)=>i+1),datasets:[{{data:D.tl.map(d=>d.b),backgroundColor:D.tl.map(d=>d.r==='win'?T:d.r==='loss'?R:A),borderRadius:3}}]}},options:{{responsive:true,maintainAspectRatio:false,onClick:(e,el)=>{{if(el.length){{const u=D.tl[el[0].index].url;if(u)window.open(u,'_blank');}}}},plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>{{const t=D.tl[c.dataIndex];return t.id+': '+t.b+' blunders ('+t.r+')'}},afterLabel:()=>'Click to open game on Lichess'}}}}}},scales:{{y:{{grid:{{color:g}},ticks:{{stepSize:2}}}},x:{{grid:{{display:false}},title:{{display:true,text:'oldest → newest · click bar to open game',font:{{size:10}}}}}}}}}}}});

new Chart(document.getElementById('ch_piece'),{{type:'bar',data:{{labels:D.piece.labels,datasets:[{{label:'Count',data:D.piece.counts,backgroundColor:R,borderRadius:3}},{{label:'Avg CP',data:D.piece.avg_cp,backgroundColor:A,borderRadius:3,yAxisID:'y1'}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{y:{{grid:{{color:g}},title:{{display:true,text:'count',font:{{size:10}}}}}},y1:{{position:'right',grid:{{display:false}},title:{{display:true,text:'avg cp loss',font:{{size:10}}}}}},x:{{grid:{{display:false}}}}}}}}}});
mkLeg('leg_piece',[[R,'Blunder count'],[A,'Avg CP loss']]);

new Chart(document.getElementById('ch_op'),{{type:'bar',data:{{labels:D.op.labels,datasets:[{{label:'Opening',data:D.op.opening,backgroundColor:C,borderRadius:2}},{{label:'Middlegame',data:D.op.middlegame,backgroundColor:R,borderRadius:2}},{{label:'Endgame',data:D.op.endgame,backgroundColor:T,borderRadius:2}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{stacked:true,grid:{{display:false}},ticks:{{font:{{size:9}},maxRotation:45}}}},y:{{stacked:true,grid:{{color:g}}}}}}}}}});
mkLeg('leg_op',[[C,'Opening'],[R,'Middlegame'],[T,'Endgame']]);

const pr=D.pr;
new Chart(document.getElementById('ch_pr'),{{type:'bar',data:{{labels:['Opening','Middlegame','Endgame'],datasets:[{{label:'Win',data:[pr.opening.win,pr.middlegame.win,pr.endgame.win],backgroundColor:T,borderRadius:2}},{{label:'Loss',data:[pr.opening.loss,pr.middlegame.loss,pr.endgame.loss],backgroundColor:R,borderRadius:2}},{{label:'Draw',data:[pr.opening.draw,pr.middlegame.draw,pr.endgame.draw],backgroundColor:A,borderRadius:2}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{stacked:true,grid:{{display:false}}}},y:{{stacked:true,grid:{{color:g}}}}}}}}}});
mkLeg('leg_pr',[[T,'Win'],[R,'Loss'],[A,'Draw']]);

const cW=D.color||{{}};const w=cW.white||{{blunders:0,wins:0}};const b=cW.black||{{blunders:0,wins:0}};
new Chart(document.getElementById('ch_color'),{{type:'bar',data:{{labels:['White','Black'],datasets:[{{label:'Blunders',data:[w.blunders,b.blunders],backgroundColor:R,borderRadius:3}},{{label:'Wins',data:[w.wins,b.wins],backgroundColor:T,borderRadius:3}}]}},options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:g}}}},y:{{grid:{{display:false}}}}}}}}}});
mkLeg('leg_color',[[R,'Blunders'],[T,'Wins']]);
</script>
</body>
</html>"""
