"""
NoQueue - OpenStreetMap (OSM) Location & CNG Station Discovery Service
======================================================================
Provides free, keyless geocoding (Nominatim) and fuel station discovery
(Overpass API with Nominatim POI fallback).

Respects OpenStreetMap usage policies:
1. Genuine application-identifying User-Agent with contact address.
2. Strict minimum 1.2-second rate-limiting between Nominatim requests.
3. In-memory caching for both geocoding and discovery queries.
4. Strict separation of verified CNG stations (explicit fuel:cng tags)
   from unverified fuel stations.
"""

import time
import math
import json
import urllib.request
import urllib.parse
import urllib.error
import threading
from typing import Dict, Any, List, Optional, Tuple

try:
    from backend.routing_service import attach_road_routes_to_stations
except ImportError:
    from routing_service import attach_road_routes_to_stations

USER_AGENT = "NoQueue-LocationDiscovery/1.0 (contact: support@noqueue.org; https://github.com/noqueue-app)"

# Rate-limiting state for Nominatim (Usage policy: max 1 request/second)
_last_nominatim_request_time: float = 0.0
_nominatim_lock = threading.Lock()

# In-memory caches
# Cache structure: key -> (timestamp, data)
_geocode_cache: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}
_reverse_geocode_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_discovery_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

# Cache TTLs in seconds
GEOCODE_CACHE_TTL = 86400  # 24 hours for successful geocode
NEGATIVE_CACHE_TTL = 180   # 3 minutes for genuinely unresolvable queries
DISCOVERY_CACHE_TTL = 3600  # 1 hour


class GeocodingServiceError(Exception):
    """Raised when external geocoding service encounters a network failure, timeout, or rate-limit."""
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code

# Overpass API endpoints (tried in order)
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def _throttle_nominatim() -> None:
    """Enforces at least 1.2 seconds between successive requests to Nominatim."""
    global _last_nominatim_request_time
    with _nominatim_lock:
        now = time.time()
        elapsed = now - _last_nominatim_request_time
        if elapsed < 1.2:
            time.sleep(1.2 - elapsed)
        _last_nominatim_request_time = time.time()


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates the great-circle distance between two points in kilometers
    using the Haversine formula.
    """
    earth_radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(earth_radius_km * c, 2)


def _execute_nominatim_search(query_str: str, country_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """Helper to query Nominatim search endpoint with rate-limiting and error discrimination."""
    _throttle_nominatim()

    params: Dict[str, str] = {
        "q": query_str,
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "1",
    }
    if country_code:
        params["countrycodes"] = country_code

    url = f"https://nominatim.openstreetmap.org/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
            if isinstance(payload, list):
                return payload
            return []
    except urllib.error.HTTPError as http_err:
        if http_err.code == 429:
            raise GeocodingServiceError(
                "OpenStreetMap Nominatim rate limit reached. Please wait a moment before searching again.",
                status_code=429,
            )
        elif http_err.code in (500, 502, 503, 504):
            raise GeocodingServiceError(
                f"OpenStreetMap Nominatim upstream service error ({http_err.code}). Please try again shortly or use your current location.",
                status_code=503,
            )
        raise GeocodingServiceError(
            f"Geocoding HTTP error ({http_err.code}): {http_err.reason}",
            status_code=502,
        )
    except urllib.error.URLError as url_err:
        raise GeocodingServiceError(
            f"Geocoding network connection failed or timed out: {url_err.reason}. Please check network access.",
            status_code=503,
        )
    except json.JSONDecodeError as json_err:
        raise GeocodingServiceError(
            f"Invalid response payload from geocoding provider: {json_err}",
            status_code=502,
        )


def geocode_location(query: str) -> Optional[Dict[str, Any]]:
    """
    Geocode a human-readable location string into latitude, longitude,
    and structured address details using OpenStreetMap Nominatim.

    Returns dict with {lat, lon, display_name, address, raw} or None if genuinely not found.
    Raises GeocodingServiceError on network failures, timeouts, and rate limits.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return None

    cache_key = cleaned_query.lower()
    now = time.time()

    # Check cache
    if cache_key in _geocode_cache:
        cached_time, cached_val = _geocode_cache[cache_key]
        ttl = GEOCODE_CACHE_TTL if cached_val is not None else NEGATIVE_CACHE_TTL
        if now - cached_time < ttl:
            return cached_val

    # 1. Attempt primary search query
    payload = _execute_nominatim_search(cleaned_query)

    # 2. If primary query yields no results, attempt country-scoped query (India context)
    if not payload and not any(term in cleaned_query.lower() for term in ["india", "in", "bharat"]):
        payload = _execute_nominatim_search(cleaned_query, country_code="in")

    # 3. If still empty, attempt appending country explicitly
    if not payload and not any(term in cleaned_query.lower() for term in ["india", "in"]):
        payload = _execute_nominatim_search(f"{cleaned_query}, India")

    if not payload:
        # Genuinely unresolvable location: cache negatively for short period
        _geocode_cache[cache_key] = (now, None)
        return None

    result = payload[0]
    resolved = {
        "query": cleaned_query,
        "lat": float(result["lat"]),
        "lon": float(result["lon"]),
        "display_name": result.get("display_name", ""),
        "osm_type": result.get("osm_type"),
        "osm_id": result.get("osm_id"),
        "address": result.get("address", {}),
        "boundingbox": result.get("boundingbox", []),
    }
    _geocode_cache[cache_key] = (now, resolved)
    return resolved


