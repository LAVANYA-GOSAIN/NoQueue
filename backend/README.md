# NoQueue - Backend API (FastAPI)

Initial lightweight FastAPI backend service for the **NoQueue** CNG queue tracking application.

---

## 🚀 Getting Started

### 1. Navigate to the backend directory
```bash
cd backend
```

### 2. Activate the Virtual Environment
- **macOS / Linux:**
  ```bash
  source venv/bin/activate
  ```
- **Windows (Command Prompt / PowerShell):**
  ```cmd
  venv\Scripts\activate
  ```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Development Server
You can start the server using either:
```bash
uvicorn main:app --reload --port 8001
```
or directly with Python:
```bash
python main.py
```

The API will be available at: `http://127.0.0.1:8001`

---

## 📡 Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Basic API welcome message and status |
| `GET` | `/api/health` | Health check endpoint returning `{"status": "healthy", "project": "NoQueue"}` |
| `GET` | `/api/stations` | Demonstration dataset of CNG stations with simulated queue/wait times |
| `GET` | `/docs` | Interactive Swagger API documentation |
| `GET` | `/redoc` | Interactive ReDoc documentation |

---

## ⚠️ Important Note on Demonstration Data
Queue lengths, wait times, and crowd levels returned by `/api/stations` are **simulated demonstration values** for testing and frontend prototyping. They are **not** real-time CCTV measurements.

---

## 🌐 CORS Configuration
CORS middleware is pre-configured to allow requests from your frontend:
- `http://localhost:5173` (Vite default)
- `http://127.0.0.1:5173`
- `http://localhost:5174` (Vite fallback)
- `http://127.0.0.1:5174`
- `http://localhost:3000`

