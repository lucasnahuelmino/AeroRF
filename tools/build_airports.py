"""
Generate src/data/airports.js from OurAirports.

The point of generating rather than hand-writing is that hand-writing
produced a file with four duplicated ICAO codes, four duplicated IATA codes,
two sets of identical coordinates under different names, and stray characters.
All of it looked plausible. A reference file that invents aerodromes is worse
than no reference file at all: an operator measuring interference protection
around a wrong ARP would produce a wrong report with total confidence.

So: the coordinates and codes come from OurAirports (public domain), and this
script is the only thing allowed to write the file.
"""
import csv, io, json, os

# Aerodromes chosen for aeronautical radio work: the ones with real traffic
# and the ones near the Argentine FIR boundaries, where interference from
# across the border shows up. Sorted by relevance within each country.
#
# A token is matched against the published `icao_code` first and against
# `gps_code` second. The second is not a convenience: some aerodromes that are
# genuinely in service publish no ICAO code at all, and San Fernando is one of
# them. Its ARP is published, so it belongs in the layer, and `gps_code` is the
# code OurAirports publishes for it. Nothing is invented either way — a token
# that matches nothing is reported and dropped.
SELECTED = {
    "AR": [
        # Large: the ones with heavy traffic and a full TWR/APP.
        "SAEZ",  # Ezeiza - the hub. Most Spanish-language traffic in the country.
        "SABE",  # Aeroparque - the other Buenos Aires field.
        "SACO",  # Cordoba
        "SAME",  # Mendoza
        "SAAR",  # Rosario
        "SASA",  # Salta
        "SANT",  # Tucuman
        "SARE",  # Resistencia
        "SAVC",  # Comodoro Rivadavia
        "SAWG",  # Rio Grande
        "SAZN",  # Neuquén
        "SAZS",  # Bariloche
        "SASJ",  # Jujuy. Large with scheduled service, and it was missing.
        # Medium with scheduled service: regional connections, still worth
        # plotting for a propagation study.
        "SANC",  # Catamarca
        "SANL",  # La Rioja
        "SANR",  # Termas de Rio Hondo
        "SANU",  # San Juan
        "SAOU",  # San Luis
        "SARC",  # Corrientes
        "SARF",  # Formosa
        "SARI",  # Puerto Iguazu
        "SARP",  # Posadas
        "SAMR",  # Mendoza, AAP
        "SAVE",  # Esquel
        "SAVT",  #.Relief / General Acha area
        "SAVV",  # Viedma
        "SAVY",  # Puerto Madryn
        "SAWC",  # El Calafate
        "SAWD",  # Puerto Deseado
        "SAWE",  # Rio Gallegos
        "SAWH",  # Ushuaia
        "SAWP",  # Perito Moreno
        "SAZB",  # Bahia Blanca
        "SAZL",  # Santa Teresita
        "SAZM",  # Mar del Plata
        "SAZO",  # Necochea
        "SAZR",  # Santa Rosa
        "SAZY",  # San Martin de los Andes
        "SAAP",  # Parana
        "SAAV",  # Sauce Viejo / Santa Fe
        # ── The Buenos Aires area, asked for by the operator ───────────────
        # Same FIR as EZE and AEP, and the fields where a second or third
        # source of metro-area interference is most likely to show up.
        "SADP",  # El Palomar, IATA EPA. No ICAO in the source, matched on gps.
        "SADF",  # San Fernando, local code FDO. Publishes neither ICAO nor
                  # IATA, matched on gps_code.
        "SAOL",  # Lago Musters, the general-aviation field
        "SADL",  # La Plata
        "SAOC",  # Area de Material, the Parques Nacionales base
        # ── Every remaining Argentine medium airport ──────────────────────
        # A rule rather than a matter of taste: an aerodrome is here if the
        # source types it medium_airport, or small_airport with scheduled
        # passenger service, and it is still in service. Those are the ones
        # that anchor a FIR sector or a border, which is where an operator
        # needs an ARP to measure from.
        "SAAC",  # Comodoro Pierrestegui
        "SAAG",  # Gualeguaychu, on the Uruguayan border
        "SACT",  # Chamical
        "SAHS",  # Rincon de los Sauces
        "SAHZ",  # Zapala
        "SAMM",  # Comodoro D.R. Salomon
        "SANE",  # SDE, El Calafate
        "SAOD",  # Villa Dolores
        "SAOR",  # Villa Reynolds
        "SAOV",  # Presidente Nestor Kirchner Regional, Rio Grande
        "SARL",  # Paso de los Libres, on the Uruguayan border
        "SARM",  # Monte Caseros, on the Uruguayan border
        "SASO",  # Oran
        "SAST",  # Santa Cruz
        "SATG",  # Goya
        "SATR",  # Reconquista
        "SATU",  # Curuzu Cuatia
        "SAVB",  # El Bolson
        "SAVH",  # Las Heras
        "SAWJ",  # Capitan D. Daniel Vazquez
        "SAWU",  # RZA
        "SAZG",  # General Pico
        "SAZH",  # Tres Arroyos
        "SAZP",  # Comodoro Pedro Zanni
        "SAZT",  # Heroes de Malvinas
        "SAZV",  # Villa Gesell
        "SAZW",  # Cutral-Co
        # Small, but with scheduled service: real passengers, so a real ARP.
        "SAVN",  # Antoine de Saint Exupery
        "SAWR",  # Gobernador Gregores
        "SAWT",  # 28 de Noviembre, Rio Mayo
    ],
    "UY": ["SUMU", "SULS", "SUCU", "SUVO", "SUCA"],
    "PY": ["SGAS", "SGCI", "SGME", "SGPP"],
    "CL": ["SCEL", "SCFA", "SCTN", "SCQP", "SCJO", "SCQR", "SCQN", "SCGL", "SCRD"],
    "BR": ["SBGR", "SBPA", "SBCT", "SBSV", "SBRF", "SBCF"],
    "ES": ["LEMD", "LEBL", "LEPA", "LEAS"],
    # Reference: a few elsewhere, for long-baseline interference studies.
    "US": ["KJFK", "KLAX", "KMIA", "KORD"],
    "FR": ["LFPG", "LFML"],
}

