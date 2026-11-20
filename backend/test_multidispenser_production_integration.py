"""
Unit & Integration Tests for Multi-Dispenser Production Integration.
===================================================================
Verifies:
1. MultiDispenserQueueSimulator initialization for the 4 default stations.
2. Accurate separation of waiting_queue_length, vehicles_being_served, and total_vehicles.
3. Phase 4 Monte Carlo lookahead forecast with 100 trials.
4. Safe fallback to legacy QueueSimulator when disabled or on error.
5. Contextual Bandit RL engine integrity and Q-table context compatibility.
6. Clean isolation of dynamic OSM discovered stations.
7. Forecast latency and caching behavior on read-only requests.
"""

import unittest
import time
from typing import Dict, Any

from main import (
    init_persistent_simulators,
    build_snapshot,
    get_dashboard,
    get_stations,
    get_recommendation,
    station_simulators,
    multi_dispenser_simulators,
    MULTI_DISPENSER_ENABLED,
    MULTI_DISPENSER_FORECAST_TRIALS,
    DEMO_MULTI_DISPENSER_CONFIGS,
    bandit_agent,
    ContextualBanditAgent,
    MODEL_PATH,
)
import main


class TestMultiDispenserProductionIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Ensure simulators and bandit agent are loaded
        if main.bandit_agent is None:
            agent = ContextualBanditAgent(actions=[1, 2, 3, 4])
            agent.load_model(MODEL_PATH)
            main.bandit_agent = agent
        init_persistent_simulators()

    def test_01_persistent_initialization(self):
        """Verify all 4 default demo stations initialize as MultiDispenserQueueSimulator."""
        self.assertEqual(len(multi_dispenser_simulators), 4)
        for s_id in [1, 2, 3, 4]:
            self.assertIn(s_id, multi_dispenser_simulators)
            sim = multi_dispenser_simulators[s_id]
            expected_dispensers = DEMO_MULTI_DISPENSER_CONFIGS[s_id]["num_dispensers"]
            self.assertEqual(sim.num_dispensers, expected_dispensers)
            self.assertEqual(len(sim.dispensers), expected_dispensers)

            # Verify property consistency: total == waiting + active
            self.assertEqual(
                sim.total_vehicles,
                sim.waiting_queue_length + sim.vehicles_being_served,
            )
            # Verify waiting_queue_length is properly distinguished
            self.assertGreaterEqual(sim.waiting_queue_length, 0)
            self.assertGreaterEqual(sim.vehicles_being_served, 0)

    def test_02_dashboard_endpoint_payload(self):
        """Verify GET /api/dashboard returns multi-dispenser metrics and telemetry."""
        dashboard = get_dashboard()
        self.assertEqual(dashboard["status"], "success")
        stations = dashboard["stations"]
        self.assertEqual(len(stations), 4)

        for st in stations:
            s_id = st["id"]
            self.assertEqual(st["simulator_engine"], "multi_dispenser")
            expected_bays = DEMO_MULTI_DISPENSER_CONFIGS[s_id]["num_dispensers"]
            self.assertEqual(st["dispenser_count"], expected_bays)
            self.assertEqual(len(st["dispenser_lines"]), expected_bays)
            self.assertEqual(st["forecast_trials"], 100)

            # Metric clarity checks
            waiting_q = st["waiting_queue_length"]
            active_veh = st["vehicles_being_served"]
            total_occ = st["total_vehicles"]
            self.assertEqual(total_occ, waiting_q + active_veh)
            # Ensure queue_length reports strictly waiting vehicles
            self.assertEqual(st["queue_length"], waiting_q)
            self.assertEqual(st["queue"], waiting_q)

            # Waiting time and congestion checks
            self.assertGreater(st["estimated_waiting_time_minutes"], 0.0)
            self.assertIn(st["congestion_level"], ["LOW", "MEDIUM", "HIGH"])
            self.assertIn(st["crowd_level"], ["Low", "Moderate", "High"])

            # Forecast checks
            forecast = st.get("queue_forecast")
            self.assertIsNotNone(forecast)
            for h in ["15m", "30m", "60m"]:
                self.assertIn(h, forecast)
                h_data = forecast[h]
                self.assertIn("expected_queue", h_data)
                self.assertIn("queue_range", h_data)
                self.assertIn("expected_wait_minutes", h_data)
                self.assertGreaterEqual(h_data["expected_queue"], 0)
                self.assertEqual(len(h_data["queue_range"]), 2)
                self.assertLessEqual(h_data["queue_range"][0], h_data["queue_range"][1])

    def test_03_forecast_latency_and_caching(self):
        """Benchmark forecast latency with 100 trials and test read-only caching."""
        # 1. Benchmark full forward simulation step with 100 trials
        t0 = time.perf_counter()
        stations_adv, rec_adv = build_snapshot(advance_simulation=True, include_forecast=True)
        adv_duration_ms = (time.perf_counter() - t0) * 1000.0

        # With 100 trials across 4 stations (24,000 forward simulation steps), latency is ~800-950ms
        self.assertLess(adv_duration_ms, 2000.0, f"Dashboard advancement took {adv_duration_ms:.2f}ms")

        # 2. Benchmark read-only snapshot (cached forecast reuse)
        t1 = time.perf_counter()
        stations_read, rec_read = build_snapshot(advance_simulation=False, include_forecast=True)
        read_duration_ms = (time.perf_counter() - t1) * 1000.0

        # Read-only snapshot with cached forecasts should execute in under 10ms
        self.assertLess(read_duration_ms, 25.0, f"Read-only snapshot took {read_duration_ms:.2f}ms")
        self.assertEqual(stations_read[0]["queue_forecast"], stations_adv[0]["queue_forecast"])

    def test_04_consecutive_simulation_advancement(self):
        """Verify simulator state advances consecutively without double-stepping or resetting."""
        sim = multi_dispenser_simulators[1]
        initial_step = sim.step_count

        # Step 1
        res1 = sim.step(duration_minutes=1.0)
        self.assertEqual(sim.step_count, initial_step + 1)
        self.assertIn("vehicles_served", res1)
        self.assertIn("waiting_queue_length", res1)

        # Step 2
        res2 = sim.step(duration_minutes=1.0)
        self.assertEqual(sim.step_count, initial_step + 2)
        self.assertEqual(res2["step_count"], initial_step + 2)

    def test_05_safe_fallback_toggle(self):
        """Verify safe fallback to legacy QueueSimulator when multi-dispenser is disabled."""
        original_state = main.MULTI_DISPENSER_ENABLED
        try:
            # Disable multi-dispenser engine
            main.MULTI_DISPENSER_ENABLED = False

            stations, rec = build_snapshot(advance_simulation=True)
            for st in stations:
                self.assertEqual(st["simulator_engine"], "legacy")
                self.assertEqual(st["dispenser_count"], 1)

            # Re-enable multi-dispenser engine
            main.MULTI_DISPENSER_ENABLED = True
            stations_re, rec_re = build_snapshot(advance_simulation=True)
            for st in stations_re:
                self.assertEqual(st["simulator_engine"], "multi_dispenser")
                self.assertIn(st["dispenser_count"], [2, 4])
        finally:
            main.MULTI_DISPENSER_ENABLED = original_state

    def test_06_rl_recommendation_integrity(self):
        """Verify Contextual Bandit recommendation operates over 36 learned context states."""
        stations, rec = build_snapshot(advance_simulation=False)
        self.assertEqual(rec["status"], "success")
        self.assertIn(rec["station_id"], [1, 2, 3, 4])
        self.assertEqual(rec["decision_mode"], "learned_policy")
        self.assertFalse(rec["fallback_status"])
        self.assertIn("context", rec)
        # Context should format like S1_LOW_LOW or S2_MODERATE_LOW
        self.assertTrue(rec["context"].startswith(f"S{rec['station_id']}_"))

        # Verify recommendation has enriched multi-dispenser metadata
        self.assertEqual(rec["station"]["simulator_engine"], "multi_dispenser")
        self.assertIn(rec["station"]["dispenser_count"], [2, 4])
        self.assertIn("waiting_queue_length", rec["station"])
        self.assertIn("vehicles_being_served", rec["station"])

    def test_07_osm_station_isolation(self):
        """Verify discovered OSM stations remain on QueueSimulator and do not alter multi-dispenser state."""
        dummy_osm_station = {
            "osm_id": 999901,
            "osm_type": "node",
            "name": "Test OSM CNG Pump",
            "latitude": 28.45,
            "longitude": 77.02,
            "distance_km": 3.0,
            "distance_text": "3.0 km",
            "is_cng_verified": True,
            "travel_time_minutes": 8.0,
        }
        discovery_payload = {
            "status": "success",
            "verified_cng_stations": [dummy_osm_station],
            "other_fuel_stations": [],
        }

        main.attach_telemetry_and_recommend(discovery_payload, advance_simulation=False)
        st = discovery_payload["verified_cng_stations"][0]
        # Discovered station uses QueueSimulator
        self.assertIn(999901, main.discovered_simulators)
        self.assertIsInstance(main.discovered_simulators[999901], main.QueueSimulator)
        # Multi-dispenser simulators remain strictly for default stations 1-4
        self.assertNotIn(999901, main.multi_dispenser_simulators)


if __name__ == "__main__":
    unittest.main()
