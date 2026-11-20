"""
Unit and Integration Tests for NoQueue Road Routing Service
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from backend.routing_service import (
    haversine_distance_km,
    fetch_osrm_route,
    fetch_osrm_table,
    attach_road_routes_to_stations,
    calculate_haversine_fallback,
    store_cached_route,
    get_cached_route,
    clear_routing_cache,
)


class TestRoutingService(unittest.TestCase):
    def setUp(self):
        clear_routing_cache()

    def test_haversine_calculation(self):
        # New Colony Gurgaon (28.468, 77.018) to Sector 37C (28.455, 76.998)
        dist = haversine_distance_km(28.468, 77.018, 28.455, 76.998)
        self.assertGreater(dist, 1.5)
        self.assertLess(dist, 3.5)

    def test_caching_mechanism(self):
        origin = (28.4595, 77.0266)
        dest = (28.4500, 77.0300)

        # Initially empty
        self.assertIsNone(get_cached_route(origin[0], origin[1], dest[0], dest[1]))

        # Store entry
        dummy = {
            "road_distance_km": 5.4,
            "travel_time_minutes": 12.0,
            "distance_type": "road",
            "routing_engine": "osrm",
            "routing_status": "success",
            "is_road_network": True,
        }
        store_cached_route(origin[0], origin[1], dest[0], dest[1], dummy)

        cached = get_cached_route(origin[0], origin[1], dest[0], dest[1])
        self.assertIsNotNone(cached)
        self.assertEqual(cached["road_distance_km"], 5.4)

    def test_offline_fallback_honest_labeling(self):
        origin_lat, origin_lon = 28.468, 77.018
        dest_lat, dest_lon = 28.455, 76.998

        fallback = calculate_haversine_fallback(origin_lat, origin_lon, dest_lat, dest_lon, reason="test_offline")
        self.assertEqual(fallback["distance_type"], "straight_line")
        self.assertEqual(fallback["routing_status"], "fallback")
        self.assertIn("straight-line", fallback["distance_text"])
        self.assertFalse(fallback["is_road_network"])
        self.assertGreater(fallback["travel_time_minutes"], 0.0)

    @patch("urllib.request.urlopen")
    def test_osrm_route_success(self, mock_urlopen):
        # Mock OSRM Route API response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({
            "code": "Ok",
            "routes": [
                {
                    "distance": 11700.0,  # 11.7 km
                    "duration": 1500.0,   # 25 minutes
                }
            ]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = fetch_osrm_route(28.468, 77.018, 28.455, 76.998)
        self.assertEqual(res["routing_status"], "success")
        self.assertEqual(res["distance_type"], "road")
        self.assertEqual(res["road_distance_km"], 11.7)
        self.assertEqual(res["travel_time_minutes"], 25.0)
        self.assertEqual(res["distance_text"], "11.7 km")
        self.assertTrue(res["is_road_network"])

    @patch("urllib.request.urlopen")
    def test_osrm_table_batch_success(self, mock_urlopen):
        # Mock OSRM Table API response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({
            "code": "Ok",
            "distances": [[11700.0, 5200.0]],
            "durations": [[1500.0, 660.0]]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        destinations = [(28.455, 76.998), (28.470, 77.050)]
        results = fetch_osrm_table(28.468, 77.018, destinations)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["road_distance_km"], 11.7)
        self.assertEqual(results[0]["travel_time_minutes"], 25.0)
        self.assertEqual(results[1]["road_distance_km"], 5.2)
        self.assertEqual(results[1]["travel_time_minutes"], 11.0)

    @patch("urllib.request.urlopen")
    def test_attach_road_routes_to_stations(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({
            "code": "Ok",
            "distances": [[11700.0]],
            "durations": [[1500.0]]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        stations = [
            {
                "osm_id": 1001,
                "name": "HCG CNG Station",
                "latitude": 28.455,
                "longitude": 76.998,
                "distance_km": 2.29,  # Old Haversine
            }
        ]

        enriched = attach_road_routes_to_stations(28.468, 77.018, stations)
        st = enriched[0]

        # Verify old 2.29 km straight-line distance is preserved as straight_line_distance_km,
        # but the primary distance_km and distance_text are updated to actual road distance!
        expected_straight = haversine_distance_km(28.468, 77.018, 28.455, 76.998)
        self.assertEqual(st["straight_line_distance_km"], expected_straight)
        self.assertEqual(st["road_distance_km"], 11.7)
        self.assertEqual(st["distance_km"], 11.7)
        self.assertEqual(st["distance_text"], "11.7 km")
        self.assertEqual(st["travel_time_minutes"], 25.0)
        self.assertEqual(st["distance_type"], "road")


if __name__ == "__main__":
    unittest.main()
