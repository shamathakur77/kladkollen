"""Weather fetch: SMHI first, MET Norway fallback. Coordinates only leave the machine.
Returns a list of hourly dicts for the outdoor window, normalised to one shape:
time_local, air_temperature, relative_humidity, wind_speed, wind_speed_of_gust,
uv, symbol_code, precipitation_amount, probability_of_precipitation
plus the source name and forecast timestamp. Never invents a forecast."""
import json, urllib.request, datetime as dt
from zoneinfo import ZoneInfo

SMHI = "https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2/geotype/point/lon/{lon}/lat/{lat}/data.json"
MET = "https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={lat}&lon={lon}"

# SMHI Wsymb2 codes: 1-7 dry, 8-10 rain showers, 11 thunder, 12-14 sleet showers, 15-17 snow showers,
# 18-20 rain, 21 thunder, 22-24 sleet, 25-27 snow
def _smhi_symbol(code):
    if code in (11, 21): return "thunder"
    if 8 <= code <= 10 or 18 <= code <= 20: return "rain"
    if 12 <= code <= 14 or 22 <= code <= 24: return "sleet"
    if 15 <= code <= 17 or 25 <= code <= 27: return "snow"
    if code in (1, 2): return "clearsky"
    if code in (3, 4): return "partlycloudy"
    return "cloudy"

def _get(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def _window(day, tz, start_h, end_h):
    z = ZoneInfo(tz)
    lo = dt.datetime.combine(day, dt.time(start_h), z).astimezone(dt.timezone.utc)
    hi = dt.datetime.combine(day, dt.time(end_h), z).astimezone(dt.timezone.utc)
    return lo, hi, z

def fetch_smhi(lat, lon, day, tz, ua, start_h=7, end_h=16):
    data = _get(SMHI.format(lat=round(lat, 4), lon=round(lon, 4)), ua)
    lo, hi, z = _window(day, tz, start_h, end_h)
    hours = []
    for ts in data["timeSeries"]:
        t = dt.datetime.fromisoformat(ts["validTime"].replace("Z", "+00:00"))
        if not (lo <= t <= hi):
            continue
        p = {x["name"]: x["values"][0] for x in ts["parameters"]}
        hours.append({
            "time_local": t.astimezone(z).strftime("%H:%M"),
            "air_temperature": p["t"], "relative_humidity": p["r"], "wind_speed": p["ws"],
            "wind_speed_of_gust": p["gust"], "uv": None, "symbol_code": _smhi_symbol(int(p["Wsymb2"])),
            "precipitation_amount": p.get("pmean", 0.0),
            # SMHI has no probability field; treat pcat != 0 with pmean > 0 as 100, else 0
            "probability_of_precipitation": 100.0 if p.get("pcat", 0) and p.get("pmean", 0) > 0 else 0.0,
        })
    if not hours:
        raise ValueError("SMHI returned no hours in window")
    return {"source": "SMHI pmp3g", "updated_at": data["approvedTime"], "hours": hours}

def fetch_met(lat, lon, day, tz, ua, start_h=7, end_h=16):
    data = _get(MET.format(lat=round(lat, 4), lon=round(lon, 4)), ua)
    lo, hi, z = _window(day, tz, start_h, end_h)
    hours = []
    for ts in data["properties"]["timeseries"]:
        t = dt.datetime.fromisoformat(ts["time"].replace("Z", "+00:00"))
        if not (lo <= t <= hi):
            continue
        d = ts["data"]
        i = d["instant"]["details"]
        n1 = d.get("next_1_hours") or d.get("next_6_hours") or {}
        hours.append({
            "time_local": t.astimezone(z).strftime("%H:%M"),
            "air_temperature": i["air_temperature"], "relative_humidity": i.get("relative_humidity", 0),
            "wind_speed": i.get("wind_speed", 0), "wind_speed_of_gust": i.get("wind_speed_of_gust", i.get("wind_speed", 0)),
            "uv": i.get("ultraviolet_index_clear_sky"),
            "symbol_code": n1.get("summary", {}).get("symbol_code", "cloudy"),
            "precipitation_amount": n1.get("details", {}).get("precipitation_amount", 0.0),
            "probability_of_precipitation": n1.get("details", {}).get("probability_of_precipitation", 0.0),
        })
    if not hours:
        raise ValueError("MET returned no hours in window")
    return {"source": "MET Norway locationforecast 2.0", "updated_at": data["properties"]["meta"]["updated_at"], "hours": hours}

def fetch(lat, lon, day, tz, ua, log=print):
    errors = []
    for name, fn in (("SMHI", fetch_smhi), ("MET Norway", fetch_met)):
        try:
            out = fn(lat, lon, day, tz, ua)
            log(f"weather source: {out['source']} ({out['updated_at']})")
            return out
        except Exception as e:
            errors.append(f"{name}: {e}")
            log(f"weather source {name} failed: {e}")
    return {"source": "unavailable", "updated_at": None, "hours": [], "errors": errors}
