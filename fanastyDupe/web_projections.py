"""
Fetch and normalize fantasy basketball projections from public websites.

Sources:
  - FantasyPros  (fantasypros.com)  — consensus ROS rankings, season totals → per-game
  - HashtagBasketball               — per-game projections

All functions accept `scoring_key: tuple` (a sorted-items tuple of the scoring dict)
so they are compatible with st.cache_data (which requires hashable arguments).
"""

import re
import time
import unicodedata
from io import StringIO

import pandas as pd
import requests
import streamlit as st

# ─── HTTP Headers ─────────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_NBA_ABBREVS = {
    "ATL","BOS","BKN","CHA","CHI","CLE","DAL","DEN","DET","GSW",
    "HOU","IND","LAC","LAL","MEM","MIA","MIL","MIN","NOP","NYK",
    "OKC","ORL","PHI","PHX","POR","SAC","SAS","SA","TOR","UTA","WAS",
}


# ─── Utilities ────────────────────────────────────────────────────────────────
def norm_name(name: str) -> str:
    """Lowercase, strip accents, drop non-alpha, collapse whitespace."""
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z\s]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _find_col(df: pd.DataFrame, *aliases: str) -> str | None:
    """Return first column name that contains any of the given aliases."""
    for col in df.columns:
        key = re.sub(r"[\s_%]", "", str(col).lower())
        for alias in aliases:
            if re.sub(r"[\s_%]", "", alias.lower()) in key:
                return col
    return None


def _strip_team_pos(name: str) -> str:
    """Remove team/position info from player name strings.

    Handles formats like:
      'Shai Gilgeous-Alexander (OKC - PG)'  → 'Shai Gilgeous-Alexander'
      'LeBron James LAL SF'                  → 'LeBron James'
    """
    # Remove parenthetical team/position block first
    name = re.sub(r"\s*\(.*?\)\s*", "", str(name)).strip()
    # Then drop any trailing uppercase abbreviation tokens
    parts = name.split()
    while parts and (
        parts[-1].upper() in _NBA_ABBREVS
        or re.fullmatch(r"[A-Z]{1,2}", parts[-1])
        or parts[-1] in ("-", "|")
    ):
        parts.pop()
    return " ".join(parts).strip("- ").strip()


def _proj_fv(df: pd.DataFrame, scoring: dict) -> pd.Series:
    """Compute fantasy value from PROJ_PTS / PROJ_REB / … columns."""
    def _g(col):
        return pd.to_numeric(df.get(col, pd.Series(0.0, index=df.index)), errors="coerce").fillna(0)

    return (
        _g("PROJ_PTS") * scoring.get("pts",  1.0)
        + _g("PROJ_REB") * scoring.get("reb",  1.2)
        + _g("PROJ_AST") * scoring.get("ast",  1.5)
        + _g("PROJ_STL") * scoring.get("stl",  3.0)
        + _g("PROJ_BLK") * scoring.get("blk",  3.0)
        + _g("PROJ_3PM") * scoring.get("fg3m", 1.0)
        + _g("PROJ_TOV") * scoring.get("tov", -1.0)
    ).round(2)


def _flatten_cols(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(str(v) for v in col if not str(v).startswith("Unnamed")).strip()
            for col in df.columns
        ]
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ─── FantasyPros ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fantasypros(scoring_key: tuple) -> tuple[pd.DataFrame, str]:
    """
    Returns (DataFrame, status_message).
    Stats are season totals on the page; we divide by GP to get per-game.
    """
    scoring = dict(scoring_key)
    try:
        r = requests.get(
            "https://www.fantasypros.com/nba/projections/ros-rankings.php",
            headers=_HEADERS, timeout=20,
        )
        r.raise_for_status()

        tables = pd.read_html(StringIO(r.text))
        if not tables:
            return pd.DataFrame(), "No tables found on page"

        df = _flatten_cols(max(tables, key=len).copy())

        # Player name column
        name_col = _find_col(df, "player", "name")
        if name_col is None:
            return pd.DataFrame(), "Could not find player name column"

        df["PLAYER_NAME"] = df[name_col].astype(str).apply(_strip_team_pos)
        df = df[df["PLAYER_NAME"].str.len() > 3].copy()
        df["PLAYER_NAME_NORM"] = df["PLAYER_NAME"].apply(norm_name)

        # Games projected (needed to convert totals → per-game).
        # Use exact "GP" / "G" match before falling back to substring search
        # to avoid accidentally matching "FG%" (which also contains "g").
        gp_col = next((c for c in df.columns if c.strip().upper() in ("GP", "G")), None)
        if gp_col is None:
            gp_col = _find_col(df, "games played")
        gp = pd.to_numeric(df[gp_col], errors="coerce").fillna(1).clip(lower=1) if gp_col else pd.Series(1, index=df.index)
        df["GP_PROJ"] = gp

        # Season totals → per-game
        for src_alias, dest in [
            (("pts",),          "PROJ_PTS"),
            (("reb",),          "PROJ_REB"),
            (("ast",),          "PROJ_AST"),
            (("stl",),          "PROJ_STL"),
            (("blk",),          "PROJ_BLK"),
            (("3pm", "3pt"),    "PROJ_3PM"),
            (("to", "tov", "turnovers"), "PROJ_TOV"),
            (("min",),          "PROJ_MIN"),
        ]:
            col = _find_col(df, *src_alias)
            if col:
                df[dest] = (pd.to_numeric(df[col], errors="coerce") / gp).round(1)

        for src_alias, dest in [(("fg%", "fgpct"), "PROJ_FG_PCT"), (("ft%", "ftpct"), "PROJ_FT_PCT")]:
            col = _find_col(df, *src_alias)
            if col:
                df[dest] = pd.to_numeric(df[col], errors="coerce").round(3)

        df["PROJ_FV"] = _proj_fv(df, scoring)
        df["PROJ_RANK"] = df["PROJ_FV"].rank(ascending=False, method="min").astype(int)
        df["SOURCE"] = "FantasyPros"

        n = len(df)
        return df.reset_index(drop=True), f"Loaded {n} players"

    except Exception as exc:
        return pd.DataFrame(), f"Error: {exc}"