ORDER = {"large_airport": 0, "medium_airport": 1, "small_airport": 2, "heliport": 3}
ALL = {c for codes in SELECTED.values() for c in codes}
COUNTRY_LABEL = {
    "AR": "Argentina", "UY": "Uruguay", "PY": "Paraguay", "CL": "Chile",
    "BR": "Brasil", "ES": "España", "US": "Estados Unidos", "FR": "Francia",
}

found = {}
matched_on = {}
with io.open("_ap.csv", encoding="utf-8", errors="replace", newline="") as fh:
    for r in csv.DictReader(fh):
        icao = (r.get("icao_code") or "").strip().upper()
        gps = (r.get("gps_code") or "").strip().upper()
        for token, field in ((icao, "icao_code"), (gps, "gps_code")):
            if not token or token not in ALL or token in found:
                continue
            found[token] = r
            matched_on[token] = field
            break

# Report anything we asked for and did not get, so a gap is never silent.
missing = sorted(ALL - set(found))
if missing:
    print("AUSENTES en la fuente (no se inventan):", ", ".join(missing))
via_gps = sorted(t for t, f in matched_on.items() if f == "gps_code")
if via_gps:
    print("resueltos por gps_code (la fuente no publica ICAO):", ", ".join(via_gps))

out = []
for cc, codes in SELECTED.items():
    block = [found[c] for c in codes if c in found]
    block.sort(key=lambda r: (ORDER.get((r.get("type") or "").strip(), 5),
                              -(int(float(r.get("latitude_deg") or 0)))))
    out.append((cc, block))

