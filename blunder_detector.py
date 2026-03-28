"""
Blunder detection engine.

Takes Lichess game data (with analysis) and extracts blunders,
mistakes, and inaccuracies for the target player.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from config import CP_BLUNDER, CP_MISTAKE, CP_INACCURACY, PHASE_OPENING, PHASE_MIDDLEGAME


@dataclass
class Blunder:
    game_id: str
    opening: str
    speed: str
    move_num: int
    half_move: int          # ply index in the analysis array
    phase: str              # opening / middlegame / endgame
    color: str              # white / black
    played_move: str        # SAN of the move played
    best_move: str          # UCI of the engine's best move
    cp_loss: Optional[int]  # centipawn loss (None if mate involved)
    eval_before: Optional[int]
    eval_after: Optional[int]
    mate_before: Optional[int]
    mate_after: Optional[int]
    severity: str           # blunder / mistake / inaccuracy
    lichess_judgment: str   # Lichess's own classification
    game_result: str        # win / loss / draw (from player's perspective)
    game_url: str
    opponent: str

    def to_dict(self):
        return asdict(self)


@dataclass
class GameSummary:
    game_id: str
    date: int               # createdAt timestamp
    speed: str
    opening: str
    opening_eco: str
    color: str              # which color the target player had
    result: str             # win / loss / draw
    opponent: str
    opponent_rating: int
    player_rating: int
    total_moves: int
    blunder_count: int
    mistake_count: int
    inaccuracy_count: int
    game_url: str

    def to_dict(self):
        return asdict(self)


def classify_phase(move_num: int) -> str:
    if move_num <= PHASE_OPENING:
        return "opening"
    elif move_num <= PHASE_MIDDLEGAME:
        return "middlegame"
    return "endgame"


def compute_cp_loss(eval_before, eval_after, mate_before, mate_after, color):
    """
    Compute centipawn loss from the player's perspective.
    Lichess evals are always from white's POV.
    Returns (cp_loss, is_significant) or (None, True) for mate swings.
    """
    # If mate is involved, it's always significant
    if mate_after is not None and mate_before is None:
        return None, True
    if mate_before is not None and mate_after is not None:
        # Mate to mate — check if it swung against us
        if color == "white":
            return None, (mate_before > 0 and mate_after < 0)
        else:
            return None, (mate_before < 0 and mate_after > 0)

    if eval_before is None or eval_after is None:
        return None, False

    if color == "white":
        loss = eval_before - eval_after
    else:
        loss = eval_after - eval_before

    return loss, loss > CP_INACCURACY


def classify_severity(cp_loss: Optional[int], lichess_judgment: str) -> str:
    """
    Only use Lichess's own judgment. We don't add our own threshold-based
    detections because they produce false positives in already-decided
    positions (e.g. losing by 6000cp, any move looks like a "blunder").
    
    Stockfish-based local analysis (future phase) can use thresholds
    since it can evaluate context properly.
    """
    if lichess_judgment in ("Blunder", "Mistake", "Inaccuracy"):
        return lichess_judgment.lower()
    return "ok"


def analyze_game(game: dict, username: str) -> tuple[GameSummary, list[Blunder]]:
    """
    Analyze a single Lichess game and extract all errors.
    
    Args:
        game: Lichess game dict (must include 'analysis' and 'moves')
        username: the player whose blunders we're tracking
    
    Returns:
        (GameSummary, list of Blunders)
    """
    game_id = game["id"]
    analysis = game.get("analysis", [])
    moves = game.get("moves", "").split()
    
    # Determine player's color
    white_name = game.get("players", {}).get("white", {}).get("user", {}).get("name", "")
    black_name = game.get("players", {}).get("black", {}).get("user", {}).get("name", "")
    
    if white_name.lower() == username.lower():
        my_color = "white"
        opponent = black_name
        opp_rating = game.get("players", {}).get("black", {}).get("rating", 0)
        my_rating = game.get("players", {}).get("white", {}).get("rating", 0)
    else:
        my_color = "black"
        opponent = white_name
        opp_rating = game.get("players", {}).get("white", {}).get("rating", 0)
        my_rating = game.get("players", {}).get("black", {}).get("rating", 0)

    # Determine result
    winner = game.get("winner")
    if winner is None:
        result = "draw"
    elif (winner == "white" and my_color == "white") or (winner == "black" and my_color == "black"):
        result = "win"
    else:
        result = "loss"

    opening = game.get("opening", {})
    speed = game.get("speed", "unknown")
    game_url = f"https://lichess.org/{game_id}"

    blunders = []
    blunder_count = 0
    mistake_count = 0
    inaccuracy_count = 0

    for i, ev in enumerate(analysis):
        # Only look at OUR moves
        move_color = "white" if i % 2 == 0 else "black"
        if move_color != my_color:
            continue

        judgment = ev.get("judgment", {})
        lichess_jname = judgment.get("name", "")
        
        # Get evals
        eval_after = ev.get("eval")
        mate_after = ev.get("mate")
        eval_before = analysis[i - 1].get("eval") if i > 0 else None
        mate_before = analysis[i - 1].get("mate") if i > 0 else None
        best_move = ev.get("best", "?")

        cp_loss, is_significant = compute_cp_loss(
            eval_before, eval_after, mate_before, mate_after, my_color
        )

        severity = classify_severity(cp_loss, lichess_jname)
        
        if severity == "blunder":
            blunder_count += 1
        elif severity == "mistake":
            mistake_count += 1
        elif severity == "inaccuracy":
            inaccuracy_count += 1
        else:
            continue  # skip "ok" moves

        move_num = (i // 2) + 1
        played_move = moves[i] if i < len(moves) else "?"

        blunders.append(Blunder(
            game_id=game_id,
            opening=opening.get("name", "Unknown"),
            speed=speed,
            move_num=move_num,
            half_move=i,
            phase=classify_phase(move_num),
            color=my_color,
            played_move=played_move,
            best_move=best_move,
            cp_loss=cp_loss,
            eval_before=eval_before,
            eval_after=eval_after,
            mate_before=mate_before,
            mate_after=mate_after,
            severity=severity,
            lichess_judgment=lichess_jname or severity,
            game_result=result,
            game_url=game_url,
            opponent=opponent,
        ))

    summary = GameSummary(
        game_id=game_id,
        date=game.get("createdAt", 0),
        speed=speed,
        opening=opening.get("name", "Unknown"),
        opening_eco=opening.get("eco", "?"),
        color=my_color,
        result=result,
        opponent=opponent,
        opponent_rating=opp_rating,
        player_rating=my_rating,
        total_moves=len(moves),
        blunder_count=blunder_count,
        mistake_count=mistake_count,
        inaccuracy_count=inaccuracy_count,
        game_url=game_url,
    )

    return summary, blunders


def analyze_all(games: list[dict], username: str) -> tuple[list[GameSummary], list[Blunder]]:
    """Analyze a batch of games. Returns (summaries, all_blunders)."""
    all_summaries = []
    all_blunders = []

    for game in games:
        summary, blunders = analyze_game(game, username)
        all_summaries.append(summary)
        all_blunders.extend(blunders)

    return all_summaries, all_blunders
