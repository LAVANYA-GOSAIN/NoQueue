"""
NoQueue - Reinforcement Learning Engine (Q-Learning)
===================================================
A beginner-friendly Q-Learning implementation designed to recommend the optimal
CNG station based on simulated traffic levels and queue conditions.

IMPORTANT DISCLAIMER:
---------------------
This engine operates on a SIMULATED DEMONSTRATION environment. It does NOT use
or claim to use live CCTV measurements. All queue lengths, waiting times, and
traffic dynamics are simulated for prototyping and algorithmic demonstration.

Key Reinforcement Learning Concepts Used:
-----------------------------------------
- Agent: The decision maker (our QLearningAgent).
- Environment: Simulated city road traffic and CNG station queues.
- State: Discretized conditions = (traffic_level, demand_level).
- Action: Choosing which CNG station to visit (station_id).
- Reward: Negative total journey time (-1 * (travel_time + waiting_time)).
          RL agents maximize reward. Minimizing 20 minutes is the same as
          maximizing -20 (since -20 > -45).
- Q-Table: A lookup table mapping State -> {Action: Expected Value}.
- Bellman Equation:
    Q(s, a) = Q(s, a) + alpha * [reward + gamma * max_a'(Q(s', a')) - Q(s, a)]
"""

import os
import json
import random
from typing import List, Dict, Tuple, Any, Optional

# =====================================================================
# 1. Environment Simulation Parameters
# =====================================================================

TRAFFIC_LEVELS = ["LOW", "MODERATE", "HEAVY"]
DEMAND_LEVELS = ["LOW", "MODERATE", "HIGH"]

# Multipliers representing how traffic affects baseline travel time
TRAFFIC_MULTIPLIERS = {
    "LOW": 0.8,
    "MODERATE": 1.0,
    "HEAVY": 1.5,
}

# Multipliers representing how overall demand affects baseline waiting time
DEMAND_MULTIPLIERS = {
    "LOW": 0.6,
    "MODERATE": 1.0,
    "HIGH": 1.6,
}

SIMULATION_NOTICE = (
    "Simulated demonstration model: Recommendation is derived using Q-learning "
    "on simulated traffic and queue dynamics, NOT live CCTV measurements."
)


# =====================================================================
# 2. Simulated Environment Class
# =====================================================================

class SimulatedCNGEnvironment:
    """
    Simulates stochastic traffic and station queue fluctuations for training.
    """

    def __init__(self, stations: List[Dict[str, Any]]):
        self.stations = stations
        self.station_map = {s["id"]: s for s in stations}
        self.current_traffic = "MODERATE"
        self.current_demand = "MODERATE"

    def get_state(self) -> str:
        """Returns the current state key, e.g. 'MODERATE_HIGH'."""
        return f"{self.current_traffic}_{self.current_demand}"

    def get_available_actions(self) -> List[int]:
        """Actions are the unique IDs of available CNG stations."""
        return [s["id"] for s in self.stations]

    def step(self, action_station_id: int) -> Tuple[str, float, Dict[str, Any]]:
        """
        Executes an action (selecting a station), calculates the simulated journey time,
        transitions the environment to the next state, and returns:
          (next_state, reward, step_details)
        """
        station = self.station_map[action_station_id]

        # Extract baseline travel and waiting times
        base_travel = float(
            station.get("travel_time_minutes")
            or station.get("travelTime")
            or 10.0
        )
        base_wait = float(
            station.get("estimated_waiting_time_minutes")
            or station.get("waitTime")
            or 15.0
        )

        # Apply current state multipliers with a small random noise factor
        traffic_mult = TRAFFIC_MULTIPLIERS[self.current_traffic]
        demand_mult = DEMAND_MULTIPLIERS[self.current_demand]

        # Add small simulated fluctuations (+- 10%)
        noise_travel = random.uniform(0.9, 1.1)
        noise_wait = random.uniform(0.85, 1.15)

        simulated_travel_time = round(base_travel * traffic_mult * noise_travel, 1)
        simulated_wait_time = round(base_wait * demand_mult * noise_wait, 1)
        total_journey_time = round(simulated_travel_time + simulated_wait_time, 1)

        # Reward is negative total journey time (shorter time = higher reward)
        reward = -total_journey_time

        # Simulate environmental transition to the next state (Markovian drift)
        self.current_traffic = random.choice(TRAFFIC_LEVELS)
        self.current_demand = random.choice(DEMAND_LEVELS)
        next_state = self.get_state()

        step_details = {
            "station_id": action_station_id,
            "station_name": station.get("name", "Unknown Station"),
            "travel_time": simulated_travel_time,
            "waiting_time": simulated_wait_time,
            "total_journey_time": total_journey_time,
            "reward": reward,
        }

        return next_state, reward, step_details

    def reset(self) -> str:
        """Resets the environment to a random initial state."""
        self.current_traffic = random.choice(TRAFFIC_LEVELS)
        self.current_demand = random.choice(DEMAND_LEVELS)
        return self.get_state()


