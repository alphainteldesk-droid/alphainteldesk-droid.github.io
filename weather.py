# Nov 22, 2026: current weather for the six homepage clocks -> weather.json (read by index.html).
# Source: MET Norway Locationforecast 2.0 (free, commercial use OK with credit, CC BY 4.0; needs a User-Agent).
import json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

CITIES = {"America/New_York": (40.71, -74.01), "Europe/London": (51.51, -0.13), "Europe/Rome": (41.9, 12.5),
          "Europe/Moscow": (55.76, 37.62), "Asia/Tokyo": (35.68, 139.69), "Australia/Sydney": (-33.87, 151.21)}
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
with ThreadPoolExecutor(6) as ex:
    for f in [ex.submit(one, tz) for tz in CITIES]:
        try:
            tz, w = f.result()
            out[tz] = w
        except Exception as e:
            print("WEATHER fail", e)
if out:
    json.dump({"t": int(time.time()), "src": "MET Norway", "w": out}, open("weather.json", "w"))
print("WEATHER", {k.split("/")[1]: v for k, v in out.items()})
