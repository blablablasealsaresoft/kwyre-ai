"""
Tool router: augments LLM queries with real-time data from free public APIs.
No API keys needed -- every integration here is free and unauthenticated.
"""

import re
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

TIMEOUT = 5


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "KwyreAI/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "KwyreAI/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. Weather — Open-Meteo (open-meteo.com) + geocoding
# ---------------------------------------------------------------------------

def get_weather(city):
    geo = _get(f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1")
    if not geo or not geo.get("results"):
        return None
    loc = geo["results"][0]
    lat, lon = loc["latitude"], loc["longitude"]
    name = loc.get("name", city)
    country = loc.get("country", "")

    wx = _get(
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code"
        f"&timezone=auto&forecast_days=3"
    )
    if not wx:
        return None

    cur = wx.get("current", {})
    daily = wx.get("daily", {})

    wmo = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
           45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle",
           55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
           71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Rain showers",
           81: "Heavy rain showers", 85: "Snow showers", 95: "Thunderstorm",
           96: "Thunderstorm + hail"}

    code = cur.get("weather_code", 0)
    desc = wmo.get(code, f"Code {code}")

    forecast_lines = []
    for i in range(min(3, len(daily.get("time", [])))):
        d = daily["time"][i]
        hi = daily["temperature_2m_max"][i]
        lo = daily["temperature_2m_min"][i]
        fc = wmo.get(daily["weather_code"][i], "?")
        rain = daily["precipitation_sum"][i]
        forecast_lines.append(f"  {d}: {lo}°C – {hi}°C, {fc}, precip {rain}mm")

    return (
        f"Weather for {name}, {country} (live data):\n"
        f"  Now: {cur.get('temperature_2m')}°C, {desc}, "
        f"humidity {cur.get('relative_humidity_2m')}%, "
        f"wind {cur.get('wind_speed_10m')} km/h\n"
        f"3-day forecast:\n" + "\n".join(forecast_lines)
    )


# ---------------------------------------------------------------------------
# 2. Cryptocurrency — CoinGecko (free, no key)
# ---------------------------------------------------------------------------

def get_crypto(coin):
    slug = coin.lower().strip()
    aliases = {
        "btc": "bitcoin", "eth": "ethereum", "sol": "solana",
        "doge": "dogecoin", "xrp": "ripple", "ada": "cardano",
        "dot": "polkadot", "matic": "polygon", "avax": "avalanche-2",
        "link": "chainlink", "bnb": "binancecoin", "shib": "shiba-inu",
    }
    slug = aliases.get(slug, slug)
    data = _get(f"https://api.coingecko.com/api/v3/coins/{slug}?"
                f"localization=false&tickers=false&community_data=false&developer_data=false")
    if not data or "market_data" not in data:
        return None

    md = data["market_data"]
    return (
        f"Crypto data for {data['name']} ({data['symbol'].upper()}) — live:\n"
        f"  Price: ${md['current_price'].get('usd', '?'):,.2f}\n"
        f"  24h change: {md.get('price_change_percentage_24h', 0):.2f}%\n"
        f"  Market cap: ${md['market_cap'].get('usd', 0):,.0f}\n"
        f"  24h volume: ${md['total_volume'].get('usd', 0):,.0f}\n"
        f"  ATH: ${md['ath'].get('usd', 0):,.2f}\n"
        f"  Rank: #{data.get('market_cap_rank', '?')}"
    )


# ---------------------------------------------------------------------------
# 3. News — HackerNews top stories
# ---------------------------------------------------------------------------

def get_hackernews():
    ids = _get("https://hacker-news.firebaseio.com/v0/topstories.json")
    if not ids:
        return None
    stories = []
    for sid in ids[:8]:
        s = _get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
        if s and s.get("title"):
            stories.append(f"  - {s['title']} ({s.get('score', 0)} pts, {s.get('descendants', 0)} comments)")
    if not stories:
        return None
    return "Top Hacker News stories right now:\n" + "\n".join(stories)


# ---------------------------------------------------------------------------
# 4. Dictionary — Free Dictionary API
# ---------------------------------------------------------------------------

def get_definition(word):
    data = _get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}")
    if not data or not isinstance(data, list):
        return None
    entry = data[0]
    lines = [f"Definition of \"{entry.get('word', word)}\":"]
    phonetic = entry.get("phonetic", "")
    if phonetic:
        lines.append(f"  Pronunciation: {phonetic}")
    for meaning in entry.get("meanings", [])[:3]:
        pos = meaning.get("partOfSpeech", "")
        for defn in meaning.get("definitions", [])[:2]:
            lines.append(f"  [{pos}] {defn['definition']}")
            if defn.get("example"):
                lines.append(f"    Example: \"{defn['example']}\"")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5. Country info — REST Countries
