"""
Unit tests for Phase 3: Accurate Waiting-Time Calculations.
Verifies all Phase 3 criteria:
1. Per-dispenser waiting time formula: W_j = R_j + sum(E[D_j]) for waiting vehicles ahead.
2. Idle dispenser waiting time is exactly zero.
3. Busy dispenser with no waiting vehicles equals active vehicle residual service time.
4. Busy dispenser with waiting vehicles includes residual service + waiting vehicles' expected durations.
5. Waiting time strictly excludes the arriving vehicle's own fueling duration (system time vs wait time).
6. Support for different service distributions (Beta Line 1, Triangular Line 2, Constant, Exponential).
7. Independent line calculations across multiple dispensers.
8. Vehicle-weighted station-level average waiting time across currently waiting vehicles.
9. Accurate seconds-to-minutes conversions and rounding.
10. Legacy QueueSimulator and RL engine preservation and stability.
"""

import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from data.synthetic.queue_simulator import (
    DispenserChannel,
    MultiDispenserQueueSimulator,
    create_research_benchmark_simulator,
    QueueSimulator,
)
import rl_engine_v2


class TestPerDispenserWaitingTime(unittest.TestCase):
    def test_idle_dispenser_waiting_time_is_zero(self):
        """Verify an idle dispenser has exactly 0.0 seconds and 0.0 minutes waiting time."""
        disp = DispenserChannel(dispenser_id=1)
        self.assertEqual(disp.estimate_incoming_waiting_time(), 0.0)
        self.assertEqual(disp.estimate_incoming_waiting_time_minutes(), 0.0)

    def test_busy_dispenser_with_no_waiting_vehicles(self):
        """Verify busy dispenser with 0 waiting vehicles has wait equal to active residual service time."""
        disp = DispenserChannel(dispenser_id=1)
        veh = {"id": 1}
        disp.start_service(veh, duration_seconds=150.0)

        # 150 seconds remaining
        self.assertEqual(disp.estimate_incoming_waiting_time(), 150.0)
        self.assertEqual(disp.estimate_incoming_waiting_time_minutes(), 2.5)

        # Step 30 seconds -> 120 seconds remaining (2.0 min)
        disp.step_service(elapsed_seconds=30.0)
        self.assertEqual(disp.estimate_incoming_waiting_time(), 120.0)
        self.assertEqual(disp.estimate_incoming_waiting_time_minutes(), 2.0)

    def test_busy_dispenser_with_waiting_vehicles_ahead(self):
        """
        Verify busy dispenser with waiting vehicles calculates:
        W = R + k * E[D]
        """
        disp = DispenserChannel(
            dispenser_id=1,
            service_distribution="constant",
            service_params={"duration_seconds": 180.0},
        )
        disp.start_service({"id": 1}, duration_seconds=45.0)  # R = 45s
        disp.add_to_queue({"id": 2})                           # veh ahead 1
        disp.add_to_queue({"id": 3})                           # veh ahead 2

        # 2 vehicles waiting ahead, each expected to take 180s
        # Expected incoming wait: 45 + 2 * 180 = 405 seconds = 6.75 minutes
        expected_wait_s = 45.0 + 2 * 180.0
        self.assertEqual(disp.estimate_incoming_waiting_time(), expected_wait_s)
        self.assertEqual(disp.estimate_incoming_waiting_time_minutes(), 6.75)

    def test_waiting_time_excludes_arriving_vehicle_fueling_duration(self):
        """Verify waiting time strictly excludes the arriving vehicle's own service duration."""
        disp = DispenserChannel(
            dispenser_id=1,
            service_distribution="constant",
            service_params={"duration_seconds": 200.0},
        )
        disp.start_service({"id": 1}, duration_seconds=100.0)
        disp.add_to_queue({"id": 2})

        # Wait until fueling begins: 100 + 1 * 200 = 300s = 5.0 min
        self.assertEqual(disp.estimate_incoming_waiting_time(), 300.0)
        self.assertEqual(disp.estimate_incoming_waiting_time_minutes(), 5.0)

        # Total system time at station (wait + fueling): 300 + 200 = 500s = 8.33 min
        self.assertEqual(disp.estimate_total_system_time(), 500.0)
        self.assertEqual(disp.estimate_total_system_time_minutes(), 8.33)

    def test_expected_service_durations_across_distributions(self):
        """Verify theoretical mean service durations across Beta, Triangular, Constant, Exponential."""
        # Line 1 Beta: 233 + 179 * (0.904 / (0.904 + 1.03)) ~ 316.67 seconds
        d_beta = DispenserChannel(dispenser_id=1, service_distribution="beta_line1")
        expected_beta = 233.0 + 179.0 * (0.904 / (0.904 + 1.03))
        self.assertAlmostEqual(d_beta.get_expected_service_duration(), expected_beta, places=2)
        self.assertAlmostEqual(d_beta.get_expected_service_duration(), 316.67, delta=0.5)

        # Line 2 Triangular: (239 + 350 + 295) / 3 = 294.67 seconds
        d_tri = DispenserChannel(dispenser_id=2, service_distribution="triangular_line2")
        self.assertAlmostEqual(d_tri.get_expected_service_duration(), 294.67, places=2)

        # Constant: 120s
        d_const = DispenserChannel(
            dispenser_id=3,
            service_distribution="constant",
            service_params={"duration_seconds": 120.0},
        )
        self.assertEqual(d_const.get_expected_service_duration(), 120.0)

        # Exponential: 240s
        d_exp = DispenserChannel(
            dispenser_id=4,
            service_distribution="exponential",
            service_params={"mean_service_seconds": 240.0},
        )
        self.assertEqual(d_exp.get_expected_service_duration(), 240.0)


