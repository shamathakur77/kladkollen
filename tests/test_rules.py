"""The evals, as tests. Run: python -m pytest -q"""
import datetime as dt
from kladkollen.rules import decide, feels_like, band_for
from kladkollen import card

def hour(t, ws=3, gust=6, pop=0, rh=70, code="cloudy", time="07:00"):
    return {"time_local": time, "air_temperature": t, "relative_humidity": rh, "wind_speed": ws, "wind_speed_of_gust": gust,
            "uv": 1, "symbol_code": code, "precipitation_amount": 0.0, "probability_of_precipitation": pop}

def test_worst_hour_not_average():
    hours = [hour(2, ws=0.5, gust=1, time="07:00")] + [hour(14, time=f"{h}:00") for h in range(8, 17)]
    d = decide(hours)
    assert d["band"] == "Cold" and d["worst"]["time_local"] == "07:00"

def test_bands_edges():
    assert band_for(-0.1) == "Freezing" and band_for(0) == "Cold" and band_for(5) == "Cool"
    assert band_for(10) == "Mild" and band_for(18) == "Warm dry"

def test_wind_chill_only_below_10():
    assert feels_like(15, 8) == 15
    assert feels_like(3, 8) < 3

def test_rain_overlay_and_humid_bag():
    d = decide([hour(8, pop=60, rh=90, code="rain")])
    assert {"regnställ", "gummistövlar", "regnvantar"} <= set(d["items"])
    assert d["bag"][0] == "2 full spare sets"

def test_wind_bump():
    assert decide([hour(12, gust=12)])["band"] == "Cool"

def test_snow_boots_by_temp():
    assert "gummistövlar" in decide([hour(2, ws=0.5, gust=1, code="snow")])["items"]
    assert "vinterkängor" in decide([hour(-3, code="snow")])["items"]

def test_card_shape_and_evals():
    fc = {"source": "test", "updated_at": "now", "hours": [hour(6)]}
    c = card.daily(fc, {}, dt.date(2026, 9, 8))
    assert len(c["lines"]) == 4 and c["all_pass"]
    assert "—" not in " ".join(c["lines"])

def test_unavailable_never_invents():
    c = card.daily({"source": "unavailable", "updated_at": None, "hours": []}, {}, dt.date(2026, 9, 8))
    assert "forecast unavailable" in c["lines"][0]
