
import random
import math
import csv
import os
import copy
from typing import List, Dict, Any, Optional, Tuple


class QueueSimulator:
    def __init__(
        self,
        initial_queue: int,
        arrival_rate: float,
        service_rate: float,
        demand_profile: str = "STATIC",
        cycle_period: int = 60,
        phase_offset: int = 0,
        balking_threshold: int = 35,
    ):
        self.queue = max(0, initial_queue)
        self.arrival_rate = arrival_rate
        self.service_rate = service_rate
        self.demand_profile = (demand_profile or "STATIC").upper()
        self.cycle_period = cycle_period
        self.phase_offset = phase_offset
        self.balking_threshold = balking_threshold
        self.step_count = 0

    def get_effective_arrival_rate(self, step_idx: int = None, queue: int = None) -> float:
        """
        Calculates effective arrival rate taking into account:
        1. Cyclical demand modulation over simulated time (LOW, MODERATE, HEAVY).
        2. Customer balking as queue approaches roadway threshold.
        """
        if self.arrival_rate <= 0:
            return 0.0

        if self.demand_profile in ("STATIC", "NONE", "") or self.cycle_period <= 0:
            nominal_rate = self.arrival_rate
        else:
            t = self.step_count if step_idx is None else step_idx
            theta = 2.0 * math.pi * ((t + self.phase_offset) % self.cycle_period) / self.cycle_period

            if self.demand_profile == "HEAVY":
                # Peak demand surge: multiplier reaches 1.45x, trough drops to 0.65x
                mult = 1.05 + 0.40 * math.sin(theta)
            elif self.demand_profile == "MODERATE":
                # Moderate normal demand: multiplier reaches 1.15x, trough drops to 0.70x
                mult = 0.90 + 0.25 * math.sin(theta)
            elif self.demand_profile == "LOW":
                # Low off-peak demand: multiplier reaches 0.80x, trough drops to 0.50x
                mult = 0.65 + 0.15 * math.sin(theta)
            else:
                mult = 1.0

            nominal_rate = max(0.05, self.arrival_rate * mult)

        # Balking queue model: as queue approaches balking_threshold, arriving drivers divert
        q = self.queue if queue is None else queue
        if self.balking_threshold > 0 and q > 0:
            if q >= self.balking_threshold:
                balk_factor = 0.10
            else:
                balk_factor = max(0.10, 1.0 - (q / self.balking_threshold) ** 2)
        else:
            balk_factor = 1.0

        return nominal_rate * balk_factor

    def generate_events(self, rate, duration):
        """
        Generate a random number of events
        using an exponential inter-arrival model.
        """
        if rate <= 0:
            return 0

        elapsed_time = 0
        count = 0

        while True:
            elapsed_time += random.expovariate(rate)

            if elapsed_time > duration:
                break

            count += 1

        return count

    def estimate_waiting_time(self):
        if self.queue == 0:
            return 0.0
        if self.service_rate <= 0:
            return float("inf")

        return round(self.queue / self.service_rate, 2)

    def get_crowd_level(self):
        if self.queue <= 5:
            return "LOW"
        elif self.queue <= 12:
            return "MODERATE"
        else:
            return "HIGH"

    def get_congestion_level(self):
        """
        Classifies congestion level based on estimated waiting time in minutes:
        - LOW: 0–10 minutes
        - MEDIUM: above 10 and up to 20 minutes
        - HIGH: above 20 minutes
        """
        wait = self.estimate_waiting_time()
        if wait <= 10.0:
            return "LOW"
        elif wait <= 20.0:
            return "MEDIUM"
        else:
            return "HIGH"

    def step(self, duration=1):
        """
        Simulate one time step.

        Vehicles arrive according to the dynamic effective arrival rate,
        and vehicles are served according to dispenser capacity.
        The queue is then updated.
        """
        effective_arrival = self.get_effective_arrival_rate()

        arrivals = self.generate_events(
            effective_arrival,
            duration
        )

        served = self.generate_events(
            self.service_rate,
            duration
        )

        old_queue = self.queue

        self.queue = max(
            0,
            self.queue + arrivals - served
        )

        self.step_count += 1

        return {
            "previous_queue": old_queue,
            "arrivals": arrivals,
            "vehicles_served": min(served, old_queue + arrivals),
            "current_queue": self.queue,
            "estimated_waiting_time_minutes":
                self.estimate_waiting_time(),
            "crowd_level": self.get_crowd_level(),
            "congestion_level": self.get_congestion_level(),
            "effective_arrival_rate": round(effective_arrival, 2),
            "data_source": "synthetic",
            "is_simulated": True
        }

    def run_simulation(self, steps=10):
        history = []

        for minute in range(1, steps + 1):
            observation = self.step()

            observation["minute"] = minute
            history.append(observation)

        return history

    def forecast(self, horizons=(15, 30, 60), trials=500, seed=None):
        """
        Monte Carlo lookahead simulation for expected queue lengths and waiting times.

        Simulates forward trajectories independently from the station's current state (Q0)
        using an isolated random generator so that the live simulation is neither
        mutated nor advanced.

        Parameters:
            horizons: sequence of lookahead minutes (default: (15, 30, 60))
            trials: number of independent simulation trajectories (default: 500)
            seed: optional random seed for independent RNG (for deterministic testing)

        Returns:
            dict with horizon projections:
            {
                "15m": {"expected_queue": int, "queue_range": [int, int], "expected_wait_minutes": float},
                "30m": {"expected_queue": int, "queue_range": [int, int], "expected_wait_minutes": float},
                "60m": {"expected_queue": int, "queue_range": [int, int], "expected_wait_minutes": float}
            }
        """
        if trials < 1:
            trials = 500

        sorted_horizons = sorted(horizons)
        max_horizon = sorted_horizons[-1] if sorted_horizons else 60

        # Isolated RNG to ensure live simulator sequence is completely untouched
        rng = random.Random(seed)

        # Store queue outcomes at each horizon across all trials
        horizon_queues = {h: [] for h in sorted_horizons}

        # Snapshot of current state (never mutated during forecasting)
        current_q = self.queue
        srv_rate = self.service_rate

        def _gen_events(rate, duration):
            if rate <= 0:
                return 0
            elapsed = 0.0
            count = 0
            while True:
                elapsed += rng.expovariate(rate)
                if elapsed > duration:
                    break
                count += 1
            return count

        for _ in range(trials):
            q = current_q
            for minute in range(1, max_horizon + 1):
                future_step = self.step_count + minute
                future_arr = self.get_effective_arrival_rate(step_idx=future_step, queue=q)

                arrivals = _gen_events(future_arr, 1)
                services = _gen_events(srv_rate, 1)
                q = max(0, q + arrivals - services)
                if minute in horizon_queues:
                    horizon_queues[minute].append(q)

        forecast_result = {}
        for h in sorted_horizons:
            samples = horizon_queues[h]
            if samples:
                samples.sort()
                mean_q = sum(samples) / float(len(samples))
                expected_q = max(0.0, round(mean_q, 1))

                # 10th and 90th percentile bounds
                p10 = int(round(samples[int(0.10 * (len(samples) - 1))]))
                p90 = int(round(samples[int(0.90 * (len(samples) - 1))]))
                queue_range = [p10, p90]

                # Expected waiting time
                if srv_rate > 0:
                    expected_wait = round(mean_q / srv_rate, 1)
                else:
                    expected_wait = 0.0
            else:
                expected_q = float(current_q)
                queue_range = [int(current_q), int(current_q)]
                expected_wait = round(current_q / srv_rate, 1) if srv_rate > 0 else 0.0

            forecast_result[f"{h}m"] = {
                "expected_queue": expected_q,
                "queue_range": queue_range,
                "expected_wait_minutes": expected_wait,
            }

        return forecast_result


