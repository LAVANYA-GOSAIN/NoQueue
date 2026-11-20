import { useState, useEffect, useRef, useMemo } from "react";
import SplashScreen from "./SplashScreen";
import QueueForecastSection from "./QueueForecast";
import GuestOnboarding from "./GuestOnboarding";
import ProfilePage from "./ProfilePage";
import HistoryPage from "./HistoryPage";
import {
  getGuestSession,
  getUserRegion,
  addHistoryEntry,
  clearGuestSession,
} from "./utils/storage";
import {
  MapPin,
  Search,
  Navigation,
  Clock,
  Fuel,
  Zap,
  History,
  UserRound,
  LocateFixed,
  ArrowUpRight,
  Gauge,
  RotateCw,
  AlertCircle,
  CheckCircle2,
  HelpCircle,
  X,
  Compass,
  ArrowDown,
  ArrowUp,
  ArrowLeft,
  ChevronDown,
} from "lucide-react";
import "./App.css";

const DASHBOARD_API_URL = "http://127.0.0.1:8001/api/dashboard";
const DISCOVER_API_URL = "http://127.0.0.1:8001/api/location/discover";
const REFRESH_API_URL = "http://127.0.0.1:8001/api/location/refresh";
const CLEAR_API_URL = "http://127.0.0.1:8001/api/location/clear";

const QUICK_SUGGESTIONS = [
  "Sector 45, Gurugram",
  "Sector 50, Gurugram",
  "Connaught Place, New Delhi",
];

/**
 * Classifies station queue congestion based on estimated waiting time in minutes:
 * - LOW: 0–10 minutes (Green)
 * - MEDIUM: 11–20 minutes (Amber/Yellow)
 * - HIGH: Above 20 minutes (Red)
 *
 * @param {number|string} waitTimeMinutes
 * @returns {{ level: "LOW"|"MEDIUM"|"HIGH", className: string, label: string }}
 */
function getCongestionStatus(waitTimeMinutes) {
  const wait =
    typeof waitTimeMinutes === "number"
      ? waitTimeMinutes
      : parseFloat(waitTimeMinutes) || 0;

  if (wait <= 10) {
    return {
      level: "LOW",
      className: "congestion-low",
      label: "LOW",
    };
  }
  if (wait <= 20) {
    return {
      level: "MEDIUM",
      className: "congestion-medium",
      label: "MEDIUM",
    };
  }
  return {
    level: "HIGH",
    className: "congestion-high",
    label: "HIGH",
  };
}

function mapBackendStation(item) {
  const travelTime =
    item.travel_time_minutes ??
    (typeof item.estimated_travel_time === "number"
      ? item.estimated_travel_time
      : parseInt(item.estimated_travel_time, 10)) ??
    item.travelTime ??
    0;

  const waitTime =
    item.estimated_waiting_time_minutes ??
    (typeof item.estimated_waiting_time === "number"
      ? item.estimated_waiting_time
      : parseInt(item.estimated_waiting_time, 10)) ??
    item.waitTime ??
    0;

  const queue = item.queue_length ?? item.queue ?? 0;
  const crowd = item.crowd_level ?? item.crowd ?? "Moderate";
  const congestion = getCongestionStatus(waitTime);

  return {
    id: item.id,
    name: item.name,
    address: item.address,
    distance: item.distance_text || item.distance || (item.distance_km ? `${item.distance_km} km` : "N/A"),
    distance_km: item.distance_km,
    distance_type: item.distance_type || "road",
    routing_engine: item.routing_engine || "osrm",
    is_road_network: item.is_road_network ?? true,
    travelTime: roundToTwo(travelTime),
    waitTime: roundToTwo(waitTime),
    totalJourneyTime: roundToTwo(item.estimated_total_journey_time_minutes ?? (travelTime + waitTime)),
    queue,
    crowd,
    congestion,
    estimated_travel_time:
      item.estimated_travel_time || `${roundToTwo(travelTime)} min`,
    estimated_waiting_time:
      item.estimated_waiting_time || `${roundToTwo(waitTime)} min`,
    queue_length: queue,
    waiting_queue_length: item.waiting_queue_length ?? queue,
    vehicles_being_served: item.vehicles_being_served ?? 0,
    total_vehicles: item.total_vehicles ?? queue,
    dispenser_count: item.dispenser_count ?? null,
    simulator_engine: item.simulator_engine || "legacy",
    forecast_trials: item.forecast_trials || 100,
    crowd_level: crowd,
    queue_forecast: item.queue_forecast || null,
  };
}

function mapRecommendation(data) {
  const station = data.station || {};
  const travelTime =
    data.estimated_travel_time_minutes ??
    station.travel_time_minutes ??
    station.travelTime ??
    0;

  const waitTime =
    data.estimated_waiting_time_minutes ??
    station.estimated_waiting_time_minutes ??
    station.waitTime ??
    0;

  const totalJourneyTime =
    data.estimated_total_journey_time_minutes ??
    roundToTwo(travelTime + waitTime);

  const queue = station.queue_length ?? station.queue ?? 0;
  const crowd = station.crowd_level ?? station.crowd ?? "Moderate";
  const congestion = getCongestionStatus(waitTime);

  return {
    id: station.id,
    name: station.name || data.station_name,
    address: station.address || "Nearby Area",
    distance: data.distance || station.distance || station.distance_text || (station.distance_km ? `${station.distance_km} km` : "N/A"),
    distance_km: data.distance_km ?? station.distance_km,
    distance_type: data.distance_type || station.distance_type || "road",
    routing_engine: data.routing_engine || station.routing_engine || "osrm",
    is_road_network: data.is_road_network ?? station.is_road_network ?? true,
    latitude: station.latitude,
    longitude: station.longitude,
    travelTime: roundToTwo(travelTime),
    waitTime: roundToTwo(waitTime),
    totalJourneyTime: roundToTwo(totalJourneyTime),
    queue,
    waiting_queue_length: station.waiting_queue_length ?? data.waiting_queue_length ?? queue,
    vehicles_being_served: station.vehicles_being_served ?? data.vehicles_being_served ?? 0,
    total_vehicles: station.total_vehicles ?? data.total_vehicles ?? queue,
    dispenser_count: station.dispenser_count ?? data.dispenser_count ?? null,
    simulator_engine: station.simulator_engine ?? data.simulator_engine ?? "legacy",
    forecast_trials: station.forecast_trials ?? data.forecast_trials ?? 100,
    crowd,
    congestion,
    decisionMode: data.decision_mode || "learned_policy",
    fallbackStatus: Boolean(data.fallback_status),
    context: data.context || "N/A",
    predictedQ: data.predicted_q_value,
    queue_forecast: data.queue_forecast || station.queue_forecast || null,
  };
}

