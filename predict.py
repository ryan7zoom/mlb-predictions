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
PARK_FACTOR_SOURCE = "RotoWire 2026 Park Factors (3yr rolling, pitching), published May 17, 2026"

PARK_LOCATIONS = {
    108: {"lat": 33.8003, "lon": -117.8827, "dome": False},
    117: {"lat": 29.7573, "lon": -95.3555, "dome": True},
    133: {"lat": 37.7126, "lon": -122.2005, "dome": False},
    141: {"lat": 43.6414, "lon": -79.3894, "dome": True},
    144: {"lat": 33.8908, "lon": -84.4678, "dome": False},
    158: {"lat": 43.0280, "lon": -87.9712, "dome": True},
    138: {"lat": 38.6226, "lon": -90.1928, "dome": False},
    112: {"lat": 41.9484, "lon": -87.6553, "dome": False},
    109: {"lat": 33.4455, "lon": -112.0667, "dome": True},
    119: {"lat": 34.0739, "lon": -118.2400, "dome": False},
    137: {"lat": 37.7786, "lon": -122.3893, "dome": False},
    114: {"lat": 41.4962, "lon": -81.6852, "dome": False},
    136: {"lat": 47.5914, "lon": -122.3325, "dome": True},
    146: {"lat": 25.7781, "lon": -80.2196, "dome": True},
    121: {"lat": 40.7571, "lon": -73.8458, "dome": False},
    120: {"lat": 38.8730, "lon": -77.0074, "dome": False},
    110: {"lat": 39.2839, "lon": -76.6218, "dome": False},
    135: {"lat": 32.7076, "lon": -117.1570, "dome": False},
    143: {"lat": 39.9061, "lon": -75.1665, "dome": False},
    134: {"lat": 40.4469, "lon": -80.0057, "dome": False},
    140: {"lat": 32.7473, "lon": -97.0945, "dome": True},
    139: {"lat": 27.7683, "lon": -82.6534, "dome": True},
    111: {"lat": 42.3467, "lon": -71.0972, "dome": False},
    113: {"lat": 39.0975, "lon": -84.5061, "dome": False},
    115: {"lat": 39.7559, "lon": -104.9942, "dome": False},
    118: {"lat": 39.0517, "lon": -94.4803, "dome": False},
    116: {"lat": 42.3390, "lon": -83.0485, "dome": False},
    142: {"lat": 44.9817, "lon": -93.2776, "dome": False},
    145: {"lat": 41.8299, "lon": -87.6338, "dome": False},
    147: {"lat": 40.8296, "lon": -73.9262, "dome": False},
}
# Weather is skipped entirely for dome parks - real conditions inside a
# closed/retractable roof don't match outdoor forecast data, and pretending
# otherwise would produce a misleading adjustment.

def team_nickname(team_id, fallback_name=None):
    """
    Returns the team's nickname (e.g. 'Guardians') instead of the MLB Stats
    API's full/location-based name (e.g. 'Cleveland Guardians' or
    'Cleveland'). Uses the PARK_FACTORS table (keyed by team_id) as the
    source of truth since it already lists nicknames for every team.
    Falls back to whatever name the API gave us if the id isn't found
    (e.g. All-Star teams), so nothing breaks on an unmapped id.
    """
    entry = PARK_FACTORS.get(team_id)
    if entry:
        return entry["team"]
    return fallback_name


# ---------- sportsbook odds (The Odds API) ----------
#
# Free tier: 500 credits/month, no card required. One call to the /odds
# endpoint below with markets=h2h,spreads,totals costs a handful of credits
# for the WHOLE day's MLB slate (cost = markets x regions, not per-game), so
# a once-daily run comfortably fits the free quota for the full season.
#
# Docs: https://the-odds-api.com/liveapi/guides/v4/
#
# The key is read from the ODDS_API_KEY environment variable - set it as a
# GitHub Actions repo secret (Settings -> Secrets and variables -> Actions),
# never hardcode it here.

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")


def get_mlb_odds():
    """
    Fetches today's MLB odds board (moneyline, spreads, totals) from The
    Odds API, one call for the whole slate. Returns the raw list of event
    objects, or None if the key is missing or the call fails - callers
    must treat None as "no market data available today" and say so
    honestly rather than silently falling back to model-only numbers
    labeled as if they were market-checked.
    """
    if not ODDS_API_KEY:
        return None
    url = (f"{ODDS_API_BASE}/sports/baseball_mlb/odds"
           f"?regions=us&markets=h2h,spreads,totals&oddsFormat=decimal"
           f"&apiKey={ODDS_API_KEY}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"WARNING: odds fetch failed ({e}) - proceeding without market data")
        return None


def _remove_vig_two_way(decimal_odds_a, decimal_odds_b):
    """
    Converts a pair of two-way decimal odds into de-vigged ("fair") implied
    probabilities that sum to exactly 1.0.
    """
    if not decimal_odds_a or not decimal_odds_b or decimal_odds_a <= 1 or decimal_odds_b <= 1:
        return None, None
    raw_a = 1 / decimal_odds_a
    raw_b = 1 / decimal_odds_b
    overround = raw_a + raw_b
    if overround <= 0:
        return None, None
    return raw_a / overround, raw_b / overround


def _average_book_prices(bookmakers, market_key, point=None):
    """
    Averages decimal price for each outcome across all books offering
    market_key (and matching `point` for spreads/totals). Returns
    {outcome_name: avg_decimal_price}.
    """
    sums = {}
    counts = {}
    for bm in bookmakers:
        for market in bm.get("markets", []):
            if market.get("key") != market_key:
                continue
            for outcome in market.get("outcomes", []):
                if point is not None and outcome.get("point") != point:
                    continue
                name = outcome.get("name")
                price = outcome.get("price")
                if name is None or price is None:
                    continue
                sums[name] = sums.get(name, 0) + price
                counts[name] = counts.get(name, 0) + 1
    return {name: sums[name] / counts[name] for name in sums}


def get_market_lines_for_event(event, home_team, away_team):
    """
    Pulls fair (de-vigged), book-averaged probabilities for h2h, spreads,
    and totals out of one Odds API event object. Any market a book didn't
    post today is simply absent, never guessed at.
    """
    bookmakers = event.get("bookmakers", [])
    if not bookmakers:
        return {}
    result = {}

    h2h_avg = _average_book_prices(bookmakers, "h2h")
    if home_team in h2h_avg and away_team in h2h_avg:
        home_prob, away_prob = _remove_vig_two_way(h2h_avg[home_team], h2h_avg[away_team])
        if home_prob is not None:
            result["h2h"] = {
                "home_prob": round(home_prob, 4), "away_prob": round(away_prob, 4),
                "home_decimal": round(h2h_avg[home_team], 3), "away_decimal": round(h2h_avg[away_team], 3),
            }

    spread_points = set()
    for bm in bookmakers:
        for market in bm.get("markets", []):
            if market.get("key") == "spreads":
                for outcome in market.get("outcomes", []):
                    if outcome.get("name") == home_team and outcome.get("point") is not None:
                        spread_points.add(outcome["point"])
    spreads_out = []
    for point in sorted(spread_points):
        avg = _average_book_prices(bookmakers, "spreads", point=point)
        avg_away = _average_book_prices(bookmakers, "spreads", point=-point)
        if home_team in avg and away_team in avg_away:
            home_prob, away_prob = _remove_vig_two_way(avg[home_team], avg_away[away_team])
            if home_prob is not None:
                spreads_out.append({
                    "point": point, "home_prob": round(home_prob, 4), "away_prob": round(away_prob, 4),
                    "home_decimal": round(avg[home_team], 3), "away_decimal": round(avg_away[away_team], 3),
                })
    if spreads_out:
        result["spreads"] = spreads_out

    total_points = set()
    for bm in bookmakers:
        for market in bm.get("markets", []):
            if market.get("key") == "totals":
                for outcome in market.get("outcomes", []):
                    if outcome.get("point") is not None:
                        total_points.add(outcome["point"])
    totals_out = []
    for point in sorted(total_points):
        avg = _average_book_prices(bookmakers, "totals", point=point)
        if "Over" in avg and "Under" in avg:
            over_prob, under_prob = _remove_vig_two_way(avg["Over"], avg["Under"])
            if over_prob is not None:
                totals_out.append({
                    "point": point, "over_prob": round(over_prob, 4), "under_prob": round(under_prob, 4),
                    "over_decimal": round(avg["Over"], 3), "under_decimal": round(avg["Under"], 3),
                })
    if totals_out:
        result["totals"] = totals_out

    return result


def match_odds_event(odds_events, home_team_short, away_team_short):
    """
    The Odds API uses full team names while this script uses nicknames -
    match on "nickname is contained in the API's full name".
    """
    if not odds_events:
        return None
    for event in odds_events:
        api_home = event.get("home_team", "")
        api_away = event.get("away_team", "")
        if home_team_short in api_home and away_team_short in api_away:
            return event
    return None


def prob_to_decimal_odds(prob):
    """Fair decimal odds implied by a probability, e.g. 0.60 -> 1.67."""
    if not prob or prob <= 0:
        return None
    return round(1 / prob, 2)


def calc_edge(model_prob, market_prob):
    """
    Edge = model probability minus market fair probability, in percentage
    points. A model probability with no market number to compare against
    is not an edge, just an opinion.
    """
    if model_prob is None or market_prob is None:
        return None
    return round((model_prob - market_prob) * 100, 1)


# ---------- low-level fetch ----------

def get(path, params=None):
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def get_safe(path, params=None):
    """
    Same as get(), but returns None on any network/HTTP error instead of
    raising. Used for per-team/per-pitcher lookups where a single bad ID or
    a transient API hiccup shouldn't crash the entire report (e.g. an
    All-Star Game team ID that doesn't resolve on /teams/{id}/stats).
    The main schedule fetch intentionally still uses raw get() - if that
    fails, the whole run should stop rather than silently produce an empty
    report.
    """
    try:
        return get(path, params)
    except Exception:
        return None


# ---------- schedule / probable pitchers ----------

def get_game_weather(team_id, game_date=None):
    loc = PARK_LOCATIONS.get(team_id)
    if not loc or loc.get("dome"):
        return None
    if game_date is None:
        game_date = TODAY
    try:
        url = (f"https://api.open-meteo.com/v1/forecast?"
               f"latitude={loc['lat']}&longitude={loc['lon']}"
               f"&daily=temperature_2m_max,windspeed_10m_max,winddirection_10m_dominant"
               f"&temperature_unit=fahrenheit&windspeed_unit=mph"
               f"&start_date={game_date}&end_date={game_date}&timezone=auto")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        daily = data.get("daily", {})
        temp = daily.get("temperature_2m_max", [None])[0]
        wind_speed = daily.get("windspeed_10m_max", [None])[0]
        wind_dir = daily.get("winddirection_10m_dominant", [None])[0]
        if temp is None and wind_speed is None:
            return None
        return {
            "temp_f": round(temp, 1) if temp is not None else None,
            "wind_mph": round(wind_speed, 1) if wind_speed is not None else None,
            "wind_dir_deg": wind_dir,
        }
    except Exception:
        return None


def describe_weather_effect(weather):
    if not weather:
        return None
    notes = []
    temp = weather.get("temp_f")
    wind = weather.get("wind_mph")
    if temp is not None:
        if temp >= 85:
            notes.append(f"hot ({temp:.0f}F - ball tends to carry further)")
        elif temp <= 50:
            notes.append(f"cold ({temp:.0f}F - ball tends to carry less, mild boost to pitchers)")
    if wind is not None and wind >= 15:
        notes.append(f"windy ({wind:.0f} mph - can affect fly balls/control; "
                      f"direction vs field orientation not factored in, check closer to first pitch)")
    if not notes:
        return "Weather looks unremarkable for scoring purposes."
    return "Weather: " + "; ".join(notes) + "."


def get_bullpen_recent_form(team_id, season=None):
    if season is None:
        season = datetime.utcnow().year
    data = get_safe(f"/teams/{team_id}/stats", {
        "stats": "season",
        "group": "pitching",
        "season": season
    })
    try:
        stat = data["stats"][0]["splits"][0]["stat"]
        era = float(stat.get("era", 0) or 0)
        whip = float(stat.get("whip", 0) or 0)
        games = int(stat.get("gamesPlayed", 0) or 0)
        if not era or not games:
            return None
        return {
            "staff_era": round(era, 2),
            "staff_whip": round(whip, 2) if whip else None,
            "note": "whole pitching staff ERA (starters + bullpen combined) - "
                    "no clean bullpen-only split is available from this free source.",
        }
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def get_todays_games(date=None):
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")  # computed fresh per call,
        # not at module import time (a default arg is only evaluated once)
    data = get("/schedule", {
        "sportId": 1,
        "date": date,
        "hydrate": "probablePitcher,team,linescore"
    })
    games = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            # Skip non-regular-season games (All-Star Game "A", Spring
            # Training "S", etc.) - these use special exhibition team IDs
            # (e.g. AL/NL All-Star squads) that don't resolve on the normal
            # /teams/{id}/stats endpoint and would 404 the whole run.
            # Postseason ("F","D","L","W") games use real team IDs and are
            # fine to include.
            game_type = g.get("gameType")
            if game_type in ("A", "S", "E"):
                continue

            away = g["teams"]["away"]
            home = g["teams"]["home"]
            away_nick = team_nickname(away["team"]["id"], away["team"]["name"])
            home_nick = team_nickname(home["team"]["id"], home["team"]["name"])
            games.append({
                "gamePk": g["gamePk"],
                "away_team": away_nick,
                "away_team_short": away_nick,
                "away_team_abbr": away["team"].get("abbreviation") or away_nick[:3].upper(),
                "away_team_id": away["team"]["id"],
                "home_team": home_nick,
                "home_team_short": home_nick,
                "home_team_abbr": home["team"].get("abbreviation") or home_nick[:3].upper(),
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
    data = get_safe(f"/people/{pitcher_id}/stats", {
        "stats": "gameLog",
        "group": "pitching",
        "season": season
    })
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError, TypeError):
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
    data = get_safe(f"/people/{pitcher_id}/stats", {
        "stats": "gameLog",
        "group": "pitching",
        "season": season
    })
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError, TypeError):
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


def check_recent_il_activation(pitcher_id, before_date_str=TODAY, lookback_days=21):
    """
    Flags if a pitcher's own game log shows a start-to-start gap consistent
    with an IL stint ending recently (a gap much longer than normal rest,
    followed by a start within the lookback window). This is a heuristic
    based on gaps in the pitcher's own start dates, NOT a direct read of
    MLB's transaction log - can false-positive on a long All-Star break or
    a skipped start for non-injury reasons. Always surfaced as "verify
    before trusting", same framing as the WNBA return-from-absence heuristic.
    """
    data = get_safe(f"/people/{pitcher_id}/stats", {
        "stats": "gameLog",
        "group": "pitching",
        "season": datetime.utcnow().year,
    })
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError, TypeError):
        return None
    starts = [s for s in splits if s["stat"].get("gamesStarted") in ("1", 1)]
    starts.sort(key=lambda s: s.get("date", ""))
    if len(starts) < 2:
        return None

    try:
        today_dt = datetime.strptime(before_date_str, "%Y-%m-%d")
    except ValueError:
        return None

    last_start = starts[-1]
    try:
        last_dt = datetime.strptime(last_start["date"], "%Y-%m-%d")
    except (KeyError, ValueError):
        return None

    days_since_last_start = (today_dt - last_dt).days
    if days_since_last_start > lookback_days:
        return None

    prev_start = starts[-2]
    try:
        prev_dt = datetime.strptime(prev_start["date"], "%Y-%m-%d")
        gap = (last_dt - prev_dt).days
    except (KeyError, ValueError):
        gap = None
    if gap is not None and gap >= 15:
        return {
            "flag": True,
            "days_gap_before_return": gap,
            "days_since_return_start": days_since_last_start,
            "note": (f"gap of {gap} days between starts on "
                     f"{prev_start.get('date')} and {last_start.get('date')} - "
                     f"consistent with an IL stint or extended absence. Verify "
                     f"actual injury status before trusting this in a bet."),
        }
    return {"flag": False}


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
    data = get_safe(f"/game/{game_pk}/boxscore")
    if not data:
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



