import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

import swisseph as swe


app = FastAPI()

# --- Swiss Ephemeris setup ---
EPHE_PATH = os.environ.get("SWEPHE_PATH", os.path.join(os.path.dirname(__file__), "ephe"))
swe.set_ephe_path(EPHE_PATH)



FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED

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
    # Optional: True Node
    "TrueNode": swe.TRUE_NODE,
}

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]


def ensure_ephe_present():
    # minimal sanity check: ephe folder exists + has at least one .se1
    if not os.path.isdir(EPHE_PATH):
        raise RuntimeError(f"EPHE_PATH not found: {EPHE_PATH}")
    found = any(fn.endswith(".se1") for fn in os.listdir(EPHE_PATH))
    if not found:
        raise RuntimeError(f"No .se1 files found in EPHE_PATH: {EPHE_PATH}")


def deg_to_sign(lon_deg: float):
    lon_deg = lon_deg % 360.0
    sign_idx = int(lon_deg // 30)
    deg_in_sign = lon_deg - sign_idx * 30
    return {
        "lon": round(lon_deg, 6),
        "sign": SIGNS[sign_idx],
        "deg": round(deg_in_sign, 6),
    }


def local_to_utc(local_dt_str: str, tz_name: str) -> datetime:
    # expects "YYYY-MM-DD HH:MM" or "YYYY-MM-DD HH:MM:SS"
    fmt = "%Y-%m-%d %H:%M:%S" if len(local_dt_str.strip()) > 16 else "%Y-%m-%d %H:%M"
    naive = datetime.strptime(local_dt_str.strip(), fmt)
    tz = ZoneInfo(tz_name)
    local = naive.replace(tzinfo=tz)
    return local.astimezone(timezone.utc)


def utc_to_jd_ut(utc_dt: datetime) -> float:
    # Swiss Ephemeris wants UT Julian Day
    y = utc_dt.year
    m = utc_dt.month
    d = utc_dt.day
    hour = utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0
    return swe.julday(y, m, d, hour, swe.GREG_CAL)


@app.get("/", response_class=HTMLResponse)
def home():
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Swiss Ephemeris Birth Chart</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 40px; }
    .row { display:flex; gap:12px; margin: 12px 0; align-items:center; }
    input, select, button { font-size: 18px; padding: 12px; }
    input[type="text"] { width: 520px; }
    pre { background:#f6f6f6; padding: 16px; border-radius: 12px; overflow:auto; }
    small { color: #444; }
  </style>
</head>
<body>
  <h1>Swiss Ephemeris Birth Chart</h1>
  <p><small>This uses Swiss Ephemeris .se1 files downloaded at deploy-time, plus real timezone conversion.</small></p>

  <div class="row">
    <input id="date" type="date" />
    <input id="time" type="time" />
    <input id="place" type="text" placeholder="Place, e.g. George Town" />
    <button onclick="searchPlace()">Search</button>
  </div>

  <div class="row">
    <select id="placeSelect" style="flex:1" disabled>
      <option>Search a place first…</option>
    </select>
    <button onclick="run()" id="calcBtn" disabled>Calculate</button>
  </div>

  <div class="row">
    <small id="placeInfo"></small>
  </div>

  <h2>Results</h2>
  <pre id="results">{}</pre>

<script>
let placeCandidates = [];

async function searchPlace() {
  const q = document.getElementById("place").value.trim();
  const sel = document.getElementById("placeSelect");
  const info = document.getElementById("placeInfo");
  const calcBtn = document.getElementById("calcBtn");
  const results = document.getElementById("results");

  if (!q) return;

  results.textContent = "{}";
  info.textContent = "Searching…";
  sel.disabled = true;
  calcBtn.disabled = true;
  sel.innerHTML = `<option>Searching…</option>`;

  const r = await fetch(`/api/resolve_place?q=${encodeURIComponent(q)}`);
  const candidates = await r.json();
  placeCandidates = candidates;

  if (!Array.isArray(candidates) || candidates.length === 0) {
    info.textContent = "No matches. Try adding country/region (e.g. George Town Malaysia).";
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
    results.textContent = JSON.stringify({error: "Please fill date and time."}, null, 2);
    return;
  }
  if (sel.disabled) {
    results.textContent = JSON.stringify({error: "Please search and select a place first."}, null, 2);
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
    return HTMLResponse(html)


@app.get("/api/resolve_place")
def resolve_place(q: str = Query(..., min_length=2)):
    # Open-Meteo Geocoding API (free, no key, returns IANA timezone)
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {"name": q, "count": 8, "language": "en", "format": "json"}
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        out = []
        for r in results:
            display = f"{r.get('name')}, {r.get('admin1') or ''} {r.get('country') or ''}".replace("  ", " ").strip().strip(",")
            out.append({
                "display_name": display,
                "lat": float(r["latitude"]),
                "lon": float(r["longitude"]),
                "tz": r.get("timezone") or "UTC"
            })
        return JSONResponse(out)
    except Exception as e:
        return JSONResponse({"error": str(e), "where": "resolve_place"}, status_code=500)


@app.post("/api/chart")
def chart(payload: dict):
    try:
        ensure_ephe_present()

        local_dt_str = payload.get("local_datetime")
        tz_name = payload.get("tz")
        lat = float(payload.get("lat"))
        lon = float(payload.get("lon"))

        if not local_dt_str or not tz_name:
            return JSONResponse({"error": "Missing local_datetime or tz"}, status_code=400)

        # Time conversion
        utc_dt = local_to_utc(local_dt_str, tz_name)
        jd_ut = utc_to_jd_ut(utc_dt)

        # Planets
        planets_out = {}
        for name, p in PLANETS.items():
            xx, _ = swe.calc_ut(jd_ut, p, FLAGS)
            planets_out[name] = deg_to_sign(xx[0])

        # Houses (safe across pyswisseph return formats)
        hsys = (payload.get("house_system") or "P").upper()[:1]  # 1 char
        hsys_b = hsys.encode("ascii")  # must be bytes length 1

        res = swe.houses_ex(jd_ut, lat, lon, hsys_b)

        # res can be (cusps, ascmc) OR just cusps depending on build
        if isinstance(res, (list, tuple)) and len(res) == 2 and isinstance(res[0], (list, tuple)):
            cusps = res[0]
            ascmc = res[1]
        else:
            cusps = res
            ascmc = None

        cusps_list = list(cusps)
        if len(cusps_list) == 13:
            cusps_12 = cusps_list[1:13]  # 1..12
        elif len(cusps_list) >= 12:
            cusps_12 = cusps_list[:12]   # 0..11
        else:
            raise RuntimeError(f"Unexpected cusps length: {len(cusps_list)}")

        house_cusps = {str(i + 1): deg_to_sign(cusps_12[i]) for i in range(12)}

        asc = deg_to_sign(ascmc[0]) if (ascmc and len(ascmc) >= 1) else None
        mc = deg_to_sign(ascmc[1]) if (ascmc and len(ascmc) >= 2) else None

        return JSONResponse({
            "code_version": "stable-v1",
            "input": {
                "local_datetime": local_dt_str,
                "tz": tz_name,
                "utc_datetime": utc_dt.isoformat(),
                "lat": lat,
                "lon": lon,
                "jd_ut": jd_ut,
                "ephe_path": EPHE_PATH,
                "house_system": hsys
            },
            "angles": {"Asc": asc, "MC": mc},
            "planets": planets_out,
            "house_cusps": house_cusps
        })

    except Exception as e:
        return JSONResponse({"error": str(e), "where": "chart"}, status_code=500)
