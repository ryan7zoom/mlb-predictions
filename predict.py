"""
MLB Daily Probability System
- Pitcher strikeout floor probabilities (e.g. P(4+ K), P(5+ K))
- Team spread-cover probabilities (based on run differential model)

Data source: MLB Stats API (statsapi.mlb.com) - free, public, unofficial.
No API key needed. For individual/non-commercial use.

Output: docs/index.html (a phone-friendly page), for GitHub Pages.
"""

import json
import math
import statistics
from datetime import datetime, timedelta
import urllib.request
import urllib.parse
import os

BASE = "https://statsapi.mlb.com/api/v1"
TODAY = datetime.utcnow().strftime("%Y-%m-%d")

# ---------- park factors ----------
# Source: RotoWire "The Z Files: 2026 Pitching and Hitting Park Factors" (Todd Zola,
# May 17 2026), https://www.rotowire.com/baseball/article/the-z-files-2026-fantasy-baseball-pitching-hitting-park-factors-114824
# These are PITCHING park factors (how the park affects run/hit/HR/SO/BB outcomes),
# 3-year rolling averages except where noted. 100 = neutral, indexed.
# Keyed by home team_id (MLB Stats API team IDs).
PARK_FACTORS = {
    108: {"team": "Angels",       "R": 102, "H": 98,  "HR": 113, "SO": 105, "BB": 103},
    117: {"team": "Astros",       "R": 100, "H": 100, "HR": 105, "SO": 102, "BB": 100},
    133: {"team": "Athletics",    "R": 117, "H": 107, "HR": 112, "SO": 97,  "BB": 107},
    141: {"team": "Blue Jays",    "R": 100, "H": 99,  "HR": 104, "SO": 97,  "BB": 100},
    144: {"team": "Braves",       "R": 102, "H": 102, "HR": 105, "SO": 106, "BB": 99},
    158: {"team": "Brewers",      "R": 94,  "H": 94,  "HR": 106, "SO": 109, "BB": 106},
    138: {"team": "Cardinals",    "R": 100, "H": 103, "HR": 87,  "SO": 91,  "BB": 96},
    112: {"team": "Cubs",         "R": 94,  "H": 96,  "HR": 99,  "SO": 103, "BB": 100},
    109: {"team": "Diamondbacks", "R": 106, "H": 105, "HR": 88,  "SO": 94,  "BB": 99},
    119: {"team": "Dodgers",      "R": 102, "H": 97,  "HR": 127, "SO": 99,  "BB": 101},
    137: {"team": "Giants",       "R": 94,  "H": 101, "HR": 81,  "SO": 97,  "BB": 90},
    114: {"team": "Guardians",    "R": 94,  "H": 97,  "HR": 85,  "SO": 102, "BB": 100},
    136: {"team": "Mariners",     "R": 83,  "H": 89,  "HR": 93,  "SO": 116, "BB": 96},
    146: {"team": "Marlins",      "R": 102, "H": 103, "HR": 90,  "SO": 97,  "BB": 97},
    121: {"team": "Mets",         "R": 96,  "H": 94,  "HR": 104, "SO": 102, "BB": 110},
    120: {"team": "Nationals",    "R": 102, "H": 104, "HR": 94,  "SO": 90,  "BB": 94},
    110: {"team": "Orioles",      "R": 98,  "H": 102, "HR": 97,  "SO": 97,  "BB": 91},
    135: {"team": "Padres",       "R": 94,  "H": 96,  "HR": 102, "SO": 102, "BB": 103},
    143: {"team": "Phillies",     "R": 102, "H": 101, "HR": 115, "SO": 104, "BB": 96},
    134: {"team": "Pirates",      "R": 98,  "H": 101, "HR": 76,  "SO": 96,  "BB": 100},
    140: {"team": "Rangers",      "R": 94,  "H": 97,  "HR": 104, "SO": 101, "BB": 100},
    139: {"team": "Rays",         "R": 92,  "H": 96,  "HR": 98,  "SO": 108, "BB": 95},
    111: {"team": "Red Sox",      "R": 110, "H": 107, "HR": 89,  "SO": 96,  "BB": 97},
    113: {"team": "Reds",         "R": 106, "H": 100, "HR": 123, "SO": 102, "BB": 103},
    115: {"team": "Rockies",      "R": 125, "H": 117, "HR": 105, "SO": 90,  "BB": 101},
    118: {"team": "Royals",       "R": 102, "H": 104, "HR": 85,  "SO": 89,  "BB": 100},
    116: {"team": "Tigers",       "R": 102, "H": 100, "HR": 99,  "SO": 98,  "BB": 100},
    142: {"team": "Twins",        "R": 106, "H": 102, "HR": 102, "SO": 103, "BB": 100},
    145: {"team": "White Sox",    "R": 98,  "H": 98,  "HR": 96,  "SO": 100, "BB": 103},
    147: {"team": "Yankees",      "R": 100, "H": 94,  "HR": 119, "SO": 101, "BB": 111},
}
# Source note shown in UI. If MLB adds/moves a franchise this table will be stale;
# it is intentionally static (not scraped) because Baseball Savant does not expose
# a documented free JSON endpoint for this data - only a web leaderboard.
PARK_FACTOR_SOURCE = "RotoWire 2026 Park Factors (3yr rolling, pitching), published May 17, 2026"

# ---------- low-level fetch ----------

def get(path, params=None):
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


# ---------- schedule / probable pitchers ----------

