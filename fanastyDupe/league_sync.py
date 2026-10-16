import re
import requests
import streamlit as st

SLEEPER_BASE = "https://api.sleeper.app/v1"


def _sanitize(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "", value)


def _norm(name: str) -> str:
    name = name.lower()
    name = re.sub(r"['\.\-]", "", name)
    name = re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", name)
    return name.strip()


def norm_player_name(name: str) -> str:
    """Public normalizer — use to key into sleeper_player_positions()."""
    return _norm(name)


def pos_group(raw_pos: str) -> str:
    """Map a raw position string (PG, SF, C …) to a display group."""
    p = (raw_pos or "").upper()
    if p in ("PG", "SG", "G"):
        return "Guards"
    if p in ("SF", "PF", "F", "G-F", "F-G", "SG-SF", "PG-SG"):
        return "Forwards"
    if p in ("C", "F-C", "C-F", "PF-C"):
        return "Centers"
    return "Other"


# ── Sleeper ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def _sleeper_raw_players() -> dict:
    """Single cached fetch of all active NBA players from Sleeper."""
    resp = requests.get(f"{SLEEPER_BASE}/players/nba", timeout=20)
    resp.raise_for_status()
    return {pid: info for pid, info in resp.json().items() if info.get("active")}


@st.cache_data(ttl=86400, show_spinner=False)
def sleeper_player_map() -> dict:
    """Fetch all active NBA players from Sleeper → {player_id: full_name}."""
    out = {}
    for pid, info in _sleeper_raw_players().items():
        full = info.get("full_name") or (
            f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
        )
        if full:
            out[pid] = full
    return out


@st.cache_data(ttl=86400, show_spinner=False)
def sleeper_player_positions() -> dict:
    """Returns {norm_player_name: raw_position} for all active NBA players."""
    out = {}
    for pid, info in _sleeper_raw_players().items():
        full = info.get("full_name") or (
            f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
        )
        pos = info.get("position", "")
        if full:
            out[_norm(full)] = pos
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def get_sleeper_user(username: str) -> dict:
    username = _sanitize(username)
    resp = requests.get(f"{SLEEPER_BASE}/user/{username}", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise ValueError(f"Sleeper user '{username}' not found.")
    return data


@st.cache_data(ttl=3600, show_spinner=False)
def get_sleeper_leagues(user_id: str, season: str) -> list:
    user_id = _sanitize(user_id)
    resp = requests.get(f"{SLEEPER_BASE}/user/{user_id}/leagues/nba/{season}", timeout=10)
    resp.raise_for_status()
    return resp.json() or []


def get_league(league_id: str) -> dict | None:
    league_id = _sanitize(league_id)
    resp = requests.get(f"{SLEEPER_BASE}/league/{league_id}", timeout=10)
    if resp.status_code == 200:
        return resp.json()
    st.error(f"Failed to fetch league data. Status code: {resp.status_code}")
    return None


def get_rosters(league_id: str) -> list | None:
    league_id = _sanitize(league_id)
    resp = requests.get(f"{SLEEPER_BASE}/league/{league_id}/rosters", timeout=10)
    if resp.status_code == 200:
        return resp.json()
    st.error(f"Failed to fetch rosters. Status code: {resp.status_code}")
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def get_sleeper_roster(league_id: str, user_id: str) -> list:
    """Returns list of player names on the user's Sleeper roster."""
    pmap = sleeper_player_map()
    rosters = get_rosters(league_id)
    if not rosters:
        return []
    for roster in rosters:
        if roster.get("owner_id") == user_id:
            return [pmap[pid] for pid in (roster.get("players") or []) if pid in pmap]
    raise ValueError("Your roster was not found in this league.")


def get_users(user_ids: list) -> dict | None:
    sanitized = [_sanitize(uid) for uid in user_ids]
    url = f"{SLEEPER_BASE}/users/{','.join(sanitized)}"
    resp = requests.get(url, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    st.error(f"Failed to fetch user data. Status code: {resp.status_code}")
    return None


# ── Sleeper full league ────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_sleeper_league_teams(league_id: str) -> list:
    """
    Returns every team in a Sleeper league with roster player names and
    W/L/points standings, sorted by rank.
    Each dict: {name, owner, owner_id, player_names, wins, losses, points, rank}
    """
    pmap = sleeper_player_map()
    lid = _sanitize(league_id)

    rosters_resp = requests.get(f"{SLEEPER_BASE}/league/{lid}/rosters", timeout=10)
    rosters_resp.raise_for_status()

    users_resp = requests.get(f"{SLEEPER_BASE}/league/{lid}/users", timeout=10)
    users_resp.raise_for_status()
    users_by_id = {u["user_id"]: u for u in users_resp.json()}

    teams = []
    for roster in rosters_resp.json():
        owner_id = roster.get("owner_id", "")
        user     = users_by_id.get(owner_id, {})
        meta     = user.get("metadata", {})
        settings = roster.get("settings", {})

        fpts = settings.get("fpts", 0) + settings.get("fpts_decimal", 0) / 100
        teams.append({
            "name":         meta.get("team_name") or user.get("display_name", f"Team {roster.get('roster_id','?')}"),
            "owner":        user.get("display_name", "Unknown"),
            "owner_id":     owner_id,
            "player_names": [pmap[pid] for pid in (roster.get("players") or []) if pid in pmap],
            "wins":         settings.get("wins", 0),
            "losses":       settings.get("losses", 0),
            "points":       round(fpts, 2),
        })

    teams.sort(key=lambda t: (-t["wins"], -t["points"]))
    for rank, team in enumerate(teams, 1):
        team["rank"] = rank
    return teams


# ── ESPN ───────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_espn_league_teams(league_id: int, year: int,
                          espn_s2: str = "", swid: str = "") -> list:
    """
    Returns every team in an ESPN league with roster player names and
    W/L/points standings, sorted by rank.
    Each dict: {name, owner, owner_id, player_names, wins, losses, points, rank}
    """
    from espn_api.basketball import League
    kwargs = {"league_id": league_id, "year": year}
    if espn_s2 and swid:
        kwargs["espn_s2"] = espn_s2
        kwargs["swid"] = swid
    lg = League(**kwargs)

    teams = []
    for team in lg.teams:
        teams.append({
            "name":         team.team_name,
            "owner":        team.owner,
            "owner_id":     None,
            "player_names": [p.name for p in team.roster],
            "wins":         team.wins,
            "losses":       team.losses,
            "points":       round(getattr(team, "points_for", 0), 2),
            "standing":     getattr(team, "standing", 0),
        })

    teams.sort(key=lambda t: (t.get("standing") or 999, -t["wins"], -t["points"]))
    for rank, team in enumerate(teams, 1):
        team["rank"] = rank
    return teams


# ── Name matching ──────────────────────────────────────────────────────────────

def match_names(raw_names: list, name_to_id: dict) -> tuple:
    """
    Match player names from a platform against our name_to_id dict.
    Returns (matched_ids, unmatched_names).
    Tries exact normalized match, then first+last partial match.
    """
    norm_index = {_norm(label): pid for label, pid in name_to_id.items()}
    matched, unmatched = [], []
    for name in raw_names:
        key = _norm(name)
        if key in norm_index:
            matched.append(norm_index[key])
            continue
        parts = key.split()
        if len(parts) >= 2:
            short = f"{parts[0]} {parts[-1]}"
            hit = next((pid for k, pid in norm_index.items() if short in k), None)
            if hit:
                matched.append(hit)
                continue
        unmatched.append(name)
    return matched, unmatched
