from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
GDELT_CACHE = DATA_DIR / "gdelt_cache.json"
CAL_CACHE = DATA_DIR / "calendar_cache.json"
PRICE_CACHE = DATA_DIR / "price_cache.json"
UPCOMING_CACHE = DATA_DIR / "upcoming_cache.json"

app = FastAPI(title="THYSMY Fundamental Web V2", version="2.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

BIQUOTE = "https://biquote.io"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"

CAL_REFRESH = 60
PRICE_REFRESH = 5
GDELT_REFRESH = 900
GDELT_BACKOFF = 1200

RULES = [
    # Specific names first
    ("nonfarm payroll", +1, 3.5, "LABOR"),
    ("non-farm payroll", +1, 3.5, "LABOR"),
    ("average hourly earnings", +1, 2.5, "LABOR"),
    ("unemployment rate", -1, 3.0, "LABOR"),
    ("adp employment", +1, 2.0, "LABOR"),
    ("employment change", +1, 1.8, "LABOR"),
    ("initial jobless claims", -1, 1.8, "LABOR"),
    ("continuing jobless claims", -1, 1.2, "LABOR"),
    ("jobless claims", -1, 1.4, "LABOR"),
    ("jolts job openings", +1, 1.8, "LABOR"),
    ("job openings", +1, 1.5, "LABOR"),
    ("ism manufacturing employment", +1, 1.6, "LABOR"),
    ("ism services employment", +1, 1.6, "LABOR"),

    ("core cpi", +1, 3.0, "INFLATION"),
    ("consumer price index", +1, 2.8, "INFLATION"),
    ("cpi", +1, 2.8, "INFLATION"),
    ("core pce", +1, 3.0, "INFLATION"),
    ("pce price", +1, 2.5, "INFLATION"),
    ("producer price index", +1, 1.8, "INFLATION"),
    ("ppi", +1, 1.8, "INFLATION"),

    ("gross domestic product", +1, 2.4, "GROWTH"),
    ("gdp", +1, 2.4, "GROWTH"),
    ("retail sales", +1, 2.0, "GROWTH"),
    ("durable goods", +1, 1.5, "GROWTH"),
    ("industrial production", +1, 1.3, "GROWTH"),
    ("ism manufacturing", +1, 1.7, "GROWTH"),
    ("ism services", +1, 1.7, "GROWTH"),
    ("manufacturing pmi", +1, 1.2, "GROWTH"),
    ("services pmi", +1, 1.2, "GROWTH"),
    ("consumer confidence", +1, 1.2, "GROWTH"),

    ("interest rate decision", +1, 3.5, "RATES"),
    ("fed funds rate", +1, 3.5, "RATES"),
    ("federal funds rate", +1, 3.5, "RATES"),
    ("fomc statement", 0, 3.0, "RATES"),
    ("fomc press conference", 0, 3.0, "RATES"),
    ("fomc minutes", 0, 2.5, "RATES"),
    ("fed chair", 0, 2.5, "RATES"),
    ("powell", 0, 2.5, "RATES"),
]

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def find_rule(name: str) -> dict[str, Any] | None:
    lower = (name or "").lower()
    for key, higher_usd, weight, category in RULES:
        if key in lower:
            return {
                "key": key,
                "higher_usd": higher_usd,
                "weight": weight,
                "category": category,
            }
    return None

def get_num(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None

def importance_value(value: str | None) -> int:
    v = (value or "").lower()
    return 3 if v == "high" else 2 if v in ("medium", "moderate", "med") else 1

def cache_read(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def cache_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def safe_get(url: str, *, params: dict[str, Any] | None = None, timeout: int = 10) -> requests.Response:
    return requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={"User-Agent": "THYSMY-Fundamental-Web-V2/2.0", "Accept": "application/json"},
    )

# -------------------------- BIQUOTE CALENDAR -------------------------- #

def fetch_calendar(force: bool = False) -> dict[str, Any]:
    now = int(time.time())
    cached = cache_read(CAL_CACHE)

    if cached and not force and now - int(cached.get("epoch", 0)) < CAL_REFRESH:
        data = cached.get("data", {})
        data["status"] = "CALENDAR LIVE (CACHE)"
        return data

    start = (now_utc() - timedelta(days=15)).isoformat().replace("+00:00", "Z")
    end = (now_utc() + timedelta(days=30)).isoformat().replace("+00:00", "Z")

    params = {
        "from": start,
        "to": end,
        "countries": "US",
        "importance": "medium",
        "limit": 500,
    }

    try:
        r = safe_get(f"{BIQUOTE}/api/calendar", params=params)
        r.raise_for_status()
        rows = r.json()
        if not isinstance(rows, list):
            raise ValueError("calendar response is not a list")

        data = {
            "ok": True,
            "status": "CALENDAR LIVE",
            "rows": rows,
            "retrieved_at": now_utc().isoformat(),
        }
        cache_write(CAL_CACHE, {"epoch": now, "data": data})
        return data
    except Exception as exc:
        if cached:
            data = cached.get("data", {})
            data["status"] = f"CALENDAR CACHE / {type(exc).__name__}"
            return data
        return {
            "ok": False,
            "status": f"CALENDAR FAILED / {type(exc).__name__}",
            "rows": [],
            "retrieved_at": None,
        }

def fetch_upcoming(force: bool = False) -> dict[str, Any]:
    """Use BiQuote's dedicated upcoming endpoint for robust next-news detection."""
    now = int(time.time())
    cached = cache_read(UPCOMING_CACHE)

    if cached and not force and now - int(cached.get("epoch", 0)) < CAL_REFRESH:
        data = cached.get("data", {})
        data["status"] = "UPCOMING LIVE (CACHE)"
        return data

    params = {"countries": "US", "importance": "medium", "limit": 100}
    try:
        r = safe_get(f"{BIQUOTE}/api/calendar/upcoming", params=params)
        r.raise_for_status()
        rows = r.json()
        if not isinstance(rows, list):
            raise ValueError("upcoming response is not a list")
        data = {
            "ok": True,
            "status": "UPCOMING LIVE",
            "rows": rows,
            "retrieved_at": now_utc().isoformat(),
        }
        cache_write(UPCOMING_CACHE, {"epoch": now, "data": data})
        return data
    except Exception as exc:
        if cached:
            data = cached.get("data", {})
            data["status"] = f"UPCOMING CACHE / {type(exc).__name__}"
            return data
        return {
            "ok": False,
            "status": f"UPCOMING FAILED / {type(exc).__name__}",
            "rows": [],
            "retrieved_at": None,
        }

def recognized_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        rule = find_rule(r.get("name", ""))
        if not rule:
            continue
        x = dict(r)
        x["_rule"] = rule
        x["_dt"] = parse_dt(r.get("time"))
        if x["_dt"]:
            out.append(x)
    return out

def next_group(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rec = recognized_rows(rows)
    now = now_utc()
    future = [r for r in rec if r["_dt"] >= now and importance_value(r.get("importance")) >= 3]
    if not future:
        future = [r for r in rec if r["_dt"] >= now]
    if not future:
        return []

    future.sort(key=lambda x: x["_dt"])
    target = future[0]["_dt"]
    return [r for r in future if abs((r["_dt"] - target).total_seconds()) <= 60]

def group_label(group: list[dict[str, Any]]) -> str:
    names = " ".join(r.get("name", "") for r in group).lower()
    if "nonfarm" in names or "non-farm" in names:
        return "NFP"
    if "consumer price index" in names or "cpi" in names:
        return "CPI"
    if "producer price index" in names or "ppi" in names:
        return "PPI"
    if "fomc" in names or "interest rate" in names or "fed funds" in names:
        return "FOMC"
    return group[0].get("name", "USD NEWS") if group else "USD NEWS"

def primary_rule(group: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not group:
        return None
    return max((r["_rule"] for r in group), key=lambda x: x["weight"], default=None)

def forecast_trend_score(row: dict[str, Any]) -> float:
    rule = row["_rule"]
    if rule["higher_usd"] == 0:
        return 0.0
    forecast = get_num(row, "forecast")
    prev = get_num(row, "revisedPrevious")
    if prev is None:
        prev = get_num(row, "previous")
    if forecast is None or prev is None or math.isclose(forecast, prev, rel_tol=1e-9, abs_tol=1e-12):
        return 0.0
    cmp = 1 if forecast > prev else -1
    return cmp * rule["higher_usd"] * rule["weight"] * 0.75

def surprise_score(row: dict[str, Any]) -> float:
    rule = row["_rule"]
    if rule["higher_usd"] == 0:
        return 0.0
    actual = get_num(row, "actual")
    forecast = get_num(row, "forecast")
    if actual is None or forecast is None or math.isclose(actual, forecast, rel_tol=1e-9, abs_tol=1e-12):
        return 0.0
    cmp = 1 if actual > forecast else -1
    denom = max(abs(forecast), 1.0)
    gap = abs(actual - forecast) / denom
    magnitude = min(1.5, 0.75 + gap * 1.5)
    return cmp * rule["higher_usd"] * rule["weight"] * magnitude

def build_macro_context(rows: list[dict[str, Any]], group: list[dict[str, Any]]) -> dict[str, Any]:
    if not group:
        return {"total": 0.0, "labor": 0.0, "inflation": 0.0, "growth": 0.0, "rates": 0.0, "used": []}

    target_time = group[0]["_dt"]
    p_rule = primary_rule(group)
    target_category = p_rule["category"] if p_rule else "OTHER"
    start = target_time - timedelta(days=14)

    scores = {"LABOR": 0.0, "INFLATION": 0.0, "GROWTH": 0.0, "RATES": 0.0}
    total = 0.0
    used = []

    rec = recognized_rows(rows)
    rec.sort(key=lambda x: x["_dt"], reverse=True)

    for r in rec:
        if not (start <= r["_dt"] < target_time):
            continue
        if get_num(r, "actual") is None or get_num(r, "forecast") is None:
            continue

        raw = surprise_score(r)
        if raw == 0:
            continue

        boost = 1.75 if r["_rule"]["category"] == target_category else 1.0
        score = raw * boost
        total += score
        if r["_rule"]["category"] in scores:
            scores[r["_rule"]["category"]] += score

        if len(used) < 10:
            used.append({
                "name": r.get("name"),
                "time": r.get("time"),
                "actual": r.get("actual"),
                "forecast": r.get("forecast"),
                "score": round(score, 2),
                "category": r["_rule"]["category"],
            })

    for r in group:
        total += forecast_trend_score(r)

    return {
        "total": round(total, 2),
        "labor": round(scores["LABOR"], 2),
        "inflation": round(scores["INFLATION"], 2),
        "growth": round(scores["GROWTH"], 2),
        "rates": round(scores["RATES"], 2),
        "used": used,
    }

# ------------------------------- PRICE ------------------------------- #

def fetch_price(force: bool = False) -> dict[str, Any]:
    now = int(time.time())
    cached = cache_read(PRICE_CACHE)
    if cached and not force and now - int(cached.get("epoch", 0)) < PRICE_REFRESH:
        return cached.get("data", {})

    try:
        r = safe_get(f"{BIQUOTE}/api/XAUUSD", timeout=6)
        r.raise_for_status()
        d = r.json()
        data = {
            "ok": True,
            "status": "LIVE",
            "bid": d.get("bid"),
            "ask": d.get("ask"),
            "mid": d.get("mid"),
            "spread": d.get("spread"),
            "dayDiffPercent": d.get("dayDiffPercent"),
            "marketState": d.get("marketState"),
            "stale": d.get("stale"),
            "timestamp": d.get("timestamp"),
            "source": d.get("source"),
        }
        cache_write(PRICE_CACHE, {"epoch": now, "data": data})
        return data
    except Exception as exc:
        if cached:
            d = cached.get("data", {})
            d["status"] = f"CACHE / {type(exc).__name__}"
            return d
        return {"ok": False, "status": f"FAILED / {type(exc).__name__}"}

# ------------------------------- GDELT ------------------------------- #

def count_hits(text: str, key: str, cap: int = 4) -> int:
    return min(cap, text.lower().count(key.lower()))

def analyze_gdelt(articles: list[dict[str, Any]]) -> dict[str, Any]:
    text = "\n".join(
        f"{a.get('title','')} {a.get('domain','')}" for a in articles
    ).lower()

    usd = xau = 0.0
    hits = 0

    def add(key: str, u: float, x: float):
        nonlocal usd, xau, hits
        n = count_hits(text, key)
        if n:
            usd += u * n
            xau += x * n
            hits += n

    for key, u, x in [
        ("hawkish", .75, 0), ("rate hike", .75, -.05), ("higher for longer", .70, -.05),
        ("strong jobs", .45, 0), ("strong labor market", .45, 0),
        ("dollar strengthens", .55, -.15), ("dollar rises", .45, -.10),
        ("treasury yields rise", .55, -.20),
        ("dovish", -.75, .05), ("rate cut", -.65, .05),
        ("weak jobs", -.45, .05), ("weak labor market", -.45, .05),
        ("dollar weakens", -.55, .15), ("dollar falls", -.45, .10),
        ("treasury yields fall", -.55, .20),
        ("recession fears", -.30, .30), ("economic slowdown", -.25, .15),
        ("geopolitical tensions", 0, .60), ("geopolitical risk", 0, .60),
        ("escalation", 0, .45), ("missile attack", 0, .55), ("military attack", 0, .55),
        ("armed conflict", 0, .50), ("war fears", 0, .55), ("sanctions", 0, .25),
        ("safe-haven demand", 0, .55), ("safe haven demand", 0, .55),
        ("risk-off", 0, .45), ("banking crisis", 0, .60), ("financial stress", 0, .45),
        ("trade war", 0, .35), ("tariff threat", 0, .30),
        ("ceasefire", 0, -.45), ("de-escalation", 0, -.45), ("risk-on", 0, -.35),
    ]:
        add(key, u, x)

    usd = clamp(usd, -4, 4)
    xau = clamp(xau, -4, 4)

    hawk = sum(count_hits(text, x) for x in ["hawkish", "rate hike", "higher for longer"])
    dove = sum(count_hits(text, x) for x in ["dovish", "rate cut"])
    fed = "HAWKISH" if hawk > dove else "DOVISH" if dove > hawk else "BALANCED"

    riskoff = sum(count_hits(text, x) for x in ["geopolitical", "escalation", "war fears", "safe-haven", "risk-off"])
    riskon = sum(count_hits(text, x) for x in ["ceasefire", "de-escalation", "risk-on"])
    risk = "RISK-OFF" if riskoff > riskon else "RISK-ON" if riskon > riskoff else "BALANCED"

    return {
        "ok": True, "status": "GDELT LIVE",
        "usd_score": round(usd, 2), "xau_score": round(xau, 2),
        "fed": fed, "risk": risk, "hits": hits,
        "articles": articles[:10],
    }

def fetch_gdelt(force: bool = False) -> dict[str, Any]:
    now = int(time.time())
    cached = cache_read(GDELT_CACHE)

    if cached and not force:
        last_ok = int(cached.get("last_ok", 0))
        last_fail = int(cached.get("last_fail", 0))
        if last_ok and now - last_ok < GDELT_REFRESH:
            d = cached.get("data", {})
            d["status"] = "GDELT LIVE (CACHE)"
            return d
        if last_fail and now - last_fail < GDELT_BACKOFF:
            d = cached.get("data", {})
            d["status"] = "GDELT COOLDOWN"
            return d

    query = '(Federal Reserve OR Fed OR inflation OR jobs OR unemployment OR dollar OR "Treasury yield" OR gold OR geopolitical OR war OR tariff OR sanctions OR recession)'
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": 75,
        "timespan": "6h",
        "sort": "datedesc",
        "format": "json",
    }

    try:
        r = safe_get(GDELT, params=params)
        if r.status_code == 429:
            raise RuntimeError("HTTP429")
        r.raise_for_status()
        articles = r.json().get("articles", [])
        data = analyze_gdelt(articles)
        cache_write(GDELT_CACHE, {"last_ok": now, "last_fail": 0, "data": data})
        return data
    except Exception as exc:
        if cached:
            d = cached.get("data", {})
            d["status"] = "GDELT RATE LIMITED" if "HTTP429" in str(exc) else f"GDELT CACHE / {type(exc).__name__}"
            cache_write(GDELT_CACHE, {
                "last_ok": cached.get("last_ok", 0),
                "last_fail": now,
                "data": d,
            })
            return d
        return {
            "ok": False,
            "status": "GDELT RATE LIMITED" if "HTTP429" in str(exc) else f"GDELT FAILED / {type(exc).__name__}",
            "usd_score": 0, "xau_score": 0, "fed": "-", "risk": "-", "hits": 0, "articles": [],
        }

# ---------------------------- FINAL ENGINE --------------------------- #

def split_one_two(
    group: list[dict[str, Any]],
    macro: dict[str, Any],
    global_ctx: dict[str, Any],
) -> tuple[int, int]:
    one = 50.0
    macro_total = float(macro["total"])
    one += min(18.0, abs(macro_total) * 2.2)

    if abs(macro_total) < 1.0:
        one -= 15
    elif abs(macro_total) < 2.0:
        one -= 8

    category_scores = [macro["labor"], macro["inflation"], macro["growth"], macro["rates"]]
    pos = sum(1 for x in category_scores if x > .60)
    neg = sum(1 for x in category_scores if x < -.60)
    if pos and neg:
        one -= min(20, 6 * min(pos, neg))

    forecast_scores = [forecast_trend_score(r) for r in group]
    fp = sum(1 for x in forecast_scores if x > 0)
    fn = sum(1 for x in forecast_scores if x < 0)
    if fp and fn:
        one -= 15

    if len(group) >= 3:
        one -= 8
    elif len(group) == 2:
        one -= 4

    label = group_label(group)
    if label == "NFP":
        one -= 7
    elif label == "CPI":
        one -= 4
    elif label == "FOMC":
        one -= 12

    global_usd_equiv = float(global_ctx.get("usd_score", 0)) - float(global_ctx.get("xau_score", 0))
    if abs(global_usd_equiv) >= .5 and abs(macro_total) >= .5:
        if (global_usd_equiv > 0 and macro_total > 0) or (global_usd_equiv < 0 and macro_total < 0):
            one += 8
        else:
            one -= 10

    one = round(clamp(one, 10, 90))
    return one, 100 - one

def spike_potential(
    group: list[dict[str, Any]],
    macro: dict[str, Any],
    global_ctx: dict[str, Any],
) -> int:
    if not group:
        return 0

    p = primary_rule(group)
    max_imp = max(importance_value(r.get("importance")) for r in group)
    pct = 35.0
    pct += 25 if max_imp >= 3 else 10 if max_imp == 2 else 0

    if p:
        pct += min(18.0, p["weight"] * 4)
        pct += {"RATES": 10, "LABOR": 7, "INFLATION": 8, "GROWTH": 3}.get(p["category"], 0)

    max_gap = 0.0
    for r in group:
        f = get_num(r, "forecast")
        prev = get_num(r, "revisedPrevious")
        if prev is None:
            prev = get_num(r, "previous")
        if f is not None and prev is not None:
            max_gap = max(max_gap, abs(f - prev) / max(abs(prev), 1.0))
    pct += min(10, max_gap * 20)

    pct += min(7, abs(float(macro["total"])) * .7)
    pct += min(8, abs(float(global_ctx.get("xau_score", 0))) * 2)
    pct += min(5, abs(float(global_ctx.get("usd_score", 0))) * 1.5)
    return round(clamp(pct, 0, 100))

def serialize_event(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r.get("id"),
        "eventId": r.get("eventId"),
        "time": r.get("time"),
        "name": r.get("name"),
        "importance": r.get("importance"),
        "actual": r.get("actual"),
        "forecast": r.get("forecast"),
        "previous": r.get("previous"),
        "revisedPrevious": r.get("revisedPrevious"),
        "unit": r.get("unit"),
        "multiplier": r.get("multiplier"),
        "source": r.get("source"),
        "sourceUrl": r.get("sourceUrl"),
    }

def calculate() -> dict[str, Any]:
    cal = fetch_calendar()
    rows = cal.get("rows", [])
    upcoming = fetch_upcoming()
    upcoming_rows = upcoming.get("rows", [])
    group = next_group(upcoming_rows)
    # Fallback to the date-range calendar if the dedicated endpoint is unavailable.
    if not group:
        group = next_group(rows)
    global_ctx = fetch_gdelt()
    price = fetch_price()

    if not group:
        return {
            "ok": False,
            "status": "NO RECOGNIZED UPCOMING USD NEWS",
            "calendar_status": cal.get("status"),
            "upcoming_status": upcoming.get("status"),
            "calendar_rows": len(rows),
            "upcoming_rows": len(upcoming_rows),
            "global": global_ctx,
            "price": price,
            "server_time": now_utc().isoformat(),
        }

    macro = build_macro_context(rows, group)
    global_usd = float(global_ctx.get("usd_score", 0))
    global_xau = float(global_ctx.get("xau_score", 0))

    final_xau = -float(macro["total"]) - global_usd + global_xau

    if final_xau > .60:
        bias = "XAU BUY"
    elif final_xau < -.60:
        bias = "XAU SELL"
    else:
        bias = "NEUTRAL / MIXED"

    evidence = abs(float(macro["total"])) + abs(global_usd) + abs(global_xau)
    confidence = 0
    if evidence > 0:
        agreement = min(1.0, abs(final_xau) / max(1.0, evidence))
        confidence = round(50 + agreement * 45)

    one, two = split_one_two(group, macro, global_ctx)
    spike = spike_potential(group, macro, global_ctx)

    target_time = group[0]["_dt"]
    seconds_to_news = max(0, int((target_time - now_utc()).total_seconds()))

    # Conflict preview based only on forecast-vs-previous.
    pre_components = []
    for r in group:
        s = forecast_trend_score(r)
        pre_components.append({
            "name": r.get("name"),
            "forecast": r.get("forecast"),
            "previous": r.get("revisedPrevious") if r.get("revisedPrevious") is not None else r.get("previous"),
            "usd_score": round(s, 2),
        })

    return {
        "ok": True,
        "status": "LIVE",
        "server_time": now_utc().isoformat(),
        "calendar_status": cal.get("status"),
        "upcoming_status": upcoming.get("status"),
        "label": group_label(group),
        "event_time": group[0].get("time"),
        "seconds_to_news": seconds_to_news,
        "events": [serialize_event(r) for r in group],
        "category": primary_rule(group)["category"] if primary_rule(group) else "OTHER",
        "macro": macro,
        "pre_components": pre_components,
        "global": global_ctx,
        "price": price,
        "final_xau_score": round(final_xau, 2),
        "bias": bias,
        "confidence": confidence,
        "spike_potential": spike,
        "one_way": one,
        "two_way": two,
        "note": "Bias/confidence/spike/one-way/two-way are heuristic context scores, not guaranteed probabilities.",
    }

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "templates" / "index.html").read_text(encoding="utf-8")

@app.get("/api/dashboard")
def dashboard():
    return JSONResponse(calculate())

@app.post("/api/refresh")
def refresh_all():
    fetch_calendar(force=True)
    fetch_upcoming(force=True)
    fetch_price(force=True)
    fetch_gdelt(force=True)
    return JSONResponse(calculate())

@app.get("/api/calendar/raw")
def calendar_raw():
    return JSONResponse(fetch_calendar())

@app.get("/api/diagnostics")
def diagnostics():
    cal = fetch_calendar()
    up = fetch_upcoming()
    price = fetch_price()
    return {
        "calendar_status": cal.get("status"),
        "calendar_rows": len(cal.get("rows", [])),
        "upcoming_status": up.get("status"),
        "upcoming_rows": len(up.get("rows", [])),
        "recognized_upcoming": len(recognized_rows(up.get("rows", []))),
        "price_status": price.get("status"),
        "price_mid": price.get("mid"),
    }

@app.get("/health")
def health():
    return {"ok": True, "app": "THYSMY Fundamental Web V2"}