def get_todays_games(date=TODAY):
    data = get("/schedule", {
        "sportId": 1,
        "date": date,
        "hydrate": "probablePitcher,team,linescore"
    })
    games = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            away = g["teams"]["away"]
            home = g["teams"]["home"]
            games.append({
                "gamePk": g["gamePk"],
                "away_team": away["team"]["name"],
                "away_team_short": away["team"].get("shortName") or away["team"]["name"],
                "away_team_abbr": away["team"].get("abbreviation") or away["team"]["name"][:3].upper(),
                "away_team_id": away["team"]["id"],
                "home_team": home["team"]["name"],
                "home_team_short": home["team"].get("shortName") or home["team"]["name"],
                "home_team_abbr": home["team"].get("abbreviation") or home["team"]["name"][:3].upper(),
                "home_team_id": home["team"]["id"],
                "away_pitcher": away.get("probablePitcher", {}).get("fullName"),
                "away_pitcher_id": away.get("probablePitcher", {}).get("id"),
                "home_pitcher": home.get("probablePitcher", {}).get("fullName"),
                "home_pitcher_id": home.get("probablePitcher", {}).get("id"),
            })
    return games


# ---------- pitcher fatigue ----------

def get_pitcher_days_rest(pitcher_id, before_date_str=TODAY, season=None):
    """
    Days between a pitcher's last start and today. MLB starters typically
    work on 4-5 days rest; meaningfully less (0-3) is a real fatigue signal
    worth surfacing directly rather than only folding into ERA, since a
    tired starter can look fine on paper (season ERA) while being at real
    risk of a short/rough outing on short rest.
    """
    if season is None:
        season = datetime.utcnow().year
    data = get(f"/people/{pitcher_id}/stats", {
        "stats": "gameLog",
        "group": "pitching",
        "season": season
    })
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError):
        return None
    starts = [s for s in splits if s["stat"].get("gamesStarted") in ("1", 1)]
    past_starts = [s for s in starts if s.get("date", "9999-99-99") < before_date_str]
    if not past_starts:
        return None
    last_start_date = max(s["date"] for s in past_starts)
    try:
        last_dt = datetime.strptime(last_start_date, "%Y-%m-%d")
        today_dt = datetime.strptime(before_date_str, "%Y-%m-%d")
        return (today_dt - last_dt).days
    except ValueError:
        return None


def get_pitcher_innings_trend(pitcher_id, season=None, last_n=5):
    """
    Innings pitched in each of the pitcher's last N starts, oldest to
    newest. A declining trend (getting pulled earlier each outing) is a
    fatigue signal independent of ERA - a pitcher can maintain a good ERA
    over shorter and shorter outings right up until it breaks down.
    """
    if season is None:
        season = datetime.utcnow().year
    data = get(f"/people/{pitcher_id}/stats", {
        "stats": "gameLog",
        "group": "pitching",
        "season": season
    })
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError):
        return []
    starts = [s for s in splits if s["stat"].get("gamesStarted") in ("1", 1)]
    recent = starts[-last_n:]
    ip_list = []
    for s in recent:
        try:
            ip_list.append(float(s["stat"].get("inningsPitched", 0) or 0))
        except (TypeError, ValueError):
            continue
    return ip_list