# =====================================================================
# Phase 1: Multi-Dispenser State and Independent Service Logic
# =====================================================================

class DispenserChannel:
    """
    Represents an independent physical CNG dispenser (server channel).

    Maintains:
    - Its waiting vehicle queue (strictly excluding the vehicle currently being served).
    - Its currently active vehicle being fueled, if any.
    - Remaining service time in seconds for the active vehicle.
    - Configured service-time distribution (e.g., empirical Beta/Triangular benchmarks or exponential/generic).
    - Service status ('IDLE' or 'BUSY').
    """

    def __init__(
        self,
        dispenser_id: int,
        service_distribution: str = "exponential",
        service_params: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
    ):
        self.dispenser_id = int(dispenser_id)
        self.name = name or f"Dispenser {dispenser_id}"
        self.service_distribution = (service_distribution or "exponential").lower()
        self.service_params = service_params or {}

        # Internal state
        self.waiting_queue: List[Dict[str, Any]] = []
        self.active_vehicle: Optional[Dict[str, Any]] = None
        self.remaining_service_time: float = 0.0  # in seconds
        self.status: str = "IDLE"  # "IDLE" or "BUSY"
        self.total_vehicles_served: int = 0

    @property
    def is_busy(self) -> bool:
        """True if a vehicle is currently occupying the dispenser nozzle."""
        return self.active_vehicle is not None

    @property
    def waiting_count(self) -> int:
        """Count of vehicles strictly waiting in line (excluding the vehicle currently being served)."""
        return len(self.waiting_queue)

    @property
    def active_count(self) -> int:
        """Count of vehicles currently being served at this dispenser (0 or 1)."""
        return 1 if self.is_busy else 0

    @property
    def total_count(self) -> int:
        """Total vehicles assigned to this dispenser (active vehicle + waiting queue)."""
        return self.active_count + self.waiting_count

    def sample_service_duration(self, rng: Optional[random.Random] = None) -> float:
        """
        Samples a service duration in seconds based on the configured distribution.

        Supported distributions:
        - 'beta_line1': 2025 Paper Line 1: 233 + 179 * Beta(0.904, 1.03) seconds (Mean ~316.5s)
        - 'triangular_line2': 2025 Paper Line 2: Triangular(239, 295, 350) seconds (Mean ~294.7s)
        - 'triangular_generic': Configurable Triangular(low, mode, high)
        - 'constant': Fixed duration (useful for deterministic tests)
        - 'exponential': Exponential distribution based on mean_service_seconds
        """
        r = rng if rng is not None else random
        dist = self.service_distribution

        if dist in ("beta_line1", "line1_beta", "research_line1"):
            # Research benchmark Line 1: 233 + 179 * Beta(0.904, 1.03) seconds
            val = 233.0 + 179.0 * r.betavariate(0.904, 1.03)
            return max(15.0, val)

        elif dist in ("triangular_line2", "line2_triangular", "research_line2"):
            # Research benchmark Line 2: Triangular(low=239, mode=295, high=350) seconds
            val = r.triangular(239.0, 350.0, 295.0)
            return max(15.0, val)

        elif dist in ("triangular", "triangular_generic"):
            low = float(self.service_params.get("low", 180.0))
            high = float(self.service_params.get("high", 420.0))
            mode = float(self.service_params.get("mode", 300.0))
            val = r.triangular(low, high, mode)
            return max(15.0, val)

        elif dist == "constant":
            return max(1.0, float(self.service_params.get("duration_seconds", 300.0)))

        else:
            # Default exponential distribution
            mean_sec = float(self.service_params.get("mean_service_seconds", 300.0))
            if "service_rate_per_minute" in self.service_params:
                rate_per_min = float(self.service_params["service_rate_per_minute"])
                if rate_per_min > 0:
                    mean_sec = 60.0 / rate_per_min
            rate = 1.0 / max(1.0, mean_sec)
            return max(15.0, r.expovariate(rate))

    def start_service(
        self,
        vehicle: Dict[str, Any],
        duration_seconds: Optional[float] = None,
        rng: Optional[random.Random] = None,
    ) -> float:
        """
        Assigns vehicle as currently active on this dispenser and initializes remaining service duration.
        Returns the assigned service duration in seconds.
        """
        if duration_seconds is None:
            duration_seconds = self.sample_service_duration(rng)
        self.active_vehicle = vehicle
        self.remaining_service_time = float(duration_seconds)
        self.status = "BUSY"
        return self.remaining_service_time

    def add_to_queue(self, vehicle: Dict[str, Any]) -> int:
        """
        Appends a vehicle to this dispenser's waiting queue (excluding active vehicle).
        Returns updated waiting queue length.
        """
        self.waiting_queue.append(vehicle)
        return len(self.waiting_queue)

    def step_service(
        self,
        elapsed_seconds: float = 60.0,
        rng: Optional[random.Random] = None,
    ) -> List[Dict[str, Any]]:
        """
        Advances service for elapsed_seconds on this dispenser independently.
        Processes service completions and automatically transitions the next waiting vehicle into service.
        Multiple dispensers step independently and can serve distinct vehicles concurrently.
        Returns list of vehicles that completed service during this time window.
        """
        completed_vehicles = []
        if not self.is_busy:
            return completed_vehicles

        self.remaining_service_time -= elapsed_seconds

        while self.remaining_service_time <= 0:
            # Current active vehicle finished service
            completed = self.active_vehicle
            surplus_seconds = -self.remaining_service_time
            if completed:
                completed["completion_surplus_seconds"] = surplus_seconds
                completed_vehicles.append(completed)
            self.total_vehicles_served += 1

            if self.waiting_queue:
                # Transition next waiting vehicle to active service
                next_veh = self.waiting_queue.pop(0)
                new_duration = self.sample_service_duration(rng)
                self.active_vehicle = next_veh
                self.remaining_service_time = new_duration - surplus_seconds
                self.status = "BUSY"
                if self.remaining_service_time > 0:
                    break
            else:
                # No more vehicles waiting; dispenser is now IDLE
                self.active_vehicle = None
                self.remaining_service_time = 0.0
                self.status = "IDLE"
                break

        return completed_vehicles

    def get_expected_service_duration(self) -> float:
        """
        Returns theoretical mean service duration in seconds for this dispenser
        based on its configured service distribution.
        """
        dist = self.service_distribution
        if dist in ("beta_line1", "line1_beta", "research_line1"):
            # Line 1 research benchmark: 233 + 179 * Beta(0.904, 1.03) seconds
            alpha = float(self.service_params.get("alpha", 0.904))
            beta = float(self.service_params.get("beta", 1.03))
            loc = float(self.service_params.get("loc", 233.0))
            scale = float(self.service_params.get("scale", 179.0))
            return loc + scale * (alpha / (alpha + beta))

        elif dist in ("triangular_line2", "line2_triangular", "research_line2"):
            # Line 2 research benchmark: Triangular(low=239, mode=295, high=350) seconds
            low = float(self.service_params.get("low", 239.0))
            high = float(self.service_params.get("high", 350.0))
            mode = float(self.service_params.get("mode", 295.0))
            return (low + high + mode) / 3.0

        elif dist in ("triangular", "triangular_generic"):
            low = float(self.service_params.get("low", 180.0))
            high = float(self.service_params.get("high", 420.0))
            mode = float(self.service_params.get("mode", 300.0))
            return (low + high + mode) / 3.0

        elif dist == "constant":
            return float(self.service_params.get("duration_seconds", 300.0))

        else:
            # Default exponential distribution
            if "mean_service_seconds" in self.service_params:
                return float(self.service_params["mean_service_seconds"])
            elif "service_rate_per_minute" in self.service_params:
                rate_per_min = float(self.service_params["service_rate_per_minute"])
                if rate_per_min > 0:
                    return 60.0 / rate_per_min
            return 300.0

    def estimate_incoming_waiting_time(self) -> float:
        """
        Calculates expected waiting time in seconds for a new vehicle joining this dispenser:
        W_j = R_j + k_j * E[D_j]
        where:
        - R_j is the active vehicle's remaining service time in seconds (0.0 if dispenser is IDLE).
        - k_j is the count of vehicles currently waiting in line ahead of the arriving vehicle.
        - E[D_j] is the expected service duration for this dispenser.
        Note: Strictly excludes the arriving vehicle's own fueling duration.
        """
        if not self.is_busy:
            return 0.0
        rem = max(0.0, self.remaining_service_time)
        return rem + self.waiting_count * self.get_expected_service_duration()

    def estimate_incoming_waiting_time_minutes(self) -> float:
        """Expected waiting time in minutes for a new vehicle joining this dispenser."""
        return round(self.estimate_incoming_waiting_time() / 60.0, 2)

    def estimate_total_system_time(self) -> float:
        """
        Calculates expected total time in seconds at the station for a new vehicle:
        T_system = W_j + E[D_j] (waiting time until fueling begins + fueling duration).
        """
        return self.estimate_incoming_waiting_time() + self.get_expected_service_duration()

    def estimate_total_system_time_minutes(self) -> float:
        """Expected total system time in minutes for a new vehicle joining this dispenser."""
        return round(self.estimate_total_system_time() / 60.0, 2)

    def calculate_waiting_vehicles_sum_wait(self) -> float:
        """
        Sum of expected waiting times in seconds across all k_j vehicles currently waiting in line:
        sum_{i=1}^{k_j} (R_j + (i - 1) * E[D_j]) = k_j * R_j + (k_j * (k_j - 1) / 2) * E[D_j]
        """
        k = self.waiting_count
        if k <= 0 or not self.is_busy:
            return 0.0
        rem = max(0.0, self.remaining_service_time)
        e_d = self.get_expected_service_duration()
        return k * rem + (k * (k - 1) / 2.0) * e_d

    def clone(self) -> "DispenserChannel":
        """
        Creates an independent deep-copy clone of this dispenser channel,
        preserving its active vehicle, exact remaining service time, waiting queue,
        status, and service configuration.
        Used for Monte Carlo forecasting trajectories without mutating live state.
        """
        cloned = DispenserChannel(
            dispenser_id=self.dispenser_id,
            service_distribution=self.service_distribution,
            service_params=copy.deepcopy(self.service_params),
            name=self.name,
        )
        if self.active_vehicle is not None:
            cloned.active_vehicle = copy.deepcopy(self.active_vehicle)
        cloned.remaining_service_time = float(self.remaining_service_time)
        cloned.status = str(self.status)
        cloned.waiting_queue = copy.deepcopy(self.waiting_queue)
        cloned.total_vehicles_served = int(self.total_vehicles_served)
        return cloned


