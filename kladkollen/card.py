"""Render the daily card and the weekly grid, run evals, write the run log."""
import json, re, datetime as dt
from .rules import decide, BAND_ITEMS, OVERLAY_ITEMS

MANTRA = "This is my movie, everything is working out for me."

def evals(lines, decision, energy):
    r = {}
    body = " ".join(lines)
    words = len(re.findall(r"\S+", body))
    r["shape"] = (len(lines) in (4, 5) and words < 80, f"{len(lines)} lines, {words} words")
    w = decision["worst"]
    r["weather_matches_source"] = (f"{w['air_temperature']:.0f}" in lines[2], f"worst {w['time_local']} T={w['air_temperature']}")
    ok_items = all(i in BAND_ITEMS[decision["band"]] + OVERLAY_ITEMS for i in decision["items"])
    r["band_from_worst_hour"] = (ok_items, decision["band"] + " " + ",".join(decision["overlays"]))
    if energy:
        bad = re.search(r"\b(bad|danger|avoid|risk|warning|beware|fear|difficult|unlucky|inauspicious)\b", energy, re.I)
        r["energy_positive_one_sentence"] = (energy.count(".") == 1 and not bad, energy[:60])
    r["no_em_dash"] = ("—" not in body, "clean")
    return r

def daily(fc, cfg, day, energy=None):
    if not fc["hours"]:
        lines = ["Tonight lay out: forecast unavailable, use yesterday's band.", "Bag: full spare set, 1 extra pair of socks.",
                 "Weather: no forecast source answered this evening.", f"Mantra: {MANTRA}"]
        return {"subject": "Tomorrow: forecast unavailable", "lines": lines, "footer": "Sources: none reachable. Audit: fallback fired.", "evals": {}, "all_pass": False, "decision": None}
    d = decide(fc["hours"])
    w = d["worst"]
    weather = f"Coolest outdoor hour {w['time_local']}: {w['air_temperature']:.0f}°C, feels like {round(w['feels_like'])}°C, rain chance {d['max_pop']:.0f}%, gusts {d['max_gust']:.0f} m/s."
    if d["storm"]:
        weather = "Thunder in the forecast: shell over everything. " + weather
    lines = ["Tonight lay out: " + ", ".join(d["items"][:6]) + ".", "Bag: " + ", ".join(d["bag"]) + ".", "Weather: " + weather]
    if energy:
        lines.append("Energy: " + energy)
    lines.append("Mantra: " + cfg.get("mantra", MANTRA))
    ev = evals(lines, d, energy)
    footer = (f"Sources: {fc['source']} {fc['updated_at']}" + (f", cosmic-timing {day:%Y-%m-%d}" if energy else "") +
              f". Audit: rule fired = {d['band']} + {', '.join(d['overlays']) or 'none'}. Evals {sum(v[0] for v in ev.values())}/{len(ev)} pass.")
    return {"subject": f"Tomorrow: {d['band']} {d['emoji']}", "lines": lines, "footer": footer, "evals": ev,
            "all_pass": all(v[0] for v in ev.values()), "decision": d}

def weekly(days, cfg):
    """days: list of (date, forecast dict) for Mon..Fri."""
    rows, bands = [], []
    for day, fc in days:
        if not fc["hours"]:
            rows.append((day, None, "unavailable")); continue
        d = decide(fc["hours"])
        word = "thunder" if d["storm"] else "snow" if "snow" in d["overlays"] else "rain" if "rain" in d["overlays"] else "windy" if "wind bump" in d["overlays"] else "dry"
        rows.append((day, d, word)); bands.append(d["band"])
    heavy = {i for i, (_, d, w) in enumerate(rows) if d and (d["band"] in ("Cool", "Cold", "Freezing") or w in ("rain", "snow"))}
    wash = set()
    for i in sorted(heavy):
        wash.add(max(0, i - 2)) if i >= 1 else None
    lines = []
    for i, (day, d, word) in enumerate(rows):
        lines.append(f"{day:%a} | {d['band'] if d else 'n/a'} | {word} | {'wash' if i in wash else ''}".rstrip(" |"))
    if not heavy:
        lines.append("Wash whenever.")
    buy = []
    words = [w for _, _, w in rows]
    if words.count("rain") >= 3: buy.append("regnvantar and a dry second regnställ (wet week)")
    if any(d and d["band"] in ("Cold", "Freezing") for _, d, _ in rows): buy.append("vinteroverall and vinterkängor fit check")
    lines.append("Buy or check: " + ("; ".join(buy) if buy else "Nothing to buy."))
    dominant = max(set(bands), key=bands.count) if bands else "unavailable"
    emoji = "🌧️" if words.count("rain") >= 2 else "❄️" if "snow" in words else "⛅"
    src = {fc["source"] for _, fc in days}
    footer = f"Sources: {', '.join(sorted(src))}. Audit: bands per day = {', '.join(bands) or 'none'}."
    return {"subject": f"This week: {dominant} {emoji}", "lines": lines, "footer": footer, "all_pass": True, "evals": {}}

def log_run(path, kind, day, fc, card):
    entry = {"run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "kind": kind, "card_for": str(day),
             "source": fc.get("source"), "source_updated": fc.get("updated_at"),
             "band": card["decision"]["band"] if card.get("decision") else None,
             "overlays": card["decision"]["overlays"] if card.get("decision") else None,
             "evals": {k: v[0] for k, v in card["evals"].items()}, "all_pass": card["all_pass"]}
    with open(path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
