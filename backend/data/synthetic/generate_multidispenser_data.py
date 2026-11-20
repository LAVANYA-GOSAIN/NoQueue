"""
NoQueue — Track A: Multi-Dispenser Synthetic Dataset Generator
=============================================================
Generates a separate, reproducible multi-dispenser synthetic dataset
using the existing MultiDispenserQueueSimulator.

Preserves the existing production system and all previously completed work.
Keeps backend/data/synthetic/noqueue_simulated_data.csv unchanged.

Generates:
1. Periodic State Snapshots: backend/data/synthetic/multidispenser_state_snapshots.csv
2. Vehicle Event Telemetry: backend/data/synthetic/multidispenser_vehicle_events.csv
3. Dataset Metadata & Provenance: backend/data/synthetic/multidispenser_dataset_metadata.json
"""

import os
import csv
import json
import random
import datetime
from typing import Dict, List, Any, Optional

from data.synthetic.queue_simulator import (
    MultiDispenserQueueSimulator,
    create_research_benchmark_simulator,
)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

# Demonstration stations aligned with NoQueue station metadata
STATION_CONFIGS = [
    {
        "station_id": 1,
        "station_name": "Green Fuel CNG Station",
        "num_dispensers": 2,
        "arrival_rate": 0.50,
        "demand_profile": "LOW",
        "cycle_period": 60,
        "phase_offset": 15,
        "balking_threshold": 35,
        "dispenser_configs": [
            {
                "dispenser_id": 1,
                "name": "Line 1 (Beta)",
                "service_distribution": "beta_line1",
                "service_params": {"alpha": 0.904, "beta": 1.03, "loc": 233.0, "scale": 179.0},
            },
            {
                "dispenser_id": 2,
                "name": "Line 2 (Triangular)",
                "service_distribution": "triangular_line2",
                "service_params": {"low": 239.0, "mode": 295.0, "high": 350.0},
            },
        ],
    },
    {
        "station_id": 2,
        "station_name": "City Gas Point",
        "num_dispensers": 2,
        "arrival_rate": 0.65,
        "demand_profile": "MODERATE",
        "cycle_period": 60,
        "phase_offset": 30,
        "balking_threshold": 35,
        "dispenser_configs": [
            {
                "dispenser_id": 1,
                "name": "Line 1 (Beta)",
                "service_distribution": "beta_line1",
                "service_params": {"alpha": 0.904, "beta": 1.03, "loc": 233.0, "scale": 179.0},
            },
            {
                "dispenser_id": 2,
                "name": "Line 2 (Triangular)",
                "service_distribution": "triangular_line2",
                "service_params": {"low": 239.0, "mode": 295.0, "high": 350.0},
            },
        ],
    },
    {
        "station_id": 3,
        "station_name": "Highway CNG Station",
        "num_dispensers": 4,
        "arrival_rate": 1.10,
        "demand_profile": "HEAVY",
        "cycle_period": 60,
        "phase_offset": 45,
        "balking_threshold": 40,
        "dispenser_configs": [
            {
                "dispenser_id": 1,
                "name": "Bay 1 (Beta)",
                "service_distribution": "beta_line1",
                "service_params": {"alpha": 0.904, "beta": 1.03, "loc": 233.0, "scale": 179.0},
            },
            {
                "dispenser_id": 2,
                "name": "Bay 2 (Triangular)",
                "service_distribution": "triangular_line2",
                "service_params": {"low": 239.0, "mode": 295.0, "high": 350.0},
            },
            {
                "dispenser_id": 3,
                "name": "Bay 3 (High-Capacity Tri)",
                "service_distribution": "triangular_generic",
                "service_params": {"low": 210.0, "mode": 270.0, "high": 330.0},
            },
            {
                "dispenser_id": 4,
                "name": "Bay 4 (Commercial Tri)",
                "service_distribution": "triangular_generic",
                "service_params": {"low": 240.0, "mode": 300.0, "high": 360.0},
            },
        ],
    },
    {
        "station_id": 4,
        "station_name": "EcoFill CNG Hub",
        "num_dispensers": 2,
        "arrival_rate": 0.70,
        "demand_profile": "MODERATE",
        "cycle_period": 60,
        "phase_offset": 0,
        "balking_threshold": 35,
        "dispenser_configs": [
            {
                "dispenser_id": 1,
                "name": "Dispenser 1 (Beta)",
                "service_distribution": "beta_line1",
                "service_params": {"alpha": 0.904, "beta": 1.03, "loc": 233.0, "scale": 179.0},
            },
            {
                "dispenser_id": 2,
                "name": "Dispenser 2 (Triangular)",
                "service_distribution": "triangular_line2",
                "service_params": {"low": 239.0, "mode": 295.0, "high": 350.0},
            },
        ],
    },
]