def get_pitcher_start_gamelogs(pitcher_id, season=None, last_n=12):
    """
    Single shared gamelog fetch for a starting pitcher's recent starts,
    returning per-start K count, innings pitched, and earned runs. Both
    get_pitcher_recent_strikeouts and get_pitcher_k_per_ip derive their
    lists from this one fetch instead of each hitting the API separately.
    """
    if season is None:
        season = datetime.utcnow().year
    data = get_safe(f"/people/{pitcher_id}/stats", {
        "stats": "gameLog",
        "group": "pitching",
        "season": season
    })
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError, TypeError):
        return []
    starts = [s for s in splits if s["stat"].get("gamesStarted", 0) in ("1", 1)]
    out = []
    for s in starts[-last_n:]:
        stat = s["stat"]
        try:
            ip = float(stat.get("inningsPitched", 0) or 0)
        except (TypeError, ValueError):
            ip = 0.0
        out.append({
            "date": s.get("date"),
            "strikeouts": int(stat.get("strikeOuts", 0)),
            "innings_pitched": ip,
            "earned_runs": int(stat.get("earnedRuns", 0)),
        })
    return out


def get_pitcher_recent_strikeouts(pitcher_id, season=None, last_n=12):
    """Return list of strikeout counts from the pitcher's most recent starts."""
    logs = get_pitcher_start_gamelogs(pitcher_id, season, last_n)
    return [g["strikeouts"] for g in logs]


def get_pitcher_k_per_ip(pitcher_id, season=None, last_n=12):
    """
    Strikeouts-per-inning-pitched rate over the pitcher's last N starts,
    derived from the same gamelog fetch as get_pitcher_recent_strikeouts
    (no duplicate API call). Used to sanity-check the K floor against
    today's likely innings, since a K floor built from a mix of 7-IP and
    5-IP starts isn't correctly discounted for a start where he's
    projected for fewer innings.
    Returns None if fewer than 3 starts have usable innings data.
    """
    logs = get_pitcher_start_gamelogs(pitcher_id, season, last_n)
    usable = [g for g in logs if g["innings_pitched"] > 0]
    if len(usable) < 3:
        return None
    total_k = sum(g["strikeouts"] for g in usable)
    total_ip = sum(g["innings_pitched"] for g in usable)
    if total_ip == 0:
        return None
    return {
        "starts_sampled": len(usable),
        "k_per_ip": round(total_k / total_ip, 3),
        "avg_ip_per_start": round(total_ip / len(usable), 2),
    }


def discount_k_floor_for_projected_innings(k_probs, k_per_ip_data, projected_innings):
    """
    If today's likely innings (from get_pitcher_innings_trend's recent
    average) are shorter than the innings baseline the K floor was built
    from (k_per_ip_data's avg_ip_per_start), discount the floor
    accordingly - a K floor built from 6-IP outings isn't trustworthy
    as-is for a start projected at 4-5 IP.
    Small, disclosed, unfitted dampening - same honesty pattern as the
    rest of this file's adjustments.
    """
    if not k_probs or not k_per_ip_data or not projected_innings:
        return k_probs
    baseline_ip = k_per_ip_data.get("avg_ip_per_start")
    if not baseline_ip or baseline_ip <= 0:
        return k_probs
    ip_ratio = projected_innings / baseline_ip
    if ip_ratio >= 1:
        return k_probs  # today's projected innings aren't shorter than baseline - no discount needed
    factor = 1 - (1 - ip_ratio) * 0.5  # UNFITTED CONSTANT - dampened, disclosed, not backtested
    return {t: round(max(0.0, p * factor), 3) for t, p in k_probs.items()}


