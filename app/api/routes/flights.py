from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
import json
import math
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.schemas import FlightRouteResponse

router = APIRouter(prefix="/flights", tags=["Flights"])

AIRPORTS = {
    'EZE': {'name': 'Ministro Pistarini', 'lat': -34.8186, 'lon': -58.5358},
    'COR': {'name': 'Córdoba', 'lat': -31.3239, 'lon': -64.2088},
    'MDZ': {'name': 'Mendoza', 'lat': -32.8975, 'lon': -68.8268},
    'AEP': {'name': 'Aeroparque', 'lat': -34.5599, 'lon': -58.4154},
    'ROS': {'name': 'Rosario', 'lat': -32.9039, 'lon': -60.7842},
}


def build_route(origin_code: str, destination_code: str, callsign: str, status: str):
    origin = AIRPORTS.get(origin_code.upper())
    destination = AIRPORTS.get(destination_code.upper())
    if not origin or not destination:
        return None

    midpoint = [
        (origin['lat'] + destination['lat']) / 2 + 0.2,
        (origin['lon'] + destination['lon']) / 2 - 0.2,
    ]

    now = datetime.utcnow()
    return {
        'callsign': callsign,
        'origin': origin_code.upper(),
        'destination': destination_code.upper(),
        'origin_name': origin['name'],
        'destination_name': destination['name'],
        'status': status,
        'departure_time': now.isoformat() + 'Z',
        'arrival_time': (now + timedelta(hours=1, minutes=25)).isoformat() + 'Z',
        'path': [
            [origin['lat'], origin['lon']],
            midpoint,
            [destination['lat'], destination['lon']],
        ],
    }


OPENSKY_STATES_URL = 'https://opensky-network.org/api/states/all'


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def find_nearest_airport(lat: float, lon: float) -> Optional[Tuple[str, dict]]:
    nearest = None
    best_distance = float('inf')
    for code, airport in AIRPORTS.items():
        distance = haversine(lat, lon, airport['lat'], airport['lon'])
        if distance < best_distance:
            best_distance = distance
            nearest = (code, airport)
    if best_distance <= 150:  # only consider airports within about 150 km
        return nearest
    return None


def fetch_opensky_states(airport_code: Optional[str] = None) -> List[list]:
    params = {}
    if airport_code and airport_code.upper() in AIRPORTS:
        airport = AIRPORTS[airport_code.upper()]
        params = {
            'lamin': airport['lat'] - 1.0,
            'lomin': airport['lon'] - 1.0,
            'lamax': airport['lat'] + 1.0,
            'lomax': airport['lon'] + 1.0,
        }

    url = OPENSKY_STATES_URL
    if params:
        url = f"{url}?{urlencode(params)}"

    request = Request(url, headers={'User-Agent': 'SIARI-OpenSky-Client/1.0'})
    with urlopen(request, timeout=20) as response:
        data = json.load(response)
    return data.get('states', []) or []


def build_opensky_route(state: list, airport_code: Optional[str] = None):
    callsign = (state[1] or '').strip()
    if not callsign:
        return None

    lat = state[6]
    lon = state[5]
    if lat is None or lon is None:
        return None

    airport = None
    if airport_code and airport_code.upper() in AIRPORTS:
        airport = AIRPORTS[airport_code.upper()]
    else:
        nearest = find_nearest_airport(lat, lon)
        airport = nearest[1] if nearest else None

    path = [[lat, lon]]
    origin = 'N/A'
    origin_name = 'OpenSky'
    destination = 'N/A'
    destination_name = 'OpenSky'

    if airport:
        origin = airport_code.upper() if airport_code and airport_code.upper() in AIRPORTS else nearest[0] if 'nearest' in locals() and nearest else airport_code or 'N/A'
        origin_name = airport['name']
        path.insert(0, [airport['lat'], airport['lon']])

    status = 'en tierra' if state[8] else 'en vuelo'
    timestamp = state[3] or state[4] or int(datetime.utcnow().timestamp())
    dt = datetime.utcfromtimestamp(timestamp)

    return {
        'callsign': callsign,
        'origin': origin,
        'destination': destination,
        'origin_name': origin_name,
        'destination_name': destination_name,
        'status': status,
        'departure_time': dt.isoformat() + 'Z',
        'arrival_time': dt.isoformat() + 'Z',
        'path': path,
    }
}


def sample_flights():
    return [
        build_route('EZE', 'COR', 'AR101', 'en ruta'),
        build_route('AEP', 'MDZ', 'LA305', 'despegando'),
        build_route('ROS', 'EZE', 'AV212', 'aterrizando'),
    ]


@router.get('/search', response_model=List[FlightRouteResponse])
def search_flights(
    origin: Optional[str] = Query(None, max_length=4),
    destination: Optional[str] = Query(None, max_length=4),
    callsign: Optional[str] = Query(None, max_length=10),
    source: Optional[str] = Query('sample', max_length=20),
):
    """Search flight routes by origin, destination, callsign, or OpenSky source."""
    origin = origin.upper() if origin else None
    destination = destination.upper() if destination else None
    callsign = callsign.upper() if callsign else None
    source = source.lower() if source else 'sample'

    if source == 'opensky':
        try:
            states = fetch_opensky_states(origin)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f'OpenSky error: {exc}')

        flights = []
        for state in states:
            route = build_opensky_route(state, origin)
            if not route:
                continue
            if callsign and callsign not in route['callsign'].upper():
                continue
            flights.append(route)

        return flights

    flights = sample_flights()
    results = []

    for flight in flights:
        if origin and flight['origin'] != origin:
            continue
        if destination and flight['destination'] != destination:
            continue
        if callsign and callsign not in flight['callsign']:
            continue
        results.append(flight)

    return results if results else flights
