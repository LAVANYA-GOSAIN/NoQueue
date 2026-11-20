import { useState, useRef, useEffect } from "react";
import {
  UserRound,
  MapPin,
  LocateFixed,
  Search,
  CheckCircle2,
  AlertCircle,
  ArrowLeft,
  RotateCw,
  LogOut,
  Save,
  Compass,
  Edit3,
} from "lucide-react";
import {
  getGuestSession,
  updateGuestName,
  getUserRegion,
  saveUserRegion,
  clearGuestSession,
  addHistoryEntry,
} from "./utils/storage";

const QUICK_REGIONS = [
  { name: "Sector 50, Gurugram", query: "Sector 50 Gurugram", lat: 28.421, lon: 77.062 },
  { name: "Connaught Place, New Delhi", query: "Connaught Place New Delhi", lat: 28.6304, lon: 77.2177 },
  { name: "Sector 45, Gurugram", query: "Sector 45 Gurugram", lat: 28.455, lon: 77.072 },
  { name: "MG Road, Gurugram", query: "MG Road Gurugram", lat: 28.480, lon: 77.086 },
];

export default function ProfilePage({ onNavigate, onRegionChange, onSignOut }) {
  const [session, setSession] = useState(() => getGuestSession() || { name: "Guest Driver", isGuest: true });
  const [region, setRegion] = useState(() => getUserRegion() || { name: "Sector 50, Gurugram", query: "Sector 50 Gurugram", detectionMethod: "manual" });

  const [displayName, setDisplayName] = useState(() => session?.name || "Guest Driver");
  const [isEditingRegion, setIsEditingRegion] = useState(false);
  const [regionQuery, setRegionQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(false);

  const [saveStatus, setSaveStatus] = useState(null); // { type: "success"|"error", message: string }
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);

  const regionSearchRef = useRef(null);
  const abortControllerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (regionSearchRef.current && !regionSearchRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleRegionQueryChange = (text) => {
    setRegionQuery(text);
    const trimmed = text.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    if (abortControllerRef.current) abortControllerRef.current.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setSuggestionsLoading(true);
    const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(trimmed)}&limit=5&lat=28.5&lon=77.1`;

    fetch(url, { signal: controller.signal })
      .then((res) => res.json())
      .then((data) => {
        const features = data.features || [];
        const mapped = features.map((feat) => {
          const props = feat.properties || {};
          const coords = feat.geometry?.coordinates || [null, null];
          const parts = [props.name, props.district || props.suburb, props.city, props.state, props.country].filter(Boolean);
          return {
            label: parts.length > 0 ? parts.join(", ") : props.name || "Unknown place",
            lon: coords[0],
            lat: coords[1],
          };
        });
        setSuggestions(mapped);
        setShowSuggestions(mapped.length > 0);
      })
      .catch((err) => {
        if (err.name !== "AbortError") setSuggestions([]);
      })
      .finally(() => setSuggestionsLoading(false));
  };

  const applyNewRegion = (newRegionObj) => {
    const updated = saveUserRegion(newRegionObj);
    setRegion(updated);
    setIsEditingRegion(false);
    setShowSuggestions(false);
    setRegionQuery("");
    setSaveStatus({ type: "success", message: `Region updated to "${updated.name}"` });

    addHistoryEntry({
      type: "region_change",
      title: updated.name,
      summary: `Changed reference region to ${updated.name}`,
      tag: "Profile Region Update",
    });

    if (onRegionChange) {
      onRegionChange(updated);
    }
  };

  const handleDetectGPS = () => {
    if (!navigator.geolocation) {
      setSaveStatus({ type: "error", message: "Geolocation is not supported by your browser." });
      return;
    }

    setGpsLoading(true);
    setSaveStatus(null);

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        const fallbackName = `Current Area (${lat.toFixed(3)}°N, ${lon.toFixed(3)}°E)`;

        try {
          const res = await fetch(`http://127.0.0.1:8001/api/location/discover?lat=${lat}&lon=${lon}&radius=5000`);
          if (res.ok) {
            const data = await res.json();
            const resolvedName = data.resolved_location?.display_name || fallbackName;
            applyNewRegion({
              name: resolvedName,
              query: resolvedName,
              lat,
              lon,
              detectionMethod: "gps",
            });
          } else {
            applyNewRegion({
              name: fallbackName,
              query: `${lat},${lon}`,
              lat,
              lon,
              detectionMethod: "gps",
            });
          }
        } catch {
          applyNewRegion({
            name: fallbackName,
            query: `${lat},${lon}`,
            lat,
            lon,
            detectionMethod: "gps",
          });
        } finally {
          setGpsLoading(false);
        }
      },
      (err) => {
        setGpsLoading(false);
        setSaveStatus({
          type: "error",
          message: err.code === 1 ? "Location permission denied. Please choose your region manually." : "Could not obtain GPS location.",
        });
      },
      { timeout: 10000, enableHighAccuracy: false }
    );
  };

  const handleSaveProfile = (e) => {
    e.preventDefault();
    if (!displayName.trim()) {
      setSaveStatus({ type: "error", message: "Display name cannot be empty." });
      return;
    }

    const updated = updateGuestName(displayName.trim());
    setSession(updated);
    setSaveStatus({ type: "success", message: "Profile display name updated successfully." });
  };

  const handleConfirmSignOut = () => {
    clearGuestSession();
    if (onSignOut) {
      onSignOut();
    }
  };

  return (
    <main className="main-content profile-page-content" id="profile">
      <div className="profile-page-container">
        {/* Header with Back button */}
        <div className="profile-page-header">
          <button
            type="button"
            className="back-to-home-btn"
            onClick={() => onNavigate && onNavigate("home")}
            aria-label="Back to stations"
          >
            <ArrowLeft size={16} />
            <span>Back to Stations</span>
          </button>

          <div className="profile-title-block">
            <div className="profile-avatar-large">
              <UserRound size={32} />
            </div>
            <div className="profile-identity">
              <h2>Guest Profile &amp; Preferences</h2>
              <p>Manage your display identity, primary residential region, and station discovery baseline</p>
            </div>
          </div>
        </div>

        {/* Feedback Banner */}
        {saveStatus && (
          <div
            className={`profile-feedback-banner ${saveStatus.type === "success" ? "success" : "error"}`}
            role="alert"
          >
            {saveStatus.type === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            <span>{saveStatus.message}</span>
          </div>
        )}

        {/* Card 1: Account & Identity */}
        <div className="profile-card">
          <div className="profile-card-header">
            <div className="profile-section-badge">
              <span>GUEST ACCOUNT</span>
            </div>
            <span className="guest-badge-pill">Local Session</span>
          </div>

          <form onSubmit={handleSaveProfile} className="profile-edit-form">
            <div className="form-group">
              <label htmlFor="displayName" className="form-label">
                Display Name
              </label>
              <div className="input-with-icon">
                <Edit3 size={16} className="field-icon" />
                <input
                  id="displayName"
                  type="text"
                  className="profile-text-input"
                  value={displayName}
                  onChange={(e) => {
                    setDisplayName(e.target.value);
                    setSaveStatus(null);
                  }}
                  maxLength={40}
                  placeholder="e.g. Guest Driver"
                />
              </div>
              <span className="form-hint">Stored locally on your browser. No account registration needed.</span>
            </div>

            <div className="profile-form-actions">
              <button type="submit" className="profile-save-btn">
                <Save size={15} />
                <span>Save Name</span>
              </button>
            </div>
          </form>
        </div>

        {/* Card 2: Residential Region & Reference Location */}
        <div className="profile-card">
          <div className="profile-card-header">
            <div className="profile-section-badge">
              <span>PRIMARY COMMUTE REGION</span>
            </div>
            <span className="region-method-badge">
              {region.detectionMethod === "gps" ? "Detected via GPS" : "Manually Selected"}
            </span>
          </div>

          <div className="current-region-display">
            <div className="region-icon-box">
              <MapPin size={22} />
            </div>
            <div className="region-text-box">
              <span className="region-label-small">Current Reference Region</span>
              <strong className="region-title-strong">{region.name}</strong>
              <span className="region-coords-text">
                {region.detectionMethod === "gps" ? "Verified via Device GPS" : "Commute Locality"} • Primary Reference Area
              </span>
            </div>
          </div>

          {/* Region Action Buttons */}
          {!isEditingRegion ? (
            <div className="region-actions-row">
              <button
                type="button"
                className="region-action-btn primary"
                onClick={() => setIsEditingRegion(true)}
              >
                <Compass size={15} />
                <span>Change Region</span>
              </button>
              <button
                type="button"
                className="region-action-btn secondary"
                onClick={handleDetectGPS}
                disabled={gpsLoading}
              >
                {gpsLoading ? <RotateCw size={15} className="btn-spinner" /> : <LocateFixed size={15} />}
                <span>{gpsLoading ? "Detecting GPS..." : "Detect Location (GPS)"}</span>
              </button>
            </div>
          ) : (
            <div className="region-editor-block" ref={regionSearchRef}>
              <div className="editor-heading-row">
                <strong>Select New Region</strong>
                <button
                  type="button"
                  className="editor-cancel-btn"
                  onClick={() => setIsEditingRegion(false)}
                >
                  Cancel
                </button>
              </div>

              <div className="onboarding-input-wrapper">
                <Search size={16} className="search-field-icon" />
                <input
                  type="text"
                  className="onboarding-search-input"
                  placeholder="Type city, locality, sector or pincode..."
                  value={regionQuery}
                  onChange={(e) => handleRegionQueryChange(e.target.value)}
                  autoFocus
                />
                {suggestionsLoading && <RotateCw size={15} className="btn-spinner onboarding-input-spinner" />}
              </div>

              {/* Suggestions */}
              {showSuggestions && suggestions.length > 0 && (
                <ul className="onboarding-suggestions-dropdown" role="listbox">
                  {suggestions.map((item, index) => (
                    <li
                      key={`prof-sugg-${index}`}
                      className="onboarding-suggestion-item"
                      onClick={() =>
                        applyNewRegion({
                          name: item.label,
                          query: item.label,
                          lat: item.lat,
                          lon: item.lon,
                          detectionMethod: "manual",
                        })
                      }
                      role="option"
                      aria-selected="false"
                    >
                      <MapPin size={14} className="suggestion-icon" />
                      <span>{item.label}</span>
                    </li>
                  ))}
                </ul>
              )}

              {/* Quick suggestions */}
              <div className="onboarding-quick-chips">
                <span className="quick-chips-label">Popular areas:</span>
                <div className="chips-row">
                  {QUICK_REGIONS.map((q) => (
                    <button
                      type="button"
                      key={q.name}
                      className="quick-chip-btn"
                      onClick={() =>
                        applyNewRegion({
                          name: q.name,
                          query: q.query,
                          lat: q.lat,
                          lon: q.lon,
                          detectionMethod: "manual",
                        })
                      }
                    >
                      {q.name}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Card 3: Session Reset / Sign Out */}
        <div className="profile-card danger-card">
          <div className="danger-card-body">
            <div>
              <strong className="danger-card-title">Reset Guest Session</strong>
              <p className="danger-card-desc">
                Clears your saved guest profile and residential region preference. You can re-select a new region upon next launch.
              </p>
            </div>
            {!showSignOutConfirm ? (
              <button
                type="button"
                className="profile-danger-btn"
                onClick={() => setShowSignOutConfirm(true)}
              >
                <LogOut size={15} />
                <span>Reset Session</span>
              </button>
            ) : (
              <div className="signout-confirm-actions">
                <span>Are you sure?</span>
                <button
                  type="button"
                  className="confirm-danger-btn"
                  onClick={handleConfirmSignOut}
                >
                  Yes, Reset
                </button>
                <button
                  type="button"
                  className="cancel-btn"
                  onClick={() => setShowSignOutConfirm(false)}
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

