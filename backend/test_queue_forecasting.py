"""
Unit and integration tests for NoQueue Queue Forecasting feature.
Verifies all 8 required criteria:
1. Output format: contains '15m', '30m', and '60m' horizons.
2. Value validity: expected_queue >= 0 and expected_wait_minutes >= 0.0.
3. Range validity: queue_range has 2 elements and p10 <= p90.
4. Queue immutability: simulator's actual queue is identical before and after forecast().
5. No step advancement: forecasting does not advance or step the live simulator.
6. Rate sensitivity: different arrival/service rates yield distinct, physically consistent forecasts.
7. Zero service rate safety: service_rate = 0 is handled safely without ZeroDivisionError.
8. API payload integration: /api/dashboard, /api/location/discover, and /api/location/refresh include queue_forecast.
"""

import os
import sys
import unittest
from unittest.mock import patch

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from data.synthetic.queue_simulator import QueueSimulator
import main


class TestQueueForecasting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.startup_event()

    def test_01_horizon_keys_present(self):
        """Criterion 1: Forecast output contains 15m, 30m, and 60m keys."""
        sim = QueueSimulator(initial_queue=5, arrival_rate=0.6, service_rate=0.8)
        result = sim.forecast(horizons=(15, 30, 60), trials=500, seed=42)

        self.assertIn("15m", result)
        self.assertIn("30m", result)
        self.assertIn("60m", result)

        for h in ("15m", "30m", "60m"):
            self.assertIn("expected_queue", result[h])
            self.assertIn("queue_range", result[h])
            self.assertIn("expected_wait_minutes", result[h])

    def test_02_non_negative_values(self):
        """Criterion 2: Expected queue and waiting time are non-negative."""
        sim = QueueSimulator(initial_queue=4, arrival_rate=0.5, service_rate=0.75)
        result = sim.forecast(trials=500, seed=123)

        for h, data in result.items():
            self.assertGreaterEqual(
                data["expected_queue"], 0,
                f"expected_queue for {h} must be >= 0"
            )
            self.assertGreaterEqual(
                data["expected_wait_minutes"], 0.0,
                f"expected_wait_minutes for {h} must be >= 0.0"
            )
            self.assertIsInstance(data["expected_queue"], (int, float))
            self.assertIsInstance(data["expected_wait_minutes"], (int, float))

    def test_03_queue_range_bounds(self):
        """Criterion 3: queue_range has 2 elements and p10 <= p90."""
        sim = QueueSimulator(initial_queue=8, arrival_rate=0.8, service_rate=0.7)
        result = sim.forecast(trials=500, seed=99)

        for h, data in result.items():
            q_range = data["queue_range"]
            self.assertIsInstance(q_range, list)
            self.assertEqual(len(q_range), 2, f"queue_range for {h} must have length 2")
            p10, p90 = q_range
            self.assertGreaterEqual(p10, 0, f"p10 for {h} must be >= 0")
            self.assertLessEqual(p10, p90, f"p10 ({p10}) must be <= p90 ({p90}) for {h}")

    def test_04_simulator_queue_immutability(self):
        """Criterion 4: Simulator's actual queue is identical before and after forecast()."""
        sim = QueueSimulator(initial_queue=7, arrival_rate=0.65, service_rate=0.75)
        q_before = sim.queue

        result = sim.forecast(trials=500)
        q_after = sim.queue

        self.assertEqual(
            q_before, q_after,
            f"Queue mutated during forecast: before={q_before}, after={q_after}"
        )
        self.assertEqual(sim.queue, 7)

    def test_05_no_step_advancement(self):
        """Criterion 5: Forecasting does not advance or step the live simulator."""
        sim = QueueSimulator(initial_queue=10, arrival_rate=0.7, service_rate=0.8)

        # Call forecast multiple times
        for _ in range(5):
            sim.forecast(trials=500)

        # Confirm queue is still exactly 10 and step hasn't been called
        self.assertEqual(sim.queue, 10)

        # Now call actual live step() and verify it behaves normally from Q=10
        step_out = sim.step(duration=1)
        self.assertEqual(step_out["previous_queue"], 10)

    def test_06_rate_sensitivity(self):
        """Criterion 6: Different arrival/service rates yield distinct, consistent forecasts."""
        # Congested station: high arrival (1.5), low service (0.4) -> queue must grow
        congested_sim = QueueSimulator(initial_queue=5, arrival_rate=1.5, service_rate=0.4)
        congested_fc = congested_sim.forecast(horizons=(15, 30, 60), trials=500, seed=10)

        # Clearing station: initial queue 25, low arrival (0.1), service (0.5) -> queue gradually clears
        clearing_sim = QueueSimulator(initial_queue=25, arrival_rate=0.1, service_rate=0.5)
        clearing_fc = clearing_sim.forecast(horizons=(15, 30, 60), trials=500, seed=10)

        self.assertGreater(
            congested_fc["60m"]["expected_queue"],
            congested_fc["15m"]["expected_queue"],
            "Congested station queue should trend upward over time"
        )
        self.assertLess(
            clearing_fc["60m"]["expected_queue"],
            clearing_fc["15m"]["expected_queue"],
            "Clearing station queue should trend downward over time"
        )
        self.assertGreater(
            congested_fc["60m"]["expected_queue"],
            clearing_fc["60m"]["expected_queue"]
        )

    def test_07_zero_service_rate_safe(self):
        """Criterion 7: Service rate = 0 is handled safely without ZeroDivisionError."""
        sim = QueueSimulator(initial_queue=3, arrival_rate=0.5, service_rate=0.0)
        try:
            fc = sim.forecast(trials=100, seed=1)
            self.assertIn("15m", fc)
            self.assertEqual(fc["15m"]["expected_wait_minutes"], 0.0)
        except ZeroDivisionError:
            self.fail("forecast() raised ZeroDivisionError when service_rate=0")

    def test_08_api_endpoints_include_queue_forecast(self):
        """Criterion 8: /api/dashboard and location discovery endpoints return queue_forecast."""
        # 1. /api/dashboard
        dashboard_data = main.get_dashboard()
        self.assertEqual(dashboard_data["status"], "success")
        self.assertIn("stations", dashboard_data)
        for st in dashboard_data["stations"]:
            self.assertIn("queue_forecast", st, f"Station {st['id']} in /api/dashboard missing queue_forecast")
            fc = st["queue_forecast"]
            self.assertIn("15m", fc)
            self.assertIn("30m", fc)
            self.assertIn("60m", fc)

        rec = dashboard_data.get("recommendation", {})
        if rec and rec.get("station"):
            self.assertIn("queue_forecast", rec["station"])
            self.assertIn("queue_forecast", rec)

        # 2. /api/location/discover (with mock OSM discovery)
        mock_discovery = {
            "total_stations_found": 1,
            "verified_cng_count": 1,
            "other_fuel_count": 0,
            "message": "Found 1 station",
            "verified_cng_stations": [
                {
                    "osm_id": 99901,
                    "name": "Test CNG Station",
                    "latitude": 28.45,
                    "longitude": 77.02,
                    "distance_km": 2.5,
                    "travel_time_minutes": 8.0,
                    "tags": {"fuel:cng": "yes"},
                }
            ],
            "other_fuel_stations": [],
        }

        with patch("main.discover_nearby_stations", return_value=mock_discovery):
            with patch("main.reverse_geocode", return_value={"display_name": "Test Location"}):
                loc_res = main.discover_location(lat=28.45, lon=77.02, radius=5000)
                self.assertEqual(loc_res["status"], "success")
                st = loc_res["verified_cng_stations"][0]
                self.assertIn("queue_forecast", st)
                self.assertIn("15m", st["queue_forecast"])
                self.assertIn("30m", st["queue_forecast"])
                self.assertIn("60m", st["queue_forecast"])

                rec = loc_res.get("recommendation")
                self.assertIsNotNone(rec)
                self.assertIn("queue_forecast", rec)
                self.assertIn("queue_forecast", rec["station"])

                # 3. /api/location/refresh
                refresh_res = main.refresh_location()
                self.assertEqual(refresh_res["status"], "success")
                refreshed_st = refresh_res["verified_cng_stations"][0]
                self.assertIn("queue_forecast", refreshed_st)
                self.assertIn("15m", refreshed_st["queue_forecast"])
                self.assertIn("30m", refreshed_st["queue_forecast"])
                self.assertIn("60m", refreshed_st["queue_forecast"])


if __name__ == "__main__":
    unittest.main()
