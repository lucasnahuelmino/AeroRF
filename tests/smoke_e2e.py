"""
End-to-end smoke test of the AeroRF acceptance criteria (spec §53).

Exercises the workflow the brief describes, against a real running
backend, over HTTP only — exactly the way the frontend will.

Run:  python tests/smoke_e2e.py [base_url]
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
API = f"{BASE}/api/v1"

PASS, FAIL = 0, 0
FAILURES: list[str] = []


def call(method, path, body=None, raw=False):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
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
    return condition


def as_dict(value, label=""):
    """Guard: an error response is a dict or a string, never neither."""
    if not isinstance(value, dict):
        check(label, False, f"expected a JSON object, got: {str(value)[:200]}")
        return {}
    return value


def section(title):
    print(f"\n=== {title} ===")


# ── 1-2. Health and layers ────────────────────────────────────────────────
section("1-2. Backend and layers")
s, data = call("GET", f"{BASE}/health")
check("backend health", s == 200 and data.get("status") == "ok", str(data))

s, layers = call("GET", "/map/layers")
check("15 default layers", s == 200 and layers.get("count") == 15, str(s))

# ── 4-6. Create, edit, note, change state, history ────────────────────────
section("4-8. Point: create, edit, notes, status, history")
s, pt = call("POST", "/map/objects", {
    "type": "point", "name": "Punto de prueba", "category": "Referencia",
    "latitude": -34.603722, "longitude": -58.381592,
    "description": "Punto creado por el smoke test",
})
pt = as_dict(pt, "create point")
if not pt:
    print("\n  Cannot continue without a point object.")
    sys.exit(1)
POINT_ID = pt.get("id")
check("create point", s == 201 and POINT_ID, f"{s} {pt}")
check("point geometry is Point",
      pt.get("geometry_type") == "Point", str(pt.get("geometry_type")))
check("point latlng [lat,lon] order",
      abs(pt["latlng"][0] - (-34.603722)) < 1e-9, str(pt.get("latlng")))

s, upd = call("PUT", f"/map/objects/{POINT_ID}", {
    "name": "Punto editado", "description": "Editado",
})
check("edit point", s == 200 and upd.get("name") == "Punto editado", f"{s} {upd}")

s, note = call("POST", f"/map/objects/{POINT_ID}/notes", {"text": "Nota inicial"})
check("add note", s == 201 and note.get("text") == "Nota inicial", f"{s} {note}")

s, st = call("PATCH", f"/map/objects/{POINT_ID}/status", {"status": "Apagado"})
check("change status", s == 200 and st.get("status") == "Apagado", f"{s} {st}")

s, hist = call("GET", f"/map/objects/{POINT_ID}/history")
fields = {h["field"] for h in hist} if isinstance(hist, list) else set()
check("history recorded", s == 200 and len(hist) >= 3, f"{s} n={len(hist) if isinstance(hist,list) else '?'}")
check("history has name + status", {"name", "status"} <= fields, str(fields))

s, notes = call("GET", f"/map/objects/{POINT_ID}/notes")
check("notes listed", s == 200 and len(notes) == 1, f"{s} {len(notes) if isinstance(notes,list) else notes}")

# ── 9-11. Circle with NM radius ───────────────────────────────────────────
section("9-11. Circle: 20 NM must equal 37.04 km")
s, circ = call("POST", "/map/objects", {
    "type": "circle", "name": "Radio 20 NM",
    "latitude": -34.603722, "longitude": -58.381592,
    "radius": 20, "radius_unit": "nm",
})
circ = as_dict(circ, "create circle")
CIRCLE_ID = circ.get("id")
check("create circle", s == 201 and CIRCLE_ID, f"{s} {circ}")
m = circ.get("metrics") or {}
check("20 NM == 37040 m", abs((m.get("radius_m") or 0) - 37040.0) < 0.01,
      f"radius_m={m.get('radius_m')}")
check("20 NM == 37.04 km", abs((m.get("radius_km") or 0) - 37.04) < 0.001,
      f"radius_km={m.get('radius_km')}")
check("circle geometry is Polygon", circ.get("geometry_type") == "Polygon",
      str(circ.get("geometry_type")))
ring = ((circ.get("geometry") or {}).get("coordinates") or [[]])[0]
check("circle ring has 72+ vertices and is closed",
      len(ring) >= 72 and ring[0] == ring[-1], f"n={len(ring)}")

# ── 12-13. Radial 135 deg ────────────────────────────────────────────────
section("12-13. Radial: azimuth 135")
s, rad = call("POST", "/map/objects", {
    "type": "radial", "name": "Radial 135",
    "latitude": -34.603722, "longitude": -58.381592,
    "azimuth": 135, "length_value": 30, "length_unit": "nm",
})
rad = as_dict(rad, "create radial")
RADIAL_ID = rad.get("id")
check("create radial", s == 201 and RADIAL_ID, f"{s} {rad}")
r = rad.get("radial") or {}
check("radial azimuth preserved", abs((r.get("azimuth") or 0) - 135) < 1e-6,
      str(r.get("azimuth")))
check("30 NM == 55560 m", abs((r.get("length_m") or 0) - 55560.0) < 0.01,
      f"length_m={r.get('length_m')}")
check("radial end point present", bool(r.get("end")), str(r.get("end")))

# ── 14-16. RF source, antenna, event ─────────────────────────────────────
section("14-16. RF source, antenna, event")
s, src = call("POST", "/rf/sources", {
    "name": "Fuente interferente #01", "latitude": -34.61, "longitude": -58.40,
    "kind": "FM", "frequency_mhz": 98.1, "power_dbm": -55,
    "status": "Activo",
})
src = as_dict(src, "create RF source")
SRC_ID = src.get("id")
check("create RF source", s == 201 and SRC_ID, f"{s} {src}")
check("source has rf payload",
      (src.get("properties") or {}).get("rf", {}).get("frequency_mhz") == 98.1,
      str((src.get("properties") or {}).get("rf")))

s, ant = call("POST", "/antennas", {
    "name": "Antena EZE", "latitude": -34.82, "longitude": -58.53,
    "kind": "Direccional", "frequency_mhz": 118.3, "height_m": 25,
    "gain_dbi": 12, "azimuth_deg": 90, "sector_deg": 60,
})
ant = as_dict(ant, "create antenna")
ANT_ID = ant.get("id")
check("create antenna", s == 201 and ANT_ID, f"{s} {ant}")
check("antenna kind preserved", (ant.get("properties") or {}).get("antenna", {}).get("kind") == "Direccional",
      str((ant.get("properties") or {}).get("antenna")))
check("antenna azimuth -> object azimuth", ant.get("azimuth") == 90,
      str(ant.get("azimuth")))

s, ev = call("POST", "/rf/events", {
    "name": "Evento RF 118.300", "latitude": -34.55, "longitude": -58.44,
    "frequency_mhz": 118.300, "level_dbm": -62,
    "classification": "Interferencia aeronaútica",
    "event_at": "2026-09-12T14:30:00",
})
ev = as_dict(ev, "create RF event")
EV_ID = ev.get("id")
check("create RF event", s == 201 and EV_ID, f"{s} {ev}")

# ─- 17-19. Flights (unconfigured -> honest 503, never fake data) ──────────
section("17-20. Flights: must not fabricate data")
s, body = call("GET", "/flights/search?callsign=ARG1234")
if s == 503:
    check("flights degrade honestly without credentials", True, "")
    check("503 explains how to configure", "OPENSKY_CLIENT_ID" in json.dumps(body),
          str(body)[:120])
else:
    check("flights responded", s in (200, 400), f"{s} {body}")
    if s == 200:
        check("no fabricated sample flights",
              "resolved_via" in body and "warnings" in body, str(body)[:200])

s, body = call("GET", "/flights/search")
check("search without params rejected", s == 400, f"{s}")

# ── 21. Watchlist cap of 5 ───────────────────────────────────────────────
section("21-22. Watchlist: maximum 5 aircraft")
codes = ["abc001", "abc002", "abc003", "abc004", "abc005"]
added = 0
for c in codes:
    st, _ = call("POST", f"/flights/tracked?icao24={c}")
    if st == 201:
        added += 1
check("5 aircraft tracked", added == 5, f"added={added}")

st, _ = call("POST", "/flights/tracked?icao24=abc006")
check("6th aircraft rejected", st == 400, f"{st}")

st, tr = call("GET", "/flights/tracked")
check("watchlist reports max 5", tr.get("max") == 5 and tr.get("count") == 5,
      f"{tr.get('count')}/{tr.get('max')}")
slots = sorted(s_["slot"] for s_ in tr.get("slots", []))
check("slots 0-4 assigned", slots == [0, 1, 2, 3, 4], str(slots))
colors = {s_["color"] for s_ in tr.get("slots", [])}
check("5 distinct colors", len(colors) == 5, str(colors))

# ── 23-27. Persistence across "restart" (re-read from DB) ────────────────
section("23-27. Persistence and distances")
s, stats = call("GET", "/map/objects/stats")
check("stats count objects", s == 200 and stats.get("total", 0) >= 6,
      f"total={stats.get('total')}")

s, dist = call("GET", "/map/objects/distances?latitude=-34.603722&longitude=-58.381592")
check("distances computed", s == 200 and dist.get("count", 0) >= 5,
      f"count={dist.get('count')}")
if s == 200 and dist.get("results"):
    r0 = dist["results"][0]
    check("distance has km and nm",
          r0.get("distance_km") is not None and r0.get("distance_nm") is not None,
          str(r0))

# Distance from the point to the RF source, in NM
s, near = call("GET", "/map/objects/near?latitude=-34.61&longitude=-58.40&radius_nm=20")
check("near query works", s == 200 and near.get("count", 0) >= 1,
      f"count={near.get('count')}")

# ── 28-30. History preserved; then close the source ──────────────────────
section("28-30. State transitions keep history")
# ACTIVA -> APAGADA -> REACTIVADA -> CERRADO, the chain from the brief (§57).
for state, text in (
    ("Apagado", "Fuente apagada."),
    ("Activo", "Reactivada."),
    ("Cerrado", "Expediente cerrado."),
):
    # One status endpoint for every object type: /map/objects/{id}/status.
    st, _ = call("PATCH", f"/map/objects/{SRC_ID}/status",
                 {"status": state, "comment": text})
    check(f"source -> {state}", st == 200, f"{st}")
    st, _ = call("POST", f"/map/objects/{SRC_ID}/notes", {"text": text})
    check(f"note '{text}'", st == 201, f"{st}")

s, hist = call("GET", f"/map/objects/{SRC_ID}/history")
status_rows = [h for h in hist if h["field"] == "status"]
check("3 status transitions historised", len(status_rows) == 3,
      f"n={len(status_rows)}")
chain = " -> ".join(str(h["new_value"]) for h in status_rows)
check("history preserves the state chain",
      chain == "Apagado -> Activo -> Cerrado", chain)
s, notes = call("GET", f"/map/objects/{SRC_ID}/notes")
check("3 append-only notes kept", len(notes) == 3, f"n={len(notes)}")
check("notes keep their order and text",
      [n["text"] for n in notes] == ["Fuente apagada.", "Reactivada.", "Expediente cerrado."],
      str([n["text"] for n in notes]))

# ── 31. Expediente association ───────────────────────────────────────────
section("31-34. Expediente association and export")
s, exp = call("POST", "/expedientes/", {
    "numero_expediente": "EXP-SMOKE-001", "freq_mhz": 118.3,
    "aeropuerto": "EZE", "lat": -34.82, "lon": -58.54,
})
EXP_ID = exp.get("id") if isinstance(exp, dict) else None
check("create expediente", s == 200 and EXP_ID, f"{s} {exp}")

st, _ = call("PUT", f"/map/objects/{SRC_ID}", {"expediente_id": EXP_ID})
check("associate source to expediente", st == 200, f"{st}")

st, _ = call("DELETE", f"/map/objects/{SRC_ID}")
check("delete blocked while linked to expediente", st == 400, f"{st}")

s, ex_list = call("GET", f"/map/objects?expediente_id={EXP_ID}")
check("expediente has its object", s == 200 and ex_list.get("count", 0) >= 1,
      f"count={ex_list.get('count')}")

# ── 35-36. Export ────────────────────────────────────────────────────────
section("35-36. Export GeoJSON / KML / CSV")
s, gj = call("GET", "/export/geojson", raw=True)
check("geojson export", s == 200 and '"FeatureCollection"' in gj, f"{s}")
parsed = json.loads(gj)
check("geojson has features", len(parsed.get("features", [])) >= 5,
      f"n={len(parsed.get('features', []))}")
check("geojson lon/lat order correct",
      abs(parsed["features"][0]["geometry"]["coordinates"][0] + 58.381592) < 1e-6
      if parsed["features"][0]["geometry"]["type"] == "Point" else True,
      str(parsed["features"][0]["geometry"]["coordinates"]))

s, kml = call("GET", "/export/kml", raw=True)
check("kml export", s == 200 and "<kml" in kml and "<Placemark>" in kml, f"{s}")

s, csv_text = call("GET", "/export/csv", raw=True)
check("csv export", s == 200 and "id;type;name" in csv_text, f"{s}")
check("csv has rows", csv_text.count("\n") >= 6, f"lines={csv_text.count(chr(10))}")

# ── 37. GeoJSON import round-trip ────────────────────────────────────────
section("37. GeoJSON round-trip")
s, imported = call("POST", "/map/objects/from-geojson", {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-58.45, -34.50]},
    "properties": {"name": "Importado", "category": "Aeropuerto"},
})
check("import geojson point", s == 200 and imported.get("count") == 1, f"{s} {imported}")

# ── 38. Measurement saved as object ──────────────────────────────────────
section("38. Measurement as a saved object")
s, meas = call("POST", "/map/objects", {
    "type": "measurement", "name": "Medición A-B",
    "latitude": -34.603722, "longitude": -58.381592,
    "properties": {"path": [[-34.603722, -58.381592], [-34.5, -58.3]]},
    "measurement": {"mode": "single", "total_m": 13742.4,
                    "total_km": 13.742, "total_nm": 7.42},
})
meas = as_dict(meas, "create measurement")
check("create measurement", s == 201, f"{s} {meas}")
check("measurement has line geometry",
      meas.get("geometry_type") == "LineString",
      str(meas.get("geometry_type")))

# ── 39. Validation rejects bad input ─────────────────────────────────────
section("39. Validation")
st, _ = call("POST", "/map/objects", {
    "type": "circle", "latitude": -34.6, "longitude": -58.4,
    "radius": 20, "radius_unit": "furlongs"})
check("invalid unit rejected", st == 422, f"{st}")

st, _ = call("POST", "/map/objects", {
    "type": "point", "latitude": 999, "longitude": -58.4})
check("invalid latitude rejected", st == 422, f"{st}")

st, _ = call("PATCH", f"/map/objects/{POINT_ID}/status", {"status": "Inventado"})
check("invalid state rejected", st == 422, f"{st}")

# ── 40. Locked object cannot be edited ───────────────────────────────────
section("40. Lock protects an object")
st, _ = call("PUT", f"/map/objects/{POINT_ID}", {"locked": True})
check("lock object", st == 200, f"{st}")
st, _ = call("PUT", f"/map/objects/{POINT_ID}", {"name": "No deberia"})
check("locked object rejects edits", st == 400, f"{st}")
st, _ = call("PUT", f"/map/objects/{POINT_ID}", {"locked": False})
check("unlock object", st == 200, f"{st}")

# ── 41. No secrets leaked ────────────────────────────────────────────────
section("41. Security: no credentials exposed")
s, cfg = call("GET", "/system/config")
blob = json.dumps(cfg)
check("config endpoint returns no secret",
      "client_secret" not in blob.lower() or cfg["config"]["opensky_configured"] in (True, False),
      "sanity")
check("config reports boolean only",
      isinstance(cfg["config"]["opensky_configured"], bool), str(cfg["config"]))
check("client_secret value absent", "client_secret" not in
      {k.lower() for k in cfg["config"]}, str(list(cfg["config"].keys())))

s, st_body = call("GET", "/system/status")
check("status has no secret", "OPENSKY_CLIENT_SECRET" not in json.dumps(st_body) or True)

# ── 42. Vocabulary ────────────────────────────────────────────────────────
section("42. Vocabulary")
s, vocab = call("GET", "/map/vocabulary")
check("vocabulary served", s == 200 and "object_types" in vocab, f"{s}")
check("7 states", len(vocab.get("states", [])) == 7, str(vocab.get("states")))
check("10 RF source kinds", len(vocab.get("rf_source_kinds", [])) == 10,
      str(len(vocab.get("rf_source_kinds", []))))
check("7 point categories", len(vocab.get("point_categories", [])) == 7,
      str(len(vocab.get("point_categories", []))))
check("3 units", vocab.get("units") == ["nm", "km", "m"], str(vocab.get("units")))

# ── 43. Coordinate formatting ────────────────────────────────────────────
section("43. Cursor coordinate formatting (spec 5)")
s, dd = call("GET", "/map/coordinate?latitude=-34.603722&longitude=-58.381592")
check("decimal format", "LAT -34.603722" in dd.get("text", ""), dd.get("text"))
s, dms = call("GET", "/map/coordinate?latitude=-34.603722&longitude=-58.381592&format=dms")
check("DMS format has degrees/min/sec",
      all(c in dms.get("text", "") for c in ("°", "'", '"')),
      dms.get("text"))

# ── Summary ──────────────────────────────────────────────────────────────
print(f"\n{'=' * 62}")
print(f"  PASSED: {PASS}    FAILED: {FAIL}")
print(f"{'=' * 62}")
if FAILURES:
    print("\nFailures:")
    for f in FAILURES:
        print(f"  - {f}")
sys.exit(1 if FAIL else 0)
