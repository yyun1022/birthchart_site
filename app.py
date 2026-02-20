import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse


import swisseph as swe

app = FastAPI()


# -----------------------
# Swiss Ephemeris setup
# -----------------------
EPHE_PATH = os.environ.get("SWEPHE_PATH", os.path.join(os.path.dirname(__file__), "ephe"))
swe.set_ephe_path(EPHE_PATH)

FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED  # <-- force Swiss ephemeris (.se1 files)

PLANETS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
    "Uranus": swe.URANUS,
    "Neptune": swe.NEPTUNE,
    "Pluto": swe.PLUTO,
}

def ensure_ephe_present():
    if not os.path.isdir(EPHE_PATH):
        raise RuntimeError(f"Ephemeris folder not found: {EPHE_PATH}")
    if not any(name.endswith(".se1") for name in os.listdir(EPHE_PATH)):
        raise RuntimeError(
            f"No .se1 files found in {EPHE_PATH}. "
            f"On Render, make sure download_ephe.py ran during build."
        )

def local_to_utc(local_dt_str: str, tz_name: str) -> datetime:
    local_naive = datetime.strptime(local_dt_str, "%Y-%m-%d %H:%M")
    local_aware = local_naive.replace(tzinfo=ZoneInfo(tz_name))
    return local_aware.astimezone(ZoneInfo("UTC"))

def utc_to_jd_ut(utc_dt: datetime) -> float:
    hour = utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0
    return swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour, swe.GREG_CAL)

def deg_to_sign(deg: float) -> dict:
    signs = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
    deg = deg % 360.0
    sign_index = int(deg // 30)
    within = deg - sign_index * 30
    return {"longitude": deg, "sign": signs[sign_index], "degree_in_sign": within}

@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Swiss Ephemeris Birth Chart</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 900px; margin: 30px auto; padding: 0 16px; }
    input, button { padding: 10px; font-size: 16px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
    #results { white-space: pre; background: #f6f6f6; padding: 12px; border-radius: 8px; overflow-x: auto; }
    small { color: #555; }
  </style>
</head>
<body>
  <h1>Swiss Ephemeris Birth Chart</h1>
  <p><small>This uses Swiss Ephemeris .se1 files downloaded at deploy-time, plus real timezone conversion.</small></p>

  <<div class="row">
  <input id="date" type="date" />
  <input id="time" type="time" />
  <input id="place" type="text" placeholder="Place, e.g. Xi'an" style="flex:1; min-width: 280px;" />
  <button onclick="searchPlace()">Search</button>
</div>

<div class="row">
  <select id="placeSelect" style="flex:1; min-width: 420px;" disabled>
    <option>Search a place first…</option>
  </select>
  <button onclick="run()" id="calcBtn" disabled>Calculate</button>
</div>

<div class="row">
  <small id="placeInfo"></small>
</div>

  <h3>Results</h3>
  <div id="results">Waiting…</div>

<script>

let placeCandidates = [];

async function searchPlace() {
  const q = document.getElementById("place").value.trim();
  const sel = document.getElementById("placeSelect");
  const info = document.getElementById("placeInfo");
  const calcBtn = document.getElementById("calcBtn");

  if (!q) return;

  info.textContent = "Searching…";
  sel.disabled = true;
  calcBtn.disabled = true;
  sel.innerHTML = `<option>Searching…</option>`;

  const r = await fetch(`/api/resolve_place?q=${encodeURIComponent(q)}`);
  const candidates = await r.json();
  placeCandidates = candidates;

  if (!candidates.length) {
    info.textContent = "No matches. Try adding country/region (e.g. Xi'an China).";
    sel.innerHTML = `<option>No matches</option>`;
    return;
  }

  sel.innerHTML = candidates.map((c, i) =>
    `<option value="${i}">${c.display_name} (tz: ${c.tz})</option>`
  ).join("");

  sel.disabled = false;
  calcBtn.disabled = false;

  const c0 = candidates[0];
  info.textContent = `Selected: ${c0.display_name} | lat=${c0.lat} lon=${c0.lon} | tz=${c0.tz}`;
}

document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "placeSelect") {
    const i = parseInt(e.target.value, 10);
    const c = placeCandidates[i];
    document.getElementById("placeInfo").textContent =
      `Selected: ${c.display_name} | lat=${c.lat} lon=${c.lon} | tz=${c.tz}`;
  }
});

async function run() {
  const date = document.getElementById("date").value;
  const time = document.getElementById("time").value;
  const sel = document.getElementById("placeSelect");
  const results = document.getElementById("results");

  if (!date || !time) {
    results.textContent = "Please fill date and time.";
    return;
  }
  if (sel.disabled) {
    results.textContent = "Please search and select a place first.";
    return;
  }

  const idx = parseInt(sel.value, 10);
  const c = placeCandidates[idx];

  results.textContent = "Calculating…";

  const payload = {
    local_datetime: `${date} ${time}`,
    tz: c.tz,
    lat: c.lat,
    lon: c.lon,
    house_system: "P"
  };

  const r2 = await fetch("/api/chart", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });

  const out = await r2.json();
  results.textContent = JSON.stringify(out, null, 2);
}

</script>
</body>
</html>
"""

@app.get("/api/resolve_place")
def resolve_place(q: str = Query(..., min_length=2)):
    # Open-Meteo Geocoding API (free, no key)
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": q,
        "count": 8,
        "language": "en",
        "format": "json",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    results = data.get("results") or []
    out = []
    for r in results:
        # Open-Meteo returns timezone already (IANA name)
        out.append({
            "display_name": f"{r.get('name')}, {r.get('admin1') or ''} {r.get('country') or ''}".replace("  ", " ").strip().strip(","),
            "lat": float(r["latitude"]),
            "lon": float(r["longitude"]),
            "tz": r.get("timezone") or "UTC"
        })
    return JSONResponse(out)

@app.post("/api/chart")
def chart(payload: dict):
    try:
        ensure_ephe_present()

        local_dt_str = payload["local_datetime"]
        tz_name = payload["tz"]
        lat = float(payload["lat"])
        lon = float(payload["lon"])
        hsys = (payload.get("house_system") or "P").upper()
        if len(hsys) != 1:
            hsys = "P"

        utc_dt = local_to_utc(local_dt_str, tz_name)
        jd_ut = utc_to_jd_ut(utc_dt)

        planets_out = {}
        for name, p in PLANETS.items():
            xx, _ = swe.calc_ut(jd_ut, p, FLAGS)
            planets_out[name] = deg_to_sign(xx[0])

        hsys = (payload.get("house_system") or "P").upper()[:1]
        hsys_b = hsys.encode("ascii")
        cusps, ascmc = swe.houses_ex(jd_ut, lat, lon, hsys)
        asc = deg_to_sign(ascmc[0])
        mc = deg_to_sign(ascmc[1])

        house_cusps = {str(i): deg_to_sign(cusps[i]) for i in range(1, 13)}

        return JSONResponse({
            "input": {
                "local_datetime": local_dt_str,
                "tz": tz_name,
                "utc_datetime": utc_dt.isoformat(),
                "lat": lat, "lon": lon,
                "house_system": hsys,
                "jd_ut": jd_ut,
                "ephe_path": EPHE_PATH
            },
            "angles": {"Asc": asc, "MC": mc},
            "planets": planets_out,
            "house_cusps": house_cusps
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