# ─── HashtagBasketball ────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_hashtagbasketball(scoring_key: tuple) -> tuple[pd.DataFrame, str]:
    """
    Returns (DataFrame, status_message).
    Stats on this site are already per-game.
    """
    scoring = dict(scoring_key)
    try:
        time.sleep(0.4)
        r = requests.get(
            "https://hashtagbasketball.com/fantasy-basketball-projections",
            headers=_HEADERS, timeout=20,
        )
        r.raise_for_status()

        tables = pd.read_html(StringIO(r.text))
        if not tables:
            return pd.DataFrame(), "No tables found on page"

        df = _flatten_cols(max(tables, key=len).copy())

        name_col = _find_col(df, "player", "name")
        if name_col is None:
            return pd.DataFrame(), "Could not find player name column"

        # HashtagBasketball appends an abbreviated form in the same cell,
        # e.g. "Nikola JokicN.Jokic" or "Victor WembanyamaV.Wembanyama".
        # Strip the "X.Lastname" suffix at the end to recover the full name.
        raw = df[name_col].astype(str)
        df["PLAYER_NAME"] = (
            raw.str.replace(r"[A-Z]\.[A-Za-z'-]+$", "", regex=True)
               .str.split(",").str[0]
               .str.strip()
        )
        df = df[df["PLAYER_NAME"].str.len() > 3].copy()
        df["PLAYER_NAME_NORM"] = df["PLAYER_NAME"].apply(norm_name)

        # Map per-game columns to standard PROJ_* names
        mapping = [
            (("pts",),             "PROJ_PTS"),
            (("treb", "reb"),      "PROJ_REB"),
            (("ast",),             "PROJ_AST"),
            (("stl",),             "PROJ_STL"),
            (("blk",),             "PROJ_BLK"),
            (("3pm", "3pt"),       "PROJ_3PM"),
            (("to", "tov"),        "PROJ_TOV"),
            (("mpg", "min"),       "PROJ_MIN"),
        ]
        for aliases, dest in mapping:
            if dest not in df.columns:
                col = _find_col(df, *aliases)
                if col:
                    df[dest] = pd.to_numeric(df[col], errors="coerce")

        for aliases, dest in [(("fg%",), "PROJ_FG_PCT"), (("ft%",), "PROJ_FT_PCT")]:
            col = _find_col(df, *aliases)
            if col:
                df[dest] = pd.to_numeric(df[col], errors="coerce").round(3)

        gp_col = _find_col(df, "gp", " g ")
        df["GP_PROJ"] = pd.to_numeric(df[gp_col], errors="coerce") if gp_col else None

        df["PROJ_FV"] = _proj_fv(df, scoring)
        df["PROJ_RANK"] = df["PROJ_FV"].rank(ascending=False, method="min").astype(int)
        df["SOURCE"] = "HashtagBasketball"

        n = len(df)
        return df.reset_index(drop=True), f"Loaded {n} players"

    except Exception as exc:
        return pd.DataFrame(), f"Error: {exc}"


# ─── Merge all sources into comparison table ──────────────────────────────────
def build_comparison(
    our_proj_df: pd.DataFrame,
    web_dfs: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Wide table with one row per player and columns for each source's FV and rank.
    Adds a Consensus FV column (mean of available sources).
    """
    if "PLAYER_NAME_NORM" not in our_proj_df.columns:
        our_proj_df = our_proj_df.copy()
        our_proj_df["PLAYER_NAME_NORM"] = our_proj_df["PLAYER_NAME"].apply(norm_name)

    base = our_proj_df[
        ["PLAYER_NAME", "PLAYER_NAME_NORM", "TEAM_ABBREVIATION", "AGE",
         "PROJ_FV", "PROJ_RANK", "CONFIDENCE"]
    ].copy().rename(columns={"PROJ_FV": "Our Model", "PROJ_RANK": "Our Model Rank"})

    for src_name, sdf in web_dfs.items():
        if sdf.empty or "PLAYER_NAME_NORM" not in sdf.columns:
            continue
        sub = (
            sdf[["PLAYER_NAME_NORM", "PROJ_FV", "PROJ_RANK"]]
            .rename(columns={"PROJ_FV": src_name, "PROJ_RANK": f"{src_name} Rank"})
        )
        base = base.merge(sub, on="PLAYER_NAME_NORM", how="left")

    fv_cols = ["Our Model"] + [s for s in web_dfs if not web_dfs[s].empty]
    present  = [c for c in fv_cols if c in base.columns]
    base["Consensus FV"]   = base[present].mean(axis=1).round(1)
    base["Consensus Rank"] = base["Consensus FV"].rank(ascending=False, method="min").astype(int)

    return base.sort_values("Consensus Rank").reset_index(drop=True)