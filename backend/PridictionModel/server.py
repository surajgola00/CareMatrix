#!/usr/bin/env python3
"""
server.py  —  Patient Influx & Capacity Prediction  —  REST API Server
════════════════════════════════════════════════════════════════════════

Start the server:
  python server.py                      # default: localhost:5000
  python server.py --port 8080
  python server.py --host 0.0.0.0       # expose to network

All endpoints accept and return JSON.
Training accepts multipart/form-data (CSV file upload).

ENDPOINTS
─────────
  GET  /health                  → server status + model info
  GET  /status                  → memory + training history
  GET  /model                   → model details + feature importance
  GET  /specialties             → list of known specialties

  POST /train                   → train on uploaded CSV
  POST /predict                 → predict one date (full capacity output)
  POST /forecast                → multi-day forecast
  POST /capacity                → capacity-only report (no ML prediction needed)
  POST /capacity/bor            → bed occupancy only
  POST /capacity/opd            → OPD load only
  POST /capacity/ed             → emergency load only
  POST /capacity/wait           → waiting times only

  POST /env/update              → live-push environment values (weather etc.)
  GET  /env/current             → read back current live environment
  POST /env/reset               → reset live environment to defaults

  DELETE /memory                → clear all training memory

API docs available at:  GET /docs
"""

import json
import logging
import os
import threading
import traceback
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, Response

import core

# ── App setup ─────────────────────────────────────────────────
app = Flask(__name__)
app.json.sort_keys = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("predictor.api")

# ── In-memory live environment state ──────────────────────────
# Your external API pushes values here via POST /env/update.
# These are merged into every predict/forecast call automatically.
_live_env: dict = {}
_live_env_lock  = threading.Lock()

# Track background training job
_training_job: dict = {"running": False, "progress": [], "result": None, "error": None}
_training_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _cors(response: Response) -> Response:
    """Add CORS headers so your API can call this from any origin."""
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = \
        "Content-Type, Authorization, X-API-Key"
    response.headers["Access-Control-Allow-Methods"] = \
        "GET, POST, PUT, DELETE, OPTIONS"
    return response

@app.after_request
def after_request(response):
    return _cors(response)

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return _cors(Response(status=204))

def ok(data: dict, status: int = 200) -> Response:
    return jsonify({"ok": True,  "data": data}), status

def err(message: str, status: int = 400) -> Response:
    return jsonify({"ok": False, "error": message}), status