class MultiDispenserQueueSimulator:
    """
    Multi-Dispenser CNG Queue Simulator (Phases 1, 2, 3 & 4).

    Models a CNG station with an arbitrary number of independent dispensers (servers).
    Each dispenser independently tracks its own waiting line, active vehicle, remaining
    service time countdown, and service distribution.

    Key Capabilities:
    - Phase 1: Multi-dispenser internal state & independent service stepping (no pooling).
    - Phase 2: Station-level arrival generation, configurable balking, and JSQ assignment.
    - Phase 3: Accurate per-dispenser waiting-time calculations (W_j = R_j + k_j * E[D_j]),
               vehicle-weighted average waiting times, and station-level summaries.
    - Phase 4: Non-mutating Monte Carlo lookahead forecasting across 15, 30, and 60 minutes
               simulating parallel channels, dynamic arrivals, balking, JSQ, and probability-weighted wait times.
    """

    def __init__(
        self,
        num_dispensers: int = 2,
        arrival_rate: float = 0.65,
        dispenser_configs: Optional[List[Dict[str, Any]]] = None,
        demand_profile: str = "STATIC",
        cycle_period: int = 60,
        phase_offset: int = 0,
        balking_threshold: int = 35,
        seed: Optional[int] = None,
    ):
        self.num_dispensers = max(1, int(num_dispensers))
        self.arrival_rate = float(arrival_rate)
        self.demand_profile = (demand_profile or "STATIC").upper()
        self.cycle_period = cycle_period
        self.phase_offset = phase_offset
        self.balking_threshold = balking_threshold
        self.step_count = 0
        self.rng = random.Random(seed)
        self.vehicle_id_counter = 0

        # Initialize independent dispensers
        self.dispensers: List[DispenserChannel] = []
        for i in range(self.num_dispensers):
            cfg = (dispenser_configs[i] if dispenser_configs and i < len(dispenser_configs) else {})
            disp_id = cfg.get("dispenser_id", i + 1)
            dist_type = cfg.get("service_distribution", "exponential")
            params = cfg.get("service_params", {})
            name = cfg.get("name", f"Dispenser {disp_id}")
            self.dispensers.append(
                DispenserChannel(
                    dispenser_id=disp_id,
                    service_distribution=dist_type,
                    service_params=params,
                    name=name,
                )
            )

    @property
    def waiting_queue_length(self) -> int:
        """Total vehicles strictly waiting in line across all dispensers (excluding active vehicles)."""
        return sum(d.waiting_count for d in self.dispensers)

    @property
    def vehicles_being_served(self) -> int:
        """Total vehicles currently connected and being actively served across all dispensers."""
        return sum(d.active_count for d in self.dispensers)

    @property
    def total_vehicles(self) -> int:
        """Total vehicles present in the station system (waiting queue + active vehicles)."""
        return sum(d.total_count for d in self.dispensers)

    @property
    def queue(self) -> int:
        """
        Public queue property representing total vehicles present at station bays (waiting + active).
        Preserves backward compatibility with existing telemetry and UI cards.
        """
        return self.total_vehicles

    def get_effective_arrival_multiplier(self, step_idx: Optional[int] = None) -> float:
        """
        Calculates cyclical demand curve multiplier matching existing demand profiles:
        - HEAVY: 1.05 + 0.40 * sin(theta)
        - MODERATE: 0.90 + 0.25 * sin(theta)
        - LOW: 0.65 + 0.15 * sin(theta)
        - STATIC: 1.0
        """
        if self.demand_profile in ("STATIC", "NONE", "") or self.cycle_period <= 0:
            return 1.0

        t = self.step_count if step_idx is None else step_idx
        theta = 2.0 * math.pi * ((t + self.phase_offset) % self.cycle_period) / self.cycle_period

        if self.demand_profile == "HEAVY":
            return 1.05 + 0.40 * math.sin(theta)
        elif self.demand_profile == "MODERATE":
            return 0.90 + 0.25 * math.sin(theta)
        elif self.demand_profile == "LOW":
            return 0.65 + 0.15 * math.sin(theta)
        else:
            return 1.0

    def get_nominal_arrival_rate(self, step_idx: Optional[int] = None) -> float:
        """Calculates station-level nominal arrival rate before balking."""
        if self.arrival_rate <= 0:
            return 0.0
        mult = self.get_effective_arrival_multiplier(step_idx)
        return max(0.05, self.arrival_rate * mult)

    def calculate_balking_probability(self, queue: Optional[int] = None) -> float:
        """
        Calculates the probability that an arriving vehicle enters the station (does not balk).
        Uses total station vehicles present (Q_station = sum(N_j)).
        Formula:
          - If Q == 0 or Q_balk <= 0: P(enter) = 1.0
          - If Q >= Q_balk: P(enter) = 0.10
          - Otherwise: P(enter) = max(0.10, 1.0 - (Q / Q_balk)^2)
        """
        q = self.total_vehicles if queue is None else queue
        if self.balking_threshold <= 0 or q <= 0:
            return 1.0
        if q >= self.balking_threshold:
            return 0.10
        return max(0.10, 1.0 - (q / self.balking_threshold) ** 2)

    def should_balk(self, queue: Optional[int] = None) -> bool:
        """
        Evaluates whether an arriving vehicle balks based on current station queue.
        Returns True if the vehicle diverts (balks), False if it enters the station.
        """
        p_enter = self.calculate_balking_probability(queue)
        return self.rng.random() >= p_enter

    def get_effective_line_lengths(self) -> List[int]:
        """
        Calculates effective line length N_j for every dispenser:
        N_j = waiting_queue_length_j + active_vehicle_indicator_j
        """
        return [d.total_count for d in self.dispensers]

    def get_shortest_dispenser_indices(self) -> List[int]:
        """
        Returns the indices of all dispensers tied for the minimum effective line length N_j.
        """
        line_lengths = self.get_effective_line_lengths()
        min_len = min(line_lengths)
        return [idx for idx, length in enumerate(line_lengths) if length == min_len]

    def select_dispenser_jsq(self) -> int:
        """
        Selects a dispenser using the Join-Shortest-Queue (JSQ) policy.
        Evaluates N_j for all dispensers, selects minimum.
        Breaks ties uniformly at random using self.rng.
        Returns selected dispenser index (0 to num_dispensers - 1).
        """
        tied_indices = self.get_shortest_dispenser_indices()
        if len(tied_indices) == 1:
            return tied_indices[0]
        else:
            return self.rng.choice(tied_indices)

    def assign_vehicle(self, vehicle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assigns an accepted arriving vehicle to a dispenser using Join-Shortest-Queue (JSQ).
        If the selected dispenser is idle, service starts immediately.
        Otherwise, the vehicle is appended to that dispenser's waiting queue.
        Never assigns a vehicle to more than one dispenser.
        Returns assignment metadata.
        """
        chosen_idx = self.select_dispenser_jsq()
        chosen_dispenser = self.dispensers[chosen_idx]

        if not chosen_dispenser.is_busy:
            assigned_status = "ACTIVE"
            chosen_dispenser.start_service(vehicle, rng=self.rng)
        else:
            assigned_status = "QUEUED"
            chosen_dispenser.add_to_queue(vehicle)

        return {
            "vehicle_id": vehicle.get("id"),
            "dispenser_id": chosen_dispenser.dispenser_id,
            "dispenser_name": chosen_dispenser.name,
            "assigned_status": assigned_status,
            "dispenser_total_after": chosen_dispenser.total_count,
        }

    def generate_station_arrivals(self, duration_minutes: float = 1.0) -> List[Dict[str, Any]]:
        """
        Generates vehicle arrivals for the entire station over duration_minutes.
        Each vehicle is generated exactly once at the station level.
        """
        nominal_rate = self.get_nominal_arrival_rate()
        if nominal_rate <= 0:
            return []

        elapsed = 0.0
        arrivals = []
        while True:
            inter_arrival = self.rng.expovariate(nominal_rate)
            elapsed += inter_arrival
            if elapsed > duration_minutes:
                break
            self.vehicle_id_counter += 1
            arrivals.append({
                "id": self.vehicle_id_counter,
                "arrival_step": self.step_count,
                "arrival_offset_seconds": round(elapsed * 60.0, 2),
            })
        return arrivals

    def step_dispensers(self, duration_seconds: float = 60.0) -> Dict[str, Any]:
        """
        Advances service independently across all dispensers for duration_seconds.
        Each dispenser processes its own service completions without server pooling.
        """
        step_summary = {}
        total_served = 0

        for disp in self.dispensers:
            completed = disp.step_service(elapsed_seconds=duration_seconds, rng=self.rng)
            step_summary[disp.dispenser_id] = {
                "dispenser_id": disp.dispenser_id,
                "name": disp.name,
                "completed_count": len(completed),
                "completed_vehicles": completed,
                "active_vehicle": disp.active_vehicle,
                "remaining_service_time": round(disp.remaining_service_time, 2),
                "waiting_count": disp.waiting_count,
                "status": disp.status,
            }
            total_served += len(completed)

        return {
            "duration_seconds": duration_seconds,
            "total_vehicles_served": total_served,
            "dispensers": step_summary,
        }

    def step(self, duration_minutes: float = 1.0) -> Dict[str, Any]:
        """
        Simulates one full time step (default 1 minute):
        1. Advances service independently across all dispensers for duration_minutes * 60 seconds.
        2. Generates station-level arrivals for this time step (each vehicle generated once).
        3. Evaluates balking once per arrival based on current total station occupancy.
        4. Assigns accepted vehicles to dispensers using Join-Shortest-Queue (JSQ).
        5. Updates step counter and returns comprehensive telemetry.
        """
        duration_seconds = duration_minutes * 60.0

        # 1. Advance service on all dispensers
        service_result = self.step_dispensers(duration_seconds=duration_seconds)

        # 2. Generate station-level arrivals
        raw_arrivals = self.generate_station_arrivals(duration_minutes=duration_minutes)

        # 3. Evaluate balking and assign accepted arrivals via JSQ
        accepted_arrivals = []
        balked_arrivals = []
        assignments = []

        for veh in raw_arrivals:
            # Balking decision evaluated once per arriving vehicle before assignment
            if self.should_balk():
                veh["status"] = "BALKED"
                balked_arrivals.append(veh)
            else:
                veh["status"] = "ACCEPTED"
                accepted_arrivals.append(veh)
                assignment_info = self.assign_vehicle(veh)
                assignments.append(assignment_info)

        self.step_count += 1

        nominal_rate = self.get_nominal_arrival_rate()
        balk_factor = self.calculate_balking_probability()
        wait_summary = self.estimate_waiting_time_summary()

        return {
            "step_count": self.step_count,
            "nominal_arrival_rate": round(nominal_rate, 3),
            "effective_arrival_rate": round(nominal_rate * balk_factor, 3),
            "potential_arrivals": len(raw_arrivals),
            "accepted_arrivals": len(accepted_arrivals),
            "balked_arrivals": len(balked_arrivals),
            "vehicles_served": service_result["total_vehicles_served"],
            "waiting_queue_length": self.waiting_queue_length,
            "vehicles_being_served": self.vehicles_being_served,
            "total_vehicles": self.total_vehicles,
            "estimated_waiting_time_minutes": wait_summary["incoming_user_wait_minutes"],
            "waiting_time_summary": wait_summary,
            "dispensers": service_result["dispensers"],
            "assignments": assignments,
        }

    def estimate_dispenser_waiting_times(self) -> Dict[int, float]:
        """Expected incoming waiting time in seconds for each dispenser."""
        return {d.dispenser_id: d.estimate_incoming_waiting_time() for d in self.dispensers}

    def estimate_dispenser_waiting_times_minutes(self) -> Dict[int, float]:
        """Expected incoming waiting time in minutes for each dispenser."""
        return {d.dispenser_id: d.estimate_incoming_waiting_time_minutes() for d in self.dispensers}

    def estimate_incoming_waiting_time(self) -> float:
        """
        Calculates expected waiting time in seconds for an arriving vehicle choosing
        under the Join-Shortest-Queue (JSQ) policy.

        When multiple dispensers have equally short lines (tied minimum N_j),
        JSQ breaks ties uniformly at random. If their remaining service times differ,
        their waiting times may also differ.
        Therefore, the expected waiting time accounts for all equally short candidate lines,
        weighted according to the actual tie-breaking probability:
            E[W_incoming] = (1 / |M|) * sum_{j in M} W_j
        where M is the set of all dispensers tied for the minimum effective line length.
        """
        tied_indices = self.get_shortest_dispenser_indices()
        if not tied_indices:
            return 0.0
        candidate_waits = [self.dispensers[idx].estimate_incoming_waiting_time() for idx in tied_indices]
        return sum(candidate_waits) / float(len(candidate_waits))

    def estimate_incoming_waiting_time_minutes(self) -> float:
        """Expected incoming waiting time in minutes under JSQ."""
        return round(self.estimate_incoming_waiting_time() / 60.0, 2)

    def estimate_average_waiting_time_across_waiting_vehicles(self) -> float:
        """
        Vehicle-weighted average expected waiting time in seconds across all vehicles
        currently waiting in dispenser lines (strictly excluding active vehicles being served).
        Returns 0.0 if no vehicles are waiting in line.
        """
        total_waiting = self.waiting_queue_length
        if total_waiting <= 0:
            return 0.0
        total_sum_wait = sum(d.calculate_waiting_vehicles_sum_wait() for d in self.dispensers)
        return total_sum_wait / float(total_waiting)

    def estimate_average_waiting_time_across_waiting_vehicles_minutes(self) -> float:
        """Vehicle-weighted average waiting time in minutes across currently waiting vehicles."""
        return round(self.estimate_average_waiting_time_across_waiting_vehicles() / 60.0, 2)

    def estimate_waiting_time(self) -> float:
        """
        Standard public method returning expected waiting time in minutes for an incoming driver.
        Preserves backward compatibility with existing telemetry interfaces.
        """
        return self.estimate_incoming_waiting_time_minutes()

    def get_congestion_level(self) -> str:
        """
        Classifies station congestion level based on expected incoming waiting time in minutes:
        - LOW: 0–10 minutes
        - MEDIUM: above 10 and up to 20 minutes
        - HIGH: above 20 minutes
        """
        wait = self.estimate_waiting_time()
        if wait <= 10.0:
            return "LOW"
        elif wait <= 20.0:
            return "MEDIUM"
        else:
            return "HIGH"

    def get_crowd_level(self) -> str:
        """
        Classifies station crowd level based on total vehicles present at station bays:
        - LOW: 0–5 vehicles
        - MODERATE: 6–12 vehicles
        - HIGH: above 12 vehicles
        """
        q = self.total_vehicles
        if q <= 5:
            return "LOW"
        elif q <= 12:
            return "MODERATE"
        else:
            return "HIGH"

    def estimate_waiting_time_summary(self) -> Dict[str, Any]:
        """
        Comprehensive station-level waiting-time summary based on individual dispenser calculations.
        Explicitly distinguishes waiting vehicles from active vehicles and avoids aggregate Q/mu pooling.
        """
        dispenser_waits_s = [d.estimate_incoming_waiting_time() for d in self.dispensers]
        min_wait_s = min(dispenser_waits_s) if dispenser_waits_s else 0.0
        max_wait_s = max(dispenser_waits_s) if dispenser_waits_s else 0.0

        incoming_wait_s = self.estimate_incoming_waiting_time()
        avg_waiting_veh_wait_s = self.estimate_average_waiting_time_across_waiting_vehicles()

        per_dispenser_data = {}
        for d in self.dispensers:
            per_dispenser_data[d.dispenser_id] = {
                "dispenser_id": d.dispenser_id,
                "name": d.name,
                "status": d.status,
                "is_busy": d.is_busy,
                "active_vehicle": d.active_vehicle,
                "remaining_service_seconds": round(max(0.0, d.remaining_service_time), 2),
                "waiting_queue_length": d.waiting_count,
                "total_vehicles": d.total_count,
                "expected_service_duration_seconds": round(d.get_expected_service_duration(), 2),
                "expected_service_duration_minutes": round(d.get_expected_service_duration() / 60.0, 2),
                "incoming_wait_seconds": round(d.estimate_incoming_waiting_time(), 2),
                "incoming_wait_minutes": d.estimate_incoming_waiting_time_minutes(),
                "incoming_total_system_time_minutes": d.estimate_total_system_time_minutes(),
            }

        return {
            "incoming_user_wait_seconds": round(incoming_wait_s, 2),
            "incoming_user_wait_minutes": round(incoming_wait_s / 60.0, 2),
            "average_waiting_vehicles_wait_seconds": round(avg_waiting_veh_wait_s, 2),
            "average_waiting_vehicles_wait_minutes": round(avg_waiting_veh_wait_s / 60.0, 2),
            "min_dispenser_wait_seconds": round(min_wait_s, 2),
            "min_dispenser_wait_minutes": round(min_wait_s / 60.0, 2),
            "max_dispenser_wait_seconds": round(max_wait_s, 2),
            "max_dispenser_wait_minutes": round(max_wait_s / 60.0, 2),
            "waiting_queue_length": self.waiting_queue_length,
            "vehicles_being_served": self.vehicles_being_served,
            "total_vehicles": self.total_vehicles,
            "per_dispenser": per_dispenser_data,
        }

    def get_state_summary(self) -> Dict[str, Any]:
        """Detailed breakdown of multi-dispenser internal state."""
        return {
            "num_dispensers": self.num_dispensers,
            "waiting_queue_length": self.waiting_queue_length,
            "vehicles_being_served": self.vehicles_being_served,
            "total_vehicles": self.total_vehicles,
            "dispensers": [
                {
                    "dispenser_id": d.dispenser_id,
                    "name": d.name,
                    "status": d.status,
                    "is_busy": d.is_busy,
                    "active_vehicle": d.active_vehicle,
                    "remaining_service_seconds": round(d.remaining_service_time, 2),
                    "waiting_queue_length": d.waiting_count,
                    "total_vehicles": d.total_count,
                    "service_distribution": d.service_distribution,
                }
                for d in self.dispensers
            ],
        }

    def clone_state(self, seed: Optional[int] = None) -> "MultiDispenserQueueSimulator":
        """
        Creates an independent deep-copy simulation instance initialized from the current live state,
        including all dispensers, step count, and vehicle counters, with an isolated RNG.
        """
        sim = MultiDispenserQueueSimulator(
            num_dispensers=self.num_dispensers,
            arrival_rate=self.arrival_rate,
            demand_profile=self.demand_profile,
            cycle_period=self.cycle_period,
            phase_offset=self.phase_offset,
            balking_threshold=self.balking_threshold,
            seed=seed,
        )
        sim.step_count = self.step_count
        sim.vehicle_id_counter = self.vehicle_id_counter
        sim.dispensers = [d.clone() for d in self.dispensers]
        return sim

    def forecast(
        self,
        horizons: Tuple[int, ...] = (15, 30, 60),
        trials: int = 500,
        seed: Optional[int] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Multi-Dispenser Monte Carlo Lookahead Forecasting (Phase 4).

        Simulates forward trajectories independently from the station's current state (S0)
        using isolated cloned simulators so that the live simulation is never mutated.

        Each trajectory simulates:
        - Multi-dispenser parallel service channels with independent service completions.
        - Station-level vehicle arrival generation using dynamic demand profiles.
        - Join-Shortest-Queue (JSQ) line assignment with uniform random tie-breaking.
        - Configurable customer balking evaluated per arrival before assignment.
        - Analytical expected incoming waiting time at each horizon accounting for JSQ tie-breaking.

        Parameters:
            horizons: Lookahead minutes to project (default: (15, 30, 60)).
            trials: Number of independent simulation trajectories (default: 500).
            seed: Optional master seed for deterministic reproducibility.

        Returns:
            Dictionary matching the frontend forecast card schema:
            {
                "15m": {
                    "expected_queue": int,                  # Mean total station vehicles (N_station)
                    "queue_range": [int, int],              # P10 and P90 of total vehicles
                    "expected_wait_minutes": float,         # Expected wait for incoming driver under JSQ
                    "expected_waiting_queue": int,          # Mean vehicles strictly waiting in line
                    "waiting_queue_range": [int, int],      # P10 and P90 of waiting queue
                    "expected_vehicles_being_served": float,# Mean vehicles actively being fueled
                    "p10_queue": int,                       # Explicit 10th percentile bound
                    "p90_queue": int                        # Explicit 90th percentile bound
                },
                "30m": { ... },
                "60m": { ... }
            }
        """
        if trials < 1:
            trials = 500

        sorted_horizons = sorted(horizons)
        max_horizon = sorted_horizons[-1] if sorted_horizons else 60

        master_rng = random.Random(seed)

        # Storage for Monte Carlo trajectory outcomes across horizons
        horizon_total_queues = {h: [] for h in sorted_horizons}
        horizon_waiting_queues = {h: [] for h in sorted_horizons}
        horizon_served_queues = {h: [] for h in sorted_horizons}
        horizon_wait_times = {h: [] for h in sorted_horizons}

        for _ in range(trials):
            trial_seed = master_rng.randint(0, 2**31 - 1) if seed is not None else None
            trial_sim = self.clone_state(seed=trial_seed)

            for minute in range(1, max_horizon + 1):
                trial_sim.step(duration_minutes=1.0)
                if minute in horizon_total_queues:
                    horizon_total_queues[minute].append(trial_sim.total_vehicles)
                    horizon_waiting_queues[minute].append(trial_sim.waiting_queue_length)
                    horizon_served_queues[minute].append(trial_sim.vehicles_being_served)
                    horizon_wait_times[minute].append(trial_sim.estimate_incoming_waiting_time_minutes())

        forecast_result = {}
        for h in sorted_horizons:
            totals = horizon_total_queues[h]
            waitings = horizon_waiting_queues[h]
            served_counts = horizon_served_queues[h]
            waits = horizon_wait_times[h]

            if totals:
                totals.sort()
                waitings.sort()

                mean_total = sum(totals) / float(len(totals))
                expected_queue = max(0.0, round(mean_total, 1))

                p10_total = int(round(totals[int(0.10 * (len(totals) - 1))]))
                p90_total = int(round(totals[int(0.90 * (len(totals) - 1))]))
                queue_range = [p10_total, p90_total]

                mean_wait = sum(waits) / float(len(waits))
                expected_wait_minutes = round(mean_wait, 1)

                mean_waiting = sum(waitings) / float(len(waitings))
                expected_waiting_queue = max(0.0, round(mean_waiting, 1))

                p10_waiting = int(round(waitings[int(0.10 * (len(waitings) - 1))]))
                p90_waiting = int(round(waitings[int(0.90 * (len(waitings) - 1))]))
                waiting_queue_range = [p10_waiting, p90_waiting]

                mean_served = sum(served_counts) / float(len(served_counts))
                expected_served = round(mean_served, 1)
            else:
                expected_queue = float(self.total_vehicles)
                queue_range = [int(self.total_vehicles), int(self.total_vehicles)]
                p10_total = int(self.total_vehicles)
                p90_total = int(self.total_vehicles)
                expected_wait_minutes = round(self.estimate_incoming_waiting_time_minutes(), 1)
                expected_waiting_queue = float(self.waiting_queue_length)
                waiting_queue_range = [int(self.waiting_queue_length), int(self.waiting_queue_length)]
                expected_served = float(self.vehicles_being_served)

            forecast_result[f"{h}m"] = {
                "expected_queue": expected_queue,
                "queue_range": queue_range,
                "expected_wait_minutes": expected_wait_minutes,
                "expected_waiting_queue": expected_waiting_queue,
                "waiting_queue_range": waiting_queue_range,
                "expected_vehicles_being_served": expected_served,
                "p10_queue": p10_total,
                "p90_queue": p90_total,
            }

        return forecast_result


def create_research_benchmark_simulator(
    seed: Optional[int] = None,
    arrival_rate: float = 0.503,
    demand_profile: str = "HEAVY",
) -> MultiDispenserQueueSimulator:
    """
    Creates an isolated 2-dispenser research benchmark simulator matching the 2025 paper:
    - Line 1: 233 + 179 * Beta(0.904, 1.03) seconds service (Mean ~316.5s)
    - Line 2: Triangular(239, 295, 350) seconds service (Mean ~294.7s)
    - Default arrival rate = 0.503 veh/min (~30.2 vph, sum of observed Line 1 & Line 2 arrivals)

    IMPORTANT NOTE:
    This is an isolated research benchmark to study and calibrate against the 2025 Arena paper.
    It is NOT applied universally to all Gurugram stations.
    """
    dispenser_configs = [
        {
            "dispenser_id": 1,
            "name": "Line 1 (Benchmark)",
            "service_distribution": "beta_line1",
            "service_params": {"alpha": 0.904, "beta": 1.03, "loc": 233.0, "scale": 179.0},
        },
        {
            "dispenser_id": 2,
            "name": "Line 2 (Benchmark)",
            "service_distribution": "triangular_line2",
            "service_params": {"low": 239.0, "mode": 295.0, "high": 350.0},
        },
    ]
    return MultiDispenserQueueSimulator(
        num_dispensers=2,
        arrival_rate=arrival_rate,
        dispenser_configs=dispenser_configs,
        demand_profile=demand_profile,
        seed=seed,
    )


def load_sample_scenario():
    """
    Load one scenario from the generated CSV.
    """

    csv_path = os.path.join(
        os.path.dirname(__file__),
        "noqueue_simulated_data.csv"
    )

    with open(csv_path, "r", newline="") as file:
        reader = csv.DictReader(file)
        scenario = next(reader)

    return scenario


def main():
    random.seed(42)

    scenario = load_sample_scenario()

    simulator = QueueSimulator(
        initial_queue=int(scenario["vehicles_in_queue"]),
        arrival_rate=float(scenario["arrival_rate_per_minute"]),
        service_rate=float(scenario["service_rate_per_minute"])
    )

    print("\n" + "=" * 60)
    print("NoQueue - CNG Queue Simulation")
    print("=" * 60)

    print(f"Station: {scenario['station_name']}")
    print(f"Initial queue: {simulator.queue} vehicles")
    print(f"Arrival rate: {simulator.arrival_rate} vehicles/min")
    print(f"Service rate: {simulator.service_rate} vehicles/min")

    print("\nQueue progression:")

    history = simulator.run_simulation(steps=10)

    for record in history:
        print(
            f"Minute {record['minute']:2d} | "
            f"Arrivals: {record['arrivals']:2d} | "
            f"Served: {record['vehicles_served']:2d} | "
            f"Queue: {record['current_queue']:2d} | "
            f"Wait: {record['estimated_waiting_time_minutes']} min | "
            f"Crowd: {record['crowd_level']}"
        )

    print("\nSimulation completed.")
    print("Data source: Synthetic (simulated)")
    print("=" * 60)


if __name__ == "__main__":
    main()
