# Klädkollen

One email every evening at 20:00 that tells you exactly what to lay out for förskola tomorrow. Nothing to open, nothing to decide.

```
Tomorrow: Cool ☁️

Tonight lay out: merino base, fleece, shell jacket, mössa, thin vantar.
Bag: full spare set, 1 extra pair of socks.
Weather: Coolest outdoor hour 07:00: 7°C, feels like 4°C, rain chance 20%, gusts 8 m/s.
Mantra: This is my movie, everything is working out for me.

Sources: SMHI pmp3g 2026-09-07T17:00:00Z. Audit: rule fired = Cool + none. Evals 4/4 pass.
```

Built by a parent who found the 07:30 "is it a regnställ day?" question one decision too many. Swedish förskola kids are outside every day in every weather, so the card follows the three-layer standard (base, mid, shell) and picks the band from the **coldest hour between 07:00 and 16:00**, never the daily average.

## Fork it, five minutes

1. Fork this repo.
2. Copy `config.example.json` to `config.json`, put in your coordinates (any map app gives you these) and your email. Delete the `energy` block if you do not want the astrology line.
3. In the repo settings, add secrets:
   `KLADKOLLEN_CONFIG` = the whole contents of your `config.json`
   `SMTP_USER` + `SMTP_PASS` (a Gmail app password works), or `RESEND_API_KEY` + `MAIL_FROM`.
4. Actions tab, run the workflow once by hand. From then on it runs itself.

Run locally with `python run.py daily --dry` to see the card without sending.

## The rules

| Band | Coldest hour feels like | Lay out |
|---|---|---|
| Warm dry | over 18°C | t-shirt, thin trousers, sun hat, sunscreen |
| Mild | 10 to 18 | long sleeve, thin fleece, light jacket, sneakers |
| Cool | 5 to 10 | merino base, fleece, shell jacket, mössa, thin vantar |
| Cold | 0 to 5 | merino base, fleece, vinteroverall, mössa, vantar, vinterkängor |
| Freezing | below 0 | add buff, thick vantar, wool socks, 2-layer base |

Overlays: rain chance over 40% adds regnställ, gummistövlar, regnvantar. Gusts over 10 m/s bump one band colder. Humidity over 85% with rain means two spare sets in the bag. Snow adds vinteroverall plus gummistövlar or vinterkängor by temperature. Thunder means a shell over everything and a line saying so.

Feels-like uses the JAG/TI wind chill formula, applied only where it is valid (10°C or below, wind above 1.3 m/s).

Sundays at 18:00 you get the week: five bands, one weather word each, which evening to run the wash so the shell and merino are dry for the next cold or wet day, and one "Buy or check" line.

## Data and privacy

Weather comes from SMHI's open point-forecast API, with MET Norway as fallback. The only thing that leaves your machine is a pair of coordinates. No child's name, size or anything else goes to any API. The card never invents a forecast: if both sources are down it says so and tells you to reuse yesterday's band.

Every card carries its source timestamp and the rule that fired. Every run appends one line to `runlog.jsonl` (time, source, band, eval results), committed back to your fork so you have an audit trail.

## Evals

The rules ship with their own checks (`python -m pytest -q`): worst hour beats average, band edges, wind chill validity, rain and humidity overlays, wind bump, snow footwear by temperature, card shape under 80 words, no em dashes, and "unavailable never invents". A failed eval still sends the card, with `EVAL FAIL:` in front of the subject, so a broken run is loud rather than silent.

## Optional energy line

If you keep the `energy` block, the card adds one calm sentence from the day's nakshatra and tithi (pure astronomy via pyswisseph, no scraping) and each person's numerology personal day. Birthdays are day-month only and never leave the config. It is framed as a strength, never a warning. Delete the block and the card is four lines.

## Licence

MIT. Made in Stockholm.