class TestStationLevelWaitingSummaries(unittest.TestCase):
    def test_multiple_dispensers_independent_line_waits(self):
        """Verify multiple dispensers calculate line waiting times independently."""
        sim = MultiDispenserQueueSimulator(num_dispensers=3, seed=42)

        # Dispenser 1: R=60s, k=2, D=300s -> W1 = 60 + 2*300 = 660s (11.0 min)
        sim.dispensers[0].start_service({"id": 1}, duration_seconds=60.0)
        sim.dispensers[0].add_to_queue({"id": 2})
        sim.dispensers[0].add_to_queue({"id": 3})

        # Dispenser 2: R=120s, k=0, D=300s -> W2 = 120s (2.0 min)
        sim.dispensers[1].start_service({"id": 4}, duration_seconds=120.0)

        # Dispenser 3: IDLE -> W3 = 0.0s (0.0 min)
        # sim.dispensers[2] remains idle

        per_disp_waits_s = sim.estimate_dispenser_waiting_times()
        self.assertEqual(per_disp_waits_s[1], 660.0)
        self.assertEqual(per_disp_waits_s[2], 120.0)
        self.assertEqual(per_disp_waits_s[3], 0.0)

        per_disp_waits_m = sim.estimate_dispenser_waiting_times_minutes()
        self.assertEqual(per_disp_waits_m[1], 11.0)
        self.assertEqual(per_disp_waits_m[2], 2.0)
        self.assertEqual(per_disp_waits_m[3], 0.0)

        # Incoming vehicle chooses shortest line (Dispenser 3 with N=0), so expected wait is 0.0!
        self.assertEqual(sim.estimate_incoming_waiting_time(), 0.0)
        self.assertEqual(sim.estimate_incoming_waiting_time_minutes(), 0.0)

        # Summary check
        summary = sim.estimate_waiting_time_summary()
        self.assertEqual(summary["min_dispenser_wait_minutes"], 0.0)
        self.assertEqual(summary["max_dispenser_wait_minutes"], 11.0)
        self.assertEqual(summary["incoming_user_wait_minutes"], 0.0)

    def test_incoming_waiting_time_weights_tied_shortest_lines(self):
        """
        Verify that when multiple dispensers have equally short lines (tied minimum N_j),
        the expected waiting time for an incoming vehicle is the analytical expectation
        weighted across all tied lines according to the tie-breaking probability (1 / |M|),
        rather than arbitrarily selecting one line.

        Example:
        Dispenser 1: N_1 = 1 (1 active, R_1 = 30s, k_1 = 0) -> W_1 = 30s
        Dispenser 2: N_2 = 1 (1 active, R_2 = 90s, k_2 = 0) -> W_2 = 90s
        Dispenser 3: N_3 = 3 (1 active, 2 waiting) -> W_3 = 600s (not tied)

        Shortest lines: Dispenser 1 and 2 (both N = 1, tie size = 2).
        Tie-breaking probability: 1/2 for Dispenser 1, 1/2 for Dispenser 2.
        Analytical expected incoming wait = (30 + 90) / 2 = 60 seconds (1.0 minute).
        """
        sim = MultiDispenserQueueSimulator(num_dispensers=3, seed=42)

        sim.dispensers[0].start_service({"id": 1}, duration_seconds=30.0)
        sim.dispensers[1].start_service({"id": 2}, duration_seconds=90.0)
        sim.dispensers[2].start_service({"id": 3}, duration_seconds=100.0)
        sim.dispensers[2].add_to_queue({"id": 4})
        sim.dispensers[2].add_to_queue({"id": 5})

        # N_0 = 1, N_1 = 1, N_2 = 3
        self.assertEqual(sim.get_effective_line_lengths(), [1, 1, 3])
        self.assertEqual(sim.get_shortest_dispenser_indices(), [0, 1])

        # Expected incoming wait must be exactly (30 + 90) / 2 = 60.0s = 1.0m
        self.assertEqual(sim.estimate_incoming_waiting_time(), 60.0)
        self.assertEqual(sim.estimate_incoming_waiting_time_minutes(), 1.0)

    def test_vehicle_weighted_average_waiting_time(self):
        """
        Verify vehicle-weighted average waiting time across all currently waiting vehicles:
        Dispenser 1: R=50s, k=2, D=100s
          - Vehicle 1 waits: 50s
          - Vehicle 2 waits: 50 + 100 = 150s
          - Sum Dispenser 1 = 200s
        Dispenser 2: R=80s, k=1, D=200s
          - Vehicle 1 waits: 80s
          - Sum Dispenser 2 = 80s
        Total waiting vehicles = 2 + 1 = 3
        Average = (200 + 80) / 3 = 280 / 3 = 93.33 seconds (1.56 min)
        """
        sim = MultiDispenserQueueSimulator(num_dispensers=2, seed=42)

        # Config dispenser 0 with constant 100s
        sim.dispensers[0].service_distribution = "constant"
        sim.dispensers[0].service_params = {"duration_seconds": 100.0}
        sim.dispensers[0].start_service({"id": 1}, duration_seconds=50.0)
        sim.dispensers[0].add_to_queue({"id": 2})
        sim.dispensers[0].add_to_queue({"id": 3})

        # Config dispenser 1 with constant 200s
        sim.dispensers[1].service_distribution = "constant"
        sim.dispensers[1].service_params = {"duration_seconds": 200.0}
        sim.dispensers[1].start_service({"id": 4}, duration_seconds=80.0)
        sim.dispensers[1].add_to_queue({"id": 5})

        avg_wait_s = sim.estimate_average_waiting_time_across_waiting_vehicles()
        self.assertAlmostEqual(avg_wait_s, 280.0 / 3.0, places=2)

        avg_wait_m = sim.estimate_average_waiting_time_across_waiting_vehicles_minutes()
        self.assertEqual(avg_wait_m, 1.56)

    def test_zero_waiting_vehicles_handles_gracefully(self):
        """Verify when no vehicles are waiting, average wait returns 0.0 with no zero-division."""
        sim = MultiDispenserQueueSimulator(num_dispensers=2)
        # Even with active vehicles fueling, if waiting queue is empty:
        sim.dispensers[0].start_service({"id": 1}, duration_seconds=100.0)
        sim.dispensers[1].start_service({"id": 2}, duration_seconds=100.0)

        self.assertEqual(sim.waiting_queue_length, 0)
        self.assertEqual(sim.estimate_average_waiting_time_across_waiting_vehicles(), 0.0)
        self.assertEqual(sim.estimate_average_waiting_time_across_waiting_vehicles_minutes(), 0.0)


class TestPreservationOfRLEngineAndLegacySimulator(unittest.TestCase):
    def test_rl_engine_and_q_table_fully_preserved(self):
        """CRITICAL: Verify Contextual Bandit RL engine in rl_engine_v2.py is intact with 36 contexts."""
        agent = rl_engine_v2.ContextualBanditAgent(actions=[1, 2, 3, 4])
        self.assertTrue(os.path.exists(rl_engine_v2.MODEL_PATH))
        agent.load_model(rl_engine_v2.MODEL_PATH)

        # Verify Q-table contains all 36 contexts
        self.assertEqual(len(agent.q_table), 36)
        # Verify sample context format
        self.assertIn(("S1_MODERATE_LOW", 1), agent.q_table)
        self.assertIn(("S4_HEAVY_HIGH", 4), agent.q_table)

    def test_legacy_simulator_intact(self):
        """Verify reference QueueSimulator produces backward-compatible wait times."""
        sim = QueueSimulator(initial_queue=6, arrival_rate=0.6, service_rate=0.75)
        # Wait = 6 / 0.75 = 8.0 min
        self.assertEqual(sim.estimate_waiting_time(), 8.0)


if __name__ == "__main__":
    unittest.main()

