"""
cosmic_timing.py
Location-aware Vedic + Human Design timing engine for The Frequency Brief.

Self-contained drop-in. One public call:

    from cosmic_timing import compute_day
    payload = compute_day()                      # today, Stockholm
    payload = compute_day(location="nashik")     # switch with one arg
    payload = compute_day(date=date(2026, 12, 21), location="stockholm")

Returns a plain dict. Nothing in here touches your renderer, your email
step, or your existing card code. Wire `payload["timeline"]` and
`payload["lines"]` into the card yourself.

Dependencies: pyswisseph (already in Darpan). Standard library otherwise.
No network calls. No scraping. Deterministic.

Solar geometry: NOAA solar position algorithm (equation of time +
declination + hour angle), as specified.
Astro layer: Swiss Ephemeris via pyswisseph, Moshier ephemeris so no
ephemeris data files are required.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, asdict, field
from datetime import date as Date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

# ---------------------------------------------------------------------------
# CONFIG  -- switch location with one change
# ---------------------------------------------------------------------------

LOCATIONS = {
    "stockholm": {"name": "Stockholm", "lat": 59.3293, "lon": 18.0686, "tz": "Europe/Stockholm"},
    "nashik":    {"name": "Nashik",    "lat": 19.9975, "lon": 73.7898, "tz": "Asia/Kolkata"},
    "pune":      {"name": "Pune",      "lat": 18.5204, "lon": 73.8567, "tz": "Asia/Kolkata"},
}

DEFAULT_LOCATION = "stockholm"

# Zenith angles used by the NOAA hour-angle solution.
ZENITH_OFFICIAL = 90.833   # standard sunrise/sunset (refraction + solar radius)
ZENITH_CIVIL    = 96.0     # civil twilight, used as the polar-mode fallback

# ---------------------------------------------------------------------------
# WEEKDAY SEGMENT TABLES
# Segment 1 begins at sunrise. Day is divided into 8 equal segments.
# ---------------------------------------------------------------------------

RAHU_SEGMENT     = {"Sunday": 8, "Monday": 2, "Tuesday": 7, "Wednesday": 5,
                    "Thursday": 6, "Friday": 4, "Saturday": 3}
YAMAGANDA_SEGMENT = {"Sunday": 5, "Monday": 4, "Tuesday": 3, "Wednesday": 2,
                     "Thursday": 1, "Friday": 7, "Saturday": 6}
GULIKA_SEGMENT   = {"Sunday": 7, "Monday": 6, "Tuesday": 5, "Wednesday": 4,
                    "Thursday": 3, "Friday": 2, "Saturday": 1}

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"]  # date.weekday() order

ABHIJIT_SKIP_WEEKDAYS = {"Wednesday"}  # traditionally not observed

# ---------------------------------------------------------------------------
# HUMAN DESIGN GATE WHEEL
# 64 gates, 5.625 degrees each, wheel anchored at Gate 41 starting
# 02deg00' Aquarius = 302.0 degrees tropical longitude. Gates then run in
# zodiacal (increasing longitude) order.
# ---------------------------------------------------------------------------

HD_WHEEL_START_DEG = 302.0
HD_GATE_WIDTH = 360.0 / 64.0          # 5.625
HD_LINE_WIDTH = HD_GATE_WIDTH / 6.0   # 0.9375

HD_GATE_ORDER = [
    41, 19, 13, 49, 30, 55, 37, 63, 22, 36, 25, 17, 21, 51, 42, 3,
    27, 24, 2, 23, 8, 20, 16, 35, 45, 12, 15, 52, 39, 53, 62, 56,
    31, 33, 7, 4, 29, 59, 40, 64, 47, 6, 46, 18, 48, 57, 32, 50,
    28, 44, 1, 43, 14, 34, 9, 5, 26, 11, 10, 58, 38, 54, 61, 60,
]

# Cardinal-point landmarks used to self-check the wheel above.
# 0 Aries -> Gate 25, 0 Cancer -> Gate 15, 0 Libra -> Gate 46, 0 Cap -> Gate 10.
HD_WHEEL_LANDMARKS = {0.0: 25, 90.0: 15, 180.0: 46, 270.0: 10}

# ---------------------------------------------------------------------------
# NAKSHATRA / TITHI TABLES
# ---------------------------------------------------------------------------

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada",
    "Revati",
]

TITHI_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
    "Trayodashi", "Chaturdashi",
]

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
         "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

# ---------------------------------------------------------------------------
# DESIGN TOKENS for the timeline strip
# ---------------------------------------------------------------------------

TOKEN_GREEN = "green"
TOKEN_YELLOW = "yellow"
TOKEN_RED = "red"
TOKEN_STAR = "star"

LABEL_YELLOW = "no new starts, routine ok"
LABEL_RED = "no launches, no signing, no big asks"
LABEL_GREEN_OPEN = "clear and open"
LABEL_ABHIJIT = "best window to send, publish or ask"

PERSONALIZATION_LINE = (
    "MG with Sacral authority: run every yes through the gut, not the head."
)

SWE_FLAGS = swe.FLG_SWIEPH | swe.FLG_MOSEPH | swe.FLG_SPEED


# ===========================================================================
# NOAA SOLAR CORE
# ===========================================================================

def _julian_day(dt_utc: datetime) -> float:
    """Julian Day from an aware UTC datetime."""
    dt = dt_utc.astimezone(timezone.utc)
    frac = (dt.hour + dt.minute / 60.0 + dt.second / 3600.0) / 24.0
    return swe.julday(dt.year, dt.month, dt.day, frac * 24.0)


def _julian_century(jd: float) -> float:
    return (jd - 2451545.0) / 36525.0


def _solar_geometry(jc: float) -> dict:
    """NOAA solar position intermediates for a given Julian century."""
    # Geometric mean longitude of the sun, degrees
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360.0
    # Geometric mean anomaly, degrees
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    # Eccentricity of earth orbit
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    m_rad = math.radians(m)
    # Equation of centre
    c = (math.sin(m_rad) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
         + math.sin(2 * m_rad) * (0.019993 - 0.000101 * jc)
         + math.sin(3 * m_rad) * 0.000289)
    true_long = l0 + c
    omega = 125.04 - 1934.136 * jc
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    # Mean obliquity of the ecliptic
    seconds = 21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))
    eps0 = 23.0 + (26.0 + seconds / 60.0) / 60.0
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))
    decl = math.degrees(math.asin(
        math.sin(math.radians(eps)) * math.sin(math.radians(app_long))
    ))
    # Equation of time, minutes
    y = math.tan(math.radians(eps / 2.0)) ** 2
    l0_rad = math.radians(l0)
    eq_time = 4.0 * math.degrees(
        y * math.sin(2 * l0_rad)
        - 2 * e * math.sin(m_rad)
        + 4 * e * y * math.sin(m_rad) * math.cos(2 * l0_rad)
        - 0.5 * y * y * math.sin(4 * l0_rad)
        - 1.25 * e * e * math.sin(2 * m_rad)
    )
    return {"decl": decl, "eq_time": eq_time}


def _hour_angle(lat: float, decl: float, zenith: float):
    """
    Sunrise hour angle in degrees. Returns (hour_angle, clamped_flag).
    The acos argument is clamped to [-1, 1] as the high-latitude guard.
    """
    lat_r = math.radians(lat)
    dec_r = math.radians(decl)
    raw = (math.cos(math.radians(zenith)) / (math.cos(lat_r) * math.cos(dec_r))
           - math.tan(lat_r) * math.tan(dec_r))
    clamped = raw < -1.0 or raw > 1.0
    raw = max(-1.0, min(1.0, raw))
    return math.degrees(math.acos(raw)), clamped


def _solve_sun_events(local_date: Date, lat: float, lon: float, tz: ZoneInfo,
                      zenith: float):
    """
    NOAA sunrise / solar noon / sunset for a local calendar date.
    Returns (sunrise, solar_noon, sunset, clamped) as aware local datetimes.
    """
    # Anchor on local noon so the correct UTC day is used at any longitude.
    anchor = datetime.combine(local_date, datetime.min.time(),
                              tzinfo=tz) + timedelta(hours=12)
    anchor_utc = anchor.astimezone(timezone.utc)
    utc_day = anchor_utc.date()

    clamped = False
    sunrise = sunset = noon = None

    # Two passes: the second uses the geometry at the estimated solar noon.
    jd = _julian_day(datetime(utc_day.year, utc_day.month, utc_day.day,
                              12, 0, tzinfo=timezone.utc))
    for _ in range(2):
        geo = _solar_geometry(_julian_century(jd))
        noon_minutes = 720.0 - 4.0 * lon - geo["eq_time"]
        ha, clamped = _hour_angle(lat, geo["decl"], zenith)
        rise_minutes = noon_minutes - 4.0 * ha
        set_minutes = noon_minutes + 4.0 * ha

        base = datetime(utc_day.year, utc_day.month, utc_day.day,
                        tzinfo=timezone.utc)
        noon = base + timedelta(minutes=noon_minutes)
        sunrise = base + timedelta(minutes=rise_minutes)
        sunset = base + timedelta(minutes=set_minutes)
        jd = _julian_day(noon)

    return (sunrise.astimezone(tz), noon.astimezone(tz),
            sunset.astimezone(tz), clamped)


def solar_day(local_date: Date, lat: float, lon: float, tz: ZoneInfo):
    """
    Sunrise / sunset with the high-latitude fallback chain.
    Returns dict with sunrise, sunset, solar_noon, polar_mode, basis.
    """
    sunrise, noon, sunset, clamped = _solve_sun_events(
        local_date, lat, lon, tz, ZENITH_OFFICIAL)
    if not clamped:
        return {"sunrise": sunrise, "sunset": sunset, "solar_noon": noon,
                "polar_mode": False, "basis": "true sunrise and sunset"}

    # No true sunrise or sunset. Fall back to civil twilight.
    sunrise, noon, sunset, clamped2 = _solve_sun_events(
        local_date, lat, lon, tz, ZENITH_CIVIL)
    if not clamped2:
        return {"sunrise": sunrise, "sunset": sunset, "solar_noon": noon,
                "polar_mode": True, "basis": "civil twilight"}

    # Neither event occurs. Use a symmetric nominal day around solar noon so
    # the card still renders something honest rather than crashing.
    return {"sunrise": noon - timedelta(hours=6),
            "sunset": noon + timedelta(hours=6),
            "solar_noon": noon,
            "polar_mode": True,
            "basis": "nominal 12h day, no sun events at this latitude"}


# ===========================================================================
# SEGMENT WINDOWS
# ===========================================================================

@dataclass
class Window:
    key: str
    label: str
    start: datetime
    end: datetime
    token: str
    segment: int | None = None
    note: str = ""

    def as_dict(self):
        d = asdict(self)
        d["start"] = self.start.strftime("%H:%M")
        d["end"] = self.end.strftime("%H:%M")
        d["start_iso"] = self.start.isoformat()
        d["end_iso"] = self.end.isoformat()
        return d


def _segment_bounds(sunrise: datetime, seg_len: timedelta, n: int):
    """Segment n is 1-indexed from sunrise."""
    return sunrise + seg_len * (n - 1), sunrise + seg_len * n


def build_windows(sunrise: datetime, sunset: datetime, weekday: str):
    """Rahu Kalam, Yamaganda, Gulika, Abhijit for the day."""
    day_length = sunset - sunrise
    seg_len = day_length / 8

    specs = [
        ("rahu", RAHU_SEGMENT[weekday], "Rahu Kalam", LABEL_RED, TOKEN_RED),
        ("yamaganda", YAMAGANDA_SEGMENT[weekday], "Yamaganda", LABEL_YELLOW, TOKEN_YELLOW),
        ("gulika", GULIKA_SEGMENT[weekday], "Gulika", LABEL_YELLOW, TOKEN_YELLOW),
    ]

    windows = []
    for key, seg, name, label, token in specs:
        start, end = _segment_bounds(sunrise, seg_len, seg)
        windows.append(Window(key=key, label=name, start=start, end=end,
                              token=token, segment=seg, note=label))

    abhijit = None
    if weekday not in ABHIJIT_SKIP_WEEKDAYS:
        solar_noon = sunrise + day_length / 2
        half = day_length / 30           # width = day_length / 15
        abhijit = Window(key="abhijit", label="Abhijit Muhurat",
                         start=solar_noon - half, end=solar_noon + half,
                         token=TOKEN_STAR, note=LABEL_ABHIJIT)

    return windows, abhijit, seg_len, day_length


def _subtract(interval, blockers):
    """Remove blocker intervals from one (start, end) interval."""
    pieces = [interval]
    for b_start, b_end in blockers:
        nxt = []
        for s, e in pieces:
            if b_end <= s or b_start >= e:
                nxt.append((s, e))
                continue
            if b_start > s:
                nxt.append((s, b_start))
            if b_end < e:
                nxt.append((b_end, e))
        pieces = nxt
    return [(s, e) for s, e in pieces if e > s]


def build_timeline(sunrise: datetime, sunset: datetime, windows, abhijit):
    """
    Ordered, non-overlapping vertical strip from sunrise to sunset.
    Green fills every gap the inauspicious windows leave behind.
    Abhijit is returned separately as an overlay marker, trimmed clear of red.
    """
    blockers = sorted([(w.start, w.end) for w in windows])
    strip = []

    for s, e in _subtract((sunrise, sunset), blockers):
        strip.append(Window(key="clear", label="Open", start=s, end=e,
                            token=TOKEN_GREEN, note=LABEL_GREEN_OPEN))
    strip.extend(windows)
    strip.sort(key=lambda w: w.start)

    notes = []
    marker = None
    if abhijit is not None:
        red = [(w.start, w.end) for w in windows if w.token == TOKEN_RED]
        clear = _subtract((abhijit.start, abhijit.end), red)
        if not clear:
            notes.append(
                "Abhijit sits inside Rahu Kalam today, so it is not shown as a "
                "green light. Use the next open stretch instead."
            )
        else:
            s, e = max(clear, key=lambda p: p[1] - p[0])
            trimmed = (s, e) != (abhijit.start, abhijit.end)
            marker = Window(key="abhijit", label="Abhijit Muhurat",
                            start=s, end=e, token=TOKEN_STAR,
                            note=LABEL_ABHIJIT)
            if trimmed:
                notes.append("Abhijit trimmed to the part clear of Rahu Kalam.")

    return strip, marker, notes


# ===========================================================================
# ASTRO LAYER (pyswisseph)
# ===========================================================================

def _lon(jd: float, body: int, sidereal: bool = False) -> float:
    flags = SWE_FLAGS | (swe.FLG_SIDEREAL if sidereal else 0)
    return swe.calc_ut(jd, body, flags)[0][0] % 360.0


def _bisect_crossing(jd_start: float, jd_end: float, target_fn, tol_days=1e-6):
    """Find jd in [start, end] where target_fn changes sign."""
    lo, hi = jd_start, jd_end
    f_lo = target_fn(lo)
    for _ in range(80):
        mid = (lo + hi) / 2
        f_mid = target_fn(mid)
        if (f_lo < 0) != (f_mid < 0):
            hi = mid
        else:
            lo, f_lo = mid, f_mid
        if hi - lo < tol_days:
            break
    return (lo + hi) / 2


def _elongation(jd: float) -> float:
    return (_lon(jd, swe.MOON) - _lon(jd, swe.SUN)) % 360.0


def _find_next_elongation(jd0: float, target: float, max_days: float = 40.0):
    """Next jd after jd0 where elongation crosses `target` degrees."""
    def f(jd):
        return ((_elongation(jd) - target + 180.0) % 360.0) - 180.0

    step = 0.25
    prev_jd, prev = jd0, f(jd0)
    jd = jd0 + step
    while jd < jd0 + max_days:
        cur = f(jd)
        if prev < 0 <= cur and abs(cur - prev) < 180:
            return _bisect_crossing(prev_jd, jd, f)
        prev_jd, prev = jd, cur
        jd += step
    return None


def _find_boundary_end(jd0: float, arc: float):
    """
    End time of the current tithi (arc=12) or nakshatra (arc=13.3333),
    based on elongation for tithi and sidereal moon for nakshatra.
    """
    if arc == 12.0:
        value_fn = _elongation
    else:
        value_fn = lambda jd: _lon(jd, swe.MOON, sidereal=True)

    start_val = value_fn(jd0)
    idx = int(start_val // arc)
    target = (idx + 1) * arc

    def f(jd):
        return ((value_fn(jd) - target + 180.0) % 360.0) - 180.0

    step = 0.02
    prev_jd, prev = jd0, f(jd0)
    jd = jd0 + step
    while jd < jd0 + 3.0:
        cur = f(jd)
        if prev < 0 <= cur and abs(cur - prev) < 180:
            return _bisect_crossing(prev_jd, jd, f)
        prev_jd, prev = jd, cur
        jd += step
    return None


def _jd_to_local(jd: float, tz: ZoneInfo) -> datetime:
    y, m, d, hours = swe.revjul(jd)
    dt = (datetime(y, m, d, tzinfo=timezone.utc)
          + timedelta(hours=hours))
    return dt.astimezone(tz)


def hd_sun_gate(sun_long_tropical: float):
    """Human Design gate and line from tropical solar longitude."""
    offset = (sun_long_tropical - HD_WHEEL_START_DEG) % 360.0
    idx = int(offset // HD_GATE_WIDTH)
    gate = HD_GATE_ORDER[idx]
    within = offset - idx * HD_GATE_WIDTH
    line = int(within // HD_LINE_WIDTH) + 1
    return {"gate": gate, "line": min(line, 6),
            "gate_start_deg": round((HD_WHEEL_START_DEG + idx * HD_GATE_WIDTH) % 360.0, 4)}


def check_hd_wheel():
    """Self-check the gate wheel against the four cardinal points."""
    bad = []
    for deg, expected in HD_WHEEL_LANDMARKS.items():
        got = hd_sun_gate(deg + 0.5)["gate"]
        if got != expected:
            bad.append(f"{deg}deg expected gate {expected}, got {got}")
    return bad


def astro_layer(sunrise_local: datetime, tz: ZoneInfo, local_date: Date):
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    jd = _julian_day(sunrise_local)

    sun_trop = _lon(jd, swe.SUN)
    moon_trop = _lon(jd, swe.MOON)
    moon_sid = _lon(jd, swe.MOON, sidereal=True)

    nak_idx = int(moon_sid // (360.0 / 27))
    nak_pos = moon_sid - nak_idx * (360.0 / 27)
    pada = int(nak_pos // (360.0 / 108)) + 1

    elong = (moon_trop - sun_trop) % 360.0
    tithi_idx = int(elong // 12.0)              # 0..29
    paksha = "Shukla" if tithi_idx < 15 else "Krishna"
    within = tithi_idx % 15
    if within == 14:
        tithi_name = "Purnima" if paksha == "Shukla" else "Amavasya"
    else:
        tithi_name = TITHI_NAMES[within]

    illum = swe.pheno_ut(jd, swe.MOON, SWE_FLAGS)[1]

    jd_full = _find_next_elongation(jd, 180.0)
    jd_new = _find_next_elongation(jd, 0.0)

    tithi_end = _find_boundary_end(jd, 12.0)
    nak_end = _find_boundary_end(jd, 360.0 / 27)

    eclipse = _eclipse_flag(jd, tz, local_date)

    return {
        "moon_sign_tropical": SIGNS[int(moon_trop // 30)],
        "moon_longitude_tropical": round(moon_trop, 4),
        "nakshatra": NAKSHATRAS[nak_idx],
        "nakshatra_pada": pada,
        "nakshatra_ends": _jd_to_local(nak_end, tz).strftime("%H:%M %d %b") if nak_end else None,
        "ayanamsa": "Lahiri",
        "tithi_number": tithi_idx + 1,
        "tithi_name": tithi_name,
        "paksha": paksha,
        "tithi_ends": _jd_to_local(tithi_end, tz).strftime("%H:%M %d %b") if tithi_end else None,
        "moon_illumination_percent": round(illum * 100, 1),
        "days_to_full_moon": round(jd_full - jd, 2) if jd_full else None,
        "days_to_new_moon": round(jd_new - jd, 2) if jd_new else None,
        "next_full_moon": _jd_to_local(jd_full, tz).strftime("%d %b %H:%M") if jd_full else None,
        "next_new_moon": _jd_to_local(jd_new, tz).strftime("%d %b %H:%M") if jd_new else None,
        "sun_longitude_tropical": round(sun_trop, 4),
        "sun_sign_tropical": SIGNS[int(sun_trop // 30)],
        "human_design_sun": hd_sun_gate(sun_trop),
        "eclipse": eclipse,
    }


def _eclipse_flag(jd: float, tz: ZoneInfo, local_date: Date):
    """Flag a solar or lunar eclipse whose maximum falls on this local date."""
    hits = []
    try:
        sol = swe.sol_eclipse_when_glob(jd - 1.0, SWE_FLAGS, 0, False)
        jd_max = sol[1][0]
        if _jd_to_local(jd_max, tz).date() == local_date:
            hits.append("solar eclipse")
    except Exception:
        pass
    try:
        lun = swe.lun_eclipse_when(jd - 1.0, SWE_FLAGS, 0, False)
        jd_max = lun[1][0]
        if _jd_to_local(jd_max, tz).date() == local_date:
            hits.append("lunar eclipse")
    except Exception:
        pass
    return hits or None


# ===========================================================================
# COPY LAYER
# ===========================================================================

def _strip_em_dashes(text: str) -> str:
    return text.replace("—", ", ").replace("–", "-")


def build_lines(payload: dict) -> list[str]:
    a = payload["astro"]
    lines = []

    marker = payload.get("abhijit")
    if marker:
        lines.append(f"Abhijit {marker['start']} to {marker['end']}. {LABEL_ABHIJIT}.")

    rahu = next(w for w in payload["timeline"] if w["key"] == "rahu")
    lines.append(f"Rahu Kalam {rahu['start']} to {rahu['end']}. {LABEL_RED}.")

    lines.append(
        f"Moon in {a['nakshatra']} pada {a['nakshatra_pada']}, "
        f"{a['paksha']} {a['tithi_name']}, "
        f"{a['moon_illumination_percent']} percent lit."
    )

    hd = a["human_design_sun"]
    lines.append(f"Sun in Gate {hd['gate']}.{hd['line']} today.")

    if a["eclipse"]:
        lines.append("Eclipse window: " + " and ".join(a["eclipse"]) + ". Rest, watch, do not force.")

    if payload["polar_mode"]:
        lines.append("Polar mode: windows built on civil twilight today.")

    lines.append(PERSONALIZATION_LINE)
    return [_strip_em_dashes(x) for x in lines]


# ===========================================================================
# PUBLIC ENTRY POINT
# ===========================================================================

def compute_day(date: Date | None = None, location: str = DEFAULT_LOCATION) -> dict:
    loc = LOCATIONS[location]
    tz = ZoneInfo(loc["tz"])
    local_date = date or datetime.now(tz).date()
    weekday = WEEKDAY_NAMES[local_date.weekday()]

    sun = solar_day(local_date, loc["lat"], loc["lon"], tz)
    windows, abhijit, seg_len, day_length = build_windows(
        sun["sunrise"], sun["sunset"], weekday)
    strip, marker, notes = build_timeline(
        sun["sunrise"], sun["sunset"], windows, abhijit)

    # Spec rule "first segment after sunrise is always green" conflicts with
    # the tables on Thursday (Yamaganda = segment 1) and Saturday (Gulika = 1).
    # The traditional window wins so the card never mislabels a caution period.
    first_seg_end = sun["sunrise"] + seg_len
    if any(w.start < first_seg_end and w.token != TOKEN_GREEN for w in strip):
        notes.append(
            f"{weekday}: segment 1 carries a caution window, so it is not "
            f"painted green. Traditional table takes priority."
        )

    payload = {
        "date": local_date.isoformat(),
        "weekday": weekday,
        "location": loc["name"],
        "timezone": loc["tz"],
        "sunrise": sun["sunrise"].strftime("%H:%M"),
        "sunset": sun["sunset"].strftime("%H:%M"),
        "solar_noon": sun["solar_noon"].strftime("%H:%M"),
        "day_length": f"{int(day_length.total_seconds() // 3600):02d}:"
                      f"{int(day_length.total_seconds() % 3600 // 60):02d}",
        "segment_minutes": round(seg_len.total_seconds() / 60, 1),
        "polar_mode": sun["polar_mode"],
        "basis": sun["basis"],
        "timeline": [w.as_dict() for w in strip],
        "abhijit": marker.as_dict() if marker else None,
        "notes": notes,
        "personalization": PERSONALIZATION_LINE,
    }
    payload["astro"] = astro_layer(sun["sunrise"], tz, local_date)
    payload["lines"] = build_lines(payload)
    return payload


def render_text(payload: dict) -> str:
    """Plain text preview of the vertical strip. For your eyes, not the card."""
    out = [f"{payload['location']}  {payload['weekday']} {payload['date']}",
           f"sunrise {payload['sunrise']}   sunset {payload['sunset']}"
           f"   day {payload['day_length']}"]
    if payload["polar_mode"]:
        out.append(f"POLAR MODE: {payload['basis']}")
    out.append("")
    glyph = {TOKEN_GREEN: "|", TOKEN_YELLOW: "!", TOKEN_RED: "X"}
    for w in payload["timeline"]:
        out.append(f"  {glyph[w['token']]}  {w['start']}-{w['end']}  "
                   f"{w['label']:<14} {w['note']}")
    if payload["abhijit"]:
        a = payload["abhijit"]
        out.append(f"  *  {a['start']}-{a['end']}  {a['label']:<14} {a['note']}")
    out.append("")
    for line in payload["lines"]:
        out.append(f"  {line}")
    for n in payload["notes"]:
        out.append(f"  note: {n}")
    return "\n".join(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--date")
    p.add_argument("--location", default=DEFAULT_LOCATION, choices=list(LOCATIONS))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    d = Date.fromisoformat(args.date) if args.date else None
    result = compute_day(d, args.location)
    print(json.dumps(result, indent=2) if args.json else render_text(result))
