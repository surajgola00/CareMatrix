# Patient Influx & Capacity Prediction — API Parameter Reference
## Every input your API must provide, and every output returned

---

## Starting the server

```bash
python server.py                        # localhost:5000
python server.py --port 8080            # custom port
python server.py --host 0.0.0.0         # expose to your network / other APIs
```

---

## Architecture

```
Your API / Weather API / IoT
        │
        ▼  HTTP JSON
  server.py  (Flask REST)
        │
        ▼  Python calls
    core.py   (ML engine)
        │
        ▼
  models/ensemble.pkl  (trained models)
  models/stats.json    (learned patterns)
  models/memory.json   (session history)
```

---

## Endpoint Index

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Server alive check |
| GET | `/status` | Training memory + history |
| GET | `/model` | Model accuracy + feature importance |
| GET | `/specialties` | List trained specialties |
| GET | `/docs` | Full parameter reference (JSON) |
| POST | `/train` | Train on CSV file |
| GET | `/train/status` | Poll async training progress |
| POST | `/predict` | Predict one date (full output) |
| POST | `/forecast` | Multi-day forecast |
| POST | `/capacity` | Full capacity report for a count |
| POST | `/capacity/bor` | Bed occupancy only |
| POST | `/capacity/opd` | OPD load only |
| POST | `/capacity/ed` | Emergency load only |
| POST | `/capacity/wait` | Waiting times only |
| POST | `/env/update` | **Push live weather/sensor values** |
| GET | `/env/current` | Read stored environment values |
| POST | `/env/reset` | Clear stored environment |
| DELETE | `/memory` | Wipe all training memory |

---

## POST `/env/update` — Live environment push

**This is the main endpoint your API calls to inject live data.**
Values are stored server-side and automatically merged into every
subsequent `/predict` and `/forecast` call until reset.

### Request body (JSON) — all fields optional

```json
{
  "temperature":  36.5,
  "aqi":          122,
  "rainfall":     0,
  "humidity":     48,
  "wind_speed":   12,
  "hour":         9,
  "holiday":      0,
  "staffing_pct": 90,
  "revisit_pct":  30,
  "lagged":       47,
  "source":       "openweathermap_api",
  "timestamp":    "2025-08-15T08:00:00"
}
```

### Field definitions

| Field | Type | Unit | Default | Effect on prediction |
|-------|------|------|---------|---------------------|
| `temperature` | float | °C | 25 | >39°C: +10% patients + 1.2% per extra degree. <5°C: +8% |
| `aqi` | float | AQI 0–500 | 80 | >100: +4%. >150: +9%. >200: +18% |
| `rainfall` | float | mm/day | 0 | >20mm: −7% footfall. >50mm: −15% |
| `humidity` | float | % | 60 | >85%: pushes AQI up 8%, +5% respiratory patients |
| `wind_speed` | float | km/h | — | Informational only, stored but not used in ML |
| `hour` | float | 0–23 | 10 | Shifts intraday weighting (morning shift peak) |
| `holiday` | int | 0 or 1 | 0 | 1 = applies learned holiday multiplier (~−28%) |
| `staffing_pct` | float | % | 100 | Scales doctors on duty. Raises wait times if <100 |
| `revisit_pct` | float | % of mean | 30 | Paper top-feature for Dental & General Medicine |
| `lagged` | float | patient count | mean | Paper top-feature for all specialties — yesterday's count |
| `source` | string | — | — | Label for auditing (e.g. "openweathermap", "manual") |
| `timestamp` | string | ISO 8601 | — | Timestamp of the reading |

### Response

```json
{
  "ok": true,
  "data": {
    "updated_fields": { "temperature": 36.5, "aqi": 122 },
    "current_env":    { "temperature": 36.5, "aqi": 122, "humidity": 48 },
    "server_time":    "2025-08-15T09:00:00"
  }
}
```

---

## POST `/predict` — Full prediction

### Request body (JSON)