def reverse_geocode(lat: float, lon: float) -> Dict[str, Any]:
    """
    Reverse geocodes latitude and longitude coordinates into a human-readable
    locality/city display name and structured address using Nominatim.
    Falls back gracefully to formatted coordinates if external lookup fails.
    """
    cache_key = f"{round(lat, 3)}_{round(lon, 3)}"
    now = time.time()
    if cache_key in _reverse_geocode_cache:
        cached_time, cached_val = _reverse_geocode_cache[cache_key]
        if now - cached_time < GEOCODE_CACHE_TTL:
            return cached_val

    _throttle_nominatim()

    params = {
        "lat": str(lat),
        "lon": str(lon),
        "format": "jsonv2",
        "addressdetails": "1",
    }
    url = f"https://nominatim.openstreetmap.org/reverse?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    fallback_display = f"Location ({round(lat, 4)}° N, {round(lon, 4)}° E)"

    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
            display_name = payload.get("display_name") or fallback_display
            resolved = {
                "display_name": display_name,
                "lat": lat,
                "lon": lon,
                "address": payload.get("address", {}),
                "osm_type": payload.get("osm_type"),
                "osm_id": payload.get("osm_id"),
            }
            _reverse_geocode_cache[cache_key] = (now, resolved)
            return resolved
    except Exception as exc:
        print(f"[OSM Service] Reverse geocoding warning for ({lat}, {lon}): {exc}")
        return {
            "display_name": fallback_display,
            "lat": lat,
            "lon": lon,
            "address": {},
        }


