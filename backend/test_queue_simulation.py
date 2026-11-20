"""
Unit and integration tests for NoQueue synthetic queue simulation stability and realism.
Verifies all criteria in Requirement 11:
1. Queues increase when arrivals exceed service.
2. Queues decrease when service exceeds arrivals.
3. Queues fluctuate plausibly under balanced conditions.
4. Waiting times respond correctly to queue changes (and 0 queue = 0 wait).
5. All four stations retain independent persistent simulation states.
6. Dashboard refresh and recommendation consistency still work.
7. Long-term simulation stability (500 steps) without queue explosion.
"""

import os
import sys
import unittest

# Ensure backend root is on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from data.synthetic.queue_simulator import QueueSimulator
import main


class TestQueueSimulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.startup_event()
    def test_queue_increases_when_arrivals_exceed_service(self):
        """Verify queue increases when arrival rate significantly exceeds service rate."""
        sim = QueueSimulator(initial_queue=5, arrival_rate=3.0, service_rate=0.2)
        initial_q = sim.queue
        for _ in range(25):
            sim.step()
        self.assertGreater(
            sim.queue,
            initial_q,
            f"Expected queue to increase from {initial_q}, got {sim.queue}"
        )
        self.assertGreaterEqual(sim.queue, 25)

    def test_queue_decreases_when_service_exceeds_arrivals(self):
        """Verify queue decreases when service rate significantly exceeds arrival rate."""
        sim = QueueSimulator(initial_queue=30, arrival_rate=0.1, service_rate=2.5)
        initial_q = sim.queue
        for _ in range(20):
            sim.step()
        self.assertLess(
            sim.queue,
            initial_q,
            f"Expected queue to decrease from {initial_q}, got {sim.queue}"
        )
        self.assertLessEqual(sim.queue, 10)

    def test_queue_fluctuates_plausibly_under_balanced_conditions(self):
        """Verify queue fluctuates within a plausible range under balanced conditions."""
        sim = QueueSimulator(initial_queue=6, arrival_rate=0.65, service_rate=0.75)
        queues = []
        for _ in range(200):
            sim.step()
            queues.append(sim.queue)

        max_q = max(queues)
        min_q = min(queues)

        self.assertLess(
            max_q,
            30,
            f"Queue exploded under balanced conditions: max={max_q}"
        )
        self.assertGreaterEqual(min_q, 0)
        # Should experience both upward and downward movement
        self.assertGreater(len(set(queues)), 3, "Queue should fluctuate across distinct values")

    def test_waiting_time_responds_to_queue_changes(self):
        """Verify waiting time formula and behavior: wait = queue / service_rate, wait(0) = 0."""
        sim = QueueSimulator(initial_queue=0, arrival_rate=0.5, service_rate=0.8)
        self.assertEqual(sim.estimate_waiting_time(), 0.0, "Zero queue must produce 0.0 waiting time")

        sim.queue = 8
        self.assertEqual(sim.estimate_waiting_time(), 10.0)

        sim.queue = 16
        self.assertEqual(sim.estimate_waiting_time(), 20.0)

        sim.queue = 24
        self.assertEqual(sim.estimate_waiting_time(), 30.0)

        sim.queue = 0
        self.assertEqual(sim.estimate_waiting_time(), 0.0)

    def test_congestion_level_boundaries(self):
        """Verify LOW (<=10), MEDIUM (10.1-20), HIGH (>20)."""
        sim = QueueSimulator(initial_queue=0, arrival_rate=0.5, service_rate=1.0)
        # 0 wait -> LOW
        self.assertEqual(sim.get_congestion_level(), "LOW")

        # 10 wait -> LOW
        sim.queue = 10
        self.assertEqual(sim.get_congestion_level(), "LOW")

        # 11 wait -> MEDIUM
        sim.queue = 11
        self.assertEqual(sim.get_congestion_level(), "MEDIUM")

        # 20 wait -> MEDIUM
        sim.queue = 20
        self.assertEqual(sim.get_congestion_level(), "MEDIUM")

        # 21 wait -> HIGH
        sim.queue = 21
        self.assertEqual(sim.get_congestion_level(), "HIGH")

    def test_four_stations_independent_persistent_states(self):
        """Verify all 4 stations retain independent persistent simulation instances."""
        main.station_simulators.clear()
        main.station_scenarios.clear()
        main.init_persistent_simulators()

        self.assertEqual(len(main.station_simulators), 4)
        sim_ids = [id(main.station_simulators[s]) for s in [1, 2, 3, 4]]
        self.assertEqual(len(set(sim_ids)), 4, "Each station must have a distinct QueueSimulator instance")

        # Record initial queues
        q_init = {s: main.station_simulators[s].queue for s in [1, 2, 3, 4]}

        # Advance simulation by 1 step
        stations, rec = main.build_snapshot(advance_simulation=True)
        self.assertEqual(len(stations), 4)

        # Simulator objects must have persisted (same memory addresses)
        self.assertEqual([id(main.station_simulators[s]) for s in [1, 2, 3, 4]], sim_ids)

    def test_long_term_stability_across_all_stations(self):
        """Verify 500 dashboard steps do not cause queue accumulation to hundreds of vehicles."""
        main.station_simulators.clear()
        main.station_scenarios.clear()
        main.init_persistent_simulators()

        history = {s: [] for s in [1, 2, 3, 4]}
        for _ in range(500):
            stations, rec = main.build_snapshot(advance_simulation=True, include_forecast=False)
            for st in stations:
                history[st["id"]].append(st["queue"])

        for s_id in [1, 2, 3, 4]:
            max_q = max(history[s_id])
            mean_q = sum(history[s_id]) / len(history[s_id])
            self.assertLess(
                max_q,
                50,
                f"Station {s_id} experienced unrealistic queue accumulation: max={max_q}"
            )
            self.assertLess(
                mean_q,
                20,
                f"Station {s_id} mean queue too high: mean={mean_q:.1f}"
            )

    def test_dashboard_and_recommendation_consistency(self):
        """Verify recommended station matches one of the dashboard stations in telemetry."""
        main.station_simulators.clear()
        main.station_scenarios.clear()
        main.init_persistent_simulators()

        stations, rec = main.build_snapshot(advance_simulation=True)
        rec_st = rec.get("station", {})
        chosen_id = rec.get("station_id")

        matching_st = next((s for s in stations if s["id"] == chosen_id), None)
        self.assertIsNotNone(matching_st, "Recommended station must exist in dashboard stations")
        self.assertEqual(matching_st["queue"], rec_st.get("queue"))
        self.assertEqual(matching_st["waitTime"], rec_st.get("waitTime") or int(round(rec.get("estimated_waiting_time_minutes", 0))))
        self.assertEqual(matching_st["travelTime"], rec_st.get("travelTime") or rec.get("estimated_travel_time_minutes"))

    def test_dynamic_demand_surge_and_recovery(self):
        """Verify dynamic demand profile produces peak queues of 15-30+ vehicles and recovers during troughs."""
        sim = QueueSimulator(
            initial_queue=18,
            arrival_rate=0.92,
            service_rate=0.85,
            demand_profile="HEAVY",
            cycle_period=60,
            phase_offset=0,
            balking_threshold=35,
        )
        queues = []
        for _ in range(60):
            sim.step()
            queues.append(sim.queue)

        max_q = max(queues)
        min_q = min(queues)

        self.assertGreaterEqual(
            max_q, 18,
            f"Expected peak surge to reach at least 18 vehicles, reached {max_q}"
        )
        self.assertLess(
            min_q, max_q,
            "Expected queue to recover during demand trough"
        )
        self.assertLess(
            max_q, 40,
            f"Balking should keep peak queue bounded, got {max_q}"
        )

    def test_balking_safety_mechanism_prevents_unbounded_growth(self):
        """Verify driver balking factor dampens arrivals as queue approaches balking threshold."""
        sim = QueueSimulator(
            initial_queue=15,
            arrival_rate=3.0,  # Overwhelming arrival rate
            service_rate=0.8,
            demand_profile="STATIC",
            balking_threshold=35,
        )
        queues = []
        for _ in range(300):
            sim.step()
            queues.append(sim.queue)

        max_q = max(queues)
        # Without balking, queue would reach ~660 vehicles (300 * (3.0 - 0.8)).
        # With quadratic balking (threshold=35), queue stays naturally bounded near or under 40.
        self.assertLess(
            max_q, 45,
            f"Balking failed to bound queue under extreme arrivals: max={max_q}"
        )

    def test_low_demand_profile_stays_calm(self):
        """Verify LOW demand profile stays within calm range (2-6 vehicles)."""
        sim = QueueSimulator(
            initial_queue=3,
            arrival_rate=0.45,
            service_rate=0.85,
            demand_profile="LOW",
            cycle_period=60,
            phase_offset=0,
            balking_threshold=35,
        )
        queues = []
        for _ in range(120):
            sim.step()
            queues.append(sim.queue)

        max_q = max(queues)
        mean_q = sum(queues) / len(queues)

        self.assertLessEqual(max_q, 10, f"LOW profile exceeded calm ceiling: max={max_q}")
        self.assertLess(mean_q, 5.0, f"LOW profile mean queue too high: mean={mean_q:.1f}")


if __name__ == "__main__":
    unittest.main()