```json
{
  "date":     "2025-08-15",
  "facility": "General Medicine",
  "season":   "auto",
  "env": {
    "temperature":  38,
    "aqi":          145,
    "rainfall":     0,
    "humidity":     55,
    "staffing_pct": 85,
    "lagged":       52
  },
  "cap": {
    "totalBeds":    150,
    "bedsOccupied": 110,
    "opdHrs":       6,
    "counters":     4,
    "doctors":      6,
    "edBeds":       25,
    "edOccupied":   15,
    "admitRate":    9,
    "edRate":       4,
    "walkInPct":    40
  },
  "events": ["flu_peak"]
}
```

### `date` field
| Value | Format |
|-------|--------|
| Any date string | `"YYYY-MM-DD"` e.g. `"2025-08-15"` |
| Default | Today's date |

### `facility` field
| Value | Meaning |
|-------|---------|
| `"all"` | Combined prediction across all specialties |
| `"General Medicine"` | Specific specialty (must match training data) |
| `"Dental"` / `"ENT"` / `"Orthopaedic"` / etc. | Any specialty from your CSV |

### `season` field
| Value | Multiplier | Use when |
|-------|-----------|----------|
| `"auto"` | Learned from data | Default — uses actual month |
| `"peak"` | ×1.18 | Manually override to peak season |
| `"off"` | ×0.88 | Override to off-peak |
| `"rain"` | ×1.04 | Override to monsoon / rainy season |
| `"cold"` | ×1.10 | Override to cold season |

### `env` fields — per-request override (same as `/env/update`)
Provided here override the stored live env for this request only.

### `cap` fields — capacity parameters

| Field | Type | Default | What it controls |
|-------|------|---------|-----------------|
| `totalBeds` | int | 100 | Total sanctioned IPD beds |
| `bedsOccupied` | int | 72 | IPD beds occupied RIGHT NOW |
| `admitRate` | float | 8 | % of OPD patients admitted to IPD |
| `opdHrs` | float | 6 | OPD operating hours per day |
| `counters` | int | 3 | Registration counters open |
| `doctors` | int | 5 | Doctors on duty |
| `edBeds` | int | 20 | Emergency department bed capacity |
| `edOccupied` | int | 12 | ED beds occupied right now |
| `edRate` | float | 3 | % of OPD patients transferred to ED |
| `walkInPct` | float | 36 | % of patients arriving as walk-ins |

### `events` field — list of event flag strings

| Flag | % Effect | Description |
|------|----------|-------------|
| `"holiday"` | −18% | Public holiday — reduced turnout |
| `"festival"` | +13% | Festival / Mela — increased load |
| `"heatwave"` | +25% | Heat wave — heat illness surge |
| `"flu_peak"` | +30% | Flu season peak — respiratory surge |
| `"rain_heavy"` | −14% | Heavy rain — reduced footfall |
| `"long_weekend"` | −20% | Long weekend — deferred visits |
| `"epidemic"` | +35% | Outbreak / epidemic — surge |
| `"mass_event"` | +10% | Nearby sporting / political event |

Multiple events stack multiplicatively.

### Response