# =====================================================================
# 3. Q-Learning Agent Class
# =====================================================================

class QLearningAgent:
    """
    Tabular Q-Learning Agent.
    
    Parameters:
      alpha (float): Learning rate (0.1) - Controls how aggressively new experiences
                     overwrite existing estimates.
      gamma (float): Discount factor (0.9) - Balances immediate vs future rewards.
      epsilon (float): Exploration rate (0.2) - Probability of choosing a random
                       exploratory action instead of the best known action.
    """

    def __init__(
        self,
        alpha: float = 0.1,
        gamma: float = 0.9,
        epsilon: float = 0.2,
    ):
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        # Q-Table structure: { state_string: { action_id_string: float_q_value } }
        self.q_table: Dict[str, Dict[str, float]] = {}

    def get_q_value(self, state: str, action: int) -> float:
        """Returns the Q-value for a given state and action (defaults to 0.0)."""
        action_key = str(action)
        if state not in self.q_table:
            return 0.0
        return self.q_table[state].get(action_key, 0.0)

    def set_q_value(self, state: str, action: int, value: float) -> None:
        """Updates the Q-value for a state-action pair."""
        action_key = str(action)
        if state not in self.q_table:
            self.q_table[state] = {}
        self.q_table[state][action_key] = value

    def choose_action(
        self,
        state: str,
        available_actions: List[int],
        explore: bool = True,
    ) -> int:
        """
        Epsilon-greedy action selection:
        - With probability epsilon (if explore=True), pick a random action (Exploration).
        - Otherwise, pick the action with the highest Q-value (Exploitation).
        """
        if not available_actions:
            raise ValueError("No actions available to select from.")

        # Exploration step
        if explore and random.random() < self.epsilon:
            return random.choice(available_actions)

        # Exploitation step: find action with max Q-value
        q_values = {a: self.get_q_value(state, a) for a in available_actions}
        max_q = max(q_values.values())

        # If there is a tie, randomly select among best actions
        best_actions = [a for a, q in q_values.items() if q == max_q]
        return random.choice(best_actions)

    def update(
        self,
        state: str,
        action: int,
        reward: float,
        next_state: str,
        next_available_actions: List[int],
    ) -> float:
        """
        Implements the classic Q-Learning Bellman update equation:
        Q(s, a) = Q(s, a) + alpha * [reward + gamma * max_a'(Q(s', a')) - Q(s, a)]
        """
        old_q = self.get_q_value(state, action)

        # Find maximum Q-value for the next state
        if next_available_actions:
            max_next_q = max(
                self.get_q_value(next_state, a) for a in next_available_actions
            )
        else:
            max_next_q = 0.0

        # Temporal Difference (TD) Target and Error
        td_target = reward + self.gamma * max_next_q
        td_error = td_target - old_q

        # New Q-value
        new_q = old_q + self.alpha * td_error
        self.set_q_value(state, action, round(new_q, 4))
        return new_q

    def save_q_table(self, filepath: str) -> None:
        """Saves the learned Q-table to a JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.q_table, f, indent=2)

    def load_q_table(self, filepath: str) -> bool:
        """Loads a previously saved Q-table from JSON."""
        if not os.path.exists(filepath):
            return False
        with open(filepath, "r", encoding="utf-8") as f:
            self.q_table = json.load(f)
        return True


# =====================================================================
# 4. Training Function
# =====================================================================

def train_agent(
    stations: List[Dict[str, Any]],
    episodes: int = 1000,
    steps_per_episode: int = 10,
    alpha: float = 0.1,
    gamma: float = 0.9,
    epsilon: float = 0.2,
    save_path: Optional[str] = None,
) -> Tuple[QLearningAgent, Dict[str, Any]]:
    """
    Trains the Q-Learning agent on the simulated CNG environment for the given
    number of episodes.
    """
    env = SimulatedCNGEnvironment(stations)
    agent = QLearningAgent(alpha=alpha, gamma=gamma, epsilon=epsilon)
    actions = env.get_available_actions()

    total_rewards: List[float] = []

    for episode in range(episodes):
        state = env.reset()
        episode_reward = 0.0

        for _ in range(steps_per_episode):
            # Select action via epsilon-greedy
            action = agent.choose_action(state, actions, explore=True)

            # Step environment
            next_state, reward, _ = env.step(action)

            # Update Q-table
            agent.update(state, action, reward, next_state, actions)

            state = next_state
            episode_reward += reward

        total_rewards.append(episode_reward)

    training_summary = {
        "episodes": episodes,
        "steps_per_episode": steps_per_episode,
        "average_reward_last_100": round(
            sum(total_rewards[-100:]) / min(len(total_rewards), 100), 2
        ),
        "total_states_learned": len(agent.q_table),
    }

    if save_path:
        agent.save_q_table(save_path)

    return agent, training_summary


# =====================================================================
# 5. Recommendation Function
# =====================================================================

def recommend_station(
    stations: List[Dict[str, Any]],
    agent: Optional[QLearningAgent] = None,
    traffic_level: str = "MODERATE",
    demand_level: str = "MODERATE",
) -> Dict[str, Any]:
    """
    Recommends the best CNG station for the given state using the trained Q-table.

    Returns:
      - selected_station: Full station dictionary
      - estimated_travel_time: String and numeric value
      - estimated_waiting_time: String and numeric value
      - estimated_total_journey_time: String and numeric value
      - q_value: The learned quality metric from the Q-table
      - is_simulated: True
      - disclaimer: Notice stating this is simulated data
    """
    if not stations:
        raise ValueError("Cannot recommend from an empty list of stations.")

    # Normalize traffic and demand
    traffic = traffic_level.upper() if traffic_level.upper() in TRAFFIC_LEVELS else "MODERATE"
    demand = demand_level.upper() if demand_level.upper() in DEMAND_LEVELS else "MODERATE"
    state = f"{traffic}_{demand}"

    available_actions = [s["id"] for s in stations]
    station_map = {s["id"]: s for s in stations}

    # If no agent provided, train a quick agent or load default
    if agent is None:
        agent = QLearningAgent()
        default_q_file = os.path.join(
            os.path.dirname(__file__), "q_table.json"
        )
        if not agent.load_q_table(default_q_file):
            # Train if no saved file exists
            agent, _ = train_agent(stations, episodes=500, save_path=default_q_file)

    # Exploitation only (no exploration when recommending to users)
    chosen_id = agent.choose_action(state, available_actions, explore=False)
    selected_station = station_map[chosen_id]

    # Calculate estimated times adjusted for the current state
    base_travel = float(
        selected_station.get("travel_time_minutes")
        or selected_station.get("travelTime")
        or 10.0
    )
    base_wait = float(
        selected_station.get("estimated_waiting_time_minutes")
        or selected_station.get("waitTime")
        or 15.0
    )

    travel_adj = round(base_travel * TRAFFIC_MULTIPLIERS[traffic], 1)
    wait_adj = round(base_wait * DEMAND_MULTIPLIERS[demand], 1)
    total_time = round(travel_adj + wait_adj, 1)

    q_val = agent.get_q_value(state, chosen_id)

    return {
        "status": "success",
        "selected_station": selected_station,
        "estimated_travel_time": f"{travel_adj} min",
        "estimated_travel_time_minutes": travel_adj,
        "estimated_waiting_time": f"{wait_adj} min",
        "estimated_waiting_time_minutes": wait_adj,
        "estimated_total_journey_time": f"{total_time} min",
        "estimated_total_journey_time_minutes": total_time,
        "q_value": q_val,
        "state_evaluated": state,
        "traffic_level": traffic,
        "demand_level": demand,
        "is_simulated": True,
        "disclaimer": SIMULATION_NOTICE,
    }


# =====================================================================
# 6. Test and Verification Demo
# =====================================================================

if __name__ == "__main__":
    print("=" * 65)
    print("NoQueue - Q-Learning Engine Demonstration")
    print("=" * 65)

    # Sample dataset matching backend/main.py structure
    sample_stations = [
        {
            "id": 1,
            "name": "Green Fuel CNG Station",
            "address": "Sector 50, Gurugram",
            "distance": "1.2 km",
            "travel_time_minutes": 5,
            "queue_length": 3,
            "estimated_waiting_time_minutes": 8,
            "crowd_level": "Low",
        },
        {
            "id": 2,
            "name": "City Gas Point",
            "address": "Golf Course Extension Road, Gurugram",
            "distance": "2.4 km",
            "travel_time_minutes": 9,
            "queue_length": 7,
            "estimated_waiting_time_minutes": 18,
            "crowd_level": "Moderate",
        },
        {
            "id": 3,
            "name": "Highway CNG Station",
            "address": "Sohna Road, Gurugram",
            "distance": "3.1 km",
            "travel_time_minutes": 11,
            "queue_length": 12,
            "estimated_waiting_time_minutes": 28,
            "crowd_level": "High",
        },
        {
            "id": 4,
            "name": "EcoFill CNG Hub",
            "address": "MG Road, Sector 28, Gurugram",
            "distance": "4.5 km",
            "travel_time_minutes": 14,
            "queue_length": 5,
            "estimated_waiting_time_minutes": 12,
            "crowd_level": "Moderate",
        },
    ]

    q_table_file = os.path.join(os.path.dirname(__file__), "q_table.json")

    # Step 1: Train the agent for 1000 episodes
    print("\n[1/4] Training agent for 1,000 episodes on simulated conditions...")
    agent, summary = train_agent(
        stations=sample_stations,
        episodes=1000,
        alpha=0.1,
        gamma=0.9,
        epsilon=0.2,
        save_path=q_table_file,
    )
    print(f"      ✓ Training complete!")
    print(f"      ✓ Summary: {summary}")

    # Step 2: Display sample Q-Table entries
    print("\n[2/4] Sample learned Q-Table values:")
    for state, actions_q in list(agent.q_table.items())[:3]:
        print(f"      State [{state}]:")
        for act, q in actions_q.items():
            st_name = next(s["name"] for s in sample_stations if s["id"] == int(act))
            print(f"        -> Station {act} ({st_name}): Q = {q}")

    # Step 3: Test saving and reloading
    print("\n[3/4] Verifying JSON save and load...")
    reloaded_agent = QLearningAgent()
    loaded = reloaded_agent.load_q_table(q_table_file)
    print(f"      ✓ Q-Table loaded successfully: {loaded}")
    assert loaded is True
    assert len(reloaded_agent.q_table) > 0

    # Step 4: Test recommendation function under different conditions
    print("\n[4/4] Testing Recommendations across various simulated states:")
    test_conditions = [
        ("LOW", "LOW"),
        ("MODERATE", "MODERATE"),
        ("HEAVY", "HIGH"),
    ]

    for traffic, demand in test_conditions:
        rec = recommend_station(
            stations=sample_stations,
            agent=reloaded_agent,
            traffic_level=traffic,
            demand_level=demand,
        )
        print(f"\n      Conditions: Traffic={traffic}, Demand={demand}")
        print(f"      -> Recommended Station: {rec['selected_station']['name']}")
        print(f"      -> Estimated Travel Time: {rec['estimated_travel_time']}")
        print(f"      -> Estimated Waiting Time: {rec['estimated_waiting_time']}")
        print(f"      -> Total Journey Time: {rec['estimated_total_journey_time']}")
        print(f"      -> Learned Q-Value: {rec['q_value']}")
        print(f"      -> Is Simulated: {rec['is_simulated']}")

    print("\n" + "=" * 65)
    print("All Q-Learning tests passed successfully!")
    print("=" * 65)