# ---------------------------------------------------------------------------

def get_country(name):
    data = _get(f"https://restcountries.com/v3.1/name/{urllib.parse.quote(name)}?fields=name,capital,population,region,subregion,currencies,languages,timezones,flags")
    if not data or not isinstance(data, list):
        return None
    c = data[0]
    cname = c.get("name", {}).get("common", name)
    cap = ", ".join(c.get("capital", ["N/A"]))
    pop = c.get("population", 0)
    reg = c.get("region", "?")
    sub = c.get("subregion", "?")
    langs = ", ".join(c.get("languages", {}).values()) if c.get("languages") else "N/A"
    currs = ", ".join(f"{v['name']} ({v.get('symbol', '')})" for v in (c.get("currencies", {}).values())) if c.get("currencies") else "N/A"
    return (
        f"Country info for {cname}:\n"
        f"  Capital: {cap}\n"
        f"  Population: {pop:,}\n"
        f"  Region: {reg} / {sub}\n"
        f"  Languages: {langs}\n"
        f"  Currencies: {currs}\n"
        f"  Timezones: {', '.join(c.get('timezones', []))}"
    )


# ---------------------------------------------------------------------------
# 6. Math — Newton API (newton.vercel.app)
# ---------------------------------------------------------------------------

def solve_math(expression):
    ops = ["simplify", "factor", "derive", "integrate", "log", "cos", "sin", "tan"]
    op = "simplify"
    expr_clean = expression.strip()
    for o in ops:
        if expr_clean.lower().startswith(o):
            op = o
            expr_clean = expr_clean[len(o):].strip().lstrip("of").strip()
            break
    encoded = urllib.parse.quote(expr_clean, safe="")
    data = _get(f"https://newton.now.sh/api/v2/{op}/{encoded}")
    if not data or "result" not in data:
        return None
    return f"Math result ({op}):\n  Input: {data.get('expression', expr_clean)}\n  Result: {data['result']}"


# ---------------------------------------------------------------------------
# 7. Random facts / jokes
# ---------------------------------------------------------------------------

def get_joke():
    data = _get("https://v2.jokeapi.dev/joke/Programming,Misc?blacklistFlags=nsfw,racist,sexist&type=twopart")
    if not data:
        data = _get("https://v2.jokeapi.dev/joke/Programming,Misc?blacklistFlags=nsfw,racist,sexist&type=single")
    if not data:
        return None
    if data.get("type") == "twopart":
        return f"Joke:\n  {data['setup']}\n  {data['delivery']}"
    return f"Joke: {data.get('joke', 'No joke found')}"


def get_fact():
    data = _get("https://uselessfacts.jsph.pl/api/v2/facts/random?language=en")
    if not data:
        return None
    return f"Random fact: {data.get('text', 'No fact found')}"


# ---------------------------------------------------------------------------
# 8. Quotes
# ---------------------------------------------------------------------------

def get_quote():
    data = _get("https://zenquotes.io/api/random")
    if not data or not isinstance(data, list):
        return None
    q = data[0]
    return f"Quote: \"{q.get('q', '')}\" — {q.get('a', 'Unknown')}"


# ---------------------------------------------------------------------------
# 9. IP geolocation — ip-api.com
# ---------------------------------------------------------------------------

def get_ip_info(ip):
    data = _get(f"http://ip-api.com/json/{urllib.parse.quote(ip)}?fields=status,message,country,regionName,city,zip,lat,lon,timezone,isp,org,as,query")
    if not data or data.get("status") != "success":
        return None
    return (
        f"IP info for {data.get('query')}:\n"
        f"  Location: {data.get('city')}, {data.get('regionName')}, {data.get('country')}\n"
        f"  Coordinates: {data.get('lat')}, {data.get('lon')}\n"
        f"  Timezone: {data.get('timezone')}\n"
        f"  ISP: {data.get('isp')}\n"
        f"  Organization: {data.get('org')}"
    )


# ---------------------------------------------------------------------------
# 10. Earthquakes — USGS
# ---------------------------------------------------------------------------