def assess_pitcher_fatigue(pitcher_id, before_date_str=TODAY, season=None):
    """
    Combines days-rest and innings-trend into one plain-language assessment.
    Returns None if not enough data exists yet (early season, call-up) -
    silence is preferable to a fabricated fatigue read on a small sample.
    """
    days_rest = get_pitcher_days_rest(pitcher_id, before_date_str, season)
    ip_trend = get_pitcher_innings_trend(pitcher_id, season)

    if days_rest is None and len(ip_trend) < 3:
        return None

    notes = []
    is_short_rest = days_rest is not None and days_rest <= 3
    is_declining_innings = False
    if len(ip_trend) >= 3:
        first_half_avg = sum(ip_trend[:len(ip_trend)//2]) / max(1, len(ip_trend)//2)
        second_half_avg = sum(ip_trend[len(ip_trend)//2:]) / max(1, len(ip_trend) - len(ip_trend)//2)
        is_declining_innings = second_half_avg < first_half_avg - 0.75  # meaningful drop, not noise

    if is_short_rest:
        notes.append(f"pitching on {days_rest} days rest (short for a starter)")
    if is_declining_innings:
        notes.append("recent outings have been getting shorter")

    return {
        "days_rest": days_rest,
        "innings_trend": ip_trend,
        "is_fatigue_flag": is_short_rest or is_declining_innings,
        "note": "; ".join(notes) if notes else None,
    }


# ---------- today's lineup handedness (for pitcher-vs-lineup matchup) ----------
#
# MLB Stats API's boxscore endpoint exposes battingOrder for each player
# once a lineup is set - but lineups are often not posted until 1-3 hours
# before first pitch, sometimes later. Earlier in the day this will come
# back empty, which we surface honestly ("lineup not posted yet") rather
# than guessing or silently falling back to something else.

def get_confirmed_lineup_handedness(game_pk, team_id):
    """
    Returns {"lefties": n, "righties": n, "switch": n, "total": n} for the
    confirmed starting lineup of one team in one game, or None if the
    lineup isn't posted yet.
    """
    try:
        data = get(f"/game/{game_pk}/boxscore")
    except Exception:
        return None

    teams = data.get("teams", {})
    side = None
    for key in ("home", "away"):
        t = teams.get(key, {})
        if t.get("team", {}).get("id") == team_id:
            side = t
            break
    if not side:
        return None

    batting_order_ids = side.get("battingOrder", [])
    if not batting_order_ids:
        return None  # lineup not posted yet

    players = side.get("players", {})
    lefties = righties = switch = 0
    for pid in batting_order_ids:
        key = f"ID{pid}"
        player = players.get(key, {})
        bat_side = player.get("person", {}).get("batSide", {}).get("code")
        if bat_side == "L":
            lefties += 1
        elif bat_side == "R":
            righties += 1
        elif bat_side == "S":
            switch += 1

    total = lefties + righties + switch
    if total == 0:
        return None
    return {"lefties": lefties, "righties": righties, "switch": switch, "total": total}


def assess_pitcher_vs_lineup(pitcher_platoon, lineup_handedness):
    """
    Combines a pitcher's platoon K-rate split with today's confirmed
    lineup's handedness mix into a plain-language read - not a new
    probability number, since the underlying samples (platoon K-rate,
    9-batter lineup) are both real but the combination is directional, not
    precise. Returns None if either input is missing (lineup not posted,
    or pitcher's platoon split had too small a sample to trust).
    """
    if not lineup_handedness:
        return {"available": False, "reason": "Lineup not posted yet - matchup read unavailable."}
    if not pitcher_platoon or pitcher_platoon.get("platoon_gap") is None:
        return {"available": False, "reason": "Pitcher's platoon K-rate split has too small a sample this season to trust."}

    k_l = pitcher_platoon["k_rate_vs_lhb"]
    k_r = pitcher_platoon["k_rate_vs_rhb"]
    gap = pitcher_platoon["platoon_gap"]
    lefty_heavy = lineup_handedness["lefties"] > lineup_handedness["righties"]
    switch_note = f", {lineup_handedness['switch']} switch-hitters" if lineup_handedness["switch"] else ""

    lineup_desc = (f"today's lineup leans left-handed "
                   f"({lineup_handedness['lefties']} of {lineup_handedness['total']}{switch_note})"
                   if lefty_heavy else
                   f"today's lineup leans right-handed "
                   f"({lineup_handedness['righties']} of {lineup_handedness['total']}{switch_note})")

    if gap < 0.04:
        return {"available": True, "reason": None,
                "summary": f"{lineup_desc} - this pitcher doesn't show a strong platoon split "
                           f"({k_l*100:.0f}% K vs LHB, {k_r*100:.0f}% K vs RHB), so the handedness mix "
                           f"likely matters less than usual tonight."}

    favors_pitcher = (lefty_heavy and k_l > k_r) or (not lefty_heavy and k_r > k_l)
    edge_text = "mild edge toward the pitcher" if favors_pitcher else "mild edge toward the batters"
    return {"available": True, "reason": None,
            "summary": f"{lineup_desc} - this pitcher has a real platoon split "
                       f"({k_l*100:.0f}% K vs LHB, {k_r*100:.0f}% K vs RHB) - {edge_text} tonight."}


# ---------- plain-language park factor ----------

def describe_park_factor(park_factors):
    """
    Converts the raw indexed park numbers into a plain sentence instead of
    bare numbers - "116 SO factor" means nothing at a glance, "this park
    favors pitchers" does.
    """
    if not park_factors:
        return None
    r, hr, so = park_factors["R"], park_factors["HR"], park_factors["SO"]
    park_name = park_factors["team"]

    leanings = []
    if r >= 108 or hr >= 112:
        leanings.append("favors hitters")
    elif r <= 92 or hr <= 88:
        leanings.append("favors pitchers")
    if so >= 108:
        leanings.append("elevated strikeout rates")
    elif so <= 92:
        leanings.append("suppressed strikeout rates")

    if not leanings:
        return f"{park_name}'s home park plays close to a neutral run/HR/strikeout environment."
    return f"{park_name}'s home park historically {', '.join(leanings)}."



def get_pitcher_recent_strikeouts(pitcher_id, season=None, last_n=12):
    """Return list of strikeout counts from the pitcher's most recent starts."""
    if season is None:
        season = datetime.utcnow().year
    data = get(f"/people/{pitcher_id}/stats", {
        "stats": "gameLog",
        "group": "pitching",
        "season": season
    })
    k_list = []
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError):
        return []
    # only count actual starts (games started)
    starts = [s for s in splits if s["stat"].get("gamesStarted", 0) == "1"
              or s["stat"].get("gamesStarted", 0) == 1]
    for s in starts[-last_n:]:
        k_list.append(int(s["stat"].get("strikeOuts", 0)))
    return k_list


def strikeout_floor_probs(k_list, thresholds=(3, 4, 5, 6)):
    """Empirical probability of hitting each K threshold, based on recent starts."""
    n = len(k_list)
    if n == 0:
        return {}
    probs = {}
    for t in thresholds:
        hits = sum(1 for k in k_list if k >= t)
        probs[t] = round(hits / n, 3)
    return probs


# ---------- team strikeout tendency (for pitcher K adjustment) ----------

# League-average team strikeouts per game (rough modern MLB baseline; used
# only as a fallback if we can't compute a live league average from today's data)
LEAGUE_AVG_K_PER_GAME_FALLBACK = 8.6

def get_team_k_rate(team_id, season=None):
    """Team's strikeouts-as-batter per game (how often this lineup whiffs)."""
    if season is None:
        season = datetime.utcnow().year
    data = get(f"/teams/{team_id}/stats", {
        "stats": "season",
        "group": "hitting",
        "season": season
    })
    try:
        stat = data["stats"][0]["splits"][0]["stat"]
        k = int(stat.get("strikeOuts", 0))
        games = int(stat.get("gamesPlayed", 1)) or 1
        return k / games
    except (KeyError, IndexError):
        return None


def adjust_k_floor_for_opponent(base_probs, opponent_k_per_game, league_avg=LEAGUE_AVG_K_PER_GAME_FALLBACK):
    """
    Nudge strikeout-floor probabilities based on how strikeout-prone the
    opposing lineup is relative to league average.
    This is a simple multiplicative adjustment on the underlying "rate", not
    a rigorous model - treat it as a directional adjustment, not gospel.
    """
    if not base_probs or not opponent_k_per_game or not league_avg:
        return base_probs
    factor = opponent_k_per_game / league_avg
    # dampen the adjustment so a single stat doesn't overcorrect
    factor = 1 + (factor - 1) * 0.5
    adjusted = {}
    for threshold, prob in base_probs.items():
        new_prob = prob * factor
        adjusted[threshold] = round(max(0.0, min(1.0, new_prob)), 3)
    return adjusted


# ---------- pitcher platoon (handedness) splits ----------
# Verified sitCode values: 'vl' = vs left-handed batters, 'vr' = vs right-handed
# batters. Confirmed via production usage in community MLB-StatsAPI tooling
# (github.com/efitz11/natsgifbot), which documents the full sitCodes list
# including vl/vr, and the toddrob99/MLB-StatsAPI wiki, which documents the
# stats=statSplits + sitCodes pattern generally.

def get_pitcher_hand(pitcher_id):
    """Return 'L' or 'R' for the pitcher's throwing hand, or None if unknown."""
    data = get(f"/people/{pitcher_id}")
    try:
        return data["people"][0]["pitchHand"]["code"]
    except (KeyError, IndexError, TypeError):
        return None


def get_pitcher_k_rate_vs_hand(pitcher_id, sitcode, season=None):
    """
    Pitcher's strikeouts per batter faced against a given batter handedness.
    sitcode: 'vl' (vs left-handed batters) or 'vr' (vs right-handed batters).
    Returns None if the split has too little data or the call fails - this is
    intentionally conservative since small-sample splits are unreliable.
    """
    if season is None:
        season = datetime.utcnow().year
    try:
        data = get(f"/people/{pitcher_id}/stats", {
            "stats": "statSplits",
            "group": "pitching",
            "sitCodes": sitcode,
            "season": season
        })
        stat = data["stats"][0]["splits"][0]["stat"]
        k = int(stat.get("strikeOuts", 0))
        bf = int(stat.get("battersFaced", 0))
        if bf < 20:  # too small a sample to trust
            return None
        return k / bf
    except (KeyError, IndexError, TypeError):
        return None


def get_pitcher_platoon_splits(pitcher_id, season=None):
    """
    Returns the pitcher's K-rate-per-batter-faced against lefties and righties,
    plus the pitcher's own throwing hand. Used to flag matchup-sensitive
    pitchers (large platoon gap) rather than silently folding this into a
    single opaque number - the actual opposing lineup's handedness mix on a
    given day isn't reliably knowable in advance, so we surface the pitcher's
    own split as context instead of pretending to know the lineup.
    """
    hand = get_pitcher_hand(pitcher_id)
    k_vs_l = get_pitcher_k_rate_vs_hand(pitcher_id, "vl", season)
    k_vs_r = get_pitcher_k_rate_vs_hand(pitcher_id, "vr", season)
    gap = None
    if k_vs_l is not None and k_vs_r is not None:
        gap = round(abs(k_vs_l - k_vs_r), 3)
    return {
        "throws": hand,
        "k_rate_vs_lhb": round(k_vs_l, 3) if k_vs_l is not None else None,
        "k_rate_vs_rhb": round(k_vs_r, 3) if k_vs_r is not None else None,
        "platoon_gap": gap
    }


# ---------- team run scoring / allowing (for spread model) ----------

def get_team_run_stats(team_id, season=None):
    if season is None:
        season = datetime.utcnow().year
    data = get(f"/teams/{team_id}/stats", {
        "stats": "season",
        "group": "hitting",
        "season": season
    })
    runs_scored = None
    games = None
    try:
        stat = data["stats"][0]["splits"][0]["stat"]
        runs_scored = int(stat.get("runs", 0))
        games = int(stat.get("gamesPlayed", 1))
    except (KeyError, IndexError):
        pass

    data2 = get(f"/teams/{team_id}/stats", {
        "stats": "season",
        "group": "pitching",
        "season": season
    })
    runs_allowed = None
    try:
        stat2 = data2["stats"][0]["splits"][0]["stat"]
        runs_allowed = int(stat2.get("runs", 0))
    except (KeyError, IndexError):
        pass

    if runs_scored is None or runs_allowed is None or not games:
        return None
    return {
        "runs_scored_pg": runs_scored / games,
        "runs_allowed_pg": runs_allowed / games,
    }


def get_pitcher_recent_form(pitcher_id, season=None, last_n=5):
    """
    A starting pitcher's runs-allowed-per-start over their last N starts,
    plus innings pitched, so the spread model can react to a pitcher who's
    been struggling or dealing recently - not just the team's full-season
    ERA, which a single bad/great starter skews far less than the individual
    game does. Returns None if too few starts are available yet.
    """
    if season is None:
        season = datetime.utcnow().year
    data = get(f"/people/{pitcher_id}/stats", {
        "stats": "gameLog",
        "group": "pitching",
        "season": season
    })
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError):
        return None
    starts = [s for s in splits if s["stat"].get("gamesStarted") in ("1", 1)]
    recent = starts[-last_n:]
    if not recent:
        return None
    total_er = sum(int(s["stat"].get("earnedRuns", 0)) for s in recent)
    total_ip = sum(float(s["stat"].get("inningsPitched", 0) or 0) for s in recent)
    if total_ip == 0:
        return None
    recent_era = round((total_er / total_ip) * 9, 2)
    return {
        "starts_sampled": len(recent),
        "recent_era": recent_era,
        "innings_pitched_total": round(total_ip, 1),
    }


def spread_cover_prob(team_a_stats, team_b_stats, spread, park_run_factor=100, std_dev=4.2,
                       pitcher_a_form=None, pitcher_b_form=None, pitcher_a_fatigue=None,
                       pitcher_b_fatigue=None, league_avg_era=4.20):
    """
    Estimate P(team_a covers `spread`) using a normal approximation
    of MLB run-differential margin, adjusted for the park's run environment
    and, when available, each side's starting pitcher's recent form and
    fatigue status.

    spread is from team_a's perspective, e.g. -1.5 (favorite) or +2.5 (dog).
    std_dev ~4.2 runs is a reasonable MLB single-game margin std dev (approx,
    derived from historical MLB scoring variance).
    park_run_factor: the game's venue R factor (100 = neutral) from PARK_FACTORS.
    A park factor >100 raises scoring for both teams, which widens the
    plausible margin somewhat; applied as a mild scaling on std_dev since a
    higher-scoring environment tends to produce more spread-out final margins.

    PITCHER ADJUSTMENT: team_a/b's runs_allowed_pg (a full-season, all-pitchers
    average) is nudged toward the starting pitcher's own recent-start ERA,
    when we have enough recent starts to trust it (starts_sampled >= 3).
    This is a blend, not a replacement - a team's bullpen still plays a role
    in the final runs-allowed number, so we don't want to hand the whole
    game's expected runs to one pitcher's small sample. The blend weight
    below (0.6 toward the pitcher) is a deliberate, disclosed choice, not a
    fitted constant - treat this as directional, same as the rest of the
    model.

    FATIGUE ADJUSTMENT: if the pitcher is flagged as fatigued (short rest
    or a declining innings trend - see assess_pitcher_fatigue), the
    pitcher-implied runs-allowed number gets a small additional penalty on
    top of the blend above. Deliberately small and disclosed, not fitted.
    """
    if not team_a_stats or not team_b_stats:
        return None

    def pitcher_adjusted_runs_allowed(team_runs_allowed_pg, pitcher_form, fatigue, weight=0.6):
        if not pitcher_form or pitcher_form.get("starts_sampled", 0) < 3:
            return team_runs_allowed_pg
        # recent_era is runs per 9 innings; runs_allowed_pg is runs per game
        # (roughly runs per 9 innings too, for a full team game) - comparable
        # units, so a direct blend is reasonable here.
        pitcher_implied_runs_pg = pitcher_form["recent_era"]
        if fatigue and fatigue.get("is_fatigue_flag"):
            pitcher_implied_runs_pg *= 1.08  # small, disclosed fatigue penalty
        return round(
            team_runs_allowed_pg * (1 - weight) + pitcher_implied_runs_pg * weight, 2
        )

    a_runs_allowed = pitcher_adjusted_runs_allowed(team_a_stats["runs_allowed_pg"], pitcher_a_form, pitcher_a_fatigue)
    b_runs_allowed = pitcher_adjusted_runs_allowed(team_b_stats["runs_allowed_pg"], pitcher_b_form, pitcher_b_fatigue)

    expected_margin = (team_a_stats["runs_scored_pg"] - a_runs_allowed) - \
                       (team_b_stats["runs_scored_pg"] - b_runs_allowed)
    park_scale = (park_run_factor / 100) ** 0.5  # dampened scaling, not linear
    adj_std_dev = std_dev * park_scale
    z = (spread + expected_margin) / adj_std_dev
    prob = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return round(prob, 3)


# ---------- main ----------

def build_report():
    games = get_todays_games()

    # Compute a live league-average K/game across today's participating teams,
    # so the opponent adjustment is relative to current-season reality rather
    # than a hardcoded guess.
    team_k_cache = {}
    team_run_stats_cache = {}
    for g in games:
        for tid in (g["away_team_id"], g["home_team_id"]):
            if tid not in team_k_cache:
                team_k_cache[tid] = get_team_k_rate(tid)
            if tid not in team_run_stats_cache:
                team_run_stats_cache[tid] = get_team_run_stats(tid)
    valid_k_rates = [v for v in team_k_cache.values() if v]
    league_avg_k = (sum(valid_k_rates) / len(valid_k_rates)) if valid_k_rates else LEAGUE_AVG_K_PER_GAME_FALLBACK

    report = []
    for g in games:
        park = PARK_FACTORS.get(g["home_team_id"])
        park_r_factor = park["R"] if park else 100

        entry = {
            "matchup": f"{g['away_team_short']} @ {g['home_team_short']}",
            "away_team": g["away_team_short"],
            "home_team": g["home_team_short"],
            "park_factor": park,
            "park_description": describe_park_factor(park),
            "pitchers": [],
            "spread_lines": []
        }

        for side, pid, pname, opp_id, opp_name in [
            ("away", g["away_pitcher_id"], g["away_pitcher"], g["home_team_id"], g["home_team_short"]),
            ("home", g["home_pitcher_id"], g["home_pitcher"], g["away_team_id"], g["away_team_short"]),
        ]:
            if not pid:
                continue
            k_list = get_pitcher_recent_strikeouts(pid)
            base_probs = strikeout_floor_probs(k_list)
            opp_k_rate = team_k_cache.get(opp_id)
            adjusted_probs = adjust_k_floor_for_opponent(base_probs, opp_k_rate, league_avg_k)
            platoon = get_pitcher_platoon_splits(pid)
            fatigue = assess_pitcher_fatigue(pid)

            # Apply park SO factor as a further mild adjustment (park factors
            # affect strikeout rates too - e.g. Coors suppresses K's, Mariners'
            # park inflates them). Dampened the same way as the opponent adjustment.
            park_so_factor = park["SO"] if park else 100
            park_scale = 1 + ((park_so_factor / 100) - 1) * 0.5
            park_adjusted_probs = {
                t: round(max(0.0, min(1.0, p * park_scale)), 3)
                for t, p in adjusted_probs.items()
            }

            # A fatigue flag (short rest or declining innings) nudges K-floors
            # down slightly - a tired starter is less likely to reach deep
            # strikeout counts even if his season rate says otherwise.
            # Dampened deliberately: this is directional, not a fitted weight.
            if fatigue and fatigue["is_fatigue_flag"]:
                park_adjusted_probs = {
                    t: round(max(0.0, p * 0.92), 3) for t, p in park_adjusted_probs.items()
                }

            opponent_team_id_for_lineup = opp_id
            lineup_handedness = get_confirmed_lineup_handedness(g["gamePk"], opponent_team_id_for_lineup)
            lineup_matchup = assess_pitcher_vs_lineup(platoon, lineup_handedness)

            entry["pitchers"].append({
                "name": pname,
                "side": side,
                "opponent": opp_name,
                "recent_starts_sampled": len(k_list),
                "recent_k_values": k_list,
                "floor_probabilities_raw": base_probs,
                "floor_probabilities_opponent_adjusted": adjusted_probs,
                "floor_probabilities_final": park_adjusted_probs,
                "opponent_k_per_game": round(opp_k_rate, 2) if opp_k_rate else None,
                "league_avg_k_per_game": round(league_avg_k, 2),
                "park_so_factor": park_so_factor,
                "platoon": platoon,
                "fatigue": fatigue,
                "lineup_matchup": lineup_matchup,
            })

        away_stats = team_run_stats_cache.get(g["away_team_id"])
        home_stats = team_run_stats_cache.get(g["home_team_id"])

        # Pull each side's probable starter's recent-start form so the
        # spread model reacts to who's actually pitching today, not just
        # each team's full-season pitching average.
        away_pitcher_form = get_pitcher_recent_form(g["away_pitcher_id"]) if g["away_pitcher_id"] else None
        home_pitcher_form = get_pitcher_recent_form(g["home_pitcher_id"]) if g["home_pitcher_id"] else None

        # Reuse fatigue already computed in the pitcher loop above, rather
        # than calling assess_pitcher_fatigue a second time.
        away_pitcher_fatigue = next((p["fatigue"] for p in entry["pitchers"] if p["side"] == "away"), None)
        home_pitcher_fatigue = next((p["fatigue"] for p in entry["pitchers"] if p["side"] == "home"), None)

        for spread in (-1.5, 1.5, 2.5):
            p_away = spread_cover_prob(
                away_stats, home_stats, spread, park_run_factor=park_r_factor,
                pitcher_a_form=away_pitcher_form, pitcher_b_form=home_pitcher_form,
                pitcher_a_fatigue=away_pitcher_fatigue, pitcher_b_fatigue=home_pitcher_fatigue
            )
            p_home = spread_cover_prob(
                home_stats, away_stats, spread, park_run_factor=park_r_factor,
                pitcher_a_form=home_pitcher_form, pitcher_b_form=away_pitcher_form,
                pitcher_a_fatigue=home_pitcher_fatigue, pitcher_b_fatigue=away_pitcher_fatigue
            )
            entry["spread_lines"].append({
                "spread": spread,
                "away_cover_prob": p_away,
                "home_cover_prob": p_home
            })

        entry["away_pitcher_form"] = away_pitcher_form
        entry["home_pitcher_form"] = home_pitcher_form

        report.append(entry)
    return report


def _prob_bar(label, prob, color):
    if prob is None:
        return f"""<div class="pbar-row">
            <span class="pbar-label">{label}</span>
            <div class="pbar-track"><div class="pbar-fill pbar-na"></div></div>
            <span class="pbar-value pbar-na-text">N/A</span>
        </div>"""
    pct = prob * 100
    return f"""<div class="pbar-row">
        <span class="pbar-label">{label}</span>
        <div class="pbar-track"><div class="pbar-fill" style="width:{pct:.0f}%; background:{color};"></div></div>
        <span class="pbar-value">{pct:.0f}%</span>
    </div>"""


def render_html(report):
    cards = []
    for g in report:
        block = []
        block.append('<section class="matchup-card">')
        block.append('<div class="matchup-header">')
        block.append('<div class="court-line"></div>')
        block.append(f'<h2>{g["away_team"]} <span class="at-sign">@</span> {g["home_team"]}</h2>')
        if g.get("park_description"):
            block.append(f'<p class="rest-line">{g["park_description"]}</p>')
        block.append('</div>')

        block.append('<h3 class="section-label">Spread Cover</h3>')
        block.append('<div class="spread-block">')
        for s in g["spread_lines"]:
            block.append('<div class="spread-row-group">')
            block.append(f'<span class="spread-num">{s["spread"]:+}</span>')
            block.append(_prob_bar(g["away_team"], s["away_cover_prob"], "var(--teal)"))
            block.append(_prob_bar(g["home_team"], s["home_cover_prob"], "var(--orange)"))
            block.append('</div>')
        block.append('</div>')

        block.append('<h3 class="section-label">Starting Pitchers</h3>')
        for p in g["pitchers"]:
            side_label = g["away_team"] if p["side"] == "away" else g["home_team"]
            block.append('<div class="player-block">')
            block.append(f'<p class="player-name">{p["name"]} <span class="games-sampled">'
                         f'{side_label}, facing {p["opponent"]} &middot; last {p["recent_starts_sampled"]} starts</span></p>')

            fatigue = p.get("fatigue")
            if fatigue and fatigue.get("note"):
                block.append(f'<div class="flag-chip flag-chip-inline">&#9888; {fatigue["note"].capitalize()}.</div>')

            lineup_matchup = p.get("lineup_matchup")
            if lineup_matchup:
                if lineup_matchup.get("available"):
                    block.append(f'<p class="vs-opp-line">{lineup_matchup["summary"]}</p>')
                else:
                    block.append(f'<p class="vs-opp-line vs-opp-empty">{lineup_matchup["reason"]}</p>')

            platoon = p.get("platoon")
            if platoon and platoon.get("k_rate_vs_lhb") is not None and platoon.get("k_rate_vs_rhb") is not None:
                block.append(f'<p class="vs-opp-line">Throws {platoon.get("throws","?")} &middot; '
                             f'K rate vs LHB {platoon["k_rate_vs_lhb"]*100:.0f}% &middot; '
                             f'K rate vs RHB {platoon["k_rate_vs_rhb"]*100:.0f}%</p>')

            form = p.get("recent_era_form")
            block.append('<div class="stat-group">')
            block.append('<span class="stat-group-label">Strikeouts</span>')
            block.append('<div class="pill-row">')
            for t, prob in p["floor_probabilities_final"].items():
                pct = prob * 100
                tier = "pill-hot" if pct >= 70 else ("pill-warm" if pct >= 40 else "pill-cool")
                block.append(f'<span class="pill {tier}">{t}+ K &middot; {pct:.0f}%</span>')
            block.append('</div>')
            block.append('</div>')
            block.append('</div>')

        block.append('<h3 class="section-label">Starter Recent Run Prevention (used in spread above)</h3>')
        block.append('<div class="spread-block">')
        for label, form in ((g["away_team"], g.get("away_pitcher_form")),
                             (g["home_team"], g.get("home_pitcher_form"))):
            if form:
                block.append(f'<p class="rest-line">{label}: {form["recent_era"]} ERA over last '
                             f'{form["starts_sampled"]} starts ({form["innings_pitched_total"]} IP)</p>')
            else:
                block.append(f'<p class="rest-line vs-opp-empty">{label}: recent form unavailable - '
                             f'spread uses team season average only for this side.</p>')
        block.append('</div>')

        block.append('</section>')
        cards.append("".join(block))

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MLB Daily Probabilities</title>
<style>
:root {{
  --bg: #0B1120;
  --card: #131B2E;
  --card-border: #1F2A44;
  --orange: #E8630A;
  --teal: #2DD4BF;
  --amber: #F5A623;
  --text: #F1F3F5;
  --text-dim: #8B96AC;
  --h1-accent: #ffb35c;
  --disclaimer-text: #C97B7B;
  --disclaimer-bg: rgba(232, 99, 10, 0.08);
  --disclaimer-border: rgba(232, 99, 10, 0.2);
  --flag-bg: rgba(245, 166, 35, 0.1);
  --flag-border: rgba(245, 166, 35, 0.3);
  --row-tint: rgba(255,255,255,0.02);
  --track-bg: rgba(255,255,255,0.06);
  --pill-hot-bg: rgba(45, 212, 191, 0.16);
  --pill-hot-text: #5eead4;
  --pill-hot-border: rgba(45, 212, 191, 0.4);
  --pill-warm-bg: rgba(232, 99, 10, 0.16);
  --pill-warm-text: #ffab6b;
  --pill-warm-border: rgba(232, 99, 10, 0.4);
  --pill-cool-bg: rgba(255,255,255,0.03);
  --pill-cool-text: #5b6579;
  --pill-cool-border: rgba(255,255,255,0.06);
}}
@media (prefers-color-scheme: light) {{
  :root {{
    --bg: #F7F8FA;
    --card: #FFFFFF;
    --card-border: #E2E6ED;
    --orange: #D4560A;
    --teal: #0D9488;
    --amber: #B8730E;
    --text: #1A2233;
    --text-dim: #64708A;
    --h1-accent: #E8630A;
    --disclaimer-text: #A8391F;
    --disclaimer-bg: rgba(212, 86, 10, 0.06);
    --disclaimer-border: rgba(212, 86, 10, 0.18);
    --flag-bg: rgba(184, 115, 14, 0.08);
    --flag-border: rgba(184, 115, 14, 0.3);
    --row-tint: rgba(20, 30, 50, 0.02);
    --track-bg: rgba(20, 30, 50, 0.08);
    --pill-hot-bg: rgba(13, 148, 136, 0.1);
    --pill-hot-text: #0D9488;
    --pill-hot-border: rgba(13, 148, 136, 0.3);
    --pill-warm-bg: rgba(212, 86, 10, 0.1);
    --pill-warm-text: #B8480E;
    --pill-warm-border: rgba(212, 86, 10, 0.3);
    --pill-cool-bg: rgba(20, 30, 50, 0.03);
    --pill-cool-text: #7A879E;
    --pill-cool-border: rgba(20, 30, 50, 0.08);
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: -apple-system, "Segoe UI", sans-serif;
  max-width: 720px;
  margin: 0 auto;
  padding: 16px;
  background: var(--bg);
  color: var(--text);
}}
h1 {{
  font-family: "Arial Narrow", "Oswald", -apple-system, sans-serif;
  font-weight: 800;
  font-size: 1.9em;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  margin: 4px 0 2px;
  background: linear-gradient(90deg, var(--orange), var(--h1-accent));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}}
.updated {{ color: var(--text-dim); font-size: 0.82em; margin: 0 0 10px; }}
.disclaimer {{
  color: var(--disclaimer-text);
  font-size: 0.78em;
  background: var(--disclaimer-bg);
  border: 1px solid var(--disclaimer-border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 22px;
  line-height: 1.5;
}}
.matchup-card {{
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  padding: 0 0 22px;
  margin-bottom: 28px;
  overflow: hidden;
}}
.matchup-header {{ padding: 20px 20px 12px; }}
.court-line {{
  height: 3px;
  width: calc(100% + 2px);
  background: linear-gradient(90deg, var(--orange), var(--teal));
  margin: -1px -1px 16px -1px;
}}
.matchup-header h2 {{
  font-family: "Arial Narrow", "Oswald", -apple-system, sans-serif;
  font-weight: 700;
  font-size: 1.25em;
  letter-spacing: 0.01em;
  margin: 0;
  line-height: 1.3;
  color: var(--text);
}}
.at-sign {{ color: var(--text-dim); font-weight: 400; }}
.rest-line {{ color: var(--text-dim); font-size: 0.82em; margin: 8px 0 0; }}
.flag-chip {{
  color: var(--amber);
  background: var(--flag-bg);
  border: 1px solid var(--flag-border);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 0.82em;
  line-height: 1.5;
}}
.flag-chip-inline {{ margin: 0 0 12px; }}
.section-label {{
  color: var(--text-dim);
  font-size: 0.72em;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-weight: 700;
  padding: 0 20px;
  margin: 26px 0 12px;
}}
.spread-block {{ padding: 0 20px; display: flex; flex-direction: column; gap: 12px; }}
.spread-row-group {{
  background: var(--row-tint);
  border: 1px solid var(--card-border);
  border-radius: 10px;
  padding: 10px 12px 12px;
}}
.spread-num {{ display: block; font-weight: 700; font-size: 0.85em; color: var(--text-dim); margin-bottom: 8px; }}
.pbar-row {{ display: flex; align-items: center; gap: 8px; margin: 6px 0; }}
.pbar-label {{ width: 34px; font-size: 0.78em; color: var(--text-dim); font-weight: 600; flex-shrink: 0; }}
.pbar-track {{ flex: 1; height: 8px; background: var(--track-bg); border-radius: 4px; overflow: hidden; }}
.pbar-fill {{ height: 100%; border-radius: 4px; }}
.pbar-na {{ width: 0%; }}
.pbar-value {{ width: 38px; text-align: right; font-size: 0.82em; font-weight: 700; flex-shrink: 0; color: var(--text); }}
.pbar-na-text {{ color: var(--text-dim); font-weight: 400; }}
.player-block {{ padding: 14px 20px 16px; border-top: 1px solid var(--card-border); }}
.player-block:first-of-type {{ border-top: none; padding-top: 0; }}
.player-name {{ font-size: 0.98em; font-weight: 700; margin: 0 0 10px; color: var(--text); }}
.games-sampled {{ color: var(--text-dim); font-weight: 400; font-size: 0.82em; display: block; margin-top: 2px; }}
.stat-group {{ margin-top: 10px; }}
.stat-group-label {{
  display: block; color: var(--text-dim); font-size: 0.68em; text-transform: uppercase;
  letter-spacing: 0.08em; font-weight: 700; margin-bottom: 6px;
}}
.pill-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.pill {{ font-size: 0.74em; font-weight: 700; padding: 5px 10px; border-radius: 20px; white-space: nowrap; letter-spacing: 0.01em; }}
.pill-hot {{ background: var(--pill-hot-bg); color: var(--pill-hot-text); border: 1px solid var(--pill-hot-border); }}
.pill-warm {{ background: var(--pill-warm-bg); color: var(--pill-warm-text); border: 1px solid var(--pill-warm-border); }}
.pill-cool {{ background: var(--pill-cool-bg); color: var(--pill-cool-text); border: 1px solid var(--pill-cool-border); }}
.vs-opp-line {{ color: var(--text-dim); font-size: 0.78em; margin: 8px 0 0; line-height: 1.6; }}
.vs-opp-empty {{ font-style: italic; }}
</style>
</head>
<body>
<h1>MLB Daily Probabilities</h1>
<p class="updated">Generated {datetime.utcnow().strftime('%d %b %y %H:%M UTC')}</p>
<p class="disclaimer">Estimates only, not guarantees. Verify actual lines at your sportsbook before betting. K probabilities are adjusted for opponent team strikeout tendency, park strikeout factor, and pitcher fatigue. Spread probabilities blend season-long team run differential with the probable starter's last-5-start ERA and fatigue status, adjusted for park run factor. Pitcher-vs-lineup matchup reads use the confirmed starting lineup when posted; earlier in the day this is unavailable. Park factors: {PARK_FACTOR_SOURCE}. Treat all outputs as directional, not precise - a single-game result can miss even a well-calibrated probability, which is expected variance, not necessarily a broken model.</p>
{''.join(cards)}
</body>
</html>"""
    return html


if __name__ == "__main__":
    report = build_report()
    os.makedirs("docs", exist_ok=True)
    with open("docs/report.json", "w") as f:
        json.dump(report, f, indent=2)
    with open("docs/index.html", "w") as f:
        f.write(render_html(report))
    print(f"Done. {len(report)} games processed.")
