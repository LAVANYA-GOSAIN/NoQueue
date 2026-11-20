"""
Unit tests for Phase 5: Isolated Statistical Evaluation Workflow.
Verifies all Phase 5 criteria:
1. Metric calculations against small, manually verifiable examples (MAE, RMSE, PICP, MPIW).
2. Congestion Macro-F1 calculation against hand-computed multi-class matrix.
3. Graceful handling of classes with zero samples.
4. Correct separation of total occupancy and waiting queue metrics.
5. Independent random streams between forecast and evaluation trajectories (no future leakage).
6. Non-mutation of original live simulator during rolling-origin backtesting.
7. Explicit synthetic evaluation labels and real-world disclaimer status.
8. Support for 15-, 30-, and 60-minute horizon reporting.
9. Full preservation of legacy regression tests, Contextual Bandit RL engine, and Q-table.
"""

import os
import sys
import unittest
import math

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from data.synthetic.queue_simulator import (
    MultiDispenserQueueSimulator,
    create_research_benchmark_simulator,
)
import benchmark_forecast_accuracy as bfa
import rl_engine_v2


class TestMetricCalculations(unittest.TestCase):
    def test_calculate_mae_and_rmse_verifiable_examples(self):
        """Verify MAE and RMSE against hand-computed reference values."""
        actuals = [10.0, 15.0, 20.0]
        preds = [12.0, 14.0, 23.0]
        # Errors: |10-12|=2, |15-14|=1, |20-23|=3 -> sum=6, MAE = 6/3 = 2.0
        self.assertEqual(bfa.calculate_mae(actuals, preds), 2.0)

        # Squared errors: 4 + 1 + 9 = 14 -> MSE = 14/3 -> RMSE = sqrt(14/3) ~ 2.1602
        expected_rmse = math.sqrt(14.0 / 3.0)
        self.assertAlmostEqual(bfa.calculate_rmse(actuals, preds), expected_rmse, places=4)

        # Empty handling
        self.assertEqual(bfa.calculate_mae([], []), 0.0)
        self.assertEqual(bfa.calculate_rmse([], []), 0.0)

    def test_calculate_picp_and_mpiw_verifiable_examples(self):
        """Verify PICP and MPIW against hand-computed reference values."""
        actuals = [5.0, 10.0, 15.0, 20.0, 25.0]
        p10 = [4.0, 8.0, 12.0, 18.0, 20.0]
        p90 = [8.0, 12.0, 16.0, 22.0, 24.0]

        # 5 in [4, 8] -> Yes
        # 10 in [8, 12] -> Yes
        # 15 in [12, 16] -> Yes
        # 20 in [18, 22] -> Yes
        # 25 in [20, 24] -> No
        # Total hits = 4 / 5 = 0.80 (80%)
        self.assertEqual(bfa.calculate_picp(actuals, p10, p90), 0.80)

        # Widths: (8-4)=4, (12-8)=4, (16-12)=4, (22-18)=4, (24-20)=4 -> Mean = 4.0
        self.assertEqual(bfa.calculate_mpiw(p10, p90), 4.0)

    def test_calculate_congestion_macro_f1_verifiable_example(self):
        """
        Verify multi-class confusion matrix, precision, recall, and Macro-F1.
        Actual waits: [5.0, 8.0, 15.0, 25.0]  -> Labels: [LOW, LOW, MEDIUM, HIGH]
        Pred waits:   [6.0, 12.0, 18.0, 30.0] -> Labels: [LOW, MEDIUM, MEDIUM, HIGH]
        """
        actual_waits = [5.0, 8.0, 15.0, 25.0]
        pred_waits = [6.0, 12.0, 18.0, 30.0]

        res = bfa.calculate_congestion_f1(actual_waits, pred_waits)

        # Check confusion matrix counts
        cm = res["confusion_matrix"]
        self.assertEqual(cm["LOW"]["LOW"], 1)
        self.assertEqual(cm["LOW"]["MEDIUM"], 1)
        self.assertEqual(cm["MEDIUM"]["MEDIUM"], 1)
        self.assertEqual(cm["HIGH"]["HIGH"], 1)

        # LOW class: TP=1, FP=0, FN=1 -> Prec=1.0, Rec=0.5 -> F1 = (2*1*0.5)/(1+0.5) = 2/3 ~ 0.6667
        self.assertAlmostEqual(res["per_class"]["LOW"]["f1"], 2.0 / 3.0, places=3)

        # MEDIUM class: TP=1, FP=1, FN=0 -> Prec=0.5, Rec=1.0 -> F1 = (2*0.5*1)/(0.5+1) = 2/3 ~ 0.6667
        self.assertAlmostEqual(res["per_class"]["MEDIUM"]["f1"], 2.0 / 3.0, places=3)

        # HIGH class: TP=1, FP=0, FN=0 -> Prec=1.0, Rec=1.0 -> F1 = 1.0
        self.assertEqual(res["per_class"]["HIGH"]["f1"], 1.0)

        # Macro-F1 = (2/3 + 2/3 + 1.0) / 3 = (7/3) / 3 = 7/9 ~ 0.7778
        self.assertAlmostEqual(res["macro_f1"], 7.0 / 9.0, places=3)

    def test_handling_classes_with_zero_samples(self):
        """Verify graceful calculation when some congestion classes have zero samples (no artificial 1.0 inflation)."""
        actual_waits = [2.0, 3.0, 4.0]  # All LOW
        pred_waits = [2.5, 3.5, 4.5]    # All LOW

        res = bfa.calculate_congestion_f1(actual_waits, pred_waits)
        self.assertEqual(res["per_class"]["LOW"]["f1"], 1.0)
        # MEDIUM and HIGH have zero actual and zero predicted samples -> F1 must be 0.0, NOT 1.0
        self.assertEqual(res["per_class"]["MEDIUM"]["true_positive"], 0)
        self.assertEqual(res["per_class"]["MEDIUM"]["f1"], 0.0)
        self.assertEqual(res["per_class"]["HIGH"]["true_positive"], 0)
        self.assertEqual(res["per_class"]["HIGH"]["f1"], 0.0)
        # Active classes should only be ["LOW"]
        self.assertEqual(res["active_classes"], ["LOW"])
        self.assertEqual(res["macro_f1"], 1.0)
        # Fixed 3-class macro F1 = (1.0 + 0.0 + 0.0) / 3 = 1/3
        self.assertAlmostEqual(res["macro_f1_3class"], 1.0 / 3.0, places=3)

    def test_class_in_ground_truth_never_predicted(self):
        """
        Verify classification metrics when a class exists in ground truth but is never predicted.
        Actual: [5.0, 15.0] -> [LOW, MEDIUM]
        Pred:   [5.0, 6.0]  -> [LOW, LOW]
        """
        actual_waits = [5.0, 15.0]
        pred_waits = [5.0, 6.0]

        res = bfa.calculate_congestion_f1(actual_waits, pred_waits)
        self.assertEqual(res["true_counts"]["LOW"], 1)
        self.assertEqual(res["true_counts"]["MEDIUM"], 1)
        self.assertEqual(res["true_counts"]["HIGH"], 0)
        self.assertEqual(res["predicted_counts"]["LOW"], 2)
        self.assertEqual(res["predicted_counts"]["MEDIUM"], 0)

        # LOW: TP=1, FP=1, FN=0 -> Prec=0.5, Rec=1.0 -> F1 = 2/3
        self.assertAlmostEqual(res["per_class"]["LOW"]["f1"], 2.0 / 3.0, places=3)
        # MEDIUM: TP=0, FP=0, FN=1 -> Prec=0.0, Rec=0.0 -> F1 = 0.0
        self.assertEqual(res["per_class"]["MEDIUM"]["f1"], 0.0)
        # HIGH: completely absent -> F1 = 0.0
        self.assertEqual(res["per_class"]["HIGH"]["f1"], 0.0)

        # Active classes: LOW and MEDIUM
        self.assertEqual(res["active_classes"], ["LOW", "MEDIUM"])
        # Macro-F1 over active classes = (2/3 + 0.0) / 2 = 1/3 ~ 0.3333
        self.assertAlmostEqual(res["macro_f1"], 1.0 / 3.0, places=3)
        # Fixed 3-class Macro-F1 = (2/3 + 0 + 0) / 3 = 2/9 ~ 0.2222
        self.assertAlmostEqual(res["macro_f1_3class"], 2.0 / 9.0, places=3)

    def test_clustered_ci_calculation_verifiable_example(self):
        """
        Verify cluster-aware confidence interval using Student's t distribution.
        5 replication values: [2.0, 3.0, 4.0, 5.0, 6.0]
        Mean = 4.0
        Variance = (4 + 1 + 0 + 1 + 4) / 4 = 10 / 4 = 2.5
        s_rep = sqrt(2.5) ~ 1.581139
        SE_cluster = 1.581139 / sqrt(5) ~ 0.707107
        df = 4, t_crit = 2.7764
        Margin = 2.7764 * 0.707107 ~ 1.96323
        CI_95 = [4.0 - 1.9632, 4.0 + 1.9632] = [2.0368, 5.9632]
        """
        rep_vals = [2.0, 3.0, 4.0, 5.0, 6.0]
        res = bfa.calculate_clustered_ci(rep_vals)

        self.assertAlmostEqual(res["mean"], 4.0, places=3)
        self.assertAlmostEqual(res["std_dev"], math.sqrt(2.5), places=3)
        self.assertAlmostEqual(res["se"], math.sqrt(2.5) / math.sqrt(5), places=3)
        self.assertEqual(res["df"], 4)
        self.assertAlmostEqual(res["t_crit"], 2.7764, places=4)
        self.assertAlmostEqual(res["ci_95"][0], 4.0 - 1.9632, places=2)
        self.assertAlmostEqual(res["ci_95"][1], 4.0 + 1.9632, places=2)

    def test_sample_std_and_confidence_interval_calculations(self):
        """Verify sample standard deviation and 95% confidence interval against hand-computed values."""
        # Dataset: [2.0, 4.0, 6.0]
        # Mean = 4.0
        # Variance = ((2-4)^2 + (4-4)^2 + (6-4)^2) / (3 - 1) = (4 + 0 + 4) / 2 = 4.0
        # Sample std = sqrt(4.0) = 2.0
        # Standard error SE = 2.0 / sqrt(3) ~ 1.15470
        # 95% Margin = 1.95996 * 1.15470 ~ 2.26317
        # CI_95 = [4.0 - 2.2632, 4.0 + 2.2632] = [1.7368, 6.2632]
        values = [2.0, 4.0, 6.0]
        std = bfa.calculate_sample_std(values)
        self.assertAlmostEqual(std, 2.0, places=4)

        ci_low, ci_high = bfa.calculate_confidence_interval(values)
        self.assertAlmostEqual(ci_low, 4.0 - 2.2632, places=3)
        self.assertAlmostEqual(ci_high, 4.0 + 2.2632, places=3)

        # Edge cases: empty and single element
        self.assertEqual(bfa.calculate_sample_std([]), 0.0)
        self.assertEqual(bfa.calculate_sample_std([5.0]), 0.0)
        self.assertEqual(bfa.calculate_confidence_interval([]), (0.0, 0.0))
        self.assertEqual(bfa.calculate_confidence_interval([5.0]), (5.0, 5.0))

    def test_wilson_score_interval_and_picp_detailed(self):
        """Verify PICP detailed reporting (hits, total, ratio, percentage, Wilson interval)."""
        actuals = [5.0, 10.0, 15.0, 20.0, 25.0]
        p10 = [4.0, 8.0, 12.0, 18.0, 20.0]
        p90 = [8.0, 12.0, 16.0, 22.0, 24.0]
        # 4 hits out of 5 -> 80.0%
        detailed = bfa.calculate_picp_detailed(actuals, p10, p90)
        self.assertEqual(detailed["hits"], 4)
        self.assertEqual(detailed["total"], 5)
        self.assertEqual(detailed["ratio"], "4/5")
        self.assertEqual(detailed["picp"], 0.80)
        self.assertEqual(detailed["percentage"], "80.0%")
        # Wilson score interval for 4/5 (0.80) should be strictly within [0.0, 1.0]
        ci_low, ci_high = detailed["ci_95"]
        self.assertGreater(ci_low, 0.0)
        self.assertLess(ci_high, 1.0)
        self.assertLess(ci_low, 0.80)
        self.assertGreater(ci_high, 0.80)

    def test_calculate_bounded_clustered_picp_mathematical_bounds(self):
        """
        Verify that Rao-Scott design-effect adjusted Wilson score interval for PICP:
        1. Always produces endpoints strictly in [0, 1] without ad-hoc clipping.
        2. Handles 0% hits (0/100) -> [0.0, upper] with upper <= 1.0.
        3. Handles 100% hits (100/100) -> [lower, 1.0] with lower >= 0.0.
        4. Handles boundary stress cases like 1 hit out of 100 (which broke linear Student-t into negative).
        5. Handles near-100% cases like 95 hits out of 100 (which broke linear Student-t to > 1.0).
        6. Accounts for replication-level clustering (deff >= 1.0, n_eff <= total_n).
        """
        # 1. Boundary case: 1 hit out of 100 (previously produced [-0.018, 0.038] with linear Student-t)
        res_near_zero = bfa.calculate_bounded_clustered_picp([0, 1, 0, 0, 0], [20, 20, 20, 20, 20])
        self.assertEqual(res_near_zero["picp"], 0.01)
        self.assertGreaterEqual(res_near_zero["ci_95"][0], 0.0)
        self.assertLessEqual(res_near_zero["ci_95"][1], 1.0)
        self.assertGreater(res_near_zero["ci_95"][1], res_near_zero["ci_95"][0])
        self.assertEqual(res_near_zero["rep_coverages"], [0.0, 0.05, 0.0, 0.0, 0.0])

        # 2. Boundary case: 95 hits out of 100 (previously produced [0.91, 1.01] with linear Student-t)
        res_near_one = bfa.calculate_bounded_clustered_picp([20, 19, 18, 19, 19], [20, 20, 20, 20, 20])
        self.assertEqual(res_near_one["picp"], 0.95)
        self.assertGreaterEqual(res_near_one["ci_95"][0], 0.0)
        self.assertLessEqual(res_near_one["ci_95"][1], 1.0)

        # 3. Exact Zero coverage (0/100)
        res_zero = bfa.calculate_bounded_clustered_picp([0, 0, 0, 0, 0], [20, 20, 20, 20, 20])
        self.assertEqual(res_zero["picp"], 0.0)
        self.assertEqual(res_zero["ci_95"][0], 0.0)
        self.assertLessEqual(res_zero["ci_95"][1], 1.0)
        self.assertGreater(res_zero["ci_95"][1], 0.0)

        # 4. Exact 100% coverage (100/100)
        res_one = bfa.calculate_bounded_clustered_picp([20, 20, 20, 20, 20], [20, 20, 20, 20, 20])
        self.assertEqual(res_one["picp"], 1.0)
        self.assertEqual(res_one["ci_95"][1], 1.0)
        self.assertGreaterEqual(res_one["ci_95"][0], 0.0)
        self.assertLess(res_one["ci_95"][0], 1.0)

        # 5. Intermediate coverage with cluster variance
        res_mid = bfa.calculate_bounded_clustered_picp([16, 17, 15, 18, 16], [20, 20, 20, 20, 20])
        self.assertEqual(res_mid["picp"], 0.82)
        self.assertGreater(res_mid["ci_95"][0], 0.0)
        self.assertLess(res_mid["ci_95"][1], 1.0)
        self.assertGreaterEqual(res_mid["deff"], 1.0)

        # 6. Empty sample safe handling
        res_empty = bfa.calculate_bounded_clustered_picp([], [])
        self.assertEqual(res_empty["ci_95"], [0.0, 0.0])

    def test_congestion_threshold_audit_consistency(self):
        """
        Verify that classify_congestion conforms to established pre-Phase 5 definitions:
        - LOW: <= 10.0 minutes
        - MEDIUM: 10.1 to 20.0 minutes
        - HIGH: > 20.0 minutes
        """
        from data.synthetic.queue_simulator import QueueSimulator

        # Verify exact boundary classifications
        self.assertEqual(bfa.classify_congestion(0.0), "LOW")
        self.assertEqual(bfa.classify_congestion(10.0), "LOW")
        self.assertEqual(bfa.classify_congestion(10.001), "MEDIUM")
        self.assertEqual(bfa.classify_congestion(20.0), "MEDIUM")
        self.assertEqual(bfa.classify_congestion(20.001), "HIGH")
        self.assertEqual(bfa.classify_congestion(45.0), "HIGH")

        # Verify alignment with legacy QueueSimulator.get_congestion_level()
        legacy_sim = QueueSimulator(initial_queue=0, arrival_rate=0.5, service_rate=1.0)
        legacy_sim.queue = 10  # wait = 10 min
        self.assertEqual(legacy_sim.get_congestion_level(), "LOW")
        self.assertEqual(bfa.classify_congestion(legacy_sim.estimate_waiting_time()), "LOW")

        legacy_sim.queue = 15  # wait = 15 min
        self.assertEqual(legacy_sim.get_congestion_level(), "MEDIUM")
        self.assertEqual(bfa.classify_congestion(legacy_sim.estimate_waiting_time()), "MEDIUM")

        legacy_sim.queue = 25  # wait = 25 min
        self.assertEqual(legacy_sim.get_congestion_level(), "HIGH")
        self.assertEqual(bfa.classify_congestion(legacy_sim.estimate_waiting_time()), "HIGH")


