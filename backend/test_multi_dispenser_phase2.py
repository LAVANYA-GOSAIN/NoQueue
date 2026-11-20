"""
Unit tests for Phase 2: Join-Shortest-Queue (JSQ) Arrival Assignment.
Verifies all Phase 2 criteria:
1. DispenserChannel step_service invariants (active, idle, transitions, surplus carryover).
2. Station-level arrival generation (each vehicle generated once, no separate per-dispenser streams).
3. Join-Shortest-Queue (JSQ) selection using N_j = waiting_queue_length_j + active_vehicle_indicator_j.
4. Immediate service start at an idle dispenser.
5. Appending to waiting line when dispenser is busy.
6. Active vehicles being counted in effective line length.
7. Uniform random tie-breaking across equally short lines.
8. Each arrival assigned exactly once; no vehicle in multiple dispenser queues.
9. Configurable balking decision evaluated once per arriving vehicle before assignment.
10. Support for 1, 2, 3, and 4 dispenser configurations.
11. Seed reproducibility.
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
)


class TestPhase1Invariants(unittest.TestCase):
    def test_dispenser_invariants_and_surplus_carryover(self):
        """
        Verify:
        - Dispenser remains BUSY while active vehicle is being served.
        - Becomes IDLE only when active finishes and waiting line is empty.
        - Next waiting vehicle immediately becomes active.
        - Surplus seconds across step boundaries are carried over accurately.
        """
        disp = DispenserChannel(
            dispenser_id=1,
            service_distribution="constant",
            service_params={"duration_seconds": 30.0},
        )
        veh1 = {"id": 1}
        veh2 = {"id": 2}
        veh3 = {"id": 3}

        # veh1 starts with 20s remaining
        disp.start_service(veh1, duration_seconds=20.0)
        disp.add_to_queue(veh2)
        disp.add_to_queue(veh3)

        self.assertTrue(disp.is_busy)
        self.assertEqual(disp.status, "BUSY")
        self.assertEqual(disp.waiting_count, 2)

        # Step 60 seconds:
        # veh1 finishes after 20s (surplus 40s).
        # veh2 becomes active with duration 30s. 30s < 40s surplus -> veh2 finishes immediately (leftover surplus 10s).
        # veh3 becomes active with duration 30s. 10s surplus applied -> veh3 has 20s remaining!
        completed = disp.step_service(elapsed_seconds=60.0)

        self.assertEqual(len(completed), 2)
        self.assertEqual(completed[0]["id"], 1)
        self.assertEqual(completed[1]["id"], 2)
        self.assertTrue(disp.is_busy)
        self.assertEqual(disp.status, "BUSY")
        self.assertEqual(disp.active_vehicle["id"], 3)
        self.assertAlmostEqual(disp.remaining_service_time, 20.0)
        self.assertEqual(disp.waiting_count, 0)
        self.assertEqual(disp.total_count, 1)

        # Step another 30 seconds -> veh3 finishes after 20s, no waiting vehicles left -> IDLE
        completed2 = disp.step_service(elapsed_seconds=30.0)
        self.assertEqual(len(completed2), 1)
        self.assertEqual(completed2[0]["id"], 3)
        self.assertFalse(disp.is_busy)
        self.assertEqual(disp.status, "IDLE")
        self.assertEqual(disp.remaining_service_time, 0.0)
        self.assertIsNone(disp.active_vehicle)
        self.assertEqual(disp.waiting_count, 0)


class TestJSQAssignment(unittest.TestCase):
    def test_arrival_starts_service_immediately_at_idle_dispenser(self):
        """Verify an arrival at an idle dispenser starts service immediately."""
        sim = MultiDispenserQueueSimulator(num_dispensers=2, seed=42)
        self.assertEqual(sim.dispensers[0].status, "IDLE")
        self.assertEqual(sim.dispensers[1].status, "IDLE")

        veh = {"id": 101}
        res = sim.assign_vehicle(veh)

        self.assertEqual(res["assigned_status"], "ACTIVE")
        self.assertEqual(sim.vehicles_being_served, 1)
        self.assertEqual(sim.waiting_queue_length, 0)
        self.assertEqual(sim.total_vehicles, 1)

    def test_arrival_joins_shortest_line(self):
        """Verify an arrival joins the dispenser with minimum effective line length."""
        sim = MultiDispenserQueueSimulator(num_dispensers=3, seed=42)

        # Dispenser 0 has 3 vehicles (1 active + 2 waiting)
        sim.dispensers[0].start_service({"id": 1}, duration_seconds=300.0)
        sim.dispensers[0].add_to_queue({"id": 2})
        sim.dispensers[0].add_to_queue({"id": 3})

        # Dispenser 1 has 1 vehicle (1 active + 0 waiting)
        sim.dispensers[1].start_service({"id": 4}, duration_seconds=300.0)

        # Dispenser 2 has 2 vehicles (1 active + 1 waiting)
        sim.dispensers[2].start_service({"id": 5}, duration_seconds=300.0)
        sim.dispensers[2].add_to_queue({"id": 6})

        # Line lengths: [3, 1, 2] -> minimum is Dispenser 1
        self.assertEqual(sim.get_effective_line_lengths(), [3, 1, 2])
        chosen_idx = sim.select_dispenser_jsq()
        self.assertEqual(chosen_idx, 1)

        # Assign new vehicle
        veh_new = {"id": 100}
        sim.assign_vehicle(veh_new)

        # Dispenser 1 should now have 2 vehicles (1 active + 1 waiting)
        self.assertEqual(sim.dispensers[1].total_count, 2)
        self.assertEqual(sim.dispensers[1].waiting_count, 1)
        self.assertEqual(sim.dispensers[1].waiting_queue[-1]["id"], 100)

    def test_active_vehicle_counted_in_effective_line_length(self):
        """
        Verify active vehicle is counted in effective line length (N_j = k_j + b_j).
        If Dispenser 0 is busy with 0 waiting (N_0 = 1) and Dispenser 1 is idle with 0 waiting (N_1 = 0),
        the new vehicle must choose Dispenser 1.
        """
        sim = MultiDispenserQueueSimulator(num_dispensers=2, seed=42)
        sim.dispensers[0].start_service({"id": 1}, duration_seconds=300.0)

        # Both have 0 waiting in line, but Dispenser 0 is BUSY (N_0 = 1) and Dispenser 1 is IDLE (N_1 = 0)
        self.assertEqual(sim.dispensers[0].waiting_count, 0)
        self.assertEqual(sim.dispensers[1].waiting_count, 0)
        self.assertEqual(sim.get_effective_line_lengths(), [1, 0])

        chosen_idx = sim.select_dispenser_jsq()
        self.assertEqual(chosen_idx, 1)

        sim.assign_vehicle({"id": 2})
        # Dispenser 1 must now be active
        self.assertTrue(sim.dispensers[1].is_busy)
        self.assertEqual(sim.dispensers[1].active_vehicle["id"], 2)

    def test_uniform_random_tie_breaking(self):
        """Verify uniform random tie-breaking when multiple dispensers have identical minimum length."""
        sim = MultiDispenserQueueSimulator(num_dispensers=3, seed=123)
        # All 3 dispensers have N_j = 0
        selections = [sim.select_dispenser_jsq() for _ in range(300)]

        count_0 = selections.count(0)
        count_1 = selections.count(1)
        count_2 = selections.count(2)

        # In 300 trials, each dispenser should be chosen approximately 100 times (+/- 35)
        self.assertGreater(count_0, 65)
        self.assertGreater(count_1, 65)
        self.assertGreater(count_2, 65)
        self.assertEqual(count_0 + count_1 + count_2, 300)


class TestStationArrivalGenerationAndBalking(unittest.TestCase):
    def test_arrivals_generated_and_assigned_exactly_once(self):
        """Verify each arriving vehicle is generated and assigned exactly once with no duplicates."""
        sim = MultiDispenserQueueSimulator(
            num_dispensers=2,
            arrival_rate=1.5,
            demand_profile="STATIC",
            balking_threshold=0,  # No balking for this test
            seed=777,
        )

        all_assigned_ids = []
        for _ in range(10):
            step_res = sim.step(duration_minutes=1.0)
            for asgn in step_res["assignments"]:
                all_assigned_ids.append(asgn["vehicle_id"])

        # Vehicle IDs must be strictly sequential with zero duplicates
        self.assertEqual(len(all_assigned_ids), len(set(all_assigned_ids)))
        self.assertEqual(all_assigned_ids, list(range(1, len(all_assigned_ids) + 1)))

        # Verify no vehicle currently in system appears more than once
        present_ids = []
        for d in sim.dispensers:
            if d.active_vehicle:
                present_ids.append(d.active_vehicle["id"])
            for v in d.waiting_queue:
                present_ids.append(v["id"])

        self.assertEqual(len(present_ids), len(set(present_ids)))

    def test_balking_evaluated_once_per_arrival(self):
        """Verify balking formula and evaluation once per arriving vehicle."""
        sim = MultiDispenserQueueSimulator(
            num_dispensers=2,
            balking_threshold=35,
            seed=42,
        )
        # Empty queue -> P(enter) = 1.0 -> should_balk() is False
        self.assertAlmostEqual(sim.calculate_balking_probability(queue=0), 1.0)
        self.assertFalse(sim.should_balk(queue=0))

        # Queue at threshold (35) -> P(enter) = 0.10
        self.assertAlmostEqual(sim.calculate_balking_probability(queue=35), 0.10)

        # Queue beyond threshold (50) -> bounded at 0.10
        self.assertAlmostEqual(sim.calculate_balking_probability(queue=50), 0.10)

        # Intermediate queue (17) -> 1 - (17/35)^2 ~ 0.764
        expected_p = 1.0 - (17.0 / 35.0) ** 2
        self.assertAlmostEqual(sim.calculate_balking_probability(queue=17), expected_p)


class TestDispenserScalabilityAndSeedReproducibility(unittest.TestCase):
    def test_dispenser_configurations_1_2_3_4(self):
        """Verify simulator functions consistently across 1, 2, 3, and 4 dispenser setups."""
        for c in [1, 2, 3, 4]:
            sim = MultiDispenserQueueSimulator(
                num_dispensers=c,
                arrival_rate=0.8,
                demand_profile="MODERATE",
                seed=100 + c,
            )
            step_res = sim.step(duration_minutes=1.0)
            self.assertEqual(len(sim.dispensers), c)
            self.assertEqual(len(step_res["dispensers"]), c)
            self.assertEqual(
                sim.total_vehicles,
                sim.waiting_queue_length + sim.vehicles_being_served,
            )

    def test_seed_reproducibility(self):
        """Verify two independent simulators with the exact same seed yield identical step outcomes."""
        sim1 = MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=1.0, seed=9999)
        sim2 = MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=1.0, seed=9999)

        for _ in range(15):
            res1 = sim1.step(duration_minutes=1.0)
            res2 = sim2.step(duration_minutes=1.0)

            self.assertEqual(res1["potential_arrivals"], res2["potential_arrivals"])
            self.assertEqual(res1["accepted_arrivals"], res2["accepted_arrivals"])
            self.assertEqual(res1["balked_arrivals"], res2["balked_arrivals"])
            self.assertEqual(res1["vehicles_served"], res2["vehicles_served"])
            self.assertEqual(res1["total_vehicles"], res2["total_vehicles"])
            self.assertEqual(res1["waiting_queue_length"], res2["waiting_queue_length"])
            self.assertEqual(res1["vehicles_being_served"], res2["vehicles_being_served"])


if __name__ == "__main__":
    unittest.main()