lines = ["""/**
 * data/airports.js
 * ───────────────
 * Aerodrome reference points, for use as map layers and as the origin of a
 * distance measurement.
 *
 * ── Provenance ───────────────────────────────────────────────────────────
 *
 * `reference`. These are published aerodrome reference points from
 * OurAirports, not anything AeroRF observed or measured. The layer is drawn
 * as reference data and its legend says so.
 *
 * ── Why a generated file and not a database table ────────────────────────
 *
 * An ICAO code and an ARP do not change between sessions, and they are the
 * same for every operator. Seeding them into `map_objects` would put rows in
 * the same table as the operator's own work, where a reference point could be
 * mistaken for something they drew, and a later correction would have to
 * fight the rows a previous run created.
 *
 * The layer is therefore not persisted: showing it, hiding it and filtering
 * it by country change nothing in the database.
 *
 * ── Do not hand-edit this file ──────────────────────────────────────────
 *
 * It is generated by `tools/build_airports.py` from OurAirports. A
 * hand-written version of this file had duplicated ICAO codes, duplicated
 * IATA codes, two identical coordinate pairs under different names, and a
 * set of coordinates that belonged to no aerodrome at all. Every one of them
 * looked plausible, which is the problem: an operator computing interference
 * protection around a wrong ARP produces a confidently wrong report.
 *
 * To change the set of aerodromes, change SELECTED in that script and re-run it
 * with OurAirports' `airports.csv` in the project root as `_ap.csv`. Codes the
 * source does not publish are reported on stdout and left out. They are never
 * filled in by hand.
 *
 * ── Accuracy ─────────────────────────────────────────────────────────────
 *
 * Coordinates are the ARP as published, to about 1e-5 degrees (~1 m). That is
 * the precision of the source, not of the application: an ADS-B position is
 * far coarser. Do not present a distance to an airport as a measured
 * separation.
 */
"""]

for cc, block in out:
    lines.append("/** @type {Airport[]} %s. */" % COUNTRY_LABEL.get(cc, cc))
    lines.append("const %s = [" % cc.lower())
    for r in block:
        icao = (r.get("icao_code") or "").strip().upper()
        gps = (r.get("gps_code") or "").strip().upper()
        local = (r.get("local_code") or "").strip().upper()
        iata = (r.get("iata_code") or "").strip().upper()
        name = (r.get("name") or "").strip()
        # No transliteration. The file is written as UTF-8 and the browser reads
        # it as UTF-8, so the accents belong in the name: "Martín Miguel de
        # Güemes", not "Martn Miguel de Gemes". An earlier version of this line
        # did `name.encode("ascii", "ignore")` on the theory that the names were
        # for display in a console. They are not, and every accented aerodrome in
        # the country came out with a hole where the vowel should be.
        typ = (r.get("type") or "").strip()
        lat = float(r["latitude_deg"])
        lon = float(r["longitude_deg"])
        elev = (r.get("elevation_ft") or "").strip()
        sched = (r.get("scheduled_service") or "").strip() == "yes"
        # Always present and always unique, even when the source publishes no
        # ICAO code: ICAO, else GPS, else the local code, else the source id.
        key = icao or gps or local or ("OA%s" % (r.get("id") or "?").strip())
        lines.append("  {")
        lines.append("    key: '%s'," % key)
        lines.append("    icao: %s," % ("'%s'" % icao if icao else "null"))
        lines.append("    gps: %s," % ("'%s'" % gps if gps else "null"))
        lines.append("    local: %s," % ("'%s'" % local if local else "null"))
        lines.append("    iata: %s," % ("'%s'" % iata if iata else "null"))
        lines.append("    name: '%s'," % name.replace("'", "\\'"))
        lines.append("    country: '%s'," % cc)
        lines.append("    kind: '%s'," % typ)
        lines.append("    lat: %s," % round(lat, 6))
        lines.append("    lon: %s," % round(lon, 6))
        lines.append("    elevFt: %s," % (int(float(elev)) if elev else "null"))
        lines.append("    scheduled: %s," % ("true" if sched else "false"))
        lines.append("  },")
    lines.append("]")
    lines.append("")

