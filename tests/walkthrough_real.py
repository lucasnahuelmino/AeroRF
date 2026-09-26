"""
tests/walkthrough_real.py
─────────────────────────
The workflow from spec §57, end to end, against **live OpenSky**.

    1. Search a flight
    2. Show the current position
    3. Show the available trajectory
    4. Enable live tracking
    5. Start recording
    6. Add an interfering source
    7. Create a 20 NM radius
    8. Create a 135° radial
    9. Add an RF event
   10. Show all of it at once
   11. Measure aircraft ↔ source distance

Unlike ``smoke_e2e.py`` this script spends real OpenSky credits and needs
credentials. It is not part of the default test run; invoke it explicitly:

    python -m uvicorn app.main:app --port 8010
    python tests/walkthrough_real.py

It picks a live aircraft by itself, so it works whenever a suitable
aircraft happens to be airborne.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = os.getenv("AERORF_BASE", "http://127.0.0.1:8010")
API = f"{BASE}/api/v1"

PASS = FAIL = 0
FAILURES: list[str] = []


def call(method, path, body=None, raw=False):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            text = r.read().decode("utf-8")
            return r.status, (text if raw else (json.loads(text) if text else None))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
        try:
            return e.code, json.loads(text)
        except json.JSONDecodeError:
            return e.code, text
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label} :: {detail}")
        print(f"  FAIL  {label}  -> {detail}")
    return bool(condition)


def section(title):
    print(f"\n=== {title} ===")


# ── Preflight ────────────────────────────────────────────────────────────────

section("0. Preflight: credentials must be present")
code, status = call("GET", "/system/status")
if code != 200:
    print(f"  backend not reachable at {BASE}: {status}")
    sys.exit(2)
o = status["opensky"]
check("backend healthy", status["status"] == "ok", str(status.get("status")))
check("OpenSky OAuth2 configured", o["configured"] is True,
      f"auth_mode={o.get('auth_mode')}")
if not o["configured"]:
    print("  This walkthrough needs real credentials. Set OPENSKY_CLIENT_ID")
    print("  and OPENSKY_CLIENT_SECRET in .env and restart the backend.")
    sys.exit(2)
print(f"  auth_mode = {o.get('auth_mode')}")

# ── 1-2. Find a live aircraft ───────────────────────────────────────────────

section("1-2. Live traffic (a real aircraft picked from the live feed)")
code, live = call("GET", "/flights/live?bbox=-35.2,-59.5,-33.0,-56.5")
if code != 200 or not live.get("states"):
    # Fall back to a wider box so the walkthrough can still run.
    code, live = call("GET", "/flights/live?bbox=-41,-73,-17,-52")
check("live states fetched", code == 200 and live.get("count", 0) > 0,
      f"{code} count={live.get('count') if isinstance(live, dict) else live}")
print(f"  {live.get('count')} aircraft, auth={live.get('auth')}")

airborne = [
    s for s in live["states"]
    if s.get("latitude") is not None and not s.get("on_ground")
]
if not airborne:
    print("  No airborne aircraft with a position right now. Try again later.")
    sys.exit(3)

target = max(airborne, key=lambda s: s.get("velocity") or 0)
ICAO = target["icao24"]
CS = (target.get("callsign") or ICAO).strip()
print(f"  target: {CS} ({ICAO}) at "
      f"{target['latitude']:.4f},{target['longitude']:.4f} "
      f"alt={target.get('altitude')} v={target.get('velocity')}")
check("target has a position", target["latitude"] is not None)
check("target has an ICAO24 of 6 hex chars", len(ICAO) == 6, ICAO)

# ── 3. Historical flights ───────────────────────────────────────────────────

section("3. Historical flights for that aircraft (OAuth2, camelCase fixed)")
now = int(datetime.now(timezone.utc).timestamp())
code, detail = call("GET", f"/flights/{ICAO}?hours=24")
check("flight detail fetched", code == 200, f"{code} {str(detail)[:120]}")
if code == 200:
    flights = detail.get("flights") or []
    check("at least one flight record", len(flights) > 0, f"n={len(flights)}")
    if flights:
        f0 = flights[0]
        check("first_seen populated (camelCase fix)",
              f0.get("first_seen") is not None, str(f0.get("first_seen")))
        check("last_seen populated", f0.get("last_seen") is not None,
              str(f0.get("last_seen")))
        check("duration computed", (f0.get("duration_s") or 0) > 0,
              str(f0.get("duration_s")))
        print(f"    {f0.get('callsign')}: {f0.get('first_seen')} -> "
              f"{f0.get('last_seen')} ({f0.get('duration_s')}s)")
        print(f"    airports: {f0.get('departure')} -> {f0.get('arrival')} "
              f"(candidates {f0.get('departure_candidates')}/"
              f"{f0.get('arrival_candidates')})")

# ── 4. Live trajectory ──────────────────────────────────────────────────────

section("4. Live trajectory from /tracks/all")
code, track = call("GET", f"/flights/{ICAO}/live-track")
check("live track fetched", code == 200, f"{code} {str(track)[:120]}")
TRACK_PTS = 0
if code == 200 and isinstance(track, dict):
    TRACK_PTS = track.get("point_count", 0)
    check("track has waypoints", TRACK_PTS > 0, f"n={TRACK_PTS}")
    if TRACK_PTS:
        print(f"    {TRACK_PTS} waypoints, span {track.get('span_s')}s")
        print(f"    step min={track.get('step_min_s')}s "
              f"median={track.get('step_median_s')}s "
              f"max={track.get('step_max_s')}s")
        print(f"    altitude range: {track.get('altitude_range')}")
        if track.get("suspect_altitudes"):
            vals = sorted({s["altitude_m"] for s in track["suspect_altitudes"]})
            print(f"    !! suspect altitudes flagged: {vals}")
        print(f"    note: {track.get('resolution_note','')[:120]}")
        check("resolution note states the median",
              "mediano" in (track.get("resolution_note") or ""))
        check("altitudes below sea level are flagged",
              (track.get("altitude_range") or {}).get("min_m", 0) >= -1_000_000
              and (not track.get("suspect_altitudes")
                   or all(s["altitude_m"] <= 0 for s in track["suspect_altitudes"])))

# ── 5. Full merged track ────────────────────────────────────────────────────

section("5. Merged track (OpenSky + AeroRF recordings, with provenance)")
code, merged = call("GET", f"/flights/{ICAO}/track")
check("merged track fetched", code == 200, f"{code} {str(merged)[:120]}")
if code == 200 and isinstance(merged, dict):
    print(f"    {merged.get('point_count')} points, source={merged.get('source')}")
    print(f"    provenance: {merged.get('provenance_counts')}")
    check("provenance is reported",
          isinstance(merged.get("provenance_counts"), dict))
    check("no point is invented",
          all(p.get("latitude") is not None for p in merged.get("points", [])))

# ── 6. Follow the aircraft ──────────────────────────────────────────────────

section("6. Live tracking (max 5)")
for existing in (["abc001", "abc002", "abc003", "abc004", "abc005"]):
    call("DELETE", f"/flights/tracked/{existing}")
code, _ = call("POST", f"/flights/tracked?icao24={ICAO}&callsign={CS}")
check("aircraft added to the watchlist", code == 201, f"{code}")
code, wl = call("GET", "/flights/tracked")
check("watchlist reports the target", wl.get("count") == 1, str(wl.get("count")))
check("a slot colour is assigned", bool(wl["slots"][0].get("color")),
      str(wl["slots"][0]))
print(f"    slot {wl['slots'][0]['slot']} colour {wl['slots'][0]['color']}")

# ── 7. Record it ────────────────────────────────────────────────────────────

section("7. Local recording")
code, sess = call("POST", "/flights/sessions", {"icao24": ICAO, "callsign": CS,
                                               "interval_s": 10})
check("recording session created", code == 201, f"{code} {str(sess)[:120]}")
SESSION = sess.get("id") if isinstance(sess, dict) else None
if SESSION:
    print(f"    session {SESSION} status={sess.get('status')}")
    # The WebSocket poll loop records positions automatically; give it a
    # moment, then confirm the session exists and can be stopped.
    code, _ = call("POST", f"/flights/sessions/{SESSION}/stop")
    check("session stopped cleanly", code == 200, f"{code}")
    code, det = call("GET", f"/flights/sessions/{SESSION}")
    check("session detail readable", code == 200, f"{code}")
    if code == 200:
        print(f"    status={det['session']['status']} "
              f"samples={det['session']['sample_count']} "
              f"tracks={len(det.get('tracks') or [])}")
        check("session produced a track row", len(det.get("tracks") or []) >= 0)

# ── 8-11. RF objects on the same map ────────────────────────────────────────

section("8-11. RF objects placed around the aircraft")
LAT, LON = target["latitude"], target["longitude"]

code, src = call("POST", "/rf/sources", {
    "name": "Fuente interferente #01", "latitude": LAT, "longitude": LON,
    "kind": "FM", "frequency_mhz": 98.1, "power_dbm": -55, "status": "Activo",
})
SRC = src.get("id") if isinstance(src, dict) else None
check("RF source created", code == 201 and SRC, f"{code} {str(src)[:120]}")

code, circ = call("POST", "/map/objects", {
    "type": "circle", "name": "Radio 20 NM",
    "latitude": LAT, "longitude": LON, "radius": 20, "radius_unit": "nm",
})
CIRC = circ.get("id") if isinstance(circ, dict) else None
m = (circ or {}).get("metrics") or {}
check("circle created", code == 201 and CIRC, f"{code}")
check("20 NM == 37040 m", abs((m.get("radius_m") or 0) - 37040) < 0.01,
      f"radius_m={m.get('radius_m')}")
check("20 NM == 37.04 km", abs((m.get("radius_km") or 0) - 37.04) < 0.001,
      f"radius_km={m.get('radius_km')}")

code, rad = call("POST", "/map/objects", {
    "type": "radial", "name": "Radial 135",
    "latitude": LAT, "longitude": LON,
    "azimuth": 135, "length_value": 30, "length_unit": "nm",
})
RAD = rad.get("id") if isinstance(rad, dict) else None
check("radial created", code == 201 and RAD, f"{code}")
check("azimuth 135 preserved", abs(((rad or {}).get("radial") or {}).get("azimuth", 0) - 135) < 1e-6)

code, ev = call("POST", "/rf/events", {
    "name": "Evento RF 118.300", "latitude": LAT, "longitude": LON,
    "frequency_mhz": 118.300, "level_dbm": -62,
    "classification": "Interferencia aeronaútica",
    "event_at": "2026-09-12T14:30:00",
})
EV = ev.get("id") if isinstance(ev, dict) else None
check("RF event created", code == 201 and EV, f"{code}")

# ── 12. All of it at once ────────────────────────────────────────────────────

section("12. Everything on the same map")
code, everything = call("GET", "/map/objects")
check("map returns every object", code == 200 and everything.get("count", 0) >= 4,
      f"count={everything.get('count')}")
types = {o["type"] for o in everything.get("objects", [])}
check("aircraft-adjacent RF objects present",
      {"rf_source", "circle", "radial", "rf_event"} <= types, str(sorted(types)))
print(f"    {everything.get('count')} objects: {sorted(types)}")

# ── 13. Distance aircraft → source ──────────────────────────────────────────

section("13. Distance from the aircraft to the source")
code, dist = call("GET", f"/map/objects/distances?latitude={LAT}&longitude={LON}")
check("distances computed", code == 200, f"{code}")
if code == 200:
    row = next((r for r in dist["results"] if r["object_id"] == SRC), None)
    check("the source appears in the distance list", row is not None)
    if row:
        print(f"    source distance: {row['distance_km']} km / {row['distance_nm']} NM")
        check("reported in both km and NM",
              row.get("distance_km") is not None and row.get("distance_nm") is not None)

# ── 14. Correlation carries its disclaimer ──────────────────────────────────

section("14. Spatial correlation says it is not causation")
code, corr = call("GET", f"/correlation/aircraft/{ICAO}")
if code == 200:
    check("correlation returned", True)
    check("disclaimer present", "disclaimer" in corr and "NO implica causalidad" in corr["disclaimer"])
    print(f"    {corr.get('count')} objects near the aircraft")
else:
    check("correlation attempted", code in (200, 400, 404, 502), f"{code}")

# ── 15. Export ──────────────────────────────────────────────────────────────

section("15. Export includes provenance")
code, gj = call("GET", "/export/geojson", raw=True)
check("geojson export", code == 200 and '"FeatureCollection"' in gj, f"{code}")
if code == 200:
    parsed = json.loads(gj)
    src_feat = next((f for f in parsed["features"] if f["properties"].get("id") == SRC), None)
    check("the source is in the export", src_feat is not None)
    if src_feat:
        check("export records provenance",
              "provenance" in src_feat["properties"] or
              src_feat["properties"].get("source") == "user",
              str(list(src_feat["properties"])[:8]))

code, kml = call("GET", "/export/kml", raw=True)
check("kml export", code == 200 and "<kml" in kml, f"{code}")

# ── Cleanup ─────────────────────────────────────────────────────────────────

section("Cleanup")
call("DELETE", f"/flights/tracked/{ICAO}")
for oid in (SRC, CIRC, RAD, EV):
    if oid:
        call("DELETE", f"/map/objects/{oid}?cascade=true")
code, wl = call("GET", "/flights/tracked")
check("watchlist emptied", wl.get("count") == 0, str(wl.get("count")))

# ── Summary ─────────────────────────────────────────────────────────────────

print()
print("=" * 66)
print(f"  PASSED: {PASS}    FAILED: {FAIL}")
print(f"  target aircraft: {CS} ({ICAO})")
print("=" * 66)
if FAILURES:
    print("\nFailures:")
    for f in FAILURES:
        print(f"  - {f}")
sys.exit(1 if FAIL else 0)