```json
{
  "ok": true,
  "data": {
    "prediction": {
      "date":            "2025-08-15",
      "facility":        "General Medicine",
      "predicted":       58,
      "low":             53,
      "high":            63,
      "confidence_pct":  87.2,
      "model_used":      "GBM",
      "ml_blend_pct":    75.0,
      "season_used":     "auto"
    },
    "bed_occupancy": {
      "total_beds":          150,
      "current_occupied":    110,
      "new_admissions":      5,
      "projected_occupied":  115,
      "beds_free_now":       40,
      "beds_free_after":     35,
      "current_bor_pct":     73.3,
      "projected_bor_pct":   76.7,
      "over_capacity":       false,
      "status":              "low",
      "nhm_target_pct":      80
    },
    "opd_load": {
      "patients_per_hour":       9.7,
      "patients_per_hr_per_ctr": 2.4,
      "patients_per_doctor":     9.7,
      "counters_available":      4,
      "counters_needed":         1,
      "doctors_available":       6,
      "doctors_needed":          1,
      "counter_status":          "low",
      "doctor_status":           "ok",
      "counter_util_pct":        12.0,
      "nhm_ctr_norm_min":        12,
      "nhm_ctr_norm_max":        20
    },
    "emergency_load": {
      "ed_beds":              25,
      "ed_occupied_now":      15,
      "opd_transfers":        2,
      "direct_walkins":       10,
      "new_ed_patients":      12,
      "projected_occupied":   25,
      "utilisation_pct":      100.0,
      "triage_immediate":     1,
      "triage_urgent":        3,
      "triage_non_urgent":    8,
      "triage_observation":   0,
      "status":               "critical"
    },
    "waiting_times": {
      "transport":      8,
      "registration":   7,
      "triage":         5,
      "consultation":   42,
      "pharmacy":       9,
      "billing":        14,
      "total":          85,
      "bed_delay_mult": 1.0,
      "effective_doctors": 5
    },
    "alerts": [
      {
        "level":   "danger",
        "code":    "ed_critical",
        "message": "ED at critical capacity — activate surge/diversion protocol"
      }
    ],
    "inputs_used": {
      "env":    { "temperature": 38, "aqi": 145 },
      "cap":    { "totalBeds": 150, "bedsOccupied": 110 },
      "events": ["flu_peak"],
      "season": "auto"
    }
  }
}
```

---

## POST `/forecast` — Multi-day forecast

### Request body

```json
{
  "days":     30,
  "facility": "all",
  "start":    "2025-08-15",
  "season":   "auto",
  "env":      { "temperature": 35, "aqi": 110 },
  "cap":      { "totalBeds": 150, "bedsOccupied": 110 },
  "events":   []
}
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `days` | int | 30 | 1–365 |
| `facility` | string | "all" | |
| `start` | string | today | "YYYY-MM-DD" |
| `season` | string | "auto" | |
| `env` | dict | live env | same fields as /predict |
| `cap` | dict | stored defaults | same fields as /predict |
| `events` | list | [] | same as /predict |

### Response (summary per day)
Each item in `forecast` array contains:

| Field | Description |
|-------|-------------|
| `date` | ISO date |
| `day` | Mon/Tue/etc. |
| `predicted` | Patient count |
| `low` / `high` | Confidence range |
| `confidence_pct` | % |
| `model_used` | Algorithm name |
| `bor_current_pct` | IPD BOR before admissions |
| `bor_projected_pct` | IPD BOR after admissions |
| `new_admissions` | New IPD admits expected |
| `beds_free_after` | Free beds at end of day |
| `bor_status` | target / low / critical |
| `opd_load_per_ctr` | Pts/hr/counter |
| `counters_needed` | Counters required |
| `counter_status` | ok / over / low |
| `ed_util_pct` | ED utilisation % |
| `ed_new_patients` | New ED arrivals |
| `ed_status` | normal / moderate / high / critical |
| `wait_registration` | min |
| `wait_consultation` | min |
| `wait_total_min` | min |
| `alerts` | list of alert objects |

---

## POST `/train` — Upload and train

### Request: `multipart/form-data`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `file` | CSV file | ✓ | See CSV format below |
| `retrain` | string | | "true" to merge with memory |
| `climate` | string | | semi_arid / tropical / temperate / cold / equatorial |
| `jobs` | int | | CPU cores (-1 = all) |
| `async` | string | | "true" for background training; poll GET /train/status |
| `totalBeds` | int | | Capacity defaults |
| `bedsOccupied` | int | | |
| `opdHrs` | float | | |
| `edBeds` | int | | |
| `edOccupied` | int | | |
| `admitRate` | float | | |
| `edRate` | float | | |
| `walkInPct` | float | | |
| `doctors` | int | | |
| `counters` | int | | |

### CSV format

**Required columns** (name auto-detected):

| Column | Accepted names |
|--------|---------------|
| Date | date, day, dt, timestamp, visit_date |
| Patients | patients, count, visits, arrivals, total, cases, attend, volume, opd |

**Optional columns** (auto-detected if present):

| Column | Accepted names | Effect |
|--------|---------------|--------|
| Specialty | specialty, facility, dept, site, unit, ward, clinic | Per-specialty models |
| Hour | hour, hh, hr, time | Intraday learning |
| Temperature | temperature, temp, celsius, tmax | Feature F8 |
| AQI | aqi, air, pm2, pm10 | Feature F9 |
| Rainfall | rainfall, rain, precip, mm | Feature F10 |
| Holiday | holiday, hol, flag, closed | Feature F5 |
| Revisit | revisit, repeat, return, follow | Feature F4 ★ |
| Lagged | lagged, yesterday, prev, prior | Feature F3 ★ |
| Doctors | doctors, doc, physician, staff | Feature F12 |
| Counters | counters, counter, window, desk | Capacity learning |
| Beds occupied | bed_occ, beds_used, ipd_occ, census | BOR baseline |

---

## POST `/capacity` — Capacity report for a known count

Use when you already have a patient count and want the capacity breakdown.

### Request

```json
{
  "predicted": 85,
  "env": { "staffing_pct": 80 },
  "cap": {
    "totalBeds":    200,
    "bedsOccupied": 160,
    "admitRate":    10,
    "counters":     5,
    "doctors":      8,
    "edBeds":       30,
    "edOccupied":   20,
    "edRate":       4,
    "walkInPct":    45
  }
}
```

If `predicted` is omitted, also accepts `date` + `facility` to auto-predict.

---

## Error response format

```json
{
  "ok":    false,
  "error": "No trained model. POST /train with a CSV file first."
}
```

| HTTP code | Meaning |
|-----------|---------|
| 200 | Success |
| 202 | Accepted (async training started) |
| 400 | Bad request (missing/invalid parameters) |
| 503 | Model not trained yet |
| 500 | Internal error |

---

## Quick integration example (Python)

```python
import requests

