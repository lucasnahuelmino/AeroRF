/**
 * tests/geo_parity.mjs
 * ────────────────────
 * Cross-checks the frontend geodesy against the backend.
 *
 * The map, the inspector, the status bar and the exports all quote the
 * same numbers. If the JS and the Python disagreed by even one decimal
 * place, an operator reading the cursor bar would see a different value
 * from the one in the popup, and the reported distances in an ENACOM
 * expediente would not match the screen.
 *
 * This script asks Node to compute a set of vectors, asks Python to
 * compute the same ones, and compares them. Run it after any change to
 * `app/core/geo.py`, `app/core/units.py` or `frontend/src/map/geo.js`:
 *
 *     node tests/geo_parity.mjs
 */

import { execFileSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')

// pathToFileURL: on Windows an absolute path has a `c:` scheme that the
// ESM loader rejects.
const geo = await import(
  pathToFileURL(path.join(root, 'frontend/src/map/geo.js')).href
)

let pass = 0
let fail = 0

function compare(label, jsValue, pyValue, tolerance = 1e-6) {
  const js = typeof jsValue === 'number' ? jsValue : Number(jsValue)
  const py = typeof pyValue === 'number' ? pyValue : Number(pyValue)
  const ok = Math.abs(js - py) <= tolerance * Math.max(1, Math.abs(py))
  if (ok) {
    pass += 1
    console.log(`  PASS  ${label}  (${js})`)
  } else {
    fail += 1
    console.log(`  FAIL  ${label}  js=${js}  py=${py}`)
  }
}

function compareText(label, jsValue, pyValue) {
  const ok = String(jsValue) === String(pyValue)
  if (ok) {
    pass += 1
    console.log(`  PASS  ${label}  «${jsValue}»`)
  } else {
    fail += 1
    console.log(`  FAIL  ${label}\n        js=«${jsValue}»\n        py=«${pyValue}»`)
  }
}

// ── Test vectors ─────────────────────────────────────────────────────────────
const POINTS = [
  [-34.603722, -58.381592],   // Buenos Aires
  [-34.8222, -58.5358],      // EZE
  [-31.3208, -64.1888],      // Córdoba
  [0, 0],
  [-54.8, -68.3],            // Ushuaia
  [51.5, -0.12],             // London
]
const BEARINGS = [0, 45, 90, 135, 180, 225, 270, 315]
const DISTANCES = [1852, 37040, 55560, 185_200, 1_000_000]
const COORD_FORMATS = [
  [-34.603722, -58.381592],
  [0, 0],
  [-54.8, -68.3],
  [51.47, -0.454],
]

// ── Ask Python ──────────────────────────────────────────────────────────────
const AZIMUTHS = [
  0, 45, 90, 135, 180, 225, 270, 315, 359.9,
  -0, -1, -45, -90, -180, -270, -359.9,
  360, 361, 450, 720, 1080, -720,
  180.0000001, -180.0000001, 1e-9, -1e-9,
]

const payload = JSON.stringify({ POINTS, BEARINGS, DISTANCES, COORD_FORMATS, AZIMUTHS })

const pyScript = `
import json, sys
sys.path.insert(0, ${JSON.stringify(root)})
from app.core import geo, units

data = json.loads(sys.stdin.read())
out = {
    "haversine": [],
    "bearing": [],
    "destination": [],
    "to_metres": [],
    "format_latlon": {},
    "circle_points": [],
    "normalise_azimuth": [],
    "compass_point": [],
}
for a in data["POINTS"]:
    for b in data["POINTS"]:
        out["haversine"].append(geo.haversine_m(a[0], a[1], b[0], b[1]))
for a in data["POINTS"]:
    for b in data["POINTS"]:
        out["bearing"].append(geo.initial_bearing(a[0], a[1], b[0], b[1]))
for a in data["POINTS"]:
    for az in data["BEARINGS"]:
        for d in data["DISTANCES"]:
            out["destination"].append(list(geo.destination_point(a[0], a[1], az, d)))
for d in data["DISTANCES"]:
    for u in ("nm", "km", "m"):
        out["to_metres"].append([d, u, units.to_metres(d, u)])
for pair in data["COORD_FORMATS"]:
    for fmt in ("dd", "dms", "dmm"):
        out["format_latlon"][fmt + ":" + str(pair)] = geo.format_latlon(pair[0], pair[1], fmt)
for a in data["POINTS"]:
    out["circle_points"].append([[c[0], c[1]] for c in geo.circle_points(a[0], a[1], 18520, steps=24)])
for az in data["AZIMUTHS"]:
    out["normalise_azimuth"].append(units.normalise_azimuth(az))
    out["compass_point"].append(units.compass_point(az))
print(json.dumps(out))
`

let py
try {
  const python = process.env.AERORF_PYTHON || path.join(root, '.venv/Scripts/python.exe')
  py = JSON.parse(
    execFileSync(python, ['-c', pyScript], {
      input: payload,
      cwd: root,
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
    }),
  )
} catch (err) {
  console.error('Could not run the Python side of the parity check.')
  console.error(err.stderr?.toString?.() || err.message)
  process.exit(2)
}

// ── Distances ───────────────────────────────────────────────────────────────
console.log('\n=== haversine ===')
let i = 0
for (const a of POINTS) {
  for (const b of POINTS) {
    compare(
      `haversine(${a}, ${b})`,
      geo.haversine(a[0], a[1], b[0], b[1]),
      py.haversine[i],
      1e-9,
    )
    i += 1
  }
}

// ── Bearings ────────────────────────────────────────────────────────────────
console.log('\n=== initial bearing ===')
i = 0
for (const a of POINTS) {
  for (const b of POINTS) {
    compare(
      `bearing(${a}, ${b})`,
      geo.bearing(a[0], a[1], b[0], b[1]),
      py.bearing[i],
      1e-9,
    )
    i += 1
  }
}

// ── Destination ─────────────────────────────────────────────────────────────
console.log('\n=== destination point ===')
i = 0
for (const a of POINTS) {
  for (const az of BEARINGS) {
    for (const d of DISTANCES) {
      const js = geo.destination(a[0], a[1], az, d)
      compare(`dest lat ${a} az=${az} d=${d}`, js[0], py.destination[i][0], 1e-9)
      compare(`dest lon ${a} az=${az} d=${d}`, js[1], py.destination[i][1], 1e-9)
      i += 1
    }
  }
}

// ── Unit conversion ─────────────────────────────────────────────────────────
console.log('\n=== unit conversion ===')
i = 0
for (const d of DISTANCES) {
  for (const u of ['nm', 'km', 'm']) {
    compare(`toMetres(${d}, ${u})`, geo.toMetres(d, u), py.to_metres[i][2], 1e-12)
    i += 1
  }
}

console.log('\n=== the spec example: 20 NM ===')
compare('20 NM in km', geo.nmToKm(20), 37.04, 1e-12)
compare('20 NM in m', geo.toMetres(20, 'nm'), 37040, 1e-12)

// ── Coordinate formatting (must be byte-identical) ──────────────────────────
console.log('\n=== coordinate formatting (exact text match) ===')
for (const [lat, lon] of COORD_FORMATS) {
  for (const fmt of ['dd', 'dms', 'dmm']) {
    const key = `${fmt}:${JSON.stringify([lat, lon])}`
    // The Python side keyed on str(tuple); rebuild the same key.
    const pyKey = Object.keys(py.format_latlon).find((k) =>
      k.startsWith(`${fmt}:`) &&
      k.slice(fmt.length + 1) === JSON.stringify([lat, lon]).replace(/"/g, ''),
    )
    const pyValue = pyKey ? py.format_latlon[pyKey] : null
    if (pyValue === null) {
      console.log(`  SKIP  ${fmt} (${lat}, ${lon}) — no Python counterpart`)
      continue
    }
    compareText(`formatLatLon(${lat}, ${lon}, ${fmt})`, geo.formatLatLon(lat, lon, fmt), pyValue)
  }
}

// ── Circle geometry ─────────────────────────────────────────────────────────
console.log('\n=== circle vertices ===')
i = 0
for (const a of POINTS) {
  const js = geo.circlePoints(a[0], a[1], 18520, 24)
  const pyPts = py.circle_points[i]
  let worst = 0
  for (let k = 0; k < Math.min(js.length, pyPts.length); k += 1) {
    worst = Math.max(worst, Math.abs(js[k][0] - pyPts[k][0]))
    worst = Math.max(worst, Math.abs(js[k][1] - pyPts[k][1]))
  }
  compare(`circlePoints(${a}, 10 NM, 24) max vertex delta`, worst, 0, 1e-9)
  i += 1
}

// ── Round-trip: a point reached by a radial is the stated distance away ──────
console.log('\n=== radial round-trip ===')
{
  const origin = [-34.603722, -58.381592]
  for (const az of BEARINGS) {
    for (const d of DISTANCES) {
      const end = geo.destination(origin[0], origin[1], az, d)
      const back = geo.haversine(origin[0], origin[1], end[0], end[1])
      compare(`radial ${az}° ${d} m round-trip`, back, d, 1e-9)
    }
  }
}

// ── Summary ─────────────────────────────────────────────────────────────────
// Azimuth normalisation -- regression guard, and the reason this block
// exists at all.
//
// JavaScript's `%` keeps the sign of the dividend: `-90 % 360` is `-90`.
// Python's does not: `-90 % 360` is `270`. A single `%` on the JS side
// therefore made the two implementations disagree for every negative
// azimuth, and nothing caught it because this script never exercised the
// function. Negative azimuths are reachable from the UI: the operator can
// type -45 in the radial options.
//
// The vectors deliberately include negatives, values past 360, exact
// multiples of 360, and the +/-180 seam.

console.log('\n=== azimuth normalisation ===')
i = 0
for (const az of AZIMUTHS) {
  compare(
    `normaliseAzimuth(${az})`,
    geo.normaliseAzimuth(az),
    py.normalise_azimuth[i],
    1e-12,
  )
  i += 1
}

// The compass label has to agree too, or the map and the status bar would
// name the same direction differently.
console.log('\n=== compass labels ===')
i = 0
for (const az of AZIMUTHS) {
  compareText(`compassPoint(${az})`, geo.compassPoint(az), py.compass_point[i])
  i += 1
}

// A radial drawn at a negative azimuth must land where the equivalent
// positive one does. This is the consequence that actually matters.
console.log('\n=== negative azimuths place geometry identically ===')
{
  const origin = [-34.603722, -58.381592]
  for (const [negative, positive] of [[-90, 270], [-45, 315], [-180, 180], [-315, 45]]) {
    const a = geo.destination(origin[0], origin[1], negative, 37040)
    const b = geo.destination(origin[0], origin[1], positive, 37040)
    compare(`dest ${negative} deg vs ${positive} deg lat`, a[0], b[0], 1e-12)
    compare(`dest ${negative} deg vs ${positive} deg lon`, a[1], b[1], 1e-12)
  }
}

console.log(`\n${'='.repeat(60)}`)
console.log(`  PASSED: ${pass}    FAILED: ${fail}`)
console.log(`${'='.repeat(60)}`)
process.exit(fail ? 1 : 0)
