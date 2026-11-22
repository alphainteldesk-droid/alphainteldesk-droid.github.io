# Nov 22, 2026: current weather for the six homepage clocks -> weather.json (read by index.html).
# Source: MET Norway Locationforecast 2.0 (free, commercial use OK with credit, CC BY 4.0; needs a User-Agent).
import json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

CITIES = {"los angeles": (34.05, -118.24), "st. pete": (27.77, -82.64), "new york": (40.71, -74.01),
          "london": (51.51, -0.13), "rome": (41.9, 12.5), "dubai": (25.2, 55.27), "mumbai": (19.08, 72.88),
          "hong kong": (22.32, 114.17), "tokyo": (35.68, 139.69), "sydney": (-33.87, 151.21)}   # keys = data-w on the clocks
UA = "AlphaIntelDesk/1.0 https://alphainteldesk.com (alphainteldesk-droid@users.noreply.github.com)"


def one(tz):
    lat, lon = CITIES[tz]
    url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    d = json.load(urllib.request.urlopen(req, timeout=15))
    ts = d["properties"]["timeseries"][0]["data"]
    c = ts["instant"]["details"]["air_temperature"]
    sym = (ts.get("next_1_hours") or ts.get("next_6_hours") or {}).get("summary", {}).get("symbol_code", "")
    return tz, {"c": round(c), "f": round(c * 9 / 5 + 32), "s": sym}


out = {}
with ThreadPoolExecutor(5) as ex:
    for f in [ex.submit(one, tz) for tz in CITIES]:
        try:
            tz, w = f.result()
            out[tz] = w
        except Exception as e:
            print("WEATHER fail", e)
if out:
    json.dump({"t": int(time.time()), "src": "MET Norway", "w": out}, open("weather.json", "w"))
print("WEATHER", len(out), "of", len(CITIES), out)
