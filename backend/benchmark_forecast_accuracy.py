"""
NoQueue — Phase 5: Isolated Statistical Evaluation of Multi-Dispenser Forecasting
==================================================================================
File: backend/benchmark_forecast_accuracy.py

RESEARCH METHODOLOGY NOTICE:
----------------------------
These results evaluate forecasting performance against independently generated outcomes
from a controlled synthetic simulation environment. They do NOT establish predictive
accuracy on real-world CNG station data. Real-world validation requires independently
observed, timestamped queue histories extracted from real petrol pump recordings.

Categories evaluated:
1. SYNTHETIC — IN-MODEL EVALUATION:
   Forecast and evaluation trajectories share identical model assumptions but use
   independent, non-shared random streams.
2. SYNTHETIC — MODEL-MISMATCH STRESS EVALUATION:
   Evaluation environment experiences alternative synthetic conditions (e.g. arrival surges,
   dispenser pressure drops, off-peak drops, aggressive balking) while forecast model assumptions
   remain unadjusted.

Metrics calculated separately at 15m, 30m, and 60m horizons:
- Queue MAE (Total station occupancy)
- Queue RMSE (Total station occupancy)
- Waiting-Time MAE (Incoming driver wait under JSQ)
- Prediction Interval Coverage Probability (PICP, nominal 80% [P10-P90])
- Mean Prediction Interval Width (MPIW, vehicles)
- Congestion Macro-F1 (LOW <= 10m, MEDIUM 10-20m, HIGH > 20m)
- Waiting Queue MAE & RMSE (Auxiliary metric for strictly waiting vehicles)
"""

import os
import sys
import math
import json
import random
import copy
import argparse
from typing import List, Dict, Any, Tuple, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from data.synthetic.queue_simulator import (
    DispenserChannel,
    MultiDispenserQueueSimulator,
    create_research_benchmark_simulator,
)

EVALUATION_DISCLAIMER = (
    "These results evaluate forecasting performance against independently generated outcomes "
    "from the controlled synthetic simulation environment. They do not establish predictive "
    "accuracy on real-world CNG station data. Real-world validation requires independently "
    "observed, timestamped queue histories."
)

REAL_WORLD_VALIDATION_STATUS = "NOT AVAILABLE — INDEPENDENT OBSERVATIONS REQUIRED"


# =====================================================================
# 1. Metric Calculation Utility Functions
# =====================================================================

def calculate_mae(actuals: List[float], predictions: List[float]) -> float:
    """Calculates Mean Absolute Error: (1/n) * sum(|y - y_hat|)."""
    if not actuals or len(actuals) != len(predictions):
        return 0.0
    return sum(abs(a - p) for a, p in zip(actuals, predictions)) / float(len(actuals))


def calculate_rmse(actuals: List[float], predictions: List[float]) -> float:
    """Calculates Root Mean Squared Error: sqrt((1/n) * sum((y - y_hat)^2))."""
    if not actuals or len(actuals) != len(predictions):
        return 0.0
    mse = sum((a - p) ** 2 for a, p in zip(actuals, predictions)) / float(len(actuals))
    return math.sqrt(mse)


def calculate_sample_std(values: List[float]) -> float:
    """
    Calculates sample standard deviation:
    s = sqrt((1 / (n - 1)) * sum((x_i - x_bar)^2))
    Represents sample-level variation among individual evaluation errors.
    Returns 0.0 if n < 2.
    """
    n = len(values)
    if n < 2:
        return 0.0
    mean_val = sum(values) / float(n)
    var = sum((x - mean_val) ** 2 for x in values) / float(n - 1)
    return math.sqrt(var)


def calculate_confidence_interval(values: List[float], confidence: float = 0.95) -> Tuple[float, float]:
    """
    Calculates 95% confidence interval for the sample mean:
    x_bar +/- z * (s / sqrt(n)), where z = 1.95996 for nominal 95% confidence.
    Represents uncertainty in aggregate metric estimates.
    Returns (mean, mean) if n <= 1.
    """
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean_val = sum(values) / float(n)
    if n == 1:
        return round(mean_val, 4), round(mean_val, 4)
    s = calculate_sample_std(values)
    se = s / math.sqrt(n)
    z = 1.95996  # Standard two-tailed 95% normal critical value
    margin = z * se
    return round(mean_val - margin, 4), round(mean_val + margin, 4)


def calculate_clustered_ci(rep_values: List[float], confidence: float = 0.95) -> Dict[str, Any]:
    """
    Computes replication-level mean, sample standard deviation, and cluster-aware
    confidence interval using Student's t-distribution with df = R - 1 degrees of freedom.
    Accounts for within-cluster temporal dependence among origins within the same replication.
    """
    R = len(rep_values)
    if R == 0:
        return {"mean": 0.0, "std_dev": 0.0, "se": 0.0, "ci_95": [0.0, 0.0], "df": 0, "replication_values": []}
    mean_val = sum(rep_values) / float(R)
    if R == 1:
        return {"mean": round(mean_val, 4), "std_dev": 0.0, "se": 0.0, "ci_95": [round(mean_val, 4), round(mean_val, 4)], "df": 0, "replication_values": [round(mean_val, 4)]}

    s_rep = math.sqrt(sum((v - mean_val) ** 2 for v in rep_values) / float(R - 1))
    se_cluster = s_rep / math.sqrt(R)

    # Student-t critical values (two-tailed 95%):
    t_table = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.7764, 5: 2.571,
        6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228
    }
    df = R - 1
    t_crit = t_table.get(df, 1.960 if df >= 30 else 2.042)
    margin = t_crit * se_cluster

    return {
        "mean": round(mean_val, 4),
        "std_dev": round(s_rep, 4),
        "se": round(se_cluster, 4),
        "ci_95": [round(mean_val - margin, 4), round(mean_val + margin, 4)],
        "df": df,
        "t_crit": t_crit,
        "replication_values": [round(v, 4) for v in rep_values],
    }


