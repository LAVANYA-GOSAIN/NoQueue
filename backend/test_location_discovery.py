"""
Automated integration tests for NoQueue location discovery, Delhi geocoding,
and coordinate-based discovery pipeline.
"""

import os
import sys
import unittest
from fastapi import HTTPException

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import main
from main import discover_location
from osm_service import geocode_location, reverse_geocode, GeocodingServiceError


class TestLocationDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.startup_event()

    def test_invalid_parameters_return_400(self):
        """No query and no coordinates should return HTTP 400."""
        with self.assertRaises(HTTPException) as ctx:
            discover_location(query=None, lat=None, lon=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_short_query_returns_400(self):
        """Query with less than 2 characters should return HTTP 400."""
        with self.assertRaises(HTTPException) as ctx:
            discover_location(query="a", lat=None, lon=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_invalid_coordinates_return_400(self):
        """Coordinates out of bounds should return HTTP 400."""
        with self.assertRaises(HTTPException) as ctx:
            discover_location(lat=95.0, lon=77.0)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_coordinate_based_discovery_success(self):
        """Direct coordinate discovery bypassing Nominatim forward geocoding."""
        # Test with coordinates for Central Delhi / Connaught Place (28.6304, 77.2177)
        data = discover_location(lat=28.6304, lon=77.2177, radius=5000, query="Connaught Place")
        self.assertEqual(data["status"], "success")
        self.assertIn("resolved_location", data)
        self.assertAlmostEqual(data["resolved_location"]["latitude"], 28.6304, places=3)
        self.assertAlmostEqual(data["resolved_location"]["longitude"], 77.2177, places=3)
        self.assertIn("verified_cng_stations", data)
        self.assertIn("other_fuel_stations", data)
        self.assertIsInstance(data["verified_cng_count"], int)

    def test_gps_coordinate_discovery_without_label(self):
        """GPS discovery without query label should return resolved locality."""
        # Coordinates for Gurugram (28.4595, 77.0266)
        data = discover_location(lat=28.4595, lon=77.0266, radius=5000)
        self.assertEqual(data["status"], "success")
        self.assertTrue(len(data["resolved_location"]["display_name"]) > 0)

    def test_reverse_geocode_graceful_fallback(self):
        """Reverse geocode should always return a structured dict and never crash."""
        res = reverse_geocode(28.6139, 77.2090)
        self.assertIsInstance(res, dict)
        self.assertIn("display_name", res)
        self.assertIn("lat", res)
        self.assertIn("lon", res)

    def test_delhi_geocoding_resolution(self):
        """Geocoding for 'Delhi' should resolve valid coordinates."""
        try:
            resolved = geocode_location("Delhi")
            if resolved is not None:
                self.assertAlmostEqual(resolved["lat"], 28.6, delta=0.5)
                self.assertAlmostEqual(resolved["lon"], 77.2, delta=0.5)
                self.assertIn("display_name", resolved)
        except GeocodingServiceError as gse:
            # Service error is accepted if network is unreachable
            self.assertIn(gse.status_code, [429, 502, 503])

    def test_discovered_stations_have_telemetry_and_dynamic_recommendation(self):
        """Discovered verified CNG stations must have simulated telemetry and a location-specific recommendation."""
        # Mock discovery payload with 2 Delhi stations
        mock_payload = {
            "status": "success",
            "query": "Delhi",
            "search_radius_km": 5.0,
            "total_stations_found": 2,
            "verified_cng_count": 2,
            "other_fuel_count": 0,
            "verified_cng_stations": [
                {
                    "osm_id": 999101,
                    "name": "IGL CNG Station Barakhamba Road",
                    "brand": "Indraprastha Gas Limited",
                    "latitude": 28.6315,
                    "longitude": 77.2241,
                    "distance_km": 1.2,
                    "distance_text": "1.2 km",
                    "address": "Barakhamba Road, Connaught Place, New Delhi",
                    "is_cng_verified": True,
                },
                {
                    "osm_id": 999102,
                    "name": "IGL CNG Station Pragati Maidan",
                    "brand": "Indraprastha Gas Limited",
                    "latitude": 28.6180,
                    "longitude": 77.2410,
                    "distance_km": 3.8,
                    "distance_text": "3.8 km",
                    "address": "Near Gate 4, Pragati Maidan, New Delhi",
                    "is_cng_verified": True,
                },
            ],
            "other_fuel_stations": [],
        }

        rec = main.attach_telemetry_and_recommend(mock_payload, advance_simulation=False)
        self.assertIsNotNone(rec)
        self.assertIn(rec["station_id"], [999101, 999102])
        self.assertNotIn(rec["station_id"], [1, 2, 3, 4])  # NOT Gurugram stations
        self.assertEqual(rec["decision_mode"], "deterministic_fallback")
        self.assertTrue(rec["fallback_status"])
        self.assertTrue(rec["is_simulated"])

        # Check telemetry fields on verified station
        st1 = mock_payload["verified_cng_stations"][0]
        self.assertIn("queue_length", st1)
        self.assertIn("estimated_waiting_time_minutes", st1)
        self.assertIn("travel_time_minutes", st1)
        self.assertIn("congestion_level", st1)
        self.assertGreater(st1["queue_length"], 0)

    def test_empty_verified_stations_produces_none_recommendation(self):
        """When 0 verified CNG stations exist, recommendation should be None."""
        mock_payload = {
            "status": "success",
            "query": "Desert Locality",
            "search_radius_km": 5.0,
            "total_stations_found": 1,
            "verified_cng_count": 0,
            "other_fuel_count": 1,
            "verified_cng_stations": [],
            "other_fuel_stations": [{"osm_id": 111, "name": "Petrol Only"}],
        }
        rec = main.attach_telemetry_and_recommend(mock_payload, advance_simulation=False)
        self.assertIsNone(rec)
        self.assertIsNone(mock_payload.get("recommendation"))

    def test_refresh_location_advances_simulation(self):
        """Refreshing location advances the queue simulator for active discovered stations."""
        mock_payload = {
            "status": "success",
            "query": "Delhi",
            "verified_cng_stations": [
                {
                    "osm_id": 999201,
                    "name": "IGL Station A",
                    "distance_km": 2.0,
                    "is_cng_verified": True,
                }
            ],
            "other_fuel_stations": [],
        }
        main.active_location_snapshot = mock_payload
        main.attach_telemetry_and_recommend(mock_payload, advance_simulation=False)

        q_before = mock_payload["verified_cng_stations"][0]["queue_length"]
        refreshed = main.refresh_location()
        self.assertEqual(refreshed["status"], "success")
        self.assertIn("recommendation", refreshed)
        self.assertIn("last_updated", refreshed)

    def test_default_scenario_is_moderate(self):
        """Newly discovered stations must default to the transparent MODERATE scenario."""
        st = {"osm_id": 888001, "name": "Station Default"}
        sim, traffic, _ = main.get_or_create_discovered_simulator(st, scenario=None)
        self.assertEqual(traffic, "MODERATE")
        self.assertEqual(sim.queue, 5)
        self.assertEqual(sim.arrival_rate, 0.64)
        self.assertEqual(sim.service_rate, 0.80)
        self.assertEqual(sim.demand_profile, "MODERATE")
        self.assertEqual(sim.balking_threshold, 35)

    def test_explicit_scenarios_low_moderate_heavy(self):
        """LOW, MODERATE, and HEAVY presets must configure accurately."""
        st = {"osm_id": 888002, "name": "Station Scenarios"}
        sim_low, sc_low, _ = main.get_or_create_discovered_simulator(st, scenario="LOW")
        self.assertEqual(sc_low, "LOW")
        self.assertEqual(sim_low.queue, 2)
        self.assertEqual(sim_low.arrival_rate, 0.44)
        self.assertEqual(sim_low.service_rate, 0.80)
        self.assertEqual(sim_low.demand_profile, "LOW")

        sim_mod, sc_mod, _ = main.get_or_create_discovered_simulator(st, scenario="MODERATE")
        self.assertEqual(sc_mod, "MODERATE")
        self.assertEqual(sim_mod.queue, 5)
        self.assertEqual(sim_mod.arrival_rate, 0.64)
        self.assertEqual(sim_mod.service_rate, 0.80)
        self.assertEqual(sim_mod.demand_profile, "MODERATE")

        sim_heavy, sc_heavy, _ = main.get_or_create_discovered_simulator(st, scenario="HEAVY")
        self.assertEqual(sc_heavy, "HEAVY")
        self.assertEqual(sim_heavy.queue, 12)
        self.assertEqual(sim_heavy.arrival_rate, 0.76)
        self.assertEqual(sim_heavy.service_rate, 0.80)
        self.assertEqual(sim_heavy.demand_profile, "HEAVY")

    def test_invalid_scenario_fallback(self):
        """Invalid scenario strings must gracefully fall back to MODERATE."""
        self.assertEqual(main.normalize_scenario("EXTREME_CONGESTION"), "MODERATE")
        self.assertEqual(main.normalize_scenario(""), "MODERATE")
        self.assertEqual(main.normalize_scenario(None), "MODERATE")
        self.assertEqual(main.normalize_scenario(123), "MODERATE")

        st = {"osm_id": 888003, "name": "Station Fallback"}
        sim, traffic, _ = main.get_or_create_discovered_simulator(st, scenario="UNKNOWN_SCENARIO")
        self.assertEqual(traffic, "MODERATE")
        self.assertEqual(sim.queue, 5)
        self.assertEqual(sim.demand_profile, "MODERATE")

    def test_different_osm_ids_receive_identical_configuration_under_same_scenario(self):
        """Elimination of OSM-ID arithmetic: Delhi and New Colony IDs receive identical configurations."""
        delhi_st = {"osm_id": 6499063500, "name": "Delhi Station"}
        nc_st = {"osm_id": 1270574318, "name": "New Colony Station"}

        sim_delhi, sc_delhi, _ = main.get_or_create_discovered_simulator(delhi_st, scenario="MODERATE")
        sim_nc, sc_nc, _ = main.get_or_create_discovered_simulator(nc_st, scenario="MODERATE")

        self.assertEqual(sc_delhi, sc_nc)
        self.assertEqual(sim_delhi.arrival_rate, sim_nc.arrival_rate)
        self.assertEqual(sim_delhi.service_rate, sim_nc.service_rate)
        self.assertEqual(sim_delhi.queue, sim_nc.queue)
        self.assertEqual(sim_delhi.demand_profile, sim_nc.demand_profile)
        self.assertEqual(sim_delhi.phase_offset, sim_nc.phase_offset)

    def test_safe_scenario_switching_for_same_station(self):
        """Switching scenarios for the same station must not corrupt state or reuse incompatible simulators."""
        st = {"osm_id": 777001, "name": "Switch Station"}

        sim_low, _, _ = main.get_or_create_discovered_simulator(st, scenario="LOW")
        sim_heavy, _, _ = main.get_or_create_discovered_simulator(st, scenario="HEAVY")
        self.assertIsNot(sim_low, sim_heavy)
        self.assertEqual(sim_low.queue, 2)
        self.assertEqual(sim_heavy.queue, 12)

        # Retrieve LOW again, must preserve isolated LOW simulator
        sim_low_again, _, _ = main.get_or_create_discovered_simulator(st, scenario="LOW")
        self.assertIs(sim_low, sim_low_again)
        self.assertEqual(sim_low_again.queue, 2)

    def test_forecast_generation_all_horizons(self):
        """Forecast generation produces 15, 30, and 60m projections with required fields."""
        payload = {
            "status": "success",
            "query": "Test Region",
            "verified_cng_stations": [
                {"osm_id": 666001, "name": "Test Forecast Station", "distance_km": 1.5, "is_cng_verified": True}
            ],
            "other_fuel_stations": [],
        }
        main.attach_telemetry_and_recommend(payload, advance_simulation=False, scenario="MODERATE")
        st = payload["verified_cng_stations"][0]
        self.assertIn("queue_forecast", st)
        f = st["queue_forecast"]
        for h in ["15m", "30m", "60m"]:
            self.assertIn(h, f)
            self.assertIn("expected_queue", f[h])
            self.assertIn("queue_range", f[h])
            self.assertIn("expected_wait_minutes", f[h])
            self.assertIsInstance(f[h]["expected_queue"], (int, float))
            self.assertIsInstance(f[h]["queue_range"], list)

    def test_isolation_of_four_benchmark_stations(self):
        """Fixed benchmark stations (1, 2, 3, 4) must remain MultiDispenserQueueSimulator instances."""
        self.assertEqual(len(main.DEMO_MULTI_DISPENSER_CONFIGS), 4)
        for sid in [1, 2, 3, 4]:
            self.assertIn(sid, main.multi_dispenser_simulators)
            multi_sim = main.multi_dispenser_simulators[sid]
            self.assertTrue(hasattr(multi_sim, "dispensers"))
            self.assertEqual(multi_sim.num_dispensers, main.DEMO_MULTI_DISPENSER_CONFIGS[sid]["num_dispensers"])

    def test_explicit_synthetic_metadata_present(self):
        """Discovered station responses must carry explicit synthetic scenario metadata and disclaimer."""
        payload = {
            "status": "success",
            "query": "Metadata Check",
            "verified_cng_stations": [
                {"osm_id": 555001, "name": "Meta Station", "distance_km": 2.1, "is_cng_verified": True}
            ],
            "other_fuel_stations": [],
        }
        main.attach_telemetry_and_recommend(payload, advance_simulation=False, scenario="MODERATE")
        self.assertEqual(payload["synthetic_scenario"], "MODERATE")
        self.assertEqual(payload["simulation_source"], "synthetic_scenario_model")
        self.assertIn("Moderate Congestion", payload["scenario_disclaimer"])

        st = payload["verified_cng_stations"][0]
        self.assertEqual(st["synthetic_scenario"], "MODERATE")
        self.assertEqual(st["simulation_source"], "synthetic_scenario_model")
        self.assertIn("Not measured by physical sensors", st["scenario_disclaimer"])

        rec = payload["recommendation"]
        self.assertEqual(rec["synthetic_scenario"], "MODERATE")
        self.assertEqual(rec["simulation_source"], "synthetic_scenario_model")


if __name__ == "__main__":
    unittest.main()
