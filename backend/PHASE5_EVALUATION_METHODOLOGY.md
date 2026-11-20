# NoQueue Phase 5, 5.1, 5.2 & 5.3: Multi-Dispenser Forecast Statistical Evaluation Methodology

**Document Version:** 1.3.0 (Phase 5.3 Final Statistical Validity, Bounded Clustered PICP & Replication Architecture)  
**Status:** Methodological Specification & Evaluation Protocol  
**Associated Benchmark Implementation:** [`backend/benchmark_forecast_accuracy.py`](file:///Users/lavanyagosain/Desktop/NoQueue/backend/benchmark_forecast_accuracy.py)  
**Associated Test Suite:** [`backend/test_forecast_evaluation_phase5.py`](file:///Users/lavanyagosain/Desktop/NoQueue/backend/test_forecast_evaluation_phase5.py)  
**Sensitivity Analysis Output:** [`backend/evaluation_results/monte_carlo_sensitivity_results.json`](file:///Users/lavanyagosain/Desktop/NoQueue/backend/evaluation_results/monte_carlo_sensitivity_results.json)  
**Benchmark Suite Output:** [`backend/evaluation_results/phase5_benchmark_results.json`](file:///Users/lavanyagosain/Desktop/NoQueue/backend/evaluation_results/phase5_benchmark_results.json)  

---

> [!IMPORTANT]
> ### Critical Research Methodology Notice & Disclaimer
> **"These results evaluate forecasting performance against independently generated outcomes from the controlled synthetic simulation environment. They do not establish predictive accuracy on real-world CNG station data. Real-world validation requires independently observed, timestamped queue histories."**
>
> The current NoQueue platform models vehicle arrivals and dispenser service durations using stochastic processes parameterized by empirical literature (e.g. the 2025 Arena simulation case study) and synthetic traffic curves. We do not yet possess independently annotated, timestamped video observations extracted from real-world Gurugram petrol pump CCTV recordings.
>
> Consequently:
> 1. We rigorously evaluate forecasting consistency, uncertainty bounds, and resilience to model mismatch against **independently simulated synthetic ground truth**.
> 2. We **never** claim predictive accuracy on real-world CNG stations.
> 3. We **never** evaluate the model against future data generated using the same random-number stream or shared events that the forecast model already sampled.
> 4. Real-world validation status is formally reported as:  
>    **`NOT AVAILABLE — INDEPENDENT OBSERVATIONS REQUIRED`**.

---

## 1. Evaluation Objectives & Statistical Independence Audit (Phase 5.2 & 5.3)

The objective of Phase 5.3 is to establish rigorous statistical validity and transparent uncertainty quantification without modifying the working queue simulator or production engine.

### Critical Audit Findings on Temporal Dependence & Clustering:
1. **Intra-Replication Dependence:**
   - Within each simulation replication, consecutive evaluation origins ($n_{\text{rep}}$ origins spaced by $10$ minutes) advance from the **same continuous simulation instance** (`live_sim`).
   - Consequently, origin $k$ shares simulated queue history and vehicle states with origin $k-1$.
   - Furthermore, forecast evaluation horizons are $15$, $30$, and $60$ minutes. A $60$-minute lookahead window initiated at $t=15$ spans to $t=75$, which **temporally overlaps** with origins initiated at $t=25, 35, 45, 55, 65, 75$.
   - **Conclusion:** The $100$ rolling-origin evaluation points are **not 100 independent identically distributed (i.i.d.) observations**. They represent clustered observations subject to positive temporal autocorrelation.
2. **True Independent Degrees of Freedom:**
   - The true number of independent experimental units is the **$R$ independent simulation replications**.
   - Each replication is initialized with an independent random seed, a separate warm-up period, and non-overlapping random streams.
   - Therefore, ordinary i.i.d. standard errors ($s/\sqrt{100}$) underestimate parameter uncertainty.
3. **Cluster-Aware Statistical Methodology:**
   - Continuous performance metrics (Queue MAE, Wait MAE, Queue RMSE, MPIW, Macro-F1) are calculated at the replication level: $\hat{M}_1, \dots, \hat{M}_R$.
   - The replication-level mean error $\bar{M}_{\text{rep}} = \frac{1}{R}\sum_{r=1}^R \hat{M}_r$ is evaluated.
   - Between-replication sample standard deviation:
     $$s_{\text{rep}} = \sqrt{\frac{1}{R-1} \sum_{r=1}^R \left( \hat{M}_r - \bar{M}_{\text{rep}} \right)^2}$$
   - Cluster-robust standard error:
     $$\text{SE}_{\text{cluster}} = \frac{s_{\text{rep}}}{\sqrt{R}}$$
   - 95% Confidence Interval using Student's $t$-distribution with $df = R - 1$ degrees of freedom:
     $$\text{CI}_{95, \text{clustered}} = \left[ \bar{M}_{\text{rep}} - t_{0.025, R-1} \cdot \text{SE}_{\text{cluster}}, \; \bar{M}_{\text{rep}} + t_{0.025, R-1} \cdot \text{SE}_{\text{cluster}} \right]$$

---

## 2. Independent Replications Scaling Audit ($R=5$ vs $R=10$ vs $R=20$)

To assess how the number of independent simulation replications ($R$) influences estimation precision, degrees of freedom, and computational cost, a controlled scaling benchmark was conducted holding total evaluation sample size fixed at $N = 100$ origins:

| Configuration | Trajectory / Rep | Total Runtime | $df$ | $t_{crit}$ ($95\%$) | Queue MAE (60m) | Clustered 95% CI | CI Width |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$R = 5$** ($20$ origins/rep) | $200\text{ min}$ | $25.57\text{s}$ | $4$ | $2.776$ | $3.36\text{ veh}$ | $[2.83, 3.89]$ | $1.060\text{ veh}$ |
| **$R = 10$** ($10$ origins/rep) | $100\text{ min}$ | $20.24\text{s}$ | $9$ | $2.262$ | $3.33\text{ veh}$ | $[2.87, 3.79]$ | **$0.920\text{ veh}$** |
| **$R = 20$** ($5$ origins/rep) | $50\text{ min}$ | $23.96\text{s}$ | $19$ | $2.093$ | $3.65\text{ veh}$ | $[2.97, 4.33]$ | $1.360\text{ veh}$ |

### Key Findings & Trade-Off Analysis:
1. **Degrees of Freedom & Critical Values:**
   - Moving from $R=5$ to $R=10$ increases degrees of freedom from $df=4$ to $df=9$, shrinking the Student-$t$ critical multiplier by **$18.5\%$** (from $2.776$ to $2.262$).
   - Moving from $R=10$ to $R=20$ yields only a minor additional reduction in $t_{crit}$ (from $2.262$ to $2.093$, $-7.5\%$).
2. **Within-Replication Trajectory Length:**
   - At $R=20$, each replication spans only $5$ origins ($50$ minutes). Because origins are spaced $10$ minutes apart, each replication explores only a short temporal window, increasing between-replication sampling variance ($s_{\text{rep}}$ rises from $0.64$ to $1.46$).
   - At $R=10$, each replication spans $100$ minutes, providing sufficient duration to experience representative queue buildup and dissipation cycles while doubling independent degrees of freedom.
3. **Confidence Interval Width:**
   - $R=10$ produces the narrowest confidence interval (**$0.920\text{ veh}$**), outperforming both $R=5$ ($1.060\text{ veh}$) and $R=20$ ($1.360\text{ veh}$).
4. **Execution Speed:**
   - Runtime remains virtually constant across all three configurations (~$20\text{--}25\text{s}$ per scenario) because the total number of evaluated origins ($N=100$) and forecast trials are identical.
5. **Architectural Recommendation:**
   - $R=10$ ($10$ origins/rep) is the statistically optimal configuration for future benchmark runs.
   - $R=5$ ($20$ origins/rep) remains a defensible, highly conservative baseline with deep individual trajectory histories.

---

## 3. Statistically Bounded PICP Methodology (Rao-Scott Adjusted Wilson Score)

### Audit of Prior Failure Mode:
In Phase 5.2, cluster-level uncertainty for Prediction Interval Coverage Probability (PICP) was computed by applying a linear Student-$t$ interval to the replication coverage rates: $\bar{p} \pm t_{crit} \cdot \text{SE}_{\text{cluster}}$.  
Because a linear interval treats coverage probability as an unconstrained continuous variable:
- Near $0.0$, subtraction of $t_{crit} \cdot \text{SE}$ generated **impossible negative lower bounds** (e.g. Stress Scenario 4 at 60m: $[-0.018, 0.038]$).
- Near $1.0$, addition generated **impossible upper bounds $> 1.0$** (e.g. Scenario 3 at 60m: $[0.91, 1.01]$).

### Rao-Scott Design-Effect Adjusted Wilson Formulation (Phase 5.3):
To guarantee that coverage intervals lie strictly within $[0, 1]$ while honestly accounting for intra-cluster correlation across replications, Phase 5.3 implements the **Rao-Scott design-effect adjusted Wilson score method**:

1. **Pooled Coverage Estimate ($\hat{p}$):**
   $$\hat{p} = \frac{K}{N} = \frac{\sum_{r=1}^R k_r}{\sum_{r=1}^R n_r}$$
2. **Simple Random Sample Variance ($V_{\text{srs}}$):**
   $$V_{\text{srs}} = \frac{\hat{p}(1 - \hat{p})}{N}$$
3. **Cluster Sample Variance ($V_{\text{cluster}}$):**
   $$V_{\text{cluster}} = \frac{R}{R - 1} \sum_{r=1}^R \left(\frac{n_r}{N}\right)^2 \left( \frac{k_r}{n_r} - \hat{p} \right)^2$$
4. **Design Effect ($\text{deff}$) & Effective Sample Size ($n_{\text{eff}}$):**
   $$\text{deff} = \max\left(1.0, \; \frac{V_{\text{cluster}}}{V_{\text{srs}}}\right), \quad n_{\text{eff}} = \frac{N}{\text{deff}}$$
5. **Wilson Score Center & Margin with Small-Sample Degrees of Freedom ($z = t_{0.025, R-1}$):**
   $$\text{denom} = 1 + \frac{z^2}{n_{\text{eff}}}$$
   $$\text{center} = \frac{\hat{p} + \frac{z^2}{2 n_{\text{eff}}}}{\text{denom}}$$
   $$\text{margin} = \frac{z}{\text{denom}} \sqrt{\frac{\hat{p}(1 - \hat{p})}{n_{\text{eff}}} + \frac{z^2}{4 n_{\text{eff}}^2}}$$
   $$\text{CI}_{95, \text{bounded}} = \left[ \max(0.0, \text{center} - \text{margin}), \; \min(1.0, \text{center} + \text{margin}) \right]$$

### Mathematical Properties & Guarantees:
- **Strict $[0, 1]$ Bounds:** The roots of the Wilson score quadratic lie strictly within $[0, 1]$ for all $\hat{p} \in [0, 1]$, $n_{\text{eff}} > 0$, and $z > 0$. Boundary violations are algebraically impossible.
- **No Ad-Hoc Clipping:** Endpoints naturally converge to $[0.0, \text{upper}]$ at $\hat{p}=0$ and $[\text{lower}, 1.0]$ at $\hat{p}=1$.
- **Transparent Reporting:** The benchmark output preserves:
  - Exact counts: $\text{hits} = K$, $\text{total} = N$, $\text{ratio} = "K/N"$.
  - Pooled Wilson interval (unclustered reference).
  - Cluster-adjusted interval, design effect $\text{deff}$, and effective sample size $n_{\text{eff}}$.
  - Individual replication rates: $[\hat{p}_1, \dots, \hat{p}_R]$.

---

## 4. Multi-State Monte Carlo Trial-Count Sensitivity Analysis

To rigorously verify whether $100$ Monte Carlo trials per origin provides stable forecast distributions across diverse operating regimes, Phase 5.3 expands the sensitivity analysis across **4 representative initial states**:
1. **Low Demand (3 Dispensers, $\lambda=0.45$, Calm Off-Peak):** Initial queue = 3, waiting = 0.
2. **Moderate Demand (2 Dispensers, $\lambda=0.75$, Urban Commute):** Initial queue = 16, waiting = 14.
3. **Heavy Demand (4 Dispensers, $\lambda=1.20$, Highway Hub):** Initial queue = 16, waiting = 12.
4. **Stress Condition (2 Dispensers, $\lambda=0.98$, $+40\%$ Surge):** Initial queue = 12, waiting = 10.

Each state was evaluated across $5$ independent seeds for $30, 100, 200,$ and $500$ trials:

| State | Trials | Runtime / fc | 60m ExpQueue (±std) | 60m P10-P90 Range | 60m Width (±std) | 60m ExpWait (±std) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Low Demand (3D)** | 30 | $0.056\text{s}$ | $2.4\text{ (±0.55)}$ | $[0.2, 5.0]$ | $4.8\text{ (±1.30)}$ | $2.4\text{m (±0.84m)}$ |
| | 100 | $0.183\text{s}$ | $2.2\text{ (±0.45)}$ | $[0.0, 5.0]$ | $5.0\text{ (±0.71)}$ | $2.0\text{m (±0.27m)}$ |
| | 200 | $0.368\text{s}$ | $2.2\text{ (±0.45)}$ | $[0.0, 5.0]$ | $5.0\text{ (±0.71)}$ | $2.0\text{m (±0.13m)}$ |
| | 500 | $0.956\text{s}$ | $2.0\text{ (±0.00)}$ | $[0.0, 4.8]$ | $4.8\text{ (±0.45)}$ | $1.9\text{m (±0.19m)}$ |
| **Moderate Demand (2D)** | 30 | $0.053\text{s}$ | $21.8\text{ (±0.45)}$ | $[16.0, 25.8]$ | $9.8\text{ (±1.92)}$ | $51.8\text{m (±1.16m)}$ |
| | 100 | $0.176\text{s}$ | $21.0\text{ (±0.71)}$ | $[15.2, 25.8]$ | $10.6\text{ (±1.14)}$ | $49.7\text{m (±1.50m)}$ |
| | 200 | $0.370\text{s}$ | $21.0\text{ (±0.00)}$ | $[15.4, 26.2]$ | $10.8\text{ (±0.84)}$ | $50.4\text{m (±0.32m)}$ |
| | 500 | $0.946\text{s}$ | $21.0\text{ (±0.00)}$ | $[15.2, 26.2]$ | $11.0\text{ (±0.71)}$ | $50.7\text{m (±0.68m)}$ |
| **Heavy Demand (4D)** | 30 | $0.087\text{s}$ | $22.6\text{ (±0.55)}$ | $[16.4, 27.2]$ | $10.8\text{ (±2.49)}$ | $24.7\text{m (±0.86m)}$ |
| | 100 | $0.296\text{s}$ | $22.8\text{ (±0.45)}$ | $[17.4, 27.6]$ | $10.2\text{ (±1.10)}$ | $25.1\text{m (±0.29m)}$ |
| | 200 | $0.582\text{s}$ | $23.0\text{ (±0.00)}$ | $[17.2, 28.0]$ | $10.8\text{ (±0.84)}$ | $25.6\text{m (±0.37m)}$ |
| | 500 | $1.445\text{s}$ | $23.0\text{ (±0.00)}$ | $[17.2, 28.0]$ | $10.8\text{ (±0.45)}$ | $25.3\text{m (±0.22m)}$ |
| **Stress Surge (2D)** | 30 | $0.054\text{s}$ | $25.0\text{ (±0.00)}$ | $[19.2, 28.8]$ | $9.6\text{ (±1.34)}$ | $60.0\text{m (±0.79m)}$ |
| | 100 | $0.178\text{s}$ | $24.8\text{ (±0.45)}$ | $[19.4, 29.4]$ | $10.0\text{ (±0.71)}$ | $59.6\text{m (±1.40m)}$ |
| | 200 | $0.356\text{s}$ | $24.4\text{ (±0.55)}$ | $[19.6, 29.0]$ | $9.4\text{ (±0.55)}$ | $59.1\text{m (±0.75m)}$ |
| | 500 | $0.905\text{s}$ | $25.0\text{ (±0.00)}$ | $[19.8, 29.0]$ | $9.2\text{ (±0.45)}$ | $59.9\text{m (±0.32m)}$ |

### Justification of 100 Trials for Evaluation:
1. **Consistency Across States:** Across all 4 demand states, 100 trials reduces interval width jitter by $45\text{--}55\%$ compared to 30 trials, keeping width standard deviations near $\approx 1\text{ veh}$.
2. **Computational Feasibility:** Evaluating 8 scenarios $\times$ 100 origins = 800 forecasts. At 100 trials (~0.20s/forecast), total execution requires ~160s (~2.5 minutes). At 500 trials (~1.2s/forecast), execution would require ~16 minutes without meaningfully shifting mean predictions (<0.2 veh difference).

---

## 5. Defensible Classification Metric Conventions (Macro-F1)

### Standard Convention (`zero_division = 0.0`):
1. **Per-Class Metrics:**
   $$\text{Precision}_c = \frac{\text{TP}_c}{\text{TP}_c + \text{FP}_c}, \quad \text{Recall}_c = \frac{\text{TP}_c}{\text{TP}_c + \text{FN}_c}, \quad \text{F1}_c = \frac{2 \cdot P_c \cdot R_c}{P_c + R_c}$$
   Where $TP_c + FP_c = 0$ or $TP_c + FN_c = 0$, Precision, Recall, and F1 are set strictly to $0.0$.
2. **Active-Class Macro-F1:**
   $$\text{Active Classes} = \{c \in \{\text{LOW}, \text{MEDIUM}, \text{HIGH}\} \mid \text{TrueCount}_c > 0 \lor \text{PredCount}_c > 0\}$$
   $$\text{Macro-F1}_{\text{active}} = \frac{1}{|\text{Active Classes}|} \sum_{c \in \text{Active Classes}} \text{F1}_c$$
   Absent classes receive $\text{F1} = 0.0$ and are excluded from the active-class denominator rather than artificially inflating the score to $1.0$.
3. **Fixed 3-Class Macro-F1:**
   $$\text{Macro-F1}_{\text{3class}} = \frac{1}{3} \left( \text{F1}_{\text{LOW}} + \text{F1}_{\text{MEDIUM}} + \text{F1}_{\text{HIGH}} \right)$$
   Directly conforms to `sklearn.metrics.f1_score(..., labels=['LOW', 'MEDIUM', 'HIGH'], average='macro', zero_division=0)`.

---

## 6. Congestion Threshold Origin (Confirmed Pre-Phase 5)

A comprehensive audit confirms that the congestion classification boundaries:
- **`LOW`:** Estimated wait $\le 10.0\text{ minutes}$
- **`MEDIUM`:** Estimated wait $10.1\text{ to } 20.0\text{ minutes}$
- **`HIGH`:** Estimated wait $> 20.0\text{ minutes}$

were **already established prior to Phase 5**:
1. **Source File:** [`backend/data/synthetic/queue_simulator.py`](file:///Users/lavanyagosain/Desktop/NoQueue/backend/data/synthetic/queue_simulator.py#L108-L121)
2. **Class & Function:** `QueueSimulator.get_congestion_level(self)`
3. **Unit:** Estimated incoming waiting time in **minutes** (`wait = self.estimate_waiting_time()`).
4. **Boundary Verification:** Pre-existing unit tests in [`backend/test_queue_simulation.py`](file:///Users/lavanyagosain/Desktop/NoQueue/backend/test_queue_simulation.py#L93-L114) (`test_congestion_level_boundaries`) verified the exact transition points: $0\text{m} \to \text{LOW}$, $10\text{m} \to \text{LOW}$, $11\text{m} \to \text{MEDIUM}$, $20\text{m} \to \text{MEDIUM}$, $21\text{m} \to \text{HIGH}$.
5. **Production Endpoints:** Used directly in production API responses in [`backend/main.py`](file:///Users/lavanyagosain/Desktop/NoQueue/backend/main.py#L218) (lines 218, 241, 379, 406).

---

## 7. Queue Measurement Definitions

To prevent mixing distinct queue metrics:
- **Total Station Occupancy ($N_{\text{total}}$):**
  $$N_{\text{total}} = N_{\text{waiting}} + N_{\text{active}} = \sum_{j=1}^c N_j$$
  Evaluated as the primary metric because Phase 4 `expected_queue` represents total station bay occupancy.
- **Waiting Queue Length ($N_{\text{waiting}}$):**
  $$N_{\text{waiting}} = \sum_{j=1}^c k_j$$
  Vehicles strictly waiting in line behind active dispensers. Reported as an auxiliary metric (`auxiliary_waiting_queue_mae`).
- **Vehicles Being Served ($N_{\text{active}}$):**
  $$N_{\text{active}} = \sum_{j=1}^c b_j$$

---

## 8. Real-World Observed Data Schema Specification

To support future validation when real-world CCTV recordings from Gurugram petrol pumps are annotated and timestamped, the evaluation suite defines the following standard schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "NoQueueRealWorldObservation",
  "type": "object",
  "required": [
    "station_id",
    "timestamp",
    "number_of_dispensers",
    "waiting_vehicles",
    "active_vehicles",
    "total_occupancy",
    "observation_source",
    "data_quality",
    "is_manually_verified"
  ],
  "properties": {
    "station_id": { "type": "integer" },
    "timestamp": { "type": "string", "format": "date-time" },
    "number_of_dispensers": { "type": "integer", "minimum": 1 },
    "waiting_vehicles": { "type": "integer", "minimum": 0 },
    "active_vehicles": { "type": "integer", "minimum": 0 },
    "total_occupancy": { "type": "integer", "minimum": 0 },
    "observed_waiting_time_seconds": { "type": ["number", "null"] },
    "observation_source": {
      "type": "string",
      "enum": ["cctv_manual_annotation", "cctv_automated_vision", "sensor_loop", "field_survey"]
    },
    "data_quality": {
      "type": "string",
      "enum": ["high_confidence", "partial_occlusion", "glare_or_weather_compromised"]
    },
    "is_manually_verified": { "type": "boolean" }
  }
}
```

### Current Status:
**`REAL-WORLD VALIDATION STATUS: NOT AVAILABLE — INDEPENDENT OBSERVATIONS REQUIRED`**  
No synthetic test outcome may be reported as real-world predictive validation.

---

## 9. Scope Protection & System Invariants

Phase 5.3 is strictly read-only with respect to live system behavior:
1. **Reinforcement Learning:** [`backend/rl_engine_v2.py`](file:///Users/lavanyagosain/Desktop/NoQueue/backend/rl_engine_v2.py) is untouched. The 36 learned contexts, Q-table weights, and contextual bandit decision policy are preserved.
2. **Production APIs:** No endpoints in `main.py` are modified or re-routed.
3. **Frontend:** All React components, forecast cards, and UI layers remain untouched.

---

## 6. Queue Measurement Definitions

To prevent mixing distinct queue metrics:
- **Total Station Occupancy ($N_{\text{total}}$):**
  $$N_{\text{total}} = N_{\text{waiting}} + N_{\text{active}} = \sum_{j=1}^c N_j$$
  Evaluated as the primary metric because Phase 4 `expected_queue` represents total station bay occupancy.
- **Waiting Queue Length ($N_{\text{waiting}}$):**
  $$N_{\text{waiting}} = \sum_{j=1}^c k_j$$
  Vehicles strictly waiting in line behind active dispensers. Reported as an auxiliary metric (`auxiliary_waiting_queue_mae`).
- **Vehicles Being Served ($N_{\text{active}}$):**
  $$N_{\text{active}} = \sum_{j=1}^c b_j$$

---

## 7. Real-World Observed Data Schema Specification

To support future validation when real-world CCTV recordings from Gurugram petrol pumps are annotated and timestamped, the evaluation suite defines the following standard schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "NoQueueRealWorldObservation",
  "type": "object",
  "required": [
    "station_id",
    "timestamp",
    "number_of_dispensers",
    "waiting_vehicles",
    "active_vehicles",
    "total_occupancy",
    "observation_source",
    "data_quality",
    "is_manually_verified"
  ],
  "properties": {
    "station_id": { "type": "integer" },
    "timestamp": { "type": "string", "format": "date-time" },
    "number_of_dispensers": { "type": "integer", "minimum": 1 },
    "waiting_vehicles": { "type": "integer", "minimum": 0 },
    "active_vehicles": { "type": "integer", "minimum": 0 },
    "total_occupancy": { "type": "integer", "minimum": 0 },
    "observed_waiting_time_seconds": { "type": ["number", "null"] },
    "observation_source": {
      "type": "string",
      "enum": ["cctv_manual_annotation", "cctv_automated_vision", "sensor_loop", "field_survey"]
    },
    "data_quality": {
      "type": "string",
      "enum": ["high_confidence", "partial_occlusion", "glare_or_weather_compromised"]
    },
    "is_manually_verified": { "type": "boolean" }
  }
}
```

### Current Status:
**`REAL-WORLD VALIDATION STATUS: NOT AVAILABLE — INDEPENDENT OBSERVATIONS REQUIRED`**  
No synthetic test outcome may be reported as real-world predictive validation.

---

## 8. Scope Protection & System Invariants

Phase 5 is strictly read-only with respect to live system behavior:
1. **Reinforcement Learning:** [`backend/rl_engine_v2.py`](file:///Users/lavanyagosain/Desktop/NoQueue/backend/rl_engine_v2.py) is untouched. The 36 learned contexts, Q-table weights, and contextual bandit decision policy are preserved.
2. **Production APIs:** No endpoints in `main.py` are modified or re-routed.
3. **Frontend:** All React components, forecast cards, and UI layers remain untouched.

