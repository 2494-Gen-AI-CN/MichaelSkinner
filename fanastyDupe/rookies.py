"""
Static 2026 NBA rookie projections for players not yet in the NBA API.
Projections are based on college performance, draft position, and historical comps.
Update TEAM_ABBREVIATION entries once rosters are confirmed.
"""
import pandas as pd

_PROJ_STATS = ["PTS", "REB", "AST", "STL", "BLK", "FG3M", "TOV"]

# (name, team, age, gp, pts, reb, ast, stl, blk, fg3m, tov, fg_pct, ft_pct, min)
_2026_CLASS = [
    ("AJ Dybantsa",  "---", 19, 65, 17.5, 6.0, 3.0, 1.1, 0.7, 1.6, 2.5, 0.47, 0.78, 28.0),
    ("Ace Bailey",   "---", 19, 65, 16.0, 5.5, 2.5, 1.0, 0.9, 1.8, 2.2, 0.45, 0.76, 27.0),
    ("Dylan Harper", "---", 19, 68, 14.0, 4.0, 5.0, 1.2, 0.4, 1.2, 2.8, 0.46, 0.82, 28.0),
    ("VJ Edgecombe", "---", 19, 60, 11.0, 3.5, 3.0, 1.3, 0.5, 1.4, 1.8, 0.44, 0.74, 25.0),
    ("Tre Johnson",  "---", 19, 65, 13.0, 3.0, 2.5, 1.0, 0.3, 2.0, 1.8, 0.43, 0.80, 24.0),
    ("Kon Knueppel", "---", 20, 65, 10.0, 3.5, 2.5, 0.8, 0.5, 1.8, 1.5, 0.45, 0.82, 23.0),
    ("Nolan Traore", "---", 19, 60,  9.0, 3.0, 4.5, 1.1, 0.3, 0.8, 2.2, 0.43, 0.75, 24.0),
]

_BASE_ID = 9_900_001


def get_rookie_projections(scoring: dict) -> pd.DataFrame:
    """Return a DataFrame of 2026 rookie projections compatible with proj_df schema."""
    s = scoring
    rows = []
    for i, (name, team, age, gp, pts, reb, ast, stl, blk, fg3m, tov, fg_pct, ft_pct, mn) in enumerate(_2026_CLASS):
        proj_fv = round(
            pts  * s.get("pts",  1.0)
            + reb  * s.get("reb",  1.2)
            + ast  * s.get("ast",  1.5)
            + stl  * s.get("stl",  3.0)
            + blk  * s.get("blk",  3.0)
            + fg3m * s.get("fg3m", 1.0)
            + tov  * s.get("tov", -1.0),
            2,
        )
        rows.append({
            "PLAYER_ID":         _BASE_ID + i,
            "PLAYER_NAME":       name,
            "TEAM_ABBREVIATION": team,
            "AGE":               float(age),
            "GP":                gp,
            "MIN":               mn,
            "PTS":               pts,
            "REB":               reb,
            "AST":               ast,
            "STL":               stl,
            "BLK":               blk,
            "FG3M":              fg3m,
            "TOV":               tov,
            "FG_PCT":            fg_pct,
            "FT_PCT":            ft_pct,
            "PROJ_PTS":          pts,
            "PROJ_REB":          reb,
            "PROJ_AST":          ast,
            "PROJ_STL":          stl,
            "PROJ_BLK":          blk,
            "PROJ_FG3M":         fg3m,
            "PROJ_TOV":          tov,
            "PROJ_FG_PCT":       fg_pct,
            "PROJ_FT_PCT":       ft_pct,
            "PROJ_MIN":          mn,
            "BASE_FV":           0.0,
            "PROJ_FV":           proj_fv,
            "FV_DELTA":          proj_fv,
            "FANTASY_VALUE":     proj_fv,
            "CONFIDENCE":        "LOW",
            "PROJ_RANK":         999,
            "RANK":              999,
        })

    return pd.DataFrame(rows)