def get_earthquakes():
    data = _get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson")
    if not data or not data.get("features"):
        data = _get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson")
    if not data or not data.get("features"):
        return None
    lines = ["Recent significant earthquakes (USGS live data):"]
    for f in data["features"][:6]:
        p = f.get("properties", {})
        lines.append(f"  - M{p.get('mag', '?')} — {p.get('place', '?')} ({p.get('type', 'earthquake')})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 11. Open Trivia
# ---------------------------------------------------------------------------

def get_trivia():
    data = _get("https://opentdb.com/api.php?amount=1&type=multiple")
    if not data or not data.get("results"):
        return None
    q = data["results"][0]
    import html as html_mod
    question = html_mod.unescape(q["question"])
    correct = html_mod.unescape(q["correct_answer"])
    category = html_mod.unescape(q["category"])
    difficulty = q["difficulty"]
    options = [html_mod.unescape(a) for a in q["incorrect_answers"]] + [correct]
    return (
        f"Trivia question ({category}, {difficulty}):\n"
        f"  Q: {question}\n"
        f"  Options: {', '.join(options)}\n"
        f"  Answer: {correct}"
    )


# ---------------------------------------------------------------------------
# 12. NASA Astronomy Picture of the Day
# ---------------------------------------------------------------------------

def get_nasa_apod():
    data = _get("https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY")
    if not data:
        return None
    return (
        f"NASA Astronomy Picture of the Day:\n"
        f"  Title: {data.get('title', '?')}\n"
        f"  Date: {data.get('date', '?')}\n"
        f"  Explanation: {data.get('explanation', '?')[:500]}"
    )


# ---------------------------------------------------------------------------
# 13. Pokemon — PokeAPI
# ---------------------------------------------------------------------------

def get_pokemon(name):
    data = _get(f"https://pokeapi.co/api/v2/pokemon/{urllib.parse.quote(name.lower())}")
    if not data:
        return None
    types = ", ".join(t["type"]["name"] for t in data.get("types", []))
    stats_str = ", ".join(f"{s['stat']['name']}: {s['base_stat']}" for s in data.get("stats", []))
    abilities = ", ".join(a["ability"]["name"] for a in data.get("abilities", []))
    return (
        f"Pokemon: {data['name'].title()}\n"
        f"  Types: {types}\n"
        f"  Height: {data.get('height', 0) / 10}m, Weight: {data.get('weight', 0) / 10}kg\n"
        f"  Base stats: {stats_str}\n"
        f"  Abilities: {abilities}"
    )


# ---------------------------------------------------------------------------
# 14. University search
# ---------------------------------------------------------------------------

def search_universities(query):
    data = _get(f"http://universities.hipolabs.com/search?name={urllib.parse.quote(query)}")
    if not data:
        return None
    lines = [f"Universities matching \"{query}\":"]
    for u in data[:8]:
        domains = ", ".join(u.get("domains", []))
        lines.append(f"  - {u['name']} ({u.get('country', '?')}) — {domains}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 15. Dog/cat facts
# ---------------------------------------------------------------------------

def get_dog_fact():
    data = _get("https://dogapi.dog/api/v2/facts?limit=1")
    if not data or not data.get("data"):
        return None
    return f"Dog fact: {data['data'][0]['attributes']['body']}"


def get_cat_fact():
    data = _get("https://catfact.ninja/fact")
    if not data:
        return None
    return f"Cat fact: {data.get('fact', 'No fact found')}"


# ---------------------------------------------------------------------------
# 16. Numbers — Numbers API
# ---------------------------------------------------------------------------

def get_number_fact(number):
    text = _get_text(f"http://numbersapi.com/{number}?json")
    if not text:
        return None
    try:
        data = json.loads(text)
        return f"Number fact: {data.get('text', 'No fact found')}"
    except Exception:
        return f"Number fact: {text.strip()}"


# ---------------------------------------------------------------------------
# 17. Exchange rates — Frankfurter
# ---------------------------------------------------------------------------

def get_exchange_rate(base, target):
    data = _get(f"https://api.frankfurter.app/latest?from={urllib.parse.quote(base.upper())}&to={urllib.parse.quote(target.upper())}")
    if not data or not data.get("rates"):
        return None
    rate = list(data["rates"].values())[0]
    return f"Exchange rate (live): 1 {data.get('base', base.upper())} = {rate} {target.upper()} (as of {data.get('date', 'today')})"


# ---------------------------------------------------------------------------
# 18. Spaceflight news
# ---------------------------------------------------------------------------

def get_space_news():
    data = _get("https://api.spaceflightnewsapi.net/v4/articles/?limit=6&ordering=-published_at")
    if not data or not data.get("results"):
        return None
    lines = ["Latest spaceflight news:"]
    for a in data["results"][:6]:
        lines.append(f"  - {a['title']} ({a.get('news_site', '?')})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 19. Bored API — activity suggestions
# ---------------------------------------------------------------------------

def get_activity():
    data = _get("https://bored-api.appbrewery.com/random")
    if not data:
        return None
    return (
        f"Activity suggestion:\n"
        f"  Activity: {data.get('activity', '?')}\n"
        f"  Type: {data.get('type', '?')}\n"
        f"  Participants: {data.get('participants', '?')}"
    )


# ===========================================================================
# ROUTER — detect intent from user message and call relevant APIs
# ===========================================================================

TOOL_PATTERNS = [
    (r"\bweather\b.*\bin\b\s+([A-Za-z\s]+)", "weather"),
    (r"\bforecast\b.*\bin\b\s+([A-Za-z\s]+)", "weather"),
    (r"\btemperature\b.*\bin\b\s+([A-Za-z\s]+)", "weather"),
    (r"\bweather\b.*\bfor\b\s+([A-Za-z\s]+)", "weather"),
    (r"\b(?:price|worth)\b.*\b(bitcoin|ethereum|solana|dogecoin|cardano|xrp|bnb|btc|eth|sol|doge|ada|dot|matic|avax|link|shib|polkadot|polygon|avalanche|chainlink|binancecoin|shiba)\b", "crypto"),
    (r"\b(bitcoin|ethereum|solana|dogecoin|cardano|xrp|bnb|btc|eth|sol|doge|ada|dot|matic|avax|link|shib)\b.*\b(?:price|value|worth|cost|market)\b", "crypto"),
    (r"\bcrypto\b.*\b([a-z]+)\b.*\bprice\b", "crypto"),
    (r"\bhacker\s*news\b", "hackernews"),
    (r"\btech\s*news\b", "hackernews"),
    (r"\btop\s*stories\b", "hackernews"),
    (r"\bdefin(?:e|ition)\b.*[\"']?(\w+)[\"']?", "dictionary"),
    (r"\bwhat\s+(?:does|is)\b\s+[\"']?(\w+)[\"']?\s+mean", "dictionary"),
    (r"\bmeaning\s+of\b\s+[\"']?(\w+)[\"']?", "dictionary"),
    (r"\b(?:country|info|about)\b.*\b((?:[A-Z][a-z]+\s?)+)\b.*\b(?:country|capital|population)\b", "country"),
    (r"\bcapital\s+of\b\s+([A-Za-z\s]+)", "country"),
    (r"\bpopulation\s+of\b\s+([A-Za-z\s]+)", "country"),
    (r"\btell\s+me\s+about\b\s+([A-Za-z\s]+)\s+(?:country|nation)\b", "country"),
    (r"\b(?:solve|calculate|simplify|factor|derive|integrate)\b\s+(.+)", "math"),
    (r"\bjoke\b", "joke"),
    (r"\bfunny\b", "joke"),
    (r"\brandom\s*fact\b", "fact"),
    (r"\btell\s+me\s+(?:a\s+)?fact\b", "fact"),
    (r"\bquote\b.*\binspir", "quote"),
    (r"\binspir.*\bquote\b", "quote"),
    (r"\bmotivat.*\bquote\b", "quote"),
    (r"\bgive\s+me\s+a\s+quote\b", "quote"),
    (r"\bip\b.*\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", "ip"),
    (r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b.*\b(?:info|location|where|lookup)\b", "ip"),
    (r"\bearthquake", "earthquake"),
    (r"\bseismic\b", "earthquake"),
    (r"\btrivia\b", "trivia"),
    (r"\bquiz\b", "trivia"),
    (r"\bnasa\b.*\b(?:picture|photo|apod|astronomy)\b", "nasa"),
    (r"\bastronomy\s+picture\b", "nasa"),
    (r"\bpokemon\b\s+(\w+)", "pokemon"),
    (r"\bpokedex\b\s+(\w+)", "pokemon"),
    (r"\buniversit(?:y|ies)\b.*\b([A-Za-z\s]{3,})\b", "university"),
    (r"\bdog\s*fact\b", "dog_fact"),
    (r"\bcat\s*fact\b", "cat_fact"),
    (r"\bnumber\b.*\b(\d+)\b.*\bfact\b", "number"),
    (r"\bfact\b.*\b(?:about|for)\b.*\bnumber\b\s+(\d+)", "number"),
    (r"\bexchange\s+rate\b.*\b([A-Z]{3})\b.*\b(?:to|in)\b\s*([A-Z]{3})\b", "exchange"),
    (r"\bconvert\b.*\b([A-Z]{3})\b.*\b(?:to|in)\b\s*([A-Z]{3})\b", "exchange"),
    (r"\b([A-Z]{3})\s+to\s+([A-Z]{3})\b.*\b(?:rate|exchange|convert)\b", "exchange"),
    (r"\bspace\s*(?:flight|x)?\s*news\b", "space_news"),
    (r"\brocket\b.*\bnews\b", "space_news"),
    (r"\bbored\b", "activity"),
    (r"\bsuggest\b.*\bactivity\b", "activity"),
    (r"\bwhat\s+should\s+i\s+do\b", "activity"),
]


def route_tools(user_message):
    """Check user message for tool triggers and return augmented context."""
    msg_lower = user_message.lower()
    results = []
    used_tools = []

    for pattern, tool_name in TOOL_PATTERNS:
        m = re.search(pattern, user_message, re.IGNORECASE)
        if not m:
            continue

        result = None

        if tool_name == "weather":
            city = m.group(1).strip().rstrip("?.!")
            result = get_weather(city)
            if result:
                used_tools.append(f"Weather ({city})")

        elif tool_name == "crypto":
            coin = m.group(1).strip()
            result = get_crypto(coin)
            if result:
                used_tools.append(f"Crypto ({coin})")

        elif tool_name == "hackernews":
            result = get_hackernews()
            if result:
                used_tools.append("Hacker News")

        elif tool_name == "dictionary":
            word = m.group(1).strip().rstrip("?.!")
            result = get_definition(word)
            if result:
                used_tools.append(f"Dictionary ({word})")

        elif tool_name == "country":
            name = m.group(1).strip().rstrip("?.!")
            result = get_country(name)
            if result:
                used_tools.append(f"Country ({name})")

        elif tool_name == "math":
            expr = m.group(1).strip().rstrip("?.!")
            result = solve_math(expr)
            if result:
                used_tools.append("Math Solver")

        elif tool_name == "joke":
            result = get_joke()
            if result:
                used_tools.append("Jokes")

        elif tool_name == "fact":
            result = get_fact()
            if result:
                used_tools.append("Random Facts")

        elif tool_name == "quote":
            result = get_quote()
            if result:
                used_tools.append("Quotes")

        elif tool_name == "ip":
            ip = m.group(1)
            result = get_ip_info(ip)
            if result:
                used_tools.append(f"IP Lookup ({ip})")

        elif tool_name == "earthquake":
            result = get_earthquakes()
            if result:
                used_tools.append("USGS Earthquakes")

        elif tool_name == "trivia":
            result = get_trivia()
            if result:
                used_tools.append("Open Trivia")

        elif tool_name == "nasa":
            result = get_nasa_apod()
            if result:
                used_tools.append("NASA APOD")

        elif tool_name == "pokemon":
            name = m.group(1).strip()
            result = get_pokemon(name)
            if result:
                used_tools.append(f"PokéAPI ({name})")

        elif tool_name == "university":
            query = m.group(1).strip().rstrip("?.!")
            if len(query) >= 3:
                result = search_universities(query)
                if result:
                    used_tools.append(f"Universities ({query})")

        elif tool_name == "dog_fact":
            result = get_dog_fact()
            if result:
                used_tools.append("Dog Facts")

        elif tool_name == "cat_fact":
            result = get_cat_fact()
            if result:
                used_tools.append("Cat Facts")

        elif tool_name == "number":
            num = m.group(1)
            result = get_number_fact(num)
            if result:
                used_tools.append(f"Number Facts ({num})")

        elif tool_name == "exchange":
            base, target = m.group(1).upper(), m.group(2).upper()
            result = get_exchange_rate(base, target)
            if result:
                used_tools.append(f"Exchange ({base}→{target})")

        elif tool_name == "space_news":
            result = get_space_news()
            if result:
                used_tools.append("Spaceflight News")

        elif tool_name == "activity":
            result = get_activity()
            if result:
                used_tools.append("Activity Suggestion")

        if result:
            results.append(result)

        if len(results) >= 3:
            break

    return results, used_tools