def strikeout_consistency_signal(gamelogs):
    """
    Checks whether this pitcher's LOW-earned-run (good) outings tend to
    also be his high-strikeout outings, or whether he can pitch well
    without piling up K's (a contact-manager). Simple, explainable check:
    compares his average K's in his best-ERA half of recent starts vs his
    worst-ERA half, rather than a full correlation coefficient.

    Returns None if fewer than 4 starts are available (need at least 2 per
    half to be meaningful). If his best-ERA outings don't come with
    meaningfully higher K's than his worst-ERA outings, flags it in plain
    English - a good pitching line today doesn't necessarily mean a K
    prop hits for this particular pitcher.
    """
    usable = [g for g in gamelogs if g["innings_pitched"] > 0]
    if len(usable) < 4:
        return None
    with_era = []
    for g in usable:
        era = (g["earned_runs"] / g["innings_pitched"]) * 9
        with_era.append((era, g["strikeouts"]))
    with_era.sort(key=lambda x: x[0])  # lowest ERA (best outings) first
    half = len(with_era) // 2
    best_half = with_era[:half]
    worst_half = with_era[half:] if len(with_era) - half >= half else with_era[-half:]
    best_avg_k = sum(k for _, k in best_half) / len(best_half)
    worst_avg_k = sum(k for _, k in worst_half) / len(worst_half)
    # UNFITTED CONSTANT: "meaningfully higher" = at least 1 more K on
    # average in the good-ERA half - a disclosed, simple cutoff.
    ks_track_with_good_outings = best_avg_k >= worst_avg_k + 1.0
    note = None
    if not ks_track_with_good_outings:
        note = ("this pitcher's best outings recently haven't come with high strikeout counts - "
                "a good pitching line today doesn't necessarily mean this K prop hits")
    return {
        "best_era_half_avg_k": round(best_avg_k, 2),
        "worst_era_half_avg_k": round(worst_avg_k, 2),
        "ks_track_with_good_outings": ks_track_with_good_outings,
        "note": note,
    }


def dampen_k_floor_for_inconsistency(k_probs, consistency_signal):
    """
    Small, disclosed, dampened reduction to K floor probabilities when
    this pitcher's good outings don't reliably come with strikeouts - the
    plain-English flag from strikeout_consistency_signal is the primary
    surface for this, but the floor itself gets a small nudge down too,
    same pattern as adjust_k_floor_for_opponent. UNFITTED CONSTANT: 0.95,
    a small disclosed guess, not backtested.
    """
    if not k_probs or not consistency_signal:
        return k_probs
    if consistency_signal.get("ks_track_with_good_outings"):
        return k_probs
    return {t: round(max(0.0, p * 0.95), 3) for t, p in k_probs.items()}


def strikeout_floor_probs(k_list, thresholds=None):
    """
    Empirical probability of hitting each K threshold, based on recent starts.

    Real sportsbook strikeout lines sit close to a pitcher's actual median
    output, not a trivially low floor - a starter averaging 8-9 K/start
    typically gets a line of 6.5 or 7.5, not 3+ or 4+. If thresholds isn't
    given explicitly, build a pitcher-specific band centered on his own
    recent average so the "floor" we surface is one a book would plausibly
    post, instead of always the same fixed (3,4,5,6) - trivial for high-K
    arms and unhelpful for a low-K one who'd actually be tested lower.
    """
    n = len(k_list)
    if n == 0:
        return {}
    if thresholds is None:
        avg = statistics.mean(k_list)
        # Center on round(avg): typical lines run from ~2 below to ~1 above
        # a pitcher's recent average, e.g. a 6.8 K/start arm gets tested at
        # 5,6,7,8 rather than a blanket 3,4,5,6.
        center = max(2, round(avg))
        thresholds = tuple(sorted(set(
            t for t in range(center - 2, center + 2) if t >= 1
        )))
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
    try:
        data = get_safe(f"/teams/{team_id}/stats", {
            "stats": "season",
            "group": "hitting",
            "season": season
        })
    except Exception:
        return None
    try:
        stat = data["stats"][0]["splits"][0]["stat"]
        k = int(stat.get("strikeOuts", 0))
        games = int(stat.get("gamesPlayed", 1)) or 1
        return k / games
    except (KeyError, IndexError, TypeError):
        return None


def get_team_k_rate_recent(team_id, season=None, last_n=12):
    """
    Opponent's strikeouts-as-batter per game over its last N games (not
    season-long). Reuses the completed-games schedule approach used for
    run trend, then pulls boxscore K totals per game - one boxscore call
    per completed game in the window. Returns None below 5 games found.
    """
    if season is None:
        season = datetime.utcnow().year
    end = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    data = get_safe("/schedule", {
        "sportId": 1,
        "teamId": team_id,
        "startDate": start,
        "endDate": end,
        "season": season,
    })
    try:
        dates = data.get("dates", [])
    except AttributeError:
        return None
    game_pks = []
    for d in dates:
        for game in d.get("games", []):
            if game.get("status", {}).get("codedGameState") == "F":
                game_pks.append(game.get("gamePk"))
    game_pks = game_pks[-last_n:]
    if len(game_pks) < 5:
        return None

    k_totals = []
    for pk in game_pks:
        box = get_safe(f"/game/{pk}/boxscore")
        if not box:
            continue
        teams = box.get("teams", {})
        for side in ("home", "away"):
            t = teams.get(side, {})
            if t.get("team", {}).get("id") == team_id:
                k = t.get("teamStats", {}).get("batting", {}).get("strikeOuts")
                if k is not None:
                    k_totals.append(k)
    if len(k_totals) < 5:
        return None
    return round(sum(k_totals) / len(k_totals), 2)


def rank_team_k_rate(team_id, team_k_cache):
    """
    Where this team's strikeout rate ranks among teams playing today, e.g.
    "3rd of 20 teams in action today" - scoped to today's slate (the data
    already being fetched) rather than all 30 teams, to avoid extra calls
    purely for a ranking display.
    """
    valid = [(tid, k) for tid, k in team_k_cache.items() if k]
    if not valid or team_id not in team_k_cache or not team_k_cache[team_id]:
        return None
    ranked = sorted(valid, key=lambda x: x[1], reverse=True)
    for i, (tid, _) in enumerate(ranked, start=1):
        if tid == team_id:
            return {"rank": i, "of": len(ranked)}
    return None


def adjust_k_floor_for_opponent(base_probs, opponent_k_per_game, league_avg=LEAGUE_AVG_K_PER_GAME_FALLBACK):
    """
    Nudge strikeout-floor probabilities based on how strikeout-prone the
    opposing lineup is relative to league average.

    HONESTY NOTE on the 0.5 dampening factor: this is a deliberate,
    disclosed guess to keep a single stat from overcorrecting - it has
    not been backtested or fitted against actual prop outcomes. Same
    caveat applies to the other dampening constants in this file (park
    scaling, fatigue penalty) - all directional choices, not calibrated
    weights.
    """
    if not base_probs or not opponent_k_per_game or not league_avg:
        return base_probs
    factor = opponent_k_per_game / league_avg
    factor = 1 + (factor - 1) * 0.5  # UNFITTED CONSTANT - see docstring
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
    data = get_safe(f"/people/{pitcher_id}")
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
        data = get_safe(f"/people/{pitcher_id}/stats", {
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
    try:
        data = get_safe(f"/teams/{team_id}/stats", {
            "stats": "season",
            "group": "hitting",
            "season": season
        })
    except Exception:
        return None
    runs_scored = None
    games = None
    try:
        stat = data["stats"][0]["splits"][0]["stat"]
        runs_scored = int(stat.get("runs", 0))
        games = int(stat.get("gamesPlayed", 1))
    except (KeyError, IndexError, TypeError):
        pass

    try:
        data2 = get_safe(f"/teams/{team_id}/stats", {
            "stats": "season",
            "group": "pitching",
            "season": season
        })
    except Exception:
        return None
    runs_allowed = None
    try:
        stat2 = data2["stats"][0]["splits"][0]["stat"]
        runs_allowed = int(stat2.get("runs", 0))
    except (KeyError, IndexError, TypeError):
        pass

    if runs_scored is None or runs_allowed is None or not games:
        return None
    return {
        "runs_scored_pg": runs_scored / games,
        "runs_allowed_pg": runs_allowed / games,
    }


def get_team_recent_run_trend(team_id, season=None, last_n=12):
    """
    Team's runs scored and runs allowed per game over its last N games
    (not season-long average) - lets current form pull the expected margin
    away from a stale full-season number. Uses the team's completed-games
    schedule since MLB Stats API doesn't expose a "last N games" team stat
    directly. Returns None if fewer than 5 completed games are available.
    """
    if season is None:
        season = datetime.utcnow().year
    end = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=45)).strftime("%Y-%m-%d")
    data = get_safe("/schedule", {
        "sportId": 1,
        "teamId": team_id,
        "startDate": start,
        "endDate": end,
        "season": season,
    })
    try:
        dates = data.get("dates", [])
    except AttributeError:
        return None
    games = []
    for d in dates:
        for game in d.get("games", []):
            if game.get("status", {}).get("codedGameState") != "F":
                continue
            teams = game.get("teams", {})
            for side in ("home", "away"):
                t = teams.get(side, {})
                if t.get("team", {}).get("id") == team_id:
                    opp_side = "away" if side == "home" else "home"
                    runs_for = t.get("score")
                    runs_against = teams.get(opp_side, {}).get("score")
                    if runs_for is not None and runs_against is not None:
                        games.append({
                            "date": game.get("officialDate", d.get("date")),
                            "runs_for": runs_for,
                            "runs_against": runs_against,
                        })
    games.sort(key=lambda g: g["date"])
    recent = games[-last_n:]
    if len(recent) < 5:
        return None
    return {
        "games_sampled": len(recent),
        "runs_scored_pg": round(sum(g["runs_for"] for g in recent) / len(recent), 2),
        "runs_allowed_pg": round(sum(g["runs_against"] for g in recent) / len(recent), 2),
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
    data = get_safe(f"/people/{pitcher_id}/stats", {
        "stats": "gameLog",
        "group": "pitching",
        "season": season
    })
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError, TypeError):
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


def blended_runs_allowed(season_allowed, recent, pitcher_form, bullpen, fatigue):
    """
    Shared blend used by both spread_cover_prob and total_runs_prob so
    there's one source of truth for how a team's runs-allowed estimate is
    built. WEIGHTS (re-balanced now that bullpen and recent-team-form are
    separate inputs, not folded into "starter + season" alone):
      runs_allowed = 0.40 season + 0.20 recent-team + 0.30 starter + 0.10 bullpen
    A missing input's weight is redistributed proportionally across whatever
    IS available, rather than assuming a league-average value for it.
    ALL WEIGHTS ABOVE ARE DISCLOSED, UNFITTED CHOICES - not backtested
    against settled results. Treat every output as directional, not gospel.
    """
    components = [(season_allowed, 0.40)]
    if recent and recent.get("runs_allowed_pg") is not None:
        components.append((recent["runs_allowed_pg"], 0.20))
    if pitcher_form and pitcher_form.get("starts_sampled", 0) >= 3:
        starter_val = pitcher_form["recent_era"]
        if fatigue and fatigue.get("is_fatigue_flag"):
            starter_val *= 1.08  # small, disclosed fatigue penalty - unfitted
        components.append((starter_val, 0.30))
    if bullpen and bullpen.get("staff_era"):
        components.append((bullpen["staff_era"], 0.10))
    total_weight = sum(w for _, w in components)
    if total_weight == 0:
        return season_allowed
    return round(sum(v * w for v, w in components) / total_weight, 2)


