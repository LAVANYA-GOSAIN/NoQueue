import { useMemo } from "react";
import { Clock, Gauge, TrendingUp, AlertCircle, RotateCw } from "lucide-react";

function getCongestionStatus(waitTimeMinutes) {
  const wait =
    typeof waitTimeMinutes === "number"
      ? waitTimeMinutes
      : parseFloat(waitTimeMinutes) || 0;

  if (wait <= 10) {
    return { level: "LOW", className: "congestion-low", label: "LOW" };
  }
  if (wait <= 20) {
    return { level: "MEDIUM", className: "congestion-medium", label: "MEDIUM" };
  }
  return { level: "HIGH", className: "congestion-high", label: "HIGH" };
}

/**
 * Renders a lightweight SVG queue projection chart showing
 * the trajectory from current queue through 15m, 30m, and 60m
 * with the P10-P90 confidence envelope.
 */
function QueueTrendChart({ currentQueue, forecast }) {
  const points = useMemo(() => {
    const isMulti = forecast?.["15m"]?.expected_waiting_queue !== undefined;
    const q0 = typeof currentQueue === "number" ? currentQueue : 0;
    const q15 = isMulti
      ? (forecast?.["15m"]?.expected_waiting_queue ?? q0)
      : (forecast?.["15m"]?.expected_queue ?? q0);
    const q30 = isMulti
      ? (forecast?.["30m"]?.expected_waiting_queue ?? q15)
      : (forecast?.["30m"]?.expected_queue ?? q15);
    const q60 = isMulti
      ? (forecast?.["60m"]?.expected_waiting_queue ?? q30)
      : (forecast?.["60m"]?.expected_queue ?? q30);

    const r15 = isMulti
      ? (forecast?.["15m"]?.waiting_queue_range ?? [q15, q15])
      : (forecast?.["15m"]?.queue_range ?? [q15, q15]);
    const r30 = isMulti
      ? (forecast?.["30m"]?.waiting_queue_range ?? [q30, q30])
      : (forecast?.["30m"]?.queue_range ?? [q30, q30]);
    const r60 = isMulti
      ? (forecast?.["60m"]?.waiting_queue_range ?? [q60, q60])
      : (forecast?.["60m"]?.queue_range ?? [q60, q60]);

    const maxVal = Math.max(
      q0,
      q15,
      q30,
      q60,
      r15[1],
      r30[1],
      r60[1],
      6
    ) + 2;

    // SVG coordinates: viewBox 0 0 540 140
    // Margins: left: 45, right: 35, top: 22, bottom: 28
    const left = 45;
    const width = 460;
    const top = 20;
    const height = 90;

    const x0 = left;
    const x15 = left + width * 0.25;
    const x30 = left + width * 0.55;
    const x60 = left + width;

    const getY = (val) => {
      const clamped = Math.max(0, val);
      return Math.round(top + height - (clamped / maxVal) * height);
    };

    const y0 = getY(q0);
    const y15 = getY(q15);
    const y30 = getY(q30);
    const y60 = getY(q60);

    const y15_p10 = getY(r15[0]);
    const y15_p90 = getY(r15[1]);
    const y30_p10 = getY(r30[0]);
    const y30_p90 = getY(r30[1]);
    const y60_p10 = getY(r60[0]);
    const y60_p90 = getY(r60[1]);

    const linePath = `M ${x0} ${y0} L ${x15} ${y15} L ${x30} ${y30} L ${x60} ${y60}`;
    const bandPath = `M ${x0} ${y0} L ${x15} ${y15_p90} L ${x30} ${y30_p90} L ${x60} ${y60_p90} L ${x60} ${y60_p10} L ${x30} ${y30_p10} L ${x15} ${y15_p10} Z`;

    return {
      isMulti,
      maxVal,
      coords: [
        { label: "Now", time: "Current", x: x0, y: y0, q: Math.round(q0) },
        { label: "15m", time: "+15m", x: x15, y: y15, q: Math.round(q15), p10: r15[0], p90: r15[1] },
        { label: "30m", time: "+30m", x: x30, y: y30, q: Math.round(q30), p10: r30[0], p90: r30[1] },
        { label: "60m", time: "+60m", x: x60, y: y60, q: Math.round(q60), p10: r60[0], p90: r60[1] },
      ],
      linePath,
      bandPath,
      yBottom: top + height,
      yMid: getY(Math.round(maxVal / 2)),
      yTop: top,
    };
  }, [currentQueue, forecast]);

  return (
    <div className="forecast-chart-card">
      <div className="forecast-chart-header">
        <div className="forecast-chart-title">
          <TrendingUp size={15} className="chart-title-icon" />
          <span>{points.isMulti ? "Waiting Queue Trajectory & Uncertainty Band (P10–P90)" : "Queue Trajectory & Uncertainty Band (P10–P90)"}</span>
        </div>
        <div className="forecast-chart-legend">
          <span className="legend-item">
            <span className="legend-line" /> Mean Projection
          </span>
          <span className="legend-item">
            <span className="legend-band" /> P10–P90 Range
          </span>
        </div>
      </div>

      <div className="forecast-svg-wrapper">
        <svg
          viewBox="0 0 540 140"
          className="forecast-svg"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Queue forecast trend chart over 60 minutes"
        >
          <defs>
            <linearGradient id="qBandGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#208c52" stopOpacity="0.22" />
              <stop offset="100%" stopColor="#208c52" stopOpacity="0.04" />
            </linearGradient>
            <linearGradient id="qLineGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#25814e" />
              <stop offset="100%" stopColor="#10b981" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line
            x1="45"
            y1={points.yBottom}
            x2="505"
            y2={points.yBottom}
            stroke="#e2ebe4"
            strokeDasharray="2 2"
          />
          <line
            x1="45"
            y1={points.yMid}
            x2="505"
            y2={points.yMid}
            stroke="#edf4ee"
            strokeDasharray="2 2"
          />
          <line
            x1="45"
            y1={points.yTop}
            x2="505"
            y2={points.yTop}
            stroke="#edf4ee"
            strokeDasharray="2 2"
          />

          {/* Y-axis tick values */}
          <text x="36" y={points.yBottom + 3} textAnchor="end" className="chart-axis-label">
            0
          </text>
          <text x="36" y={points.yMid + 3} textAnchor="end" className="chart-axis-label">
            {Math.round(points.maxVal / 2)}
          </text>
          <text x="36" y={points.yTop + 3} textAnchor="end" className="chart-axis-label">
            {points.maxVal}
          </text>

          {/* Confidence Band Polygon */}
          <path d={points.bandPath} fill="url(#qBandGrad)" />

          {/* Main Trajectory Line */}
          <path
            d={points.linePath}
            fill="none"
            stroke="url(#qLineGrad)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Dot Markers & Value Badges */}
          {points.coords.map((pt, idx) => (
            <g key={pt.label}>
              {/* Vertical guideline */}
              <line
                x1={pt.x}
                y1={pt.y}
                x2={pt.x}
                y2={points.yBottom}
                stroke="#d3e4d7"
                strokeDasharray="2 2"
              />

              {/* Dot outer and inner */}
              <circle
                cx={pt.x}
                cy={pt.y}
                r="5"
                fill="#ffffff"
                stroke="#208c52"
                strokeWidth="2.5"
              />

              {/* Value text above dot */}
              <text
                x={pt.x}
                y={pt.y - 8}
                textAnchor="middle"
                className="chart-dot-value"
              >
                {typeof pt.q === "number" ? Math.round(pt.q) : pt.q}
              </text>

              {/* X-axis label */}
              <text
                x={pt.x}
                y={points.yBottom + 18}
                textAnchor="middle"
                className={`chart-x-label ${idx === 0 ? "now" : ""}`}
              >
                {pt.time}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}

/**
 * Queue Forecast Section for the active (selected or recommended) station.
 */
export default function QueueForecastSection({
  station,
  isRecommended = true,
  onResetToRecommended,
}) {
  if (!station) {
    return null;
  }

  const forecast = station.queue_forecast;
  const isMalformed =
    !forecast ||
    typeof forecast !== "object" ||
    !forecast["15m"] ||
    !forecast["30m"] ||
    !forecast["60m"];

  const currentQueue = station.queue_length ?? station.queue ?? 0;
  const stationName = station.name || "Station";

  const horizons = [
    { key: "15m", label: "15 minutes", horizonPill: "+15 min" },
    { key: "30m", label: "30 minutes", horizonPill: "+30 min" },
    { key: "60m", label: "60 minutes", horizonPill: "+60 min" },
  ];

  return (
    <section className="section-block forecast-section" id="queue-forecast-section">
      <div className="section-heading forecast-heading">
        <div className="forecast-heading-left">
          <div className="forecast-eyebrow-row">
            <span className="eyebrow">PREDICTIVE LOOKAHEAD</span>
            <span className="forecast-transparency-pill">
              <Gauge size={11} /> {station.simulator_engine === "multi_dispenser" ? `Multi-dispenser forecast (${station.forecast_trials || 100} trials)` : `Simulation forecast (${station.forecast_trials || 100} trials)`}
            </span>
            {station.dispenser_count ? (
              <span className="forecast-dispenser-pill" style={{ marginLeft: "8px", fontSize: "0.75rem", background: "#e8f5e9", color: "#25814e", padding: "2px 8px", borderRadius: "12px", fontWeight: "600" }}>
                {station.dispenser_count} bays
              </span>
            ) : null}
          </div>
          <h2>Queue Forecast</h2>
          <p className="section-subtitle">
            Expected queue and waiting times for <strong>{stationName}</strong>
            {isRecommended ? (
              <span className="forecast-station-type-tag rec"> (Best Option)</span>
            ) : (
              <span className="forecast-station-type-tag user-selected"> (Selected Station)</span>
            )}
          </p>
        </div>

        <div className="heading-actions forecast-heading-actions">
          {!isRecommended && typeof onResetToRecommended === "function" && (
            <button
              type="button"
              className="forecast-reset-btn"
              onClick={onResetToRecommended}
              title="Return to Recommended station forecast"
            >
              <RotateCw size={12} />
              <span>Reset to Recommended</span>
            </button>
          )}
        </div>
      </div>

      {isMalformed ? (
        <div className="state-container forecast-unavailable-card">
          <AlertCircle size={24} className="forecast-alert-icon" />
          <div className="forecast-empty-copy">
            <h3>Forecast Data Unavailable</h3>
            <p>
              Simulation-based queue projections are currently unavailable for{" "}
              <strong>{stationName}</strong>.
            </p>
            <span className="forecast-empty-subtext">
              Projections refresh automatically when new simulator cycles complete.
            </span>
          </div>
        </div>
      ) : (
        <>
          {/* Three Forecast Cards: 15m, 30m, 60m */}
          <div className="forecast-cards-grid">
            {horizons.map(({ key, horizonPill }) => {
              const hData = forecast[key];
              const isMulti = hData?.expected_waiting_queue !== undefined;

              // Rounding rule: In accordance with presentation standards, vehicle counts represent
              // physical units and are rounded to whole numbers using standard half-up rounding (Math.round).
              // Expected waiting times strictly remain in decimal format (e.g. 0.7 min).
              const rawWaiting = isMulti
                ? (hData.expected_waiting_queue ?? 0)
                : (hData?.expected_queue ?? 0);
              const waitingVeh = Math.round(Number(rawWaiting));

              const expWait = Number(hData?.expected_wait_minutes ?? 0).toFixed(1);

              // Matching integer range: waiting_queue_range for multi-dispenser, queue_range for legacy
              const rawRange = isMulti ? hData?.waiting_queue_range : hData?.queue_range;
              const qRange = Array.isArray(rawRange) && rawRange.length === 2
                ? [Math.round(rawRange[0]), Math.round(rawRange[1])]
                : [waitingVeh, waitingVeh];

              // Breakdown counts rounded to whole integers
              const rawServed = isMulti && hData?.expected_vehicles_being_served !== undefined
                ? hData.expected_vehicles_being_served
                : null;
              const servedVeh = rawServed !== null ? Math.round(Number(rawServed)) : null;

              const rawTotal = hData?.expected_queue !== undefined
                ? hData.expected_queue
                : null;
              const totalOccupancy = rawTotal !== null ? Math.round(Number(rawTotal)) : waitingVeh;

              const cong = getCongestionStatus(Number(expWait));

              return (
                <article key={key} className="forecast-card">
                  <div className="forecast-card-top">
                    <div className="forecast-horizon-badge">
                      <Clock size={12} />
                      <span>{horizonPill}</span>
                    </div>
                    <span
                      className={`congestion-badge ${cong.className}`}
                      title={`Queue Congestion: ${cong.level}`}
                    >
                      {cong.level}
                    </span>
                  </div>

                  <div className="forecast-stat-hero">
                    <div className="forecast-queue-number">{waitingVeh}</div>
                    <div className="forecast-queue-label">
                      <strong>{waitingVeh === 1 ? "vehicle" : "vehicles"}</strong>
                      <span>{isMulti ? "expected waiting in line" : "expected in queue"}</span>
                    </div>
                  </div>

                  <div className="forecast-metric-row">
                    <Clock size={14} className="forecast-metric-icon" />
                    <span className="forecast-metric-label">Expected wait:</span>
                    <strong className="forecast-metric-value">{expWait} min</strong>
                  </div>

                  {isMulti ? (
                    <div className="forecast-dispenser-breakdown">
                      <div className="breakdown-item">
                        <span className="breakdown-label">Actively fueling:</span>
                        <strong>{servedVeh} veh</strong>
                      </div>
                      <div className="breakdown-item">
                        <span className="breakdown-label">Total station occupancy:</span>
                        <strong>{totalOccupancy} veh</strong>
                      </div>
                    </div>
                  ) : (
                    <div className="forecast-dispenser-breakdown">
                      <div className="breakdown-item">
                        <span className="breakdown-label">Total station occupancy:</span>
                        <strong>{totalOccupancy} veh</strong>
                      </div>
                    </div>
                  )}

                  <div className="forecast-range-container">
                    <div className="forecast-range-header">
                      <span className="forecast-range-title">
                        {isMulti ? "P10–P90 waiting range" : "P10–P90 queue range"}
                      </span>
                      <strong className="forecast-range-spread">
                        {qRange[0]} – {qRange[1]} vehicles
                      </strong>
                    </div>
                    <div className="forecast-range-track" aria-hidden="true">
                      <div
                        className="forecast-range-band"
                        style={{
                          left: `${Math.min(100, (qRange[0] / Math.max(Number(waitingVeh) * 2, qRange[1], 10)) * 100)}%`,
                          width: `${Math.max(
                            8,
                            Math.min(
                              100,
                              ((qRange[1] - qRange[0]) / Math.max(Number(waitingVeh) * 2, qRange[1], 10)) * 100
                            )
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                </article>
              );
            })}
          </div>

          {/* Lightweight Trend Chart */}
          <QueueTrendChart currentQueue={currentQueue} forecast={forecast} />

          {/* Explanatory Note / Transparency */}
          <div className="forecast-note-banner">
            <AlertCircle size={15} className="forecast-note-icon" />
            <p>
              Forecasts are estimated using simulated vehicle arrivals and service rates.
              They are not live CCTV measurements.
            </p>
          </div>
        </>
      )}
    </section>
  );
}
