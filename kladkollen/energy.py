"""Optional energy line: Vedic day timing (pure math via cosmic_timing) + personal day numbers.
Skipped entirely when config has no "energy" block. Never fear-framed."""
import datetime as dt

THEMES = {1: "fresh starts", 2: "gentle teamwork", 3: "play and words", 4: "steady routine", 5: "curiosity and change",
          6: "care and home", 7: "quiet focus", 8: "calm confidence", 9: "letting go lightly", 11: "intuition", 22: "big picture building"}

def reduce_num(n):
    while n > 9 and n not in (11, 22):
        n = sum(int(c) for c in str(n))
    return n

def personal_day(birth_day, birth_month, date):
    universal = reduce_num(sum(int(c) for c in date.strftime("%Y%m%d")))
    return reduce_num(birth_day + birth_month + universal)

def energy_line(cfg, date, day_start="07:00", day_end="09:00"):
    """cfg["energy"] = {"location": "stockholm", "people": {"Shama": "19-09", "Ivaan": "12-02"}}"""
    try:
        from .cosmic_timing import compute_day
    except ImportError:
        from cosmic_timing import compute_day
    p = compute_day(date=date, location=cfg.get("location", "stockholm"))
    a = p["astro"]
    parts = []
    for name, dm in cfg.get("people", {}).items():
        d, m = (int(x) for x in dm.split("-"))
        n = personal_day(d, m, date)
        parts.append(f"{name}'s day {n} of {THEMES[n]}")
    rk = next((s for s in p["timeline"] if s["token"] == "red"), None)
    rk_txt = f" (Rahu Kalam {rk['start']} to {rk['end']}, so start the drop-off unhurried)" if rk and rk["start"] < day_end and rk["end"] > day_start else ""
    who = " and ".join(parts) if parts else "the day"
    return f"{a['nakshatra']} nakshatra with a {a['paksha'].lower()} paksha {a['tithi_name']} moon{rk_txt} suits {who}, so an easy morning is already on your side."