def blended_runs_scored(season_scored, recent):
    """Shared blend used by both spread_cover_prob and total_runs_prob."""
    if recent and recent.get("runs_scored_pg") is not None:
        return round(season_scored * 0.7 + recent["runs_scored_pg"] * 0.3, 2)
    return season_scored


def park_scoring_scale(park_run_factor):
    """
    Dampened (sqrt) scaling applied to the expected LEVEL of scoring for a
    game at this park, not just to variance. Same dampening pattern as the
    existing variance-widening scale below and as park_so_factor's 0.5
    dampening elsewhere in this file - not applied linearly.
    UNFITTED CONSTANT: sqrt dampening, not backtested against settled
    results. Shared by spread_cover_prob and total_runs_prob so a hitter's
    park like Coors shifts both markets consistently.
    """
    return (park_run_factor / 100) ** 0.5


def spread_cover_prob(team_a_stats, team_b_stats, spread, park_run_factor=100, std_dev=4.2,
                       pitcher_a_form=None, pitcher_b_form=None, pitcher_a_fatigue=None,
                       pitcher_b_fatigue=None, league_avg_era=4.20,
                       team_a_recent=None, team_b_recent=None,
                       bullpen_a=None, bullpen_b=None, weather_a=None):
    """
    Estimate P(team_a covers `spread`) using a normal approximation of MLB
    run-differential margin.

    Blend inputs (each optional, gracefully degrading if missing):
      - team_x_stats: full-season runs_scored_pg / runs_allowed_pg (baseline)
      - team_x_recent: last-~12-game runs trend (get_team_recent_run_trend)
      - pitcher_x_form: probable starter's last-5-start ERA
      - bullpen_x: team staff ERA proxy (get_bullpen_recent_form)
      - pitcher_x_fatigue: short-rest/declining-innings flag
      - weather_a: home-park weather snapshot

    spread is from team_a's perspective. std_dev ~4.2 runs is an approximate
    MLB single-game margin std dev. park_run_factor: venue R factor (100=neutral).

    PARK FACTOR APPLIES TWICE, TO TWO DIFFERENT THINGS:
      1. It shifts the expected LEVEL of scoring itself (both teams'
         blended runs_scored/runs_allowed are scaled by park_scoring_scale
         BEFORE expected_margin is computed) - a hitter's park like Coors
         should raise the actual expected run total for both sides, not
         just widen the range of outcomes around an unchanged margin.
      2. It also still widens/narrows adj_std_dev (the uncertainty band),
         since a high-scoring park also tends to produce more variable
         final margins. Both effects are real and both are kept.
    """
    if not team_a_stats or not team_b_stats:
        return None

    a_runs_allowed = blended_runs_allowed(
        team_a_stats["runs_allowed_pg"], team_a_recent, pitcher_a_form, bullpen_a, pitcher_a_fatigue)
    b_runs_allowed = blended_runs_allowed(
        team_b_stats["runs_allowed_pg"], team_b_recent, pitcher_b_form, bullpen_b, pitcher_b_fatigue)
    a_runs_scored = blended_runs_scored(team_a_stats["runs_scored_pg"], team_a_recent)
    b_runs_scored = blended_runs_scored(team_b_stats["runs_scored_pg"], team_b_recent)

    scoring_scale = park_scoring_scale(park_run_factor)
    a_runs_scored *= scoring_scale
    b_runs_scored *= scoring_scale
    a_runs_allowed *= scoring_scale
    b_runs_allowed *= scoring_scale

    expected_margin = (a_runs_scored - a_runs_allowed) - (b_runs_scored - b_runs_allowed)

    park_scale = (park_run_factor / 100) ** 0.5  # dampened scaling, not linear - unfitted
    weather_scale = 1.0
    if weather_a:
        wind = weather_a.get("wind_mph")
        if wind is not None and wind >= 15:
            weather_scale = 1.05  # small widening of variance - unfitted, no wind-direction data
    adj_std_dev = std_dev * park_scale * weather_scale

    z = (spread + expected_margin) / adj_std_dev
    prob = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return round(prob, 3)


def total_runs_prob(team_a_stats, team_b_stats, total_line, park_run_factor=100,
                     std_dev=5.6, pitcher_a_form=None, pitcher_b_form=None,
                     pitcher_a_fatigue=None, pitcher_b_fatigue=None,
                     team_a_recent=None, team_b_recent=None,
                     bullpen_a=None, bullpen_b=None):
    """
    Estimate P(combined runs > total_line) using a normal approximation,
    same style as spread_cover_prob's z-score approach. Reuses the same
    blended_runs_allowed / blended_runs_scored / park_scoring_scale helpers
    as spread_cover_prob (see item 1's park-factor fix) rather than
    duplicating that blend logic, so both markets react to park factor the
    same way.

    Each team's expected run contribution = average of its own park-scaled
    scoring rate and the opponent's park-scaled rate of allowing runs (same
    "both signals matter" idea as margin, but summed instead of differenced).
    mean = sum of both teams' expected contributions.

    std_dev: MLB combined-game totals are a DIFFERENT, wider distribution
    than a single team's margin. UNFITTED CONSTANT: 5.6 runs, a separate,
    disclosed guess - not the margin model's 4.2, and not backtested.
    """
    if not team_a_stats or not team_b_stats:
        return None

    a_runs_allowed = blended_runs_allowed(
        team_a_stats["runs_allowed_pg"], team_a_recent, pitcher_a_form, bullpen_a, pitcher_a_fatigue)
    b_runs_allowed = blended_runs_allowed(
        team_b_stats["runs_allowed_pg"], team_b_recent, pitcher_b_form, bullpen_b, pitcher_b_fatigue)
    a_runs_scored = blended_runs_scored(team_a_stats["runs_scored_pg"], team_a_recent)
    b_runs_scored = blended_runs_scored(team_b_stats["runs_scored_pg"], team_b_recent)

    scoring_scale = park_scoring_scale(park_run_factor)
    a_runs_scored *= scoring_scale
    b_runs_scored *= scoring_scale
    a_runs_allowed *= scoring_scale
    b_runs_allowed *= scoring_scale

    # UNFITTED CONSTANT: simple average of the two signals (own scoring
    # rate vs opponent's allowing rate), not weighted.
    a_expected = (a_runs_scored + b_runs_allowed) / 2
    b_expected = (b_runs_scored + a_runs_allowed) / 2
    expected_total = a_expected + b_expected

    adj_std_dev = std_dev * park_scoring_scale(park_run_factor)  # same dampened widening as margin

    z = (expected_total - total_line) / adj_std_dev
    over_prob = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return {
        "line": total_line,
        "expected_total": round(expected_total, 2),
        "over_prob": round(over_prob, 3),
        "under_prob": round(1 - over_prob, 3),
    }


def build_total_runs_lines(expected_total, rungs=2, step=1.0):
    """
    Generates a plausible total-runs line centered on the model's own
    blended expected-total, with `rungs` above/below at `step` intervals -
    mirrors the rung-generation pattern used for pitcher K thresholds
    (_build_player_thresholds-style), adapted to runs, since this is a
    probability-only model with no live sportsbook odds feed to pull a
    real total line from. Lines are rounded to the nearest .5 (standard
    total-runs line convention).
    """
    if expected_total is None:
        return []
    center = round(expected_total * 2) / 2
    lines = []
    for i in range(-rungs, rungs + 1):
        lines.append(round(center + i * step, 1))
    return sorted(set(lines))


def yrfi_nrfi_prob(pitcher_a_form, pitcher_b_form, team_a_stats, team_b_stats,
                    park_run_factor=100, league_avg_era=4.20):
    """
    Estimate P(a run scores in the 1st inning by either team) - the
    "YRFI" (yes) market; NRFI is just 1 - this.

    Approach: treat each starter's runs-per-9-innings rate as a Poisson
    rate, scale it down to a single inning (divide by 9), and use the
    Poisson formula P(at least 1 run) = 1 - e^(-lambda) for each starter
    facing the opposing lineup in the top/bottom of the 1st. Combine the
    two independent half-innings: P(no run either half) = (1-p_a)(1-p_b),
    so P(YRFI) = 1 - (1-p_a)(1-p_b).

    lambda per starter blends his recent-start ERA (70%) with the
    opposing team's season run-scoring rate (30%) when both are
    available, so a soft-tossing starter facing a weak lineup gets pulled
    toward NRFI and vice versa. Falls back to league_avg_era if recent
    form is missing (e.g. early season / call-up with <3 starts sampled).

    This is a simplification - real first-inning scoring also depends on
    who's actually due up (leadoff hitters specifically), which this
    model doesn't have lineup-order data for yet. Treat as directional,
    same as the rest of this file's props.
    """
    def starter_first_inning_lambda(pitcher_form, opp_team_stats):
        era = league_avg_era
        if pitcher_form and pitcher_form.get("starts_sampled", 0) >= 3:
            era = pitcher_form["recent_era"]
        per_inning = era / 9
        if opp_team_stats and opp_team_stats.get("runs_scored_pg") is not None:
            opp_per_inning = opp_team_stats["runs_scored_pg"] / 9
            per_inning = per_inning * 0.7 + opp_per_inning * 0.3
        park_scale = park_run_factor / 100  # linear here - single inning, small effect either way
        return max(per_inning * park_scale, 0.01)

    lam_a = starter_first_inning_lambda(pitcher_a_form, team_b_stats)  # team A's starter faces team B's lineup
    lam_b = starter_first_inning_lambda(pitcher_b_form, team_a_stats)  # team B's starter faces team A's lineup

    p_a_scores = 1 - math.exp(-lam_a)
    p_b_scores = 1 - math.exp(-lam_b)
    p_yrfi = 1 - (1 - p_a_scores) * (1 - p_b_scores)
    return round(p_yrfi, 3)



