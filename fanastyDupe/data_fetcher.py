import time
import pandas as pd
import streamlit as st
from nba_api.stats.endpoints import leaguedashplayerstats, playergamelog


@st.cache_data(ttl=3600, show_spinner=False)
def get_season_stats(season: str = "2025-26") -> pd.DataFrame:
    time.sleep(0.6)
    endpoint = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        per_mode_detailed="PerGame",
        season_type_all_star="Regular Season",
    )
    df = endpoint.get_data_frames()[0]
    if df.empty:
        raise ValueError(f"No data returned for season {season}.")
    return df


@st.cache_data(ttl=1800, show_spinner=False)
def get_player_game_logs(player_id: int, season: str = "2024-25") -> pd.DataFrame:
    time.sleep(0.6)
    endpoint = playergamelog.PlayerGameLog(
        player_id=player_id,
        season=season,
        season_type_all_star="Regular Season",
    )
    return endpoint.get_data_frames()[0]