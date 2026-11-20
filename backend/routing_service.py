"""
NoQueue Road Routing Service (OSRM Integration)
==============================================
Provides real road-network distance and driving duration calculations using the
Open Source Routing Machine (OSRM) driving profile.

Features:
- OSRM HTTP API integration (Table and Route endpoints).
- In-memory LRU/TTL caching to eliminate redundant HTTP calls on dashboard refresh.
- Graceful offline and network-failure fallbacks with honest labeling (straight-line vs road).
- Urban detour & driving time heuristics for offline fallbacks.
- Thread-safe caching mechanism.
"""

import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("noqueue.routing")

# OSRM Public Demo API configuration
OSRM_BASE_URL = "http://router.project-osrm.org"
OSRM_TIMEOUT_SECONDS = 4.0
USER_AGENT = "NoQueue-Routing/1.0 (Smart CNG Queue Assistant; contact: support@noqueue.app)"

# In-memory routing cache: (lat1, lon1, lat2, lon2) -> (result_dict, timestamp)
_ROUTING_CACHE: Dict[Tuple[float, float, float, float], Tuple[Dict[str, Any], float]] = {}
CACHE_TTL_SECONDS = 3600.0  # 1 hour TTL for static road network coordinates
MAX_CACHE_SIZE = 1000


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes great-circle straight-line distance in kilometers.
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


def _cache_key(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float, float, float]:
    """Generates coordinate cache key rounded to 5 decimal places (~1.1 meter accuracy)."""
    return (round(lat1, 5), round(lon1, 5), round(lat2, 5), round(lon2, 5))