# ---------- batter props ----------
# Section D: batter prop floors (hits, HR, RBI, total bases), opponent
# pitcher matchup context, home/away splits, recent-return-from-injury
# flag. Roughly doubles the fetch surface vs. pitcher-only (batters +
# pitchers instead of just pitchers) - one call per confirmed lineup
# player for game logs, so this only runs for lineups that are posted.

def get_confirmed_lineup_player_ids(game_pk, team_id):
    """
    Returns a list of {"id", "name", "bat_side"} for the confirmed starting
    lineup (battingOrder) of one team in one game, or [] if not posted yet.
    Reuses the same boxscore call pattern as get_confirmed_lineup_handedness.
    """
    data = get_safe(f"/game/{game_pk}/boxscore")
    if not data:
        return []
    teams = data.get("teams", {})
    side = None
    for key in ("home", "away"):
        t = teams.get(key, {})
        if t.get("team", {}).get("id") == team_id:
            side = t
            break
    if not side:
        return []
    batting_order_ids = side.get("battingOrder", [])
    if not batting_order_ids:
        return []
    players = side.get("players", {})
    out = []
    for pid in batting_order_ids:
        key = f"ID{pid}"
        player = players.get(key, {})
        person = player.get("person", {})
        out.append({
            "id": pid,
            "name": person.get("fullName", "Unknown"),
            "bat_side": player.get("batSide", {}).get("code"),
        })
    return out


def get_batter_recent_game_logs(batter_id, season=None, last_n=15):
    """
    Batter's last N game logs (hits, home runs, RBIs, total bases per
    game), used as the empirical base for prop floor probabilities - same
    pattern as get_pitcher_recent_strikeouts but for hitting stats.
    """
    if season is None:
        season = datetime.utcnow().year
    data = get_safe(f"/people/{batter_id}/stats", {
        "stats": "gameLog",
        "group": "hitting",
        "season": season
    })
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError, TypeError):
        return []
    games = []
    for s in splits[-last_n:]:
        stat = s.get("stat", {})
        try:
            games.append({
                "date": s.get("date"),
                "hits": int(stat.get("hits", 0)),
                "home_runs": int(stat.get("homeRuns", 0)),
                "rbi": int(stat.get("rbi", 0)),
                "total_bases": int(stat.get("totalBases", 0)),
                "is_home": s.get("isHome"),
            })
        except (TypeError, ValueError):
            continue
    return games


# A "0+" (or otherwise trivial) floor on a counting stat is meaningless as
# a bettable pick - almost every player clears it almost every game, so it
# would otherwise surface as a false "safe" pick. Minimum bettable
# threshold per stat, below which we don't report a floor at all.
MIN_BETTABLE_THRESHOLD = {
    "hits": 1,
    "home_runs": 1,
    "rbi": 1,
    "total_bases": 1,
}


def batter_prop_floor_probs(game_logs, thresholds=None):
    """
    Empirical probability of hitting each prop threshold, based on recent
    games - same style as strikeout_floor_probs. thresholds is a dict of
    {stat_key: [threshold values]}, defaults cover the common markets.
    Any threshold below MIN_BETTABLE_THRESHOLD for that stat is skipped -
    a "0+" floor is trivially true almost every game and isn't a real pick.
    """
    if thresholds is None:
        thresholds = {
            "hits": [1, 2],
            "home_runs": [1],
            "rbi": [1, 2],
            "total_bases": [1, 2, 3],
        }
    n = len(game_logs)
    if n == 0:
        return {}
    probs = {}
    for stat_key, t_list in thresholds.items():
        min_t = MIN_BETTABLE_THRESHOLD.get(stat_key, 1)
        probs[stat_key] = {}
        for t in t_list:
            if t < min_t:
                continue
            hits = sum(1 for g in game_logs if g.get(stat_key, 0) >= t)
            probs[stat_key][t] = round(hits / n, 3)
    return probs


def adjust_batter_floor_for_matchup(base_probs, matchup_context):
    """
    Nudges batter prop floor probabilities based on tonight's opposing
    starter's strikeout rate against this batter's handedness (from
    get_opponent_pitcher_matchup_context). A tough matchup pitcher (high
    K rate vs this handedness) should lower hit-prop floors; a weak
    matchup should raise them slightly. Same "small, disclosed, unfitted
    dampened multiplier" pattern as adjust_k_floor_for_opponent - not
    backtested, purely directional.

    Uses a league-average K-rate-vs-handedness baseline (roughly modern
    MLB norm) since get_opponent_pitcher_matchup_context returns a single
    pitcher's rate, not a comparison point - without a baseline there's
    nothing to compare "tough" or "weak" against.
    """
    if not base_probs or not matchup_context:
        return base_probs
    pitcher_k_rate = matchup_context.get("pitcher_k_rate_vs_this_handedness")
    if pitcher_k_rate is None:
        return base_probs
    league_avg_k_rate_vs_hand = 0.22  # UNFITTED CONSTANT - rough modern-MLB K-rate-per-PA baseline, not backtested
    factor = pitcher_k_rate / league_avg_k_rate_vs_hand
    # Dampened and inverted: a tougher-than-average matchup (factor > 1)
    # should PULL DOWN hit-prop floors, not up - opposite direction from
    # the K-prop adjustment, since more opponent K's is bad for a hitter.
    adj_factor = 1 - (factor - 1) * 0.3  # UNFITTED CONSTANT - dampened, disclosed, not backtested
    adjusted = {}
    for stat_key, thresholds in base_probs.items():
        adjusted[stat_key] = {}
        for t, prob in thresholds.items():
            new_prob = prob * adj_factor
            adjusted[stat_key][t] = round(max(0.0, min(1.0, new_prob)), 3)
    return adjusted


def batter_prop_thin_margin_flags(game_logs, floor_probs):
    """
    For each reported floor threshold, checks whether the batter usually
    clears it with room to spare or is barely scraping over it most
    games - same "thin margin" idea used for pitcher K props. A batter who
    hits exactly 1 hit in most of his qualifying games (not 2+) is a much
    less comfortable "1+ hits" pick than one who usually gets 2-3.
    Returns {stat_key: {threshold: bool_is_thin}}.

    "Thin" here means: among games where the batter cleared the threshold,
    the average amount by which he cleared it is small (<0.5 over the
    line) - a simple, explainable check, not a full distribution analysis.
    UNFITTED CONSTANT: 0.5 margin cutoff, a disclosed guess.
    """
    flags = {}
    if not game_logs or not floor_probs:
        return flags
    for stat_key, thresholds in floor_probs.items():
        flags[stat_key] = {}
        for t in thresholds:
            clearing_games = [g.get(stat_key, 0) for g in game_logs if g.get(stat_key, 0) >= t]
            if not clearing_games:
                flags[stat_key][t] = False
                continue
            avg_margin_over = sum(v - t for v in clearing_games) / len(clearing_games)
            flags[stat_key][t] = avg_margin_over < 0.5  # UNFITTED CONSTANT - see docstring
    return flags


def get_batter_home_away_split(game_logs):
    """
    Batter's hits-per-game at home vs. away, from the same recent game
    logs already fetched (no extra API call) - mirrors the home/away
    split feature already built for other markets.
    """
    home_games = [g for g in game_logs if g.get("is_home") is True]
    away_games = [g for g in game_logs if g.get("is_home") is False]
    if not home_games and not away_games:
        return None
    return {
        "home_games_sampled": len(home_games),
        "home_hits_per_game": round(sum(g["hits"] for g in home_games) / len(home_games), 2) if home_games else None,
        "away_games_sampled": len(away_games),
        "away_hits_per_game": round(sum(g["hits"] for g in away_games) / len(away_games), 2) if away_games else None,
    }


def get_opponent_pitcher_matchup_context(pitcher_id, batter_hand, season=None):
    """
    Opposing starter's K-rate against the batter's specific handedness -
    mirrors the platoon-split logic already built for pitcher-vs-lineup,
    just flipped to batter-vs-pitcher. Directly relevant to "will this
    batter get a hit" props: a pitcher who K's same-handed batters at a
    high rate is a real headwind for that specific batter's hit props.
    Returns None if handedness is unknown or the split sample is too small
    (reuses get_pitcher_k_rate_vs_hand's own >=20-batters-faced floor).
    """
    if not batter_hand or batter_hand not in ("L", "R", "S"):
        return None
    # Switch hitters bat opposite the pitcher's throwing hand by convention;
    # approximate with 'vr' (vs RHB) since most switch-hitter platoon data
    # isn't broken out further by this free API - disclosed approximation.
    sitcode = "vl" if batter_hand == "L" else "vr"
    k_rate = get_pitcher_k_rate_vs_hand(pitcher_id, sitcode, season)
    if k_rate is None:
        return None
    return {
        "sitcode": sitcode,
        "pitcher_k_rate_vs_this_handedness": round(k_rate, 3),
        "note": ("approximated using vs-RHB split (switch hitter)" if batter_hand == "S" else None),
    }


def check_batter_recent_il_activation(batter_id, before_date_str=TODAY, lookback_days=21):
    """
    Same heuristic as check_recent_il_activation but for batters: a gap in
    the batter's own game log consistent with an IL stint or extended
    absence ending recently. Batters play far more frequently than
    pitchers start, so a much shorter gap (5+ days with no games, vs. a
    pitcher's normal 4-6 day rest cycle) is the meaningful signal here.
    Always surfaced as "verify before trusting" - can false-positive on
    a scheduled off day, a bench day, or a callup/demotion.
    """
    data = get_safe(f"/people/{batter_id}/stats", {
        "stats": "gameLog",
        "group": "hitting",
        "season": datetime.utcnow().year,
    })
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError, TypeError):
        return None
    dates = sorted(s.get("date") for s in splits if s.get("date"))
    if len(dates) < 2:
        return None
    try:
        today_dt = datetime.strptime(before_date_str, "%Y-%m-%d")
        last_dt = datetime.strptime(dates[-1], "%Y-%m-%d")
    except ValueError:
        return None
    days_since_last = (today_dt - last_dt).days
    if days_since_last > lookback_days:
        return None
    prev_dt = datetime.strptime(dates[-2], "%Y-%m-%d")
    gap = (last_dt - prev_dt).days
    if gap >= 10:  # meaningfully longer than a normal 1-3 day gap between games played
        return {
            "flag": True,
            "days_gap_before_return": gap,
            "note": (f"gap of {gap} days between games played, ending {dates[-1]} - "
                     f"consistent with an IL stint or extended absence. Verify actual "
                     f"injury/roster status before trusting this in a bet."),
        }
    return {"flag": False}