def _parse_cng_tags(tags: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    """
    Inspects OSM element tags to determine CNG fuel availability.

    Returns:
        (is_cng_verified, cng_status, tag_evidence)
    """
    fuel_cng = str(tags.get("fuel:cng", "")).strip().lower()
    cng = str(tags.get("cng", "")).strip().lower()

    # Explicit positive tagging according to OSM conventions
    if fuel_cng in ("yes", "only"):
        return True, "verified", f"fuel:cng={fuel_cng}"
    if cng in ("yes", "only"):
        return True, "verified", f"cng={cng}"

    # Explicit negative tagging
    if fuel_cng == "no" or cng == "no":
        return False, "no_cng", "fuel:cng=no"

    # Name-based indication without explicit fuel:cng tag
    name = str(tags.get("name", "")).upper()
    operator = str(tags.get("operator", "")).upper()
    if "CNG" in name or "CNG" in operator:
        return False, "unverified_name_indicates_cng", "name_contains_cng"

    return False, "unverified", None


def _format_address(tags: Dict[str, Any], address_dict: Optional[Dict[str, Any]] = None) -> str:
    """Formats an address string from OSM tags or address component dictionary."""
    parts = []
    if address_dict:
        road = address_dict.get("road")
        suburb = address_dict.get("suburb") or address_dict.get("neighbourhood")
        city = (
            address_dict.get("city")
            or address_dict.get("town")
            or address_dict.get("county")
        )
        state = address_dict.get("state")
        postcode = address_dict.get("postcode")
        for p in [road, suburb, city, state, postcode]:
            if p and p not in parts:
                parts.append(p)
        if parts:
            return ", ".join(parts)

    # Fallback to direct tags
    street = tags.get("addr:street")
    housenumber = tags.get("addr:housenumber")
    city = tags.get("addr:city")
    postcode = tags.get("addr:postcode")

    if housenumber and street:
        parts.append(f"{housenumber} {street}")
    elif street:
        parts.append(street)
    if city:
        parts.append(city)
    if postcode:
        parts.append(postcode)

    return ", ".join(parts) if parts else ""


def _query_overpass(lat: float, lon: float, radius_meters: int) -> Optional[List[Dict[str, Any]]]:
    """
    Attempts to fetch nearby amenity=fuel stations using Overpass API.
    Returns list of elements or None if Overpass instances fail/timeout.
    """
    query = f"""[out:json][timeout:4];
(
  node["amenity"="fuel"](around:{radius_meters},{lat},{lon});
  way["amenity"="fuel"](around:{radius_meters},{lat},{lon});
);
out center tags;"""

    encoded_data = urllib.parse.urlencode({"data": query}).encode("utf-8")

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(
                endpoint,
                data=encoded_data,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json, */*",
                },
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                res = json.loads(response.read().decode("utf-8"))
                elements = res.get("elements", [])
                return elements
        except Exception as exc:
            print(f"[OSM Service] Overpass endpoint {endpoint} failed: {exc}")
            continue

    return None


def _query_nominatim_fuel(
    lat: float, lon: float, radius_meters: int
) -> List[Dict[str, Any]]:
    """
    Fallback POI search using Nominatim bounded bounding-box when Overpass is unavailable.
    """
    _throttle_nominatim()

    # Convert radius to approximate lat/lon degrees
    radius_km = float(radius_meters) / 1000.0
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * math.cos(math.radians(lat)))

    min_lon = lon - delta_lon
    max_lon = lon + delta_lon
    min_lat = lat - delta_lat
    max_lat = lat + delta_lat

    params = {
        "amenity": "fuel",
        "viewbox": f"{min_lon},{max_lat},{max_lon},{min_lat}",
        "bounded": "1",
        "format": "jsonv2",
        "extratags": "1",
        "addressdetails": "1",
        "limit": "50",
    }
    url = f"https://nominatim.openstreetmap.org/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"[OSM Service] Nominatim POI fallback failed: {exc}")
        return []


def discover_nearby_stations(
    lat: float, lon: float, radius_meters: int = 5000
) -> Dict[str, Any]:
    """
    Discover fuel stations around coordinates, categorizing them into:
    - verified_cng_stations: explicit fuel:cng tags
    - other_fuel_stations: general fuel pumps without verified CNG tags
    """
    radius_meters = int(radius_meters) if isinstance(radius_meters, (int, float)) else 5000
    # Round coordinates for cache key (~100m grid)
    cache_key = f"{round(lat, 3)}_{round(lon, 3)}_{radius_meters}"
    now = time.time()

    if cache_key in _discovery_cache:
        cached_time, cached_val = _discovery_cache[cache_key]
        if now - cached_time < DISCOVERY_CACHE_TTL:
            return cached_val

    # 1. Try Overpass API first
    raw_elements = _query_overpass(lat, lon, radius_meters)
    source_service = "overpass"

    # 2. Fallback to Nominatim bounded POI search if Overpass failed
    if raw_elements is None:
        source_service = "nominatim_fallback"
        raw_elements = _query_nominatim_fuel(lat, lon, radius_meters)

    verified_cng_stations: List[Dict[str, Any]] = []
    other_fuel_stations: List[Dict[str, Any]] = []

    seen_ids = set()

    for item in raw_elements:
        osm_id = item.get("id") or item.get("osm_id")
        osm_type = item.get("type") or item.get("osm_type", "node")
        unique_key = f"{osm_type}_{osm_id}"
        if unique_key in seen_ids:
            continue
        seen_ids.add(unique_key)

        # Coordinate resolution
        if "lat" in item and "lon" in item:
            st_lat = float(item["lat"])
            st_lon = float(item["lon"])
        elif "center" in item:
            st_lat = float(item["center"]["lat"])
            st_lon = float(item["center"]["lon"])
        else:
            continue

        dist_km = haversine_distance_km(lat, lon, st_lat, st_lon)
        # Verify within radius (bounding boxes may include corner outliers)
        if dist_km > (radius_meters / 1000.0):
            continue

        tags = item.get("tags") or item.get("extratags") or {}
        address_dict = item.get("address")

        name = (
            tags.get("name")
            or item.get("name")
            or tags.get("brand")
            or tags.get("operator")
            or ""
        )
        if not name and item.get("display_name"):
            name = item["display_name"].split(",")[0].strip()
        if not name:
            name = "Fuel Station"

        brand = tags.get("brand") or tags.get("brand:wikidata")
        operator = tags.get("operator")

        is_cng_verified, cng_status, tag_evidence = _parse_cng_tags(tags)
        address_str = _format_address(tags, address_dict)

        station_record = {
            "osm_id": osm_id,
            "osm_type": osm_type,
            "name": name,
            "brand": brand,
            "operator": operator,
            "latitude": st_lat,
            "longitude": st_lon,
            "distance_km": dist_km,
            "distance_text": f"{dist_km} km",
            "address": address_str,
            "is_cng_verified": is_cng_verified,
            "cng_status": cng_status,
            "cng_tag_evidence": tag_evidence,
            "fuel_tags": {
                k: v
                for k, v in tags.items()
                if k.startswith("fuel:") or k in ("cng", "lpg", "diesel", "petrol")
            },
        }

        if is_cng_verified:
            verified_cng_stations.append(station_record)
        else:
            other_fuel_stations.append(station_record)

    # Enrich verified CNG stations with actual road-network routing (OSRM)
    try:
        attach_road_routes_to_stations(lat, lon, verified_cng_stations)
    except Exception as route_err:
        print(f"[OSM Service] Warning: Could not attach road routes: {route_err}")

    # Sort each list by proximity (verified stations sorted by road distance)
    verified_cng_stations.sort(key=lambda s: s["distance_km"])
    other_fuel_stations.sort(key=lambda s: s["distance_km"])

    message = ""
    if not verified_cng_stations and not other_fuel_stations:
        message = (
            f"No fuel stations were found within a {radius_meters / 1000.0} km radius of this location on OpenStreetMap."
        )
    elif not verified_cng_stations:
        message = (
            f"No verified CNG stations (explicitly tagged fuel:cng=yes) were found within {radius_meters / 1000.0} km. "
            f"Displaying {len(other_fuel_stations)} nearby fuel stations that may or may not offer CNG."
        )
    else:
        message = (
            f"Found {len(verified_cng_stations)} verified CNG station(s) within {radius_meters / 1000.0} km."
        )

    result_payload = {
        "status": "success",
        "search_radius_km": radius_meters / 1000.0,
        "data_source": "openstreetmap",
        "discovery_engine": source_service,
        "total_stations_found": len(verified_cng_stations) + len(other_fuel_stations),
        "verified_cng_count": len(verified_cng_stations),
        "other_fuel_count": len(other_fuel_stations),
        "message": message,
        "verified_cng_stations": verified_cng_stations,
        "other_fuel_stations": other_fuel_stations,
    }

    _discovery_cache[cache_key] = (now, result_payload)
    return result_payload
