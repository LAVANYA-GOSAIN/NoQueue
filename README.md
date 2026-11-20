# NoQueue 🚗⚡
> Intelligent CNG Queue Prediction, Multi-Dispenser Simulation & Smart Routing

NoQueue is a comprehensive full-stack platform designed to help CNG vehicle drivers avoid long petrol pump queues. It combines real-time OpenStreetMap discovery, OSRM routing, an $M/M/c$ Join-the-Shortest-Queue (JSQ) multi-dispenser queue simulator, a Monte Carlo predictive queue forecasting engine, and a Reinforcement Learning contextual bandit recommendation policy.

---

## 🌟 Key Features

1. **Guest Onboarding & Mandatory Region Selection**
   - Zero friction: no passwords or registration required.
   - Mandatory region selection on initial launch to localize nearby stations.
   - Photon OSM autocomplete, rapid region chips, and optional GPS geolocation.
   - Persistent guest session and preferences stored safely in client-side storage.

2. **Multi-Dispenser Queue Simulation ($M/M/c$ JSQ)**
   - Distinguishes waiting vehicles in queue from vehicles actively being refueled at dispenser bays.
   - Multi-server Join-the-Shortest-Queue dynamics with configurable bay counts per station.
   - Automatic fallback to legacy queue simulator for external OSM-discovered stations.

3. **Phase 4 Monte Carlo Queue Forecasting**
   - Probabilistic 15, 30, and 60-minute queue horizons across 100 simulation trials.
   - Reports expected queue length, predicted wait times, and 90% confidence prediction intervals (P05–P95).
   - Clear visual distinction between simulated predictive forecasts and live sensor measurements.

4. **Reinforcement Learning Recommendation Engine**
   - Offline-trained Contextual Bandit policy (`q_table_v2.json`) optimizing total journey time (travel time + queue wait).
   - Dynamic exploration/exploitation trade-off with deterministic fallback safeguards.

5. **Profile & Activity History**
   - **Profile Page**: Update display name, review active commute region and GPS coordinates, or reset guest session.
   - **History Page**: Chronological timeline of searches, forecasts inspected, and Google Maps directions launched, with filter chips and clear history controls.

---

## 🛠️ Technology Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, NumPy, SciPy
- **Frontend**: React 19, Vite, Lucide Icons, Leaflet / React-Leaflet
- **APIs & Data**: OpenStreetMap (Overpass & Nominatim), Photon Geocoding, OSRM Routing, Google Maps Navigation

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+
- Node.js 18+ and npm

### 2. Backend Setup
```bash
# Navigate to backend directory
cd backend

# Activate virtual environment
source venv/bin/activate  # macOS / Linux
# or: venv\Scripts\activate on Windows

# Install dependencies (if not already installed)
pip install -r requirements.txt

# Start FastAPI server on port 8001
uvicorn main:app --reload --port 8001
```
The backend API and interactive documentation will be accessible at:
- API Base: `http://127.0.0.1:8001`
- Swagger Docs: `http://127.0.0.1:8001/docs`

### 3. Frontend Setup
```bash
# In a separate terminal, navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```
The frontend application will be accessible at:
- Web App: `http://localhost:5173` (or `http://localhost:5174`)

---

## 🧪 Running Tests

### Backend Test Suite (118 Tests)
```bash
PYTHONPATH=backend backend/venv/bin/python3 -m unittest discover -s backend -p "test_*.py"
```

### Frontend Storage Unit Tests
```bash
npm test --prefix frontend
```

### Frontend Production Build
```bash
npm run build --prefix frontend
```

---

## 🛡️ Privacy & Reliability Notice
NoQueue uses simulated queue data and stochastic Monte Carlo forecasts to model station congestion. Queue metrics and forecasts are labeled as simulated estimates to maintain transparency.

