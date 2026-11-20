import { useState, useRef, useEffect } from "react";
import {
  MapPin,
  Search,
  LocateFixed,
  Zap,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  RotateCw,
  Compass,
  ShieldCheck,
} from "lucide-react";
import { saveGuestSession, saveUserRegion, addHistoryEntry } from "./utils/storage";

const QUICK_REGIONS = [
  { name: "Sector 50, Gurugram", query: "Sector 50 Gurugram", lat: 28.421, lon: 77.062 },
  { name: "Connaught Place, New Delhi", query: "Connaught Place New Delhi", lat: 28.6304, lon: 77.2177 },
  { name: "Sector 45, Gurugram", query: "Sector 45 Gurugram", lat: 28.455, lon: 77.072 },
  { name: "MG Road, Gurugram", query: "MG Road Gurugram", lat: 28.480, lon: 77.086 },
];

export default function GuestOnboarding({ onComplete }) {
  const [step, setStep] = useState("welcome"); // "welcome" | "region_select"
  const [query, setQuery] = useState("");
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  const searchContainerRef = useRef(null);
  const abortControllerRef = useRef(null);

  // Click outside listener for autocomplete suggestions
  useEffect(() => {
    function handleClickOutside(e) {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Fetch location suggestions from Photon
  const handleQueryChange = (text) => {
    setQuery(text);
    setErrorMessage(null);

    const trimmed = text.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setSuggestionsLoading(true);
    const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(trimmed)}&limit=5&lat=28.5&lon=77.1`;

    fetch(url, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error("Search failed");
        return res.json();
      })
      .then((data) => {
        const features = data.features || [];
        const mapped = features.map((feat) => {
          const props = feat.properties || {};
          const coords = feat.geometry?.coordinates || [null, null];
          const parts = [props.name, props.district || props.suburb, props.city, props.state, props.country].filter(Boolean);
          const label = parts.length > 0 ? parts.join(", ") : props.name || "Unknown place";
          return {
            label,
            lon: coords[0],
            lat: coords[1],
            city: props.city || props.district || "",
            state: props.state || "",
          };
        });
        setSuggestions(mapped);
        setShowSuggestions(mapped.length > 0);
      })
      .catch((err) => {
        if (err.name !== "AbortError") {
          setSuggestions([]);
        }
      })
      .finally(() => {
        setSuggestionsLoading(false);
      });
  };

  const handleSelectSuggestion = (item) => {
    setSelectedRegion({
      name: item.label,
      query: item.label,
      lat: item.lat,
      lon: item.lon,
      detectionMethod: "manual",
    });
    setQuery(item.label);
    setShowSuggestions(false);
    setErrorMessage(null);
  };

  const handleSelectQuickRegion = (quick) => {
    setSelectedRegion({
      name: quick.name,
      query: quick.query,
      lat: quick.lat,
      lon: quick.lon,
      detectionMethod: "manual",
    });
    setQuery(quick.name);
    setShowSuggestions(false);
    setErrorMessage(null);
  };

  const handleDetectGPS = () => {
    if (!navigator.geolocation) {
      setErrorMessage("Geolocation is not supported by your browser. Please search manually.");
      return;
    }

    setGpsLoading(true);
    setErrorMessage(null);

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        const fallbackName = `Current Area (${lat.toFixed(3)}°N, ${lon.toFixed(3)}°E)`;

        try {
          // Attempt reverse geocoding via OpenStreetMap backend
          const res = await fetch(`http://127.0.0.1:8001/api/location/discover?lat=${lat}&lon=${lon}&radius=5000`);
          if (res.ok) {
            const data = await res.json();
            const resolvedName = data.resolved_location?.display_name || fallbackName;
            setSelectedRegion({
              name: resolvedName,
              query: resolvedName,
              lat,
              lon,
              detectionMethod: "gps",
            });
            setQuery(resolvedName);
          } else {
            setSelectedRegion({
              name: fallbackName,
              query: `${lat},${lon}`,
              lat,
              lon,
              detectionMethod: "gps",
            });
            setQuery(fallbackName);
          }
        } catch {
          setSelectedRegion({
            name: fallbackName,
            query: `${lat},${lon}`,
            lat,
            lon,
            detectionMethod: "gps",
          });
          setQuery(fallbackName);
        } finally {
          setGpsLoading(false);
        }
      },
      (err) => {
        setGpsLoading(false);
        if (err.code === 1) {
          setErrorMessage("Location permission was denied. Please select your region manually from the list or search box.");
        } else {
          setErrorMessage("Could not detect location. Please type your city or area manually.");
        }
      },
      { timeout: 10000, enableHighAccuracy: false }
    );
  };

  const handleConfirmAndEnter = () => {
    if (!selectedRegion) {
      if (query.trim().length >= 2) {
        // Use free text if user entered something without picking from dropdown
        const freeTextRegion = {
          name: query.trim(),
          query: query.trim(),
          lat: null,
          lon: null,
          detectionMethod: "manual",
        };
        saveGuestSession();
        saveUserRegion(freeTextRegion);
        addHistoryEntry({
          type: "region_change",
          title: freeTextRegion.name,
          summary: "Selected residential region during guest onboarding",
          tag: "Region Onboarding",
        });
        if (onComplete) onComplete(freeTextRegion);
        return;
      }
      setErrorMessage("Please select or search your region before proceeding to the dashboard.");
      return;
    }

    saveGuestSession();
    saveUserRegion(selectedRegion);
    addHistoryEntry({
      type: "region_change",
      title: selectedRegion.name,
      summary: `Set residential region to ${selectedRegion.name} (${selectedRegion.detectionMethod === "gps" ? "GPS" : "Manual"})`,
      tag: "Region Onboarding",
    });
    if (onComplete) onComplete(selectedRegion);
  };

  return (
    <div className="onboarding-overlay" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
      <div className="onboarding-card">
        {step === "welcome" ? (
          <div className="onboarding-welcome-step">
            <div className="onboarding-logo-badge">
              <img src="/logo-icon.png" alt="NoQueue Logo" className="onboarding-logo-img" />
            </div>

            <div className="onboarding-header">
              <span className="onboarding-eyebrow">
                <Zap size={14} /> SMART CNG MOBILITY
              </span>
              <h1 id="onboarding-title">
                Welcome to <span>NoQueue</span>
              </h1>
              <p className="onboarding-desc">
                Find nearby CNG stations, bypass long queues with predictive multi-dispenser simulations, and optimize your journey time.
              </p>
            </div>

            <div className="onboarding-feature-list">
              <div className="onboarding-feature-item">
                <div className="feature-icon-wrapper">
                  <Compass size={18} />
                </div>
                <div>
                  <strong>Live CNG Station Discovery</strong>
                  <p>OpenStreetMap fuel registry with verified CNG dispensers</p>
                </div>
              </div>
              <div className="onboarding-feature-item">
                <div className="feature-icon-wrapper">
                  <Zap size={18} />
                </div>
                <div>
                  <strong>Multi-Dispenser Predictive Queue</strong>
                  <p>Parallel bay tracking &amp; 15/30/60m Monte Carlo forecasts</p>
                </div>
              </div>
            </div>

            <div className="onboarding-actions">
              <button
                type="button"
                className="onboarding-primary-btn"
                onClick={() => setStep("region_select")}
              >
                <span>Continue as Guest</span>
                <ArrowRight size={17} />
              </button>
            </div>

            <div className="onboarding-trust-note">
              <ShieldCheck size={14} className="trust-icon" />
              <span>No password or registration required. Instant guest access saved on this device.</span>
            </div>
          </div>
        ) : (
          <div className="onboarding-region-step">
            <div className="onboarding-header">
              <span className="onboarding-eyebrow">
                <MapPin size={14} /> MANDATORY RESIDENTIAL REGION
              </span>
              <h2 id="onboarding-title">Which region do you live in?</h2>
              <p className="onboarding-desc">
                Select your city or daily commuting area. NoQueue uses this as your initial reference point for station recommendations.
              </p>
            </div>

            {/* Search Box */}
            <div className="onboarding-search-container" ref={searchContainerRef}>
              <div className="onboarding-input-wrapper">
                <Search size={18} className="search-field-icon" />
                <input
                  type="text"
                  className="onboarding-search-input"
                  placeholder="Enter city, locality or pincode..."
                  value={query}
                  onChange={(e) => handleQueryChange(e.target.value)}
                  autoFocus
                />
                {suggestionsLoading && (
                  <RotateCw size={16} className="btn-spinner onboarding-input-spinner" />
                )}
              </div>

              {/* Suggestions Dropdown */}
              {showSuggestions && suggestions.length > 0 && (
                <ul className="onboarding-suggestions-dropdown" role="listbox">
                  {suggestions.map((item, index) => (
                    <li
                      key={`sugg-${index}`}
                      className="onboarding-suggestion-item"
                      onClick={() => handleSelectSuggestion(item)}
                      role="option"
                      aria-selected="false"
                    >
                      <MapPin size={14} className="suggestion-icon" />
                      <span>{item.label}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* GPS Locate Action */}
            <div className="onboarding-gps-row">
              <button
                type="button"
                className="onboarding-gps-btn"
                onClick={handleDetectGPS}
                disabled={gpsLoading}
              >
                {gpsLoading ? (
                  <RotateCw size={15} className="btn-spinner" />
                ) : (
                  <LocateFixed size={15} />
                )}
                <span>{gpsLoading ? "Detecting coordinates..." : "Detect my current location (GPS)"}</span>
              </button>
            </div>

            {/* Error Banner */}
            {errorMessage && (
              <div className="onboarding-error-banner" role="alert">
                <AlertCircle size={16} />
                <span>{errorMessage}</span>
              </div>
            )}

            {/* Selected Region Confirmation Card */}
            {selectedRegion && (
              <div className="onboarding-selected-card">
                <CheckCircle2 size={18} className="selected-card-icon" />
                <div className="selected-card-body">
                  <span className="selected-card-label">SELECTED REGION</span>
                  <strong>{selectedRegion.name}</strong>
                  <span className="selected-card-method">
                    {selectedRegion.detectionMethod === "gps" ? "Detected via GPS" : "Manually selected"}
                  </span>
                </div>
              </div>
            )}

            {/* Quick Suggestions Chips */}
            <div className="onboarding-quick-chips">
              <span className="quick-chips-label">Popular areas:</span>
              <div className="chips-row">
                {QUICK_REGIONS.map((quick) => (
                  <button
                    type="button"
                    key={quick.name}
                    className={`quick-chip-btn ${selectedRegion?.name === quick.name ? "active" : ""}`}
                    onClick={() => handleSelectQuickRegion(quick)}
                  >
                    {quick.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Confirm & Enter Button */}
            <div className="onboarding-actions">
              <button
                type="button"
                className="onboarding-primary-btn"
                onClick={handleConfirmAndEnter}
                disabled={!selectedRegion && query.trim().length < 2}
              >
                <span>Confirm Region &amp; Enter Dashboard</span>
                <ArrowRight size={17} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