def build_batter_props_for_game(game, opp_pitcher_id_by_side):
    """
    Builds batter prop entries for both confirmed lineups in a game.
    Returns [] for a side if its lineup isn't posted yet (honest
    unavailability, same pattern as the pitcher-vs-lineup matchup read).
    """
    results = []
    for side, team_id, opp_side in (("away", game["away_team_id"], "home"),
                                     ("home", game["home_team_id"], "away")):
        lineup = get_confirmed_lineup_player_ids(game["gamePk"], team_id)
        if not lineup:
            continue
        opp_pitcher_id = opp_pitcher_id_by_side.get(opp_side)
        for player in lineup:
            logs = get_batter_recent_game_logs(player["id"])
            if not logs:
                continue
            raw_floors = batter_prop_floor_probs(logs)
            splits = get_batter_home_away_split(logs)
            matchup = (get_opponent_pitcher_matchup_context(opp_pitcher_id, player["bat_side"])
                       if opp_pitcher_id else None)
            # Actually apply the matchup adjustment - previously fetched
            # and stored but never used to move the floor probabilities.
            floors = adjust_batter_floor_for_matchup(raw_floors, matchup)
            thin_margin_flags = batter_prop_thin_margin_flags(logs, floors)
            il_check = check_batter_recent_il_activation(player["id"])
            results.append({
                "name": player["name"],
                "side": side,
                "bat_side": player["bat_side"],
                "games_sampled": len(logs),
                "floor_probabilities_raw": raw_floors,
                "floor_probabilities": floors,
                "thin_margin_flags": thin_margin_flags,
                "home_away_split": splits,
                "opponent_pitcher_matchup": matchup,
                "il_check": il_check,
            })
    return results


# ---------- main ----------

def build_report():
    games = get_todays_games()
    odds_events = get_mlb_odds()

    # Compute a live league-average K/game across today's participating teams,
    # so the opponent adjustment is relative to current-season reality rather
    # than a hardcoded guess.
    team_k_cache = {}
    team_run_stats_cache = {}
    team_k_recent_cache = {}
    team_run_recent_cache = {}
    team_bullpen_cache = {}
    for g in games:
        for tid in (g["away_team_id"], g["home_team_id"]):
            if tid not in team_k_cache:
                team_k_cache[tid] = get_team_k_rate(tid)
            if tid not in team_run_stats_cache:
                team_run_stats_cache[tid] = get_team_run_stats(tid)
            if tid not in team_run_recent_cache:
                team_run_recent_cache[tid] = get_team_recent_run_trend(tid)
            if tid not in team_bullpen_cache:
                team_bullpen_cache[tid] = get_bullpen_recent_form(tid)
            # Recent opponent K-rate trend is more expensive (one boxscore
            # call per recent game), so only fetch it for teams actually
            # appearing as an OPPONENT of a probable starter today - handled
            # lazily below via team_k_recent_cache instead of pre-fetching
            # for every team here.
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
            "spread_lines": [],
            "moneyline": None
        }

        # Market odds for this game, if available today. Matched by team
        # nickname; absent entirely (not zero/guessed) if the book hasn't
        # posted lines yet or the odds fetch failed.
        odds_event = match_odds_event(odds_events, g["home_team_short"], g["away_team_short"])
        market = get_market_lines_for_event(
            odds_event, odds_event.get("home_team"), odds_event.get("away_team")
        ) if odds_event else {}
        entry["market"] = market

        for side, pid, pname, opp_id, opp_name in [
            ("away", g["away_pitcher_id"], g["away_pitcher"], g["home_team_id"], g["home_team_short"]),
            ("home", g["home_pitcher_id"], g["home_pitcher"], g["away_team_id"], g["away_team_short"]),
        ]:
            if not pid:
                continue
            start_gamelogs = get_pitcher_start_gamelogs(pid)
            k_list = [g["strikeouts"] for g in start_gamelogs]
            base_probs = strikeout_floor_probs(k_list)
            k_per_ip = get_pitcher_k_per_ip(pid)
            consistency = strikeout_consistency_signal(start_gamelogs)

            # Opponent K tendency: prefer the RECENT (last-~12-game) trend
            # over the season-long rate when we have it, since a lineup's
            # current form matters more than its full-season number.
            if opp_id not in team_k_recent_cache:
                team_k_recent_cache[opp_id] = get_team_k_rate_recent(opp_id)
            opp_k_rate_recent = team_k_recent_cache.get(opp_id)
            opp_k_rate_season = team_k_cache.get(opp_id)
            opp_k_rate = opp_k_rate_recent if opp_k_rate_recent else opp_k_rate_season
            opp_k_source = "recent (~12 games)" if opp_k_rate_recent else "season" if opp_k_rate_season else None
            opp_k_league_rank = rank_team_k_rate(opp_id, team_k_cache)

            adjusted_probs = adjust_k_floor_for_opponent(base_probs, opp_k_rate, league_avg_k)
            platoon = get_pitcher_platoon_splits(pid)
            fatigue = assess_pitcher_fatigue(pid)
            il_check = check_recent_il_activation(pid)

            # Park SO factor: a further mild adjustment (e.g. Coors
            # suppresses K's, Mariners' park inflates them). Dampened the
            # same way as the opponent adjustment. UNFITTED CONSTANT (0.5),
            # same honesty caveat as adjust_k_floor_for_opponent - directional
            # guess, not backtested against settled outcomes.
            park_so_factor = park["SO"] if park else 100
            park_scale = 1 + ((park_so_factor / 100) - 1) * 0.5
            park_adjusted_probs = {
                t: round(max(0.0, min(1.0, p * park_scale)), 3)
                for t, p in adjusted_probs.items()
            }

            # Weather: wind suppresses offense broadly, and can modestly
            # affect K rate too (batters more tentative in poor conditions).
            # Small, disclosed, unfitted - same caveat as everything else.
            weather = get_game_weather(g["home_team_id"])
            weather_desc = describe_weather_effect(weather)
            if weather and weather.get("wind_mph") and weather["wind_mph"] >= 15:
                park_adjusted_probs = {
                    t: round(max(0.0, min(1.0, p * 1.03)), 3) for t, p in park_adjusted_probs.items()
                }

            # A fatigue flag (short rest or declining innings) nudges K-floors
            # down slightly. UNFITTED CONSTANT (0.92) - directional, not fitted.
            if fatigue and fatigue["is_fatigue_flag"]:
                park_adjusted_probs = {
                    t: round(max(0.0, p * 0.92), 3) for t, p in park_adjusted_probs.items()
                }

            # Sanity-check today's K floor against a projected innings count
            # (reuse the innings trend already used for fatigue, rather than
            # inventing a new innings-projection source) - if he's likely
            # to go shorter today than the innings his K floor was built
            # from, discount the floor.
            projected_innings = None
            if fatigue and fatigue.get("innings_trend"):
                projected_innings = round(sum(fatigue["innings_trend"]) / len(fatigue["innings_trend"]), 2)
            park_adjusted_probs = discount_k_floor_for_projected_innings(
                park_adjusted_probs, k_per_ip, projected_innings)

            # Strikeout consistency: small dampening on the floor itself,
            # plus a plain-English flag surfaced separately below (not just
            # silently folded into the number).
            park_adjusted_probs = dampen_k_floor_for_inconsistency(park_adjusted_probs, consistency)

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
                "opponent_k_source": opp_k_source,
                "opponent_k_league_rank": opp_k_league_rank,
                "league_avg_k_per_game": round(league_avg_k, 2),
                "park_so_factor": park_so_factor,
                "weather": weather,
                "weather_description": weather_desc,
                "platoon": platoon,
                "fatigue": fatigue,
                "il_check": il_check,
                "lineup_matchup": lineup_matchup,
                "k_per_ip": k_per_ip,
                "projected_innings": projected_innings,
                "strikeout_consistency": consistency,
            })

        away_stats = team_run_stats_cache.get(g["away_team_id"])
        home_stats = team_run_stats_cache.get(g["home_team_id"])

        # Pull each side's probable starter's recent-start form so the
        # spread model reacts to who's actually pitching today, not just
        # each team's full-season pitching average.
        away_pitcher_form = get_pitcher_recent_form(g["away_pitcher_id"]) if g["away_pitcher_id"] else None
        home_pitcher_form = get_pitcher_recent_form(g["home_pitcher_id"]) if g["home_pitcher_id"] else None

        away_recent = team_run_recent_cache.get(g["away_team_id"])
        home_recent = team_run_recent_cache.get(g["home_team_id"])
        away_bullpen = team_bullpen_cache.get(g["away_team_id"])
        home_bullpen = team_bullpen_cache.get(g["home_team_id"])
        game_weather = get_game_weather(g["home_team_id"])

        # Reuse fatigue already computed in the pitcher loop above, rather
        # than calling assess_pitcher_fatigue a second time.
        away_pitcher_fatigue = next((p["fatigue"] for p in entry["pitchers"] if p["side"] == "away"), None)
        home_pitcher_fatigue = next((p["fatigue"] for p in entry["pitchers"] if p["side"] == "home"), None)

        # Test the model's default lines PLUS whatever spread point(s) the
        # book actually posted (from the away side's perspective, i.e. the
        # negation of the home-team point on the market board) - same
        # reasoning as the totals fix above: edge detection needs a model
        # number at the SAME point the market is offering.
        spread_points_to_test = {-1.5, 1.5, 2.5}
        for market_spread in entry.get("market", {}).get("spreads", []):
            spread_points_to_test.add(-market_spread["point"])  # away-perspective point
        for spread in sorted(spread_points_to_test):
            p_away = spread_cover_prob(
                away_stats, home_stats, spread, park_run_factor=park_r_factor,
                pitcher_a_form=away_pitcher_form, pitcher_b_form=home_pitcher_form,
                pitcher_a_fatigue=away_pitcher_fatigue, pitcher_b_fatigue=home_pitcher_fatigue,
                team_a_recent=away_recent, team_b_recent=home_recent,
                bullpen_a=away_bullpen, bullpen_b=home_bullpen, weather_a=game_weather,
            )
            p_home = spread_cover_prob(
                home_stats, away_stats, -spread, park_run_factor=park_r_factor,
                pitcher_a_form=home_pitcher_form, pitcher_b_form=away_pitcher_form,
                pitcher_a_fatigue=home_pitcher_fatigue, pitcher_b_fatigue=away_pitcher_fatigue,
                team_a_recent=home_recent, team_b_recent=away_recent,
                bullpen_a=home_bullpen, bullpen_b=away_bullpen, weather_a=game_weather,
            )
            # "spread" here is always the AWAY team's perspective point (e.g.
            # away +1.5 means home -1.5). home_cover_prob is computed at the
            # negated point (-spread) since spread_cover_prob's `spread` arg
            # is from team_a's perspective and team_a=home in that call.
            entry["spread_lines"].append({
                "spread": spread,
                "away_cover_prob": p_away,
                "home_cover_prob": p_home
            })

        # Moneyline (straight-up win prob): same run-differential model,
        # just evaluated at spread=0 instead of a run line. Same disclosed,
        # unfitted-weights caveat as the spread model above applies here too.
        ml_away = spread_cover_prob(
            away_stats, home_stats, 0, park_run_factor=park_r_factor,
            pitcher_a_form=away_pitcher_form, pitcher_b_form=home_pitcher_form,
            pitcher_a_fatigue=away_pitcher_fatigue, pitcher_b_fatigue=home_pitcher_fatigue,
            team_a_recent=away_recent, team_b_recent=home_recent,
            bullpen_a=away_bullpen, bullpen_b=home_bullpen, weather_a=game_weather,
        )
        ml_home = spread_cover_prob(
            home_stats, away_stats, 0, park_run_factor=park_r_factor,
            pitcher_a_form=home_pitcher_form, pitcher_b_form=away_pitcher_form,
            pitcher_a_fatigue=home_pitcher_fatigue, pitcher_b_fatigue=away_pitcher_fatigue,
            team_a_recent=home_recent, team_b_recent=away_recent,
            bullpen_a=home_bullpen, bullpen_b=away_bullpen, weather_a=game_weather,
        )
        entry["moneyline"] = {"away_win_prob": ml_away, "home_win_prob": ml_home}

        # Total Runs (Over/Under): reuses the same blended inputs as the
        # spread model (season + recent + starter + bullpen), with the same
        # park-factor-shifts-scoring fix applied. No live sportsbook odds
        # feed exists here, so the line(s) tested are generated centered on
        # the model's own blended expected-total, mirroring how K
        # thresholds are generated around a pitcher's own average.
        total_probe = total_runs_prob(
            away_stats, home_stats, total_line=8.5, park_run_factor=park_r_factor,
            pitcher_a_form=away_pitcher_form, pitcher_b_form=home_pitcher_form,
            pitcher_a_fatigue=away_pitcher_fatigue, pitcher_b_fatigue=home_pitcher_fatigue,
            team_a_recent=away_recent, team_b_recent=home_recent,
            bullpen_a=away_bullpen, bullpen_b=home_bullpen,
        )
        total_runs_lines = []
        if total_probe:
            # Test the model's own centered lines PLUS whatever line(s) the
            # book actually posted today - the latter is what matters for
            # edge detection (extract_top_picks only matches a model line
            # against a market line at the SAME point), so if the book's
            # posted total isn't one of the model's default guesses, it
            # would never be checked against the market without this.
            lines_to_test = set(build_total_runs_lines(total_probe["expected_total"]))
            for market_total in entry.get("market", {}).get("totals", []):
                lines_to_test.add(market_total["point"])
            for line in sorted(lines_to_test):
                result = total_runs_prob(
                    away_stats, home_stats, total_line=line, park_run_factor=park_r_factor,
                    pitcher_a_form=away_pitcher_form, pitcher_b_form=home_pitcher_form,
                    pitcher_a_fatigue=away_pitcher_fatigue, pitcher_b_fatigue=home_pitcher_fatigue,
                    team_a_recent=away_recent, team_b_recent=home_recent,
                    bullpen_a=away_bullpen, bullpen_b=home_bullpen,
                )
                if result:
                    total_runs_lines.append(result)
        entry["total_runs"] = total_runs_lines

        # YRFI/NRFI: independent of the spread model above (single-inning
        # Poisson approach, not the full-game normal approximation), using
        # the same starter-form and team-offense inputs already fetched.
        p_yrfi = yrfi_nrfi_prob(
            away_pitcher_form, home_pitcher_form, away_stats, home_stats,
            park_run_factor=park_r_factor,
        )
        entry["yrfi_nrfi"] = {
            "yrfi_prob": p_yrfi,
            "nrfi_prob": round(1 - p_yrfi, 3) if p_yrfi is not None else None,
        } if p_yrfi is not None else None


        entry["away_pitcher_form"] = away_pitcher_form
        entry["home_pitcher_form"] = home_pitcher_form
        entry["away_recent_trend"] = away_recent
        entry["home_recent_trend"] = home_recent
        entry["away_bullpen"] = away_bullpen
        entry["home_bullpen"] = home_bullpen
        entry["weather"] = game_weather
        entry["weather_description"] = describe_weather_effect(game_weather)

        report.append(entry)
    return report


