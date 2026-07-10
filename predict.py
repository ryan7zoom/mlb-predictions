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


def spread_cover_prob(team_a_stats, team_b_stats, spread, std_dev=4.2):
    """
    Estimate P(team_a covers `spread`) using a normal approximation
    of MLB run-differential margin.
    spread is from team_a's perspective, e.g. -1.5 (favorite) or +2.5 (dog).
    std_dev ~4.2 runs is a reasonable MLB single-game margin std dev (approx,
    derived from historical MLB scoring variance).
    """
    if not team_a_stats or not team_b_stats:
        return None
    expected_margin = (
        (team_a_stats["runs_scored_pg"] - team_b_stats["runs_allowed_pg"]) -
        (team_b_stats["runs_scored_pg"] - team_a_stats["runs_allowed_pg"])
    ) / 2 + (team_a_stats["runs_scored_pg"] - team_a_stats["runs_allowed_pg"]) * 0 
    # simplified expected run differential for team_a
    expected_margin = (team_a_stats["runs_scored_pg"] - team_a_stats["runs_allowed_pg"]) - \
                       (team_b_stats["runs_scored_pg"] - team_b_stats["runs_allowed_pg"])
    # P(actual margin > -spread) i.e. covering
    z = (spread + expected_margin) / std_dev
    prob = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return round(prob, 3)


# ---------- main ----------

def build_report():
    games = get_todays_games()

    # Compute a live league-average K/game across today's participating teams,
    # so the opponent adjustment is relative to current-season reality rather
    # than a hardcoded guess.
    team_k_cache = {}
    for g in games:
        for tid in (g["away_team_id"], g["home_team_id"]):
            if tid not in team_k_cache:
                team_k_cache[tid] = get_team_k_rate(tid)
    valid_k_rates = [v for v in team_k_cache.values() if v]
    league_avg_k = (sum(valid_k_rates) / len(valid_k_rates)) if valid_k_rates else LEAGUE_AVG_K_PER_GAME_FALLBACK

    report = []
    for g in games:
        entry = {
            "matchup": f"{g['away_team_short']} @ {g['home_team_short']}",
            "away_team": g["away_team_short"],
            "home_team": g["home_team_short"],
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
            entry["pitchers"].append({
                "name": pname,
                "side": side,
                "opponent": opp_name,
                "recent_starts_sampled": len(k_list),
                "recent_k_values": k_list,
                "floor_probabilities_raw": base_probs,
                "floor_probabilities_adjusted": adjusted_probs,
                "opponent_k_per_game": round(opp_k_rate, 2) if opp_k_rate else None,
                "league_avg_k_per_game": round(league_avg_k, 2)
            })

        away_stats = get_team_run_stats(g["away_team_id"])
        home_stats = get_team_run_stats(g["home_team_id"])
        for spread in (-1.5, 1.5, 2.5):
            p_away = spread_cover_prob(away_stats, home_stats, spread)
            p_home = spread_cover_prob(home_stats, away_stats, spread)
            entry["spread_lines"].append({
                "spread": spread,
                "away_cover_prob": p_away,
                "home_cover_prob": p_home
            })

        report.append(entry)
    return report


def render_html(report):
    rows = []
    for g in report:
        rows.append(f"<h2>{g['away_team']} (Away) @ {g['home_team']} (Home)</h2>")
        rows.append("<div class='card'>")
        rows.append("<h3>Pitcher Strikeout Floors</h3>")
        for p in g["pitchers"]:
            side_label = "Away" if p["side"] == "away" else "Home"
            rows.append(f"<p><b>{p['name']}</b> — {side_label}, facing <b>{p['opponent']}</b> "
                        f"(sampled {p['recent_starts_sampled']} recent starts)</p>")
            if p.get("opponent_k_per_game"):
                rows.append(f"<p class='sub'>Opponent K/game: {p['opponent_k_per_game']} "
                            f"vs league avg {p['league_avg_k_per_game']} "
                            f"— adjusted for opponent strikeout tendency below</p>")
            rows.append("<ul>")
            for t, prob in p["floor_probabilities_adjusted"].items():
                raw = p["floor_probabilities_raw"].get(t)
                raw_txt = f" (raw: {raw*100:.0f}%)" if raw is not None else ""
                rows.append(f"<li>{t}+ strikeouts: <b>{prob*100:.0f}%</b>{raw_txt}</li>")
            rows.append("</ul>")
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
<p style="color:#f66; font-size:0.85em;">Estimates only, not guarantees. Verify actual lines at your sportsbook before betting. K probabilities are adjusted for opponent team strikeout tendency. Spread probabilities use season-long team run differential (not park-adjusted, not pitcher-specific, not handedness-split). Treat as directional, not precise.</p>
{''.join(rows)}
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
