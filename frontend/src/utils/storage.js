/**
 * LocalStorage utilities for NoQueue:
 * - Guest Session management (privacy-preserving local session)
 * - User Region preference (mandatory onboarding region)
 * - Activity History tracking (local-only, non-sensitive actions)
 */

const GUEST_SESSION_KEY = "noqueue_guest_session";
const USER_REGION_KEY = "noqueue_user_region";
const ACTIVITY_HISTORY_KEY = "noqueue_activity_history";
const MAX_HISTORY_ITEMS = 50;

// ============================================================================
// 1. Guest Session
// ============================================================================

export function getGuestSession() {
  try {
    const raw = localStorage.getItem(GUEST_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && parsed.isGuest) {
      return parsed;
    }
    return null;
  } catch (err) {
    console.warn("Could not read guest session from localStorage:", err);
    return null;
  }
}

export function saveGuestSession(nameOrOptions = "Guest Driver") {
  try {
    const existing = getGuestSession();
    let resolvedName = "Guest Driver";
    if (typeof nameOrOptions === "string") {
      resolvedName = nameOrOptions.trim() || "Guest Driver";
    } else if (nameOrOptions && typeof nameOrOptions === "object") {
      resolvedName = (nameOrOptions.name || nameOrOptions.displayName || "").trim() || "Guest Driver";
    }

    const id = existing?.guestId || existing?.sessionId || `guest_${Date.now().toString(36)}_${Math.random().toString(36).substring(2, 6)}`;
    const session = {
      isGuest: true,
      guestId: id,
      sessionId: id,
      name: resolvedName,
      displayName: resolvedName,
      createdAt: existing?.createdAt || new Date().toISOString(),
      lastActiveAt: new Date().toISOString(),
    };
    localStorage.setItem(GUEST_SESSION_KEY, JSON.stringify(session));
    return session;
  } catch (err) {
    console.warn("Could not save guest session to localStorage:", err);
    return null;
  }
}

export function updateGuestName(name) {
  try {
    const session = getGuestSession() || saveGuestSession(name);
    const resolvedName = (name && typeof name === "string" ? name.trim() : "") || "Guest Driver";
    session.name = resolvedName;
    session.displayName = resolvedName;
    session.lastActiveAt = new Date().toISOString();
    localStorage.setItem(GUEST_SESSION_KEY, JSON.stringify(session));
    return session;
  } catch (err) {
    console.warn("Could not update guest name in localStorage:", err);
    return null;
  }
}

export function clearGuestSession() {
  try {
    localStorage.removeItem(GUEST_SESSION_KEY);
    localStorage.removeItem(USER_REGION_KEY);
    // Note: Activity history can optionally be retained or cleared; clearing session resets region.
  } catch (err) {
    console.warn("Could not clear guest session from localStorage:", err);
  }
}

// ============================================================================
// 2. User Region
// ============================================================================

export function getUserRegion() {
  try {
    const raw = localStorage.getItem(USER_REGION_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (err) {
    console.warn("Could not read user region from localStorage:", err);
    return null;
  }
}

export function saveUserRegion({ name, query, lat = null, lon = null, detectionMethod = "manual", method = null }) {
  try {
    const dm = method || detectionMethod;
    const region = {
      name: name || query || "Unknown Region",
      query: query || name || "",
      lat: typeof lat === "number" ? lat : null,
      lon: typeof lon === "number" ? lon : null,
      detectionMethod: dm === "gps" ? "gps" : "manual",
      method: dm === "gps" ? "gps" : "manual",
      updatedAt: new Date().toISOString(),
    };
    localStorage.setItem(USER_REGION_KEY, JSON.stringify(region));
    return region;
  } catch (err) {
    console.warn("Could not save user region to localStorage:", err);
    return null;
  }
}

// ============================================================================
// 3. Activity History
// ============================================================================

export function getHistory() {
  try {
    const raw = localStorage.getItem(ACTIVITY_HISTORY_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list : [];
  } catch (err) {
    console.warn("Could not read history from localStorage:", err);
    return [];
  }
}

/**
 * Appends a new activity to local history:
 * @param {Object} item
 * @param {"search"|"view_station"|"forecast"|"recommendation"|"directions"|"region_change"} item.type
 * @param {string} item.title
 * @param {string} item.summary
 * @param {string} [item.tag]
 * @param {Object} [item.meta]
 */
export function addHistoryEntry({ type, title, summary, tag, meta = {} }) {
  try {
    if (!title) return null;
    const history = getHistory();

    const newEntry = {
      id: `act_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
      type: type || "activity",
      title: title.trim(),
      summary: summary || "",
      tag: tag || null,
      timestamp: new Date().toISOString(),
      meta: meta || {},
    };

    // Avoid duplicate immediate consecutive entries (e.g., rapid clicks on same forecast or station)
    if (history.length > 0) {
      const top = history[0];
      if (top.type === newEntry.type && top.title === newEntry.title) {
        const timeDiffMs = new Date(newEntry.timestamp) - new Date(top.timestamp);
        if (timeDiffMs < 5000) {
          return top; // Skip duplicate within 5 seconds
        }
      }
    }

    const updated = [newEntry, ...history].slice(0, MAX_HISTORY_ITEMS);
    localStorage.setItem(ACTIVITY_HISTORY_KEY, JSON.stringify(updated));
    return newEntry;
  } catch (err) {
    console.warn("Could not record history entry in localStorage:", err);
    return null;
  }
}

export function clearHistory() {
  try {
    localStorage.removeItem(ACTIVITY_HISTORY_KEY);
    return true;
  } catch (err) {
    console.warn("Could not clear history in localStorage:", err);
    return false;
  }
}
