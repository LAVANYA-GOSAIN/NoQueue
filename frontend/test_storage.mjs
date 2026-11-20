// Unit test for frontend storage utilities and user flows
import assert from "node:assert";

// Mock localStorage for Node environment
class MockLocalStorage {
  constructor() {
    this.store = {};
  }
  getItem(key) {
    return this.store[key] || null;
  }
  setItem(key, value) {
    this.store[key] = String(value);
  }
  removeItem(key) {
    delete this.store[key];
  }
  clear() {
    this.store = {};
  }
}

globalThis.localStorage = new MockLocalStorage();

// Import storage module
const {
  getGuestSession,
  saveGuestSession,
  updateGuestName,
  clearGuestSession,
  getUserRegion,
  saveUserRegion,
  getHistory,
  addHistoryEntry,
  clearHistory,
} = await import("./src/utils/storage.js");

console.log("Running storage unit tests...");

// Test 1: Initial state is clean
assert.strictEqual(getGuestSession(), null, "Guest session should be null initially");
assert.strictEqual(getUserRegion(), null, "User region should be null initially");
assert.deepStrictEqual(getHistory(), [], "History should be empty array initially");

// Test 2: Guest onboarding - save guest session
const session = saveGuestSession({ displayName: "Guest Driver" });
assert(session.sessionId.startsWith("guest_"), "Session ID must start with guest_");
assert.strictEqual(session.isGuest, true, "isGuest must be true");
assert.strictEqual(session.displayName, "Guest Driver", "displayName must match");
assert.deepStrictEqual(getGuestSession(), session, "Stored session must match returned session");

// Test 3: Update guest display name
const updatedSession = updateGuestName("Dev Tester");
assert.strictEqual(updatedSession.displayName, "Dev Tester", "Display name should be updated");
assert.strictEqual(getGuestSession().displayName, "Dev Tester", "Stored display name should be updated");

// Test 4: Mandatory Region Selection - manual selection
const manualRegion = saveUserRegion({
  name: "Sector 50, Gurugram",
  query: "Sector 50 Gurugram",
  lat: 28.418,
  lon: 77.062,
  method: "manual",
});
assert.strictEqual(manualRegion.name, "Sector 50, Gurugram");
assert.strictEqual(manualRegion.detectionMethod, "manual");
assert.deepStrictEqual(getUserRegion(), manualRegion);

// Test 5: Region update via GPS
const gpsRegion = saveUserRegion({
  name: "Connaught Place, New Delhi",
  query: "Connaught Place",
  lat: 28.6304,
  lon: 77.2177,
  detectionMethod: "gps",
});
assert.strictEqual(gpsRegion.detectionMethod, "gps");
assert.strictEqual(getUserRegion().name, "Connaught Place, New Delhi");

// Test 6: Log all 5 required activity types
// A. Location search
const actSearch = addHistoryEntry({
  type: "search",
  title: "Sector 50, Gurugram",
  summary: "Discovered 4 verified CNG stations within 5 km",
  tag: "OpenStreetMap Discovery",
});
assert.strictEqual(actSearch.type, "search");

// B. Station recommendation viewed/selected
const actRec = addHistoryEntry({
  type: "recommendation",
  title: "Green Fuel CNG Station",
  summary: "Top recommendation with 14m journey",
  tag: "AI Policy Recommendation",
});
assert.strictEqual(actRec.type, "recommendation");

// C. Station details viewed
const actStation = addHistoryEntry({
  type: "view_station",
  title: "City Gas Point",
  summary: "Viewed station details (2 bays, 11m wait)",
  tag: "Station Details",
});
assert.strictEqual(actStation.type, "view_station");

// D. Forecast requested / viewed
const actForecast = addHistoryEntry({
  type: "forecast",
  title: "Highway CNG Station",
  summary: "Inspected queue forecast (15/30/60m, multi-dispenser)",
  tag: "Simulation Forecast",
});
assert.strictEqual(actForecast.type, "forecast");

// E. Google Maps directions opened
const actDirections = addHistoryEntry({
  type: "directions",
  title: "EcoFill CNG Hub",
  summary: "Navigating to Sector 49, Sohna Road",
  tag: "Google Maps Navigation",
});
assert.strictEqual(actDirections.type, "directions");

// Test 7: Verify newest-first ordering
const history = getHistory();
assert.strictEqual(history.length, 5, "History should contain exactly 5 entries");
assert.strictEqual(history[0].id, actDirections.id, "Most recent (directions) must be first");
assert.strictEqual(history[1].id, actForecast.id, "Forecast must be second");
assert.strictEqual(history[2].id, actStation.id, "Station view must be third");
assert.strictEqual(history[3].id, actRec.id, "Recommendation must be fourth");
assert.strictEqual(history[4].id, actSearch.id, "Search must be fifth");

// Test 8: Verify filtering logic matches HistoryPage useMemo
const forecastFilter = history.filter((i) => i.type === "forecast");
assert.strictEqual(forecastFilter.length, 1);
assert.strictEqual(forecastFilter[0].title, "Highway CNG Station");

const directionsFilter = history.filter((i) => i.type === "directions");
assert.strictEqual(directionsFilter.length, 1);
assert.strictEqual(directionsFilter[0].title, "EcoFill CNG Hub");

const searchFilter = history.filter((i) => i.type === "search");
assert.strictEqual(searchFilter.length, 1);
assert.strictEqual(searchFilter[0].title, "Sector 50, Gurugram");

// Test 9: Clear history
clearHistory();
assert.deepStrictEqual(getHistory(), [], "History should be empty after clearHistory()");

// Test 10: Reset Guest Session (profile sign out)
clearGuestSession();
assert.strictEqual(getGuestSession(), null, "Guest session must be cleared");
assert.strictEqual(getUserRegion(), null, "User region must be cleared");
assert.deepStrictEqual(getHistory(), [], "History must be cleared");

console.log("All storage unit tests and user flow validations passed successfully!");
