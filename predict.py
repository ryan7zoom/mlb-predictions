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


# ---------- pitcher strikeout history ----------

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
                       pitcher_a_form=None, pitcher_b_form=None, league_avg_era=4.20):
    """
    Estimate P(team_a covers `spread`) using a normal approximation
    of MLB run-differential margin, adjusted for the park's run environment
    and, when available, each side's starting pitcher's recent form.

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
    """
    if not team_a_stats or not team_b_stats:
        return None

    def pitcher_adjusted_runs_allowed(team_runs_allowed_pg, pitcher_form, weight=0.6):
        if not pitcher_form or pitcher_form.get("starts_sampled", 0) < 3:
            return team_runs_allowed_pg
        # recent_era is runs per 9 innings; runs_allowed_pg is runs per game
        # (roughly runs per 9 innings too, for a full team game) - comparable
        # units, so a direct blend is reasonable here.
        pitcher_implied_runs_pg = pitcher_form["recent_era"]
        return round(
            team_runs_allowed_pg * (1 - weight) + pitcher_implied_runs_pg * weight, 2
        )

    a_runs_allowed = pitcher_adjusted_runs_allowed(team_a_stats["runs_allowed_pg"], pitcher_a_form)
    b_runs_allowed = pitcher_adjusted_runs_allowed(team_b_stats["runs_allowed_pg"], pitcher_b_form)

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

            # Apply park SO factor as a further mild adjustment (park factors
            # affect strikeout rates too - e.g. Coors suppresses K's, Mariners'
            # park inflates them). Dampened the same way as the opponent adjustment.
            park_so_factor = park["SO"] if park else 100
            park_scale = 1 + ((park_so_factor / 100) - 1) * 0.5
            park_adjusted_probs = {
                t: round(max(0.0, min(1.0, p * park_scale)), 3)
                for t, p in adjusted_probs.items()
            }

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
                "platoon": platoon
            })

        away_stats = team_run_stats_cache.get(g["away_team_id"])
        home_stats = team_run_stats_cache.get(g["home_team_id"])

        # Pull each side's probable starter's recent-start form so the
        # spread model reacts to who's actually pitching today, not just
        # each team's full-season pitching average (a team can run 15-20+
        # different pitchers through a season - the guy on the mound today
        # matters far more than that blended average).
        away_pitcher_form = get_pitcher_recent_form(g["away_pitcher_id"]) if g["away_pitcher_id"] else None
        home_pitcher_form = get_pitcher_recent_form(g["home_pitcher_id"]) if g["home_pitcher_id"] else None

        for spread in (-1.5, 1.5, 2.5):
            p_away = spread_cover_prob(
                away_stats, home_stats, spread, park_run_factor=park_r_factor,
                pitcher_a_form=away_pitcher_form, pitcher_b_form=home_pitcher_form
            )
            p_home = spread_cover_prob(
                home_stats, away_stats, spread, park_run_factor=park_r_factor,
                pitcher_a_form=home_pitcher_form, pitcher_b_form=away_pitcher_form
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


def render_html(report):
    rows = []
    for g in report:
        rows.append(f"<h2>{g['away_team']} (Away) @ {g['home_team']} (Home)</h2>")
        rows.append("<div class='card'>")
        rows.append("<h3>Pitcher Strikeout Floors</h3>")
        park = g.get("park_factor")
        if park:
            rows.append(f"<p class='sub'>Park: {park['team']} home venue — "
                        f"Runs {park['R']}, HR {park['HR']}, SO {park['SO']} "
                        f"(100 = neutral, 3yr rolling factor)</p>")

        for p in g["pitchers"]:
            side_label = "Away" if p["side"] == "away" else "Home"
            rows.append(f"<p><b>{p['name']}</b> — {side_label}, facing <b>{p['opponent']}</b> "
                        f"(sampled {p['recent_starts_sampled']} recent starts)</p>")
            if p.get("opponent_k_per_game"):
                rows.append(f"<p class='sub'>Opponent K/game: {p['opponent_k_per_game']} "
                            f"vs league avg {p['league_avg_k_per_game']} · "
                            f"Park SO factor: {p['park_so_factor']}</p>")
            platoon = p.get("platoon")
            if platoon and platoon.get("k_rate_vs_lhb") is not None and platoon.get("k_rate_vs_rhb") is not None:
                gap_flag = ""
                if platoon.get("platoon_gap") and platoon["platoon_gap"] > 0.08:
                    gap_flag = " ⚠ large platoon gap — outcome more matchup-sensitive than usual"
                rows.append(f"<p class='sub'>Throws {platoon.get('throws','?')} · "
                            f"K rate vs LHB: {platoon['k_rate_vs_lhb']*100:.0f}% · "
                            f"K rate vs RHB: {platoon['k_rate_vs_rhb']*100:.0f}%{gap_flag}</p>")
            rows.append("<ul>")
            for t, prob in p["floor_probabilities_final"].items():
                raw = p["floor_probabilities_raw"].get(t)
                raw_txt = f" (season raw: {raw*100:.0f}%)" if raw is not None else ""
                rows.append(f"<li>{t}+ strikeouts: <b>{prob*100:.0f}%</b>{raw_txt}</li>")
            rows.append("</ul>")

        rows.append("<h3>Starting Pitcher Recent Form (used in spread below)</h3>")
        for label, form in ((g["away_team"], g.get("away_pitcher_form")),
                             (g["home_team"], g.get("home_pitcher_form"))):
            if form:
                rows.append(f"<p class='sub'>{label}: {form['recent_era']} ERA over last "
                            f"{form['starts_sampled']} starts ({form['innings_pitched_total']} IP)</p>")
            else:
                rows.append(f"<p class='sub'>{label}: recent form unavailable (fewer than 3 tracked "
                            f"starts, or probable pitcher not yet announced) — spread uses team season "
                            f"average only for this side.</p>")

        rows.append("<h3>Spread Cover Probabilities</h3>")
        rows.append(f"<table><tr><th>Spread</th><th>{g['away_team']}</th><th>{g['home_team']}</th></tr>")
        for s in g["spread_lines"]:
            ap = f"{s['away_cover_prob']*100:.0f}%" if s['away_cover_prob'] is not None else "N/A"
            hp = f"{s['home_cover_prob']*100:.0f}%" if s['home_cover_prob'] is not None else "N/A"
            rows.append(f"<tr><td>{s['spread']}</td><td>{ap}</td><td>{hp}</td></tr>")
        rows.append("</table>")
        rows.append("</div>")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MLB Daily Probabilities</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 700px; margin: 0 auto; padding: 16px; background: #0f1115; color: #eee; }}
h1 {{ font-size: 1.3em; }}
h2 {{ margin-top: 2em; border-bottom: 1px solid #333; padding-bottom: 6px; }}
h3 {{ font-size: 1em; color: #aaa; margin-bottom: 4px; }}
.card {{ background: #1a1d24; border-radius: 10px; padding: 12px 16px; margin-bottom: 12px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
th, td {{ text-align: left; padding: 6px; border-bottom: 1px solid #333; }}
ul {{ margin: 4px 0 12px 0; padding-left: 18px; }}
.updated {{ color: #888; font-size: 0.85em; }}
.sub {{ color: #888; font-size: 0.85em; margin: -4px 0 8px 0; }}
</style>
</head>
<body>
<h1>MLB Daily Probabilities</h1>
<p class="updated">Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
<p style="color:#f66; font-size:0.85em;">Estimates only, not guarantees. Verify actual lines at your sportsbook before betting. K probabilities are adjusted for opponent team strikeout tendency and park strikeout factor. Spread probabilities blend season-long team run differential with the probable starter's last-5-start ERA (when available), adjusted for park run factor. Platoon (handedness) splits are shown for context where large gaps exist, but the actual starting lineup's handedness mix is not fetched daily. Park factors: {PARK_FACTOR_SOURCE}. Treat all outputs as directional, not precise, and remember any single-game result can miss even a well-calibrated probability - that's expected variance, not necessarily a broken model.</p>
{''.join(rows)}
</body>
</html>"""
    return html


if __name__ == "__main__":
    report = build_report()
    os.makedirs("docs", exist_ok=True)
    with open("docs/report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    with open("docs/index.html", "w") as f:
        f.write(render_html(report))
    print(f"Done. {len(report)} games processed.")
