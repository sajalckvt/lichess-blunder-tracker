"""
blunder-tracker configuration
"""

# Lichess API
LICHESS_BASE = "https://lichess.org/api"

# Blunder detection thresholds (centipawn loss)
CP_BLUNDER = 200      # ≥200cp loss = blunder
CP_MISTAKE = 100      # ≥100cp loss = mistake  
CP_INACCURACY = 50    # ≥50cp loss = inaccuracy

# Game phase boundaries (by move number)
PHASE_OPENING = 10     # moves 1-10
PHASE_MIDDLEGAME = 30  # moves 11-30
# everything after = endgame

# Default fetch settings
DEFAULT_GAME_COUNT = 50
DEFAULT_SPEED = "rapid"

# Lichess puzzle theme mapping
# Maps common tactical patterns to Lichess training URLs
THEME_MAP = {
    "fork": "https://lichess.org/training/fork",
    "pin": "https://lichess.org/training/pin",
    "skewer": "https://lichess.org/training/skewer",
    "discoveredAttack": "https://lichess.org/training/discoveredAttack",
    "backRankMate": "https://lichess.org/training/backRankMate",
    "hangingPiece": "https://lichess.org/training/hangingPiece",
    "trappedPiece": "https://lichess.org/training/trappedPiece",
    "deflection": "https://lichess.org/training/deflection",
    "sacrifice": "https://lichess.org/training/sacrifice",
    "endgame": "https://lichess.org/training/endgame",
    "pawnEndgame": "https://lichess.org/training/pawnEndgame",
    "rookEndgame": "https://lichess.org/training/rookEndgame",
    "mateIn1": "https://lichess.org/training/mateIn1",
    "mateIn2": "https://lichess.org/training/mateIn2",
    "mateIn3": "https://lichess.org/training/mateIn3",
    "opening": "https://lichess.org/training/opening",
    "middlegame": "https://lichess.org/training/middlegame",
    "short": "https://lichess.org/training/short",
    "long": "https://lichess.org/training/long",
    "queenEndgame": "https://lichess.org/training/queenEndgame",
    "bishopEndgame": "https://lichess.org/training/bishopEndgame",
    "knightEndgame": "https://lichess.org/training/knightEndgame",
    "masterVsMaster": "https://lichess.org/training/masterVsMaster",
}
