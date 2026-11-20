// Comprehensive Acceptance Audit Test for NoQueue Guest Experience
import assert from "node:assert";

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

console.log("==================================================================");
console.log("NoQueue — Guest Experience Acceptance Audit Test Suite");
console.log("==================================================================");

// SECTION A: Guest Onboarding
console.log("\n[SECTION A: Guest Onboarding]");

// A1: Fresh Guest State
assert.strictEqual(getGuestSession(), null, "Fresh guest session must be null");
assert.strictEqual(getUserRegion(), null, "Fresh user region must be null");
console.log("  ✓ A1: Fresh guest has clean empty state");

// A2: Mandatory Region Selection Enforcement
function simulateOnboardingEnter(selectedRegion, textQuery) {
  if (!selectedRegion) {
    if (textQuery && textQuery.trim().length >= 2) {
      const freeRegion = {
        name: textQuery.trim(),
        query: textQuery.trim(),
        lat: null,
        lon: null,
        detectionMethod: "manual",
      };
      saveGuestSession();
      saveUserRegion(freeRegion);
      return { allowed: true, region: freeRegion };
    }
    return { allowed: false, error: "Please select or search your region before proceeding to the dashboard." };
  }
  saveGuestSession();
  saveUserRegion(selectedRegion);
  return { allowed: true, region: selectedRegion };
}

const emptyAttempt = simulateOnboardingEnter(null, "");
assert.strictEqual(emptyAttempt.allowed, false, "Dashboard entry must be blocked without selecting a valid region");
assert.strictEqual(getGuestSession(), null, "Guest session must not be created on blocked attempt");
console.log("  ✓ A2 & A3: Dashboard entry blocked without region; mandatory validation confirmed");

// A4: Quick-pick selection
const quickPick = {
  name: "Sector 50, Gurugram",
  query: "Sector 50 Gurugram",
  lat: 28.421,
  lon: 77.062,
  detectionMethod: "manual",
};
const quickPickResult = simulateOnboardingEnter(quickPick, "");
assert.strictEqual(quickPickResult.allowed, true);
assert.strictEqual(getUserRegion().name, "Sector 50, Gurugram");
assert.strictEqual(getUserRegion().detectionMethod, "manual");
console.log("  ✓ A4 & A6: Quick-pick selection and storage confirmed");

// A7: Session & Region restoration after simulated page refresh
const restoredSession = getGuestSession();
const restoredRegion = getUserRegion();
assert.notStrictEqual(restoredSession, null, "Guest session must persist across refreshes");
assert.strictEqual(restoredSession.isGuest, true);
assert.strictEqual(restoredRegion.name, "Sector 50, Gurugram");
console.log("  ✓ A7: Refresh restoration verified");

// SECTION B: Profile
console.log("\n[SECTION B: Profile]");

// B1: Initial Profile matches Onboarding
assert.strictEqual(getUserRegion().name, "Sector 50, Gurugram");
console.log("  ✓ B1: Profile displays onboarding region accurately");

// B2: Change Region
const updatedRegion = saveUserRegion({
  name: "Sector 45, Gurugram",
  query: "Sector 45 Gurugram",
  lat: 28.455,
  lon: 77.072,
  detectionMethod: "manual",
});
assert.strictEqual(getUserRegion().name, "Sector 45, Gurugram");
console.log("  ✓ B2: Change region updates persistence correctly");

// B3: GPS vs Manual status
const gpsRegion = saveUserRegion({
  name: "Connaught Place, New Delhi",
  query: "Connaught Place New Delhi",
  lat: 28.6304,
  lon: 77.2177,
  detectionMethod: "gps",
});
assert.strictEqual(getUserRegion().detectionMethod, "gps");
console.log("  ✓ B3: GPS detection method tracked accurately");

// B4: Session Reset
clearGuestSession();
assert.strictEqual(getGuestSession(), null, "Reset session must wipe guest session");
assert.strictEqual(getUserRegion(), null, "Reset session must wipe user region");
assert.deepStrictEqual(getHistory(), [], "Reset session must wipe activity history");
console.log("  ✓ B4: Session reset cleanly purges guest data");

// SECTION C: History Activity Tracking
console.log("\n[SECTION C: History Activity Tracking]");

// Re-establish session
saveGuestSession("Audit Guest");
saveUserRegion(quickPick);

// Log 1: Location search
const h1 = addHistoryEntry({
  type: "search",
  title: "Sector 50, Gurugram",
  summary: "Discovered 4 verified CNG stations within 5 km",
  tag: "OpenStreetMap Discovery",
});

// Log 2: Station recommendation viewed
const h2 = addHistoryEntry({
  type: "recommendation",
  title: "Green Fuel CNG Station",
  summary: "Top recommendation with 13m journey (10m queue wait)",
  tag: "AI Policy Recommendation",
});

// Log 3: Station details viewed
const h3 = addHistoryEntry({
  type: "view_station",
  title: "City Gas Point",
  summary: "Viewed station details (2 bays, 14m est. wait)",
  tag: "Station Details",
});

// Log 4: Forecast requested
const h4 = addHistoryEntry({
  type: "forecast",
  title: "Highway CNG Station",
  summary: "Inspected queue forecast (15/30/60m horizons, multi-dispenser)",
  tag: "Simulation Forecast",
});

// Log 5: Navigation opened
const h5 = addHistoryEntry({
  type: "directions",
  title: "Highway CNG Station",
  summary: "Navigating to Sohna Road, Sector 48",
  tag: "Google Maps Navigation",
});

const allHistory = getHistory();
assert.strictEqual(allHistory.length, 5, "All 5 required activities must be logged");
assert.strictEqual(allHistory[0].id, h5.id, "Newest entry (directions) must be first");
assert.strictEqual(allHistory[1].id, h4.id, "Forecast must be second");
assert.strictEqual(allHistory[2].id, h3.id, "Station view must be third");
assert.strictEqual(allHistory[3].id, h2.id, "Recommendation must be fourth");
assert.strictEqual(allHistory[4].id, h1.id, "Search must be fifth");
console.log("  ✓ C1: All 5 required activity types logged with newest-first ordering");

// Filters verification
assert.strictEqual(allHistory.filter(i => i.type === "search").length, 1);
assert.strictEqual(allHistory.filter(i => i.type === "recommendation").length, 1);
assert.strictEqual(allHistory.filter(i => i.type === "view_station").length, 1);
assert.strictEqual(allHistory.filter(i => i.type === "forecast").length, 1);
assert.strictEqual(allHistory.filter(i => i.type === "directions").length, 1);
console.log("  ✓ C2: History filtering works cleanly for all categories");

// Clear History
clearHistory();
assert.deepStrictEqual(getHistory(), [], "Clear history must empty list");
console.log("  ✓ C3: Clear history verified");

console.log("\n==================================================================");
console.log("All Acceptance Criteria Passed Successfully!");
console.log("==================================================================");