def get_cached_route(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[Dict[str, Any]]:
    """Retrieves route from memory cache if present and unexpired."""
    key = _cache_key(lat1, lon1, lat2, lon2)
    if key in _ROUTING_CACHE:
        entry, timestamp = _ROUTING_CACHE[key]
        if (time.time() - timestamp) < CACHE_TTL_SECONDS:
            return dict(entry)
        else:
            del _ROUTING_CACHE[key]
    return None


def store_cached_route(lat1: float, lon1: float, lat2: float, lon2: float, route_data: Dict[str, Any]) -> None:
    """Stores route in memory cache with size eviction."""
    global _ROUTING_CACHE
    if len(_ROUTING_CACHE) >= MAX_CACHE_SIZE:
        # Evict oldest 20%
        sorted_keys = sorted(_ROUTING_CACHE.keys(), key=lambda k: _ROUTING_CACHE[k][1])
        for k in sorted_keys[: int(MAX_CACHE_SIZE * 0.2)]:
            _ROUTING_CACHE.pop(k, None)

    key = _cache_key(lat1, lon1, lat2, lon2)
    _ROUTING_CACHE[key] = (dict(route_data), time.time())


def clear_routing_cache() -> None:
    """Clears all cached routes (useful in tests)."""
    global _ROUTING_CACHE
    _ROUTING_CACHE.clear()


def calculate_haversine_fallback(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    reason: str = "offline_fallback"
) -> Dict[str, Any]:
    """
    Computes straight-line Haversine fallback with honest labeling.
    Estimated driving duration uses an urban detour index of ~1.35x and ~25 km/h urban speed.
    """
    straight_dist_km = haversine_distance_km(origin_lat, origin_lon, dest_lat, dest_lon)
    # Estimate typical urban driving road distance & time for fallback
    est_road_km = round(max(straight_dist_km, straight_dist_km * 1.35), 2)
    # Average urban transit speed ~25 km/h with 1.5 min minimum overhead
    est_duration_min = round(max(2.0, (est_road_km / 25.0) * 60.0), 1)

    return {
        "road_distance_km": est_road_km,
        "straight_line_distance_km": straight_dist_km,
        "distance_km": straight_dist_km,  # honest straight-line value
        "distance_text": f"{straight_dist_km} km (straight-line)",
        "distance_type": "straight_line",
        "travel_time_minutes": est_duration_min,
        "duration_seconds": est_duration_min * 60.0,
        "routing_engine": "haversine_estimate",
        "routing_status": "fallback",
        "fallback_reason": reason,
        "is_road_network": False,
    }


def fetch_osrm_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    timeout: float = OSRM_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """
    Queries OSRM Route service for driving distance and travel duration between two coordinates.
    OSRM expects coordinates in '{longitude},{latitude}' order.
    """
    # 1. Check cache first
    cached = get_cached_route(origin_lat, origin_lon, dest_lat, dest_lon)
    if cached:
        return cached

    # 2. Check for identical or negligible distance
    straight_dist = haversine_distance_km(origin_lat, origin_lon, dest_lat, dest_lon)
    if straight_dist < 0.05:
        res = {
            "road_distance_km": 0.1,
            "straight_line_distance_km": straight_dist,
            "distance_km": 0.1,
            "distance_text": "0.1 km",
            "distance_type": "road",
            "travel_time_minutes": 1.0,
            "duration_seconds": 60.0,
            "routing_engine": "osrm",
            "routing_status": "success",
            "is_road_network": True,
        }
        store_cached_route(origin_lat, origin_lon, dest_lat, dest_lon, res)
        return res

    # 3. Request OSRM routing
    url = f"{OSRM_BASE_URL}/route/v1/driving/{origin_lon:.6f},{origin_lat:.6f};{dest_lon:.6f},{dest_lat:.6f}?overview=false&alternatives=false&steps=false"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise urllib.error.HTTPError(url, response.status, "OSRM status error", response.headers, None)
            data = json.loads(response.read().decode("utf-8"))

        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            distance_meters = float(route.get("distance", 0.0))
            duration_seconds = float(route.get("duration", 0.0))

            road_distance_km = round(distance_meters / 1000.0, 2)
            travel_time_minutes = round(duration_seconds / 60.0, 1)

            res = {
                "road_distance_km": road_distance_km,
                "straight_line_distance_km": straight_dist,
                "distance_km": road_distance_km,
                "distance_text": f"{road_distance_km} km",
                "distance_type": "road",
                "travel_time_minutes": max(1.0, travel_time_minutes),
                "duration_seconds": duration_seconds,
                "routing_engine": "osrm",
                "routing_status": "success",
                "is_road_network": True,
            }
            store_cached_route(origin_lat, origin_lon, dest_lat, dest_lon, res)
            return res
        else:
            code = data.get("code", "NoRoute")
            logger.warning(f"OSRM returned non-OK code '{code}' for ({origin_lat}, {origin_lon}) -> ({dest_lat}, {dest_lon})")
            return calculate_haversine_fallback(origin_lat, origin_lon, dest_lat, dest_lon, reason=f"osrm_code_{code}")

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as net_err:
        logger.info(f"OSRM service network request failed: {net_err}. Using honest fallback.")
        return calculate_haversine_fallback(origin_lat, origin_lon, dest_lat, dest_lon, reason=str(net_err))
    except Exception as exc:
        logger.warning(f"Unexpected error in OSRM route fetch: {exc}")
        return calculate_haversine_fallback(origin_lat, origin_lon, dest_lat, dest_lon, reason=str(exc))


def fetch_osrm_table(
    origin_lat: float,
    origin_lon: float,
    destinations: List[Tuple[float, float]],
    timeout: float = OSRM_TIMEOUT_SECONDS
) -> List[Dict[str, Any]]:
    """
    Uses the OSRM Table Service to fetch road distances and durations for multiple destinations
    in a single HTTP batch request. Falls back to individual route requests or haversine on error.
    """
    if not destinations:
        return []

    # Check how many are already cached
    cached_results = [get_cached_route(origin_lat, origin_lon, d_lat, d_lon) for d_lat, d_lon in destinations]
    all_cached = all(c is not None for c in cached_results)
    if all_cached:
        return [c for c in cached_results if c is not None]

    # Construct coordinates string: origin is index 0, destinations are index 1..N
    coords_list = [f"{origin_lon:.6f},{origin_lat:.6f}"]
    for d_lat, d_lon in destinations:
        coords_list.append(f"{d_lon:.6f},{d_lat:.6f}")

    dest_indices = ";".join(str(i) for i in range(1, len(destinations) + 1))
    coords_str = ";".join(coords_list)
    url = f"{OSRM_BASE_URL}/table/v1/driving/{coords_str}?sources=0&destinations={dest_indices}&annotations=distance,duration"

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise urllib.error.HTTPError(url, response.status, "OSRM table status error", response.headers, None)
            data = json.loads(response.read().decode("utf-8"))

        if data.get("code") == "Ok" and "distances" in data and "durations" in data:
            dist_matrix = data["distances"][0]  # row for source 0 to all destinations
            dur_matrix = data["durations"][0]

            results = []
            for idx, (d_lat, d_lon) in enumerate(destinations):
                dist_m = dist_matrix[idx]
                dur_s = dur_matrix[idx]
                straight_dist = haversine_distance_km(origin_lat, origin_lon, d_lat, d_lon)

                if dist_m is not None and dur_s is not None:
                    road_km = round(float(dist_m) / 1000.0, 2)
                    travel_min = max(1.0, round(float(dur_s) / 60.0, 1))

                    res = {
                        "road_distance_km": road_km,
                        "straight_line_distance_km": straight_dist,
                        "distance_km": road_km,
                        "distance_text": f"{road_km} km",
                        "distance_type": "road",
                        "travel_time_minutes": travel_min,
                        "duration_seconds": float(dur_s),
                        "routing_engine": "osrm",
                        "routing_status": "success",
                        "is_road_network": True,
                    }
                else:
                    res = calculate_haversine_fallback(origin_lat, origin_lon, d_lat, d_lon, reason="table_null_element")

                store_cached_route(origin_lat, origin_lon, d_lat, d_lon, res)
                results.append(res)
            return results

    except Exception as exc:
        logger.info(f"OSRM Table request failed ({exc}). Falling back to individual route calls.")

    # Fallback to individual fetches
    results = []
    for d_lat, d_lon in destinations:
        results.append(fetch_osrm_route(origin_lat, origin_lon, d_lat, d_lon, timeout=timeout))
    return results


def attach_road_routes_to_stations(
    origin_lat: float,
    origin_lon: float,
    stations: List[Dict[str, Any]],
    timeout: float = OSRM_TIMEOUT_SECONDS
) -> List[Dict[str, Any]]:
    """
    Enriches a list of station records with road-network distance and travel time.
    Updates each station in-place with:
      - distance_km (actual road distance)
      - distance_text
      - distance_type ('road' or 'straight_line')
      - travel_time_minutes (road-network driving time)
      - straight_line_distance_km
      - routing_engine ('osrm' or 'haversine_estimate')
      - routing_status ('success' or 'fallback')
    """
    if not stations:
        return stations

    valid_coords = []
    coord_indices = []

    for i, st in enumerate(stations):
        s_lat = st.get("latitude")
        s_lon = st.get("longitude")
        if isinstance(s_lat, (int, float)) and isinstance(s_lon, (int, float)):
            valid_coords.append((float(s_lat), float(s_lon)))
            coord_indices.append(i)
        else:
            # Missing coordinates fallback
            st["distance_type"] = "unavailable"
            st["travel_time_minutes"] = 10.0
            st["routing_status"] = "missing_coordinates"

    if valid_coords:
        routes = fetch_osrm_table(origin_lat, origin_lon, valid_coords, timeout=timeout)
        for idx, route_info in zip(coord_indices, routes):
            st = stations[idx]
            st["road_distance_km"] = route_info["road_distance_km"]
            st["straight_line_distance_km"] = route_info["straight_line_distance_km"]
            st["distance_km"] = route_info["distance_km"]
            st["distance_text"] = route_info["distance_text"]
            st["distance_type"] = route_info["distance_type"]
            st["travel_time_minutes"] = route_info["travel_time_minutes"]
            st["base_travel_time_minutes"] = route_info["travel_time_minutes"]
            st["routing_engine"] = route_info["routing_engine"]
            st["routing_status"] = route_info["routing_status"]
            st["is_road_network"] = route_info["is_road_network"]

    return stations

