# Patient Influx & Capacity Prediction System
### Standalone · No database · Local CSV storage · CPU/GPU · REST API

---

## What this system does

Predicts daily patient arrivals for any hospital OPD or specialty, then calculates bed occupancy, OPD load, emergency department load, and patient waiting times — all from a single CSV file, running entirely offline on your laptop.

**No MySQL. No PostgreSQL. No MongoDB. No internet required after setup.**
Everything is stored in plain CSV and JSON files on your machine.

---

## Files in this package

```
patient_predictor/
  core.py                        ← ML engine (pure Python, no CLI)
  server.py                      ← REST API server (Flask)
  train.py                       ← Command-line interface
  requirements.txt               ← pip dependencies
  README.md                      ← this file
  FILE_LOCATIONS.txt             ← where to put your files
  API_PARAMETERS.md              ← full API parameter reference
  patient_prediction_system.html ← browser dashboard
  data/
    demo.csv                     ← included demo dataset
```

---

## Installation (one time only)

```bash
# 1. Enter the folder
cd patient_predictor

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Verify
python train.py --status
```

**Python 3.9 or newer required.**

---

## Quickstart (3 commands)

```bash
# Train
python train.py --csv data/demo.csv

# Predict today
python train.py --predict --date 2025-08-15 --capacity

# 30-day forecast
python train.py --forecast --days 30 --capacity
```

---

## All commands

### TRAINING

```bash
# Train fresh on a CSV
python train.py --csv data/patients.csv

# Add new data to existing training memory (incremental)
python train.py --csv data/june.csv --retrain

# Train only on a specific date window
python train.py --csv data/patients.csv --from-date 2023-06-01 --to-date 2024-01-01

# Retrain with memory, only adding rows from a date range
python train.py --csv data/new.csv --retrain --from-date 2024-01-01

# Use a specific climate profile (affects seasonal priors)
python train.py --csv data/patients.csv --climate tropical

# Limit to 4 CPU cores
python train.py --csv data/patients.csv --jobs 4
```

**Climate options:** `semi_arid` (default) · `tropical` · `temperate` · `cold` · `equatorial`

---

### PREDICTION

```bash
# Predict a specific date
python train.py --predict --date 2025-08-15

# Predict for one specialty
python train.py --predict --date 2025-08-15 --facility "General Medicine"

# Include full capacity report (BOR + OPD + ED + waiting times)
python train.py --predict --date 2025-08-15 --capacity

# Inject live environmental conditions
python train.py --predict --date 2025-08-15 --temp 38 --aqi 145 --rain 0

# Mark as a holiday
python train.py --predict --date 2025-08-15 --holiday 1

# Apply event flags (stack as many as needed)
python train.py --predict --date 2025-08-15 --events epidemic heatwave

# Staff shortage scenario
python train.py --predict --date 2025-08-15 --staffing 75 --lagged 65

# Override capacity parameters
python train.py --predict --date 2025-08-15 --capacity \
  --beds 150 --beds-occ 110 --doctors 6 --counters 4 \
  --ed-beds 30 --ed-occ 18
```

**Environment flags you can set:**

| Flag | Unit | Effect |
|------|------|--------|
| `--temp` | °C | >39°C raises predictions; <5°C also raises |
| `--aqi` | AQI | >100=+4%, >150=+9%, >200=+18% |
| `--rain` | mm | >20mm=−7%, >50mm=−15% footfall |
| `--humidity` | % | >85% adds ~5% respiratory load |
| `--hour` | 0–23 | Shifts intraday weighting |
| `--holiday` | 0/1 | Applies learned holiday multiplier |
| `--staffing` | % | Scales doctors; raises wait times |
| `--lagged` | count | Yesterday's actual patient count |

**Event flags** (use with `--events`, multiple allowed):
`holiday` `festival` `heatwave` `flu_peak` `rain_heavy` `long_weekend` `epidemic` `mass_event`

---

### FORECAST

```bash
# 30-day forecast from today
python train.py --forecast --days 30

# With capacity columns per day
python train.py --forecast --days 30 --capacity

# For a specific specialty
python train.py --forecast --days 14 --facility "Dental"

# Starting from a future date
python train.py --forecast --days 7 --start 2025-09-01

# With environmental conditions
python train.py --forecast --days 30 --temp 34 --aqi 120
```

Forecast is automatically saved to `exports/forecast_*.csv` with all capacity columns.

---

### CAPACITY REPORT

```bash
# Full report for today
python train.py --capacity-report

# With your actual bed snapshot
python train.py --capacity-report --beds 150 --beds-occ 110

# With ED and staffing
python train.py --capacity-report \
  --beds 200 --beds-occ 155 \
  --ed-beds 30 --ed-occ 22 \
  --doctors 8 --counters 5 \
  --staffing 85

# For a specific specialty
python train.py --capacity-report --facility "Emergency"
```

**Capacity parameters:**

| Flag | Default | What it sets |
|------|---------|-------------|
| `--beds` | 100 | Total sanctioned beds |
| `--beds-occ` | 72 | Beds occupied right now |
| `--admit-rate` | 8 | OPD→IPD admission % |
| `--ed-beds` | 20 | ED bed capacity |
| `--ed-occ` | 12 | ED beds occupied now |
| `--ed-rate` | 3 | OPD→ED transfer % |
| `--doctors` | 5 | Doctors on duty |
| `--counters` | 3 | Registration counters |
| `--opd-hrs` | 6 | OPD hours per day |
| `--walk-in` | 36 | Walk-in patient % |

---

### DATA INSPECT