def _ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


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


def _render_empty_state():
    """
    Shown when zero games were found for today - e.g. the All-Star break,
    or a genuine off day. Distinguishes "nothing scheduled" from "something
    broke" so a blank page doesn't read as a bug.
    """
    return """
    <div class="empty-state">
      <p class="empty-state-title">No MLB games today.</p>
      <p class="empty-state-sub">Could be a scheduled off day (e.g. the All-Star break) or the season
      hasn't started/has ended. If you expect games today, check MLB.com's schedule directly -
      this could also mean the schedule fetch failed silently.</p>
    </div>"""


MIN_EDGE_POINTS = 5.0   # minimum model-vs-market edge (percentage points) to surface a pick
TOP_PICKS_LIMIT = 20    # cap on total picks shown, not games


def extract_top_picks(report, min_edge=MIN_EDGE_POINTS, limit=TOP_PICKS_LIMIT):
    """
    Scans every game for spread and total lines where BOTH a model
    probability AND a real de-vigged market probability exist, and keeps
    only the ones where the model beats the market by at least `min_edge`
    percentage points. This replaces the old "model confidence alone"
    approach entirely - a bare model probability with nothing to compare
    it against is not surfaced here at all, no matter how high it is.

    No player props, no bet builders, no moneyline/YRFI - spread and
    total only, per the decision to focus exclusively on markets where a
    real, checkable market price exists via the free odds feed.

    Each pick includes the fair decimal odds implied by BOTH the model's
    probability and the market's probability, so the gap is visible at a
    glance and directly usable for staking.
    """
    picks = []

    for g in report:
        matchup = f'{g["away_team"]} @ {g["home_team"]}'
        market = g.get("market") or {}

        # --- spread ---
        market_spreads = {s["point"]: s for s in market.get("spreads", [])}
        for s in g.get("spread_lines", []):
            away_point = s["spread"]  # s["spread"] is always the AWAY team's perspective point
            # market_spreads is keyed by the HOME team's book point, so the
            # away point must be negated to look up home's market line, and
            # matched directly (no negation) to look up away's market line.
            home_market = market_spreads.get(-away_point)
            away_market = market_spreads.get(away_point)
            for side_label, model_prob, market_entry, market_prob_key, market_dec_key, line_point in (
                (g["home_team"], s.get("home_cover_prob"), home_market, "home_prob", "home_decimal", -away_point),
                (g["away_team"], s.get("away_cover_prob"), away_market, "away_prob", "away_decimal", away_point),
            ):
                if model_prob is None or not market_entry:
                    continue
                market_prob = market_entry.get(market_prob_key)
                market_decimal = market_entry.get(market_dec_key)
                edge = calc_edge(model_prob, market_prob)
                # Sanity backstop, not a fix: a real MLB run-line point is
                # essentially always within ±3.5, and a legitimate model
                # probability on a spread this close almost never saturates
                # to near-certain. Values outside these bounds indicate a
                # matching/unit bug upstream (log and skip, don't display).
                if abs(line_point) > 3.5:
                    print(f"BUG SIGNAL: skipping spread pick with implausible point {line_point} ({matchup})")
                    continue
                if model_prob >= 0.97 or model_prob <= 0.03:
                    print(f"BUG SIGNAL: skipping spread pick with implausible model_prob {model_prob} ({matchup})")
                    continue
                if edge is not None and edge >= min_edge:
                    picks.append({
                        "matchup": matchup,
                        "type": "Spread",
                        "side": side_label,
                        "line_label": f'{side_label} {line_point:+}',
                        "model_prob": model_prob,
                        "market_prob": market_prob,
                        "model_decimal": prob_to_decimal_odds(model_prob),
                        "market_decimal": market_decimal,
                        "edge_points": edge,
                    })

        # --- total ---
        market_totals = {t["point"]: t for t in market.get("totals", [])}
        for tr in g.get("total_runs", []):
            line = tr.get("line")
            market_entry = market_totals.get(line)
            if not market_entry:
                continue
            for side_label, model_prob, market_prob_key, market_dec_key in (
                ("Over", tr.get("over_prob"), "over_prob", "over_decimal"),
                ("Under", tr.get("under_prob"), "under_prob", "under_decimal"),
            ):
                if model_prob is None:
                    continue
                market_prob = market_entry.get(market_prob_key)
                market_decimal = market_entry.get(market_dec_key)
                edge = calc_edge(model_prob, market_prob)
                # Same sanity backstop as spreads: real MLB totals run
                # roughly 6-13, and a legitimate total-line probability
                # shouldn't saturate near-certain either.
                if not (6 <= line <= 13):
                    print(f"BUG SIGNAL: skipping total pick with implausible line {line} ({matchup})")
                    continue
                if model_prob >= 0.97 or model_prob <= 0.03:
                    print(f"BUG SIGNAL: skipping total pick with implausible model_prob {model_prob} ({matchup})")
                    continue
                if edge is not None and edge >= min_edge:
                    picks.append({
                        "matchup": matchup,
                        "type": "Total",
                        "side": side_label,
                        "line_label": f'{side_label} {line}',
                        "model_prob": model_prob,
                        "market_prob": market_prob,
                        "model_decimal": prob_to_decimal_odds(model_prob),
                        "market_decimal": market_decimal,
                        "edge_points": edge,
                    })

    picks.sort(key=lambda x: x["edge_points"], reverse=True)
    return picks[:limit]