def calculate_bounded_clustered_picp(
    rep_hits: List[int],
    rep_totals: List[int],
    confidence: float = 0.95,
    df: Optional[int] = None,
    t_crit: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Computes cluster-aware confidence interval for PICP coverage probability
    using the Rao-Scott design-effect adjusted Wilson score method.
    Guarantees that confidence intervals lie strictly within [0, 1] under all conditions
    without ad-hoc clipping.
    Accounts for intra-cluster correlation across independent replications.
    """
    R = len(rep_hits)
    total_hits = sum(rep_hits)
    total_n = sum(rep_totals)
    if total_n == 0:
        return {
            "picp": 0.0,
            "ci_95": [0.0, 0.0],
            "deff": 1.0,
            "n_eff": 0.0,
            "rep_coverages": [],
            "method": "zero_sample_safe"
        }

    p_hat = total_hits / float(total_n)

    # Simple random sample variance
    v_srs = (p_hat * (1.0 - p_hat)) / float(total_n)

    # Cluster sample variance (ratio estimator variance across clusters)
    v_cluster = 0.0
    if R > 1:
        v_cluster = (float(R) / float(R - 1)) * sum(
            ((n / float(total_n)) ** 2) * (((k / float(n)) - p_hat) ** 2)
            for k, n in zip(rep_hits, rep_totals)
        )

    # Design effect (ratio of cluster variance to simple random sample variance)
    deff = (v_cluster / v_srs) if (v_srs > 1e-9 and v_cluster > 0) else 1.0
    deff = max(1.0, deff)
    n_eff = total_n / deff

    # Determine critical value based on degrees of freedom (df = R - 1)
    if df is None:
        df = max(1, R - 1)
    if t_crit is None:
        t_table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.7764, 5: 2.571, 9: 2.262, 19: 2.093}
        z = t_table.get(df, 1.960 if df >= 30 else 2.042)
    else:
        z = t_crit

    # Wilson score interval on effective sample size
    denom = 1.0 + (z ** 2) / n_eff
    center = (p_hat + (z ** 2) / (2.0 * n_eff)) / denom
    under_sqrt = (p_hat * (1.0 - p_hat) / n_eff) + (z ** 2) / (4.0 * (n_eff ** 2))
    margin = (z / denom) * math.sqrt(max(0.0, under_sqrt))

    ci_low = max(0.0, min(1.0, center - margin))
    ci_high = max(0.0, min(1.0, center + margin))

    rep_rates = [round(k / float(n), 4) for k, n in zip(rep_hits, rep_totals)]
    return {
        "picp": round(p_hat, 4),
        "ci_95": [round(ci_low, 4), round(ci_high, 4)],
        "deff": round(deff, 3),
        "n_eff": round(n_eff, 1),
        "rep_coverages": rep_rates,
        "method": "rao_scott_cluster_adjusted_wilson"
    }


def calculate_wilson_score_interval(hits: int, total: int, confidence: float = 0.95) -> Tuple[float, float]:
    """
    Calculates Wilson score interval for binomial proportion (e.g. PICP).
    Produces robust confidence intervals even near 0 or 1 and for moderate sample sizes.
    Formula:
      center = (p_hat + z^2 / (2n)) / (1 + z^2 / n)
      margin = (z / (1 + z^2 / n)) * sqrt((p_hat * (1 - p_hat) / n) + (z^2 / (4n^2)))
    """
    if total <= 0:
        return 0.0, 0.0
    p_hat = hits / float(total)
    z = 1.95996
    denom = 1.0 + (z ** 2) / total
    center = (p_hat + (z ** 2) / (2.0 * total)) / denom
    under_sqrt = (p_hat * (1.0 - p_hat) / total) + (z ** 2) / (4.0 * (total ** 2))
    margin = (z / denom) * math.sqrt(max(0.0, under_sqrt))
    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return round(low, 4), round(high, 4)


def calculate_picp(actuals: List[float], p10s: List[float], p90s: List[float]) -> float:
    """
    Calculates Prediction Interval Coverage Probability (PICP):
    PICP = (1/n) * sum(I(L_i <= y_i <= U_i))
    Nominal coverage target for P10-P90 interval is 80% (0.80).
    """
    if not actuals or len(actuals) != len(p10s) or len(actuals) != len(p90s):
        return 0.0
    hits = sum(1 for a, low, high in zip(actuals, p10s, p90s) if low <= a <= high)
    return hits / float(len(actuals))


def calculate_picp_detailed(actuals: List[float], p10s: List[float], p90s: List[float]) -> Dict[str, Any]:
    """
    Calculates PICP with full numerator/denominator count (k/n), ratio string,
    percentage, and 95% Wilson score confidence interval.
    """
    if not actuals or len(actuals) != len(p10s) or len(actuals) != len(p90s):
        return {
            "hits": 0,
            "total": 0,
            "ratio": "0/0",
            "picp": 0.0,
            "percentage": "0.0%",
            "ci_95": [0.0, 0.0],
        }
    n = len(actuals)
    hits = sum(1 for a, low, high in zip(actuals, p10s, p90s) if low <= a <= high)
    picp = hits / float(n)
    ci_low, ci_high = calculate_wilson_score_interval(hits, n)
    return {
        "hits": hits,
        "total": n,
        "ratio": f"{hits}/{n}",
        "picp": round(picp, 4),
        "percentage": f"{round(picp * 100, 1)}%",
        "ci_95": [ci_low, ci_high],
    }


def calculate_mpiw(p10s: List[float], p90s: List[float]) -> float:
    """Calculates Mean Prediction Interval Width: (1/n) * sum(U_i - L_i)."""
    if not p10s or len(p10s) != len(p90s):
        return 0.0
    return sum((high - low) for low, high in zip(p10s, p90s)) / float(len(p10s))


def classify_congestion(wait_minutes: float) -> str:
    """
    Classifies congestion state based on established NoQueue wait-time boundaries:
    - LOW: <= 10.0 minutes
    - MEDIUM: 10.1 to 20.0 minutes
    - HIGH: > 20.0 minutes
    """
    if wait_minutes <= 10.0:
        return "LOW"
    elif wait_minutes <= 20.0:
        return "MEDIUM"
    else:
        return "HIGH"


def calculate_congestion_f1(
    actual_waits: List[float],
    predicted_waits: List[float],
    classes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Calculates multi-class confusion matrix, per-class metrics, and Macro-F1.
    Conforms to standard classification conventions (zero_division=0.0):
    - Classes absent from both ground truth and predictions receive F1=0.0.
    - Macro-F1 is evaluated across active classes (classes present in ground truth or predictions).
    - Also reports fixed 3-class Macro-F1 (averaging over all classes with zero_division=0.0).
    - Never assigns artificial 1.0 scores to absent classes.
    """
    if classes is None:
        classes = ["LOW", "MEDIUM", "HIGH"]

    actual_labels = [classify_congestion(w) for w in actual_waits]
    predicted_labels = [classify_congestion(w) for w in predicted_waits]

    # Initialize confusion matrix: matrix[actual][predicted]
    conf_matrix = {c_act: {c_pred: 0 for c_pred in classes} for c_act in classes}
    for act, pred in zip(actual_labels, predicted_labels):
        if act in conf_matrix and pred in conf_matrix[act]:
            conf_matrix[act][pred] += 1

    per_class = {}
    true_counts = {}
    pred_counts = {}
    active_classes = []
    classes_in_truth = []

    for c in classes:
        tp = conf_matrix[c][c]
        fp = sum(conf_matrix[other][c] for other in classes if other != c)
        fn = sum(conf_matrix[c][other] for other in classes if other != c)

        true_count = tp + fn
        pred_count = tp + fp

        true_counts[c] = true_count
        pred_counts[c] = pred_count

        precision = tp / float(pred_count) if pred_count > 0 else 0.0
        recall = tp / float(true_count) if true_count > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        per_class[c] = {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_count": true_count,
            "pred_count": pred_count,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

        if true_count > 0:
            classes_in_truth.append(c)
        if true_count > 0 or pred_count > 0:
            active_classes.append(c)

    # Defensible Macro-F1 calculation:
    # 1. Macro-F1 across active classes (classes present in ground truth or predictions)
    #    Absent classes (true_count=0 and pred_count=0) receive F1=0.0 and are excluded
    #    from active-class denominator rather than receiving an inflated 1.0.
    if active_classes:
        macro_f1 = sum(per_class[c]["f1"] for c in active_classes) / float(len(active_classes))
    else:
        macro_f1 = 0.0

    # 2. Fixed 3-class Macro-F1 across all 3 predefined classes (sklearn zero_division=0)
    macro_f1_3class = sum(per_class[c]["f1"] for c in classes) / float(len(classes))

    return {
        "macro_f1": round(macro_f1, 4),
        "macro_f1_3class": round(macro_f1_3class, 4),
        "active_classes": active_classes,
        "classes_in_ground_truth": classes_in_truth,
        "true_counts": true_counts,
        "predicted_counts": pred_counts,
        "per_class": per_class,
        "confusion_matrix": conf_matrix,
        "sample_count": len(actual_waits),
        "absent_class_handling": "Classes absent in ground truth and predictions receive F1=0.0 and are excluded from active-class Macro-F1 to prevent artificial inflation."
    }


# =====================================================================
# 2. Rolling-Origin Backtesting Evaluator
# =====================================================================

class RollingOriginForecastEvaluator:
    """
    Executes rolling-origin forecast evaluations with strictly separated random streams.

    At each rolling origin:
    1. The live simulator state is cloned for the forecast.
    2. A forecast is generated using Phase 4 Monte Carlo lookahead with its own RNG seed.
    3. An independent evaluation trajectory is cloned from the SAME initial state but stepped
       using an independent RNG seed (and optional model-mismatch parameters).
    4. Predictions at horizons (15m, 30m, 60m) are compared against the independent future states.
    5. Zero mutation occurs on the primary live simulator.
    """

    def __init__(
        self,
        horizons: Tuple[int, ...] = (15, 30, 60),
        forecast_trials: int = 40,
        master_seed: int = 42,
    ):
        self.horizons = tuple(sorted(horizons))
        self.max_horizon = self.horizons[-1] if self.horizons else 60
        self.forecast_trials = forecast_trials
        self.master_seed = master_seed
        self.rng = random.Random(master_seed)

    def evaluate_scenario(
        self,
        base_simulator: MultiDispenserQueueSimulator,
        warmup_steps: int = 15,
        num_origins: int = 100,
        replications: int = 5,
        origin_interval: int = 10,
        stress_modifier: Optional[Dict[str, Any]] = None,
        category_label: str = "SYNTHETIC — IN-MODEL EVALUATION",
        scenario_name: str = "In-Model Benchmark",
    ) -> Dict[str, Any]:
        """
        Executes rolling-origin evaluation across num_origins points partitioned over
        multiple independent simulation replications to avoid single-run auto-correlation.

        Parameters:
            base_simulator: Configured simulator template.
            warmup_steps: Minutes to run simulator before first evaluation origin of each replication.
            num_origins: Total number of rolling origins to test across all replications.
            replications: Number of independent simulation replications.
            origin_interval: Minutes elapsed between consecutive origins within a replication.
            stress_modifier: Optional overrides applied ONLY to the evaluation trajectory.
            category_label: 'SYNTHETIC — IN-MODEL EVALUATION' or 'SYNTHETIC — MODEL-MISMATCH STRESS EVALUATION'.
            scenario_name: Descriptive name for reporting.
        """
        replications = max(1, replications)
        origins_per_rep = math.ceil(num_origins / float(replications))

        # Storage for pooled paired observations per horizon: {h: {"actual_totals": [], ...}}
        horizon_data = {
            h: {
                "actual_totals": [],
                "pred_totals": [],
                "p10_totals": [],
                "p90_totals": [],
                "actual_waits": [],
                "pred_waits": [],
                "actual_waitings": [],
                "pred_waitings": [],
            }
            for h in self.horizons
        }

        # Storage for paired observations per replication to enable cluster-aware inference
        rep_horizon_data = [
            {
                h: {
                    "actual_totals": [],
                    "pred_totals": [],
                    "p10_totals": [],
                    "p90_totals": [],
                    "actual_waits": [],
                    "pred_waits": [],
                    "actual_waitings": [],
                    "pred_waitings": [],
                }
                for h in self.horizons
            }
            for _ in range(replications)
        ]

        origins_evaluated = 0

        for rep_idx in range(replications):
            if origins_evaluated >= num_origins:
                break

            # Set up independent live simulator for this replication
            live_seed = self.rng.randint(0, 2**31 - 1)
            live_sim = base_simulator.clone_state(seed=live_seed)

            # Warm up the simulator to reach representative initial queues
            for _ in range(warmup_steps):
                live_sim.step(duration_minutes=1.0)

            rep_target = min(origins_per_rep, num_origins - origins_evaluated)

            for origin_idx in range(rep_target):
                origins_evaluated += 1

                # 1. Generate Forecast from current origin state (isolated forecast RNG stream)
                forecast_seed = self.rng.randint(0, 2**31 - 1)
                forecast_result = live_sim.forecast(
                    horizons=self.horizons,
                    trials=self.forecast_trials,
                    seed=forecast_seed,
                )

                # 2. Setup Evaluation Trajectory starting from IDENTICAL origin state
                eval_seed = self.rng.randint(0, 2**31 - 1)
                eval_sim = live_sim.clone_state(seed=eval_seed)

                # Apply stress modifier ONLY to the evaluation trajectory if requested
                if stress_modifier:
                    if "arrival_rate_multiplier" in stress_modifier:
                        eval_sim.arrival_rate *= float(stress_modifier["arrival_rate_multiplier"])
                    if "balking_threshold" in stress_modifier:
                        eval_sim.balking_threshold = int(stress_modifier["balking_threshold"])
                    if "service_time_multiplier" in stress_modifier:
                        mult = float(stress_modifier["service_time_multiplier"])
                        for d in eval_sim.dispensers:
                            d.remaining_service_time *= mult
                            if "duration_seconds" in d.service_params:
                                d.service_params["duration_seconds"] *= mult
                            if "mean_service_seconds" in d.service_params:
                                d.service_params["mean_service_seconds"] *= mult
                            if "loc" in d.service_params:
                                d.service_params["loc"] *= mult
                                d.service_params["scale"] *= mult
                            if "low" in d.service_params:
                                d.service_params["low"] *= mult
                                d.service_params["mode"] *= mult
                                d.service_params["high"] *= mult

                # 3. Independently advance evaluation trajectory up to max_horizon minutes
                for minute in range(1, self.max_horizon + 1):
                    eval_sim.step(duration_minutes=1.0)

                    if minute in self.horizons:
                        # Ground-truth evaluation outcomes at horizon minute
                        y_actual = eval_sim.total_vehicles
                        w_actual = eval_sim.estimate_incoming_waiting_time_minutes()
                        waiting_actual = eval_sim.waiting_queue_length

                        # Forecast predictions for this horizon
                        fc_h = forecast_result[f"{minute}m"]
                        y_pred = fc_h["expected_queue"]
                        p10 = fc_h["queue_range"][0]
                        p90 = fc_h["queue_range"][1]
                        w_pred = fc_h["expected_wait_minutes"]
                        waiting_pred = fc_h.get("expected_waiting_queue", y_pred)

                        # Store paired observations in both pooled and replication storage
                        for store in [horizon_data[minute], rep_horizon_data[rep_idx][minute]]:
                            store["actual_totals"].append(y_actual)
                            store["pred_totals"].append(y_pred)
                            store["p10_totals"].append(p10)
                            store["p90_totals"].append(p90)
                            store["actual_waits"].append(w_actual)
                            store["pred_waits"].append(w_pred)
                            store["actual_waitings"].append(waiting_actual)
                            store["pred_waitings"].append(waiting_pred)

                # Advance live simulator to next rolling origin
                for _ in range(origin_interval):
                    live_sim.step(duration_minutes=1.0)

        # Compute metrics across each horizon
        horizon_metrics = {}
        for h in self.horizons:
            data = horizon_data[h]
            n_samples = len(data["actual_totals"])

            # 1. Pooled sample statistics
            queue_abs_errors = [abs(a - p) for a, p in zip(data["actual_totals"], data["pred_totals"])]
            wait_abs_errors = [abs(a - p) for a, p in zip(data["actual_waits"], data["pred_waits"])]
            interval_widths = [(high - low) for low, high in zip(data["p10_totals"], data["p90_totals"])]
            waiting_q_abs_errors = [abs(a - p) for a, p in zip(data["actual_waitings"], data["pred_waitings"])]

            queue_mae = calculate_mae(data["actual_totals"], data["pred_totals"])
            queue_mae_std = calculate_sample_std(queue_abs_errors)
            queue_mae_ci = calculate_confidence_interval(queue_abs_errors)

            queue_rmse = calculate_rmse(data["actual_totals"], data["pred_totals"])

            wait_mae = calculate_mae(data["actual_waits"], data["pred_waits"])
            wait_mae_std = calculate_sample_std(wait_abs_errors)
            wait_mae_ci = calculate_confidence_interval(wait_abs_errors)

            picp_stats = calculate_picp_detailed(data["actual_totals"], data["p10_totals"], data["p90_totals"])

            mpiw = calculate_mpiw(data["p10_totals"], data["p90_totals"])
            mpiw_std = calculate_sample_std(interval_widths)
            mpiw_ci = calculate_confidence_interval(interval_widths)

            congestion_eval = calculate_congestion_f1(data["actual_waits"], data["pred_waits"])

            waiting_queue_mae = calculate_mae(data["actual_waitings"], data["pred_waitings"])
            waiting_queue_mae_std = calculate_sample_std(waiting_q_abs_errors)
            waiting_queue_mae_ci = calculate_confidence_interval(waiting_q_abs_errors)
            waiting_queue_rmse = calculate_rmse(data["actual_waitings"], data["pred_waitings"])

            # 2. Replication-level statistics (accounts for intra-replication temporal correlation)
            rep_mae_list = []
            rep_rmse_list = []
            rep_wait_mae_list = []
            rep_picp_list = []
            rep_picp_hits = []
            rep_picp_totals = []
            rep_mpiw_list = []
            rep_macro_f1_list = []

            for r in range(replications):
                r_data = rep_horizon_data[r][h]
                if len(r_data["actual_totals"]) > 0:
                    r_mae = calculate_mae(r_data["actual_totals"], r_data["pred_totals"])
                    r_rmse = calculate_rmse(r_data["actual_totals"], r_data["pred_totals"])
                    r_wait = calculate_mae(r_data["actual_waits"], r_data["pred_waits"])
                    r_hits = sum(1 for y, low, high in zip(r_data["actual_totals"], r_data["p10_totals"], r_data["p90_totals"]) if low <= y <= high)
                    r_tot = len(r_data["actual_totals"])
                    r_picp = r_hits / float(r_tot) if r_tot > 0 else 0.0
                    r_mpiw = calculate_mpiw(r_data["p10_totals"], r_data["p90_totals"])
                    r_f1 = calculate_congestion_f1(r_data["actual_waits"], r_data["pred_waits"])["macro_f1"]

                    rep_mae_list.append(r_mae)
                    rep_rmse_list.append(r_rmse)
                    rep_wait_mae_list.append(r_wait)
                    rep_picp_list.append(r_picp)
                    rep_picp_hits.append(r_hits)
                    rep_picp_totals.append(r_tot)
                    rep_mpiw_list.append(r_mpiw)
                    rep_macro_f1_list.append(r_f1)

            clustered_mae = calculate_clustered_ci(rep_mae_list)
            clustered_rmse = calculate_clustered_ci(rep_rmse_list)
            clustered_wait = calculate_clustered_ci(rep_wait_mae_list)
            bounded_picp = calculate_bounded_clustered_picp(
                rep_hits=rep_picp_hits,
                rep_totals=rep_picp_totals,
                df=max(1, len(rep_picp_hits) - 1),
            )
            clustered_mpiw = calculate_clustered_ci(rep_mpiw_list)
            clustered_macro_f1 = calculate_clustered_ci(rep_macro_f1_list)

            horizon_metrics[f"{h}m"] = {
                "sample_count": n_samples,
                "replications_count": len(rep_mae_list),
                "queue_mae": round(queue_mae, 2),
                "queue_mae_std_dev": round(queue_mae_std, 2),
                "queue_mae_pooled_ci_95": [round(queue_mae_ci[0], 2), round(queue_mae_ci[1], 2)],
                "queue_mae_clustered_mean": round(clustered_mae["mean"], 2),
                "queue_mae_clustered_ci_95": [round(clustered_mae["ci_95"][0], 2), round(clustered_mae["ci_95"][1], 2)],
                "queue_mae_rep_values": [round(v, 2) for v in clustered_mae["replication_values"]],
                "queue_rmse": round(queue_rmse, 2),
                "queue_rmse_clustered_mean": round(clustered_rmse["mean"], 2),
                "queue_rmse_clustered_ci_95": [round(clustered_rmse["ci_95"][0], 2), round(clustered_rmse["ci_95"][1], 2)],
                "queue_rmse_rep_values": [round(v, 2) for v in clustered_rmse["replication_values"]],
                "waiting_time_mae_minutes": round(wait_mae, 2),
                "waiting_time_mae_std_dev": round(wait_mae_std, 2),
                "waiting_time_mae_pooled_ci_95": [round(wait_mae_ci[0], 2), round(wait_mae_ci[1], 2)],
                "waiting_time_mae_clustered_mean": round(clustered_wait["mean"], 2),
                "waiting_time_mae_clustered_ci_95": [round(clustered_wait["ci_95"][0], 2), round(clustered_wait["ci_95"][1], 2)],
                "waiting_time_mae_rep_values": [round(v, 2) for v in clustered_wait["replication_values"]],
                "picp_80_nominal": picp_stats["picp"],
                "picp_hits": picp_stats["hits"],
                "picp_total": picp_stats["total"],
                "picp_fraction": picp_stats["ratio"],
                "picp_percentage": picp_stats["percentage"],
                "picp_pooled_wilson_ci_95": picp_stats["ci_95"],
                "picp_clustered_mean": bounded_picp["picp"],
                "picp_clustered_ci_95": bounded_picp["ci_95"],
                "picp_rep_coverages": bounded_picp["rep_coverages"],
                "picp_deff": bounded_picp["deff"],
                "picp_n_eff": bounded_picp["n_eff"],
                "picp_method": bounded_picp["method"],
                "mpiw_vehicles": round(mpiw, 2),
                "mpiw_std_dev": round(mpiw_std, 2),
                "mpiw_pooled_ci_95": [round(mpiw_ci[0], 2), round(mpiw_ci[1], 2)],
                "mpiw_clustered_mean": round(clustered_mpiw["mean"], 2),
                "mpiw_clustered_ci_95": [round(clustered_mpiw["ci_95"][0], 2), round(clustered_mpiw["ci_95"][1], 2)],
                "mpiw_rep_values": [round(v, 2) for v in clustered_mpiw["replication_values"]],
                "congestion_macro_f1": congestion_eval["macro_f1"],
                "congestion_macro_f1_3class": congestion_eval["macro_f1_3class"],
                "congestion_macro_f1_clustered_mean": round(clustered_macro_f1["mean"], 4),
                "congestion_macro_f1_clustered_ci_95": [round(clustered_macro_f1["ci_95"][0], 4), round(clustered_macro_f1["ci_95"][1], 4)],
                "congestion_macro_f1_rep_values": [round(v, 4) for v in clustered_macro_f1["replication_values"]],
                "congestion_details": congestion_eval["per_class"],
                "active_classes": congestion_eval["active_classes"],
                "classes_in_ground_truth": congestion_eval["classes_in_ground_truth"],
                "true_counts": congestion_eval["true_counts"],
                "predicted_counts": congestion_eval["predicted_counts"],
                "confusion_matrix": congestion_eval["confusion_matrix"],
                "absent_class_handling": congestion_eval["absent_class_handling"],
                "auxiliary_waiting_queue_mae": round(waiting_queue_mae, 2),
                "auxiliary_waiting_queue_mae_std_dev": round(waiting_queue_mae_std, 2),
                "auxiliary_waiting_queue_mae_ci_95": [round(waiting_queue_mae_ci[0], 2), round(waiting_queue_mae_ci[1], 2)],
                "auxiliary_waiting_queue_rmse": round(waiting_queue_rmse, 2),
            }

        return {
            "category": category_label,
            "scenario_name": scenario_name,
            "origins_evaluated": origins_evaluated,
            "replications": replications,
            "forecast_trials_per_origin": self.forecast_trials,
            "dispenser_count": base_simulator.num_dispensers,
            "demand_profile": base_simulator.demand_profile,
            "base_arrival_rate": base_simulator.arrival_rate,
            "stress_modifier": stress_modifier,
            "temporal_dependence_audit": {
                "independent_replications": replications,
                "origins_per_replication": origins_per_rep,
                "shared_simulated_history_within_replication": True,
                "overlapping_forecast_horizons": "60m forecast horizon exceeds 10m origin interval; consecutive origins within replication share state transitions.",
                "clustering_method": "Replication-level estimates are mutually independent. Student-t cluster CIs (df=R-1, t_crit=2.7764 for R=5) account for intra-replication temporal autocorrelation."
            },
            "disclaimer": EVALUATION_DISCLAIMER,
            "real_world_validation_status": REAL_WORLD_VALIDATION_STATUS,
            "horizons": horizon_metrics,
        }


# =====================================================================
# 3. Monte Carlo Trial-Count Sensitivity Analysis
# =====================================================================

def run_trial_count_sensitivity_analysis(
    trial_counts: Tuple[int, ...] = (30, 100, 200, 500),
    num_runs: int = 5,
    master_seed: int = 42,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates whether the Monte Carlo trial count is sufficient for stable P10, P90,
    interval widths, expected queue, and expected waiting times across candidate trial counts.
    Executes multiple independent forecast runs per trial count across 4 representative initial states:
      1. Low Demand (3 dispensers, λ=0.45)
      2. Moderate Demand (2 dispensers, λ=0.75)
      3. Heavy Demand (4 dispensers, λ=1.20)
      4. Stress Surge (2 dispensers, λ=0.98, +40% surge)
    """
    import time
    rng = random.Random(master_seed)
    horizons = (15, 30, 60)

    states_to_test = [
        {
            "id": "low_demand_3d",
            "name": "Low Demand (3 Dispensers, λ=0.45)",
            "sim_factory": lambda: MultiDispenserQueueSimulator(num_dispensers=3, arrival_rate=0.45, demand_profile="LOW", seed=101),
            "warmup_steps": 25,
        },
        {
            "id": "moderate_demand_2d",
            "name": "Moderate Demand (2 Dispensers, λ=0.75)",
            "sim_factory": lambda: MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.75, demand_profile="MODERATE", seed=102),
            "warmup_steps": 25,
        },
        {
            "id": "heavy_demand_4d",
            "name": "Heavy Demand (4 Dispensers, λ=1.20)",
            "sim_factory": lambda: MultiDispenserQueueSimulator(num_dispensers=4, arrival_rate=1.20, demand_profile="HEAVY", seed=103),
            "warmup_steps": 25,
        },
        {
            "id": "stress_surge_2d",
            "name": "Stress Surge (2 Dispensers, λ=0.98 [+40%])",
            "sim_factory": lambda: MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.98, demand_profile="MODERATE", seed=104),
            "warmup_steps": 25,
        },
    ]

    sensitivity_results = {
        "analysis_title": "Phase 5.3 Multi-State Monte Carlo Trial-Count Sensitivity Analysis",
        "trial_counts": list(trial_counts),
        "independent_seed_runs_per_trial_count": num_runs,
        "horizons": list(horizons),
        "scenarios": {},
        "results_by_trial_count": {},  # Backward compatibility alias (Moderate Demand)
    }

    print("\n" + "=" * 80)
    print("NoQueue — Phase 5.3: Multi-State Monte Carlo Trial-Count Sensitivity Analysis")
    print("=" * 80)
    print(f"Candidate Trial Counts: {trial_counts} | Runs/Count: {num_runs} | States: {len(states_to_test)}")

    for state_cfg in states_to_test:
        sid = state_cfg["id"]
        sname = state_cfg["name"]
        sim = state_cfg["sim_factory"]()
        for _ in range(state_cfg["warmup_steps"]):
            sim.step(1.0)

        initial_state = {
            "num_dispensers": sim.num_dispensers,
            "total_vehicles": sim.total_vehicles,
            "waiting_queue": sim.waiting_queue_length,
            "arrival_rate": sim.arrival_rate,
        }

        print(f"\n--- State: {sname} (Total Q: {initial_state['total_vehicles']}, Waiting: {initial_state['waiting_queue']}) ---")
        scenario_results = {
            "scenario_id": sid,
            "scenario_name": sname,
            "representative_state": initial_state,
            "results_by_trial_count": {},
        }

        for tc in trial_counts:
            t0 = time.time()
            runs = []
            for run_idx in range(num_runs):
                f_seed = rng.randint(0, 2**31 - 1)
                fc = sim.forecast(horizons=horizons, trials=tc, seed=f_seed)
                runs.append(fc)
            elapsed = time.time() - t0

            tc_metrics = {
                "trials": tc,
                "total_elapsed_seconds": round(elapsed, 3),
                "seconds_per_forecast": round(elapsed / float(num_runs), 4),
                "horizons": {},
            }

            for h in horizons:
                h_key = f"{h}m"
                exp_q = [r[h_key]["expected_queue"] for r in runs]
                p10_q = [r[h_key]["queue_range"][0] for r in runs]
                p90_q = [r[h_key]["queue_range"][1] for r in runs]
                w_q = [r[h_key]["queue_range"][1] - r[h_key]["queue_range"][0] for r in runs]
                exp_w = [r[h_key]["expected_wait_minutes"] for r in runs]

                tc_metrics["horizons"][h_key] = {
                    "expected_queue_mean": round(sum(exp_q) / len(exp_q), 2),
                    "expected_queue_std": round(calculate_sample_std(exp_q), 2),
                    "p10_mean": round(sum(p10_q) / len(p10_q), 2),
                    "p10_std": round(calculate_sample_std(p10_q), 2),
                    "p90_mean": round(sum(p90_q) / len(p90_q), 2),
                    "p90_std": round(calculate_sample_std(p90_q), 2),
                    "mpiw_mean": round(sum(w_q) / len(w_q), 2),
                    "mpiw_std": round(calculate_sample_std(w_q), 2),
                    "expected_wait_minutes_mean": round(sum(exp_w) / len(exp_w), 2),
                    "expected_wait_minutes_std": round(calculate_sample_std(exp_w), 2),
                }

            m60 = tc_metrics["horizons"]["60m"]
            print(
                f"  Trials {tc:3d} ({tc_metrics['seconds_per_forecast']:.3f}s/fc) -> "
                f"60m ExpQ={m60['expected_queue_mean']:.1f} (±{m60['expected_queue_std']:.2f}) | "
                f"P10-P90=[{m60['p10_mean']:.1f}, {m60['p90_mean']:.1f}] (Width={m60['mpiw_mean']:.1f} ±{m60['mpiw_std']:.2f}) | "
                f"ExpWait={m60['expected_wait_minutes_mean']:.1f}m (±{m60['expected_wait_minutes_std']:.2f}m)"
            )

            scenario_results["results_by_trial_count"][str(tc)] = tc_metrics

        sensitivity_results["scenarios"][sid] = scenario_results

        # Set backward-compatibility alias for moderate demand
        if sid == "moderate_demand_2d":
            sensitivity_results["results_by_trial_count"] = scenario_results["results_by_trial_count"]
            sensitivity_results["representative_state"] = initial_state

    # Save results
    target_dir = output_dir or os.path.join(CURRENT_DIR, "evaluation_results")
    os.makedirs(target_dir, exist_ok=True)
    out_path = os.path.join(target_dir, "monte_carlo_sensitivity_results.json")
    with open(out_path, "w") as f:
        json.dump(sensitivity_results, f, indent=2)
    print(f"\nMulti-state sensitivity analysis saved to: {out_path}\n" + "=" * 80)

    return sensitivity_results


# =====================================================================
# 4. Main Benchmark Execution Workflow
# =====================================================================

def run_phase5_benchmark_suite(
    trials: int = 100,
    origins: int = 100,
    replications: int = 5,
    master_seed: int = 42,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the complete Phase 5 evaluation benchmark suite:
    - 4 In-Model Synthetic Scenarios
    - 4 Model-Mismatch Stress Scenarios
    Evaluates at least 100 evaluation origins partitioned over R=5 independent replications.
    Computes both pooled sample metrics and replication-level clustered confidence intervals.
    Saves results to a structured JSON report and returns summary.
    """
    evaluator = RollingOriginForecastEvaluator(
        horizons=(15, 30, 60),
        forecast_trials=trials,
        master_seed=master_seed,
    )

    all_results = {
        "benchmark_metadata": {
            "evaluation_title": "NoQueue Phase 5.2 Multi-Dispenser Forecast Statistical Evaluation",
            "master_seed": master_seed,
            "forecast_trials_per_origin": trials,
            "rolling_origins_per_scenario": origins,
            "simulation_replications_per_scenario": replications,
            "disclaimer": EVALUATION_DISCLAIMER,
            "real_world_validation_status": REAL_WORLD_VALIDATION_STATUS,
        },
        "in_model_scenarios": [],
        "stress_scenarios": [],
    }

    print("\n" + "=" * 78)
    print("NoQueue — Phase 5.2: Multi-Dispenser Forecast Statistical Evaluation")
    print("=" * 78)
    print(f"Master Seed: {master_seed} | Trials/Origin: {trials} | Origins/Scenario: {origins} | Replications: {replications}")
    print(f"Notice: {EVALUATION_DISCLAIMER}\n")

    # -----------------------------------------------------------------
    # A. In-Model Synthetic Scenarios
    # -----------------------------------------------------------------
    in_model_configs = [
        {
            "name": "2-Dispenser MODERATE Demand (Exponential Service)",
            "sim": MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.75, demand_profile="MODERATE", seed=101),
        },
        {
            "name": "2-Dispenser Research Benchmark HEAVY (Line 1 Beta, Line 2 Triangular)",
            "sim": create_research_benchmark_simulator(seed=202, arrival_rate=0.503, demand_profile="HEAVY"),
        },
        {
            "name": "3-Dispenser LOW Demand (Calm Off-Peak)",
            "sim": MultiDispenserQueueSimulator(num_dispensers=3, arrival_rate=0.45, demand_profile="LOW", seed=303),
        },
        {
            "name": "4-Dispenser HEAVY Demand (High-Capacity Highway Station)",
            "sim": MultiDispenserQueueSimulator(num_dispensers=4, arrival_rate=1.20, demand_profile="HEAVY", seed=404),
        },
    ]

    print("--- [CATEGORY A: SYNTHETIC — IN-MODEL EVALUATION] ---")
    for cfg in in_model_configs:
        res = evaluator.evaluate_scenario(
            base_simulator=cfg["sim"],
            warmup_steps=15,
            num_origins=origins,
            replications=replications,
            origin_interval=10,
            stress_modifier=None,
            category_label="SYNTHETIC — IN-MODEL EVALUATION",
            scenario_name=cfg["name"],
        )
        all_results["in_model_scenarios"].append(res)
        print(f"\nScenario: {cfg['name']} (n={origins}, R={replications} independent replications)")
        for h, m in res["horizons"].items():
            print(
                f"  Horizon {h}: Queue MAE={m['queue_mae']} (clustered 95%CI={m['queue_mae_clustered_ci_95']}), RMSE={m['queue_rmse']} (clustered 95%CI={m['queue_rmse_clustered_ci_95']}) | "
                f"Wait MAE={m['waiting_time_mae_minutes']}m (clustered 95%CI={m['waiting_time_mae_clustered_ci_95']}) | "
                f"PICP={m['picp_fraction']} ({m['picp_percentage']}, clustered 95%CI={m['picp_clustered_ci_95']}, width={m['mpiw_vehicles']} veh) | "
                f"Macro-F1={m['congestion_macro_f1']} (active: {m['active_classes']})"
            )

    # -----------------------------------------------------------------
    # B. Model-Mismatch Stress Scenarios
    # -----------------------------------------------------------------
    stress_configs = [
        {
            "name": "Stress 1: Unanticipated Arrival Surge (+40% Evaluation Arrivals)",
            "sim": MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.70, demand_profile="MODERATE", seed=501),
            "modifier": {"arrival_rate_multiplier": 1.40},
        },
        {
            "name": "Stress 2: Cascade Pressure Drop (+35% Slower Dispenser Service)",
            "sim": MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.65, demand_profile="MODERATE", seed=601),
            "modifier": {"service_time_multiplier": 1.35},
        },
        {
            "name": "Stress 3: Sudden Off-Peak Drop (-40% Evaluation Arrivals)",
            "sim": MultiDispenserQueueSimulator(num_dispensers=3, arrival_rate=0.90, demand_profile="HEAVY", seed=701),
            "modifier": {"arrival_rate_multiplier": 0.60},
        },
        {
            "name": "Stress 4: Aggressive Roadway Balking (Balk Threshold Dropped 35 -> 15)",
            "sim": MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.85, demand_profile="HEAVY", balking_threshold=35, seed=801),
            "modifier": {"balking_threshold": 15},
        },
    ]

    print("\n--- [CATEGORY B: SYNTHETIC — MODEL-MISMATCH STRESS EVALUATION] ---")
    for cfg in stress_configs:
        res = evaluator.evaluate_scenario(
            base_simulator=cfg["sim"],
            warmup_steps=15,
            num_origins=origins,
            replications=replications,
            origin_interval=10,
            stress_modifier=cfg["modifier"],
            category_label="SYNTHETIC — MODEL-MISMATCH STRESS EVALUATION",
            scenario_name=cfg["name"],
        )
        all_results["stress_scenarios"].append(res)
        print(f"\nScenario: {cfg['name']} (n={origins}, R={replications} independent replications)")
        for h, m in res["horizons"].items():
            print(
                f"  Horizon {h}: Queue MAE={m['queue_mae']} (clustered 95%CI={m['queue_mae_clustered_ci_95']}), RMSE={m['queue_rmse']} (clustered 95%CI={m['queue_rmse_clustered_ci_95']}) | "
                f"Wait MAE={m['waiting_time_mae_minutes']}m (clustered 95%CI={m['waiting_time_mae_clustered_ci_95']}) | "
                f"PICP={m['picp_fraction']} ({m['picp_percentage']}, clustered 95%CI={m['picp_clustered_ci_95']}, width={m['mpiw_vehicles']} veh) | "
                f"Macro-F1={m['congestion_macro_f1']} (active: {m['active_classes']})"
            )

    # Save to evaluation_results directory
    target_dir = output_dir or os.path.join(CURRENT_DIR, "evaluation_results")
    os.makedirs(target_dir, exist_ok=True)
    report_path = os.path.join(target_dir, "phase5_benchmark_results.json")

    with open(report_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print("\n" + "=" * 78)
    print(f"Results saved to: {report_path}")
    print(f"Real-World Status: {REAL_WORLD_VALIDATION_STATUS}")
    print("=" * 78 + "\n")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NoQueue Phase 5 Forecast Evaluation Benchmark")
    parser.add_argument("--trials", type=int, default=100, help="Monte Carlo forecast trials per origin")
    parser.add_argument("--origins", type=int, default=100, help="Number of rolling origins per scenario")
    parser.add_argument("--replications", type=int, default=5, help="Number of independent simulation replications")
    parser.add_argument("--seed", type=int, default=42, help="Master evaluation seed")
    parser.add_argument("--run-sensitivity", action="store_true", help="Run Monte Carlo trial sensitivity analysis")
    args = parser.parse_args()

    if args.run_sensitivity:
        run_trial_count_sensitivity_analysis(master_seed=args.seed)

    run_phase5_benchmark_suite(
        trials=args.trials,
        origins=args.origins,
        replications=args.replications,
        master_seed=args.seed
    )