class MultiDispenserDatasetGenerator:
    """
    Simulates multi-dispenser stations and records both periodic state snapshots
    and granular vehicle event lifecycles with exact timestamps.
    """

    def __init__(
        self,
        master_seed: int = 42,
        duration_minutes_per_station: int = 240,
        base_datetime_iso: str = "2026-11-15T08:00:00Z",
    ):
        self.master_seed = master_seed
        self.duration_minutes = duration_minutes_per_station
        self.base_datetime = datetime.datetime.fromisoformat(base_datetime_iso.replace("Z", "+00:00"))
        self.rng = random.Random(master_seed)

    def generate_station_dataset(self, station_cfg: Dict[str, Any], station_seed: int) -> Dict[str, Any]:
        """
        Runs the simulation for a single station and collects:
        - periodic state snapshots
        - event telemetry records
        """
        s_id = station_cfg["station_id"]
        s_name = station_cfg["station_name"]
        num_disp = station_cfg["num_dispensers"]

        sim = MultiDispenserQueueSimulator(
            num_dispensers=num_disp,
            arrival_rate=station_cfg["arrival_rate"],
            dispenser_configs=station_cfg["dispenser_configs"],
            demand_profile=station_cfg["demand_profile"],
            cycle_period=station_cfg["cycle_period"],
            phase_offset=station_cfg["phase_offset"],
            balking_threshold=station_cfg["balking_threshold"],
            seed=station_seed,
        )

        snapshots: List[Dict[str, Any]] = []
        vehicles: Dict[int, Dict[str, Any]] = {}
        dispenser_waiting_lines: Dict[int, List[int]] = {d.dispenser_id: [] for d in sim.dispensers}
        dispenser_active_veh: Dict[int, Optional[int]] = {d.dispenser_id: None for d in sim.dispensers}

        global_event_counter = 0

        for step_idx in range(1, self.duration_minutes + 1):
            step_start_seconds = (step_idx - 1) * 60.0
            step_end_seconds = step_idx * 60.0
            step_start_dt = self.base_datetime + datetime.timedelta(seconds=step_start_seconds)
            step_end_dt = self.base_datetime + datetime.timedelta(seconds=step_end_seconds)

            # 1. Advance simulator by one step
            step_result = sim.step(duration_minutes=1.0)

            # 2. Process service completions from step_dispensers
            for d_id, d_data in step_result["dispensers"].items():
                for comp in d_data["completed_vehicles"]:
                    v_id = comp["id"]
                    surplus = float(comp.get("completion_surplus_seconds", 0.0))
                    t_comp = round(step_end_seconds - surplus, 2)
                    t_comp_iso = (self.base_datetime + datetime.timedelta(seconds=t_comp)).isoformat()

                    if v_id in vehicles:
                        veh_rec = vehicles[v_id]
                        veh_rec["service_completion_time_seconds"] = t_comp
                        veh_rec["service_completion_time_iso"] = t_comp_iso
                        veh_rec["final_status"] = "COMPLETED"

                        # Service duration
                        s_start = veh_rec.get("service_start_time_seconds")
                        if s_start is not None:
                            veh_rec["actual_service_duration_seconds"] = round(t_comp - s_start, 2)
                            veh_rec["actual_service_duration_minutes"] = round((t_comp - s_start) / 60.0, 3)
                            w_dur = veh_rec.get("actual_waiting_duration_seconds", 0.0)
                            veh_rec["actual_total_system_time_seconds"] = round(w_dur + (t_comp - s_start), 2)

                    # When the active vehicle finished, the next waiting vehicle on this dispenser began service
                    if dispenser_waiting_lines[d_id]:
                        next_vid = dispenser_waiting_lines[d_id].pop(0)
                        dispenser_active_veh[d_id] = next_vid
                        next_rec = vehicles[next_vid]
                        next_rec["service_start_time_seconds"] = t_comp
                        next_rec["service_start_time_iso"] = t_comp_iso
                        next_rec["actual_waiting_duration_seconds"] = round(t_comp - next_rec["arrival_time_seconds"], 2)
                        next_rec["actual_waiting_duration_minutes"] = round((t_comp - next_rec["arrival_time_seconds"]) / 60.0, 3)
                        next_rec["final_status"] = "IN_SERVICE"
                    else:
                        dispenser_active_veh[d_id] = None

            # 3. Process new vehicle arrivals and assignments in this step
            # Retrieve arriving vehicles directly from assignments and dispenser queues
            for asgn in step_result["assignments"]:
                v_id = asgn["vehicle_id"]
                d_id = asgn["dispenser_id"]
                asgn_status = asgn["assigned_status"]

                # Find the vehicle's exact arrival offset
                target_disp = next(d for d in sim.dispensers if d.dispenser_id == d_id)
                veh_dict = None
                if target_disp.active_vehicle and target_disp.active_vehicle.get("id") == v_id:
                    veh_dict = target_disp.active_vehicle
                else:
                    for w in target_disp.waiting_queue:
                        if w.get("id") == v_id:
                            veh_dict = w
                            break

                offset = float(veh_dict.get("arrival_offset_seconds", 30.0)) if veh_dict else 30.0
                t_arr = round(step_start_seconds + offset, 2)
                t_arr_iso = (self.base_datetime + datetime.timedelta(seconds=t_arr)).isoformat()

                global_event_counter += 1
                veh_record = {
                    "event_id": f"EVT-S{s_id}-{v_id:05d}",
                    "vehicle_id": v_id,
                    "station_id": s_id,
                    "station_name": s_name,
                    "arrival_step": step_idx,
                    "arrival_time_seconds": t_arr,
                    "arrival_time_iso": t_arr_iso,
                    "arrival_status": "ACCEPTED",
                    "assigned_dispenser_id": d_id,
                    "assigned_dispenser_name": asgn["dispenser_name"],
                    "assigned_status": asgn_status,
                    "line_length_at_assignment": asgn["dispenser_total_after"],
                    "service_start_time_seconds": None,
                    "service_start_time_iso": None,
                    "service_completion_time_seconds": None,
                    "service_completion_time_iso": None,
                    "actual_waiting_duration_seconds": None,
                    "actual_waiting_duration_minutes": None,
                    "actual_service_duration_seconds": None,
                    "actual_service_duration_minutes": None,
                    "actual_total_system_time_seconds": None,
                    "final_status": "WAITING",
                    "is_synthetic": True,
                    "provenance": "NoQueue_MultiDispenserQueueSimulator_TrackA",
                    "random_seed": station_seed,
                }

                if asgn_status == "ACTIVE":
                    # Dispenser was idle: service starts immediately
                    veh_record["service_start_time_seconds"] = t_arr
                    veh_record["service_start_time_iso"] = t_arr_iso
                    veh_record["actual_waiting_duration_seconds"] = 0.0
                    veh_record["actual_waiting_duration_minutes"] = 0.0
                    veh_record["final_status"] = "IN_SERVICE"
                    dispenser_active_veh[d_id] = v_id
                else:
                    # Vehicle joined waiting queue behind active vehicle
                    dispenser_waiting_lines[d_id].append(v_id)

                vehicles[v_id] = veh_record

            # 4. Record periodic state snapshot at end of this minute
            disp_active = [1 if d.is_busy else 0 for d in sim.dispensers]
            disp_waiting = [d.waiting_count for d in sim.dispensers]
            disp_remaining = [round(d.remaining_service_time, 1) for d in sim.dispensers]

            snapshot = {
                "snapshot_id": f"SNAP-S{s_id}-{step_idx:04d}",
                "timestamp_iso": step_end_dt.isoformat(),
                "simulation_time_seconds": round(step_end_seconds, 1),
                "simulation_time_minutes": step_idx,
                "step_index": step_idx,
                "station_id": s_id,
                "station_name": s_name,
                "num_dispensers": num_disp,
                "demand_profile": station_cfg["demand_profile"],
                "nominal_arrival_rate_per_min": step_result["nominal_arrival_rate"],
                "effective_arrival_rate_per_min": step_result["effective_arrival_rate"],
                "total_vehicles": step_result["total_vehicles"],
                "waiting_queue_length": step_result["waiting_queue_length"],
                "vehicles_being_served": step_result["vehicles_being_served"],
                "dispenser_active_counts": json.dumps(disp_active),
                "dispenser_waiting_counts": json.dumps(disp_waiting),
                "dispenser_remaining_service_seconds": json.dumps(disp_remaining),
                "potential_arrivals_in_step": step_result["potential_arrivals"],
                "accepted_arrivals_in_step": step_result["accepted_arrivals"],
                "balked_arrivals_in_step": step_result["balked_arrivals"],
                "vehicles_served_in_step": step_result["vehicles_served"],
                "estimated_incoming_wait_minutes": step_result["estimated_waiting_time_minutes"],
                "congestion_level": sim.get_congestion_level(),
                "crowd_level": sim.get_crowd_level(),
                "is_synthetic": True,
                "provenance": "NoQueue_MultiDispenserQueueSimulator_TrackA",
                "random_seed": station_seed,
            }
            snapshots.append(snapshot)

        # Sort vehicle events by arrival timestamp
        event_list = sorted(vehicles.values(), key=lambda v: (v["arrival_time_seconds"], v["vehicle_id"]))
        return {
            "station_id": s_id,
            "station_name": s_name,
            "snapshots": snapshots,
            "events": event_list,
        }

    def generate_full_dataset(self) -> Dict[str, Any]:
        """
        Simulates all configured demonstration stations and aggregates datasets.
        """
        all_snapshots: List[Dict[str, Any]] = []
        all_events: List[Dict[str, Any]] = []

        station_summaries = []

        for st_cfg in STATION_CONFIGS:
            st_seed = self.rng.randint(1000, 999999)
            res = self.generate_station_dataset(st_cfg, station_seed=st_seed)
            all_snapshots.extend(res["snapshots"])
            all_events.extend(res["events"])

            comp_count = sum(1 for e in res["events"] if e["final_status"] == "COMPLETED")
            in_serv_count = sum(1 for e in res["events"] if e["final_status"] == "IN_SERVICE")
            wait_count = sum(1 for e in res["events"] if e["final_status"] == "WAITING")

            station_summaries.append({
                "station_id": st_cfg["station_id"],
                "station_name": st_cfg["station_name"],
                "num_dispensers": st_cfg["num_dispensers"],
                "demand_profile": st_cfg["demand_profile"],
                "arrival_rate": st_cfg["arrival_rate"],
                "random_seed": st_seed,
                "snapshot_count": len(res["snapshots"]),
                "total_vehicles_arrived": len(res["events"]),
                "completed_vehicles": comp_count,
                "in_service_vehicles": in_serv_count,
                "waiting_vehicles": wait_count,
            })

        return {
            "metadata": {
                "dataset_name": "NoQueue Multi-Dispenser Synthetic Dataset (Track A)",
                "version": "1.0.0",
                "creation_timestamp_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "master_seed": self.master_seed,
                "duration_minutes_per_station": self.duration_minutes,
                "total_stations": len(STATION_CONFIGS),
                "total_snapshots": len(all_snapshots),
                "total_vehicle_events": len(all_events),
                "provenance": "Generated via MultiDispenserQueueSimulator (Join-Shortest-Queue, independent physical dispenser channels, 2025 CNG Arena case-study distributions)",
                "data_type": "SYNTHETIC",
                "real_world_validation_status": "NOT AVAILABLE — INDEPENDENT OBSERVATIONS REQUIRED",
                "station_summaries": station_summaries,
            },
            "snapshots": all_snapshots,
            "events": all_events,
        }


