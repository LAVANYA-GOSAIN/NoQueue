"""
Unit tests for Phase 1: Multi-Dispenser State and Independent Service Logic.
Verifies all Phase 1 criteria:
1. Multi-dispenser internal state with independent dispenser channels.
2. Independent tracking of waiting queue, active vehicle, remaining service time, and status.
3. Clear distinction:
   - waiting_queue_length: vehicles waiting, excluding active vehicle.
   - vehicles_being_served: vehicles currently being served.
   - total_vehicles: total vehicles in the station system.
4. Simultaneous parallel service without double-speed pooling.
5. Transition of waiting vehicles into active service on completion.
6. Support for arbitrary dispenser counts (1, 2, 3, 4).
7. Research paper benchmark distributions (Line 1 Beta, Line 2 Triangular).
8. Legacy QueueSimulator reference availability and stability.
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


class TestDispenserChannel(unittest.TestCase):
    def test_dispenser_initial_state(self):
        """Verify dispenser initializes with IDLE status and zero counts."""
        disp = DispenserChannel(dispenser_id=1, name="Bay 1")
        self.assertEqual(disp.dispenser_id, 1)
        self.assertEqual(disp.name, "Bay 1")
        self.assertEqual(disp.status, "IDLE")
        self.assertFalse(disp.is_busy)
        self.assertEqual(disp.waiting_count, 0)
        self.assertEqual(disp.active_count, 0)
        self.assertEqual(disp.total_count, 0)
        self.assertEqual(disp.remaining_service_time, 0.0)
        self.assertIsNone(disp.active_vehicle)

    def test_start_service_and_add_to_queue(self):
        """Verify clear distinction between active vehicle and waiting queue."""
        disp = DispenserChannel(dispenser_id=1)

        # Start service on active vehicle
        veh1 = {"id": 101, "arrival_time": 0.0}
        disp.start_service(vehicle=veh1, duration_seconds=180.0)

        self.assertTrue(disp.is_busy)
        self.assertEqual(disp.status, "BUSY")
        self.assertEqual(disp.active_count, 1)
        self.assertEqual(disp.waiting_count, 0)
        self.assertEqual(disp.total_count, 1)
        self.assertEqual(disp.remaining_service_time, 180.0)
        self.assertEqual(disp.active_vehicle["id"], 101)

        # Add two vehicles to waiting queue
        veh2 = {"id": 102, "arrival_time": 10.0}
        veh3 = {"id": 103, "arrival_time": 20.0}
        disp.add_to_queue(veh2)
        disp.add_to_queue(veh3)

        self.assertEqual(disp.active_count, 1)
        self.assertEqual(disp.waiting_count, 2)
        self.assertEqual(disp.total_count, 3)

    def test_independent_service_countdown_and_completion(self):
        """Verify remaining service time decrements accurately and transitions next waiting vehicle."""
        disp = DispenserChannel(
            dispenser_id=1,
            service_distribution="constant",
            service_params={"duration_seconds": 120.0},
        )
        veh1 = {"id": 201}
        veh2 = {"id": 202}

        disp.start_service(veh1, duration_seconds=60.0)
        disp.add_to_queue(veh2)

        # Step 30 seconds -> 30s remaining
        completed = disp.step_service(elapsed_seconds=30.0)
        self.assertEqual(len(completed), 0)
        self.assertEqual(disp.remaining_service_time, 30.0)
        self.assertEqual(disp.waiting_count, 1)

        # Step another 30 seconds -> veh1 finishes (60s total), veh2 transitions to active with 120s
        completed = disp.step_service(elapsed_seconds=30.0)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["id"], 201)
        self.assertEqual(disp.active_vehicle["id"], 202)
        self.assertEqual(disp.remaining_service_time, 120.0)
        self.assertEqual(disp.waiting_count, 0)
        self.assertEqual(disp.total_count, 1)

        # Step 120 seconds -> veh2 finishes, dispenser becomes IDLE
        completed = disp.step_service(elapsed_seconds=120.0)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["id"], 202)
        self.assertFalse(disp.is_busy)
        self.assertEqual(disp.status, "IDLE")
        self.assertEqual(disp.remaining_service_time, 0.0)
        self.assertIsNone(disp.active_vehicle)
        self.assertEqual(disp.total_vehicles_served, 2)


class TestMultiDispenserSimulator(unittest.TestCase):
    def test_multi_dispenser_initialization_and_counts(self):
        """Verify multi-dispenser simulator initializes independent channels and distinct counts."""
        sim = MultiDispenserQueueSimulator(num_dispensers=3)
        self.assertEqual(sim.num_dispensers, 3)
        self.assertEqual(len(sim.dispensers), 3)
        self.assertEqual(sim.waiting_queue_length, 0)
        self.assertEqual(sim.vehicles_being_served, 0)
        self.assertEqual(sim.total_vehicles, 0)

        # Populate channels independently
        sim.dispensers[0].start_service({"id": 1}, duration_seconds=100.0)
        sim.dispensers[0].add_to_queue({"id": 2})

        sim.dispensers[1].start_service({"id": 3}, duration_seconds=200.0)
        sim.dispensers[1].add_to_queue({"id": 4})
        sim.dispensers[1].add_to_queue({"id": 5})

        # Dispenser 2 remains idle
        self.assertEqual(sim.vehicles_being_served, 2)  # Dispensers 0 and 1 are busy
        self.assertEqual(sim.waiting_queue_length, 3)  # 1 on disp 0, 2 on disp 1
        self.assertEqual(sim.total_vehicles, 5)        # 2 active + 3 waiting
        self.assertEqual(sim.queue, 5)                 # Backward-compatible property

    def test_simultaneous_parallel_service_no_server_pooling(self):
        """
        Verify multiple dispensers serve vehicles simultaneously.
        Does NOT pool 2 dispensers into a single 2x faster server.
        """
        sim = MultiDispenserQueueSimulator(num_dispensers=2)

        # Both dispensers start a vehicle with 100 seconds service duration
        sim.dispensers[0].start_service({"id": 10}, duration_seconds=100.0)
        sim.dispensers[1].start_service({"id": 20}, duration_seconds=100.0)

        # Step 60 seconds
        step_result = sim.step_dispensers(duration_seconds=60.0)
        self.assertEqual(step_result["total_vehicles_served"], 0)
        # Both vehicles should have 40 seconds remaining
        self.assertAlmostEqual(sim.dispensers[0].remaining_service_time, 40.0)
        self.assertAlmostEqual(sim.dispensers[1].remaining_service_time, 40.0)

        # Step another 60 seconds -> BOTH vehicles finish during this step
        step_result = sim.step_dispensers(duration_seconds=60.0)
        self.assertEqual(step_result["total_vehicles_served"], 2)
        self.assertEqual(sim.vehicles_being_served, 0)
        self.assertEqual(sim.total_vehicles, 0)

    def test_arbitrary_dispenser_counts(self):
        """Verify simulator works cleanly for 1, 2, 4 dispensers without 2-dispenser assumptions."""
        for c in [1, 2, 4]:
            sim = MultiDispenserQueueSimulator(num_dispensers=c)
            self.assertEqual(len(sim.dispensers), c)
            for i, disp in enumerate(sim.dispensers):
                self.assertEqual(disp.dispenser_id, i + 1)
                self.assertEqual(disp.status, "IDLE")


class TestResearchBenchmarkDistributions(unittest.TestCase):
    def test_research_benchmark_simulator(self):
        """Verify research benchmark simulator configures Line 1 Beta and Line 2 Triangular models."""
        sim = create_research_benchmark_simulator(seed=42)
        self.assertEqual(sim.num_dispensers, 2)

        d1 = sim.dispensers[0]
        d2 = sim.dispensers[1]

        self.assertEqual(d1.service_distribution, "beta_line1")
        self.assertEqual(d2.service_distribution, "triangular_line2")

        # Sample Line 1 Beta (must be in range [233, 412] seconds)
        rng = sim.rng
        d1_samples = [d1.sample_service_duration(rng) for _ in range(200)]
        self.assertTrue(all(233.0 <= s <= 412.0 for s in d1_samples))
        mean_d1 = sum(d1_samples) / len(d1_samples)
        # Theoretical mean: 233 + 179 * (0.904 / (0.904 + 1.03)) ~ 316.6 seconds (~5.28 min)
        self.assertGreater(mean_d1, 300.0)
        self.assertLess(mean_d1, 335.0)

        # Sample Line 2 Triangular (must be in range [239, 350] seconds)
        d2_samples = [d2.sample_service_duration(rng) for _ in range(200)]
        self.assertTrue(all(239.0 <= s <= 350.0 for s in d2_samples))
        mean_d2 = sum(d2_samples) / len(d2_samples)
        # Theoretical mean: (239 + 295 + 350) / 3 = 294.7 seconds (~4.91 min)
        self.assertGreater(mean_d2, 280.0)
        self.assertLess(mean_d2, 310.0)


class TestLegacyReferenceSimulatorStability(unittest.TestCase):
    def test_legacy_simulator_unaffected(self):
        """Verify legacy single-channel QueueSimulator remains fully intact as reference."""
        legacy = QueueSimulator(initial_queue=5, arrival_rate=0.7, service_rate=0.8)
        self.assertEqual(legacy.queue, 5)
        self.assertEqual(legacy.arrival_rate, 0.7)
        self.assertEqual(legacy.service_rate, 0.8)
        step_res = legacy.step(duration=1)
        self.assertIn("current_queue", step_res)
        self.assertIn("vehicles_served", step_res)


if __name__ == "__main__":
    unittest.main()

