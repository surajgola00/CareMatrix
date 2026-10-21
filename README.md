# CareMatrix

CareMatrix is a real-time hospital coordination and management system built for hackathons and rapid deployment. It enables hospitals to broadcast patient transfer requests, share medical resources, predict patient surges using ML, and visualize live demand across a network of facilities — all through a fast, brutalist-styled web interface.

---

## Project Structure

```
CareMatrix/
├── Client/          # React + TypeScript frontend (Vite + Bun)
├── Server/          # FastAPI backend (Python + SQLite)
├── setup.sh         # One-command setup for Linux / macOS
├── setup.bat        # One-command setup for Windows
└── README.md
```

---

## Tech Stack

### Frontend — `Client/`
| Technology | Purpose |
|---|---|
| React 18 + TypeScript | UI framework |
| Vite + Bun | Build tool and package manager |
| React Router v6 | Client-side routing |
| React Leaflet | Interactive hospital heatmap |
| Custom SVG charts | Patient surge visualization |

### Backend — `Server/`
| Technology | Purpose |
|---|---|
| FastAPI | REST API framework |
| SQLite | Lightweight embedded database |
| Pydantic | Request validation |
| Uvicorn | ASGI server |
| PredictionModel | ML-based patient surge forecasting |

---

## Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js + Bun (`npm install -g bun`)

### One-command setup

From the project root:

**Linux / macOS:**
```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**
```bat
setup.bat
```

Both scripts will:
1. Create a Python virtual environment in `Server/.venv`
2. Install all Python dependencies from `Server/requirements.txt`
3. Start the FastAPI server on `http://localhost:8000`
4. Install frontend dependencies and build the React app
5. Serve the built frontend on `http://localhost:5173`

> On Linux/macOS both servers run in the same terminal — press `Ctrl+C` to stop both.
> On Windows each server opens in its own command window — close them individually to stop.

### Manual setup

**Backend:**
```bash
cd Server
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd Client
bun install
bun run dev                    # development
# or
bun run build && bun run preview --port 5173   # production build
```

---

## Usage

1. Open `http://localhost:5173`
2. Log in with your **Hospital ID** (e.g. `hospital123`) and password
3. Use the dashboard to register patients, respond to incoming transfers, and manage inventory

---

## API Endpoints

Base URL: `http://localhost:8000`

### Hospital
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/hospital/register` | Register a new hospital |
| `POST` | `/api/hospital/capacity` | Update department bed capacity |
| `GET` | `/api/hospital/open-requests` | Fetch open patient transfer requests |
| `POST` | `/api/hospital/respond` | Respond to a patient request |
| `POST` | `/api/hospital/predict` | Get ML surge prediction for a date |

### Patient
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/request` | Create a new patient transfer request |
| `GET` | `/api/patient/responses` | Get hospital responses for a patient |
| `POST` | `/api/patient/select` | Assign patient to a hospital |
| `GET` | `/api/getResult` | Get final assignment result |

### Resources
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/resource/request` | Create a resource sharing request |
| `GET` | `/api/resource/open` | Get all open resource requests |
| `POST` | `/api/resource/respond` | Respond to a resource request |
| `GET` | `/api/resource/responses` | Get responses for a resource request |
| `POST` | `/api/resource/select` | Select a resource provider |

### Analytics
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/heatmap` | Live demand data for all hospitals |
| `GET` | `/api/debug/state` | Full database snapshot (dev only) |

Interactive API docs available at `http://localhost:8000/docs`

---

## Screenshots

> Dashboard — patient registration and incoming transfer requests

> Surge Prediction — 24h ML forecast with confidence band, triage breakdown, and waiting times

> Heatmap — live demand visualization across hospital network

> Inventory Management — ML-predicted resource requirements and restock billing

---

## System Flow

```
Patient Transfer
  Hospital A registers patient → broadcast to all hospitals
  → Hospitals respond (accept/reject)
  → Hospital A selects a match
  → Bed capacity auto-decremented

Resource Sharing
  Hospital requests resource → broadcast
  → Other hospitals respond
  → Requester selects provider
  → Request marked fulfilled
```
## Team Members
Suraj Gola,
 Vibhor Sahu,
 Tushar Kaushik,
 Tushar Verma,
 Harshvardhan Negi

## Contributors

- Harshvardhan Negi
- Suraj Gola
- Tushar Kaushik
