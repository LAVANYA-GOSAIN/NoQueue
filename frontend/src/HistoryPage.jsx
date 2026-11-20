import { useState, useMemo } from "react";
import {
  History,
  Trash2,
  Clock,
  Search,
  Navigation,
  Gauge,
  Zap,
  ArrowLeft,
  AlertCircle,
  Compass,
  Fuel,
} from "lucide-react";
import { getHistory, clearHistory } from "./utils/storage";

function formatRelativeTime(isoString) {
  if (!isoString) return "";
  const date = new Date(isoString);
  const now = new Date();
  const diffSec = Math.floor((now - date) / 1000);

  if (diffSec < 60) return "Just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  if (diffSec < 172800) return "Yesterday";
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getActionIcon(type) {
  switch (type) {
    case "forecast":
      return <Gauge size={16} className="history-type-icon forecast" />;
    case "directions":
      return <Navigation size={16} className="history-type-icon directions" />;
    case "search":
      return <Search size={16} className="history-type-icon search" />;
    case "recommendation":
      return <Zap size={16} className="history-type-icon recommendation" />;
    case "view_station":
    case "station_view":
      return <Fuel size={16} className="history-type-icon station" />;
    case "region_change":
      return <Compass size={16} className="history-type-icon region" />;
    default:
      return <Clock size={16} className="history-type-icon default" />;
  }
}

function getActionLabel(type) {
  switch (type) {
    case "forecast":
      return "Queue Forecast";
    case "directions":
      return "Navigation";
    case "search":
      return "Location Search";
    case "recommendation":
      return "AI Recommendation";
    case "view_station":
    case "station_view":
      return "Station Selected";
    case "region_change":
      return "Region Updated";
    default:
      return "Activity";
  }
}

export default function HistoryPage({ onNavigate }) {
  const [historyItems, setHistoryItems] = useState(() => getHistory());
  const [filter, setFilter] = useState("all"); // "all" | "forecast" | "directions" | "search"
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  const filteredItems = useMemo(() => {
    if (filter === "all") return historyItems;
    return historyItems.filter((item) => item.type === filter);
  }, [historyItems, filter]);

  const handleClearHistory = () => {
    clearHistory();
    setHistoryItems([]);
    setShowClearConfirm(false);
  };

  return (
    <main className="main-content history-page-content" id="history">
      <div className="history-page-container">
        {/* Header */}
        <div className="history-page-header">
          <button
            type="button"
            className="back-to-home-btn"
            onClick={() => onNavigate && onNavigate("home")}
            aria-label="Back to stations"
          >
            <ArrowLeft size={16} />
            <span>Back to Stations</span>
          </button>

          <div className="history-title-row">
            <div className="history-title-block">
              <div className="history-avatar-large">
                <History size={28} />
              </div>
              <div className="history-identity">
                <h2>Activity History</h2>
                <p>Recent searches, requested queue projections, and directions for your guest session</p>
              </div>
            </div>

            {historyItems.length > 0 && !showClearConfirm && (
              <button
                type="button"
                className="clear-history-btn"
                onClick={() => setShowClearConfirm(true)}
                title="Clear all activity history"
              >
                <Trash2 size={15} />
                <span>Clear History</span>
              </button>
            )}

            {showClearConfirm && (
              <div className="clear-confirm-banner">
                <span>Clear all history?</span>
                <button
                  type="button"
                  className="confirm-clear-btn"
                  onClick={handleClearHistory}
                >
                  Yes, Clear
                </button>
                <button
                  type="button"
                  className="cancel-clear-btn"
                  onClick={() => setShowClearConfirm(false)}
                >
                  Cancel
                </button>
              </div>
            )}
          </div>

          {/* Filter Chips */}
          {historyItems.length > 0 && (
            <div className="history-filter-bar">
              <span className="filter-label">Filter:</span>
              <button
                type="button"
                className={`filter-chip ${filter === "all" ? "active" : ""}`}
                onClick={() => setFilter("all")}
              >
                All ({historyItems.length})
              </button>
              <button
                type="button"
                className={`filter-chip ${filter === "forecast" ? "active" : ""}`}
                onClick={() => setFilter("forecast")}
              >
                Forecasts ({historyItems.filter((i) => i.type === "forecast").length})
              </button>
              <button
                type="button"
                className={`filter-chip ${filter === "directions" ? "active" : ""}`}
                onClick={() => setFilter("directions")}
              >
                Directions ({historyItems.filter((i) => i.type === "directions").length})
              </button>
              <button
                type="button"
                className={`filter-chip ${filter === "search" ? "active" : ""}`}
                onClick={() => setFilter("search")}
              >
                Searches ({historyItems.filter((i) => i.type === "search").length})
              </button>
            </div>
          )}
        </div>

        {/* History List or Empty State */}
        {filteredItems.length === 0 ? (
          <div className="history-empty-card">
            <div className="empty-icon-circle">
              <History size={32} />
            </div>
            <h3>No recent activity</h3>
            <p>
              {filter === "all"
                ? "Your searches, station selections, and simulation forecasts will appear here automatically."
                : `No activity found for filter "${filter}".`}
            </p>
            <button
              type="button"
              className="history-home-cta-btn"
              onClick={() => onNavigate && onNavigate("home")}
            >
              <span>Explore Nearby CNG Stations</span>
            </button>
          </div>
        ) : (
          <div className="history-timeline">
            {filteredItems.map((item) => (
              <article key={item.id} className="history-item-card">
                <div className="history-item-left">
                  <div className="history-icon-badge">
                    {getActionIcon(item.type)}
                  </div>
                </div>

                <div className="history-item-content">
                  <div className="history-item-top">
                    <span className="history-action-tag">
                      {getActionLabel(item.type)}
                    </span>
                    <span className="history-timestamp" title={item.timestamp}>
                      <Clock size={12} />
                      {formatRelativeTime(item.timestamp)}
                    </span>
                  </div>

                  <h3 className="history-item-title">{item.title}</h3>

                  {item.summary && (
                    <p className="history-item-summary">{item.summary}</p>
                  )}

                  {/* Explicit notice for simulation projections */}
                  {item.tag && (
                    <div className="history-item-footer">
                      <span className="history-tag-pill">
                        {item.tag}
                      </span>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}

        {/* Informational Disclaimer Footer */}
        <div className="history-disclaimer-note">
          <AlertCircle size={14} className="note-icon" />
          <span>
            Activity is saved locally in your browser. Simulation forecasts recorded in history reflect mathematical queue projections, not live CCTV measurements.
          </span>
        </div>
      </div>
    </main>
  );
}

