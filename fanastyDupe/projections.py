import pandas as pd

PROJ_STATS = ["PTS", "REB", "AST", "STL", "BLK", "FG3M", "TOV"]

INJURY_RETURN_FACTOR = 0.82  # conservative discount for players returning from a missed season
MIN_PREV_GP_FOR_RETURN = 20   # must have played meaningfully in their last active season

# (max_age_inclusive, multiplier applied to next season)
_AGE_CURVE = [
    (21, 1.07),
    (23, 1.05),
    (25, 1.02),
    (27, 1.01),
    (29, 1.00),
    (31, 0.98),
    (33, 0.95),
    (35, 0.91),
    (float("inf"), 0.86),
]


def _age_factor(age: float) -> float:
    if pd.isna(age):
        return 1.0
    for threshold, factor in _AGE_CURVE:
        if age <= threshold:
            return factor
    return 0.86


def _confidence(gp: int, age: float) -> str:
    if gp >= 60 and 22 <= age <= 33:
        return "HIGH"
    elif gp >= 35:
        return "MEDIUM"
    return "LOW"


def _col(df: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in df.columns:
            return df[name]
    return pd.Series(0.0, index=df.index)


class ProjectionEngine:
    """
    Projects next-season per-game stats using a weighted blend of the last
    two seasons plus an age-curve multiplier.

    base_df  — most recent completed season (70% weight)
    prev_df  — season before that (30% weight); optional
    scoring  — fantasy scoring weights dict
    """

    def __init__(
        self,
        base_df: pd.DataFrame,
        prev_df: pd.DataFrame | None,
        scoring: dict[str, float],
    ):
        self.base = base_df.copy()
        self.prev = prev_df.copy() if prev_df is not None else None
        self.scoring = scoring

    def build(self) -> pd.DataFrame:
        stat_cols = PROJ_STATS + ["FG_PCT", "FT_PCT", "MIN"]

        # ── Merge previous season ─────────────────────────────────────────
        if self.prev is not None:
            prev_cols = [c for c in stat_cols if c in self.prev.columns]
            prev_sub = self.prev[["PLAYER_ID"] + prev_cols].rename(
                columns={c: f"PREV_{c}" for c in prev_cols}
            )
            df = self.base.merge(prev_sub, on="PLAYER_ID", how="left")
        else:
            df = self.base.copy()

        # ── Weighted blend: 70% current + 30% previous ────────────────────
        for col in stat_cols:
            prev_col = f"PREV_{col}"
            if col in df.columns and prev_col in df.columns:
                curr = df[col].fillna(df[prev_col])
                prev = df[prev_col].fillna(df[col])
                df[f"BL_{col}"] = curr * 0.70 + prev * 0.30
            elif col in df.columns:
                df[f"BL_{col}"] = df[col]
            else:
                df[f"BL_{col}"] = 0.0

        # ── Age-curve adjustment ──────────────────────────────────────────
        next_age = df["AGE"].fillna(28) + 1
        factors = next_age.map(_age_factor)

        for col in PROJ_STATS:
            blend = df[f"BL_{col}"].fillna(0)
            if col == "TOV":
                # Improvement → fewer turnovers (divide by factor when factor > 1)
                df[f"PROJ_{col}"] = (blend / factors).round(1).clip(lower=0)
            else:
                df[f"PROJ_{col}"] = (blend * factors).round(1).clip(lower=0)

        for col in ["FG_PCT", "FT_PCT", "MIN"]:
            df[f"PROJ_{col}"] = df[f"BL_{col}"].round(3 if "PCT" in col else 1)

        # ── Projected fantasy value ───────────────────────────────────────
        s = self.scoring
        df["PROJ_FV"] = (
            _col(df, "PROJ_PTS")  * s.get("pts",  1.0)
            + _col(df, "PROJ_REB")  * s.get("reb",  1.2)
            + _col(df, "PROJ_AST")  * s.get("ast",  1.5)
            + _col(df, "PROJ_STL")  * s.get("stl",  3.0)
            + _col(df, "PROJ_BLK")  * s.get("blk",  3.0)
            + _col(df, "PROJ_FG3M") * s.get("fg3m", 1.0)
            + _col(df, "PROJ_TOV")  * s.get("tov", -1.0)
        ).round(2)

        df["BASE_FV"] = (
            _col(df, "PTS")  * s.get("pts",  1.0)
            + _col(df, "REB")  * s.get("reb",  1.2)
            + _col(df, "AST")  * s.get("ast",  1.5)
            + _col(df, "STL")  * s.get("stl",  3.0)
            + _col(df, "BLK")  * s.get("blk",  3.0)
            + _col(df, "FG3M") * s.get("fg3m", 1.0)
            + _col(df, "TOV")  * s.get("tov", -1.0)
        ).round(2)

        df["FV_DELTA"]  = (df["PROJ_FV"] - df["BASE_FV"]).round(2)
        df["PROJ_RANK"] = df["PROJ_FV"].rank(ascending=False, method="min").astype(int)
        df["CONFIDENCE"] = df.apply(
            lambda r: _confidence(int(r.get("GP", 0)), float(r.get("AGE", 28))), axis=1
        )

        # Overwrite stat columns with projected values so FantasyEvaluator
        # can be used directly in trade/start-sit with projected numbers.
        for col in PROJ_STATS:
            df[col] = df[f"PROJ_{col}"]

        # FantasyEvaluator compatibility aliases
        df["FANTASY_VALUE"] = df["PROJ_FV"]
        df["RANK"]          = df["PROJ_RANK"]

        # ── Inject injury returnees ───────────────────────────────────────
        returnees = self._build_returnees()
        if not returnees.empty:
            df = pd.concat([df, returnees], ignore_index=True)
            df["PROJ_RANK"] = df["PROJ_FV"].rank(ascending=False, method="min").astype(int)
            df["RANK"]      = df["FANTASY_VALUE"].rank(ascending=False, method="min").astype(int)

        return df

    def _build_returnees(self) -> pd.DataFrame:
        """
        Players present in prev_df but absent from base_df — they missed an entire
        season (injury, suspension, etc.).  Project using their last active stats
        discounted by INJURY_RETURN_FACTOR and the age curve.
        """
        if self.prev is None:
            return pd.DataFrame()

        base_ids = set(self.base["PLAYER_ID"].values)
        missed = self.prev[
            (~self.prev["PLAYER_ID"].isin(base_ids)) &
            (self.prev["GP"] >= MIN_PREV_GP_FOR_RETURN)
        ].copy()

        if missed.empty:
            return pd.DataFrame()

        # Age in projection year = last active age + 2 (one missed season + one projected)
        missed["AGE"] = missed["AGE"].fillna(28) + 2
        age_factors   = missed["AGE"].map(_age_factor) * INJURY_RETURN_FACTOR

        # Build PROJ_* columns before overwriting originals (BASE_FV needs originals)
        for col in PROJ_STATS:
            if col not in missed.columns:
                missed[f"PROJ_{col}"] = 0.0
            elif col == "TOV":
                missed[f"PROJ_{col}"] = (missed[col] * INJURY_RETURN_FACTOR).round(1).clip(lower=0)
            else:
                missed[f"PROJ_{col}"] = (missed[col] * age_factors).round(1).clip(lower=0)

        for col in ["FG_PCT", "FT_PCT", "MIN"]:
            missed[f"PROJ_{col}"] = _col(missed, col).round(3 if "PCT" in col else 1)

        s = self.scoring
        missed["BASE_FV"] = (
            _col(missed, "PTS")  * s.get("pts",  1.0)
            + _col(missed, "REB")  * s.get("reb",  1.2)
            + _col(missed, "AST")  * s.get("ast",  1.5)
            + _col(missed, "STL")  * s.get("stl",  3.0)
            + _col(missed, "BLK")  * s.get("blk",  3.0)
            + _col(missed, "FG3M") * s.get("fg3m", 1.0)
            + _col(missed, "TOV")  * s.get("tov", -1.0)
        ).round(2)

        missed["PROJ_FV"] = (
            _col(missed, "PROJ_PTS")  * s.get("pts",  1.0)
            + _col(missed, "PROJ_REB")  * s.get("reb",  1.2)
            + _col(missed, "PROJ_AST")  * s.get("ast",  1.5)
            + _col(missed, "PROJ_STL")  * s.get("stl",  3.0)
            + _col(missed, "PROJ_BLK")  * s.get("blk",  3.0)
            + _col(missed, "PROJ_FG3M") * s.get("fg3m", 1.0)
            + _col(missed, "PROJ_TOV")  * s.get("tov", -1.0)
        ).round(2)

        missed["FV_DELTA"]  = (missed["PROJ_FV"] - missed["BASE_FV"]).round(2)
        missed["CONFIDENCE"] = "LOW"

        # Override stat columns with projected values (consistent with main build)
        for col in PROJ_STATS:
            missed[col] = missed[f"PROJ_{col}"]

        missed["FANTASY_VALUE"] = missed["PROJ_FV"]
        missed["PROJ_RANK"]     = 999  # re-ranked after concat in build()
        missed["RANK"]          = 999

        return missed
