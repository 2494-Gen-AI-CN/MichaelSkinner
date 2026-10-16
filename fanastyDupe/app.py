import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from data_fetcher import get_player_game_logs, get_season_stats
from evaluator import FantasyEvaluator, TRADE_STAT_COLS
from projections import ProjectionEngine
from web_projections import (
    build_comparison,
    fetch_fantasypros,
    fetch_hashtagbasketball,
    norm_name,
)

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fantasy Basketball Analyzer",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main .block-container { padding-top: 1rem; }
  .grade-badge { font-size: 3.5rem; font-weight: 900; text-align: center; line-height: 1.1; }
  .win-big  { color: #00b894; }
  .win      { color: #55efc4; }
  .fair     { color: #fdcb6e; }
  .lose     { color: #e17055; }
  .lose-big { color: #d63031; }
  .start-pill {
    background: #00b894; color: #fff;
    border-radius: 12px; padding: 2px 10px;
    font-size: 0.72rem; font-weight: 700; display: inline-block;
  }
  .sit-pill {
    background: #636e72; color: #fff;
    border-radius: 12px; padding: 2px 10px;
    font-size: 0.72rem; font-weight: 700; display: inline-block;
  }
  .conf-high   { color: #00b894; font-weight: 700; }
  .conf-medium { color: #fdcb6e; font-weight: 700; }
  .conf-low    { color: #e17055; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ─── Scoring Presets ──────────────────────────────────────────────────────────
PRESETS = {
    "ESPN Standard":  {"pts": 1.0, "reb": 1.2,  "ast": 1.5, "stl": 3.0, "blk": 3.0, "fg3m": 1.0, "tov": -1.0},
    "Yahoo Standard": {"pts": 1.0, "reb": 1.2,  "ast": 1.5, "stl": 2.0, "blk": 2.0, "fg3m": 1.0, "tov": -1.0},
    "DraftKings":     {"pts": 1.0, "reb": 1.25, "ast": 1.5, "stl": 2.0, "blk": 2.0, "fg3m": 0.5, "tov": -0.5},
    "Custom":         {"pts": 1.0, "reb": 1.2,  "ast": 1.5, "stl": 3.0, "blk": 3.0, "fg3m": 1.0, "tov": -1.0},
}

SEASONS        = ["2025-26", "2026-27", "2024-25", "2023-24"]
PROJ_BASE_SEA  = "2025-26"
PROJ_PREV_SEA  = "2024-25"
PROJ_LABEL     = "📈 Projections (2026-27)"
ACTUAL_LABEL   = "📊 Actual Stats"

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏀 Fantasy Hoops")
    st.caption("Trade evaluator & start/sit advisor")
    st.divider()

    st.subheader("Data Source")
    use_projections = st.toggle(
        "Use 2026-27 Projections",
        value=True,
        help="Season just started — projections blend 2025-26 + 2024-25 stats with an age-curve model.",
    )
    if use_projections:
        st.caption("Projections based on 2025-26 (70%) + 2024-25 (30%) + age curve")
        actual_season = PROJ_BASE_SEA
    else:
        actual_season = st.selectbox("Actual Season", SEASONS, index=0)

    st.divider()
    st.subheader("Scoring Settings")
    preset_name = st.selectbox("Preset", list(PRESETS.keys()), index=0)

    if preset_name == "Custom":
        scoring = {
            "pts":  st.number_input("Points (PTS)",     value=1.0,  step=0.1, format="%.1f"),
            "reb":  st.number_input("Rebounds (REB)",   value=1.2,  step=0.1, format="%.1f"),
            "ast":  st.number_input("Assists (AST)",    value=1.5,  step=0.1, format="%.1f"),
            "stl":  st.number_input("Steals (STL)",     value=3.0,  step=0.1, format="%.1f"),
            "blk":  st.number_input("Blocks (BLK)",     value=3.0,  step=0.1, format="%.1f"),
            "fg3m": st.number_input("3-Pointers (3PM)", value=1.0,  step=0.1, format="%.1f"),
            "tov":  st.number_input("Turnovers (TOV)",  value=-1.0, step=0.1, format="%.1f"),
        }
    else:
        scoring = PRESETS[preset_name]
        score_tbl = pd.DataFrame([{"Stat": k.upper(), "Pts/Stat": v} for k, v in scoring.items()])
        st.dataframe(score_tbl, hide_index=True, use_container_width=True, height=270)

    st.divider()
    st.caption("Data via NBA.com API · Built with Streamlit")

# ─── Load NBA Data ────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_data(season: str) -> pd.DataFrame:
    return get_season_stats(season)

with st.spinner(f"Loading {actual_season} NBA data..."):
    try:
        raw_df = load_data(actual_season)
        evaluator = FantasyEvaluator(raw_df, scoring)
    except Exception as err:
        st.error(f"Could not load NBA data: {err}")
        st.stop()

# ─── Build Projections ────────────────────────────────────────────────────────
with st.spinner("Building 2026-27 projections..."):
    try:
        proj_base = load_data(PROJ_BASE_SEA) if actual_season != PROJ_BASE_SEA else raw_df
        try:
            proj_prev = load_data(PROJ_PREV_SEA)
        except Exception:
            proj_prev = None

        engine    = ProjectionEngine(proj_base, proj_prev, scoring)
        proj_df   = engine.build()
        proj_eval = FantasyEvaluator(proj_df, scoring)
    except Exception as proj_err:
        st.warning(f"Could not build projections: {proj_err}")
        proj_df   = None
        proj_eval = evaluator

active_eval = proj_eval if use_projections else evaluator
mode_label  = PROJ_LABEL if use_projections else ACTUAL_LABEL

# ─── Session State ────────────────────────────────────────────────────────────
for _k in ("give_ids", "recv_ids", "roster_ids"):
    if _k not in st.session_state:
        st.session_state[_k] = []

# ─── Player Selector (always from projection pool — full season) ──────────────
_rows = (
    proj_eval.stats[proj_eval.stats["GP"] >= 5]
    .sort_values("FANTASY_VALUE", ascending=False)[["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"]]
    .values.tolist()
)
_lbl       = lambda r: f"{r[1]} ({r[2]})"
name_to_id = {_lbl(r): int(r[0]) for r in _rows}
all_names  = list(name_to_id.keys())

# ─── Tabs ─────────────────────────────────────────────────────────────────────
st.title("🏀 Fantasy Basketball Analyzer")
st.caption(f"Active mode: **{mode_label}**")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Player Explorer",
    "⚖️ Trade Evaluator",
    "🎯 Start / Sit",
    "📈 Projections",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PLAYER EXPLORER
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    f1, f2, f3 = st.columns([3, 1, 1])
    with f1:
        query = st.text_input("🔍 Search Player", placeholder="e.g. LeBron, Curry, Giannis")
    with f2:
        min_gp = st.number_input("Min Games Played", value=10, min_value=1, max_value=82)
    with f3:
        sort_by = st.selectbox("Sort By", ["Fantasy Value", "PTS", "REB", "AST", "STL", "BLK"])

    sort_map = {"Fantasy Value": "FANTASY_VALUE", "PTS": "PTS", "REB": "REB",
                "AST": "AST", "STL": "STL", "BLK": "BLK"}

    view = active_eval.stats[active_eval.stats["GP"] >= min_gp].copy()
    if query:
        view = view[view["PLAYER_NAME"].str.lower().str.contains(query.lower(), na=False)]
    view = view.sort_values(sort_map[sort_by], ascending=False)

    # ── Single-player detail card ─────────────────────────────────────────────
    if query and len(view) == 1:
        p = view.iloc[0]
        st.divider()

        conf_html = ""
        if "CONFIDENCE" in p.index:
            conf = p["CONFIDENCE"]
            cls  = {"HIGH": "conf-high", "MEDIUM": "conf-medium", "LOW": "conf-low"}.get(conf, "")
            conf_html = f' · <span class="{cls}">{conf} confidence</span>'

        delta_html = ""
        if "FV_DELTA" in p.index:
            delta = p["FV_DELTA"]
            arrow = "▲" if delta >= 0 else "▼"
            color = "#00b894" if delta >= 0 else "#d63031"
            delta_html = f' · <span style="color:{color}">{arrow} {abs(delta):.1f} vs last season</span>'

        st.markdown(
            f"### {p['PLAYER_NAME']} · {p['TEAM_ABBREVIATION']} · Rank #{p['RANK']}"
            + conf_html + delta_html,
            unsafe_allow_html=True,
        )

        m = st.columns(7)
        lbl = "Proj FV/G" if use_projections else "FV/G"
        m[0].metric(lbl,  f"{p['FANTASY_VALUE']:.1f}")
        m[1].metric("PTS", f"{p['PTS']:.1f}")
        m[2].metric("REB", f"{p['REB']:.1f}")
        m[3].metric("AST", f"{p['AST']:.1f}")
        m[4].metric("STL", f"{p['STL']:.1f}")
        m[5].metric("BLK", f"{p['BLK']:.1f}")
        m[6].metric("3PM", f"{p['FG3M']:.1f}")

        # Recent game logs always from actual data
        with st.spinner("Fetching recent game logs..."):
            try:
                logs = get_player_game_logs(int(p["PLAYER_ID"]), PROJ_BASE_SEA)
                if not logs.empty:
                    recent = logs.head(15).iloc[::-1].reset_index(drop=True)
                    fv = active_eval.compute_game_log_value(recent)
                    colors = ["#00b894" if v >= p["FANTASY_VALUE"] else "#d63031" for v in fv]

                    fig = go.Figure(go.Bar(
                        x=recent["GAME_DATE"], y=fv,
                        marker_color=colors,
                        text=fv.round(1), textposition="outside",
                        customdata=recent[["PTS", "REB", "AST"]].values,
                        hovertemplate="<b>%{x}</b><br>FP: %{y:.1f}<br>PTS %{customdata[0]} / REB %{customdata[1]} / AST %{customdata[2]}<extra></extra>",
                    ))
                    ref_label = f"Projected avg {p['FANTASY_VALUE']:.1f}" if use_projections else f"Season avg {p['FANTASY_VALUE']:.1f}"
                    fig.add_hline(
                        y=p["FANTASY_VALUE"], line_dash="dot", line_color="#fdcb6e",
                        annotation_text=ref_label, annotation_position="top left",
                    )
                    fig.update_layout(
                        title=f"2025-26 Game Log — Fantasy Points per Game",
                        xaxis_title="", yaxis_title="Fantasy Points",
                        height=320, plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=45, b=10),
                    )
                    st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.caption("Game logs unavailable for this player/season.")

    # ── Rankings table ─────────────────────────────────────────────────────────
    st.divider()
    _want = ["RANK", "PLAYER_NAME", "TEAM_ABBREVIATION", "AGE", "GP", "MIN",
             "PTS", "REB", "AST", "STL", "BLK", "FG3M", "TOV",
             "FG_PCT", "FT_PCT", "FANTASY_VALUE"]
    if use_projections:
        _want += ["FV_DELTA", "CONFIDENCE"]

    tbl = view[[c for c in _want if c in view.columns]].head(200).copy()
    tbl = tbl.rename(columns={
        "PLAYER_NAME": "Player", "TEAM_ABBREVIATION": "Team",
        "FANTASY_VALUE": "FV/G" if not use_projections else "Proj FV/G",
        "FG_PCT": "FG%", "FT_PCT": "FT%", "FG3M": "3PM", "RANK": "#",
        "FV_DELTA": "Δ vs 25-26", "CONFIDENCE": "Conf.",
    })
    for col in ["PTS", "REB", "AST", "STL", "BLK", "3PM", "TOV", "MIN",
                "FV/G", "Proj FV/G", "Δ vs 25-26"]:
        if col in tbl.columns:
            tbl[col] = tbl[col].round(1)
    for pct in ["FG%", "FT%"]:
        if pct in tbl.columns:
            tbl[pct] = (tbl[pct] * 100).round(1)

    st.dataframe(tbl, use_container_width=True, height=520, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — TRADE EVALUATOR
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Trade Evaluator")
    st.caption(f"Using: **{mode_label}**  ·  Toggle the mode in the sidebar.")

    if st.button("🗑️ Clear Trade", key="clear_trade"):
        st.session_state.give_ids = []
        st.session_state.recv_ids = []
        st.rerun()

    col_give, col_arrow, col_recv = st.columns([5, 1, 5])

    def _render_side(header: str, id_key: str, sel_key: str, btn_key: str, rm_prefix: str):
        st.markdown(f"### {header}")
        sel = st.selectbox("Search player", all_names, key=sel_key)
        if st.button("＋ Add", key=btn_key):
            pid = name_to_id[sel]
            if pid not in st.session_state[id_key]:
                st.session_state[id_key].append(pid)
                st.rerun()

        total = 0.0
        for pid in list(st.session_state[id_key]):
            row = active_eval.get_player_stats(pid)
            if row is not None:
                fv = row["FANTASY_VALUE"]
                total += fv
                c1, c2, c3 = st.columns([4, 2, 1])
                c1.markdown(f"**{row['PLAYER_NAME']}** ({row['TEAM_ABBREVIATION']})")
                c2.markdown(f"FV: **{fv:.1f}**/g")
                if c3.button("✕", key=f"{rm_prefix}_{pid}"):
                    st.session_state[id_key].remove(pid)
                    st.rerun()

        st.divider()
        st.metric("Total FV/Game", f"{total:.1f}")
        return total

    with col_give:
        _render_side("You Give Away", "give_ids", "give_sel", "give_add", "rm_give")
    with col_arrow:
        st.markdown(
            "<div style='text-align:center;padding-top:160px;font-size:2rem'>⇄</div>",
            unsafe_allow_html=True,
        )
    with col_recv:
        _render_side("You Receive", "recv_ids", "recv_sel", "recv_add", "rm_recv")

    # ── Grade & Analysis ───────────────────────────────────────────────────────
    if st.session_state.give_ids and st.session_state.recv_ids:
        result = active_eval.evaluate_trade(st.session_state.give_ids, st.session_state.recv_ids)
        st.divider()

        _, gc, _ = st.columns([1, 2, 1])
        with gc:
            st.markdown(
                f'<div class="grade-badge {result["color"]}">{result["grade"]}</div>'
                f'<p style="text-align:center;font-size:1.25rem;font-weight:600;margin-top:6px">{result["label"]}</p>'
                f'<p style="text-align:center;color:#b2bec3">You receive {result["pct_diff"]:+.1f}% in fantasy value</p>',
                unsafe_allow_html=True,
            )

        # Radar chart
        st.subheader("Stat Category Breakdown (Per-Game Average)")
        cats = TRADE_STAT_COLS
        fig_r = go.Figure()
        fig_r.add_trace(go.Scatterpolar(
            r=[result["cat_give"][c] for c in cats], theta=cats,
            fill="toself", name="You Give", line_color="#e17055",
        ))
        fig_r.add_trace(go.Scatterpolar(
            r=[result["cat_recv"][c] for c in cats], theta=cats,
            fill="toself", name="You Receive", line_color="#00b894",
        ))
        fig_r.update_layout(
            polar=dict(radialaxis=dict(visible=True)),
            height=380, paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_r, use_container_width=True)

        # Side-by-side tables
        st.subheader("Player Comparison")
        _stat_cols = ["PLAYER_NAME", "TEAM_ABBREVIATION", "AGE", "GP",
                      "PTS", "REB", "AST", "STL", "BLK", "FG3M", "TOV",
                      "FG_PCT", "FT_PCT", "FANTASY_VALUE"]

        def _fmt_df(df: pd.DataFrame) -> pd.DataFrame:
            d = df[[c for c in _stat_cols if c in df.columns]].copy()
            for col in ["PTS","REB","AST","STL","BLK","FG3M","TOV","FANTASY_VALUE"]:
                if col in d.columns:
                    d[col] = d[col].round(1)
            for pct in ["FG_PCT", "FT_PCT"]:
                if pct in d.columns:
                    d[pct] = (d[pct] * 100).round(1)
            fv_label = "Proj FV/G" if use_projections else "FV/G"
            return d.rename(columns={
                "PLAYER_NAME": "Player", "TEAM_ABBREVIATION": "Team",
                "FANTASY_VALUE": fv_label, "FG_PCT": "FG%", "FT_PCT": "FT%", "FG3M": "3PM",
            })

        t1, t2 = st.columns(2)
        t1.caption("**You Give Away**")
        t1.dataframe(_fmt_df(result["give_df"]), hide_index=True, use_container_width=True)
        t2.caption("**You Receive**")
        t2.dataframe(_fmt_df(result["recv_df"]), hide_index=True, use_container_width=True)

    elif not st.session_state.give_ids and not st.session_state.recv_ids:
        st.info("Add players to both sides of the trade to get an evaluation.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — START / SIT
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Start / Sit Advisor")
    st.caption(f"Using: **{mode_label}**  ·  Toggle the mode in the sidebar.")

    sa1, sa2, sa3 = st.columns([4, 1, 1])
    with sa1:
        ss_sel = st.selectbox("Add player to roster", all_names, key="ss_sel")
    with sa2:
        n_start = st.number_input("# to Start", value=5, min_value=1, max_value=15)
    with sa3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("＋ Add", key="ss_add"):
            pid = name_to_id[ss_sel]
            if pid not in st.session_state.roster_ids:
                st.session_state.roster_ids.append(pid)
                st.rerun()

    if st.button("🗑️ Clear Roster", key="clear_roster"):
        st.session_state.roster_ids = []
        st.rerun()

    if st.session_state.roster_ids:
        recs = active_eval.get_start_sit(st.session_state.roster_ids, int(n_start))
        st.divider()

        for _, row in recs.iterrows():
            rec   = row["RECOMMENDATION"]
            badge = ('<span class="start-pill">START</span>' if rec == "START"
                     else '<span class="sit-pill">SIT</span>')

            delta_str = ""
            if use_projections and "FV_DELTA" in row.index:
                d = row["FV_DELTA"]
                arrow = "▲" if d >= 0 else "▼"
                clr   = "#00b894" if d >= 0 else "#d63031"
                delta_str = f' <span style="color:{clr};font-size:0.75rem">{arrow}{abs(d):.1f}</span>'

            c = st.columns([3, 1, 1, 1, 1, 1, 1, 1, 0.6])
            c[0].markdown(
                f"{badge}&nbsp; **{row['PLAYER_NAME']}** ({row['TEAM_ABBREVIATION']}){delta_str}",
                unsafe_allow_html=True,
            )
            fv_lbl = "Proj FV/G" if use_projections else "FV/G"
            for i, (label, stat) in enumerate(
                [(fv_lbl, "FANTASY_VALUE"), ("PTS","PTS"), ("REB","REB"),
                 ("AST","AST"), ("STL","STL"), ("BLK","BLK"), ("3PM","FG3M")],
                start=1,
            ):
                c[i].metric(label, f"{row[stat]:.1f}", label_visibility="visible")

            if c[8].button("✕", key=f"rm_roster_{row['PLAYER_ID']}"):
                st.session_state.roster_ids.remove(int(row["PLAYER_ID"]))
                st.rerun()

        # Bar chart
        st.divider()
        fv_col  = "FANTASY_VALUE"
        fig_b = px.bar(
            recs, x="PLAYER_NAME", y=fv_col,
            color="RECOMMENDATION",
            color_discrete_map={"START": "#00b894", "SIT": "#636e72"},
            text=fv_col,
            title="Roster Fantasy Value Per Game" + (" (Projected)" if use_projections else ""),
            labels={"PLAYER_NAME": "", fv_col: "Fantasy Pts/G"},
        )
        fig_b.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig_b.update_layout(
            height=340, plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=45, b=10),
        )
        st.plotly_chart(fig_b, use_container_width=True)

        # Recent form
        with st.expander("📈 Load 2025-26 Recent Form (last 10 games)", expanded=False):
            for _, row in recs.iterrows():
                st.markdown(f"**{row['PLAYER_NAME']}**")
                try:
                    logs = get_player_game_logs(int(row["PLAYER_ID"]), PROJ_BASE_SEA)
                    if not logs.empty:
                        recent    = logs.head(10).iloc[::-1].reset_index(drop=True)
                        fv_series = active_eval.compute_game_log_value(recent)
                        recent_avg = fv_series.mean()
                        delta_str  = f"{recent_avg - row['FANTASY_VALUE']:+.1f} vs {'projection' if use_projections else 'season avg'}"
                        st.metric("Last 10 avg", f"{recent_avg:.1f}", delta_str)
                except Exception:
                    st.caption("Logs unavailable")
                st.divider()
    else:
        st.info("Add players from your fantasy roster above to get start/sit recommendations.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — PROJECTIONS DEEP DIVE
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    if proj_df is None:
        st.error("Projections could not be built. Check your connection and try again.")
        st.stop()

    st.subheader("2026-27 Season Projections")
    st.caption(
        "Our model: 70% 2025-26 + 30% 2024-25, adjusted for age curve.  "
        "Web sources fetched live from FantasyPros and HashtagBasketball."
    )

    # ── Fetch web projections ─────────────────────────────────────────────────
    scoring_key = tuple(sorted(scoring.items()))
    with st.spinner("Fetching live projections from FantasyPros & HashtagBasketball..."):
        fp_df,  fp_msg  = fetch_fantasypros(scoring_key)
        htb_df, htb_msg = fetch_hashtagbasketball(scoring_key)

    # Source status row
    src_col1, src_col2, src_col3 = st.columns(3)
    src_col1.success("✅ Our Model — built from NBA API")
    src_col2.success(f"✅ FantasyPros — {fp_msg}") if not fp_df.empty else src_col2.error(f"❌ FantasyPros — {fp_msg}")
    src_col3.success(f"✅ HashtagBasketball — {htb_msg}") if not htb_df.empty else src_col3.error(f"❌ HashtagBasketball — {htb_msg}")

    # Add PLAYER_NAME_NORM to proj_df for merging
    proj_df["PLAYER_NAME_NORM"] = proj_df["PLAYER_NAME"].apply(norm_name)
    web_dfs = {"FantasyPros": fp_df, "HashtagBasketball": htb_df}

    st.divider()

    # ── Summary metrics ───────────────────────────────────────────────────────
    _proj_filtered = proj_df[proj_df["GP"] >= 20]
    sm1, sm2, sm3, sm4 = st.columns(4)
    sm1.metric("Players Projected", len(_proj_filtered))
    sm2.metric("High Confidence",   len(_proj_filtered[_proj_filtered["CONFIDENCE"] == "HIGH"]))
    sm3.metric("Breakout Candidates",
               len(_proj_filtered[(_proj_filtered["AGE"] <= 25) &
                                   (_proj_filtered["FV_DELTA"] >= 1.5) &
                                   (_proj_filtered["PROJ_FV"] >= 15)]))
    sm4.metric("Decline Watch",
               len(_proj_filtered[(_proj_filtered["AGE"] >= 32) &
                                   (_proj_filtered["FV_DELTA"] <= -1.5) &
                                   (_proj_filtered["BASE_FV"] >= 20)]))

    st.divider()

    # ════════════════════════════════════════════════════════════════
    # SUB-TABS: Our Model  |  Source Comparison  |  Breakouts/Declines
    # ════════════════════════════════════════════════════════════════
    p_tab1, p_tab2, p_tab3 = st.tabs([
        "🤖 Our Model", "🔍 Source Comparison", "🚀 Breakouts & Declines"
    ])

    # ── Our Model ─────────────────────────────────────────────────────────────
    with p_tab1:
        fc1, fc2, fc3 = st.columns([3, 1, 1])
        with fc1:
            proj_q = st.text_input("🔍 Search", placeholder="Player name...", key="proj_search")
        with fc2:
            conf_filter = st.selectbox("Confidence", ["ALL", "HIGH", "MEDIUM", "LOW"], key="conf_filter")
        with fc3:
            proj_min_gp = st.number_input("Min Games (last season)", value=20, min_value=1, max_value=82, key="proj_min_gp")

        proj_view = _proj_filtered.copy()
        if proj_q:
            proj_view = proj_view[proj_view["PLAYER_NAME"].str.lower().str.contains(proj_q.lower(), na=False)]
        if conf_filter != "ALL":
            proj_view = proj_view[proj_view["CONFIDENCE"] == conf_filter]
        proj_view = proj_view.sort_values("PROJ_RANK")

        _proj_cols = ["PROJ_RANK", "PLAYER_NAME", "TEAM_ABBREVIATION", "AGE", "GP",
                      "PROJ_PTS", "PROJ_REB", "PROJ_AST", "PROJ_STL", "PROJ_BLK",
                      "PROJ_FG3M", "PROJ_TOV", "BASE_FV", "PROJ_FV", "FV_DELTA", "CONFIDENCE"]
        proj_tbl = proj_view[[c for c in _proj_cols if c in proj_view.columns]].head(200).copy()
        proj_tbl = proj_tbl.rename(columns={
            "PROJ_RANK": "#", "PLAYER_NAME": "Player", "TEAM_ABBREVIATION": "Team",
            "PROJ_PTS": "Proj PTS", "PROJ_REB": "Proj REB", "PROJ_AST": "Proj AST",
            "PROJ_STL": "Proj STL", "PROJ_BLK": "Proj BLK", "PROJ_FG3M": "Proj 3PM",
            "PROJ_TOV": "Proj TOV", "BASE_FV": "25-26 FV", "PROJ_FV": "Proj FV",
            "FV_DELTA": "Δ FV", "CONFIDENCE": "Conf.",
        })
        for col in ["Proj PTS","Proj REB","Proj AST","Proj STL","Proj BLK","Proj 3PM",
                    "Proj TOV","25-26 FV","Proj FV","Δ FV"]:
            if col in proj_tbl.columns:
                proj_tbl[col] = proj_tbl[col].round(1)
        st.dataframe(proj_tbl, use_container_width=True, height=480, hide_index=True)

        # Top 20 chart
        top20 = _proj_filtered.nsmallest(20, "PROJ_RANK")
        fig_top = px.bar(
            top20, x="PROJ_FV", y="PLAYER_NAME", orientation="h",
            color="PROJ_FV", color_continuous_scale="Teal", text="PROJ_FV",
            title="Top 20 — Our Model (2026-27 Projected FV/G)",
            labels={"PROJ_FV": "Projected FV/G", "PLAYER_NAME": ""},
        )
        fig_top.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig_top.update_layout(
            yaxis={"autorange": "reversed"}, height=560,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=45, b=10), coloraxis_showscale=False,
        )
        st.plotly_chart(fig_top, use_container_width=True)

    # ── Source Comparison ─────────────────────────────────────────────────────
    with p_tab2:
        st.caption(
            "Each source's projected FV/G computed with **your current scoring settings**.  "
            "Consensus = average across all available sources."
        )

        cmp_q = st.text_input("🔍 Filter player", key="cmp_search")
        cmp_min_gp = st.number_input("Min GP (last season)", value=20, min_value=1, max_value=82, key="cmp_min_gp")

        cmp_df = build_comparison(
            proj_df[proj_df["GP"] >= cmp_min_gp].copy(),
            web_dfs,
        )
        if cmp_q:
            cmp_df = cmp_df[cmp_df["PLAYER_NAME"].str.lower().str.contains(cmp_q.lower(), na=False)]

        # Display table
        disp_cols = ["Consensus Rank", "PLAYER_NAME", "TEAM_ABBREVIATION", "AGE", "CONFIDENCE",
                     "Our Model", "Our Model Rank"]
        for src in ["FantasyPros", "HashtagBasketball"]:
            if src in cmp_df.columns:
                disp_cols += [src, f"{src} Rank"]
        disp_cols.append("Consensus FV")

        cmp_tbl = cmp_df[[c for c in disp_cols if c in cmp_df.columns]].head(200).copy()
        cmp_tbl = cmp_tbl.rename(columns={
            "PLAYER_NAME": "Player", "TEAM_ABBREVIATION": "Team",
            "Consensus Rank": "#", "CONFIDENCE": "Conf.",
        })
        for col in ["Our Model", "FantasyPros", "HashtagBasketball", "Consensus FV"]:
            if col in cmp_tbl.columns:
                cmp_tbl[col] = cmp_tbl[col].round(1)

        st.dataframe(cmp_tbl, use_container_width=True, height=500, hide_index=True)

        # Rank divergence — show players where sources disagree most
        st.subheader("Biggest Ranking Disagreements")
        st.caption("Players where our model rank differs most from the consensus.")

        rank_cols = [c for c in cmp_df.columns if "Rank" in c and c != "Consensus Rank"]
        if len(rank_cols) >= 2:
            cmp_df["Max Rank Diff"] = (
                cmp_df[rank_cols].max(axis=1) - cmp_df[rank_cols].min(axis=1)
            )
            disagree = cmp_df.nlargest(10, "Max Rank Diff")[
                ["PLAYER_NAME", "TEAM_ABBREVIATION", "Consensus Rank"] + rank_cols + ["Max Rank Diff"]
            ].copy()
            disagree = disagree.rename(columns={
                "PLAYER_NAME": "Player", "TEAM_ABBREVIATION": "Team",
                "Consensus Rank": "Consensus #",
            })
            st.dataframe(disagree, use_container_width=True, hide_index=True)

        # Scatter: Our Model vs FantasyPros
        if "FantasyPros" in cmp_df.columns:
            valid = cmp_df[["PLAYER_NAME", "Our Model", "FantasyPros"]].dropna()
            if not valid.empty:
                try:
                    import statsmodels  # noqa: F401
                    trendline = "ols"
                except ImportError:
                    trendline = None

                fig_sc = px.scatter(
                    valid, x="FantasyPros", y="Our Model", hover_name="PLAYER_NAME",
                    title="Our Model vs FantasyPros — Projected FV/G",
                    labels={"FantasyPros": "FantasyPros FV/G", "Our Model": "Our Model FV/G"},
                    trendline=trendline,
                )
                fig_sc.update_layout(
                    height=400, plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig_sc, use_container_width=True)

    # ── Breakouts & Declines ──────────────────────────────────────────────────
    with p_tab3:
        col_break, col_dec = st.columns(2)

        with col_break:
            st.subheader("🚀 Breakout Candidates")
            st.caption("Age ≤ 25  ·  Proj FV ≥ 15  ·  Δ FV ≥ +1.5")
            breakouts_sorted = (
                _proj_filtered[
                    (_proj_filtered["AGE"] <= 25) &
                    (_proj_filtered["FV_DELTA"] >= 1.5) &
                    (_proj_filtered["PROJ_FV"] >= 15)
                ]
                .sort_values("FV_DELTA", ascending=False)
                .head(10)
            )
            if breakouts_sorted.empty:
                st.info("No breakout candidates found.")
            else:
                for _, r in breakouts_sorted.iterrows():
                    conf = r.get("CONFIDENCE", "")
                    cls  = {"HIGH": "conf-high", "MEDIUM": "conf-medium", "LOW": "conf-low"}.get(conf, "")
                    st.markdown(
                        f"**{r['PLAYER_NAME']}** ({r['TEAM_ABBREVIATION']}) · Age {int(r['AGE'])}  "
                        f"&nbsp; Proj: **{r['PROJ_FV']:.1f}** FP/g  "
                        f"<span style='color:#00b894'>▲ {r['FV_DELTA']:.1f}</span>  "
                        f"<span class='{cls}'>{conf}</span>",
                        unsafe_allow_html=True,
                    )

        with col_dec:
            st.subheader("⚠️ Decline Watch")
            st.caption("Age ≥ 32  ·  Last season FV ≥ 20  ·  Δ FV ≤ −1.5")
            declines_sorted = (
                _proj_filtered[
                    (_proj_filtered["AGE"] >= 32) &
                    (_proj_filtered["FV_DELTA"] <= -1.5) &
                    (_proj_filtered["BASE_FV"] >= 20)
                ]
                .sort_values("FV_DELTA")
                .head(10)
            )
            if declines_sorted.empty:
                st.info("No decline watch players found.")
            else:
                for _, r in declines_sorted.iterrows():
                    conf = r.get("CONFIDENCE", "")
                    cls  = {"HIGH": "conf-high", "MEDIUM": "conf-medium", "LOW": "conf-low"}.get(conf, "")
                    st.markdown(
                        f"**{r['PLAYER_NAME']}** ({r['TEAM_ABBREVIATION']}) · Age {int(r['AGE'])}  "
                        f"&nbsp; Proj: **{r['PROJ_FV']:.1f}** FP/g  "
                        f"<span style='color:#d63031'>▼ {abs(r['FV_DELTA']):.1f}</span>  "
                        f"<span class='{cls}'>{conf}</span>",
                        unsafe_allow_html=True,
                    )