def _render_top_picks(picks, market_data_available):
    """
    Renders the picks section: every entry here has a real sportsbook
    price behind it and a model probability that beats it by at least
    MIN_EDGE_POINTS. No confidence-only picks, no props, no parlays.
    """
    if not market_data_available:
        return """
    <section class="top-picks">
      <h2 class="top-picks-title">today's picks</h2>
      <p class="top-picks-sub">No market odds data available today - either the ODDS_API_KEY isn't set, or the odds fetch failed. Without a real sportsbook price to compare against, no picks can be shown; a bare model number isn't a pick.</p>
    </section>"""

    if not picks:
        return """
    <section class="top-picks">
      <h2 class="top-picks-title">today's picks</h2>
      <p class="top-picks-sub">No spread or total today cleared the minimum model-vs-market edge. That's a normal, honest outcome - it means the books' prices already line up closely with the model's own numbers, so there's no real edge to bet. No picks is a valid result, not a bug.</p>
    </section>"""

    rows = []
    for pk in picks:
        rows.append(f"""
      <div class="pick-card">
        <div class="pick-card-top">
          <span class="pick-type">{pk["type"]}</span>
          <span class="pick-prob">+{pk["edge_points"]:.1f} pts edge</span>
        </div>
        <p class="pick-player">{pk["matchup"]}</p>
        <p class="pick-line">{pk["line_label"]}</p>
        <div class="odds-compare">
          <div class="odds-col">
            <span class="odds-col-label">model</span>
            <span class="odds-col-value">{pk["model_decimal"]}</span>
            <span class="odds-col-sub">{pk["model_prob"]*100:.1f}%</span>
          </div>
          <div class="odds-col">
            <span class="odds-col-label">market</span>
            <span class="odds-col-value">{pk["market_decimal"]}</span>
            <span class="odds-col-sub">{pk["market_prob"]*100:.1f}%</span>
          </div>
        </div>
      </div>""")

    return f"""
    <section class="top-picks">
      <h2 class="top-picks-title">today's picks</h2>
      <div class="pick-grid">
        {''.join(rows)}
      </div>
    </section>"""


def render_html(report):
    market_data_available = any(g.get("market") for g in report)
    top_picks = extract_top_picks(report)
    top_picks_html = _render_top_picks(top_picks, market_data_available)
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

        total_runs = g.get("total_runs") or []
        if total_runs:
            block.append('<h3 class="section-label">Total Runs (Over/Under)</h3>')
            block.append('<div class="spread-block">')
            for tr in total_runs:
                block.append('<div class="spread-row-group">')
                block.append(f'<span class="spread-num">{tr["line"]}</span>')
                block.append(_prob_bar(f'Over {tr["line"]}', tr["over_prob"], "var(--teal)"))
                block.append(_prob_bar(f'Under {tr["line"]}', tr["under_prob"], "var(--orange)"))
                block.append('</div>')
            block.append('</div>')

        block.append('<ul class="why-list">')
        for label, recent, bullpen, form in (
            (g["away_team"], g.get("away_recent_trend"), g.get("away_bullpen"), g.get("away_pitcher_form")),
            (g["home_team"], g.get("home_recent_trend"), g.get("home_bullpen"), g.get("home_pitcher_form")),
        ):
            if recent:
                block.append(f'<li>{label} lately: scoring {recent["runs_scored_pg"]} runs and giving up '
                             f'{recent["runs_allowed_pg"]} per game over their last {recent["games_sampled"]} games</li>')
            else:
                block.append(f'<li class="vs-opp-empty">{label} recent form not available - using season averages instead</li>')
            if form:
                block.append(f'<li>{label}\'s starting pitcher has allowed {form["recent_era"]} runs per 9 innings '
                             f'in his last {form["starts_sampled"]} starts</li>')
            if bullpen:
                block.append(f'<li>{label}\'s pitching staff (starters + relievers) is allowing '
                             f'{bullpen["staff_era"]} runs per 9 innings on the season</li>')
        if g.get("weather_description"):
            block.append(f'<li>{g["weather_description"]}</li>')
        block.append('</ul>')

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
  --card-border: #2A3752;
  --orange: #E8630A;
  --teal: #2DD4BF;
  --amber: #F5A623;
  --text: #F7F8FA;
  --text-dim: #AEB8CC;
  --h1-accent: #ffb35c;
  --disclaimer-text: #E39A9A;
  --disclaimer-bg: rgba(232, 99, 10, 0.08);
  --disclaimer-border: rgba(232, 99, 10, 0.2);
  --flag-bg: rgba(245, 166, 35, 0.12);
  --flag-border: rgba(245, 166, 35, 0.35);
  --row-tint: rgba(255,255,255,0.02);
  --track-bg: rgba(255,255,255,0.08);
  --pill-hot-bg: rgba(45, 212, 191, 0.16);
  --pill-hot-text: #5eead4;
  --pill-hot-border: rgba(45, 212, 191, 0.4);
  --pill-warm-bg: rgba(232, 99, 10, 0.16);
  --pill-warm-text: #ffab6b;
  --pill-warm-border: rgba(232, 99, 10, 0.4);
  --pill-cool-bg: rgba(255,255,255,0.04);
  --pill-cool-text: #9AA5BC;
  --pill-cool-border: rgba(255,255,255,0.10);
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
.pbar-row {{ display: flex; align-items: center; gap: 10px; margin: 10px 0; }}
.pbar-label {{ width: 84px; font-size: 0.78em; color: var(--text-dim); font-weight: 600; flex-shrink: 0; line-height: 1.25; }}
.pbar-track {{ flex: 1; height: 8px; background: var(--track-bg); border-radius: 4px; overflow: hidden; min-width: 0; }}
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
.why-list {{
  margin: 8px 20px 4px;
  padding: 0 0 0 18px;
  list-style: disc;
  color: var(--text-dim);
  font-size: 0.78em;
  line-height: 1.6;
}}
.why-list li {{ margin: 2px 0; }}
.why-list li.vs-opp-empty {{ list-style: none; margin-left: -18px; font-style: italic; }}
.empty-state {{
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  padding: 28px 22px;
  text-align: center;
}}
.empty-state-title {{ font-size: 1.15em; font-weight: 700; color: var(--text); margin: 0 0 8px; }}
.empty-state-sub {{ color: var(--text-dim); font-size: 0.85em; line-height: 1.6; margin: 0; }}
.top-picks {{
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  padding: 20px 18px;
  margin-bottom: 22px;
}}
.top-picks-title {{ font-size: 1.1em; font-weight: 800; margin: 0 0 4px; color: var(--text); }}
.top-picks-sub {{ font-size: 0.78em; color: var(--text-dim); line-height: 1.5; margin: 0 0 14px; }}
.pick-grid {{ display: flex; flex-direction: column; gap: 10px; }}
.bed-builder-group {{ margin-bottom: 20px; }}
.bed-builder-group:last-child {{ margin-bottom: 0; }}
.bed-builder-label {{
  font-size: 0.85em;
  font-weight: 700;
  text-transform: lowercase;
  color: var(--teal);
  margin: 0 0 10px;
}}
.pick-card {{
  background: var(--track-bg);
  border: 1px solid var(--card-border);
  border-radius: 10px;
  padding: 12px 14px;
}}
.pick-card-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
.pick-type {{
  font-size: 0.68em;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-dim);
}}
.pick-prob {{ font-size: 1.1em; font-weight: 800; color: var(--teal); }}
.pick-player {{ font-size: 0.98em; font-weight: 700; color: var(--text); margin: 0 0 2px; }}
.pick-line {{ font-size: 0.88em; font-weight: 600; color: var(--orange); margin: 0 0 2px; }}
.pick-context {{ font-size: 0.75em; color: var(--text-dim); margin: 0; }}
.pick-reasons {{
  margin: 8px 0 0;
  padding: 0 0 0 16px;
  list-style: disc;
  font-size: 0.75em;
  color: var(--text-dim);
  line-height: 1.5;
}}
.pick-reasons li {{ margin: 2px 0; }}
.odds-compare {{ display: flex; gap: 10px; margin-top: 8px; }}
.odds-col {{
  flex: 1; background: var(--card-bg, rgba(255,255,255,0.03)); border-radius: 8px;
  padding: 8px 10px; display: flex; flex-direction: column; align-items: center;
}}
.odds-col-label {{ font-size: 0.65em; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim); font-weight: 700; }}
.odds-col-value {{ font-size: 1.3em; font-weight: 800; color: var(--text); margin-top: 2px; }}
.odds-col-sub {{ font-size: 0.7em; color: var(--text-dim); margin-top: 1px; }}
.section-divider {{ font-size: 1em; font-weight: 700; color: var(--text-dim); margin: 24px 20px 10px; text-transform: lowercase; }}

.tab-nav {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  padding: 0 20px;
  margin: 18px 0 4px;
}}
.tab-card {{
  background: var(--card, #131B2E);
  border: 1px solid var(--card-border, rgba(255,255,255,0.08));
  border-radius: 12px;
  padding: 14px 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 4px;
  cursor: pointer;
  font-family: inherit;
  color: var(--text, #F7F8FA);
}}
.tab-card-title {{
  font-size: 0.95em;
  font-weight: 800;
}}
.tab-card-sub {{
  font-size: 0.68em;
  color: var(--text-dim, #AEB8CC);
  line-height: 1.3;
}}
.tab-card.active {{
  border-color: var(--teal, #2DD4BF);
  background: rgba(45, 212, 191, 0.08);
}}
.tab-card.active .tab-card-title {{ color: var(--teal, #2DD4BF); }}
.tab-panel {{ display: none; }}
.tab-panel.active {{ display: block; }}
</style>
</head>
<body>
<h1>MLB Daily Probabilities</h1>
<p class="updated">Generated {datetime.utcnow().strftime('%d %b %y %H:%M UTC')}</p>
{top_picks_html}

<h2 class="section-divider">All games: spread &amp; total detail</h2>
{_render_empty_state() if not cards else ''.join(cards)}

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