BASE = "http://localhost:5000"

# 1. Push live weather from your weather API
requests.post(f"{BASE}/env/update", json={
    "temperature":  37.2,
    "aqi":          138,
    "rainfall":     0,
    "humidity":     52,
    "staffing_pct": 88,
    "lagged":       54,    # yesterday's actual count
    "source":       "openweathermap",
})

# 2. Get today's full prediction (uses stored env automatically)
r = requests.post(f"{BASE}/predict", json={
    "date":     "2025-08-15",
    "facility": "all",
    "cap": {
        "totalBeds":    150,
        "bedsOccupied": 108,
    }
})
data = r.json()["data"]

print(f"Predicted: {data['prediction']['predicted']} patients")
print(f"BOR after admissions: {data['bed_occupancy']['projected_bor_pct']}%")
print(f"ED utilisation: {data['emergency_load']['utilisation_pct']}%")
print(f"Total wait: {data['waiting_times']['total']} min")
for alert in data["alerts"]:
    print(f"[{alert['level'].upper()}] {alert['message']}")
```

---

## Integration example (Node.js / your API)

```javascript
const BASE = "http://localhost:5000";

// Push weather data
await fetch(`${BASE}/env/update`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    temperature:  36.8,
    aqi:          115,
    rainfall:     0,
    humidity:     50,
    staffing_pct: 90,
    lagged:       49,
  })
});

// Get prediction
const res  = await fetch(`${BASE}/predict`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    date:     "2025-08-15",
    facility: "General Medicine",
    cap: { totalBeds: 150, bedsOccupied: 108 }
  })
});
const { data } = await res.json();
console.log(data.prediction.predicted);     // OPD count
console.log(data.bed_occupancy);            // BOR panel
console.log(data.waiting_times.consultation); // wait min
```
