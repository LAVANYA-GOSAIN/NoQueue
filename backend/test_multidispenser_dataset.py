"""
Unit and integration tests for NoQueue Track A: Multi-Dispenser Synthetic Dataset.
Verifies all Track A requirements and invariants:
1. Output files exist and are populated.
2. Total occupancy invariant: total_vehicles == waiting_queue_length + vehicles_being_served.
3. Dispenser active capacity invariant: active_count <= 1 for every dispenser.
4. Exactly one dispenser assignment per accepted arrival.
5. Service completion corresponds to a valid service start (completion >= start >= arrival).
6. Waiting duration is calculated from recorded timestamps (start - arrival).
7. Idle arrivals have waiting_duration == 0.0.
8. Queued arrivals have waiting_duration > 0.0 upon starting service.
9. Deterministic reproducibility across repeated runs with fixed master seed.
10. Preservation of original noqueue_simulated_data.csv.
"""

import os
import csv
import json
import unittest

from data.synthetic.generate_multidispenser_data import (
    MultiDispenserDatasetGenerator,
    save_multidispenser_dataset,
    CURRENT_DIR,
)

SNAPSHOTS_PATH = os.path.join(CURRENT_DIR, "multidispenser_state_snapshots.csv")
EVENTS_PATH = os.path.join(CURRENT_DIR, "multidispenser_vehicle_events.csv")
METADATA_PATH = os.path.join(CURRENT_DIR, "multidispenser_dataset_metadata.json")
LEGACY_CSV_PATH = os.path.join(CURRENT_DIR, "noqueue_simulated_data.csv")


class TestMultiDispenserDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure fresh generation if needed
        if not (os.path.exists(SNAPSHOTS_PATH) and os.path.exists(EVENTS_PATH) and os.path.exists(METADATA_PATH)):
            save_multidispenser_dataset(master_seed=42)

    def test_output_files_exist_and_non_empty(self):
        """Verify that all three dataset artifacts exist and have non-trivial size."""
        self.assertTrue(os.path.exists(SNAPSHOTS_PATH), "Snapshots CSV does not exist")
        self.assertTrue(os.path.exists(EVENTS_PATH), "Vehicle events CSV does not exist")
        self.assertTrue(os.path.exists(METADATA_PATH), "Metadata JSON does not exist")

        self.assertGreater(os.path.getsize(SNAPSHOTS_PATH), 50000, "Snapshots CSV is too small")
        self.assertGreater(os.path.getsize(EVENTS_PATH), 50000, "Events CSV is too small")
        self.assertGreater(os.path.getsize(METADATA_PATH), 500, "Metadata JSON is too small")

    def test_total_occupancy_invariant(self):
        """
        Validation: Total occupancy = waiting vehicles + active vehicles.
        Must hold for every snapshot row in the dataset.
        """
        with open(SNAPSHOTS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                count += 1
                total_q = int(row["total_vehicles"])
                wait_q = int(row["waiting_queue_length"])
                active_q = int(row["vehicles_being_served"])
                self.assertEqual(
                    total_q,
                    wait_q + active_q,
                    f"Invariant violated at snapshot {row['snapshot_id']}: {total_q} != {wait_q} + {active_q}",
                )

                # Check dispenser array consistency
                disp_active = json.loads(row["dispenser_active_counts"])
                disp_waiting = json.loads(row["dispenser_waiting_counts"])
                self.assertEqual(sum(disp_active), active_q)
                self.assertEqual(sum(disp_waiting), wait_q)

            self.assertEqual(count, 960, "Expected 960 state snapshots (4 stations x 240 minutes)")

    def test_single_active_vehicle_per_dispenser(self):
        """
        Validation: Each dispenser has at most one active vehicle.
        Must hold across all dispensers in every snapshot.
        """
        with open(SNAPSHOTS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                disp_active = json.loads(row["dispenser_active_counts"])
                for idx, active in enumerate(disp_active):
                    self.assertIn(
                        active,
                        [0, 1],
                        f"Dispenser {idx} at snapshot {row['snapshot_id']} has invalid active count {active}",
                    )

    def test_accepted_arrivals_have_exactly_one_dispenser_assignment(self):
        """
        Validation: Every accepted arrival has exactly one dispenser assignment.
        """
        with open(EVENTS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                count += 1
                self.assertEqual(row["arrival_status"], "ACCEPTED")
                disp_id = row["assigned_dispenser_id"]
                self.assertTrue(disp_id.isdigit(), f"Vehicle {row['event_id']} lacks valid dispenser assignment")
                self.assertIn(int(disp_id), [1, 2, 3, 4])
                self.assertIn(row["assigned_status"], ["ACTIVE", "QUEUED"])

            self.assertGreaterEqual(count, 450, "Expected at least 450 vehicle event records")

    def test_service_completion_corresponds_to_valid_service_start(self):
        """
        Validation: Service completion must correspond to a valid service start
        (completion >= start >= arrival).
        """
        with open(EVENTS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            completed_count = 0
            for row in reader:
                if row["final_status"] == "COMPLETED":
                    completed_count += 1
                    t_arr = float(row["arrival_time_seconds"])
                    t_start = float(row["service_start_time_seconds"])
                    t_end = float(row["service_completion_time_seconds"])

                    self.assertGreaterEqual(
                        t_start,
                        t_arr,
                        f"Vehicle {row['event_id']}: service start {t_start} < arrival {t_arr}",
                    )
                    self.assertGreater(
                        t_end,
                        t_start,
                        f"Vehicle {row['event_id']}: service end {t_end} <= start {t_start}",
                    )

            self.assertGreater(completed_count, 350, "Expected at least 350 completed vehicles")

    def test_waiting_duration_calculated_from_recorded_timestamps(self):
        """
        Validation: Waiting duration must be calculated from recorded arrival
        and service-start timestamps (start - arrival).
        - If assigned to idle dispenser (ACTIVE), wait == 0.0.
        - If queued behind vehicles and started, wait > 0.0.
        """
        with open(EVENTS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                t_arr = float(row["arrival_time_seconds"])
                s_start = row["service_start_time_seconds"]

                if s_start:
                    t_start = float(s_start)
                    expected_wait = round(t_start - t_arr, 2)
                    recorded_wait = float(row["actual_waiting_duration_seconds"])
                    self.assertAlmostEqual(
                        recorded_wait,
                        expected_wait,
                        places=2,
                        msg=f"Vehicle {row['event_id']} waiting duration mismatch",
                    )

                    if row["assigned_status"] == "ACTIVE":
                        self.assertEqual(recorded_wait, 0.0)
                        self.assertEqual(t_start, t_arr)
                    elif row["assigned_status"] == "QUEUED":
                        self.assertGreater(recorded_wait, 0.0)

    def test_service_duration_calculated_from_recorded_timestamps(self):
        """
        Validation: Service duration must be calculated from recorded
        service-completion and service-start timestamps (completion - start).
        """
        with open(EVENTS_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["final_status"] == "COMPLETED":
                    t_start = float(row["service_start_time_seconds"])
                    t_end = float(row["service_completion_time_seconds"])
                    expected_serv = round(t_end - t_start, 2)
                    recorded_serv = float(row["actual_service_duration_seconds"])
                    self.assertAlmostEqual(
                        recorded_serv,
                        expected_serv,
                        places=2,
                        msg=f"Vehicle {row['event_id']} service duration mismatch",
                    )
                    self.assertGreater(recorded_serv, 0.0)

    def test_reproducibility_via_fixed_seed(self):
        """Verify that two independent generations with seed=42 yield identical outputs."""
        gen1 = MultiDispenserDatasetGenerator(master_seed=42, duration_minutes_per_station=60)
        data1 = gen1.generate_full_dataset()

        gen2 = MultiDispenserDatasetGenerator(master_seed=42, duration_minutes_per_station=60)
        data2 = gen2.generate_full_dataset()

        self.assertEqual(len(data1["snapshots"]), len(data2["snapshots"]))
        self.assertEqual(len(data1["events"]), len(data2["events"]))

        # Check exact snapshot match
        for s1, s2 in zip(data1["snapshots"], data2["snapshots"]):
            self.assertEqual(s1["total_vehicles"], s2["total_vehicles"])
            self.assertEqual(s1["waiting_queue_length"], s2["waiting_queue_length"])
            self.assertEqual(s1["vehicles_being_served"], s2["vehicles_being_served"])

        # Check exact event match
        for e1, e2 in zip(data1["events"], data2["events"]):
            self.assertEqual(e1["vehicle_id"], e2["vehicle_id"])
            self.assertEqual(e1["arrival_time_seconds"], e2["arrival_time_seconds"])
            self.assertEqual(e1["assigned_dispenser_id"], e2["assigned_dispenser_id"])
            self.assertEqual(e1["actual_waiting_duration_seconds"], e2["actual_waiting_duration_seconds"])

    def test_original_csv_remains_intact(self):
        """CRITICAL: Verify backend/data/synthetic/noqueue_simulated_data.csv is unchanged."""
        self.assertTrue(os.path.exists(LEGACY_CSV_PATH))
        with open(LEGACY_CSV_PATH, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 1000, "Original CSV record count altered!")
            # Check first row
            self.assertEqual(reader[0]["station_name"], "Green Fuel CNG Station")
            self.assertEqual(reader[0]["vehicles_in_queue"], "4")


if __name__ == "__main__":
    unittest.main()