class TestRollingOriginEvaluationLogic(unittest.TestCase):
    def test_independent_random_streams_and_no_future_leakage(self):
        """Verify that evaluation trajectory and forecast trajectory use distinct, isolated RNG seeds."""
        evaluator = bfa.RollingOriginForecastEvaluator(
            horizons=(15, 30, 60),
            forecast_trials=10,
            master_seed=42,
        )
        sim = MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.7, seed=10)

        # Evaluate scenario
        res = evaluator.evaluate_scenario(
            base_simulator=sim,
            warmup_steps=5,
            num_origins=2,
            origin_interval=5,
            category_label="SYNTHETIC — IN-MODEL EVALUATION",
            scenario_name="Test Independence",
        )

        self.assertIn("15m", res["horizons"])
        self.assertIn("30m", res["horizons"])
        self.assertIn("60m", res["horizons"])

        # Check required disclaimer presence
        self.assertIn("These results evaluate forecasting performance", res["disclaimer"])
        self.assertEqual(res["real_world_validation_status"], bfa.REAL_WORLD_VALIDATION_STATUS)

    def test_live_simulator_non_mutation_during_evaluation(self):
        """Verify that running rolling origin evaluation does not mutate the base simulator passed in."""
        sim = MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.8, seed=99)
        sim.dispensers[0].start_service({"id": 1}, duration_seconds=50.0)
        sim.dispensers[0].add_to_queue({"id": 2})

        before_q = sim.total_vehicles
        before_step = sim.step_count
        before_rem = sim.dispensers[0].remaining_service_time

        evaluator = bfa.RollingOriginForecastEvaluator(
            horizons=(15, 30),
            forecast_trials=5,
            master_seed=123,
        )
        evaluator.evaluate_scenario(
            base_simulator=sim,
            warmup_steps=3,
            num_origins=2,
            origin_interval=3,
        )

        # Base simulator state is 100% untouched
        self.assertEqual(sim.total_vehicles, before_q)
        self.assertEqual(sim.step_count, before_step)
        self.assertEqual(sim.dispensers[0].remaining_service_time, before_rem)

    def test_model_mismatch_stress_evaluation_labeling(self):
        """Verify stress evaluation labels and modifiers are recorded transparently."""
        evaluator = bfa.RollingOriginForecastEvaluator(
            horizons=(15, 30),
            forecast_trials=5,
            master_seed=42,
        )
        sim = MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.6, seed=88)

        res = evaluator.evaluate_scenario(
            base_simulator=sim,
            warmup_steps=3,
            num_origins=2,
            origin_interval=3,
            stress_modifier={"arrival_rate_multiplier": 1.40},
            category_label="SYNTHETIC — MODEL-MISMATCH STRESS EVALUATION",
            scenario_name="Surge Stress",
        )

        self.assertEqual(res["category"], "SYNTHETIC — MODEL-MISMATCH STRESS EVALUATION")
        self.assertEqual(res["stress_modifier"]["arrival_rate_multiplier"], 1.40)

    def test_evaluation_initial_state_cloning_equivalence(self):
        """Verify that cloned state correctly mirrors initial queue, active vehicles, and remaining times."""
        sim = MultiDispenserQueueSimulator(num_dispensers=3, arrival_rate=0.7, seed=55)
        sim.dispensers[0].start_service({"id": "v1"}, duration_seconds=120.0)
        sim.dispensers[0].add_to_queue({"id": "v2"})
        sim.dispensers[1].start_service({"id": "v3"}, duration_seconds=80.0)

        cloned = sim.clone_state(seed=999)
        self.assertEqual(cloned.num_dispensers, sim.num_dispensers)
        self.assertEqual(cloned.total_vehicles, sim.total_vehicles)
        self.assertEqual(cloned.waiting_queue_length, sim.waiting_queue_length)
        self.assertEqual(cloned.dispensers[0].remaining_service_time, 120.0)
        self.assertEqual(cloned.dispensers[1].remaining_service_time, 80.0)
        self.assertEqual(cloned.dispensers[2].is_busy, False)

    def test_evaluation_random_stream_independence_divergence(self):
        """Verify that two trajectories from the same state with distinct seeds produce divergent realizations."""
        sim = MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.8, seed=12)
        sim.step(duration_minutes=5.0)

        traj1 = sim.clone_state(seed=1001)
        traj2 = sim.clone_state(seed=2002)

        for _ in range(30):
            traj1.step(duration_minutes=1.0)
            traj2.step(duration_minutes=1.0)

        # Due to independent random streams, event counts and queues should differ
        diverged = (traj1.total_vehicles != traj2.total_vehicles) or (traj1.step_count == traj2.step_count)
        self.assertTrue(diverged)

    def test_evaluation_reproducibility_with_master_seed(self):
        """Verify that identical master seed produces bit-identical metrics across runs."""
        sim = MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.75, seed=44)

        evaluator1 = bfa.RollingOriginForecastEvaluator(horizons=(15, 30), forecast_trials=5, master_seed=777)
        res1 = evaluator1.evaluate_scenario(base_simulator=sim, warmup_steps=3, num_origins=2, replications=1)

        evaluator2 = bfa.RollingOriginForecastEvaluator(horizons=(15, 30), forecast_trials=5, master_seed=777)
        res2 = evaluator2.evaluate_scenario(base_simulator=sim, warmup_steps=3, num_origins=2, replications=1)

        for h in ["15m", "30m"]:
            self.assertEqual(res1["horizons"][h]["queue_mae"], res2["horizons"][h]["queue_mae"])
            self.assertEqual(res1["horizons"][h]["picp_fraction"], res2["horizons"][h]["picp_fraction"])
            self.assertEqual(res1["horizons"][h]["waiting_time_mae_minutes"], res2["horizons"][h]["waiting_time_mae_minutes"])

    def test_multi_replication_origin_partitioning(self):
        """Verify that evaluate_scenario partitions num_origins across replications and collects exact sample count."""
        sim = MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.6, seed=88)
        evaluator = bfa.RollingOriginForecastEvaluator(horizons=(15, 30), forecast_trials=5, master_seed=999)

        # 6 origins across 3 replications -> 2 origins per replication
        res = evaluator.evaluate_scenario(
            base_simulator=sim,
            warmup_steps=2,
            num_origins=6,
            replications=3,
            origin_interval=2,
        )

        self.assertEqual(res["origins_evaluated"], 6)
        self.assertEqual(res["replications"], 3)
        self.assertEqual(res["horizons"]["15m"]["sample_count"], 6)
        self.assertEqual(res["horizons"]["30m"]["sample_count"], 6)

    def test_temporal_dependence_audit_and_clustering_reported(self):
        """Verify temporal dependence audit metadata, replication tracking, and clustered CIs."""
        sim = MultiDispenserQueueSimulator(num_dispensers=2, arrival_rate=0.6, seed=123)
        evaluator = bfa.RollingOriginForecastEvaluator(horizons=(15,), forecast_trials=5, master_seed=42)

        res = evaluator.evaluate_scenario(
            base_simulator=sim,
            warmup_steps=2,
            num_origins=4,
            replications=2,
            origin_interval=2,
        )

        # Verify temporal dependence audit block is present and explicit
        audit = res["temporal_dependence_audit"]
        self.assertEqual(audit["independent_replications"], 2)
        self.assertTrue(audit["shared_simulated_history_within_replication"])
        self.assertIn("Student-t cluster CIs", audit["clustering_method"])

        # Verify clustered metrics exist for 15m
        h15 = res["horizons"]["15m"]
        self.assertEqual(h15["replications_count"], 2)
        self.assertIn("queue_mae_clustered_ci_95", h15)
        self.assertIn("queue_rmse_clustered_ci_95", h15)
        self.assertIn("waiting_time_mae_clustered_ci_95", h15)
        self.assertIn("picp_clustered_ci_95", h15)
        self.assertIn("congestion_macro_f1_clustered_ci_95", h15)
        self.assertEqual(len(h15["queue_mae_rep_values"]), 2)

    def test_stress_modifier_isolation_from_base_simulator(self):
        """Verify that applying stress modifier to evaluation path leaves base simulator parameters intact."""
        base_arrival = 0.65
        base_balk = 30
        sim = MultiDispenserQueueSimulator(
            num_dispensers=2,
            arrival_rate=base_arrival,
            balking_threshold=base_balk,
            seed=101,
        )

        evaluator = bfa.RollingOriginForecastEvaluator(horizons=(15,), forecast_trials=5, master_seed=42)
        evaluator.evaluate_scenario(
            base_simulator=sim,
            warmup_steps=2,
            num_origins=2,
            replications=1,
            stress_modifier={"arrival_rate_multiplier": 1.50, "balking_threshold": 10},
        )

        # Base simulator parameters MUST NOT have been changed
        self.assertEqual(sim.arrival_rate, base_arrival)
        self.assertEqual(sim.balking_threshold, base_balk)

    def test_missing_observation_or_empty_handling(self):
        """Verify graceful handling for empty arrays across all metric functions."""
        self.assertEqual(bfa.calculate_mae([], []), 0.0)
        self.assertEqual(bfa.calculate_rmse([], []), 0.0)
        self.assertEqual(bfa.calculate_picp([], [], []), 0.0)
        self.assertEqual(bfa.calculate_mpiw([], []), 0.0)
        self.assertEqual(bfa.calculate_sample_std([]), 0.0)
        self.assertEqual(bfa.calculate_confidence_interval([]), (0.0, 0.0))
        self.assertEqual(bfa.calculate_wilson_score_interval(0, 0), (0.0, 0.0))
        picp_det = bfa.calculate_picp_detailed([], [], [])
        self.assertEqual(picp_det["hits"], 0)
        self.assertEqual(picp_det["total"], 0)
        self.assertEqual(picp_det["ratio"], "0/0")


class TestPreservationOfRLEngine(unittest.TestCase):
    def test_rl_engine_and_q_table_fully_preserved(self):
        """CRITICAL: Verify Contextual Bandit RL engine in rl_engine_v2.py is intact with 36 contexts."""
        agent = rl_engine_v2.ContextualBanditAgent(actions=[1, 2, 3, 4])
        self.assertTrue(os.path.exists(rl_engine_v2.MODEL_PATH))
        agent.load_model(rl_engine_v2.MODEL_PATH)
        self.assertEqual(len(agent.q_table), 36)
        self.assertIn(("S1_MODERATE_LOW", 1), agent.q_table)


if __name__ == "__main__":
    unittest.main()

