import pandas as pd

TRADE_STAT_COLS = ["PTS", "REB", "AST", "STL", "BLK", "FG3M", "TOV"]


class FantasyEvaluator:
    def __init__(self, stats_df: pd.DataFrame, scoring: dict[str, float]):
        self.scoring = scoring
        self.stats = stats_df.copy()
        self._compute_fantasy_value()

    def _compute_fantasy_value(self):
        s = self.scoring
        df = self.stats
        df["FANTASY_VALUE"] = (
            df["PTS"]  * s.get("pts",  1.0)
            + df["REB"]  * s.get("reb",  1.2)
            + df["AST"]  * s.get("ast",  1.5)
            + df["STL"]  * s.get("stl",  3.0)
            + df["BLK"]  * s.get("blk",  3.0)
            + df["FG3M"] * s.get("fg3m", 1.0)
            + df["TOV"]  * s.get("tov", -1.0)
        ).round(2)
        df["RANK"] = df["FANTASY_VALUE"].rank(ascending=False, method="min").astype(int)

    def compute_game_log_value(self, logs: pd.DataFrame) -> pd.Series:
        s = self.scoring
        return (
            logs["PTS"]  * s.get("pts",  1.0)
            + logs["REB"]  * s.get("reb",  1.2)
            + logs["AST"]  * s.get("ast",  1.5)
            + logs["STL"]  * s.get("stl",  3.0)
            + logs["BLK"]  * s.get("blk",  3.0)
            + logs["FG3M"] * s.get("fg3m", 1.0)
            + logs["TOV"]  * s.get("tov", -1.0)
        ).round(2)

    def get_player_stats(self, player_id: int) -> pd.Series | None:
        row = self.stats[self.stats["PLAYER_ID"] == player_id]
        return row.iloc[0] if not row.empty else None

    def get_rankings(self, min_games: int = 10, limit: int = 250) -> pd.DataFrame:
        df = self.stats[self.stats["GP"] >= min_games].copy()
        return df.nlargest(limit, "FANTASY_VALUE").reset_index(drop=True)

    def evaluate_trade(self, give_ids: list[int], receive_ids: list[int]) -> dict:
        give_df = self.stats[self.stats["PLAYER_ID"].isin(give_ids)]
        recv_df = self.stats[self.stats["PLAYER_ID"].isin(receive_ids)]

        give_total = give_df["FANTASY_VALUE"].sum()
        recv_total = recv_df["FANTASY_VALUE"].sum()

        pct_diff = ((recv_total - give_total) / give_total * 100) if give_total > 0 else 0.0

        if pct_diff >= 20:
            grade, label, color = "A+", "You Win Big!", "win-big"
        elif pct_diff >= 10:
            grade, label, color = "A",  "You Win!",             "win-big"
        elif pct_diff >= 3:
            grade, label, color = "B",  "Slight Edge for You",  "win"
        elif pct_diff >= -3:
            grade, label, color = "C",  "Fair Trade",           "fair"
        elif pct_diff >= -10:
            grade, label, color = "D",  "Slight Edge for Them", "lose"
        elif pct_diff >= -20:
            grade, label, color = "F",  "You Lose",             "lose"
        else:
            grade, label, color = "F-", "You Lose Big!",        "lose-big"

        cat_give = {c: (give_df[c].mean() if not give_df.empty else 0.0) for c in TRADE_STAT_COLS}
        cat_recv = {c: (recv_df[c].mean() if not recv_df.empty else 0.0) for c in TRADE_STAT_COLS}

        return {
            "give_total": round(give_total, 1),
            "recv_total": round(recv_total, 1),
            "pct_diff":   round(pct_diff, 1),
            "grade": grade, "label": label, "color": color,
            "give_df": give_df, "recv_df": recv_df,
            "cat_give": cat_give, "cat_recv": cat_recv,
        }

    def get_start_sit(self, player_ids: list[int], n_starters: int) -> pd.DataFrame:
        df = self.stats[self.stats["PLAYER_ID"].isin(player_ids)].copy()
        df = df.sort_values("FANTASY_VALUE", ascending=False).reset_index(drop=True)
        df["RECOMMENDATION"] = (
            ["START"] * min(n_starters, len(df))
            + ["SIT"]   * max(0, len(df) - n_starters)
        )
        return df