def save_multidispenser_dataset(output_dir: Optional[str] = None, master_seed: int = 42) -> Dict[str, str]:
    """
    Generates and saves:
    1. multidispenser_state_snapshots.csv
    2. multidispenser_vehicle_events.csv
    3. multidispenser_dataset_metadata.json
    """
    target_dir = output_dir or CURRENT_DIR
    os.makedirs(target_dir, exist_ok=True)

    generator = MultiDispenserDatasetGenerator(master_seed=master_seed, duration_minutes_per_station=240)
    dataset = generator.generate_full_dataset()

    snapshots_path = os.path.join(target_dir, "multidispenser_state_snapshots.csv")
    events_path = os.path.join(target_dir, "multidispenser_vehicle_events.csv")
    metadata_path = os.path.join(target_dir, "multidispenser_dataset_metadata.json")

    # 1. Save Snapshots CSV
    snapshots = dataset["snapshots"]
    if snapshots:
        fieldnames = list(snapshots[0].keys())
        with open(snapshots_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(snapshots)

    # 2. Save Vehicle Events CSV
    events = dataset["events"]
    if events:
        fieldnames = list(events[0].keys())
        with open(events_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(events)

    # 3. Save Metadata JSON
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(dataset["metadata"], f, indent=2)

    print("=" * 78)
    print("NoQueue — Track A Multi-Dispenser Synthetic Dataset Generated Successfully!")
    print("=" * 78)
    print(f"Master Seed: {master_seed}")
    print(f"Total State Snapshots: {len(snapshots):,}")
    print(f"Total Vehicle Events:  {len(events):,}")
    print(f"Snapshots CSV:         {snapshots_path}")
    print(f"Events CSV:            {events_path}")
    print(f"Metadata JSON:         {metadata_path}")
    print("=" * 78)

    return {
        "snapshots_path": snapshots_path,
        "events_path": events_path,
        "metadata_path": metadata_path,
    }


if __name__ == "__main__":
    save_multidispenser_dataset()

