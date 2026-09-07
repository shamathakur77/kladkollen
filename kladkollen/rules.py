"""Clothing decision. Worst hour, not the average. Swedish förskola three-layer standard."""

BANDS = [("Freezing", -99, 0), ("Cold", 0, 5), ("Cool", 5, 10), ("Mild", 10, 18), ("Warm dry", 18, 99)]
BAND_ITEMS = {
    "Warm dry": ["t-shirt", "thin trousers", "sun hat", "sunscreen"],
    "Mild": ["long sleeve", "thin fleece", "light jacket", "sneakers"],
    "Cool": ["merino base", "fleece", "shell jacket", "mössa", "thin vantar"],
    "Cold": ["merino base", "fleece", "vinteroverall", "mössa", "vantar", "vinterkängor"],
    "Freezing": ["2-layer merino base", "fleece", "vinteroverall", "mössa", "buff", "thick vantar", "wool socks", "vinterkängor"],
}
OVERLAY_ITEMS = ["regnställ", "gummistövlar", "regnvantar", "shell over everything", "galonisar"]
EMOJI = {"thunder": "⛈️", "snow": "❄️", "rain": "🌧️", "partly": "⛅", "cloud": "☁️", "sun": "☀️"}

def feels_like(t, wind_ms):
    """JAG/TI wind chill. Valid at or below 10°C with wind above 1.3 m/s (4.8 km/h). Otherwise air temp."""
    v = wind_ms * 3.6
    if t <= 10 and v > 4.8:
        return 13.12 + 0.6215 * t - 11.37 * v ** 0.16 + 0.3965 * t * v ** 0.16
    return t

def band_for(feels, wind_bump=False):
    b = next(name for name, lo, hi in BANDS if lo <= feels < hi)
    if wind_bump:
        names = [n for n, _, _ in BANDS]
        b = names[max(0, names.index(b) - 1)]
    return b

def decide(hours):
    hs = [{**h, "feels_like": feels_like(h["air_temperature"], h["wind_speed"])} for h in hours]
    worst = min(hs, key=lambda h: h["feels_like"])
    max_pop = max(h["probability_of_precipitation"] or 0 for h in hs)
    max_gust = max(h["wind_speed_of_gust"] or 0 for h in hs)
    max_rh = max(h["relative_humidity"] or 0 for h in hs)
    codes = " ".join(h["symbol_code"] for h in hs)
    snow = "snow" in codes or "sleet" in codes
    rain = max_pop > 40 or "rain" in codes
    storm = "thunder" in codes
    wind_bump = max_gust > 10
    band = band_for(worst["feels_like"], wind_bump)
    items = list(BAND_ITEMS[band]); overlays = []
    if rain:
        overlays.append("rain"); items += ["regnställ", "gummistövlar", "regnvantar"]
    if wind_bump:
        overlays.append("wind bump")
    if snow:
        overlays.append("snow")
        if "vinteroverall" not in items: items.append("vinteroverall")
        items.append("vinterkängor" if worst["feels_like"] < 0 else "gummistövlar")
    if storm:
        overlays.append("storm"); items.append("shell over everything")
    bag = ["full spare set", "1 extra pair of socks"]
    if max_rh > 85 and rain:
        overlays.append("humid rain"); bag = ["2 full spare sets", "1 extra pair of socks"]
    seen = []
    for i in items:
        if i not in seen: seen.append(i)
    emoji = (EMOJI["thunder"] if storm else EMOJI["snow"] if snow else EMOJI["rain"] if rain
             else EMOJI["partly"] if "partly" in codes else EMOJI["cloud"] if "cloudy" in codes else EMOJI["sun"])
    return {"band": band, "items": seen, "bag": bag, "overlays": overlays, "worst": worst,
            "max_pop": max_pop, "max_gust": max_gust, "max_rh": max_rh, "storm": storm, "emoji": emoji}