def require_model(f):
    """Decorator: return 503 if no model is trained yet."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not core.MODEL_PKL.exists() or not core.STATS_JSON.exists():
            return err("No trained model. POST /train with a CSV file first.",
                       503)
        return f(*args, **kwargs)
    return wrapper

def _merge_env(request_env: dict) -> dict:
    """Merge live env state with per-request env overrides."""
    with _live_env_lock:
        merged = dict(_live_env)
    merged.update(request_env or {})
    return merged


# ══════════════════════════════════════════════════════════════
# HEALTH & INFO
# ══════════════════════════════════════════════════════════════

@app.route("/health", methods=["GET"])
def health():
    """
    Quick health check. Always returns 200 if server is up.

    Response:
      status          : "ok"
      model_ready     : bool
      server_time     : ISO timestamp
      version         : API version string
    """
    model_ready = (core.MODEL_PKL.exists() and core.STATS_JSON.exists())
    return ok({
        "status":       "ok",
        "model_ready":  model_ready,
        "server_time":  datetime.now().isoformat(),
        "version":      "4.0",
        "endpoints":    [
            "GET /health", "GET /status", "GET /model",
            "GET /specialties", "GET /docs",
            "POST /train", "POST /predict", "POST /forecast",
            "POST /capacity", "POST /capacity/bor",
            "POST /capacity/opd", "POST /capacity/ed",
            "POST /capacity/wait",
            "POST /env/update", "GET /env/current", "POST /env/reset",
            "DELETE /memory",
        ],
    })


@app.route("/status", methods=["GET"])
def status():
    """
    Training memory summary and session history.

    Response: see core.get_status() — sessions, total_rows,
              date_range, specialties, training_history, device info.
    """
    return ok(core.get_status())


@app.route("/model", methods=["GET"])
@require_model
def model_info():
    """
    Full model details: accuracy, MAE, feature importance,
    per-specialty routing, capacity defaults.
    """
    return ok(core.get_model_info())


@app.route("/specialties", methods=["GET"])
@require_model
def specialties():
    """
    List specialties in the trained model with their routing info.
    """
    info = core.get_model_info()
    return ok({
        "specialties":  info["facilities"],
        "routing":      info["spec_routing"],
    })


# ══════════════════════════════════════════════════════════════
# TRAINING
# ══════════════════════════════════════════════════════════════

@app.route("/train", methods=["POST"])
def train():
    """
    Train (or retrain) the model on a CSV file.

    Request: multipart/form-data
      file        : (required) CSV file upload
      retrain     : "true" / "false"  — merge with previous sessions
      climate     : semi_arid | tropical | temperate | cold | equatorial
      jobs        : int  — CPU cores (-1 = all)
      async       : "true" — returns immediately, poll GET /train/status
      totalBeds   : int
      bedsOccupied: int
      opdHrs      : float
      edBeds      : int
      edOccupied  : int
      admitRate   : float  (%)
      edRate      : float  (%)
      walkInPct   : float  (%)
      doctors     : int
      counters    : int

    Response (sync):
      session_id, best_model, accuracy_pct, mae, total_rows, facilities, ...
    """
    if "file" not in request.files:
        return err("No CSV file. Send as multipart field 'file'.")

    csv_bytes = request.files["file"].read()
    if not csv_bytes:
        return err("Uploaded file is empty.")

    retrain  = request.form.get("retrain","false").lower() == "true"
    climate  = request.form.get("climate","semi_arid")
    n_jobs   = int(request.form.get("jobs", -1))
    async_   = request.form.get("async","false").lower() == "true"
    from_date= request.form.get("from_date") or request.form.get("from")
    to_date  = request.form.get("to_date")   or request.form.get("to")

    cap = {}
    for field in ["totalBeds","bedsOccupied","opdHrs","edBeds","edOccupied",
                  "admitRate","edRate","walkInPct","phonePct","doctors",
                  "counters"]:
        v = request.form.get(field)
        if v is not None:
            try:
                cap[field] = float(v) if "." in v else int(v)
            except ValueError:
                pass

    if async_:
        def _bg():
            with _training_lock:
                _training_job["running"]  = True
                _training_job["progress"] = []
                _training_job["result"]   = None
                _training_job["error"]    = None

            def _cb(step, total, msg):
                _training_job["progress"].append(
                    {"step": step, "total": total, "message": msg})

            try:
                result = core.run_training(
                    csv_bytes=csv_bytes, retrain=retrain,
                    climate=climate, n_jobs=n_jobs, cap=cap,
                    progress_cb=_cb,
                    from_date=from_date, to_date=to_date)
                with _training_lock:
                    _training_job["result"] = result
            except Exception as e:
                with _training_lock:
                    _training_job["error"] = str(e)
            finally:
                with _training_lock:
                    _training_job["running"] = False

        t = threading.Thread(target=_bg, daemon=True)
        t.start()
        return ok({"message": "Training started in background",
                   "poll": "GET /train/status"}, 202)

    # Synchronous
    try:
        stats = core.run_training(
            csv_bytes=csv_bytes, retrain=retrain,
            climate=climate, n_jobs=n_jobs, cap=cap,
            from_date=from_date, to_date=to_date)
        return ok({
            "session_id":    stats["session_id"],
            "best_model":    stats["best_model"],
            "accuracy_pct":  round(100 - stats["best_mape"], 1),
            "mae":           stats["best_mae"],
            "rmse":          stats["best_rmse"],
            "r2":            stats["best_r2"],
            "total_rows":    stats["total_rows"],
            "facilities":    stats["facilities"],
            "training_time_sec": stats.get("training_time_sec"),
            "gpu_used":      stats.get("gpu_used"),
            "all_results":   stats["all_results"],
            "spec_routing":  stats["spec_info"],
        })
    except Exception as e:
        log.exception("Training failed")
        return err(f"Training failed: {e}", 500)


@app.route("/train/status", methods=["GET"])
def train_status():
    """Poll background training progress."""
    with _training_lock:
        return ok({
            "running":  _training_job["running"],
            "progress": _training_job["progress"],
            "result":   _training_job["result"],
            "error":    _training_job["error"],
        })


# ══════════════════════════════════════════════════════════════
# PREDICTION
# ══════════════════════════════════════════════════════════════

@app.route("/predict", methods=["POST"])
@require_model
def predict():
    """
    Predict OPD patients + full capacity report for one date.

    Request JSON body:
    ┌─────────────────────────────────────────────────────────┐
    │ PREDICTION PARAMETERS                                   │
    │   date         string   "YYYY-MM-DD"  (default: today) │
    │   facility     string   specialty name or "all"         │
    │   season       string   auto|peak|off|rain|cold         │
    │                                                         │
    │ LIVE ENVIRONMENT (from your weather/sensor API)         │
    │   env.temperature   float   °C                          │
    │   env.aqi           float   Air Quality Index           │
    │   env.rainfall      float   mm                          │
    │   env.humidity      float   %                           │
    │   env.hour          float   0–23                        │
    │   env.holiday       int     0 or 1                      │
    │   env.staffing_pct  float   0–100                       │
    │   env.revisit_pct   float   % of avg that are revisits  │
    │   env.lagged        float   yesterday's patient count   │
    │                                                         │
    │ CAPACITY OVERRIDES                                       │
    │   cap.totalBeds     int                                  │
    │   cap.bedsOccupied  int                                  │
    │   cap.opdHrs        float                               │
    │   cap.edBeds        int                                  │
    │   cap.edOccupied    int                                  │
    │   cap.admitRate     float   %                           │
    │   cap.edRate        float   %                           │
    │   cap.counters      int                                  │
    │   cap.doctors       int                                  │
    │   cap.walkInPct     float   %                           │
    │                                                         │
    │ EVENTS                                                   │
    │   events  list of strings:                              │
    │     "holiday"  "festival"  "heatwave"  "flu_peak"       │
    │     "rain_heavy"  "long_weekend"  "epidemic"            │
    │     "mass_event"                                        │
    └─────────────────────────────────────────────────────────┘

    Response: prediction + bed_occupancy + opd_load +
              emergency_load + waiting_times + alerts
    """
    body = request.get_json(silent=True) or {}

    date_str  = body.get("date", datetime.now().strftime("%Y-%m-%d"))
    facility  = body.get("facility", "all")
    season    = body.get("season", "auto")
    env_req   = body.get("env", {})
    cap_req   = body.get("cap", {})
    events    = body.get("events", [])

    # Merge live env state + per-request env overrides
    env = _merge_env(env_req)

    try:
        result = core.predict_one(
            date_str, facility, season,
            env=env, cap_override=cap_req, events=events)
        return ok(result)
    except Exception as e:
        log.exception("Prediction failed")
        return err(f"Prediction failed: {e}", 500)


@app.route("/forecast", methods=["POST"])
@require_model
def forecast():
    """
    Generate multi-day forecast with capacity data.

    Request JSON body:
      days        int     1–365   (default 30)
      facility    string          (default "all")
      start       string  "YYYY-MM-DD"  (default today)
      season      string          (default "auto")
      env         dict    same fields as /predict env
      cap         dict    same fields as /predict cap
      events      list    same as /predict events
      include_capacity  bool  (default true)

    Response: list of daily predictions, each with full
              bed_occupancy, opd_load, emergency_load, waiting_times
    """
    body = request.get_json(silent=True) or {}

    days     = min(int(body.get("days", 30)), 365)
    facility = body.get("facility", "all")
    start    = body.get("start", None)
    season   = body.get("season", "auto")
    env_req  = body.get("env", {})
    cap_req  = body.get("cap", {})
    events   = body.get("events", [])

    env = _merge_env(env_req)

    try:
        results = core.forecast_range(
            days, facility, start,
            env=env, cap_override=cap_req, events=events)

        # Build compact summary array
        summary = []
        for r in results:
            p   = r["prediction"]
            bor = r["bed_occupancy"]
            opd = r["opd_load"]
            ed  = r["emergency_load"]
            wt  = r["waiting_times"]
            summary.append({
                "date":               p["date"],
                "day":                datetime.strptime(
                                          p["date"], "%Y-%m-%d"
                                      ).strftime("%a"),
                "predicted":          p["predicted"],
                "low":                p["low"],
                "high":               p["high"],
                "confidence_pct":     p["confidence_pct"],
                "model_used":         p["model_used"],
                "bor_current_pct":    bor["current_bor_pct"],
                "bor_projected_pct":  bor["projected_bor_pct"],
                "new_admissions":     bor["new_admissions"],
                "beds_free_after":    bor["beds_free_after"],
                "bor_status":         bor["status"],
                "opd_load_per_ctr":   opd["patients_per_hr_per_ctr"],
                "counters_needed":    opd["counters_needed"],
                "counter_status":     opd["counter_status"],
                "ed_util_pct":        ed["utilisation_pct"],
                "ed_new_patients":    ed["new_ed_patients"],
                "ed_status":          ed["status"],
                "wait_registration":  wt["registration"],
                "wait_consultation":  wt["consultation"],
                "wait_total_min":     wt["total"],
                "alerts":             r["alerts"],
            })

        return ok({
            "days":          days,
            "facility":      facility,
            "start":         (results[0]["prediction"]["date"]
                              if results else None),
            "forecast":      summary,
            "full_results":  results,
        })
    except Exception as e:
        log.exception("Forecast failed")
        return err(f"Forecast failed: {e}", 500)


# ══════════════════════════════════════════════════════════════
# CAPACITY ENDPOINTS
# ══════════════════════════════════════════════════════════════

def _get_cap_and_count(body: dict):
    """Extract predicted count + cap dict from request body."""
    predicted = body.get("predicted")
    if predicted is None:
        # Try to predict now
        date_str = body.get("date", datetime.now().strftime("%Y-%m-%d"))
        facility = body.get("facility", "all")
        env_req  = body.get("env", {})
        env      = _merge_env(env_req)
        if core.MODEL_PKL.exists():
            res = core.predict_one(
                date_str, facility,
                env=env, cap_override=body.get("cap", {}))
            predicted = res["prediction"]["predicted"]
        else:
            predicted = int(body.get("predicted_fallback", 50))
    cap = {**core.load_memory().get("capacity_defaults", {}),
           **body.get("cap", {})}
    return int(predicted), cap


@app.route("/capacity", methods=["POST"])
@require_model
def capacity_full():
    """
    Full capacity report for a given patient count.

    Request JSON:
      predicted     int     patient count (or provide date+facility to auto-predict)
      date          string  used if predicted not given
      facility      string  used if predicted not given
      env           dict    environment overrides
      cap           dict    capacity overrides

    Response: bor + opd_load + ed_load + wait_times + alerts
    """
    body = request.get_json(silent=True) or {}
    try:
        predicted, cap = _get_cap_and_count(body)
        env = _merge_env(body.get("env", {}))
        return ok({
            "predicted":         predicted,
            "bed_occupancy":     core.calc_bor(predicted, cap),
            "opd_load":          core.calc_opd_load(predicted, cap),
            "emergency_load":    core.calc_ed_load(predicted, cap),
            "waiting_times":     core.calc_wait_times(predicted, cap, env),
        })
    except Exception as e:
        return err(str(e), 500)


@app.route("/capacity/bor", methods=["POST"])
def capacity_bor():
    """
    Bed occupancy only.

    Request JSON:
      predicted     int      OPD patient count
      cap.totalBeds    int   total sanctioned beds
      cap.bedsOccupied int   beds occupied right now
      cap.admitRate    float OPD→IPD admission rate %
    """
    body = request.get_json(silent=True) or {}
    try:
        predicted, cap = _get_cap_and_count(body)
        return ok(core.calc_bor(predicted, cap))
    except Exception as e:
        return err(str(e), 500)


@app.route("/capacity/opd", methods=["POST"])
def capacity_opd():
    """
    OPD load only.

    Request JSON:
      predicted      int    OPD patient count
      cap.opdHrs     float  OPD hours per day
      cap.counters   int    registration counters open
      cap.doctors    int    doctors on duty
    """
    body = request.get_json(silent=True) or {}
    try:
        predicted, cap = _get_cap_and_count(body)
        return ok(core.calc_opd_load(predicted, cap))
    except Exception as e:
        return err(str(e), 500)


@app.route("/capacity/ed", methods=["POST"])
def capacity_ed():
    """
    Emergency department load only.

    Request JSON:
      predicted       int   OPD patient count
      cap.edBeds      int   total ED beds
      cap.edOccupied  int   ED beds occupied now
      cap.edRate      float OPD→ED transfer rate %
    """
    body = request.get_json(silent=True) or {}
    try:
        predicted, cap = _get_cap_and_count(body)
        return ok(core.calc_ed_load(predicted, cap))
    except Exception as e:
        return err(str(e), 500)


@app.route("/capacity/wait", methods=["POST"])
def capacity_wait():
    """
    Waiting-time estimates only.

    Request JSON:
      predicted         int    OPD patient count
      env.staffing_pct  float  staff availability %
      cap.opdHrs        float
      cap.counters      int
      cap.doctors       int
      cap.walkInPct     float  walk-in patient %
    """
    body = request.get_json(silent=True) or {}
    try:
        predicted, cap = _get_cap_and_count(body)
        env = _merge_env(body.get("env", {}))
        return ok(core.calc_wait_times(predicted, cap, env))
    except Exception as e:
        return err(str(e), 500)


# ══════════════════════════════════════════════════════════════
# LIVE ENVIRONMENT  (your weather/sensor API pushes here)
# ══════════════════════════════════════════════════════════════

@app.route("/env/update", methods=["POST"])
def env_update():
    """
    Push live environment values that will be automatically applied
    to every subsequent /predict and /forecast call.

    Your weather API / IoT integration calls this endpoint.

    Request JSON — any subset of:
    ┌────────────────────────────────────────────────────────┐
    │  temperature    float   Ambient temperature °C         │
    │  aqi            float   Air Quality Index (0–500)      │
    │  rainfall       float   Daily precipitation mm         │
    │  humidity       float   Relative humidity %            │
    │  wind_speed     float   km/h  (informational)          │
    │  hour           float   Current hour 0–23              │
    │  holiday        int     1 = public holiday, 0 = normal │
    │  staffing_pct   float   Staff availability 0–100 %     │
    │  revisit_pct    float   Revisit patients as % of mean  │
    │  lagged         float   Yesterday's patient count      │
    │  source         string  Label for the data source      │
    │  timestamp      string  ISO timestamp of the reading   │
    └────────────────────────────────────────────────────────┘

    Response: confirmed stored values + timestamp
    """
    body = request.get_json(silent=True) or {}

    ALLOWED = {
        "temperature", "aqi", "rainfall", "humidity", "wind_speed",
        "hour", "holiday", "staffing_pct", "revisit_pct", "lagged",
        "source", "timestamp",
    }

    updated = {}
    with _live_env_lock:
        for k, v in body.items():
            if k in ALLOWED:
                _live_env[k] = v
                updated[k] = v

    if not updated:
        return err("No recognised environment fields. "
                   "Valid fields: " + ", ".join(sorted(ALLOWED)))

    with _live_env_lock:
        current = dict(_live_env)

    log.info(f"Live env updated: {updated}")
    return ok({
        "updated_fields":  updated,
        "current_env":     current,
        "server_time":     datetime.now().isoformat(),
    })


@app.route("/env/current", methods=["GET"])
def env_current():
    """
    Read back the current live environment state.

    Response: all currently stored env values + last update time.
    """
    with _live_env_lock:
        current = dict(_live_env)
    return ok({
        "env":         current,
        "field_count": len(current),
        "server_time": datetime.now().isoformat(),
    })


@app.route("/env/reset", methods=["POST"])
def env_reset():
    """
    Clear all stored live environment values.
    Subsequent predictions will use model defaults.

    Request JSON (optional):
      fields: ["temperature","aqi"]  — reset only specific fields
                                       omit to reset everything
    """
    body   = request.get_json(silent=True) or {}
    fields = body.get("fields")

    with _live_env_lock:
        if fields:
            for f in fields:
                _live_env.pop(f, None)
            cleared = fields
        else:
            cleared = list(_live_env.keys())
            _live_env.clear()

    return ok({"cleared_fields": cleared,
               "message": "Environment reset"})


# ══════════════════════════════════════════════════════════════
# MEMORY MANAGEMENT
# ══════════════════════════════════════════════════════════════

@app.route("/memory", methods=["DELETE"])
def delete_memory():
    """
    Clear all training memory, session data, and model files.

    Request JSON:
      confirm: true
    """
    body = request.get_json(silent=True) or {}
    if not body.get("confirm", False):
        return err("Send {\"confirm\": true} to clear memory.")
    try:
        result = core.clear_memory()
        return ok(result)
    except Exception as e:
        return err(str(e), 500)


# ══════════════════════════════════════════════════════════════
# DATA QUERY ENDPOINTS — inspect stored training data
# ══════════════════════════════════════════════════════════════

@app.route("/data", methods=["GET","POST"])
def data_query():
    """
    Query all stored training data with optional filters.

    GET params or POST JSON body:
      from_date   string  "YYYY-MM-DD"
      to_date     string  "YYYY-MM-DD"
      facility    string  specialty name or "all"
      summary     bool    true = daily aggregates, false = every row (default: true)

    Response:
      rows, summary stats, data array
    """
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
    else:
        body = request.args

    from_date = body.get("from_date") or body.get("from")
    to_date   = body.get("to_date")   or body.get("to")
    facility  = body.get("facility")
    summary   = str(body.get("summary","true")).lower() != "false"

    if facility and facility.lower() == "all":
        facility = None

    try:
        result = core.get_data_range(
            from_date=from_date, to_date=to_date,
            facility=facility, summary=summary)
        return ok(result)
    except Exception as e:
        return err(str(e), 500)


@app.route("/data/<date_str>", methods=["GET","POST"])
def data_for_date(date_str: str):
    """
    Get stored data AND the model's prediction for one specific date.

    URL: /data/2025-08-15
    GET params or POST JSON:
      facility  string  specialty or "all"

    Response:
      actual_data  — stored CSV rows for this date
      prediction   — model's prediction for comparison
      stored_rows  — count of matching records
    """
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
    else:
        body = request.args

    facility = body.get("facility")
    if facility and facility.lower() == "all":
        facility = None

    # Validate date format
    try:
        pd.to_datetime(date_str)
    except Exception:
        return err(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")

    try:
        result = core.get_data_for_date(date_str, facility)
        return ok(result)
    except Exception as e:
        return err(str(e), 500)


@app.route("/data/export", methods=["GET","POST"])
def data_export():
    """
    Export all stored training data as a downloadable CSV.

    GET params or POST JSON:
      from_date  string
      to_date    string
      facility   string
      filename   string  custom filename (optional)

    Response:
      path — path of saved CSV in exports/
      rows — number of rows exported
    """
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
    else:
        body = request.args

    from_date = body.get("from_date") or body.get("from")
    to_date   = body.get("to_date")   or body.get("to")
    facility  = body.get("facility")
    if facility and facility.lower() == "all":
        facility = None

    try:
        path = core.export_all_data(
            facility=facility, from_date=from_date, to_date=to_date)
        import pandas as pd_
        rows = len(pd_.read_csv(path))
        return ok({"path": path, "rows": rows,
                   "message": f"Exported {rows:,} rows"})
    except Exception as e:
        return err(str(e), 500)


@app.route("/storage", methods=["GET"])
def storage_info():
    """
    Show all local storage files — no database is used.

    Response:
      storage_type    "local_files_only"
      database_used   false
      total_size_mb
      files           list of all files with size + modified date
      formats_used    what format each type of data is stored in
    """
    return ok(core.get_storage_info())


# ══════════════════════════════════════════════════════════════
# API DOCUMENTATION  (inline)
# ══════════════════════════════════════════════════════════════

@app.route("/docs", methods=["GET"])
def docs():
    """Returns the full API parameter reference as JSON."""
    return jsonify({
        "title":   "Patient Influx & Capacity Prediction API",
        "version": "4.0",
        "base_url": "http://localhost:5000",

        "env_fields": {
            "temperature":  {"type":"float","unit":"°C","effect":"Raises/lowers predicted count. >39°C = +10% respiratory load"},
            "aqi":          {"type":"float","unit":"AQI 0-500","effect":">100=+4%, >150=+9%, >200=+18% patients"},
            "rainfall":     {"type":"float","unit":"mm","effect":">20mm=-7%, >50mm=-15% footfall"},
            "humidity":     {"type":"float","unit":"%","effect":">85% slightly boosts AQI effect, +5% patients"},
            "wind_speed":   {"type":"float","unit":"km/h","effect":"Informational only"},
            "hour":         {"type":"float","range":"0-23","effect":"Intraday profile weighting"},
            "holiday":      {"type":"int","values":"0 or 1","effect":"1 = apply holiday multiplier (~-28%)"},
            "staffing_pct": {"type":"float","range":"0-100","effect":"Scales doctors on duty, raises wait times if <100"},
            "revisit_pct":  {"type":"float","unit":"% of mean","effect":"Paper top-feature for Dental & Gen. Medicine"},
            "lagged":       {"type":"float","unit":"patient count","effect":"Paper top-feature for all specialties — yesterday's count"},
        },

        "cap_fields": {
            "totalBeds":    {"type":"int","default":100,"effect":"BOR denominator"},
            "bedsOccupied": {"type":"int","default":72,"effect":"BOR starting snapshot"},
            "admitRate":    {"type":"float","unit":"%","default":8,"effect":"OPD→IPD admission rate"},
            "opdHrs":       {"type":"float","default":6,"effect":"OPD operating hours/day"},
            "counters":     {"type":"int","default":3,"effect":"Registration counters open"},
            "doctors":      {"type":"int","default":5,"effect":"Doctors on duty"},
            "edBeds":       {"type":"int","default":20,"effect":"ED bed capacity"},
            "edOccupied":   {"type":"int","default":12,"effect":"ED beds occupied now"},
            "edRate":       {"type":"float","unit":"%","default":3,"effect":"OPD→ED transfer rate"},
            "walkInPct":    {"type":"float","unit":"%","default":36,"effect":"Walk-in % affects wait clustering"},
        },

        "events": {
            "holiday":     -18,
            "festival":    +13,
            "heatwave":    +25,
            "flu_peak":    +30,
            "rain_heavy":  -14,
            "long_weekend":-20,
            "epidemic":    +35,
            "mass_event":  +10,
        },

        "season_values": ["auto","peak","off","rain","cold"],

        "climate_values": ["semi_arid","tropical","temperate","cold","equatorial"],

        "example_predict_request": {
            "date":     "2025-08-15",
            "facility": "General Medicine",
            "season":   "auto",
            "env": {
                "temperature": 38,
                "aqi":         145,
                "rainfall":    0,
                "humidity":    55,
                "staffing_pct":85,
                "lagged":      52,
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
            },
            "events": ["flu_peak"],
        },

        "example_env_update": {
            "temperature": 36.5,
            "aqi":         122,
            "rainfall":    0,
            "humidity":    48,
            "staffing_pct":90,
            "lagged":      47,
            "source":      "openweathermap_api",
            "timestamp":   "2025-08-15T08:00:00",
        },
    })


# ══════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ══════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return err(f"Endpoint not found. See GET /docs", 404)

@app.errorhandler(405)
def method_not_allowed(e):
    return err(f"Method not allowed on this endpoint.", 405)

@app.errorhandler(500)
def internal_error(e):
    return err(f"Internal server error: {e}", 500)


# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Patient Influx Prediction API Server")
    ap.add_argument("--host",  default="127.0.0.1",
                    help="Host to bind (0.0.0.0 for network access)")
    ap.add_argument("--port",  type=int, default=5000)
    ap.add_argument("--debug", action="store_true",
                    help="Enable Flask debug mode (dev only)")
    args = ap.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Patient Influx & Capacity Prediction — API Server           ║
╠══════════════════════════════════════════════════════════════╣
║  URL       : http://{args.host}:{args.port}
║  Docs      : http://{args.host}:{args.port}/docs
║  Health    : http://{args.host}:{args.port}/health
╚══════════════════════════════════════════════════════════════╝
""")

    app.run(host=args.host, port=args.port, debug=args.debug,
            threaded=True)
