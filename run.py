"""Entry point. `python run.py daily` or `python run.py weekly`. Add --dry to print instead of email."""
import sys, json, datetime as dt
from zoneinfo import ZoneInfo
from kladkollen import weather, card, mail

def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "daily"
    dry = "--dry" in sys.argv
    cfg = json.load(open("config.json"))
    tz = cfg.get("timezone", "Europe/Stockholm")
    ua = cfg.get("user_agent", "kladkollen/0.1 github.com/YOURNAME/kladkollen")
    today = dt.datetime.now(ZoneInfo(tz)).date()
    lat, lon = cfg["lat"], cfg["lon"]
    log = lambda m: print(f"[kladkollen] {m}")

    if kind == "daily":
        day = today + dt.timedelta(days=1)
        if day.weekday() >= 5 and not cfg.get("weekends", False):
            log("weekend tomorrow, nothing to send"); return
        fc = weather.fetch(lat, lon, day, tz, ua, log)
        energy = None
        if cfg.get("energy") and fc["hours"]:
            try:
                from kladkollen.energy import energy_line
                energy = energy_line(cfg["energy"], day)
            except Exception as e:
                log(f"energy line skipped: {e}")
        c = card.daily(fc, cfg, day, energy)
    else:
        monday = today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7)
        days = [(monday + dt.timedelta(days=i), weather.fetch(lat, lon, monday + dt.timedelta(days=i), tz, ua, log)) for i in range(5)]
        c = card.weekly(days, cfg)
        fc = days[0][1]; day = monday
    entry = card.log_run(cfg.get("runlog", "runlog.jsonl"), kind, day, fc, c)
    prefix = "" if c["all_pass"] else "EVAL FAIL: " + ", ".join(k for k, v in c["evals"].items() if not v[0]) + " | "
    print(prefix + c["subject"]); print("\n".join(c["lines"])); print(c["footer"])
    for k, v in c["evals"].items(): print(("PASS " if v[0] else "FAIL ") + k + ": " + v[1])
    if dry:
        return
    mail.send(c, cfg["to"], prefix)
    log("sent to " + ", ".join(cfg["to"]))

if __name__ == "__main__":
    main()