function roundToTwo(num) {
  return Math.round((num + Number.EPSILON) * 100) / 100;
}

function App() {
  // Demonstration / Persistent Simulation state
  const [stations, setStations] = useState([]);
  const [recommendation, setRecommendation] = useState(null);
  const [selectedStationId, setSelectedStationId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState("");
  const [disclaimer, setDisclaimer] = useState(
    "Road distances and driving durations are calculated via static OSRM road-network topology (not live traffic). Station queue metrics are simulated."
  );

  // Search & Dynamic OSM Discovery state
  const [location, setLocation] = useState("");
  const [searchedLocation, setSearchedLocation] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [currentLocationLoading, setCurrentLocationLoading] = useState(false);
  const [pendingQuery, setPendingQuery] = useState("");
  const [searchError, setSearchError] = useState(null);
  const [searchResult, setSearchResult] = useState(null);
  const [isUnverifiedExpanded, setIsUnverifiedExpanded] = useState(false);

  // Guest Session & Mandatory Region state (LocalStorage-backed)
  const [guestSession, setGuestSession] = useState(() => getGuestSession());
  const [userRegion, setUserRegion] = useState(() => getUserRegion());
  const isGuestOnboardingRequired = !guestSession || !userRegion;

  // Navigation & Page Routing state (hash-based to support browser refresh and back/forward)
  const [currentPage, setCurrentPage] = useState(() => {
    const hash = typeof window !== "undefined" ? window.location.hash.toLowerCase() : "";
    if (hash === "#profile") return "profile";
    if (hash === "#history") return "history";
    return "home";
  });
  const [showSplash, setShowSplash] = useState(true);

  const navigateTo = (page) => {
    setCurrentPage(page);
    window.location.hash = page === "home" ? "#home" : `#${page}`;
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.toLowerCase();
      if (hash === "#profile") {
        setCurrentPage("profile");
      } else if (hash === "#history") {
        setCurrentPage("history");
      } else {
        setCurrentPage("home");
      }
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  // Autocomplete Suggestions (Photon by Komoot - OSM based)
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const searchContainerRef = useRef(null);
  const autocompleteAbortRef = useRef(null);
  const autocompleteTimerRef = useRef(null);
  const suggestionsCacheRef = useRef(new Map());

  // Distance Sorting ('asc' = nearest first, 'desc' = farthest first)
  const [sortOrder, setSortOrder] = useState("asc");

  // Request race-condition and abort controllers
  const latestRequestIdRef = useRef(0);
  const activeSearchAbortControllerRef = useRef(null);
  const activeLocationRef = useRef(null);

  // Client-side distance sorting for verified CNG stations
  const sortedVerifiedStations = useMemo(() => {
    if (!searchResult?.verifiedCngStations) return [];
    const list = [...searchResult.verifiedCngStations];
    return list.sort((a, b) => {
      const distA =
        typeof a.distance_km === "number"
          ? a.distance_km
          : parseFloat(a.distance_km) || 0;
      const distB =
        typeof b.distance_km === "number"
          ? b.distance_km
          : parseFloat(b.distance_km) || 0;
      return sortOrder === "desc" ? distB - distA : distA - distB;
    });
  }, [searchResult, sortOrder]);

  // Active station selected for predictive queue forecast (defaults to recommended station for active search)
  const activeForecastStation = useMemo(() => {
    if (!searchResult || !searchResult.verifiedCngStations || searchResult.verifiedCngStations.length === 0) {
      return null;
    }
    if (selectedStationId !== null) {
      const found = searchResult.verifiedCngStations.find(
        (s) => (s.id ?? s.osm_id) === selectedStationId
      );
      if (found) return found;

      if (
        recommendation &&
        (recommendation.id === selectedStationId ||
          recommendation.station_id === selectedStationId)
      ) {
        return recommendation;
      }
    }
    return recommendation;
  }, [selectedStationId, searchResult, recommendation]);

  const isForecastRecommended = useMemo(() => {
    if (!activeForecastStation || !recommendation) return true;
    const activeId = activeForecastStation.id ?? activeForecastStation.osm_id;
    const recId = recommendation.id ?? recommendation.station_id;
    return selectedStationId === null || activeId === recId;
  }, [activeForecastStation, recommendation, selectedStationId]);

  // Click outside to dismiss autocomplete dropdown
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(event.target)
      ) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Fetch suggestions using Photon (OSM-based autocomplete) with debouncing & in-memory caching
  const fetchAutocompleteSuggestions = (text) => {
    const trimmed = text.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setSuggestionsLoading(false);
      setShowSuggestions(false);
      return;
    }

    const cacheKey = trimmed.toLowerCase();
    if (suggestionsCacheRef.current.has(cacheKey)) {
      setSuggestions(suggestionsCacheRef.current.get(cacheKey));
      setSuggestionsLoading(false);
      setShowSuggestions(true);
      return;
    }

    if (autocompleteAbortRef.current) {
      autocompleteAbortRef.current.abort();
    }
    const controller = new AbortController();
    autocompleteAbortRef.current = controller;

    setSuggestionsLoading(true);

    // Photon endpoint biased around India coordinates
    const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(
      trimmed
    )}&limit=5&lat=28.5&lon=77.1`;

    fetch(url, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error("Autocomplete request failed");
        return res.json();
      })
      .then((data) => {
        const items = (data.features || [])
          .map((f) => {
            const p = f.properties || {};
            const name = p.name || "";
            const parts = [p.district, p.city, p.state, p.country]
              .filter(Boolean)
              .filter(
                (item, idx, arr) => arr.indexOf(item) === idx && item !== name
              );
            const secondary = parts.join(", ");
            const fullQuery = p.city ? `${name}, ${p.city}` : name;
            // Extract coordinates directly from GeoJSON geometry [longitude, latitude]
            const coords = f.geometry?.coordinates;
            const lon = coords && coords.length >= 2 ? coords[0] : null;
            const lat = coords && coords.length >= 2 ? coords[1] : null;

            return {
              id: `${p.osm_type || "N"}-${p.osm_id || Math.random()}`,
              name,
              secondary,
              fullQuery: fullQuery || name,
              lat,
              lon,
            };
          })
          .filter((item) => item.name);

        suggestionsCacheRef.current.set(cacheKey, items);
        setSuggestions(items);
        setHighlightedIndex(-1);
        setShowSuggestions(true);
      })
      .catch((err) => {
        if (err.name !== "AbortError") {
          console.warn("Photon autocomplete warning:", err);
          setSuggestions([]);
        }
      })
      .finally(() => {
        setSuggestionsLoading(false);
      });
  };

  const handleInputChange = (event) => {
    const val = event.target.value;
    setLocation(val);
    if (searchError) setSearchError(null);

    if (autocompleteTimerRef.current) {
      clearTimeout(autocompleteTimerRef.current);
    }

    if (!val.trim() || val.trim().length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      setSuggestionsLoading(false);
      return;
    }

    // Debounce keystrokes by 300ms to respect public API policies
    autocompleteTimerRef.current = setTimeout(() => {
      fetchAutocompleteSuggestions(val);
    }, 300);
  };

  const selectSuggestion = (sug) => {
    const chosen = sug.fullQuery || sug.name;
    setLocation(chosen);
    setShowSuggestions(false);
    setSuggestions([]);

    // If Photon provides coordinates, pass them directly to skip redundant geocoding
    if (typeof sug.lat === "number" && typeof sug.lon === "number") {
      handleLocationSearch({
        lat: sug.lat,
        lon: sug.lon,
        label: chosen,
      });
    } else {
      handleLocationSearch(chosen);
    }
  };

  const handleInputKeyDown = (event) => {
    if (showSuggestions && suggestions.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setHighlightedIndex((prev) =>
          prev < suggestions.length - 1 ? prev + 1 : 0
        );
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setHighlightedIndex((prev) =>
          prev > 0 ? prev - 1 : suggestions.length - 1
        );
        return;
      }
      if (event.key === "Enter" && highlightedIndex >= 0) {
        event.preventDefault();
        selectSuggestion(suggestions[highlightedIndex]);
        return;
      }
      if (event.key === "Escape") {
        setShowSuggestions(false);
        return;
      }
    }

    if (event.key === "Enter") {
      event.preventDefault();
      setShowSuggestions(false);
      handleLocationSearch(location);
    }
  };

  const handleSearchSubmit = (e) => {
    if (e && typeof e.preventDefault === "function") {
      e.preventDefault();
    }
    setShowSuggestions(false);
    handleLocationSearch(location);
  };

  const fetchDashboard = async (isInitial = false) => {
    try {
      if (isInitial) {
        setLoading(true);
        setError(null);
      }

      const response = await fetch(DASHBOARD_API_URL);
      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }
      const data = await response.json();

      if (data.disclaimer) {
        setDisclaimer(data.disclaimer);
      }

      if (data.timestamp) {
        const dateObj = new Date(data.timestamp);
        const formatted = isNaN(dateObj.getTime())
          ? data.timestamp
          : dateObj.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
        setLastUpdated(formatted);
      }

      const rawStations = Array.isArray(data.stations) ? data.stations : [];
      setStations(rawStations.map(mapBackendStation));

      // Only set Gurugram benchmark recommendation if no location search is active
      if (!activeLocationRef.current && data.recommendation) {
        setRecommendation(mapRecommendation(data.recommendation));
      }

      setError(null);
    } catch (err) {
      console.error("Dashboard fetch error:", err);
      if (isInitial || stations.length === 0) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load live dashboard from backend"
        );
      }
    } finally {
      if (isInitial) {
        setLoading(false);
      }
    }
  };

  const refreshActiveLocation = async () => {
    if (!activeLocationRef.current) return;
    try {
      const response = await fetch(REFRESH_API_URL);
      if (!response.ok) return;
      const data = await response.json();
      if (data.status === "no_active_location") return;

      if (data.last_updated || data.timestamp) {
        const timeStr = data.last_updated || data.timestamp;
        const dateObj = new Date(timeStr);
        const formatted = isNaN(dateObj.getTime())
          ? timeStr
          : dateObj.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
        setLastUpdated(formatted);
      }

      setSearchResult((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          verifiedCngStations: Array.isArray(data.verified_cng_stations)
            ? data.verified_cng_stations
            : prev.verifiedCngStations,
          otherFuelStations: Array.isArray(data.other_fuel_stations)
            ? data.other_fuel_stations
            : prev.otherFuelStations,
          totalStationsFound: data.total_stations_found ?? prev.totalStationsFound,
          verifiedCount: data.verified_cng_count ?? prev.verifiedCount,
          otherCount: data.other_fuel_count ?? prev.otherCount,
        };
      });

      if (data.recommendation) {
        setRecommendation(mapRecommendation(data.recommendation));
      } else {
        setRecommendation(null);
      }
    } catch (err) {
      console.warn("Location refresh error:", err);
    }
  };

  useEffect(() => {
    fetchDashboard(true);
    if (userRegion) {
      handleLocationSearch(userRegion);
    }
  }, []);

  useEffect(() => {
    // Dynamic persistent synthetic simulation polling every 10 seconds
    const intervalId = setInterval(() => {
      if (activeLocationRef.current) {
        refreshActiveLocation();
      } else {
        fetchDashboard(false);
      }
    }, 10000);

    return () => clearInterval(intervalId);
  }, []);

  const handleOnboardingComplete = (selectedRegion) => {
    setGuestSession(getGuestSession());
    setUserRegion(selectedRegion);
    handleLocationSearch(selectedRegion);
    navigateTo("home");
  };

  const handleResetSession = () => {
    clearGuestSession();
    setGuestSession(null);
    setUserRegion(null);
    navigateTo("home");
  };

  async function handleLocationSearch(target) {
    // If an existing request is active, abort it
    if (activeSearchAbortControllerRef.current) {
      activeSearchAbortControllerRef.current.abort();
    }

    let queryParam = "";
    let latParam = null;
    let lonParam = null;

    if (typeof target === "object" && target !== null) {
      latParam = target.lat;
      lonParam = target.lon;
      queryParam = target.label || target.query || "";
    } else {
      queryParam = (typeof target === "string" ? target : location).trim();
    }

    if (!queryParam && (latParam === null || lonParam === null)) {
      setSearchError(
        "Please enter a locality, city or pincode to search, or click 'Use my current location'."
      );
      return;
    }

    if (latParam === null && lonParam === null && queryParam.length < 2) {
      setSearchError("Search query must contain at least 2 characters.");
      return;
    }

    // Set up AbortController and request ID for this execution
    const controller = new AbortController();
    activeSearchAbortControllerRef.current = controller;
    const currentRequestId = ++latestRequestIdRef.current;

    const displayQuery =
      queryParam ||
      (latParam !== null && lonParam !== null
        ? `Location (${Number(latParam).toFixed(4)}°, ${Number(lonParam).toFixed(4)}°)`
        : "");

    setPendingQuery(displayQuery);
    setSearchLoading(true);
    setSearchError(null);
    setShowSuggestions(false);
    setSuggestions([]);
    setIsUnverifiedExpanded(false);

    try {
      let url = `${DISCOVER_API_URL}?radius=5000`;
      if (latParam !== null && lonParam !== null) {
        url += `&lat=${encodeURIComponent(latParam)}&lon=${encodeURIComponent(
          lonParam
        )}`;
        if (queryParam) {
          url += `&query=${encodeURIComponent(queryParam)}`;
        }
      } else {
        url += `&query=${encodeURIComponent(queryParam)}`;
      }

      const response = await fetch(url, { signal: controller.signal });
      const data = await response.json();

      // Ensure older responses cannot overwrite newer search results
      if (currentRequestId !== latestRequestIdRef.current) {
        return;
      }

      if (!response.ok) {
        const errorMsg =
          data.detail ||
          data.message ||
          `Server returned HTTP ${response.status}: Failed to resolve location.`;
        throw new Error(errorMsg);
      }

      activeLocationRef.current = {
        query: displayQuery,
        lat: latParam,
        lon: lonParam,
      };

      const mappedRec = data.recommendation ? mapRecommendation(data.recommendation) : null;
      setRecommendation(mappedRec);
      setSelectedStationId(null);

      setSearchResult({
        query: displayQuery,
        resolvedLocation: data.resolved_location || {},
        verifiedCngStations: Array.isArray(data.verified_cng_stations)
          ? data.verified_cng_stations
          : [],
        otherFuelStations: Array.isArray(data.other_fuel_stations)
          ? data.other_fuel_stations
          : [],
        searchRadiusKm: data.search_radius_km || 5,
        totalStationsFound: data.total_stations_found || 0,
        verifiedCount: data.verified_cng_count || 0,
        otherCount: data.other_fuel_count || 0,
        message: data.message || "",
        discoveryEngine: data.discovery_engine || "OpenStreetMap",
      });

      const shortLoc =
        data.resolved_location?.display_name?.split(",")[0] || displayQuery;
      setSearchedLocation(shortLoc);
      setLocation(displayQuery);

      addHistoryEntry({
        type: "search",
        title: shortLoc || displayQuery,
        summary: `Discovered ${data.verified_cng_count || 0} verified CNG station(s) within ${data.search_radius_km || 5} km`,
        tag: "OpenStreetMap Discovery",
      });

      if (mappedRec) {
        addHistoryEntry({
          type: "recommendation",
          title: mappedRec.name || "AI Recommended Station",
          summary: `Top recommendation with ${mappedRec.travelTime || 0}m total journey (${mappedRec.waitingTime || 0}m queue wait)`,
          tag: "AI Policy Recommendation",
        });
      }
    } catch (err) {
      if (err.name === "AbortError") {
        return;
      }
      console.error("Location search error:", err);
      if (currentRequestId === latestRequestIdRef.current) {
        setSearchError(
          err instanceof Error
            ? err.message
            : "Unable to discover stations for this location."
        );
      }
    } finally {
      if (currentRequestId === latestRequestIdRef.current) {
        setSearchLoading(false);
        setPendingQuery("");
        setCurrentLocationLoading(false);
      }
    }
  };

  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      setSearchError(
        "Geolocation is not supported by your browser. Please search manually."
      );
      return;
    }

    if (searchLoading || currentLocationLoading) {
      return;
    }

    setCurrentLocationLoading(true);
    setSearchError(null);
    setShowSuggestions(false);
    setPendingQuery("Detecting current location...");

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        handleLocationSearch({
          lat: latitude,
          lon: longitude,
          label: "My Current Location",
        });
      },
      (geoError) => {
        setCurrentLocationLoading(false);
        setSearchLoading(false);
        setPendingQuery("");
        let msg = "Unable to retrieve your current location.";
        if (geoError.code === 1) {
          msg =
            "Location permission was denied. Please allow location access in your browser or search manually.";
        } else if (geoError.code === 2) {
          msg =
            "Location information is unavailable. Please check your network/GPS connection or search manually.";
        } else if (geoError.code === 3) {
          msg = "Location request timed out. Please try again or search manually.";
        }
        setSearchError(msg);
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 60000,
      }
    );
  };

  const handleClearSearch = () => {
    if (activeSearchAbortControllerRef.current) {
      activeSearchAbortControllerRef.current.abort();
    }
    latestRequestIdRef.current++;
    activeLocationRef.current = null;
    setSearchResult(null);
    setRecommendation(null);
    setStations([]);
    setSelectedStationId(null);
    setSearchError(null);
    setSearchLoading(false);
    setCurrentLocationLoading(false);
    setPendingQuery("");
    setShowSuggestions(false);
    setSuggestions([]);
    setSortOrder("asc");
    setLocation("");
    setSearchedLocation("");
    setIsUnverifiedExpanded(false);
    fetch(CLEAR_API_URL, { method: "POST" }).catch(() => { });
  };

  const openDirections = (station) => {
    if (!station) return;
    addHistoryEntry({
      type: "directions",
      title: station.name || "CNG Station",
      summary: `Navigating to ${station.address || "Station"}`,
      tag: "Google Maps Navigation",
    });
    if (station.latitude && station.longitude) {
      window.open(
        `https://www.google.com/maps/dir/?api=1&destination=${station.latitude},${station.longitude}`,
        "_blank",
        "noopener,noreferrer"
      );
    } else {
      const query = encodeURIComponent(
        `${station.name}, ${station.address || ""}`
      );
      window.open(
        `https://www.google.com/maps/search/?api=1&query=${query}`,
        "_blank",
        "noopener,noreferrer"
      );
    }
  };

  return (
    <div className="app-shell">
      {showSplash && <SplashScreen onFinish={() => setShowSplash(false)} />}
      <header className="topbar">
        <a
          className="brand"
          href="#home"
          onClick={(e) => {
            e.preventDefault();
            navigateTo("home");
            handleClearSearch();
          }}
        >
          <span className="brand-icon">
            <img
              src="/logo-icon.png"
              alt="NoQueue Logo"
              className="brand-logo-img"
            />
          </span>
          <span>
            No<span>Queue</span>
          </span>
        </a>

        <div className="topbar-right">
          <div
            className="live-update-badge"
            title="Persistent synthetic queue simulator advances dynamically"
          >
            <span className="live-dot" />
            <span>Simulated live update</span>
            {lastUpdated && <span className="update-time">· {lastUpdated}</span>}
          </div>
          <span className="location-label" title={searchedLocation || userRegion?.name || "Region"}>
            <MapPin size={15} /> {searchedLocation || userRegion?.name || "Select Region"}
          </span>
          <button
            className={`history-button ${currentPage === "history" ? "active" : ""}`}
            aria-label="Activity History"
            title={currentPage === "history" ? "Back to Stations" : "Open Activity History"}
            onClick={() => navigateTo(currentPage === "history" ? "home" : "history")}
          >
            <History size={18} />
          </button>
          <button
            className={`profile-button ${currentPage === "profile" ? "active" : ""}`}
            aria-label="User Profile"
            title={currentPage === "profile" ? "Back to Stations" : "Open Profile"}
            onClick={() => navigateTo(currentPage === "profile" ? "home" : "profile")}
          >
            <UserRound size={19} />
          </button>
        </div>
      </header>

      {isGuestOnboardingRequired && (
        <GuestOnboarding onComplete={handleOnboardingComplete} />
      )}

      {currentPage === "profile" ? (
        <ProfilePage
          onNavigate={navigateTo}
          onRegionChange={(newRegion) => {
            setUserRegion(newRegion);
            handleLocationSearch(newRegion);
          }}
          onSignOut={handleResetSession}
        />
      ) : currentPage === "history" ? (
        <HistoryPage onNavigate={navigateTo} />
      ) : (
        <main className="main-content" id="stations">
          <section className="search-section">
            <div className="search-box-wrapper">
              <form
                onSubmit={handleSearchSubmit}
                className={`search-box ${showSuggestions && suggestions.length > 0 ? "has-suggestions" : ""}`}
              >
                <Search size={18} className="search-pin" />
                <input
                  type="text"
                  value={location}
                  onChange={handleInputChange}
                  onKeyDown={handleInputKeyDown}
                  placeholder="Search locality, city or landmark..."
                />
                {suggestionsLoading && (
                  <div className="input-spinner" title="Searching places...">
                    <RotateCw size={15} className="btn-spinner" />
                  </div>
                )}
                {searchResult && (
                  <button
                    type="button"
                    className="clear-icon-button"
                    onClick={handleClearSearch}
                    aria-label="Clear search"
                    title="Clear search and reset location"
                  >
                    <X size={17} />
                  </button>
                )}
                <button
                  type="submit"
                  className="search-button"
                  disabled={searchLoading || currentLocationLoading}
                  onClick={(e) => {
                    e.preventDefault();
                    setShowSuggestions(false);
                    handleLocationSearch(location);
                  }}
                  aria-label="Submit search"
                >
                  {searchLoading ? (
                    <>
                      <RotateCw size={17} className="btn-spinner" />
                      <span>Searching...</span>
                    </>
                  ) : (
                    <>
                      <Search size={18} />
                      <span>Search</span>
                    </>
                  )}
                </button>
              </form>

              {/* Autocomplete Dropdown (Photon by Komoot - OSM based) */}
              {showSuggestions && (
                <div className="autocomplete-dropdown" role="listbox">
                  {suggestions.length > 0 ? (
                    suggestions.map((item, index) => (
                      <div
                        key={item.id}
                        className={`suggestion-item ${index === highlightedIndex ? "highlighted" : ""
                          }`}
                        onClick={() => selectSuggestion(item)}
                        onMouseEnter={() => setHighlightedIndex(index)}
                        role="option"
                        aria-selected={index === highlightedIndex}
                      >
                        <div className="suggestion-icon">
                          <MapPin size={16} />
                        </div>
                        <div className="suggestion-content">
                          <span className="suggestion-primary">{item.name}</span>
                          {item.secondary && (
                            <span className="suggestion-secondary">
                              {item.secondary}
                            </span>
                          )}
                        </div>
                        <ArrowUpRight size={14} className="suggestion-arrow" />
                      </div>
                    ))
                  ) : suggestionsLoading ? (
                    <div className="suggestion-status">
                      <RotateCw size={14} className="btn-spinner" />
                      <span>Searching places via OpenStreetMap...</span>
                    </div>
                  ) : location.trim().length >= 3 ? (
                    <div className="suggestion-status no-results">
                      <span>
                        No suggestions found. Press Enter to search directly.
                      </span>
                    </div>
                  ) : null}
                </div>
              )}
            </div>

            <div className="search-meta-row">
              <div className="search-meta-left">
                <button
                  type="button"
                  className="current-location-pill"
                  onClick={handleUseCurrentLocation}
                  disabled={searchLoading || currentLocationLoading}
                  title="Detect and discover CNG stations near your GPS coordinates"
                >
                  {currentLocationLoading ? (
                    <>
                      <RotateCw size={14} className="btn-spinner" />
                      <span>Detecting location...</span>
                    </>
                  ) : (
                    <>
                      <LocateFixed size={14} />
                      <span>Use my current location</span>
                    </>
                  )}
                </button>
              </div>
              <div className="quick-suggestions">
                <span className="suggestion-label">Quick try:</span>
                {QUICK_SUGGESTIONS.map((sug) => (
                  <button
                    key={sug}
                    type="button"
                    className={`suggestion-chip ${location === sug ? "active" : ""
                      }`}
                    onClick={() => handleLocationSearch(sug)}
                    disabled={searchLoading || currentLocationLoading}
                  >
                    {sug}
                  </button>
                ))}
              </div>
            </div>

            {/* Search Loading State */}
            {searchLoading && (
              <div className="state-container search-loading-state">
                <div className="state-spinner" />
                <p>
                  Discovering OpenStreetMap CNG stations near "{pendingQuery || location}"...
                </p>
                <span className="state-subtext">
                  Resolving coordinates with Nominatim & querying mapped fuel stations
                </span>
              </div>
            )}

            {/* Search Error State */}
            {searchError && !searchLoading && (
              <div className="state-container error-state search-error-container">
                <AlertCircle size={24} />
                <div className="error-copy">
                  <strong>Location Discovery Failed</strong>
                  <p>{searchError}</p>
                  {searchResult && (
                    <span className="error-preserved-note">
                      Previous results for "{searchResult.query}" are still displayed below.
                    </span>
                  )}
                </div>
                <button
                  className="retry-button"
                  onClick={() => handleLocationSearch(location)}
                >
                  <RotateCw size={14} /> Retry Search
                </button>
              </div>
            )}
          </section>

          {/* Resolved Location Banner (Active when search succeeds) */}
          {searchResult && !searchLoading && (
            <div className="resolved-banner">
              <div className="resolved-banner-left">
                <div className="resolved-icon">
                  <Compass size={22} />
                </div>
                <div className="resolved-info">
                  <div className="resolved-eyebrow">
                    <span>RESOLVED LOCATION</span>
                    <span className="data-source-pill">OpenStreetMap</span>
                  </div>
                  <h3>
                    {searchResult.resolvedLocation?.display_name ||
                      searchResult.query}
                  </h3>
                  <div className="resolved-chips">
                    {searchResult.resolvedLocation?.latitude && (
                      <span>
                        <MapPin size={12} />{" "}
                        {searchResult.resolvedLocation.latitude.toFixed(4)}° N,{" "}
                        {searchResult.resolvedLocation.longitude.toFixed(4)}° E
                      </span>
                    )}
                    <span>
                      <Navigation size={12} /> {searchResult.searchRadiusKm} km radius
                    </span>
                    <span>
                      <Fuel size={12} /> {searchResult.verifiedCount} verified CNG ·{" "}
                      {searchResult.otherCount} other fuel
                    </span>
                  </div>
                </div>
              </div>
              <button
                className="reset-fleet-button"
                onClick={handleClearSearch}
                title="Clear search and reset location"
              >
                <RotateCw size={13} /> Clear & Search New Location
              </button>
            </div>
          )}

          {/* Section 1: AI Recommendation Card (Contextual Bandit) */}
          <section className="section-block">
            <div className="section-heading">
              <div>
                <span className="eyebrow">YOUR BEST OPTION</span>
                <h2>Recommended for you</h2>
                {searchResult ? (
                  <p className="section-subtitle">
                    {searchResult.verifiedCount > 0
                      ? `Optimal choice among ${searchResult.verifiedCount} verified CNG station${searchResult.verifiedCount > 1 ? "s" : ""
                      } near ${searchResult.resolvedLocation?.display_name?.split(",")[0] ||
                      searchResult.query
                      }`
                      : `No recommendation available for ${searchResult.resolvedLocation?.display_name?.split(",")[0] ||
                      searchResult.query
                      }`}
                  </p>
                ) : null}
              </div>
              {searchResult && !searchLoading && (
                <div className="heading-live-meta">
                  <span className="live-dot" />
                  <span>Auto-refreshing (10s)</span>
                </div>
              )}
            </div>

            {searchResult ? (
              searchResult.verifiedCount === 0 ? (
                <div className="state-container empty-cng-rec">
                  <Fuel size={28} className="empty-rec-icon" />
                  <div className="empty-rec-copy">
                    <h3>No Verified CNG Stations Found</h3>
                    <p>
                      No stations explicitly tagged with <code>fuel:cng=yes</code> were
                      found within {searchResult.searchRadiusKm} km of{" "}
                      <strong>{searchResult.query}</strong> to evaluate for AI recommendation.
                    </p>
                    <span className="empty-rec-subtext">
                      Check the unverified fuel stations below or search another locality or city.
                    </span>
                  </div>
                </div>
              ) : recommendation ? (
                <article
                  className={`recommended-card ${isForecastRecommended ? "selected-for-forecast" : ""}`}
                  onClick={() => {
                    if (selectedStationId !== null) setSelectedStationId(null);
                    addHistoryEntry({
                      type: "forecast",
                      title: recommendation.name || "Recommended Station",
                      summary: `Inspected predictive queue forecast (${recommendation.travelTime || 0} min total journey)`,
                      tag: "Simulation Forecast",
                    });
                  }}
                >
                  <div className="recommend-top">
                    <span className="recommend-label">
                      BEST OVERALL JOURNEY TIME
                    </span>
                    <div className="recommend-top-badges">
                      {isForecastRecommended ? (
                        <span className="forecast-active-tag">
                          <Gauge size={11} /> Forecast Active
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="view-forecast-chip-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedStationId(null);
                            addHistoryEntry({
                              type: "forecast",
                              title: recommendation.name || "Recommended Station",
                              summary: `Inspected predictive queue forecast (${recommendation.travelTime || 0} min total journey)`,
                              tag: "Simulation Forecast",
                            });
                          }}
                        >
                          <Gauge size={11} /> View Forecast
                        </button>
                      )}
                      <span
                        className={`congestion-badge ${recommendation.congestion.className}`}
                        title={`Queue Congestion: ${recommendation.congestion.level}`}
                      >
                        {recommendation.congestion.level}
                      </span>
                      <span className="simulated-pill">Simulated estimate</span>
                    </div>
                  </div>

                  <div className="station-title-row">
                    <div className="station-icon">
                      <Fuel size={24} />
                    </div>
                    <div>
                      <h3>{recommendation.name || "Recommended Station"}</h3>
                      <p>
                        <MapPin size={13} /> {recommendation.address || "Nearby Area"}
                      </p>
                    </div>
                  </div>

                  <div className="metrics-grid">
                    <div className="metric">
                      <div className="metric-header">
                        <Navigation size={15} />
                        <span>{recommendation.distance_type === "straight_line" ? "Straight-line dist" : "Road distance"}</span>
                      </div>
                      <strong>{recommendation.distance}</strong>
                    </div>
                    <div className="metric">
                      <div className="metric-header">
                        <Clock size={15} />
                        <span>Road travel time</span>
                      </div>
                      <strong>{recommendation.travelTime} min</strong>
                    </div>
                    <div className="metric">
                      <div className="metric-header">
                        <Gauge size={15} />
                        <span>{recommendation.dispenser_count ? "Waiting queue" : "Queue length"}</span>
                      </div>
                      <strong>{recommendation.waiting_queue_length ?? recommendation.queue} vehicles</strong>
                      {recommendation.dispenser_count ? (
                        <span className="dispenser-subtext" style={{ fontSize: "0.72rem", color: "#4b5563", display: "block", marginTop: "2px" }}>
                          ({recommendation.vehicles_being_served} fueling across {recommendation.dispenser_count} bays)
                        </span>
                      ) : null}
                    </div>
                    <div className="metric">
                      <div className="metric-header">
                        <Clock size={15} />
                        <span>Waiting time</span>
                      </div>
                      <strong>{recommendation.waitTime} min</strong>
                    </div>
                  </div>

                  <div className="total-time">
                    <span>Total estimated time</span>
                    <strong>{recommendation.totalJourneyTime} min</strong>
                  </div>

                  <button
                    className="directions-button"
                    onClick={() => openDirections(recommendation)}
                  >
                    Get Directions <ArrowUpRight size={17} />
                  </button>
                </article>
              ) : (
                <div className="state-container">
                  <p>No recommendation currently available.</p>
                </div>
              )
            ) : (
              <div className="state-container initial-rec-prompt">
                <div className="initial-rec-icon">
                  <Zap size={26} />
                </div>
                <div className="initial-rec-copy">
                  <h3>AI Route Optimization Ready</h3>
                  <p>
                    Search a location or click <strong>Use my current location</strong> to discover nearby CNG stations and estimate queue conditions.
                  </p>
                </div>
              </div>
            )}
          </section>

          {/* Section: Queue Forecast for Active Station */}
          {searchResult && searchResult.verifiedCount > 0 && activeForecastStation && (
            <QueueForecastSection
              station={activeForecastStation}
              isRecommended={isForecastRecommended}
              onResetToRecommended={() => setSelectedStationId(null)}
            />
          )}

          {/* Section 2: Nearby Verified CNG Stations */}
          <section className="section-block nearby-section">
            <div className="section-heading">
              <div>
                <span className="eyebrow">AROUND YOUR LOCATION</span>
                <h2>Nearby CNG stations</h2>
                <p className="section-subtitle">
                  {searchLoading
                    ? `Discovering stations near ${pendingQuery || location}...`
                    : searchResult
                      ? `Verified CNG stations within ${searchResult.searchRadiusKm} km of ${searchResult.query}`
                      : searchedLocation
                        ? `Stations near ${searchedLocation}`
                        : "Search a locality or city to discover nearby verified CNG stations"}
                </p>
              </div>
              <div className="heading-actions">
                {searchResult && !searchLoading && searchResult.verifiedCount > 1 && (
                  <div
                    className="sort-control"
                    role="group"
                    aria-label="Sort stations by distance"
                  >
                    <span className="sort-label">Sort:</span>
                    <button
                      type="button"
                      className={`sort-pill ${sortOrder === "asc" ? "active" : ""}`}
                      onClick={() => setSortOrder("asc")}
                      title="Sort nearest first"
                      aria-pressed={sortOrder === "asc"}
                    >
                      <ArrowDown size={12} /> Nearest first
                    </button>
                    <button
                      type="button"
                      className={`sort-pill ${sortOrder === "desc" ? "active" : ""}`}
                      onClick={() => setSortOrder("desc")}
                      title="Sort farthest first"
                      aria-pressed={sortOrder === "desc"}
                    >
                      <ArrowUp size={12} /> Farthest first
                    </button>
                  </div>
                )}
                {searchLoading ? (
                  <span className="station-count">Searching...</span>
                ) : searchResult ? (
                  <span className="station-count">
                    {searchResult.verifiedCount === 0
                      ? "0 stations"
                      : `${searchResult.verifiedCount} verified CNG`}
                  </span>
                ) : null}
              </div>
            </div>

            {/* Active Search Loading in Section 2 */}
            {searchLoading ? (
              <div className="state-container search-in-progress-state">
                <div className="state-spinner" />
                <p>
                  Discovering OpenStreetMap CNG stations near "{pendingQuery || location}"...
                </p>
                <span className="state-subtext">
                  Querying free Nominatim geocoder & Overpass fuel registry
                </span>
              </div>
            ) : searchResult ? (
              searchResult.verifiedCount === 0 ? (
                <div className="state-container empty-cng-state">
                  <Fuel size={32} className="empty-icon" />
                  <div className="empty-copy">
                    <h3>No verified CNG stations found nearby</h3>
                    <p>
                      No stations explicitly tagged with <code>fuel:cng=yes</code> were
                      found within a {searchResult.searchRadiusKm} km radius of{" "}
                      <strong>{searchResult.query}</strong> on OpenStreetMap.
                    </p>
                    <span className="empty-subtext">
                      See the unverified fuel stations below that may dispense CNG,
                      or try searching another locality.
                    </span>
                  </div>
                </div>
              ) : (
                <div className="station-list">
                  {sortedVerifiedStations.map((station) => {
                    const stationId = station.id ?? station.osm_id;
                    const isSelected = selectedStationId === stationId;
                    return (
                      <article
                        className={`station-card verified-cng-card ${isSelected ? "selected-for-forecast" : ""}`}
                        key={`cng-${station.osm_type || "node"}-${station.osm_id}`}
                        onClick={() => {
                          const nextId = isSelected ? null : stationId;
                          setSelectedStationId(nextId);
                          if (!isSelected) {
                            addHistoryEntry({
                              type: "view_station",
                              title: station.name,
                              summary: `Viewed station details (${station.dispenser_count || 2} bays, ${station.estimated_waiting_time_minutes ?? 0}m est. wait)`,
                              tag: "Station Details",
                            });
                          }
                        }}
                      >
                        <div className="station-card-top">
                          <div className="station-card-identity">
                            <div className="station-icon small verified">
                              <Fuel size={20} />
                            </div>
                            <div className="station-header-text">
                              <div className="station-name-row">
                                <h3>{station.name}</h3>
                                {station.brand && (
                                  <span className="brand-chip">
                                    {station.brand}
                                  </span>
                                )}
                              </div>
                              <p className="station-address-line">
                                <MapPin size={13} />{" "}
                                {station.address || "Address details mapped on OpenStreetMap"}
                              </p>
                            </div>
                          </div>
                          <div className="station-badges-group">
                            <span className="cng-badge verified">
                              <CheckCircle2 size={12} /> Verified CNG
                            </span>
                            {station.estimated_waiting_time_minutes !== undefined && (() => {
                              const cong = getCongestionStatus(station.estimated_waiting_time_minutes);
                              return (
                                <span
                                  className={`congestion-badge ${cong.className}`}
                                  title={`Queue Congestion: ${cong.level}`}
                                >
                                  {cong.level}
                                </span>
                              );
                            })()}
                          </div>
                        </div>

                        <div className="station-telemetry-row">
                          <div className="telemetry-chip">
                            <Navigation size={13} className="telemetry-icon" />
                            <span className="telemetry-label">
                              {station.distance_type === "straight_line" ? "Dist (straight):" : "Road dist:"}
                            </span>
                            <strong>{station.distance_text || `${station.distance_km} km`}</strong>
                          </div>
                          {station.travel_time_minutes !== undefined && (
                            <div className="telemetry-chip">
                              <Clock size={13} className="telemetry-icon" />
                              <span className="telemetry-label">Road travel:</span>
                              <strong>{station.travel_time_minutes} min</strong>
                            </div>
                          )}
                          {station.queue_length !== undefined && (
                            <div className="telemetry-chip">
                              <Gauge size={13} className="telemetry-icon" />
                              <span className="telemetry-label">Queue:</span>
                              <strong>{station.queue_length} vehicles</strong>
                            </div>
                          )}
                          {station.estimated_waiting_time && (
                            <div className="telemetry-chip wait-chip">
                              <Clock size={13} className="telemetry-icon" />
                              <span className="telemetry-label">Wait:</span>
                              <strong>{station.estimated_waiting_time}</strong>
                            </div>
                          )}
                        </div>

                        <div className="station-card-bottom">
                          <div className="station-meta-tags">
                            {station.cng_tag_evidence && (
                              <span className="cng-tag-chip">
                                Tag: {station.cng_tag_evidence}
                              </span>
                            )}
                            <span className="osm-id-chip">
                              OSM #{station.osm_id}
                            </span>
                            <button
                              type="button"
                              className={`card-forecast-btn ${isSelected ? "active" : ""}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                const nextId = isSelected ? null : stationId;
                                setSelectedStationId(nextId);
                                if (!isSelected) {
                                  addHistoryEntry({
                                    type: "forecast",
                                    title: station.name,
                                    summary: `Inspected queue forecast (15/30/60m horizons, ${station.engine_type || "multi-dispenser"})`,
                                    tag: "Simulation Forecast",
                                  });
                                }
                              }}
                              title="View predictive queue forecast"
                            >
                              <Gauge size={13} />
                              <span>{isSelected ? "Viewing Forecast" : "Forecast"}</span>
                            </button>
                          </div>
                          <button
                            className="card-directions-button"
                            aria-label={`Get directions to ${station.name}`}
                            title="Get Directions in Google Maps"
                            onClick={(e) => {
                              e.stopPropagation();
                              openDirections(station);
                            }}
                          >
                            <span>Directions</span>
                            <ArrowUpRight size={14} />
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )
            ) : (
              /* Neutral Empty State: Prompt user to search or use GPS */
              <div className="state-container initial-search-prompt">
                <div className="initial-icon">
                  <Compass size={38} />
                </div>
                <div className="initial-copy">
                  <h3>Discover Nearby CNG Stations</h3>
                  <p>
                    Enter a sector, locality, city, or pincode above, or use your current location
                    to discover CNG stations identified from OpenStreetMap data, with simulated queue estimates.
                  </p>
                  <div className="initial-actions">
                    <button
                      type="button"
                      className="initial-locate-btn"
                      onClick={handleUseCurrentLocation}
                      disabled={searchLoading || currentLocationLoading}
                    >
                      {currentLocationLoading ? (
                        <RotateCw size={16} className="btn-spinner" />
                      ) : (
                        <LocateFixed size={16} />
                      )}
                      <span>
                        {currentLocationLoading
                          ? "Detecting location..."
                          : "Use my current location"}
                      </span>
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* Section 3: Other Fuel Stations — CNG Not Verified (Collapsible Accordion) */}
          {searchResult && !searchLoading && searchResult.otherCount > 0 && (
            <section className="section-block other-fuel-section">
              <div className="unverified-accordion-container">
                <button
                  type="button"
                  className={`unverified-accordion-header ${isUnverifiedExpanded ? "expanded" : ""}`}
                  onClick={() => setIsUnverifiedExpanded((prev) => !prev)}
                  aria-expanded={isUnverifiedExpanded}
                  aria-controls="unverified-station-content"
                >
                  <div className="unverified-header-left">
                    <div className="unverified-title-group">
                      <div className="unverified-title-row">
                        <div className="station-icon small unverified">
                          <Fuel size={17} />
                        </div>
                        <h2 className="unverified-title">Other Fuel Stations</h2>
                        <span className="cng-badge unverified header-badge">
                          <HelpCircle size={11} /> CNG Unverified
                        </span>
                      </div>
                      <p className="unverified-header-desc">
                        These fuel stations are mapped in OpenStreetMap, but their CNG availability has not been confirmed.
                      </p>
                    </div>
                  </div>
                  <div className="unverified-header-right">
                    <span className="station-count unverified">
                      {searchResult.otherCount} {searchResult.otherCount === 1 ? "station" : "stations"}
                    </span>
                    <div className={`accordion-chevron-icon ${isUnverifiedExpanded ? "rotated" : ""}`}>
                      <ChevronDown size={19} />
                    </div>
                  </div>
                </button>

                {isUnverifiedExpanded && (
                  <div id="unverified-station-content" className="unverified-accordion-body">
                    <div className="station-list compact-unverified-list">
                      {searchResult.otherFuelStations.map((station) => (
                        <article
                          className="station-card unverified-card compact-card"
                          key={`other-${station.osm_type || "node"}-${station.osm_id}`}
                        >
                          <div className="station-icon small unverified">
                            <Fuel size={16} />
                          </div>
                          <div className="station-info compact-info">
                            <div className="station-name-row">
                              <h3>{station.name}</h3>
                              {station.brand && (
                                <span className="brand-chip compact-chip">
                                  Brand: {station.brand}
                                </span>
                              )}
                            </div>
                            <p className="compact-address">
                              <MapPin size={12} />{" "}
                              {station.address || "Address details mapped on OpenStreetMap"}
                            </p>
                            <div className="station-details compact-details">
                              <span>
                                <Navigation size={12} />{" "}
                                {station.distance_text || `${station.distance_km} km`}
                              </span>
                              <span className="osm-id-chip compact-chip">
                                OSM #{station.osm_id}
                              </span>
                            </div>
                          </div>
                          <div className="station-actions compact-actions">
                            <span className="cng-badge unverified compact-badge">
                              <HelpCircle size={11} /> CNG Unverified
                            </span>
                            <button
                              className="direction-icon compact-direction"
                              aria-label={`Get directions to ${station.name}`}
                              title="Get Directions in Google Maps"
                              onClick={() => openDirections(station)}
                            >
                              <ArrowUpRight size={16} />
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}

          <footer className="disclaimer">
            <Zap size={14} />
            <span>{disclaimer}</span>
          </footer>
        </main>
      )}

      <nav className="bottom-nav">
        <a
          href="#home"
          className={`nav-item ${currentPage === "home" ? "active" : ""}`}
          onClick={(e) => {
            e.preventDefault();
            navigateTo("home");
          }}
        >
          <Fuel size={19} />
          Home
        </a>
        <a
          href="#history"
          className={`nav-item ${currentPage === "history" ? "active" : ""}`}
          onClick={(e) => {
            e.preventDefault();
            navigateTo("history");
          }}
        >
          <History size={19} />
          History
        </a>
        <a
          href="#profile"
          className={`nav-item ${currentPage === "profile" ? "active" : ""}`}
          onClick={(e) => {
            e.preventDefault();
            navigateTo("profile");
          }}
        >
          <UserRound size={19} />
          Profile
        </a>
      </nav>
    </div>
  );
}

export default App;