```bash
# Show all stored training data (daily summary)
python train.py --data

# Filter by date range
python train.py --data --from-date 2023-06-01 --to-date 2023-06-30

# Filter by specialty
python train.py --data --facility "General Medicine"

# Show actual stored rows + model prediction for one specific date
python train.py --data-date 2023-07-15

# For one specialty on that date
python train.py --data-date 2023-07-15 --facility "Dental"

# Export all stored data to CSV
python train.py --export-data

# Export a date range
python train.py --export-data --from-date 2023-01-01 --to-date 2023-06-30
```

---

### SYSTEM

```bash
# Training history + model accuracy
python train.py --status

# All local files, sizes, and formats (confirms no database)
python train.py --storage

# CPU vs GPU speed test
python train.py --benchmark

# Export model for HTML browser dashboard
python train.py --export-dashboard

# Wipe all training memory and start fresh
python train.py --clear-memory
```

---

## Local storage — what goes where

```
data/
  demo.csv               your original CSV (for reference)
  session_0001.csv       data from first training session
  session_0002.csv       data from second session (if --retrain used)
  ...

models/
  ensemble.pkl           all 5 trained ML models (joblib pickle)
  stats.json             learned patterns, multipliers, accuracy
  memory.json            session history, row counts, specialties

exports/
  forecast_*.csv         saved forecasts (auto-generated)
  dashboard_model_*.json model export for HTML dashboard
  data_export_*.csv      manual exports from --export-data

logs/
  train_*.log            training run logs
```

**Format summary:**

| Data type | Format | Why |
|-----------|--------|-----|
| Training data | CSV | Human-readable, editable, portable |
| Trained ML models | Pickle (.pkl) | Standard Python/scikit-learn format |
| Learned patterns | JSON | Human-readable, easy to inspect |
| Session memory | JSON | Append-only session index |
| Forecasts | CSV | Import into Excel, Google Sheets, etc. |
| Dashboard export | JSON | Loaded by browser dashboard |

**No database of any kind is used.** The system runs entirely from these files. You can copy the whole `patient_predictor/` folder to a USB drive and run it on any machine with Python installed.

---

## REST API server

All functionality is also available over HTTP for integration with your own API:

```bash
# Start the server
python server.py

# On a specific port
python server.py --port 8080

# Accessible to other machines on your network
python server.py --host 0.0.0.0 --port 5000
```

### Key API endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/train` | Upload CSV and train |
| `POST` | `/predict` | Predict one date |
| `POST` | `/forecast` | Multi-day forecast |
| `POST` | `/capacity` | Capacity report for a count |
| `POST` | `/env/update` | Push live weather/sensor values |
| `GET` | `/env/current` | Read stored environment |
| `GET` | `/data` | Query stored training data |
| `GET` | `/data/2023-07-15` | Specific date data + prediction |
| `GET` | `/data/export` | Download stored data as CSV |
| `GET` | `/storage` | Local file inventory |
| `GET` | `/status` | Training history |
| `GET` | `/health` | Server alive check |
| `GET` | `/docs` | Full parameter reference |

See `API_PARAMETERS.md` for complete request/response schemas.

---

## GPU acceleration

The system detects your hardware automatically and upgrades models when GPU libraries are installed:

| Hardware | Install | Effect |
|----------|---------|--------|
| NVIDIA GPU | `pip install xgboost lightgbm` | GBM→XGBoost CUDA, RF→LightGBM GPU |
| AMD GPU | `pip install xgboost lightgbm` | GBM→XGBoost, RF→LightGBM OpenCL |
| Apple M-series | nothing extra needed | scikit-learn uses Metal Accelerate |
| CPU only | nothing extra needed | RF uses all cores with `n_jobs=-1` |

Run `python train.py --benchmark` to see actual speed on your hardware.

---

## CSV format for your data

**Minimum required:**
```
date,patients
2024-01-01,42
2024-01-02,38
```

**Full optional columns:**
```
date,specialty,patients,temperature,aqi,rainfall,holiday,revisit,doctors,counters,hour
```

Column names are auto-detected — they don't have to match exactly. The system looks for keywords like `date`/`day`/`dt`, `patients`/`count`/`visits`, `specialty`/`facility`/`dept`, etc.

Date formats accepted: `2024-01-15` · `15/01/2024` · `01/15/2024` · `15-01-2024` · `15 Jan 2024`

---

## Models used

All from **scikit-learn**. No external ML service, no cloud, no API key.

| Algorithm | Library | Paper basis |
|-----------|---------|-------------|
| GBM (Gradient Boosting) | `sklearn.ensemble.GradientBoostingRegressor` | Best for General Medicine, ENT |
| RF (Random Forest) | `sklearn.ensemble.RandomForestRegressor` | Best for Dental, Orthopaedic |
| KNN | `sklearn.neighbors.KNeighborsRegressor` | Baseline |
| Ridge | `sklearn.linear_model.Ridge` | Baseline |
| DT (Decision Tree) | `sklearn.tree.DecisionTreeRegressor` | Baseline |

Source: Gupta & Sharma (2025), GD Goenka University, Gurugram — Table 1 MAE results.

---

## Persistent memory — how it works

Every time you train, the processed data is saved as `data/session_NNNN.csv`.
When you run `--retrain`, all previous sessions are loaded, merged (duplicates removed), and the model trains on everything combined.

The `models/memory.json` file tracks every session:
- Date and time
- Rows added and total cumulative rows
- Best model and accuracy
- Which GPU was used

This means each new month of data makes the model progressively more accurate without you having to keep track of which files you've used.

---

## Accuracy expectations

| Training data size | Typical accuracy |
|-------------------|-----------------|
| 30–100 rows | 75–82% |
| 100–500 rows | 82–88% |
| 500–2,000 rows | 88–93% |
| 2,000+ rows | 92–97% |

Use `--retrain` each time you add new data to keep improving accuracy over time.
