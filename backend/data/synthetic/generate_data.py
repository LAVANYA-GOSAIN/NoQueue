
import csv
import random
import os

# Make the generated data reproducible
random.seed(42)

# Demonstration stations with realistic physical dispenser capacity
STATIONS = [
    {
        "station_id": 1,
        "station_name": "Green Fuel CNG Station",
        "base_distance_km": 1.2,
        "base_travel_time": 5,
        "service_range": (0.55, 0.68),
        "dispensers": 2
    },
    {
        "station_id": 2,
        "station_name": "City Gas Point",
        "base_distance_km": 2.4,
        "base_travel_time": 9,
        "service_range": (0.70, 0.82),
        "dispensers": 2
    },
    {
        "station_id": 3,
        "station_name": "Highway CNG Station",
        "base_distance_km": 3.1,
        "base_travel_time": 11,
        "service_range": (0.95, 1.25),
        "dispensers": 4
    },
    {
        "station_id": 4,
        "station_name": "EcoFill CNG Hub",
        "base_distance_km": 4.5,
        "base_travel_time": 14,
        "service_range": (0.65, 0.78),
        "dispensers": 2
    }
]

TRAFFIC_LEVELS = ["LOW", "MODERATE", "HEAVY"]

def generate_scenario(scenario_id, station, traffic_override=None, queue_override=None):
    # Determine traffic condition
    traffic = traffic_override or random.choice(TRAFFIC_LEVELS)

    traffic_multiplier = {
        "LOW": 0.8,
        "MODERATE": 1.0,
        "HEAVY": 1.5
    }[traffic]

    # Realistic service rate based on station dispenser capacity
    min_serv, max_serv = station["service_range"]
    service_rate = round(random.uniform(min_serv, max_serv), 2)

    # Realistic arrival rate correlated with traffic condition
    if traffic == "LOW":
        arrival_ratio = random.uniform(0.60, 0.78)
        default_q = random.randint(1, 5)
    elif traffic == "MODERATE":
        arrival_ratio = random.uniform(0.78, 0.90)
        default_q = random.randint(5, 11)
    else:  # HEAVY
        arrival_ratio = random.uniform(0.85, 1.05)
        default_q = random.randint(10, 16)

    arrival_rate = round(service_rate * arrival_ratio, 2)
    vehicles_in_queue = queue_override if queue_override is not None else default_q

    # Estimate waiting time: 0 vehicles in queue produces 0 waiting time
    if vehicles_in_queue == 0:
        estimated_wait = 0.0
    else:
        estimated_wait = round(vehicles_in_queue / max(service_rate, 0.1), 2)

    # Adjust travel time according to traffic
    travel_time = round(
        station["base_travel_time"] * traffic_multiplier
        + random.uniform(0, 1.5),
        2
    )

    # Assign crowd level
    if vehicles_in_queue <= 5:
        crowd_level = "LOW"
    elif vehicles_in_queue <= 12:
        crowd_level = "MODERATE"
    else:
        crowd_level = "HIGH"

    return {
        "scenario_id": scenario_id,
        "station_id": station["station_id"],
        "station_name": station["station_name"],
        "distance_km": station["base_distance_km"],
        "travel_time_minutes": travel_time,
        "traffic_level": traffic,
        "vehicles_in_queue": vehicles_in_queue,
        "arrival_rate_per_minute": arrival_rate,
        "service_rate_per_minute": service_rate,
        "estimated_waiting_time_minutes": estimated_wait,
        "crowd_level": crowd_level,
        "data_source": "synthetic",
        "is_simulated": True
    }


def generate_dataset(total_scenarios=1000):
    rows = []

    # Scenarios 1-4: Deterministic, stable demonstration baselines for all 4 stations
    # Station 1: Green Fuel (LOW traffic, 4 queue, balanced)
    rows.append({
        "scenario_id": 1,
        "station_id": 1,
        "station_name": "Green Fuel CNG Station",
        "distance_km": 1.2,
        "travel_time_minutes": 4.0,
        "traffic_level": "LOW",
        "vehicles_in_queue": 4,
        "arrival_rate_per_minute": 0.50,
        "service_rate_per_minute": 0.60,
        "estimated_waiting_time_minutes": 6.67,
        "crowd_level": "LOW",
        "data_source": "synthetic",
        "is_simulated": True
    })

    # Station 2: City Gas Point (MODERATE traffic, 7 queue, balanced)
    rows.append({
        "scenario_id": 2,
        "station_id": 2,
        "station_name": "City Gas Point",
        "distance_km": 2.4,
        "travel_time_minutes": 9.0,
        "traffic_level": "MODERATE",
        "vehicles_in_queue": 7,
        "arrival_rate_per_minute": 0.65,
        "service_rate_per_minute": 0.75,
        "estimated_waiting_time_minutes": 9.33,
        "crowd_level": "MODERATE",
        "data_source": "synthetic",
        "is_simulated": True
    })

    # Station 3: Highway CNG Station (MODERATE traffic, 11 queue, 4-pump high throughput)
    rows.append({
        "scenario_id": 3,
        "station_id": 3,
        "station_name": "Highway CNG Station",
        "distance_km": 3.1,
        "travel_time_minutes": 11.0,
        "traffic_level": "MODERATE",
        "vehicles_in_queue": 11,
        "arrival_rate_per_minute": 0.95,
        "service_rate_per_minute": 1.10,
        "estimated_waiting_time_minutes": 10.0,
        "crowd_level": "MODERATE",
        "data_source": "synthetic",
        "is_simulated": True
    })

    # Station 4: EcoFill CNG Hub (HEAVY traffic, 8 queue, balanced urban hub)
    rows.append({
        "scenario_id": 4,
        "station_id": 4,
        "station_name": "EcoFill CNG Hub",
        "distance_km": 4.5,
        "travel_time_minutes": 21.0,
        "traffic_level": "HEAVY",
        "vehicles_in_queue": 8,
        "arrival_rate_per_minute": 0.62,
        "service_rate_per_minute": 0.70,
        "estimated_waiting_time_minutes": 11.43,
        "crowd_level": "MODERATE",
        "data_source": "synthetic",
        "is_simulated": True
    })

    # Ensure all 36 combinations (4 stations x 3 traffic levels x 3 queue levels) exist
    queue_samples = {
        "LOW": [1, 3, 5],
        "MODERATE": [6, 9, 12],
        "HIGH": [14, 17, 20]
    }

    # Generate remaining scenarios covering all combinations
    scenario_id = 5
    while scenario_id <= total_scenarios:
        for st in STATIONS:
            for tf in TRAFFIC_LEVELS:
                for q_lvl in ["LOW", "MODERATE", "HIGH"]:
                    if scenario_id > total_scenarios:
                        break
                    q_val = random.choice(queue_samples[q_lvl])
                    rows.append(generate_scenario(scenario_id, st, traffic_override=tf, queue_override=q_val))
                    scenario_id += 1

    output_path = os.path.join(
        os.path.dirname(__file__),
        "noqueue_simulated_data.csv"
    )

    fieldnames = rows[0].keys()

    with open(output_path, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("=" * 55)
    print("NoQueue Synthetic Dataset Generated Successfully!")
    print("=" * 55)
    print(f"Total scenarios: {len(rows)}")
    print(f"Output file: {output_path}")
    print("\nSample records:")

    for row in rows[:5]:
        print(row)


if __name__ == "__main__":
    generate_dataset()