lines.append("""/**
 * @typedef {object} Airport
 * @property {string}  key     Unique identifier: ICAO, else GPS, else local
 * @property {?string} icao    ICAO location indicator, null when unpublished
 * @property {?string} gps     GPS code, null when unpublished
 * @property {?string} local   Local code, null when unpublished
 * @property {?string} iata    IATA code, null when the field has none
 * @property {string}  name    Aerodrome name
 * @property {string}  country ISO 3166-1 alpha-2
 * @property {string}  kind    large_airport | medium_airport | small_airport | heliport
 * @property {number}  lat     ARP latitude, WGS84 decimal degrees
 * @property {number}  lon     ARP longitude, WGS84 decimal degrees
 * @property {?number} elevFt  Field elevation, feet, null when unpublished
 * @property {boolean} scheduled Whether scheduled passenger service
 */
""")
spread = "\n".join("  ...%s," % cc.lower() for cc, _ in out)
country_rows = ",\n".join(
    "  { code: '%s', label: '%s', count: %s.length }" % (cc, COUNTRY_LABEL.get(cc, cc), cc.lower())
    for cc, _ in out
)

lines.append(
    "/** Every airport, ordered by country then by size. */\n"
    "export const AIRPORTS = [\n%s\n]\n" % spread
)
lines.append(
    "/** Countries present, for the layer's filter. */\n"
    "export const AIRPORT_COUNTRIES = [\n%s\n]\n" % country_rows
)

lines.append("""/**
 * The short code to show on the map: the IATA first.
 *
 * An operator says "EZE" and "AEP", not "SAEZ" and "SABE" — the IATA is the
 * code they read on a boarding pass and type into a slot. It is not always
 * published, so this falls back through the codes the source does publish and
 * ends at a shortened name rather than at nothing.
 */
export function airportCode(airport) {
  return (
    airport.iata || airport.icao || airport.gps || airport.local || shortName(airport)
  )
}

/** The name without the trailing "Airport", for the codes that have nothing else. */
function shortName(airport) {
  return String(airport.name || '')
    .replace(/\\s+(International\\s+)?Airport$/i, '')
    .slice(0, 14)
}

/**
 * True for an aerodrome that carries regular traffic.
 *
 * Used to tell the big fields from the small ones on the map. `scheduled` is
 * the source's own answer, and the size class is the fallback, so an
 * aerodrome that is medium but has no scheduled service still reads as major
 * rather than as a strip.
 */
export function isMajor(airport) {
  return airport.scheduled || airport.kind === 'large_airport' || airport.kind === 'medium_airport'
}

/** Lookup by ICAO, case-insensitive. Only the aerodromes that publish one. */
export const AIRPORTS_BY_ICAO = new Map(
  AIRPORTS.filter((a) => a.icao).map((a) => [a.icao.toLowerCase(), a]),
)

/** Lookup by IATA. */
export const AIRPORTS_BY_IATA = new Map(AIRPORTS.filter((a) => a.iata).map((a) => [a.iata, a]))

/**
 * Every published code for one aerodrome, longest first, so a lookup matches
 * the most specific thing the operator typed.
 */
export function airportCodes(airport) {
  return [airport.icao, airport.iata, airport.gps, airport.local]
    .filter((c) => typeof c === 'string' && c.length > 0)
    .sort((a, b) => b.length - a.length)
}

/** Every published code of every aerodrome, mapped to the aerodrome. */
const BY_CODE = new Map()
for (const airport of AIRPORTS) {
  for (const code of airportCodes(airport)) {
    const k = code.toLowerCase()
    if (!BY_CODE.has(k)) BY_CODE.set(k, airport)
  }
}

/**
 * Resolve an aerodrome from any code it publishes, case-insensitively.
 *
 * The distance tool asks for a code and the operator may type any of them: the
 * IATA they know, the ICAO from a chart, the local code printed in a FIR
 * publication, or the GPS code for a field like San Fernando that publishes no
 * ICAO at all.
 *
 * @param {string} text
 * @returns {Airport | null}
 */
export function findAirport(text) {
  if (!text) return null
  const t = String(text).trim().toUpperCase()
  if (t.length < 3 || t.length > 4) return null
  return BY_CODE.get(t.toLowerCase()) || null
}
""")

os.makedirs("frontend/src/data", exist_ok=True)
with io.open("frontend/src/data/airports.js", "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(lines))
print("escrito frontend/src/data/airports.js con %d aeropuertos" % len(found))
